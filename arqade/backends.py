"""Chat backends: Ollama, OpenAI-compatible servers, llama-cpp-python, transformers.

Every heavy import is lazy and guarded, so a missing library surfaces as a
friendly `BackendError` in the chat window instead of crashing the server.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, AsyncIterator, Callable, Iterator

import httpx

from . import libs

TIMEOUT = httpx.Timeout(connect=3.0, read=600.0, write=10.0, pool=3.0)
PROBE = httpx.Timeout(1.5)


class BackendError(Exception):
    """A problem the user can act on (shown verbatim in the UI)."""


# ---- discovery ---------------------------------------------------------------

async def _probe_ollama(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    info = {"id": "ollama", "kind": "ollama", "label": "Ollama", "base_url": url, "online": False, "models": []}
    try:
        r = await client.get(f"{url.rstrip('/')}/api/tags")
        r.raise_for_status()
        info["models"] = [m["name"] for m in r.json().get("models", [])]
        info["online"] = True
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    return info


async def _probe_openai(client: httpx.AsyncClient, ep: dict[str, str]) -> dict[str, Any]:
    info = {
        "id": f"openai:{ep['name']}", "kind": "openai", "label": ep["name"],
        "base_url": ep["base_url"], "endpoint": ep["name"], "online": False, "models": [],
    }
    headers = {"Authorization": f"Bearer {ep['api_key']}"} if ep.get("api_key") else {}
    try:
        r = await client.get(f"{ep['base_url'].rstrip('/')}/models", headers=headers)
        r.raise_for_status()
        info["models"] = [m["id"] for m in r.json().get("data", [])]
        info["online"] = True
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    return info


async def detect(settings: dict[str, Any]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=PROBE) as client:
        found = await asyncio.gather(
            _probe_ollama(client, settings["ollama_url"]),
            *[_probe_openai(client, ep) for ep in settings["openai_endpoints"]],
        )
    found = list(found)
    found.append({
        "id": "llama_cpp", "kind": "llama_cpp", "label": "llama-cpp-python (local GGUF)",
        "online": libs.has("llama_cpp"), "models": [],
        "hint": "" if libs.has("llama_cpp") else "Install llama-cpp-python in the Libraries tab",
    })
    ready = libs.has("transformers") and libs.has("torch")
    found.append({
        "id": "transformers", "kind": "transformers", "label": "Transformers (local HF folder)",
        "online": ready, "models": [],
        "hint": "" if ready else "Install torch + transformers in the Libraries tab",
    })
    return found


# ---- streaming helpers -------------------------------------------------------

async def _iter_in_thread(factory: Callable[[threading.Event], Iterator[str]]) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()
    done = object()

    def put(item: Any) -> None:
        try:
            loop.call_soon_threadsafe(q.put_nowait, item)
        except RuntimeError:  # loop already closed
            pass

    def worker() -> None:
        try:
            for piece in factory(stop):
                if stop.is_set():
                    break
                put(piece)
        except Exception as exc:  # noqa: BLE001
            put(exc)
        finally:
            put(done)

    threading.Thread(target=worker, daemon=True, name="arqade-gen").start()
    try:
        while True:
            item = await q.get()
            if item is done:
                return
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        stop.set()


def _ollama_options(p: dict[str, Any]) -> dict[str, Any]:
    opts: dict[str, Any] = {}
    if p.get("temperature") is not None:
        opts["temperature"] = p["temperature"]
    if p.get("top_p") is not None:
        opts["top_p"] = p["top_p"]
    if p.get("max_tokens"):
        opts["num_predict"] = p["max_tokens"]
    return opts


async def _stream_ollama(url: str, model: str, messages: list[dict], params: dict) -> AsyncIterator[str]:
    body = {"model": model, "messages": messages, "stream": True, "options": _ollama_options(params)}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream("POST", f"{url.rstrip('/')}/api/chat", json=body) as r:
                if r.status_code >= 400:
                    raise BackendError(f"Ollama said {r.status_code}: {(await r.aread()).decode('utf-8', 'replace')[:300]}")
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise BackendError(f"Ollama: {data['error']}")
                    piece = data.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if data.get("done"):
                        return
    except httpx.ConnectError as exc:
        raise BackendError(f"Can't reach Ollama at {url}. Is it running? (`ollama serve`)") from exc


async def _stream_openai(ep: dict[str, str], model: str, messages: list[dict], params: dict) -> AsyncIterator[str]:
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
    for src, dst in (("temperature", "temperature"), ("top_p", "top_p"), ("max_tokens", "max_tokens")):
        if params.get(src) is not None:
            body[dst] = params[src]
    headers = {"Authorization": f"Bearer {ep['api_key']}"} if ep.get("api_key") else {}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream("POST", f"{ep['base_url'].rstrip('/')}/chat/completions", json=body, headers=headers) as r:
                if r.status_code >= 400:
                    raise BackendError(f"{ep['name']} said {r.status_code}: {(await r.aread()).decode('utf-8', 'replace')[:300]}")
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        return
                    try:
                        choice = json.loads(payload)["choices"][0]
                    except (ValueError, KeyError, IndexError):
                        continue
                    piece = (choice.get("delta") or {}).get("content")
                    if piece:
                        yield piece
    except httpx.ConnectError as exc:
        raise BackendError(f"Can't reach {ep['name']} at {ep['base_url']}. Is the server running?") from exc


# ---- in-process engines ------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"key": None, "obj": None}


def _cached(key: str, loader: Callable[[], Any]) -> Any:
    with _cache_lock:
        if _cache["key"] != key:
            _cache["obj"] = None  # free the previous model first
            _cache["obj"] = loader()
            _cache["key"] = key
        return _cache["obj"]


def _llama_cpp_factory(path: str, messages: list[dict], params: dict):
    def run(stop: threading.Event) -> Iterator[str]:
        if not libs.has("llama_cpp"):
            raise BackendError("llama-cpp-python isn't installed. Add it in the Libraries tab (it needs a C++ compiler).")
        from llama_cpp import Llama  # noqa: PLC0415

        llm = _cached(f"llama_cpp:{path}", lambda: Llama(model_path=path, n_ctx=4096, n_gpu_layers=-1, verbose=False))
        stream = llm.create_chat_completion(
            messages=messages, stream=True,
            temperature=params.get("temperature") if params.get("temperature") is not None else 0.7,
            top_p=params.get("top_p") if params.get("top_p") is not None else 0.95,
            max_tokens=params.get("max_tokens") or None,
        )
        for chunk in stream:
            if stop.is_set():
                break
            piece = chunk["choices"][0].get("delta", {}).get("content")
            if piece:
                yield piece

    return run


def _transformers_factory(path: str, messages: list[dict], params: dict):
    def run(stop: threading.Event) -> Iterator[str]:
        if not (libs.has("transformers") and libs.has("torch")):
            raise BackendError("Install `torch` and `transformers` in the Libraries tab first.")
        import torch  # noqa: PLC0415
        from transformers import (  # noqa: PLC0415
            AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer,
        )

        def load():
            tok = AutoTokenizer.from_pretrained(path, trust_remote_code=False)
            kwargs: dict[str, Any] = {"trust_remote_code": False, "torch_dtype": "auto"}
            if libs.has("accelerate"):
                kwargs["device_map"] = "auto"
            model = AutoModelForCausalLM.from_pretrained(path, **kwargs)
            return tok, model

        tok, model = _cached(f"transformers:{path}", load)
        if not getattr(tok, "chat_template", None):
            prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"
            inputs = tok(prompt, return_tensors="pt")
        else:
            inputs = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)

        class Stop(StoppingCriteria):
            def __call__(self, input_ids, scores, **kw):  # noqa: ANN001
                return stop.is_set()

        temp = params.get("temperature")
        gen_kwargs = dict(
            **inputs, streamer=streamer, max_new_tokens=params.get("max_tokens") or 512,
            do_sample=bool(temp) and temp > 0, stopping_criteria=StoppingCriteriaList([Stop()]),
        )
        if gen_kwargs["do_sample"]:
            gen_kwargs.update(temperature=temp, top_p=params.get("top_p") or 0.95)

        def generate() -> None:
            with torch.no_grad():
                model.generate(**gen_kwargs)

        t = threading.Thread(target=generate, daemon=True)
        t.start()
        for piece in streamer:
            if stop.is_set():
                break
            yield piece
        t.join(timeout=5)

    return run


# ---- public entry point ------------------------------------------------------

async def stream_chat(spec: dict[str, Any], messages: list[dict], params: dict) -> AsyncIterator[str]:
    """`spec` is already resolved/validated by the API layer."""
    kind = spec["kind"]
    if kind == "ollama":
        async for piece in _stream_ollama(spec["base_url"], spec["model"], messages, params):
            yield piece
    elif kind == "openai":
        async for piece in _stream_openai(spec["endpoint"], spec["model"], messages, params):
            yield piece
    elif kind == "llama_cpp":
        async for piece in _iter_in_thread(_llama_cpp_factory(spec["path"], messages, params)):
            yield piece
    elif kind == "transformers":
        async for piece in _iter_in_thread(_transformers_factory(spec["path"], messages, params)):
            yield piece
    else:
        raise BackendError(f"Unknown backend '{kind}'")
