"""Reading X.509 certificates: parsing, identity, classification.

Everything here is read-only inspection of certificates an administrator
imports into the trusted-authority store (see ``trustconfig.py``). The
application does not own a server certificate: TLS is terminated by the
infrastructure in front of it (see ADR 0013), so there is nothing here to
generate a key, load a PKCS#12 bundle or build an ``SSLContext`` for serving.
The only context this application builds is the outbound one, in ``trust.py``.
"""
from __future__ import annotations

import datetime as _dt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtensionOID, NameOID


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


def _is_ca(cert: x509.Certificate) -> bool:
    """True if BasicConstraints marks this cert as a CA (no extension -> not a CA)."""
    try:
        bc = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        return bool(bc.value.ca)
    except x509.ExtensionNotFound:
        return False


def cert_info(pem: str) -> dict:
    """Summary of the first certificate in ``pem``, as the CA store records it."""
    cert = _load_first_cert(pem)
    na = cert.not_valid_after_utc
    now = _dt.datetime.now(_dt.timezone.utc)
    return {
        "subject": _name_str(cert.subject),
        "issuer": _name_str(cert.issuer),
        "not_after": na.isoformat(),
        "days_remaining": (na - now).days,
        "expired": now > na,
        "fingerprint_sha256": _fingerprint(cert),
        "is_ca": _is_ca(cert),
        "self_signed": cert.subject == cert.issuer,
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


def split_pem_bundle(pem: str) -> list[str]:
    """Split a concatenated PEM into individual normalized certificate PEMs."""
    return [c.public_bytes(serialization.Encoding.PEM).decode() for c in _load_all_certs(pem)]
