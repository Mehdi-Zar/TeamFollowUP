"""HTTPS / TLS: crypto primitives, DB orchestration and admin API."""
import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from app import tls, tlsconfig
from tests.conftest import login


@pytest.fixture(autouse=True)
def _tmp_cert_dir(tmp_path, monkeypatch):
    """Keep materialised cert files out of the real CERT_DIR."""
    monkeypatch.setattr(tls, "CERT_DIR", str(tmp_path))
    monkeypatch.setattr(tls, "FULLCHAIN_PATH", str(tmp_path / "fullchain.pem"))
    monkeypatch.setattr(tls, "KEY_PATH", str(tmp_path / "server.key"))


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
    if isinstance(obj, x509.Certificate):
        return obj.public_bytes(serialization.Encoding.PEM).decode()
    return obj.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.TraditionalOpenSSL,
                             serialization.NoEncryption()).decode()


# ---- crypto primitives ---------------------------------------------------------

def test_self_signed_generation_and_info():
    cert, key = tls.generate_self_signed("localhost", ["localhost", "127.0.0.1"])
    info = tls.cert_info(cert)
    assert info["self_signed"] is True
    assert "localhost" in info["sans"] and "127.0.0.1" in info["sans"]
    assert info["days_remaining"] > 300
    assert tls.key_matches_cert(cert, key) is True


def test_key_mismatch_detected():
    cert, _ = tls.generate_self_signed("a")
    _, other = tls.generate_self_signed("b")
    assert tls.key_matches_cert(cert, other) is False


def test_normalize_encrypted_key():
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    enc = k.private_bytes(serialization.Encoding.PEM,
                          serialization.PrivateFormat.TraditionalOpenSSL,
                          serialization.BestAvailableEncryption(b"pw")).decode()
    out = tls.normalize_key_pem(enc, "pw")
    assert "ENCRYPTED" not in out


def test_ca_kind_and_split_bundle():
    ca_key, ca_cert = _make_ca()
    _, leaf = _make_leaf(ca_key, ca_cert)
    assert tls.ca_kind(_pem(ca_cert)) == "root"
    assert tls.ca_kind(_pem(leaf)) == "intermediate"  # not-a-CA falls back
    bundle = _pem(leaf) + "\n" + _pem(ca_cert)
    assert len(tls.split_pem_bundle(bundle)) == 2


def test_load_pfx_roundtrip():
    ca_key, ca_cert = _make_ca()
    leaf_key, leaf = _make_leaf(ca_key, ca_cert)
    data = pkcs12.serialize_key_and_certificates(
        b"srv", leaf_key, leaf, [ca_cert], serialization.BestAvailableEncryption(b"pw"))
    got = tls.load_pfx(data, "pw")
    assert tls.key_matches_cert(got.cert_pem, got.key_pem)
    assert len(got.ca_pems) == 1


# ---- DB orchestration ----------------------------------------------------------

def test_bootstrap_creates_self_signed(db):
    st = tlsconfig.ensure_materialized(db)
    assert st["mode"] == "self_signed"
    assert st["active"]["self_signed"] is True


def test_regenerate_custom_cn_san(db):
    tlsconfig.ensure_materialized(db)
    st = tlsconfig.regenerate_self_signed(db, cn="app.internal", sans=["app.internal", "10.0.0.9"])
    assert st["active"]["subject"] == "app.internal"
    assert "10.0.0.9" in st["active"]["sans"]


def test_import_pfx_switches_to_custom_and_builds_chain(db):
    tlsconfig.ensure_materialized(db)
    ca_key, ca_cert = _make_ca()
    leaf_key, leaf = _make_leaf(ca_key, ca_cert, cn="pfx.example.com")
    data = pkcs12.serialize_key_and_certificates(
        b"srv", leaf_key, leaf, [ca_cert], serialization.BestAvailableEncryption(b"pw"))
    st = tlsconfig.import_pfx(db, data, "pw")
    assert st["mode"] == "custom"
    assert st["active"]["subject"] == "pfx.example.com"
    # materialised fullchain = leaf + bundled intermediate
    with open(tls.FULLCHAIN_PATH) as f:
        assert len(tls.split_pem_bundle(f.read())) == 2


def test_import_pem_rejects_mismatched_key(db):
    tlsconfig.ensure_materialized(db)
    ca_key, ca_cert = _make_ca()
    _, leaf = _make_leaf(ca_key, ca_cert)
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ValueError):
        tlsconfig.import_pem(db, _pem(leaf), _pem(wrong))


def test_ca_store_add_remove(db):
    tlsconfig.ensure_materialized(db)
    _, ca_cert = _make_ca()
    st = tlsconfig.add_ca(db, _pem(ca_cert), "My Root")
    assert any(c["name"] == "My Root" and c["kind"] == "root" for c in st["roots"])
    ca_id = st["roots"][0]["id"]
    st = tlsconfig.remove_ca(db, ca_id)
    assert st["roots"] == []
    with pytest.raises(ValueError):
        tlsconfig.remove_ca(db, ca_id)


# ---- admin API -----------------------------------------------------------------

def test_tls_api_admin_can_read_and_member_forbidden(client, seeded):
    login(client, seeded["admin"])
    r = client.get("/api/admin/tls-config")
    assert r.status_code == 200, r.text
    assert r.json()["mode"] in ("self_signed", "custom")

    login(client, seeded["member"])
    assert client.get("/api/admin/tls-config").status_code == 403


def test_tls_api_regenerate_self_signed(client, seeded):
    login(client, seeded["admin"])
    r = client.post("/api/admin/tls-config/self-signed", json={"cn": "cockpit.local", "sans": "cockpit.local, 192.168.1.10"})
    assert r.status_code == 200, r.text
    assert r.json()["active"]["subject"] == "cockpit.local"
    assert "192.168.1.10" in r.json()["active"]["sans"]
