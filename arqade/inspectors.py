"""Read model metadata without loading weights and without unpickling anything.

GGUF and safetensors are parsed in pure Python so inspection works even when
no ML library is installed. Pickle-based formats (.pt/.pth/.ckpt/.bin/.pkl) are
only *listed*, never executed - unpickling untrusted files can run arbitrary code.
"""
from __future__ import annotations

import json
import os
import struct
import zipfile
from pathlib import Path
from typing import Any

from . import libs

_GGUF_FILE_TYPES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 7: "Q8_0", 8: "Q5_0", 9: "Q5_1",
    10: "Q2_K", 11: "Q3_K_S", 12: "Q3_K_M", 13: "Q3_K_L", 14: "Q4_K_S", 15: "Q4_K_M",
    16: "Q5_K_S", 17: "Q5_K_M", 18: "Q6_K", 19: "IQ2_XXS", 20: "IQ2_XS", 21: "Q2_K_S",
    22: "IQ3_XS", 23: "IQ3_XXS", 24: "IQ1_S", 25: "IQ4_NL", 26: "IQ3_S", 27: "IQ3_M",
    28: "IQ2_S", 29: "IQ2_M", 30: "IQ4_XS", 31: "IQ1_M", 32: "BF16",
}
_FIXED = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
_KEEP_SUFFIXES = (
    "context_length", "block_count", "embedding_length", "feed_forward_length",
    "attention.head_count", "attention.head_count_kv", "expert_count", "vocab_size",
)


def _read_str(fh) -> str:
    (n,) = struct.unpack("<Q", fh.read(8))
    if n > 1 << 24:
        raise ValueError("string too long")
    return fh.read(n).decode("utf-8", "replace")


def _read_value(fh, vtype: int, keep: bool):
    if vtype in _FIXED:
        fmt = _FIXED[vtype]
        (v,) = struct.unpack(fmt, fh.read(struct.calcsize(fmt)))
        return v
    if vtype == 8:
        if keep:
            return _read_str(fh)
        (n,) = struct.unpack("<Q", fh.read(8))
        fh.seek(n, os.SEEK_CUR)
        return None
    if vtype == 9:
        etype, count = struct.unpack("<IQ", fh.read(12))
        if etype in _FIXED:
            fh.seek(struct.calcsize(_FIXED[etype]) * count, os.SEEK_CUR)
        else:
            for _ in range(count):
                _read_value(fh, etype, False)
        return f"<array of {count}>"
    raise ValueError(f"unknown GGUF value type {vtype}")


def inspect_gguf(path: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    with open(path, "rb") as fh:
        if fh.read(4) != b"GGUF":
            raise ValueError("not a GGUF file")
        (version,) = struct.unpack("<I", fh.read(4))
        tensor_count, kv_count = struct.unpack("<QQ", fh.read(16))
        info.update({"gguf_version": version, "tensor_count": tensor_count})
        if kv_count > 100_000:
            raise ValueError("implausible metadata size")
        for _ in range(kv_count):
            key = _read_str(fh)
            (vtype,) = struct.unpack("<I", fh.read(4))
            keep = key.startswith("general.") or key.endswith(_KEEP_SUFFIXES) or key == "tokenizer.chat_template"
            value = _read_value(fh, vtype, keep)
            if value is None or not keep:
                continue
            if key == "general.file_type":
                info["quantization"] = _GGUF_FILE_TYPES.get(value, f"type {value}")
            elif key == "tokenizer.chat_template":
                info["chat_template"] = str(value)[:600]
            else:
                info[key] = value
    arch = info.get("general.architecture")
    if arch:
        info["architecture"] = arch
    return info


def inspect_safetensors(path: str) -> dict[str, Any]:
    with open(path, "rb") as fh:
        (n,) = struct.unpack("<Q", fh.read(8))
        if n > 100 * 1024 * 1024:
            raise ValueError("implausible safetensors header")
        header = json.loads(fh.read(n))
    meta = header.pop("__metadata__", {}) or {}
    params, dtypes = 0, {}
    for t in header.values():
        count = 1
        for dim in t.get("shape", []):
            count *= dim
        params += count
        dtypes[t.get("dtype", "?")] = dtypes.get(t.get("dtype", "?"), 0) + count
    return {"tensor_count": len(header), "parameters": params, "dtypes": dtypes, "metadata": meta}


def inspect_torch_zip(path: str) -> dict[str, Any]:
    info: dict[str, Any] = {"pickle": True, "warning": "Pickle-based format: only load from sources you trust."}
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            info["archive_entries"] = len(names)
            info["has_data_pkl"] = any(n.endswith("data.pkl") for n in names)
    else:
        info["legacy_format"] = True
    return info


def inspect_onnx(path: str) -> dict[str, Any]:
    if not libs.has("onnx"):
        return {"note": "Install the `onnx` library (Libraries tab) for graph details."}
    if os.path.getsize(path) > 2 * 1024**3:
        return {"note": "File larger than 2 GB; skipping graph parse."}
    import onnx  # noqa: PLC0415 - heavy, lazy on purpose

    m = onnx.load(path, load_external_data=False)
    return {
        "producer": f"{m.producer_name} {m.producer_version}".strip(),
        "ir_version": m.ir_version,
        "opset": [o.version for o in m.opset_import][:3],
        "inputs": [i.name for i in m.graph.input][:12],
        "outputs": [o.name for o in m.graph.output][:12],
        "nodes": len(m.graph.node),
    }


def inspect_h5(path: str) -> dict[str, Any]:
    if not libs.has("h5py"):
        return {"note": "Install `h5py` (Libraries tab) for Keras details."}
    import h5py  # noqa: PLC0415

    with h5py.File(path, "r") as f:
        attrs = {k: (v.decode() if isinstance(v, bytes) else str(v))[:300] for k, v in f.attrs.items()}
        return {"top_level_groups": list(f.keys())[:20], "attrs": attrs}


def inspect_hf_dir(path: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fname in ("config.json", "model_index.json"):
        fp = Path(path) / fname
        if fp.is_file() and fp.stat().st_size < 2_000_000:
            try:
                cfg = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            keys = (
                "model_type", "architectures", "_class_name", "hidden_size", "num_hidden_layers",
                "num_attention_heads", "vocab_size", "max_position_embeddings", "torch_dtype",
            )
            out.update({k: cfg[k] for k in keys if k in cfg})
    return out


def inspect(model: dict[str, Any]) -> dict[str, Any]:
    path, fmt = model["path"], model["format"]
    try:
        if model.get("is_dir"):
            return inspect_hf_dir(path)
        if fmt == "GGUF":
            return inspect_gguf(path)
        if fmt == "SafeTensors":
            return inspect_safetensors(path)
        if fmt == "ONNX":
            return inspect_onnx(path)
        if fmt in ("Keras H5", "Keras"):
            return inspect_h5(path) if path.endswith((".h5", ".hdf5")) else {}
        if fmt in ("PyTorch", "PyTorch checkpoint"):
            return inspect_torch_zip(path)
        if fmt == "Ollama":
            return inspect_gguf(path)
    except Exception as exc:  # noqa: BLE001 - surface parse problems to the UI
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {}
