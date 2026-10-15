"""Exercise inherited, immutable and strictly validated experiment settings."""

import json
from pathlib import Path

import pytest

from ioi_das.config import ConfigError, config_sha256, load_config, validate_config


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "configs/single-condition-das/layer8-seed42.json"


def write_experiment(tmp_path, **values):
    directory = tmp_path / "example-task"
    directory.mkdir(exist_ok=True)
    path = directory / "example.json"
    settings = {"extends": str(ROOT / "configs/base.json"),
                "task": directory.name, "name": path.stem, **values}
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def test_reference_config_preserves_defaults_and_is_immutable():
    config = load_config(REFERENCE)
    assert config["training"]["epochs"] == 10
    assert config["training"]["schedule"] == "legacy_per_update_linearlr"
    assert config["data"]["train"] == "legacy_v1/train"
    assert config.project_root == ROOT
    assert config.source_path == REFERENCE
    with pytest.raises(TypeError):
        config["training"]["epochs"] = 1
    values = config.to_dict()
    values["training"]["betas"][0] = 0.5
    assert config["training"]["betas"][0] == 0.9
    assert config.sha256 == config_sha256(config.to_dict())


def test_recursive_extends_merges_objects_and_replaces_lists(tmp_path):
    parent = tmp_path / "parent.json"
    parent.write_text(json.dumps({"extends": str(ROOT / "configs/base.json"),
                                  "training": {"epochs": 3, "betas": [0.5, 0.95]}}))
    path = write_experiment(tmp_path, extends="../parent.json", training={"batch_size": 5})
    config = load_config(path)
    assert config["training"]["epochs"] == 3
    assert config["training"]["batch_size"] == 5
    assert config["training"]["betas"] == (0.5, 0.95)
    assert config["training"]["scheduler"]["total_iters"] == 10
    assert "extends" not in config


def test_dotted_overrides_parse_json_and_validate(tmp_path):
    path = write_experiment(tmp_path)
    config = load_config(path, ["training.epochs=2", 'device="cpu"', "training.betas=[0.7,0.8]"])
    assert config["training"]["epochs"] == 2
    assert config["device"] == "cpu"
    assert config["training"]["betas"] == (0.7, 0.8)
    with pytest.raises(ConfigError, match="not JSON"):
        load_config(path, ["device=cpu"])
    with pytest.raises(ConfigError, match="minimum"):
        load_config(path, ["training.epochs=0"])
    with pytest.raises(ConfigError, match="no object"):
        load_config(path, ["missing.option=1"])


@pytest.mark.parametrize("override", ["unknown=1", "training.unknown=1", "model.unknown=1"])
def test_unknown_keys_are_rejected(override):
    with pytest.raises(ConfigError, match="Additional properties"):
        load_config(REFERENCE, [override])


def test_inheritance_cycle_is_rejected(tmp_path):
    path = write_experiment(tmp_path, extends="example.json")
    with pytest.raises(ConfigError, match="inheritance cycle"):
        load_config(path)


@pytest.mark.parametrize("values", [{"task": "other-task"}, {"name": "other-name"}])
def test_config_identity_matches_directory_and_file(tmp_path, values):
    with pytest.raises(ConfigError, match="does not match"):
        load_config(write_experiment(tmp_path, **values))


def test_grid_axes_are_ordered_and_checked(tmp_path):
    path = write_experiment(tmp_path, grid={"intervention.layer": [7, 8], "seed": [42, 43]})
    config = load_config(path)
    assert list(config["grid"]) == ["intervention.layer", "seed"]
    reversed_values = config.to_dict()
    reversed_values["grid"] = dict(reversed(list(reversed_values["grid"].items())))
    assert config_sha256(reversed_values) != config.sha256
    for grid, message in [({"unknown": [1]}, "not a setting"),
                          ({"training": [{}]}, "names an object"),
                          ({"grid": [{}]}, "not a setting"),
                          ({"seed": "all"}, "only intervention.layer"),
                          ({"seed": [-1]}, "invalid value"),
                          ({"seed": []}, "not valid")]:
        with pytest.raises(ConfigError, match=message):
            load_config(write_experiment(tmp_path, grid=grid))


def test_schema_accepts_shared_defaults_and_rejects_nonfinite_values(tmp_path):
    validate_config(json.loads((ROOT / "configs/base.json").read_text()))
    path = write_experiment(tmp_path)
    with pytest.raises(ConfigError, match="Nonfinite"):
        load_config(path, ["training.learning_rate=NaN"])


@pytest.mark.parametrize("extends", [None, 1, ""])
def test_invalid_extends_is_rejected(tmp_path, extends):
    with pytest.raises(ConfigError, match="invalid extends"):
        load_config(write_experiment(tmp_path, extends=extends))


