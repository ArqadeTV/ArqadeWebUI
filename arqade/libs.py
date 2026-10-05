"""Registry of every AI/ML library Arqade knows about.

Stdlib only on purpose: the installer, the CLI and the API all import this
module *before* any heavy dependency exists. Detection never imports the
package itself (that would take seconds for torch/tensorflow) - it only asks
importlib whether the module can be found and reads the dist metadata.
"""
from __future__ import annotations

import importlib.metadata as md
import importlib.util
import platform
import sys
from dataclasses import dataclass

PROFILES = ("lite", "standard", "full")


@dataclass(frozen=True)
class Lib:
    pip: str  # name passed to `pip install`
    module: str  # top-level import name
    category: str
    desc: str
    profile: str = "full"  # smallest profile that includes it
    only: str = ""  # "", "linux", "darwin", "win32", "darwin-arm64", "not-darwin"

    @property
    def dist(self) -> str:
        """Distribution name without extras, used for metadata lookups."""
        return self.pip.split("[")[0]


def _l(pip, module, category, desc, profile="full", only=""):
    return Lib(pip, module, category, desc, profile, only)


LIBRARIES: tuple[Lib, ...] = (
    # --- core: needed for the UI itself --------------------------------------
    _l("fastapi", "fastapi", "Core", "Web API framework powering Arqade", "lite"),
    _l("uvicorn[standard]", "uvicorn", "Core", "ASGI server", "lite"),
    _l("pydantic", "pydantic", "Core", "Data validation", "lite"),
    _l("httpx", "httpx", "Core", "HTTP client for Ollama / OpenAI-compatible servers", "lite"),
    _l("psutil", "psutil", "Core", "CPU / RAM / disk telemetry", "lite"),
    _l("numpy", "numpy", "Core", "Array maths used by nearly everything", "lite"),
    # --- deep learning frameworks --------------------------------------------
    _l("torch", "torch", "Deep learning", "PyTorch", "standard"),
    _l("tensorflow", "tensorflow", "Deep learning", "TensorFlow", "standard"),
    _l("keras", "keras", "Deep learning", "Keras 3 (multi-backend)", "standard"),
    _l("torchvision", "torchvision", "Deep learning", "PyTorch vision models & transforms"),
    _l("torchaudio", "torchaudio", "Deep learning", "PyTorch audio"),
    _l("pytorch-lightning", "pytorch_lightning", "Deep learning", "Lightning trainer for PyTorch"),
    _l("jax", "jax", "Deep learning", "JAX autodiff / XLA"),
    _l("flax", "flax", "Deep learning", "Neural nets on JAX"),
    _l("fastai", "fastai", "Deep learning", "High-level PyTorch training"),
    _l("tensorboard", "tensorboard", "Deep learning", "Training visualisation"),
    _l("timm", "timm", "Deep learning", "PyTorch image models"),
    _l("einops", "einops", "Deep learning", "Tensor reshaping"),
    # --- Hugging Face ----------------------------------------------------------
    _l("transformers", "transformers", "Hugging Face", "Transformer models", "standard"),
    _l("safetensors", "safetensors", "Hugging Face", "Safe tensor file format", "standard"),
    _l("huggingface_hub", "huggingface_hub", "Hugging Face", "Hub client & cache", "standard"),
    _l("tokenizers", "tokenizers", "Hugging Face", "Fast tokenizers", "standard"),
    _l("accelerate", "accelerate", "Hugging Face", "Multi-device inference/training", "standard"),
    _l("datasets", "datasets", "Hugging Face", "Dataset loading"),
    _l("diffusers", "diffusers", "Hugging Face", "Diffusion / image generation models"),
    _l("peft", "peft", "Hugging Face", "LoRA / parameter-efficient fine-tuning"),
    _l("trl", "trl", "Hugging Face", "RLHF / SFT trainers"),
    _l("optimum", "optimum", "Hugging Face", "Hardware-optimised exports"),
    _l("sentence-transformers", "sentence_transformers", "Hugging Face", "Embedding models"),
    # --- inference runtimes ----------------------------------------------------
    _l("onnx", "onnx", "Inference", "ONNX model format", "standard"),
    _l("onnxruntime", "onnxruntime", "Inference", "ONNX Runtime", "standard"),
    _l("gguf", "gguf", "Inference", "GGUF reader/writer", "standard"),
    _l("h5py", "h5py", "Inference", "HDF5 (Keras .h5 inspection)", "standard"),
    _l("llama-cpp-python", "llama_cpp", "Inference", "Run GGUF models locally (needs a C++ compiler)"),
    _l("ctransformers", "ctransformers", "Inference", "C transformers bindings"),
    _l("ctranslate2", "ctranslate2", "Inference", "Fast Transformer inference"),
    _l("faster-whisper", "faster_whisper", "Inference", "Whisper via CTranslate2"),
    _l("openai-whisper", "whisper", "Inference", "OpenAI Whisper"),
    _l("openvino", "openvino", "Inference", "Intel OpenVINO"),
    _l("ai-edge-litert", "ai_edge_litert", "Inference", "TensorFlow Lite runtime (LiteRT)"),
    _l("bitsandbytes", "bitsandbytes", "Inference", "8/4-bit quantisation", "full", "not-darwin"),
    _l("vllm", "vllm", "Inference", "High-throughput LLM serving", "full", "linux"),
    _l("mlx", "mlx", "Inference", "Apple MLX", "full", "darwin-arm64"),
    _l("mlx-lm", "mlx_lm", "Inference", "LLMs on Apple MLX", "full", "darwin-arm64"),
    _l("coremltools", "coremltools", "Inference", "Core ML conversion", "full", "darwin"),
    # --- classic ML / data -----------------------------------------------------
    _l("scikit-learn", "sklearn", "Classic ML", "scikit-learn", "standard"),
    _l("scipy", "scipy", "Classic ML", "Scientific computing"),
    _l("pandas", "pandas", "Classic ML", "DataFrames"),
    _l("xgboost", "xgboost", "Classic ML", "Gradient boosting"),
    _l("lightgbm", "lightgbm", "Classic ML", "Gradient boosting"),
    _l("catboost", "catboost", "Classic ML", "Gradient boosting"),
    # --- NLP / vision ----------------------------------------------------------
    _l("spacy", "spacy", "NLP & vision", "Industrial NLP"),
    _l("nltk", "nltk", "NLP & vision", "Natural Language Toolkit"),
    _l("gensim", "gensim", "NLP & vision", "Topic modelling / word2vec"),
    _l("sentencepiece", "sentencepiece", "NLP & vision", "Subword tokenizer"),
    _l("tiktoken", "tiktoken", "NLP & vision", "OpenAI tokenizer"),
    _l("opencv-python-headless", "cv2", "NLP & vision", "OpenCV"),
    _l("pillow", "PIL", "NLP & vision", "Image I/O", "standard"),
    # --- LLM apps --------------------------------------------------------------
    _l("openai", "openai", "LLM apps", "OpenAI-compatible client", "standard"),
    _l("anthropic", "anthropic", "LLM apps", "Anthropic client", "standard"),
    _l("ollama", "ollama", "LLM apps", "Ollama Python client", "standard"),
    _l("langchain", "langchain", "LLM apps", "LangChain"),
    _l("langchain-community", "langchain_community", "LLM apps", "LangChain integrations"),
    _l("llama-index", "llama_index", "LLM apps", "LlamaIndex RAG framework"),
    _l("chromadb", "chromadb", "LLM apps", "Vector database"),
    _l("faiss-cpu", "faiss", "LLM apps", "Vector similarity search"),
    # --- MLOps & hardware ------------------------------------------------------
    _l("mlflow", "mlflow", "MLOps", "Experiment tracking"),
    _l("wandb", "wandb", "MLOps", "Weights & Biases"),
    _l("nvidia-ml-py", "pynvml", "Hardware", "NVIDIA GPU telemetry", "standard", "not-darwin"),
    _l("py-cpuinfo", "cpuinfo", "Hardware", "CPU details", "standard"),
)

