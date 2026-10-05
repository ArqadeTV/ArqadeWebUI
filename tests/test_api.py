import time

import pytest
from fastapi.testclient import TestClient

from arqade import libs, scanner
from arqade.app import app
from helpers import make_gguf

client = TestClient(app)


def test_health_and_index():
    assert client.get("/api/health").json()["ok"] is True
    r = client.get("/")
    assert r.status_code == 200 and "Arqade" in r.text
    assert client.get("/static/theme.js").status_code == 200


def test_rejects_foreign_host_header():
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 403


def test_rejects_cross_origin_writes_but_allows_reads():
    assert client.post("/api/scan/cancel", headers={"origin": "http://evil.example"}).status_code == 403
    assert client.post("/api/scan/cancel", headers={"origin": "http://testserver"}).status_code == 200
    assert client.get("/api/health", headers={"origin": "http://evil.example"}).status_code == 200


def test_library_registry_and_install_validation():
    data = client.get("/api/libraries").json()
    names = {l["pip"] for l in data["libraries"]}
    assert {"torch", "tensorflow", "transformers", "fastapi"} <= names
    assert client.post("/api/libraries/install", json={"packages": ["totally-not-listed; rm -rf /"]}).status_code == 400
    # everything in the lite profile is the core set and must be installed for the app to run at all
    assert all(libs.installed_version(l) for l in libs.select("lite"))


def test_requirements_files_match_registry():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for fname, profile in (("requirements-core.txt", "lite"), ("requirements.txt", "full")):
        listed = {ln.split(";")[0].strip() for ln in (root / fname).read_text().splitlines() if ln and not ln.startswith("#")}
        expected = {l.pip for l in libs.LIBRARIES if libs.in_profile(l, profile)}
        assert listed == expected, fname


def test_prompt_endpoints():
    d = client.get("/api/prompts").json()
    assert "Default hierarchy" in d["builtin"]
    r = client.post("/api/prompts/compile", json={"hierarchy": d["default"], "untrusted_context": "hello"})
    assert r.status_code == 200 and "Instruction hierarchy" in r.json()["system"]
    assert client.post("/api/prompts/compile", json={"hierarchy": {"mode": "bad"}}).status_code == 400


def test_settings_validation_and_roundtrip():
    assert client.put("/api/settings", json={"ollama_url": "file:///etc/passwd"}).status_code == 400
    assert client.put("/api/settings", json={"extra_roots": ["/tmp/x", "  "]}).json()["extra_roots"] == ["/tmp/x"]


def test_scan_inspect_and_chat_guards(tmp_path, monkeypatch):
    make_gguf(tmp_path / "tiny.gguf")
    monkeypatch.setattr(scanner, "plan", lambda mode, extra: [(tmp_path, "Test", 5)])
    assert client.post("/api/scan", json={"mode": "quick"}).status_code == 200
    for _ in range(100):
        if not client.get("/api/scan").json()["running"]:
            break
        time.sleep(0.05)
    models = client.get("/api/models").json()["models"]
    assert [m["name"] for m in models] == ["tiny"]
    mid = models[0]["id"]
    det = client.get(f"/api/models/{mid}/inspect").json()["details"]
    assert det["architecture"] == "llama"
    assert client.get("/api/models/doesnotexist/inspect").status_code == 404

    # backends can only be chosen via scanned ids / configured endpoints, never raw paths or URLs
    base = {"messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/api/chat", json={**base, "backend": {"kind": "llama_cpp", "model_id": "../../etc/passwd"}}).status_code == 400
    assert client.post("/api/chat", json={**base, "backend": {"kind": "openai", "endpoint": "http://attacker", "model": "x"}}).status_code == 400
    assert client.post("/api/chat", json={**base, "backend": {"kind": "transformers", "model_id": mid}}).status_code == 400  # a GGUF is not an HF folder


def test_chat_streams_errors_as_events_when_backend_is_down():
    r = client.post("/api/chat", json={
        "backend": {"kind": "openai", "endpoint": "LM Studio", "model": "x"},
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert r.status_code == 200
    assert '"type": "meta"' in r.text
    assert '"type": "error"' in r.text or '"type": "delta"' in r.text