def test_selection_requires_validation_and_separate_registered_locked_splits():
    path = ROOT / "configs/layer-sweep/gpt2-small.json"
    config = load_config(path)
    assert config["selection"]["evaluate_after_lock"] == ("test",)
    for override, message in [
        ('data={"train":"legacy_v1/train","test":"legacy_v1/test"}', "requires data.validation"),
        ('selection.evaluate_after_lock=["validation"]', "configured separately"),
        ('selection.evaluate_after_lock=["missing"]', "configured separately"),
        ('selection.unknown=true', "unknown"),
        ('data.validation="val_indist_v1/test"', "matching split name"),
    ]:
        with pytest.raises(ConfigError, match=message):
            load_config(path, [override])


@pytest.mark.parametrize("family", ["gpt2", "gpt2-medium", "gpt2-large", "gpt2-xl"])
@pytest.mark.parametrize("prefix", ["", "openai-community/"])
def test_schema_accepts_every_pinned_gpt2_family_name(family, prefix):
    name = prefix + family
    config = load_config(REFERENCE, [f"model.name={json.dumps(name)}",
                                     f"tokenizer.name={json.dumps(name)}"])
    assert config["model"]["name"] == config["tokenizer"]["name"] == name


@pytest.mark.parametrize("model_name, tokenizer_name", [
    ("gpt2-medium", "openai-community/gpt2-medium"),
    ("openai-community/gpt2-xl", "gpt2-xl"),
])
def test_model_and_tokenizer_aliases_may_name_the_same_family(model_name, tokenizer_name):
    config = load_config(REFERENCE, [f"model.name={json.dumps(model_name)}",
                                     f"tokenizer.name={json.dumps(tokenizer_name)}"])
    assert config["model"]["name"] == model_name
    assert config["tokenizer"]["name"] == tokenizer_name


@pytest.mark.parametrize("override", [
    'tokenizer.name="gpt2-medium"',
    'tokenizer.revision="' + "b" * 40 + '"',
])
def test_model_and_tokenizer_require_the_same_family_and_revision(override):
    with pytest.raises(ConfigError, match="same pinned revision"):
        load_config(REFERENCE, [override])


@pytest.mark.parametrize("section", ["model", "tokenizer"])
@pytest.mark.parametrize("revision", ["main", "a" * 39, "b" * 41, "z" * 40])
def test_schema_requires_exact_40_hex_revisions(section, revision):
    with pytest.raises(ConfigError, match="does not match"):
        load_config(REFERENCE, [f"{section}.revision={json.dumps(revision)}"])


@pytest.mark.parametrize("section", ["model", "tokenizer"])
def test_schema_rejects_other_model_architectures(section):
    with pytest.raises(ConfigError):
        load_config(REFERENCE, [f'{section}.name="bert-base-uncased"'])


def test_update_budget_removes_inherited_epochs_explicitly(tmp_path):
    path = write_experiment(tmp_path, training={"epochs": None, "max_updates": 7})
    config = load_config(path)
    assert "epochs" not in config["training"]
    assert config["training"]["max_updates"] == 7
    assert config["training"]["scheduler"]["total_iters"] == 10
    switched = load_config(path, ["training.max_updates=null", "training.epochs=3"])
    assert "max_updates" not in switched["training"]
    assert switched["training"]["epochs"] == 3


@pytest.mark.parametrize("training", [{"max_updates": 1}, {"epochs": None},
                                       {"epochs": None, "max_updates": 0},
                                       {"epochs": None, "max_updates": True}])
def test_schema_rejects_conflicting_missing_or_invalid_budgets(tmp_path, training):
    with pytest.raises(ConfigError):
        load_config(write_experiment(tmp_path, training=training))


def test_inheritance_removal_rejects_unknown_names(tmp_path):
    with pytest.raises(ConfigError, match="absent inherited setting"):
        load_config(write_experiment(tmp_path, training={"typo": None}))
    with pytest.raises(ConfigError, match="absent setting"):
        load_config(REFERENCE, ["training.typo=null"])


def test_original_condition_config_hash_is_unchanged():
    metadata = json.loads((ROOT / "outputs/single-condition-das/20261015-layer8-seed42-3/run.json").read_text())
    assert load_config(REFERENCE).sha256 == metadata["config_sha256"]


def test_training_grid_does_not_reselect_the_layer():
    with pytest.raises(ConfigError, match="cannot mix training datasets"):
        load_config(ROOT / "configs/layer-sweep/gpt2-small.json",
                    ['grid={"data.train":["legacy_v1/train"]}'])
