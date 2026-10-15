"""Load immutable experiment settings with inheritance and schema validation."""

import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator

from .models import validate_model


class ConfigError(ValueError):
    """An invalid experiment configuration or override."""


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def config_sha256(values: Mapping[str, Any]) -> str:
    """Return a stable settings hash including the execution order of grid axes."""
    plain = _plain(values)
    payload = {"config": plain, "grid_order": list(plain.get("grid", {}))}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ResolvedConfig(Mapping[str, Any]):
    """Expose validated settings without allowing mutation of nested values."""

    _values: Mapping[str, Any]
    project_root: Path
    source_path: Path
    sha256: str

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def to_dict(self) -> dict[str, Any]:
        """Return an independent mutable JSON representation of these settings."""
        return _plain(self._values)


def _merge(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(parent)
    for key, value in child.items():
        if value is None:
            if key not in merged:
                raise ConfigError(f"Cannot remove absent inherited setting {key!r}; check the setting name.")
            del merged[key]
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _reject_constant(value: str) -> None:
    raise ConfigError(f"Nonfinite JSON number {value!r}; use a finite number.")


def _read_inherited(path: Path, stack: tuple[Path, ...] = ()) -> dict[str, Any]:
    if path in stack:
        chain = " -> ".join(str(item) for item in (*stack, path))
        raise ConfigError(f"Configuration inheritance cycle: {chain}; remove an extends link.")
    try:
        values = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"Cannot read configuration {path}: {error}; provide a valid JSON file.") from error
    if not isinstance(values, dict):
        raise ConfigError(f"Configuration {path} contains {type(values).__name__}; use a JSON object.")
    if "extends" not in values:
        return values
    inherited = values.pop("extends")
    if not isinstance(inherited, str) or not inherited:
        raise ConfigError(f"Configuration {path} has invalid extends {inherited!r}; use a file path.")
    parent = (path.parent / inherited).resolve()
    return _merge(_read_inherited(parent, (*stack, path)), values)


def set_path(values: dict[str, Any], path: str, value: Any) -> None:
    """Set a dotted-path value within existing parent objects."""
    keys = path.split(".")
    if not all(keys):
        raise ConfigError(f"Invalid override path {path!r}; use dot-separated setting names.")
    target = values
    for key in keys[:-1]:
        if key not in target or not isinstance(target[key], dict):
            raise ConfigError(f"Setting path {path!r} has no object at {key!r}; use an existing object.")
        target = target[key]
    target[keys[-1]] = value


def _apply_override(values: dict[str, Any], override: str) -> None:
    path, separator, encoded = override.partition("=")
    if not separator or not path:
        raise ConfigError(f"Invalid override {override!r}; use key.path=JSON_VALUE.")
    try:
        value = json.loads(encoded, parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        raise ConfigError(f"Override {override!r} is not JSON; quote string values, for example "
                          "device=\"cuda:0\".") from error
    if value is None:
        keys = path.split(".")
        target = values
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                raise ConfigError(f"Setting path {path!r} has no object at {key!r}; use an existing object.")
            target = target[key]
        if keys[-1] not in target:
            raise ConfigError(f"Cannot remove absent setting {path!r}; check the setting name.")
        del target[keys[-1]]
    else:
        set_path(values, path, value)


def _project_root(path: Path) -> Path:
    for directory in path.parents:
        if (directory / "configs" / "schema.json").is_file():
            return directory
    return Path(__file__).resolve().parents[2]


def _validate_grid(values: dict[str, Any], validator: Draft202012Validator) -> None:
    for path, choices in values.get("grid", {}).items():
        target: Any = values
        for key in path.split("."):
            if not isinstance(target, dict) or key not in target or path.split(".")[0] == "grid":
                raise ConfigError(f"Grid axis {path!r} is not a setting; use an existing dotted path.")
            target = target[key]
        if isinstance(target, dict):
            raise ConfigError(f"Grid axis {path!r} names an object; use a dotted path to a leaf setting.")
        if choices == "all":
            if path != "intervention.layer":
                raise ConfigError(f"Grid axis {path!r} uses 'all'; only intervention.layer supports it.")
            continue
        for choice in choices:
            candidate = deepcopy(values)
            set_path(candidate, path, choice)
            error = next(validator.iter_errors(candidate), None)
            if error:
                raise ConfigError(f"Grid axis {path!r} has invalid value {choice!r}: "
                                  f"{error.message}; choose a schema-valid value.")


def validate_config(values: Mapping[str, Any], project_root: Path | None = None) -> None:
    """Reject unknown keys and invalid setting values using the repository schema."""
    root = project_root or Path(__file__).resolve().parents[2]
    schema = json.loads((root / "configs" / "schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    plain = _plain(values)
    error = next(validator.iter_errors(plain), None)
    if error:
        location = ".".join(str(key) for key in error.absolute_path) or "<root>"
        raise ConfigError(f"Invalid configuration at {location}: {error.message}; fix the setting.")
    if validate_model(plain["model"]["name"], plain["model"]["revision"]) != \
            validate_model(plain["tokenizer"]["name"], plain["tokenizer"]["revision"]) or \
            plain["model"]["revision"] != plain["tokenizer"]["revision"]:
        raise ConfigError("Model and tokenizer families or revisions differ; use the same pinned revision.")
    for split, reference in plain["data"].items():
        if reference.split("/")[-1] != split:
            raise ConfigError(f"Data split {split!r} references {reference!r}; use a matching split name.")
    if "selection" in plain:
        if "data.train" in plain.get("grid", {}):
            raise ConfigError("Layer selection cannot mix training datasets; use a fixed layer config without selection.")
        if "validation" not in plain["data"]:
            raise ConfigError("Selection requires data.validation; configure a registered validation split.")
        for split in plain["selection"]["evaluate_after_lock"]:
            if split in {"train", "validation"} or split not in plain["data"]:
                raise ConfigError(f"Locked split {split!r} must be configured separately from train and validation.")
    _validate_grid(plain, validator)


def load_config(path: str | Path, overrides: Sequence[str] = ()) -> ResolvedConfig:
    """Return immutable, inherited, overridden, and validated experiment settings."""
    source = Path(path).resolve()
    root = _project_root(source)
    values = _read_inherited(source)
    for override in overrides:
        _apply_override(values, override)
    validate_config(values, root)
    if source.name != "base.json" or source.parent.name != "configs":
        expected = {"task": source.parent.name, "name": source.stem}
        for key, value in expected.items():
            if values.get(key) != value:
                raise ConfigError(f"Configuration {key} {values.get(key)!r} does not match {value!r}; "
                                  "match task to the directory and name to the file stem.")
    return ResolvedConfig(_freeze(values), root, source, config_sha256(values))
