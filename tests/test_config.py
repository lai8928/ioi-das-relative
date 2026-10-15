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
