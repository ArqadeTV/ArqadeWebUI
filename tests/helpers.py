"""Builders for tiny but valid model files."""
import json
import struct
from pathlib import Path


def _s(text: str) -> bytes:
    raw = text.encode()
    return struct.pack("<Q", len(raw)) + raw


def make_gguf(path: Path, pad: int = 1_200_000) -> Path:
    kvs = [
        ("general.architecture", 8, _s("llama")),
        ("general.name", 8, _s("Tiny Test")),
        ("llama.context_length", 4, struct.pack("<I", 4096)),
        ("general.file_type", 4, struct.pack("<I", 15)),
        ("tokenizer.ggml.tokens", 9, struct.pack("<IQ", 8, 2) + _s("a") + _s("b")),
    ]
    blob = b"GGUF" + struct.pack("<I", 3) + struct.pack("<QQ", 0, len(kvs))
    for key, vtype, payload in kvs:
        blob += _s(key) + struct.pack("<I", vtype) + payload
    path.write_bytes(blob + b"\0" * pad)
    return path


def make_safetensors(path: Path, pad: int = 200_000) -> Path:
    header = {
        "__metadata__": {"format": "pt"},
        "w": {"dtype": "F32", "shape": [2, 3], "data_offsets": [0, 24]},
        "b": {"dtype": "F16", "shape": [4], "data_offsets": [24, 32]},
    }
    raw = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"\0" * pad)
    return path