BY_PIP = {lib.pip: lib for lib in LIBRARIES}


def applicable(lib: Lib) -> bool:
    plat = sys.platform
    arm_mac = plat == "darwin" and platform.machine() == "arm64"
    return {
        "": True,
        "linux": plat.startswith("linux"),
        "darwin": plat == "darwin",
        "win32": plat == "win32",
        "darwin-arm64": arm_mac,
        "not-darwin": plat != "darwin",
    }.get(lib.only, True)


def in_profile(lib: Lib, profile: str) -> bool:
    return PROFILES.index(lib.profile) <= PROFILES.index(profile)


def select(profile: str) -> list[Lib]:
    return [lib for lib in LIBRARIES if applicable(lib) and in_profile(lib, profile)]


def installed_version(lib: Lib) -> str | None:
    try:
        if importlib.util.find_spec(lib.module) is None:
            return None
    except (ImportError, ValueError, AttributeError):
        return None
    try:
        return md.version(lib.dist)
    except md.PackageNotFoundError:
        return "?"


def status() -> list[dict]:
    out = []
    for lib in LIBRARIES:
        ok = applicable(lib)
        ver = installed_version(lib) if ok else None
        out.append(
            {
                "pip": lib.pip,
                "module": lib.module,
                "category": lib.category,
                "desc": lib.desc,
                "profile": lib.profile,
                "applicable": ok,
                "installed": ver is not None,
                "version": ver,
            }
        )
    return out


def has(module: str) -> bool:
    """True if `module` is importable (without importing it)."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError):
        return False
