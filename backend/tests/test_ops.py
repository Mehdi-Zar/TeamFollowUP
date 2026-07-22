"""Ops / Maintenance: runtime diagnostics + self-restart admin API.

The restart is exercised with ``OPS_DISABLE_RESTART=1`` so no SIGTERM is ever sent
to the test process; the real kill path (a threading.Timer -> os.kill) is not fired.
"""
import logging

from app import logbuffer, ops
from tests.conftest import login


def test_detect_orchestrator_process_by_default(monkeypatch):
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.delenv("container", raising=False)
    monkeypatch.setattr(ops.os.path, "exists", lambda p: False)
    assert ops.detect_orchestrator() == "process"


def test_detect_orchestrator_kubernetes(monkeypatch):
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    assert ops.detect_orchestrator() == "kubernetes"


def test_request_restart_disabled_is_noop(monkeypatch):
    monkeypatch.setenv("OPS_DISABLE_RESTART", "1")
    r = ops.request_restart()
    assert r["scheduled"] is False
    assert r["reason"] == "disabled"


def test_runtime_status_shape(db):
    st = ops.runtime_status(db)
    for key in ("version", "hostname", "pid", "python", "orchestrator",
                "uptime_seconds", "tls_enabled", "tls_running", "restart_pending"):
        assert key in st
    assert isinstance(st["uptime_seconds"], int)


# ---- admin API -----------------------------------------------------------------

def test_runtime_admin_only(client, seeded):
    login(client, seeded["admin"])
    r = client.get("/api/admin/runtime")
    assert r.status_code == 200, r.text
    assert "version" in r.json() and "orchestrator" in r.json()

    login(client, seeded["member"])
    assert client.get("/api/admin/runtime").status_code == 403


def test_restart_admin_only_and_scheduled(client, seeded, monkeypatch):
    monkeypatch.setenv("OPS_DISABLE_RESTART", "1")  # never actually SIGTERM the test process
    login(client, seeded["admin"])
    r = client.post("/api/admin/restart")
    assert r.status_code == 200, r.text
    assert r.json()["scheduled"] is False  # disabled -> no-op, but the endpoint works

    login(client, seeded["member"])
    assert client.post("/api/admin/restart").status_code == 403


# ---- log buffer + level control ------------------------------------------------

def test_logbuffer_captures_and_filters():
    logbuffer.install()
    logbuffer.clear()
    logging.getLogger("trt.test").warning("boom-42")
    logging.getLogger("trt.test").info("quiet-note")
    msgs = [r["message"] for r in logbuffer.records(limit=50)]
    assert any("boom-42" in m for m in msgs)
    # min_level filter keeps WARNING and drops INFO
    warn = [r["message"] for r in logbuffer.records(min_level="WARNING")]
    assert any("boom-42" in m for m in warn)
    assert not any("quiet-note" in m for m in warn)


def test_set_live_level_roundtrip():
    logbuffer.set_live_level("DEBUG")
    assert logbuffer.current_level() == "DEBUG"
    logbuffer.set_live_level("INFO")
    assert logbuffer.current_level() == "INFO"


def test_logs_api_read_set_level_and_download(client, seeded):
    login(client, seeded["admin"])
    r = client.get("/api/admin/logs?limit=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "records" in body and body["level"] in logbuffer.LEVELS

    # set level (live only), then a bad level is rejected
    assert client.post("/api/admin/log-level", json={"level": "DEBUG"}).json()["level"] == "DEBUG"
    assert client.post("/api/admin/log-level", json={"level": "NOPE"}).status_code == 400

    # download as text + json
    assert client.get("/api/admin/logs/download?fmt=txt").status_code == 200
    assert client.get("/api/admin/logs/download?fmt=json").status_code == 200
    client.post("/api/admin/log-level", json={"level": "INFO"})  # restore

    login(client, seeded["member"])
    assert client.get("/api/admin/logs").status_code == 403
    assert client.post("/api/admin/log-level", json={"level": "DEBUG"}).status_code == 403
