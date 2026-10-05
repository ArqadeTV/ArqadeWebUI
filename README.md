# Arqade — Local AI Workbench

Scan your machine for local AI models, inspect them, chat with them, and control exactly how your system prompts are prioritised. Dark by default, light on request, one command to install.

**Powered by** PyTorch, TensorFlow/Keras, Hugging Face Transformers, ONNX Runtime, llama.cpp and ~70 other well-known Python AI libraries — all optional, all guarded.

## Install (one command)

macOS / Linux:
```bash
curl -fsSL https://arqadetv.github.io/ArqadeWebUI/install.sh | bash
```

Windows (PowerShell):
```powershell
irm https://arqadetv.github.io/ArqadeWebUI/install.ps1 | iex
```


Options (macOS/Linux: `… | bash -s -- --full`; Windows: set `$env:ARQADE_PROFILE='full'` first):

| Profile | What you get | Time |
|---|---|---|
| `--lite` | The UI only. Add libraries later from the **Libraries** tab. | seconds |
| `--standard` *(default)* | UI + PyTorch, TensorFlow, Keras, Transformers, SafeTensors, ONNX, GGUF, scikit-learn, OpenAI/Anthropic/Ollama clients | minutes |
| `--full` | Everything in the registry (~66 libraries on your OS) | long, several GB |

Manual install:
```bash
git clone https://github.com/ArqadeTV/ArqadeWebUI.git && cd ArqadeWebUI
./setup.sh          # Windows: setup.bat
./run.sh            # later launches (Windows: run.bat)
```

Requires Python 3.9+. Python 3.11/3.12 has the widest wheel coverage for TensorFlow and friends; the scripts prefer those when present.

### Why isn't every library vendored in the repo?
PyTorch and TensorFlow alone are multi-GB, platform-specific binaries, so they can't live in a git repo. Instead:

- `arqade/libs.py` is the single registry of every library; `requirements.txt` / `requirements-core.txt` are generated from it (CI fails if they drift).
- The installer installs **one package at a time**, so a single failing wheel (e.g. `llama-cpp-python` without a C++ compiler) never blocks the rest.
- Every import in Arqade is lazy and guarded. A missing library shows a friendly message in the UI — it can never crash the app or cause an `ImportError` at startup.
- The frontend has zero dependencies (no CDN, no npm), so it works offline.

## Features

- **Model scanner** — Quick / Home / Deep (all drives) scans. Recognises GGUF, GGML, SafeTensors, PyTorch (`.pt/.pth/.ckpt/.bin`), ONNX, Keras/H5, TF SavedModel, TFLite, Core ML, TensorRT, Flax, joblib/pickle, Hugging Face repos and caches (collapsed to one entry), diffusers pipelines, sharded weights, and **Ollama** / **LM Studio** / Jan / GPT4All folders. Cancellable, with live progress.
- **Inspector** — pure-Python GGUF and SafeTensors readers (architecture, context length, quantisation, parameter count, dtypes…). Pickle-based files are *listed, never loaded*, and flagged.
- **Chat** — talk to Ollama, any OpenAI-compatible server (LM Studio, llama.cpp server, vLLM…), or load a scanned GGUF (`llama-cpp-python`) / Hugging Face folder (`transformers`) in-process. Streaming, Stop button, Markdown + code blocks.
- **Custom system prompts & prompt authority hierarchy** — see below.
- **Libraries manager** — see what's installed, one-click install per library or per profile, live pip log.
- **System** — CPU/RAM/disk/GPU info, plus an on-demand probe for CUDA/Metal in PyTorch, TensorFlow and JAX.
- **Dark / light theme** — see below.

## Prompt authority hierarchy

Most chat templates take a single system message, so conflicting instructions (developer rules vs. a persona vs. pasted text) are usually resolved by luck. Arqade makes the precedence explicit:

- Layers are ordered by authority — **top wins**. Default stack: *Root policy → Developer/system → Operator persona → User preferences*, plus an *Untrusted content* lane.
- **Locked** layers are declared immutable: no lower layer may modify or relax them.
- **Untrusted** layers (and the "Untrusted context" box in Chat) are wrapped in fences and declared *data, never instructions* — a prompt-injection defence for pasted documents and tool output. Fence-breaking text is neutralised.
- Pick a **conflict policy**: silently obey the higher layer, obey and tell the user, or decline only the conflicting part.
- Save/load presets (built-ins: Default, Strict, Coding, Persona-with-locked-safety, Simple). Prefer a plain prompt? Switch to **Simple prompt** mode.
- The right-hand pane shows the exact compiled system prompt and a token estimate as you type.

This is prompt-level enforcement: it measurably helps models follow the ordering, but it isn't a security boundary — a determined jailbreak against a small local model can still win.

## Dark mode that plays nice with dark-mode extensions

Arqade defaults to dark. If a dark-mode browser extension (Dark Reader, Night Eye, Midnight Lizard, Turn Off the Lights, Super Dark Mode…) is detected, Arqade switches its own base to light so the extension darkens a light page instead of mangling one that's already dark. A chip in the header says when that happened, the switch reverses if you disable the extension, and clicking the theme button overrides it for the session. Settings let you turn the auto-switch off.

Detection is heuristic (DOM markers those extensions inject) and lives in one small file, [`arqade/static/theme.js`](arqade/static/theme.js) — add a selector there to support another extension. Browser-level "force dark" flags (Chrome/Opera) can't be detected from a page, but Arqade declares `color-scheme: dark light`, which tells those features to leave it alone.

## Security notes

Arqade reads your disk and can run `pip`, so it is locked down by default:

- Binds to `127.0.0.1` only; rejects foreign `Host` headers (DNS-rebinding) and cross-origin writes. `ARQADE_ALLOWED_HOSTS=*` plus `--host 0.0.0.0` exposes it on your LAN — only do that on a network you trust.
- The installer only accepts package names from the built-in registry — never arbitrary strings.
- Chat backends and file paths are resolved server-side from your settings / scan results; the browser can't supply raw URLs or paths.
- Models are never unpickled.

## Publishing your own copy (GitHub Pages one-liner)

1. Push this repo to GitHub (default branch `main`).
2. **Settings → Pages → Source: GitHub Actions.**
3. The [`pages.yml`](.github/workflows/pages.yml) workflow publishes `docs/` (landing page, `install.sh`, `install.ps1`) at `https://<owner>.github.io/<repo>/`, substituting your repo name into the scripts.

## Development

```bash
python -m pip install -r requirements-core.txt pytest
python -m pytest -q
python scripts/gen_requirements.py     # after editing arqade/libs.py
python -m arqade --no-browser --port 8765
```

Data (settings, saved prompts, scan cache) lives in `~/.arqade` (override with `ARQADE_HOME`).

## License

MIT — see [LICENSE](LICENSE).
