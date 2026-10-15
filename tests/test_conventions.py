"""Enforce the engineering rules explicitly marked as tested."""

import ast
import copy
import io
import json
from pathlib import Path
import re
import tokenize

import jsonschema
import pytest

from ioi_das.config import load_config, validate_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIGS = PROJECT_ROOT / "configs"
LEGACY_CONFIGS = {"audit.json", "phase2.json"}
LEGACY_OUTPUT_ROOTS = {"audit", "audit-manual-check", "environment", "notebooks", "phase2"}
FROZEN_SCRIPTS = {"render_phase2_notebook.py"}
HISTORICAL_NAME = re.compile(r"phase_?\d|milestone|(?:^|_)m\d+(?:_|$)", re.IGNORECASE)
DATED_NAME = re.compile(r"(?:^|[_-])\d{4}[-_]?\d{2}[-_]?\d{2}(?:[_-]|$)")


@pytest.mark.parametrize("directory", ["src", "tests"])
def test_python_file_names_describe_functions(directory):
    for path in sorted((PROJECT_ROOT / directory).rglob("*.py")):
        assert not HISTORICAL_NAME.search(path.stem), path
        assert not DATED_NAME.search(path.stem), path


def test_source_identifiers_describe_functions():
    for path in sorted((PROJECT_ROOT / "src").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NAME:
                assert not HISTORICAL_NAME.search(token.string), (path, token.start, token.string)
                assert not DATED_NAME.search(token.string), (path, token.start, token.string)


def test_every_experiment_config_validates_and_matches_its_path():
    schema = json.loads((CONFIGS / "schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    validate_config(json.loads((CONFIGS / "base.json").read_text()))
    experiment_paths = []
    for path in sorted(CONFIGS.rglob("*.json")):
        if path.parent == CONFIGS and path.name in LEGACY_CONFIGS | {"base.json", "schema.json"}:
            continue
        if path.parent.name == "datasets":
            continue  # Dataset-builder recipes have a separate, future schema.
        config = load_config(path)
        assert config["task"] == path.parent.name, path
        assert config["name"] == path.stem, path
        experiment_paths.append(path)
    assert experiment_paths, "At least one experiment must exercise the shared config schema."


@pytest.mark.parametrize("section", [None, "model", "tokenizer", "data", "intervention", "training"])
def test_schema_rejects_unknown_keys_at_each_config_level(section):
    config = copy.deepcopy(load_config(CONFIGS / "single-condition-das/layer8-seed42.json").to_dict())
    target = config if section is None else config[section]
    target["unrecognized_option"] = True
    with pytest.raises(ValueError, match="unrecognized_option"):
        validate_config(config)


def test_new_scripts_are_thin_package_entry_points():
    for path in sorted((PROJECT_ROOT / "scripts").rglob("*.py")):
        if path.parent.name == "adhoc":
            assert re.fullmatch(r"\d{8}-[a-z][a-z0-9-]*", path.stem), path
            continue
        if path.name in FROZEN_SCRIPTS:
            continue  # The brief freezes the saved-notebook builder and its output.
        assert re.fullmatch(r"[a-z]+_[a-z][a-z_]*", path.stem), path
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) < 100, path
        tree = ast.parse(source, filename=str(path))
        imported_names, imported_modules = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("ioi_das"):
                imported_names.update(alias.asname or alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported_modules.update(alias.asname or alias.name.split(".")[0] for alias in node.names
                                        if alias.name.startswith("ioi_das"))
        assert imported_names or imported_modules, f"{path} must import its behavior from ioi_das."
        calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if isinstance(called, ast.Name) and called.id in imported_names:
                calls.append(node)
            elif isinstance(called, ast.Attribute):
                while isinstance(called, ast.Attribute):
                    called = called.value
                if isinstance(called, ast.Name) and called.id in imported_modules:
                    calls.append(node)
        assert len(calls) == 1, f"{path} must make one package entry-point call."


def test_every_new_experiment_output_has_run_metadata():
    for task_dir in sorted((PROJECT_ROOT / "outputs").iterdir()):
        if not task_dir.is_dir() or task_dir.name in LEGACY_OUTPUT_ROOTS or task_dir.name.startswith("."):
            continue
        for experiment_dir in sorted(task_dir.iterdir()):
            if experiment_dir.is_dir():
                assert (experiment_dir / "run.json").is_file(), experiment_dir
