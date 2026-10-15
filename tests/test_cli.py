"""Keep dataset commands thin and remove superseded audit entry points."""

from pathlib import Path
import subprocess
import sys

import pytest

from ioi_das import cli


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_audit_command_is_removed(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["audit", "--config", "configs/audit.json"])
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert not hasattr(cli, "load_config")


def test_data_subcommand_requires_build_or_audit():
    with pytest.raises(SystemExit) as error:
        cli.main(["data"])
    assert error.value.code == 2


def test_data_build_delegates_to_dataset_builder(monkeypatch, capsys):
    from ioi_das import datasets

    seen = []
    monkeypatch.setattr(datasets, "build_dataset", lambda path: seen.append(path) or {"name": "example"})
    assert cli.main(["data", "build", "--config", "configs/datasets/example.json"]) == 0
    assert seen == [Path("configs/datasets/example.json")]
    assert "example" in capsys.readouterr().out


def test_data_audit_delegates_and_prints_saved_evidence(monkeypatch, capsys):
    from ioi_das import audit

    seen = []
    def run(name, command):
        seen.append((name, command))
        return {"status": "passed", "counts": {"validation": 200},
                "unsupported_answer_checks": [], "output_dir": "/saved/audit"}

    monkeypatch.setattr(audit, "run_audit", run)
    arguments = ["data", "audit", "--dataset", "example"]
    assert cli.main(arguments) == 0
    assert seen == [("example", [sys.executable, "-m", "ioi_das.cli", *arguments])]
    assert "/saved/audit/summary.md" in capsys.readouterr().out


def test_data_audit_returns_failure_for_unsupported_answers(monkeypatch):
    from ioi_das import audit

    monkeypatch.setattr(audit, "run_audit", lambda *args, **kwargs:
                        {"status": "failed", "counts": {"validation": 1},
                         "unsupported_answer_checks": [{"sample_id": "bad"}], "output_dir": "/saved"})
    assert cli.main(["data", "audit", "--dataset", "example"]) == 2


def test_report_help_does_not_import_torch():
    code = (f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); from ioi_das.cli import main; "
            "\ntry: main(['report', '--help'])\nexcept SystemExit as error: assert error.code == 0\n"
            "assert 'torch' not in sys.modules")
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
