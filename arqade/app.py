"""FastAPI application: JSON API + static single-page UI.

Security model: Arqade can read your disk and spawn pip, so it only serves
loopback Host headers (blocks DNS-rebinding) and rejects cross-origin writes
(blocks drive-by requests from other websites). Set ARQADE_ALLOWED_HOSTS=*
if you deliberately expose it on a LAN.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, backends, inspectors, libs, prompts, scanner, store

STATIC = Path(__file__).parent / "static"
LOOPBACK = {"localhost", "127.0.0.1", "[::1]", "testserver"}

app = FastAPI(title="Arqade", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")


def _hostname(netloc: str) -> str:
    return netloc[: netloc.index("]") + 1] if netloc.startswith("[") else netloc.split(":")[0]


def _allowed_hosts() -> set[str] | None:
    extra = {h.strip().lower() for h in os.environ.get("ARQADE_ALLOWED_HOSTS", "").split(",") if h.strip()}
    return None if "*" in extra else LOOPBACK | extra


@app.middleware("http")
async def guard(request: Request, call_next):
    allowed = _allowed_hosts()
    host = request.headers.get("host", "")
    if allowed is not None and _hostname(host).lower() not in allowed:
        return JSONResponse({"detail": "Host not allowed"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != host:
            return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


# ---- health / system ---------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


def _nvidia_smi() -> list[dict[str, Any]]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            gpus.append({"name": parts[0], "memory_mb": int(float(parts[1])) if parts[1].replace(".", "").isdigit() else None, "driver": parts[2]})
    return gpus


_deep_cache: dict[str, Any] = {}


def _framework_probe() -> dict[str, Any]:
    """Imports torch/tensorflow/jax - slow, so only on explicit request."""
    out: dict[str, Any] = {}
    if libs.has("torch"):
        try:
            import torch  # noqa: PLC0415

            mps = getattr(getattr(torch, "backends", None), "mps", None)
            out["torch"] = {
                "version": torch.__version__,
                "cuda": bool(torch.cuda.is_available()),
                "cuda_version": torch.version.cuda,
                "mps": bool(mps and mps.is_available()),
                "devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
            }
        except Exception as exc:  # noqa: BLE001
            out["torch"] = {"error": f"{type(exc).__name__}: {exc}"}
    if libs.has("tensorflow"):
        try:
            os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
            import tensorflow as tf  # noqa: PLC0415

            out["tensorflow"] = {
                "version": tf.__version__,
                "gpus": [d.name for d in tf.config.list_physical_devices("GPU")],
            }
        except Exception as exc:  # noqa: BLE001
            out["tensorflow"] = {"error": f"{type(exc).__name__}: {exc}"}
    if libs.has("jax"):
        try:
            import jax  # noqa: PLC0415

            out["jax"] = {"version": jax.__version__, "devices": [str(d) for d in jax.devices()]}
        except Exception as exc:  # noqa: BLE001
            out["jax"] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


@app.get("/api/system")
async def system(deep: bool = False):
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "cpu_count": os.cpu_count(),
        "data_dir": str(store.data_dir()),
        "gpus": await asyncio.to_thread(_nvidia_smi),
    }
    if libs.has("psutil"):
        import psutil  # noqa: PLC0415

        vm = psutil.virtual_memory()
        info["memory"] = {"total": vm.total, "available": vm.available}
        anchor = Path.home().anchor or "/"
        du = shutil.disk_usage(anchor)
        info["disk"] = {"path": anchor, "total": du.total, "free": du.free}
    if deep:
        if "frameworks" not in _deep_cache:
            _deep_cache["frameworks"] = await asyncio.to_thread(_framework_probe)
        info["frameworks"] = _deep_cache["frameworks"]
    return info


# ---- libraries / installer ---------------------------------------------------

class Job:
    def __init__(self, packages: list[str]):
        self.id = uuid.uuid4().hex[:10]
        self.packages = packages
        self.log: list[str] = []
        self.running = True
        self.results: dict[str, bool] = {}


JOBS: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _install_worker(job: Job) -> None:
    for pip in job.packages:
        job.log.append(f"\n=== pip install {pip} ===")
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", pip],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                job.log.append(line.rstrip())
                del job.log[:-3000]
            job.results[pip] = proc.wait() == 0
        except OSError as exc:
            job.log.append(f"could not start pip: {exc}")
            job.results[pip] = False
        job.log.append("OK" if job.results[pip] else "FAILED (skipping - the rest still install)")
    job.running = False


class InstallReq(BaseModel):
    packages: list[str] = Field(default_factory=list)
    profile: Literal["lite", "standard", "full", ""] = ""


@app.get("/api/libraries")
def libraries():
    return {"libraries": libs.status(), "profiles": list(libs.PROFILES)}


@app.post("/api/libraries/install")
def install(req: InstallReq):
    if req.profile:
        wanted = [l.pip for l in libs.select(req.profile) if libs.installed_version(l) is None]
    else:
        wanted = []
        for name in req.packages:
            lib = libs.BY_PIP.get(name)
            if lib is None or not libs.applicable(lib):  # only registry names: never arbitrary strings
                raise HTTPException(400, f"'{name}' is not an installable library on this platform")
            wanted.append(lib.pip)
    if not wanted:
        return {"job": None, "message": "Nothing to install - everything selected is already present."}
    with _jobs_lock:
        if any(j.running for j in JOBS.values()):
            raise HTTPException(409, "An install is already running")
        job = Job(wanted)
        JOBS[job.id] = job
    threading.Thread(target=_install_worker, args=(job,), daemon=True, name="arqade-pip").start()
    return {"job": job.id, "packages": wanted}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, since: int = 0):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return {"running": job.running, "lines": job.log[since:], "next": len(job.log), "results": job.results}


# ---- scanning / models -------------------------------------------------------

class ScanReq(BaseModel):
    mode: Literal["quick", "home", "deep"] = "quick"


@app.post("/api/scan")
def scan_start(req: ScanReq):
    started = scanner.start(req.mode, store.get_settings()["extra_roots"])
    return {"started": started, **scanner.snapshot()}


@app.post("/api/scan/cancel")
def scan_cancel():
    scanner.STATE.cancel = True
    return {"ok": True}


@app.get("/api/scan")
def scan_status():
    scanner.load_cache()
    return scanner.snapshot()


@app.get("/api/models")
def models_list():
    scanner.load_cache()
    return {"models": scanner.models(), "running": scanner.STATE.running}


def _model_or_404(mid: str) -> dict[str, Any]:
    scanner.load_cache()
    m = scanner.get(mid)
    if not m:
        raise HTTPException(404, "Model not found - rescan?")
    return m


@app.get("/api/models/{mid}/inspect")
async def model_inspect(mid: str):
    m = _model_or_404(mid)
    if not os.path.exists(m["path"]):
        raise HTTPException(410, "File no longer exists - rescan?")
    return {"model": m, "details": await asyncio.to_thread(inspectors.inspect, m)}


@app.post("/api/models/{mid}/reveal")
def model_reveal(mid: str):
    m = _model_or_404(mid)
    try:
        scanner.reveal(m["path"])
    except OSError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"ok": True}


# ---- settings / prompts ------------------------------------------------------

@app.get("/api/settings")
def settings_get():
    return store.get_settings()


@app.put("/api/settings")
def settings_put(patch: dict[str, Any]):
    if "extra_roots" in patch:
        roots = patch["extra_roots"]
        if not isinstance(roots, list) or not all(isinstance(r, str) for r in roots):
            raise HTTPException(400, "extra_roots must be a list of strings")
        patch["extra_roots"] = [r.strip() for r in roots if r.strip()][:50]
    if "ollama_url" in patch and not str(patch["ollama_url"]).startswith(("http://", "https://")):
        raise HTTPException(400, "ollama_url must start with http:// or https://")
    if "openai_endpoints" in patch:
        eps = patch["openai_endpoints"]
        if not isinstance(eps, list):
            raise HTTPException(400, "openai_endpoints must be a list")
        clean = []
        for ep in eps[:20]:
            if not isinstance(ep, dict) or not str(ep.get("base_url", "")).startswith(("http://", "https://")):
                raise HTTPException(400, "each endpoint needs a http(s) base_url")
            clean.append({"name": str(ep.get("name") or ep["base_url"])[:60], "base_url": str(ep["base_url"]), "api_key": str(ep.get("api_key", ""))})
        patch["openai_endpoints"] = clean
    return store.put_settings(patch)


@app.get("/api/prompts")
def prompts_list():
    return {**prompts.list_presets(), "default": prompts.default_hierarchy()}


class CompileReq(BaseModel):
    hierarchy: dict[str, Any]
    untrusted_context: str = ""


@app.post("/api/prompts/compile")
def prompts_compile(req: CompileReq):
    try:
        text = prompts.compile_hierarchy(req.hierarchy, req.untrusted_context)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"system": text, "tokens": prompts.estimate_tokens(text)}


class SavePreset(BaseModel):
    name: str
    hierarchy: dict[str, Any]


@app.post("/api/prompts")
def prompts_save(req: SavePreset):
    try:
        return {"saved": prompts.save_preset(req.name, req.hierarchy)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/prompts/{name}")
def prompts_delete(name: str):
    if not prompts.delete_preset(name):
        raise HTTPException(404, "no such saved preset")
    return {"ok": True}


# ---- chat --------------------------------------------------------------------

class Msg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=200_000)


class Params(BaseModel):
    temperature: float | None = Field(0.7, ge=0, le=2)
    top_p: float | None = Field(0.95, ge=0, le=1)
    max_tokens: int | None = Field(None, ge=1, le=131072)


class ChatReq(BaseModel):
    backend: dict[str, Any]
    messages: list[Msg] = Field(max_length=300)
    hierarchy: dict[str, Any] | None = None
    untrusted_context: str = Field("", max_length=200_000)
    params: Params = Params()


def _resolve_backend(spec: dict[str, Any]) -> dict[str, Any]:
    """Turn client-supplied hints into trusted values (no client-chosen URLs or paths)."""
    s = store.get_settings()
    kind = spec.get("kind")
    if kind == "ollama":
        model = str(spec.get("model", "")).strip()
        if not model:
            raise HTTPException(400, "choose an Ollama model")
        return {"kind": kind, "base_url": s["ollama_url"], "model": model}
    if kind == "openai":
        ep = next((e for e in s["openai_endpoints"] if e["name"] == spec.get("endpoint")), None)
        if not ep:
            raise HTTPException(400, "unknown endpoint - add it in Settings")
        model = str(spec.get("model", "")).strip()
        if not model:
            raise HTTPException(400, "choose a model")
        return {"kind": kind, "endpoint": ep, "model": model}
    if kind in ("llama_cpp", "transformers"):
        scanner.load_cache()
        m = scanner.get(str(spec.get("model_id", "")))
        if not m:
            raise HTTPException(400, "choose a scanned model (run a scan first)")
        if kind == "llama_cpp" and m["format"] not in ("GGUF", "Ollama"):
            raise HTTPException(400, "llama-cpp-python only runs GGUF models")
        if kind == "transformers" and not m.get("is_dir"):
            raise HTTPException(400, "Transformers runs Hugging Face model folders (with config.json)")
        return {"kind": kind, "path": m["path"]}
    raise HTTPException(400, "unknown backend kind")


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.get("/api/backends")
async def backends_list():
    return {"backends": await backends.detect(store.get_settings())}


@app.post("/api/chat")
async def chat(req: ChatReq):
    spec = _resolve_backend(req.backend)
    try:
        system = prompts.compile_hierarchy(req.hierarchy or prompts.default_hierarchy(), req.untrusted_context)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    messages = ([{"role": "system", "content": system}] if system else []) + [m.model_dump() for m in req.messages]
    params = req.params.model_dump()

    async def events():
        yield _sse({"type": "meta", "system_tokens": prompts.estimate_tokens(system)})
        started = time.time()
        pieces = 0
        try:
            async for piece in backends.stream_chat(spec, messages, params):
                pieces += 1
                yield _sse({"type": "delta", "text": piece})
            yield _sse({"type": "done", "seconds": round(time.time() - started, 2), "chunks": pieces})
        except backends.BackendError as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---- static UI ---------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
