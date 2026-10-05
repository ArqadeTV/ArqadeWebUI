import pytest

from arqade import inspectors
from helpers import make_gguf, make_safetensors


def test_gguf_metadata(tmp_path):
    info = inspectors.inspect_gguf(str(make_gguf(tmp_path / "m.gguf")))
    assert info["architecture"] == "llama"
    assert info["general.name"] == "Tiny Test"
    assert info["llama.context_length"] == 4096
    assert info["quantization"] == "Q4_K_M"


def test_gguf_rejects_garbage(tmp_path):
    p = tmp_path / "x.gguf"
    p.write_bytes(b"NOPE" + b"\0" * 100)
    with pytest.raises(ValueError):
        inspectors.inspect_gguf(str(p))


def test_safetensors_counts_params(tmp_path):
    info = inspectors.inspect_safetensors(str(make_safetensors(tmp_path / "m.safetensors")))
    assert info["parameters"] == 10
    assert info["tensor_count"] == 2
    assert info["dtypes"] == {"F32": 6, "F16": 4}
    assert info["metadata"] == {"format": "pt"}


def test_inspect_reports_errors_instead_of_raising(tmp_path):
    p = tmp_path / "bad.gguf"
    p.write_bytes(b"x" * 64)
    out = inspectors.inspect({"path": str(p), "format": "GGUF"})
    assert "error" in out
