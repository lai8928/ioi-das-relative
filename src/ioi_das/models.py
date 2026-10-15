"""Validate pinned GPT-2 families and inspect explicit local model assets."""

import json
from pathlib import Path
import re
import shlex
import sys
from typing import Any


MODEL_FILES = ("config.json", "model.safetensors")
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt")
FAMILIES = ("gpt2", "gpt2-medium", "gpt2-large", "gpt2-xl")


def validate_model(name: str, revision: str) -> str:
    """Return the GPT-2 family name after validating its pinned revision."""
    family = name.removeprefix("openai-community/")
    if family not in FAMILIES:
        raise ValueError(f"Unsupported GPT-2 family {name!r}; choose {', '.join(FAMILIES)}.")
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError(f"Model {name!r} requires a pinned revision of 40 lowercase hexadecimal characters; got {revision!r}.")
    return family


def model_download_command(name: str, revision: str) -> str:
    """Return an explicit command that downloads only the required pinned files."""
    validate_model(name, revision)
    command = [str(Path(sys.executable).with_name("hf")), "download", name,
               *MODEL_FILES, *TOKENIZER_FILES, "--revision", revision]
    return "HF_HUB_OFFLINE=0 " + shlex.join(command)


def require_cached_model(name: str, revision: str,
                         tokenizer_name: str | None = None, *,
                         include_tokenizer: bool = True) -> dict[str, Path]:
    """Reject missing assets without network access or output allocation."""
    from huggingface_hub import try_to_load_from_cache

    family = validate_model(name, revision)
    tokenizer_name = tokenizer_name or name
    if validate_model(tokenizer_name, revision) != family:
        raise ValueError("Model and tokenizer must name the same GPT-2 family and pinned revision.")
    assets = {}
    requests = [(name, MODEL_FILES)]
    if include_tokenizer:
        requests.append((tokenizer_name, TOKENIZER_FILES))
    for repository, filenames in requests:
        missing = []
        for filename in filenames:
            cached = try_to_load_from_cache(repository, filename, revision=revision)
            if isinstance(cached, str) and Path(cached).is_file():
                assets[filename] = Path(cached)
            else:
                missing.append(filename)
        if missing:
            raise ValueError(f"Pinned assets are not cached for {repository}@{revision}: {', '.join(missing)}. "
                             f"Download explicitly before running:\n{model_download_command(repository, revision)}")
    return assets


def cached_model_metadata(name: str, revision: str) -> dict[str, Any]:
    """Read GPT-2 dimensions and tied-weight parameter count without loading weights."""
    from huggingface_hub import try_to_load_from_cache

    validate_model(name, revision)
    cached = try_to_load_from_cache(name, "config.json", revision=revision)
    if not isinstance(cached, str) or not Path(cached).is_file():
        raise ValueError(f"Model config is not cached; run {model_download_command(name, revision)}")
    config = json.loads(Path(cached).read_text(encoding="utf-8"))
    if config.get("model_type") != "gpt2":
        raise ValueError(f"Cached model {name!r} has model_type={config.get('model_type')!r}; use a GPT-2 checkpoint.")
    width, layers = config["n_embd"], config["n_layer"]
    inner = config.get("n_inner") or 4 * width
    embeddings = (config["vocab_size"] + config["n_positions"]) * width
    block = 4 * width ** 2 + 2 * width * inner + 9 * width + inner
    parameters = embeddings + layers * block + 2 * width
    return {"name": name, "revision": revision, "parameter_count": parameters,
            "layer_count": layers, "hidden_size": width}
