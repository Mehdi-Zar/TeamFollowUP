"""HTTPS / TLS certificate primitives.

The application terminates TLS itself (uvicorn runs with an SSL context). The
active server certificate, its private key and the admin-managed CA store are
persisted in the database as the single source of truth (see ``tlsconfig.py``);
at boot and on every change they are *materialised* to PEM files under
``CERT_DIR`` and the live ``SSLContext`` is hot-reloaded, so new TLS handshakes
pick up a freshly uploaded certificate without restarting the container.

This module holds only the low-level crypto + file + context plumbing. The
DB-backed orchestration (import PEM/PFX, regenerate self-signed, add/remove CA)
lives in ``tlsconfig.py``.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import ssl
import threading
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtensionOID, NameOID

log = logging.getLogger("trt.tls")

# --- Filesystem layout -------------------------------------------------------
# CERT_DIR is a plain scratch directory: the DB is authoritative, these files
# are just what uvicorn's SSLContext reads. Safe to be an ephemeral volume.
CERT_DIR = os.environ.get("CERT_DIR") or os.path.join(os.path.dirname(__file__), "..", "certs")
CERT_DIR = os.path.abspath(CERT_DIR)
FULLCHAIN_PATH = os.path.join(CERT_DIR, "server_fullchain.pem")
KEY_PATH = os.path.join(CERT_DIR, "server.key")

# The live SSLContext used by the running server, so uploads can hot-reload it.
_live_context: ssl.SSLContext | None = None
_lock = threading.Lock()


# =============================================================================
# Self-signed generation
# =============================================================================

def generate_self_signed(common_name: str = "localhost",
                         sans: list[str] | None = None,
                         days: int = 825) -> tuple[str, str]:
    """Return ``(cert_pem, key_pem)`` for a fresh self-signed RSA-2048 certificate.

    ``sans`` are Subject Alternative Names (DNS names and/or IP addresses). The
    CN is always mirrored into the SAN list because modern clients ignore CN.
    """
    import ipaddress

    sans = list(sans or [])
    if common_name and common_name not in sans:
        sans.insert(0, common_name)
    if not sans:
        sans = ["localhost"]

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name or "localhost"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Tribe Cockpit"),
    ])

    san_entries: list[x509.GeneralName] = []
    for name in sans:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            san_entries.append(x509.DNSName(name))

    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(minutes=5))
        .not_valid_after(now + _dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


# =============================================================================
# Parsing / validation helpers
# =============================================================================

def _load_first_cert(pem: str) -> x509.Certificate:
    """Parse the first certificate from a PEM string (raises on invalid PEM)."""
    return x509.load_pem_x509_certificate(pem.encode())


def _load_all_certs(pem: str) -> list[x509.Certificate]:
    """Parse every certificate from a concatenated PEM bundle."""
    return list(x509.load_pem_x509_certificates(pem.encode()))


def _fingerprint(cert: x509.Certificate) -> str:
    """Colon-separated uppercase SHA-256 fingerprint (stable identity of a cert)."""
    return cert.fingerprint(hashes.SHA256()).hex(":").upper()


def _name_str(name: x509.Name) -> str:
    """Human label for an X.509 name: the Common Name, else the full RFC4514 DN."""
    try:
        cn = name.get_attributes_for_oid(NameOID.COMMON_NAME)
        if cn:
            return cn[0].value
    except Exception:
        pass
    return name.rfc4514_string()


def _sans(cert: x509.Certificate) -> list[str]:
    """Subject Alternative Names (DNS + IP) as strings; [] if the extension is absent."""
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        out: list[str] = []
        for gn in ext.value:
            if isinstance(gn, x509.DNSName):
                out.append(gn.value)
            elif isinstance(gn, x509.IPAddress):
                out.append(str(gn.value))
        return out
    except x509.ExtensionNotFound:
        return []


def _is_ca(cert: x509.Certificate) -> bool:
    """True if BasicConstraints marks this cert as a CA (no extension → not a CA)."""
    try:
        bc = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        return bool(bc.value.ca)
    except x509.ExtensionNotFound:
        return False


def cert_info(pem: str) -> dict:
    """Human/machine-readable summary of the first certificate in ``pem``."""
    cert = _load_first_cert(pem)
    nb = cert.not_valid_before_utc
    na = cert.not_valid_after_utc
    now = _dt.datetime.now(_dt.timezone.utc)
    is_ca = _is_ca(cert)
    self_signed = cert.subject == cert.issuer
    return {
        "subject": _name_str(cert.subject),
        "issuer": _name_str(cert.issuer),
        "subject_dn": cert.subject.rfc4514_string(),
        "issuer_dn": cert.issuer.rfc4514_string(),
        "serial": format(cert.serial_number, "x"),
        "not_before": nb.isoformat(),
        "not_after": na.isoformat(),
        "days_remaining": (na - now).days,
        "expired": now > na,
        "not_yet_valid": now < nb,
        "sans": _sans(cert),
        "fingerprint_sha256": _fingerprint(cert),
        "is_ca": is_ca,
        "self_signed": self_signed,
        "signature_algorithm": cert.signature_hash_algorithm.name if cert.signature_hash_algorithm else "unknown",
    }


def ca_kind(pem: str) -> str:
    """Classify a CA certificate as ``root`` (self-signed CA) or ``intermediate``."""
    cert = _load_first_cert(pem)
    if not _is_ca(cert):
        # Not a CA at all; caller decides whether to reject. Treat as intermediate.
        return "intermediate"
    return "root" if cert.subject == cert.issuer else "intermediate"


def normalize_cert_pem(pem: str) -> str:
    """Re-serialize a single certificate to canonical PEM (raises on garbage)."""
    return _load_first_cert(pem).public_bytes(serialization.Encoding.PEM).decode()


def normalize_key_pem(key_pem: str, passphrase: str | None = None) -> str:
    """Load a private key (optionally encrypted) and return an unencrypted PEM."""
    key = serialization.load_pem_private_key(
        key_pem.encode(),
        password=passphrase.encode() if passphrase else None,
    )
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()


def key_matches_cert(cert_pem: str, key_pem: str) -> bool:
    """True iff the private key corresponds to the certificate's public key."""
    cert = _load_first_cert(cert_pem)
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    cert_pub = cert.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    key_pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return cert_pub == key_pub


