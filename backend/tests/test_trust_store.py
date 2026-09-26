"""The trusted-authority store: reading certificates, DB orchestration, admin API.

The layer above ``test_trust.py``: that one pins what the merged bundle and the
verification context do, this one pins how an administrator fills the store, from
a PEM landing in ``app_settings`` to the endpoints the screen calls. The app does
not serve TLS at all (ADR 0013), so there is no server certificate, no private key
and no SSLContext to configure here.
"""
import datetime as dt
import os

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app import certinfo, trust, trustconfig
from tests.conftest import login


@pytest.fixture(autouse=True)
def _tmp_bundle(tmp_path, monkeypatch):
    """Keep the merged bundle out of the real CERT_DIR, and restore the env.

    ``trust.apply`` points SSL_CERT_FILE at the bundle it writes; a temporary
    path leaking into later tests would break every outbound call.
    """
    monkeypatch.setattr(trust, "BUNDLE_PATH", str(tmp_path / "trust_bundle.pem"))
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _make_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Unit Test Root CA")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=1))
            .not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    return key, cert


def _make_leaf(ca_key, ca_cert, cn="leaf.example.com"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=1))
            .not_valid_after(now + dt.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    return key, cert


def _pem(obj):
    return obj.public_bytes(serialization.Encoding.PEM).decode()


# ---- reading certificates ------------------------------------------------------

def test_cert_info_reads_identity_and_validity():
    _, ca_cert = _make_ca()
    info = certinfo.cert_info(_pem(ca_cert))
    assert info["subject"] == "Unit Test Root CA"
    assert info["is_ca"] is True and info["self_signed"] is True
    assert info["expired"] is False and info["days_remaining"] > 3000


def test_ca_kind_and_split_bundle():
    ca_key, ca_cert = _make_ca()
    _, leaf = _make_leaf(ca_key, ca_cert)
    assert certinfo.ca_kind(_pem(ca_cert)) == "root"
    assert certinfo.ca_kind(_pem(leaf)) == "intermediate"  # not-a-CA falls back
    bundle = _pem(leaf) + "\n" + _pem(ca_cert)
    assert len(certinfo.split_pem_bundle(bundle)) == 2


# ---- DB orchestration ----------------------------------------------------------

def test_ca_store_add_remove(db):
    _, ca_cert = _make_ca()
    st = trustconfig.add_ca(db, _pem(ca_cert), "My Root")
    assert any(c["name"] == "My Root" and c["kind"] == "root" for c in st["roots"])
    ca_id = st["roots"][0]["id"]
    st = trustconfig.remove_ca(db, ca_id)
    assert st["roots"] == []
    with pytest.raises(ValueError):
        trustconfig.remove_ca(db, ca_id)


def test_stored_pem_never_leaves_through_the_list(db):
    """The list feeds a screen; a PEM body is downloaded one authority at a time."""
    _, ca_cert = _make_ca()
    st = trustconfig.add_ca(db, _pem(ca_cert), "My Root")
    assert all("pem" not in c for c in st["cas"])
    assert _pem(ca_cert).strip() in trustconfig.export_ca_pem(db, st["roots"][0]["id"])


def test_adding_a_ca_makes_it_trusted_for_outbound_calls(db):
    """The whole point of the store: an imported authority must reach the
    outbound trust bundle, without any restart."""
    _, ca_cert = _make_ca()
    pem = _pem(ca_cert)
    trustconfig.add_ca(db, pem, "Internal Root")

    with open(trust.BUNDLE_PATH, encoding="utf-8") as fh:
        bundle = fh.read()
    assert pem.strip() in bundle
    # Public roots are kept: the app still talks to public endpoints.
    assert bundle.count("BEGIN CERTIFICATE") > 1
    assert os.environ["SSL_CERT_FILE"] == trust.BUNDLE_PATH


def test_removing_a_ca_withdraws_the_trust(db):
    _, ca_cert = _make_ca()
    pem = _pem(ca_cert)
    st = trustconfig.add_ca(db, pem, "Internal Root")
    trustconfig.remove_ca(db, st["roots"][0]["id"])
    with open(trust.BUNDLE_PATH, encoding="utf-8") as fh:
        assert pem.strip() not in fh.read()


def test_boot_hook_reapplies_the_store(db):
    _, ca_cert = _make_ca()
    trustconfig.add_ca(db, _pem(ca_cert), "Internal Root")
    assert trustconfig.ensure_trust(db) == 1


# ---- admin API -----------------------------------------------------------------

def test_trust_api_admin_can_read_and_member_forbidden(client, seeded):
    login(client, seeded["admin"])
    r = client.get("/api/admin/trust-store")
    assert r.status_code == 200, r.text
    assert r.json()["cas"] == []

    login(client, seeded["member"])
    assert client.get("/api/admin/trust-store").status_code == 403


def test_trust_api_add_and_download_ca(client, seeded):
    login(client, seeded["admin"])
    _, ca_cert = _make_ca()
    pem = _pem(ca_cert)
    r = client.post("/api/admin/trust-store/ca",
                    files={"ca": ("root.pem", pem, "application/x-pem-file")},
                    data={"name": "Internal Root"})
    assert r.status_code == 200, r.text
    ca_id = r.json()["roots"][0]["id"]

    r = client.get(f"/api/admin/trust-store/ca/{ca_id}/download")
    assert r.status_code == 200
    assert "BEGIN CERTIFICATE" in r.text
    assert client.get("/api/admin/trust-store/ca/nope/download").status_code == 404


def test_trust_api_rejects_a_payload_that_is_not_a_certificate(client, seeded):
    login(client, seeded["admin"])
    r = client.post("/api/admin/trust-store/ca", data={"ca_pem": "not a certificate"})
    assert r.status_code == 400
