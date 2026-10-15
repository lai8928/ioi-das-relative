"""Check pinned model assets and metadata without downloads or pretrained weights."""

import json
from pathlib import Path
import shlex

import huggingface_hub
import pytest

from ioi_das import models, pipeline
from ioi_das.config import load_config


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "configs/single-condition-das/layer8-seed42.json"
REVISION = "a" * 40
ASSET_NAMES = ("config.json", "model.safetensors", "tokenizer.json",
               "tokenizer_config.json", "vocab.json", "merges.txt")


@pytest.fixture
def cached_assets(tmp_path, monkeypatch):
    files = {}
    calls = []
    for filename in ASSET_NAMES:
        path = tmp_path / filename
        path.write_text("cached fixture", encoding="utf-8")
        files[filename] = path

    def lookup(repository, filename, *, revision):
        calls.append((repository, filename, revision))
        return str(files[filename]) if filename in files else None

    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", lookup)
    return files, calls


@pytest.mark.parametrize("family", ["gpt2", "gpt2-medium", "gpt2-large", "gpt2-xl"])
@pytest.mark.parametrize("prefix", ["", "openai-community/"])
def test_model_names_normalize_to_gpt2_family(family, prefix):
    assert models.validate_model(prefix + family, REVISION) == family


@pytest.mark.parametrize("name, revision", [
    ("gpt2-v2", REVISION), ("other/gpt2", REVISION),
    ("gpt2", "main"), ("gpt2", "a" * 39), ("gpt2", "A" * 40),
])
def test_model_names_and_revisions_are_explicit(name, revision):
    with pytest.raises(ValueError):
        models.validate_model(name, revision)


def test_cache_guard_returns_verified_assets_from_model_and_tokenizer_aliases(cached_assets):
    files, calls = cached_assets
    actual = models.require_cached_model("gpt2-medium", REVISION,
                                         tokenizer_name="openai-community/gpt2-medium")
    assert actual == files
    assert calls == [("gpt2-medium", filename, REVISION) for filename in ASSET_NAMES[:2]] + [
        ("openai-community/gpt2-medium", filename, REVISION) for filename in ASSET_NAMES[2:]]


def test_loader_cache_guard_can_require_only_model_files(cached_assets):
    files, calls = cached_assets
    for filename in ASSET_NAMES[2:]:
        del files[filename]
    actual = models.require_cached_model("gpt2-medium", REVISION, include_tokenizer=False)
    assert actual == files
    assert calls == [("gpt2-medium", filename, REVISION) for filename in ASSET_NAMES[:2]]


@pytest.mark.parametrize("filename", ASSET_NAMES)
def test_each_required_missing_asset_reports_the_exact_download_command(cached_assets, filename):
    files, _ = cached_assets
    files[filename].unlink()
    with pytest.raises(ValueError) as error:
        models.require_cached_model("gpt2-medium", REVISION)
    assert filename in str(error.value)
    assert models.model_download_command("gpt2-medium", REVISION) in str(error.value)


def test_cache_guard_rejects_different_tokenizer_family_before_cache_lookup(cached_assets):
    _, calls = cached_assets
    with pytest.raises(ValueError, match="same GPT-2 family"):
        models.require_cached_model("gpt2-medium", REVISION, tokenizer_name="gpt2")
    assert calls == []


def test_download_command_pins_revision_and_lists_only_required_assets():
    command = shlex.split(models.model_download_command("openai-community/gpt2-medium", REVISION))
    assert command[0] == "HF_HUB_OFFLINE=0"
    assert Path(command[1]).name == "hf"
    assert command[2:4] == ["download", "openai-community/gpt2-medium"]
    assert command[4:-2] == list(ASSET_NAMES)
    assert command[-2:] == ["--revision", REVISION]


@pytest.mark.parametrize("name, layers, width, parameters", [
    ("gpt2", 12, 768, 124439808),
    ("gpt2-medium", 24, 1024, 354823168),
])
def test_cached_metadata_reads_config_without_loading_weights(
        cached_assets, name, layers, width, parameters):
    files, calls = cached_assets
    files["config.json"].write_text(json.dumps({
        "model_type": "gpt2", "n_layer": layers, "n_embd": width,
        "vocab_size": 50257, "n_positions": 1024, "n_inner": None}), encoding="utf-8")
    actual = models.cached_model_metadata(name, REVISION)
    assert actual == {"name": name, "revision": REVISION, "parameter_count": parameters,
                      "layer_count": layers, "hidden_size": width}
    assert calls == [(name, "config.json", REVISION)]


def test_missing_medium_cache_stops_before_data_reads_or_output_allocation(monkeypatch):
    config = load_config(REFERENCE, ['model.name="gpt2-medium"',
                                     'tokenizer.name="gpt2-medium"',
                                     f'model.revision="{REVISION}"',
                                     f'tokenizer.revision="{REVISION}"'])
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "_git_state", lambda root:
                        {"commit": "b" * 40, "clean_tree": True, "protected_tree_clean": True})
    monkeypatch.setattr(pipeline, "_dataset_inputs", lambda *args:
                        pytest.fail("Missing model must fail before reading datasets"))
    monkeypatch.setattr(pipeline, "_allocate_output", lambda *args:
                        pytest.fail("Missing model must fail before allocating output"))
    with pytest.raises(ValueError) as error:
        pipeline.run_experiment(config, smoke=True)
    assert models.model_download_command("gpt2-medium", REVISION) in str(error.value)
