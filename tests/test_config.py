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


@pytest.mark.parametrize("component,head", [
    ("block_output", None), ("attention_output", None), ("mlp_output", None),
    ("head_attention_value_output", 0), ("head_query_output", 0),
    ("head_key_output", 0), ("head_value_output", 0),
])
def test_schema_accepts_each_component_without_inserting_defaults(component, head):
    overrides = [f"intervention.component={json.dumps(component)}"]
    if head is not None:
        overrides.append(f"intervention.head={head}")
    config = load_config(REFERENCE, overrides)
    assert config["intervention"]["component"] == component
    if head is None:
        assert "head" not in config["intervention"]
    else:
        assert config["intervention"]["head"] == head
    assert "site_size" not in config["intervention"]


@pytest.mark.parametrize("component", [
    "head_attention_value_output", "head_query_output", "head_key_output", "head_value_output",
])
def test_head_components_require_a_head_and_name_the_component(component):
    with pytest.raises(ConfigError, match=component + r".*requires intervention.head"):
        load_config(REFERENCE, [f"intervention.component={json.dumps(component)}"])


@pytest.mark.parametrize("component", ["block_output", "attention_output", "mlp_output"])
def test_non_head_components_reject_head_and_name_the_component(component):
    with pytest.raises(ConfigError, match=component + r".*does not accept intervention.head"):
        load_config(REFERENCE, [f"intervention.component={json.dumps(component)}",
                                "intervention.head=0"])


@pytest.mark.parametrize("head", [-1, 0.5, True, "all"])
def test_schema_rejects_negative_or_non_integer_heads(head):
    with pytest.raises(ConfigError, match=r"intervention.head"):
        load_config(REFERENCE, ['intervention.component="head_query_output"',
                                f"intervention.head={json.dumps(head)}"])


@pytest.mark.parametrize("component", ["mlp_activation", "attention_weight", "block_input"])
def test_schema_rejects_components_outside_the_supported_sites(component):
    with pytest.raises(ConfigError, match=r"intervention.component"):
        load_config(REFERENCE, [f"intervention.component={json.dumps(component)}"])


def test_grid_component_choices_obey_the_head_rule(tmp_path):
    with pytest.raises(ConfigError, match=r"head_key_output.*requires intervention.head"):
        load_config(write_experiment(tmp_path, grid={"intervention.component": ["head_key_output"]}))
    with pytest.raises(ConfigError, match=r"mlp_output.*does not accept intervention.head"):
        load_config(write_experiment(tmp_path,
            intervention={"component": "head_key_output", "head": 0},
            grid={"intervention.component": ["mlp_output"]}))


