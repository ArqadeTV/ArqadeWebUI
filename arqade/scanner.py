"""Filesystem scanner that finds local AI model files.

Design notes
- Manual os.scandir recursion (fast, cancellable, never follows directory symlinks).
- Directories that *are* a model (HF repo, diffusers pipeline, TF SavedModel,
  .mlpackage) are reported once and not descended into.
- Sharded weights (model-00001-of-00004.safetensors) collapse into one entry.
- Ambiguous extensions (.bin, .pkl, .pt ...) only count above a size floor to
  keep random game assets and caches out of the results.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import store

# ext -> (format, framework, min_size_bytes)
KB, MB = 1024, 1024**2
EXT: dict[str, tuple[str, str, int]] = {
    ".gguf": ("GGUF", "llama.cpp", 1 * MB),
    ".ggml": ("GGML", "llama.cpp", 10 * MB),
    ".llamafile": ("Llamafile", "llama.cpp", 10 * MB),
    ".safetensors": ("SafeTensors", "PyTorch / HF", 100 * KB),
    ".pt": ("PyTorch", "PyTorch", 1 * MB),
    ".pth": ("PyTorch", "PyTorch", 1 * MB),
    ".ckpt": ("PyTorch checkpoint", "PyTorch", 10 * MB),
    ".bin": ("Binary weights", "PyTorch / HF", 50 * MB),
    ".onnx": ("ONNX", "ONNX", 100 * KB),
    ".h5": ("Keras H5", "TensorFlow / Keras", 100 * KB),
    ".hdf5": ("Keras H5", "TensorFlow / Keras", 100 * KB),
    ".keras": ("Keras", "TensorFlow / Keras", 100 * KB),
    ".tflite": ("TFLite", "TensorFlow Lite", 100 * KB),
    ".mlmodel": ("Core ML", "Core ML", 100 * KB),
    ".engine": ("TensorRT", "TensorRT", 1 * MB),
    ".plan": ("TensorRT", "TensorRT", 1 * MB),
    ".pte": ("ExecuTorch", "ExecuTorch", 100 * KB),
    ".nemo": ("NeMo", "NVIDIA NeMo", 1 * MB),
    ".msgpack": ("Flax msgpack", "JAX / Flax", 10 * MB),
    ".joblib": ("Joblib", "scikit-learn", 100 * KB),
    ".pkl": ("Pickle", "scikit-learn / generic", 5 * MB),
    ".pickle": ("Pickle", "scikit-learn / generic", 5 * MB),
}
PICKLE_FORMATS = {"PyTorch", "PyTorch checkpoint", "Binary weights", "Joblib", "Pickle"}
DIR_EXT = {".mlpackage": ("Core ML package", "Core ML"), ".mlmodelc": ("Core ML compiled", "Core ML")}
WEIGHT_EXTS = {".safetensors", ".bin", ".pt", ".pth", ".gguf", ".onnx", ".h5", ".msgpack", ".ckpt"}
SHARD_RE = re.compile(r"^(?P<stem>.+?)-(?P<i>\d{3,6})-of-(?P<n>\d{3,6})(?P<ext>\.[A-Za-z0-9]+)$")

SKIP_DIRS = {
    "node_modules", ".git", ".hg", ".svn", "__pycache__", "site-packages", "dist-packages",
    ".venv", "venv", ".tox", ".idea", ".vscode", "$recycle.bin", "system volume information",
    "windows", "program files", "program files (x86)", "programdata", "appdata\\local\\temp",
    "proc", "sys", "dev", "run", "boot", "snap", "system", "cores", "lost+found",
}


def _known_locations() -> list[tuple[Path, str]]:
    home = Path.home()
    env = os.environ
    cand: list[tuple[Path, str]] = [
        (Path(env.get("HF_HOME", home / ".cache" / "huggingface")) / "hub", "Hugging Face cache"),
        (Path(env["HUGGINGFACE_HUB_CACHE"]) if "HUGGINGFACE_HUB_CACHE" in env else home / ".cache" / "huggingface" / "hub", "Hugging Face cache"),
        (Path(env.get("OLLAMA_MODELS", home / ".ollama" / "models")), "Ollama"),
        (home / ".lmstudio" / "models", "LM Studio"),
        (home / ".cache" / "lm-studio" / "models", "LM Studio"),
        (home / ".cache" / "torch", "PyTorch hub"),
        (home / ".keras", "Keras"),
        (home / ".cache" / "gpt4all", "GPT4All"),
        (home / "AppData" / "Local" / "nomic.ai" / "GPT4All", "GPT4All"),
        (home / "AppData" / "Roaming" / "Jan" / "data" / "models", "Jan"),
        (home / "jan" / "models", "Jan"),
        (home / ".cache" / "whisper", "Whisper"),
        (home / ".cache" / "instructlab", "InstructLab"),
        (home / "Library" / "Application Support" / "nomic.ai" / "GPT4All", "GPT4All"),
        (home / "ComfyUI" / "models", "ComfyUI"),
        (home / "stable-diffusion-webui" / "models", "A1111"),
        (home / "models", "models folder"),
        (home / "Models", "models folder"),
        (home / ".local" / "share" / "nomic.ai" / "GPT4All", "GPT4All"),
    ]
    seen, out = set(), []
    for p, label in cand:
        key = str(p).lower()
        if key not in seen and p.is_dir():
            seen.add(key)
            out.append((p, label))
    return out


def _user_folders() -> list[tuple[Path, str]]:
    home = Path.home()
    out = []
    for name in ("Downloads", "Documents", "Desktop", "Projects", "Code", "dev", "repos", "source"):
        p = home / name
        if p.is_dir():
            out.append((p, name))
    return out


def _drive_roots() -> list[Path]:
    if os.name == "nt":
        import string

        return [Path(f"{d}:\\") for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    roots = [Path("/")]
    for base in ("/mnt", "/media", "/Volumes"):
        b = Path(base)
        if b.is_dir():
            roots += [c for c in b.iterdir() if c.is_dir()]
    return roots


def plan(mode: str, extra: list[str]) -> list[tuple[Path, str, int]]:
    """(root, source label, max depth) triples for a scan mode."""
    jobs: list[tuple[Path, str, int]] = [(p, s, 10) for p, s in _known_locations()]
    if mode in ("quick", "home"):
        if mode == "home":
            jobs.append((Path.home(), "Home", 12))
        else:
            jobs += [(p, s, 6) for p, s in _user_folders()]
    elif mode == "deep":
        jobs += [(r, str(r), 14) for r in _drive_roots()]
    for e in extra:
        p = Path(e).expanduser()
        if p.is_dir():
            jobs.append((p, "Custom folder", 14))
    # de-duplicate: drop roots nested under an earlier, deeper-or-equal root
    result: list[tuple[Path, str, int]] = []
    for job in jobs:
        if not any(_is_within(job[0], prev[0]) and prev[2] >= job[2] for prev in result):
            result.append(job)
    return result


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


@dataclass
class ScanState:
    running: bool = False
    cancel: bool = False
    mode: str = ""
    started: float = 0.0
    finished: float = 0.0
    dirs: int = 0
    files: int = 0
    current: str = ""
    found: int = 0
    error: str = ""
    models: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)


STATE = ScanState()


def model_id(path: str) -> str:
    return hashlib.sha1(os.path.normcase(path).encode("utf-8", "surrogateescape")).hexdigest()[:12]


def _entry(path: str, name: str, fmt: str, fw: str, size: int, mtime: float, source: str, **extra) -> dict[str, Any]:
    return {
        "id": model_id(path),
        "name": name,
        "path": path,
        "format": fmt,
        "framework": fw,
        "size": size,
        "mtime": mtime,
        "source": source,
        "unsafe_pickle": fmt in PICKLE_FORMATS,
        **extra,
    }


def _hf_repo_name(path: str) -> str | None:
    m = re.search(r"models--([^/\\]+)--([^/\\]+)", path)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def _dir_weight_size(root: str) -> tuple[int, float, int]:
    total, newest, n = 0, 0.0, 0
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in WEIGHT_EXTS:
                try:
                    st = os.stat(os.path.join(dp, fn))
                except OSError:
                    continue
                total += st.st_size
                newest = max(newest, st.st_mtime)
                n += 1
    return total, newest, n


def _ollama_models(root: Path) -> list[dict[str, Any]]:
    out = []
    manifests = root / "manifests"
    blobs = root / "blobs"
    if not manifests.is_dir():
        return out
    import json

    for mf in manifests.rglob("*"):
        if not mf.is_file():
            continue
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rel = mf.relative_to(manifests).parts  # registry host, namespace, model, tag
        name = f"{rel[-2]}:{rel[-1]}" if len(rel) >= 2 else mf.name
        if len(rel) >= 4 and rel[1] != "library":
            name = f"{rel[1]}/{name}"
        size, blob_path = 0, ""
        for layer in data.get("layers", []):
            size += int(layer.get("size", 0))
            if layer.get("mediaType", "").endswith("image.model"):
                blob_path = str(blobs / layer["digest"].replace(":", "-"))
        if blob_path and os.path.exists(blob_path):
            out.append(_entry(blob_path, name, "Ollama", "Ollama (GGUF)", size, mf.stat().st_mtime, "Ollama", ollama_name=name))
    return out


def _scan_dir(path: str, depth: int, max_depth: int, source: str, out: dict[str, dict[str, Any]], seen: set[str]) -> None:
    st = STATE
    if st.cancel or depth > max_depth:
        return
    try:
        real = os.path.realpath(path)
    except OSError:
        return
    if real in seen:
        return
    seen.add(real)
    st.dirs += 1
    st.current = path
    try:
        entries = list(os.scandir(path))
    except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
        return

    names = {e.name.lower(): e for e in entries}
    files = [e for e in entries if _is_file(e)]
    st.files += len(files)

    # Whole directories that count as a single model ------------------------------
    is_diffusers = "model_index.json" in names
    is_hf = "config.json" in names and any(os.path.splitext(e.name)[1].lower() in WEIGHT_EXTS for e in files)
    is_saved_model = "saved_model.pb" in names and "variables" in names
    if is_diffusers or is_hf or is_saved_model:
        size, mtime, n = _dir_weight_size(path)
        if is_saved_model:
            size, mtime = _dir_size_all(path)
            fmt, fw = "TF SavedModel", "TensorFlow"
        elif is_diffusers:
            fmt, fw = "Diffusers pipeline", "PyTorch / HF"
        else:
            fmt, fw = "HF Transformers", "PyTorch / HF"
        if size or is_saved_model:
            name = _hf_repo_name(path) or os.path.basename(path.rstrip("/\\")) or path
            ent = _entry(path, name, fmt, fw, size, mtime, source, is_dir=True, weight_files=n)
            out[ent["id"]] = ent
            st.found = len(out)
            return  # do not descend: sub-folders belong to this model

    # Shard grouping + single files -------------------------------------------------
    shards: dict[tuple[str, str], list[os.DirEntry]] = {}
    for e in files:
        ext = os.path.splitext(e.name)[1].lower()
        if ext not in EXT:
            continue
        fmt, fw, floor = EXT[ext]
        try:
            stt = e.stat()
        except OSError:
            continue
        if stt.st_size < floor:
            continue
        m = SHARD_RE.match(e.name)
        if m:
            shards.setdefault((m["stem"], m["ext"]), []).append(e)
            continue
        ent = _entry(e.path, os.path.splitext(e.name)[0], fmt, fw, stt.st_size, stt.st_mtime, source)
        out[ent["id"]] = ent
    for (stem, ext), group in shards.items():
        fmt, fw, _ = EXT[ext.lower()]
        group.sort(key=lambda x: x.name)
        total = sum(_safe_size(x) for x in group)
        ent = _entry(group[0].path, stem, fmt, fw, total, group[0].stat().st_mtime, source, shards=len(group))
        out[ent["id"]] = ent
    st.found = len(out)

    # Directory-style models and recursion ------------------------------------------
    for e in entries:
        try:
            if e.is_symlink() or not e.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        low = e.name.lower()
        ext = os.path.splitext(low)[1]
        if ext in DIR_EXT:
            size, mtime = _dir_size_all(e.path)
            fmt, fw = DIR_EXT[ext]
            ent = _entry(e.path, os.path.splitext(e.name)[0], fmt, fw, size, mtime, source, is_dir=True)
            out[ent["id"]] = ent
            continue
        if low in SKIP_DIRS:
            continue
        _scan_dir(e.path, depth + 1, max_depth, source, out, seen)
        if st.cancel:
            return


def _is_file(e: os.DirEntry) -> bool:
    try:
        return e.is_file()
    except OSError:
        return False


def _safe_size(e: os.DirEntry) -> int:
    try:
        return e.stat().st_size
    except OSError:
        return 0


def _dir_size_all(root: str) -> tuple[int, float]:
    total, newest = 0, 0.0
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            try:
                st = os.stat(os.path.join(dp, fn))
            except OSError:
                continue
            total += st.st_size
            newest = max(newest, st.st_mtime)
    return total, newest


def _run(mode: str, extra: list[str]) -> None:
    st = STATE
    found: dict[str, dict[str, Any]] = {}
    try:
        seen: set[str] = set()
        for root, source, max_depth in plan(mode, extra):
            if st.cancel:
                break
            if source == "Ollama":
                for ent in _ollama_models(root):
                    found[ent["id"]] = ent
                st.found = len(found)
                continue
            _scan_dir(str(root), 0, max_depth, source, found, seen)
            with st.lock:
                st.models = dict(found)  # publish partial results as we go
    except Exception as exc:  # noqa: BLE001
        st.error = f"{type(exc).__name__}: {exc}"
    finally:
        with st.lock:
            st.models = found
            st.found = len(found)
            st.running = False
            st.finished = time.time()
            st.current = ""
        _persist(found)


def _persist(models: dict[str, dict[str, Any]]) -> None:
    store.write("scan_cache.json", {"time": time.time(), "models": list(models.values())})


def load_cache() -> None:
    if STATE.models or STATE.running:
        return
    data = store.read("scan_cache.json", {})
    if isinstance(data, dict):
        STATE.models = {m["id"]: m for m in data.get("models", []) if isinstance(m, dict) and "id" in m}
        STATE.finished = float(data.get("time", 0))
        STATE.found = len(STATE.models)


def start(mode: str = "quick", extra: list[str] | None = None) -> bool:
    if mode not in ("quick", "home", "deep"):
        raise ValueError("mode must be quick, home or deep")
    with STATE.lock:
        if STATE.running:
            return False
        STATE.running, STATE.cancel, STATE.mode = True, False, mode
        STATE.started, STATE.finished = time.time(), 0.0
        STATE.dirs = STATE.files = STATE.found = 0
        STATE.error = ""
        STATE.models = {}
    threading.Thread(target=_run, args=(mode, list(extra or [])), daemon=True, name="arqade-scan").start()
    return True


def snapshot() -> dict[str, Any]:
    s = STATE
    return {
        "running": s.running,
        "mode": s.mode,
        "dirs": s.dirs,
        "files": s.files,
        "found": s.found,
        "current": s.current,
        "error": s.error,
        "elapsed": (time.time() - s.started) if s.running else max(0.0, s.finished - s.started),
        "finished": s.finished,
    }


def models() -> list[dict[str, Any]]:
    with STATE.lock:
        return sorted(STATE.models.values(), key=lambda m: m["size"], reverse=True)


def get(mid: str) -> dict[str, Any] | None:
    return STATE.models.get(mid)


def reveal(path: str) -> None:
    """Open the containing folder in the OS file manager (local use only)."""
    import subprocess

    target = path if os.path.isdir(path) else os.path.dirname(path)
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])  # noqa: S603,S607
    else:
        subprocess.Popen(["xdg-open", target])  # noqa: S603,S607
