"""Compare a portable environment against exact package and interpreter pins."""

from importlib import metadata
from pathlib import Path

import pytest

from ioi_das import environment


ROOT = Path(__file__).resolve().parents[1]


def test_requirements_lock_covers_runtime_and_notebook_imports():
    pins = environment.read_version_pins(ROOT / "environment/requirements-lock.txt")
    assert pins["Python"].startswith("3.10.")
    assert pins["torch"] == "2.5.1+cu121"
    assert {"transformers", "tokenizers", "pyvene", "numpy", "jsonschema", "safetensors",
            "huggingface-hub", "pytest", "matplotlib", "pandas", "nbformat"} <= pins.keys()


@pytest.mark.parametrize("installed, expected_status, expected_dependency_status", [
    ("2.5.1+cu121", "passed", "ready"),
    ("2.5.1", "failed", "version_mismatch"),
    (None, "failed", "missing_dependencies"),
])
def test_doctor_reports_exact_version_differences(
        tmp_path, monkeypatch, installed, expected_status, expected_dependency_status):
    path = tmp_path / "requirements-lock.txt"
    path.write_text("# Python==3.10.21\ntorch==2.5.1+cu121\ntransformers==4.57.6\n"
                    "tokenizers==0.22.2\npytest==9.1.1\n")
    versions = {"torch": installed, "transformers": "4.57.6", "tokenizers": "0.22.2",
                "pytest": "9.1.1", "pip": "26.2.1"}

    def version(name):
        if versions[name] is None:
            raise metadata.PackageNotFoundError(name)
        return versions[name]

    monkeypatch.setattr(environment.metadata, "version", version)
    monkeypatch.setattr(environment.platform, "python_version", lambda: "3.10.21")
    report = environment.inspect_environment(lock_file=path)
    assert report["status"] == expected_status
    assert report["dependency_status"] == expected_dependency_status
    assert report["requirements_lock"]["differences"] == (
        [] if installed == "2.5.1+cu121" else
        [{"package": "torch", "expected": "2.5.1+cu121", "installed": installed}])
    assert report["missing_dependencies"] == (["torch"] if installed is None else [])
    assert report["gpu"]["status"] == "not_checked"
    assert report["model_weights_loaded"] is False


def test_doctor_reports_interpreter_mismatch(tmp_path, monkeypatch):
    path = tmp_path / "requirements-lock.txt"
    path.write_text("# Python==3.10.21\ntransformers==4.57.6\ntokenizers==0.22.2\npytest==9.1.1\n")
    versions = {"transformers": "4.57.6", "tokenizers": "0.22.2", "pytest": "9.1.1", "pip": "26.2.1"}
    monkeypatch.setattr(environment.metadata, "version", versions.__getitem__)
    monkeypatch.setattr(environment.platform, "python_version", lambda: "3.11.0")
    report = environment.inspect_environment(lock_file=path)
    assert report["status"] == "failed"
    assert report["requirements_lock"]["differences"] == [
        {"package": "Python", "expected": "3.10.21", "installed": "3.11.0"}]


@pytest.mark.parametrize("text", ["torch>=2.5.1\n", "# Python==3.10.21\ntorch==2.5.1\ntorch==2.5.0\n"])
def test_requirements_lock_rejects_ambiguous_versions(tmp_path, text):
    path = tmp_path / "requirements-lock.txt"
    path.write_text(text)
    with pytest.raises(ValueError):
        environment.read_version_pins(path)