@pytest.mark.parametrize("path,expected_sha256", [
    ("configs/base.json",
     "0ad42b6bacd5f3729fc361b578b6af119644f03852f683de334eff38d658d9a7"),
    ("configs/data-scale/gpt2-medium-rank1-n1000.json",
     "ac195951575466f840992d473dc567078d88ae85ac67ac7d88bb3008978a8789"),
    ("configs/data-scale/gpt2-medium-rank1-n200-updates2500.json",
     "1dca2d448d03047b86cae8fc2f449ffabcf7dce13924a6b6cc40c628f2630b37"),
    ("configs/data-scale/gpt2-medium-rank1-n200.json",
     "f30aae6955882bab67a2f327c88bfc5abbd504c9938e53d13f075ea6aa43b79c"),
    ("configs/data-scale/gpt2-medium-rank1-n5000.json",
     "3c5c50fd04ac1d773e034e4ee999ab2341873773df21e96a79d6a49e6c2f1aa8"),
    ("configs/data-scale/gpt2-medium-rank2-n1000.json",
     "33a8725d2958e3b1242cc6e62fd796bd419c9a0b8d7ab7cefc45862323efd18a"),
    ("configs/data-scale/gpt2-medium-rank2-n200-updates2500.json",
     "42b32580de93fa1042e59db9ffcb935d4ba28ee936f07968991e2abda60387a9"),
    ("configs/data-scale/gpt2-medium-rank2-n200.json",
     "51f35a1a9f263639a57057fb509b0c614bac32afc7394f7920bf5b6f981d1ed5"),
    ("configs/data-scale/gpt2-medium-rank2-n5000.json",
     "e56086bfe91dbf36f99b6c822fe568b6a3eaed7a928dfcb6cb4d84911c622245"),
    ("configs/data-scale/gpt2-medium-rank4-n1000.json",
     "f2ae35155dbf1020351d496b085eff7c6434eb800dfe98835598ea7bf9bc3a0c"),
    ("configs/data-scale/gpt2-medium-rank4-n200-updates2500.json",
     "e98ba1281d2cdd2755405d33cb39f0289eb23a7c7b95bd5f5cb8ce65261e152d"),
    ("configs/data-scale/gpt2-medium-rank4-n200.json",
     "a4b008a8b41c5dd0f87587395d21c39b59a7d211e711819f3c29d2da9aa65b33"),
    ("configs/data-scale/gpt2-medium-rank4-n5000.json",
     "22da0fddf30c402665129b46ae75afaaa26ff13450bab99cf45c85a853f38d21"),
    ("configs/data-scale/gpt2-medium-rank8-n1000.json",
     "305a5fbd319fe3cdb3b02b68c3aa54ac399acebb5cdd39a1c9a191adfeeb9077"),
    ("configs/data-scale/gpt2-medium-rank8-n200-updates2500.json",
     "f2676202cf43ee599deee7021a4e1d3892cdb719bb878220a66bd0eabdb185f2"),
    ("configs/data-scale/gpt2-medium-rank8-n200.json",
     "84b2b843965bfb2cbd4b4ecc0729b1bf32d60295e8aa71bc833fddbaec25b801"),
    ("configs/data-scale/gpt2-medium-rank8-n5000.json",
     "bfa05eb03ca731db27aa0b6ce3ab78e2771b9958cbcda9a83245756ac4742d4c"),
    ("configs/data-scale/gpt2-small-layer8-placeholder-equal-epochs.json",
     "f84c7e7aa3b1149f72e5db49b9747212ab8e9a38cadbcc78a20319aa3dcae306"),
    ("configs/data-scale/gpt2-small-layer8-placeholder-equal-updates.json",
     "6848c5955455504db861b4048591e9d05e1ff00ec30c1235123f5a185dcc5bbd"),
    ("configs/layer-sweep/gpt2-small.json",
     "30a4e9eb983fbabff7d7bb0cc792549fe18312d03988bfdb737870fb821a882c"),
    ("configs/model-scale/gpt2-medium.json",
     "76a6dd7f8883de36b61191952947bf13489f70180dbcea7f60b1159cda8334de"),
    ("configs/rank-sweep/gpt2-medium-rank1.json",
     "20400c7ef7325f81fc7b7cde4f01d0473eedb0c742647ccce27f2105b30d9813"),
    ("configs/rank-sweep/gpt2-medium-rank2.json",
     "70329bf54377bea1528e7e16f7349d501754f5e8ef7911f0e2c35678f7ad8d56"),
    ("configs/rank-sweep/gpt2-medium-rank4.json",
     "e5c88d0a0c0724677e70cbda94261d158155b6cf596820d8ce3a8cd9a69470aa"),
    ("configs/rank-sweep/gpt2-medium-rank8.json",
     "b43cb81d4cc7160528817ebb285d56c50904841ef58741aacc26a37d53a9f8c9"),
    ("configs/rank-sweep/gpt2-small-rank1.json",
     "b8488ab716e549c314f6a4d5fd73fca1e3465ae8556577bca182f188cb9ff38d"),
    ("configs/rank-sweep/gpt2-small-rank2.json",
     "2635ae43e807a1497b045f633cce5330b0925a5945f91263d5c03f24824d835d"),
    ("configs/rank-sweep/gpt2-small-rank4.json",
     "2a6505c7e3140fdcbbccd565f585bc5d807083290baafcdce53d3703394f359a"),
    ("configs/rank-sweep/gpt2-small-rank8.json",
     "699f71415a26c2d266cab2f9835c3881c6a25439d5c50f7f31a5ff7282a9680e"),
    ("configs/single-condition-das/layer8-seed42.json",
     "f9c74ce47dc4ac9a94c090a533d6628544e0cdf93fb5a5ae850f898243015f5b"),
])
def test_existing_resolved_config_hashes_stay_unchanged(path, expected_sha256):
    assert load_config(ROOT / path).sha256 == expected_sha256
