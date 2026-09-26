"""Outbound TLS trust: the store an administrator fills must actually be used.

The failure this guards against is silent and total. An internal IdP issued by a
private authority answers the discovery fetch with a certificate no public root
signs; httpx raises ``self signed certificate in certificate chain``; SSO is
impossible. The only supported fix is to import that authority from the admin UI,
so these tests pin the whole path: the merge keeps the public roots, the imported
certificate really lands in the verification context, the change needs no
restart, and nothing anywhere can end up with verification switched off.
"""
import os
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app import mail, trust


@pytest.fixture(autouse=True)
def _tmp_bundle(tmp_path, monkeypatch):
    """Bundle in a temp dir, environment restored: ``apply`` writes SSL_CERT_FILE
    into the live process, which must not leak into the rest of the suite."""
    monkeypatch.setattr(trust, "BUNDLE_PATH", str(tmp_path / "trust_bundle.pem"))
    monkeypatch.setattr(trust, "_context", None, raising=False)
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)
    trust._context = None


def _ca_pem(cn="Internal Root CA"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=1))
            .not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _certs_in(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().count("BEGIN CERTIFICATE")


# ---- the bundle ----------------------------------------------------------------

def test_the_public_roots_are_kept_alongside_the_internal_one():
    """Replacing rather than extending the store is the classic mistake: it makes
    the IdP reachable and breaks every public endpoint (log export, in this app)."""
    base = _certs_in(trust.BASE_CA_FILE)
    trust.apply([_ca_pem()])
    assert _certs_in(trust.BUNDLE_PATH) == base + 1


def test_an_empty_store_still_yields_a_usable_bundle():
    trust.apply([])
    assert _certs_in(trust.BUNDLE_PATH) == _certs_in(trust.BASE_CA_FILE)


def test_applying_twice_does_not_stack_the_base_store():
    """``apply`` points SSL_CERT_FILE at its own output, so a base captured at
    call time instead of import time would double the bundle on every save."""
    trust.apply([_ca_pem()])
    first = _certs_in(trust.BUNDLE_PATH)
    trust.apply([_ca_pem("Another Root CA")])
    assert _certs_in(trust.BUNDLE_PATH) == first


def test_third_party_clients_are_pointed_at_the_bundle():
    """google-auth in ``logexport`` gets no context from us; the env var is how
    the bundle reaches it."""
    trust.apply([_ca_pem()])
    assert os.environ["SSL_CERT_FILE"] == trust.BUNDLE_PATH
    assert os.environ["REQUESTS_CA_BUNDLE"] == trust.BUNDLE_PATH


# ---- the context ---------------------------------------------------------------

def test_the_imported_authority_is_loaded_into_the_verification_context():
    trust.apply([_ca_pem("Acme Internal Root")])
    subjects = str(trust.context().get_ca_certs())
    assert "Acme Internal Root" in subjects


def test_the_context_is_rebuilt_after_a_change_so_no_restart_is_needed():
    trust.apply([])
    before = trust.context()
    assert trust.context() is before          # cached between changes
    trust.apply([_ca_pem()])
    assert trust.context() is not before      # invalidated by the change


def test_verification_is_never_relaxed():
    """No configuration path may produce a permissive context: an imported CA is
    the way in, not a disabled check."""
    trust.apply([_ca_pem()])
    ctx = trust.context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_an_unusable_bundle_falls_back_instead_of_breaking_every_call():
    with open(trust.BUNDLE_PATH, "w", encoding="utf-8") as fh:
        fh.write("not a certificate at all\n")
    trust._context = None
    ctx = trust.context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.get_ca_certs()  # the base store, so public endpoints still work


# ---- call sites ----------------------------------------------------------------

class _FakeSMTP:
    """Records what the mail path hands to the TLS handshake."""

    def __init__(self, *a, **kw):
        self.started_with = "not called"

    def starttls(self, context=None):
        self.started_with = context

    def login(self, *a):
        pass

    def send_message(self, *a):
        pass

    def quit(self):
        pass


def test_smtp_starttls_receives_an_explicit_context(monkeypatch):
    """Called without one, smtplib uses ssl._create_stdlib_context(): no hostname
    check, no verification, credentials handed to whoever answered."""
    created = []

    def _factory(*a, **kw):
        srv = _FakeSMTP()
        created.append(srv)
        return srv

    monkeypatch.setattr(mail.smtplib, "SMTP", _factory)
    ok = mail.send_email(
        {"enabled": True, "host": "smtp.internal", "port": 587, "use_tls": True,
         "from_addr": "noreply@internal", "username": "u", "password": "p"},
        "someone@internal", "subject", "body")
    assert ok is True
    assert isinstance(created[0].started_with, ssl.SSLContext)
    assert created[0].started_with.verify_mode == ssl.CERT_REQUIRED
