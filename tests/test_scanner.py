import json
import time
from pathlib import Path

from arqade import scanner
from helpers import make_gguf, make_safetensors


def run_scan(root: Path, monkeypatch):
    monkeypatch.setattr(scanner, "plan", lambda mode, extra: [(root, "Test", 8)])
    assert scanner.start("quick", [])
    for _ in range(200):
        if not scanner.STATE.running:
            break
        time.sleep(0.05)
    assert not scanner.STATE.running
    return {m["name"]: m for m in scanner.models()}


def test_finds_common_formats_and_skips_noise(tmp_path, monkeypatch):
    make_gguf(tmp_path / "llama.gguf")
    (tmp_path / "sub").mkdir()
    make_safetensors(tmp_path / "sub" / "adapter.safetensors")
    (tmp_path / "tiny.onnx").write_bytes(b"x" * 10)  # below size floor
    (tmp_path / "game.bin").write_bytes(b"x" * 1000)  # ambiguous ext, too small
    (tmp_path / "notes.txt").write_text("hi")
    (tmp_path / "node_modules").mkdir()
    make_gguf(tmp_path / "node_modules" / "ignored.gguf")

    found = run_scan(tmp_path, monkeypatch)
    assert set(found) == {"llama", "adapter"}
    assert found["llama"]["format"] == "GGUF"
    assert found["adapter"]["framework"] == "PyTorch / HF"
    assert not found["llama"]["unsafe_pickle"]


def test_sharded_weights_collapse_to_one_entry(tmp_path, monkeypatch):
    for i in (1, 2, 3):
        make_safetensors(tmp_path / f"model-0000{i}-of-00003.safetensors")
    found = run_scan(tmp_path, monkeypatch)
    assert list(found) == ["model"]
    assert found["model"]["shards"] == 3
    assert found["model"]["size"] > 3 * 200_000


def test_hf_directory_is_one_model_and_not_descended(tmp_path, monkeypatch):
    repo = tmp_path / "models--acme--tiny" / "snapshots" / "abc"
    repo.mkdir(parents=True)
    (repo / "config.json").write_text(json.dumps({"model_type": "llama"}))
    make_safetensors(repo / "model.safetensors")
    found = run_scan(tmp_path, monkeypatch)
    assert list(found) == ["acme/tiny"]
    assert found["acme/tiny"]["format"] == "HF Transformers"
    assert found["acme/tiny"]["is_dir"] is True


def test_pickle_formats_are_flagged(tmp_path, monkeypatch):
    (tmp_path / "w.pt").write_bytes(b"\0" * 2_000_000)
    found = run_scan(tmp_path, monkeypatch)
    assert found["w"]["unsafe_pickle"] is True


def test_ollama_manifest_is_resolved(tmp_path):
    root = tmp_path / "ollama"
    mf = root / "manifests" / "registry.ollama.ai" / "library" / "tiny" / "latest"
    mf.parent.mkdir(parents=True)
    blob = root / "blobs" / "sha256-abc"
    blob.parent.mkdir(parents=True)
    make_gguf(blob)
    mf.write_text(json.dumps({"layers": [{"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:abc", "size": blob.stat().st_size}]}))
    models = scanner._ollama_models(root)
    assert [m["name"] for m in models] == ["tiny:latest"]
    assert models[0]["format"] == "Ollama"


def test_cancel_stops_scan(tmp_path, monkeypatch):
    for i in range(50):
        (tmp_path / f"d{i}").mkdir()
    scanner.STATE.cancel = True
    monkeypatch.setattr(scanner, "plan", lambda mode, extra: [(tmp_path, "Test", 8)])
    found = {}
    scanner._scan_dir(str(tmp_path), 0, 8, "Test", found, set())
    assert found == {}