@dataclass
class PfxContents:
    """The three parts extracted from a PKCS#12 bundle: private key, leaf cert,
    and any additional CA certificates shipped inside it (all as PEM strings)."""
    key_pem: str
    cert_pem: str
    ca_pems: list[str]


def load_pfx(data: bytes, password: str | None) -> PfxContents:
    """Extract key + leaf cert + any bundled CA certs from a PKCS#12 (.pfx/.p12)."""
    pwd = password.encode() if password else None
    key, cert, extra = pkcs12.load_key_and_certificates(data, pwd)
    if key is None or cert is None:
        raise ValueError("Le fichier PFX ne contient pas de clé privée et de certificat.")
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    ca_pems = [c.public_bytes(serialization.Encoding.PEM).decode() for c in (extra or [])]
    return PfxContents(key_pem=key_pem, cert_pem=cert_pem, ca_pems=ca_pems)


def split_pem_bundle(pem: str) -> list[str]:
    """Split a concatenated PEM into individual normalized certificate PEMs."""
    return [c.public_bytes(serialization.Encoding.PEM).decode() for c in _load_all_certs(pem)]


# =============================================================================
# Materialisation + live context
# =============================================================================

def materialize(fullchain_pem: str, key_pem: str) -> None:
    """Write the active cert chain + key to disk with tight permissions."""
    os.makedirs(CERT_DIR, exist_ok=True)
    with _lock:
        # Write key first with 0600 before any content lands.
        fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(key_pem)
        with open(FULLCHAIN_PATH, "w") as fh:
            fh.write(fullchain_pem)
    log.info("TLS material written to %s", CERT_DIR)


def build_context() -> ssl.SSLContext:
    """Create a hardened server SSLContext from the on-disk material."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=FULLCHAIN_PATH, keyfile=KEY_PATH)
    return ctx


def set_live_context(ctx: ssl.SSLContext) -> None:
    """Register the running server's SSLContext so later uploads can hot-reload it.

    Called once by the launcher after `build_context`; without this handle a
    certificate change could only take effect on a full restart.
    """
    global _live_context
    _live_context = ctx


def reload_live_context() -> bool:
    """Hot-swap the certificate on the running server. Returns True if reloaded.

    ``SSLContext.load_cert_chain`` may be called repeatedly; subsequent TLS
    handshakes use the new certificate while in-flight connections are undisturbed.
    """
    if _live_context is None:
        return False
    with _lock:
        _live_context.load_cert_chain(certfile=FULLCHAIN_PATH, keyfile=KEY_PATH)
    log.info("Live TLS context reloaded (new certificate active for new connections).")
    return True
