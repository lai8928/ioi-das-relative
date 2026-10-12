"""Real pinned-tokenizer checks of occurrence, padding, and answer contracts."""

import json
from pathlib import Path

import pytest

from ioi_das.checks import run_focused_checks
from ioi_das.tokenization import load_tokenizers


@pytest.fixture(scope="module")
def tokenizers():
    config = json.loads((Path(__file__).resolve().parents[1] / "configs/audit.json").read_text())
    return load_tokenizers(config["tokenizer"])


def test_real_tokenizer_position_contracts(tokenizers):
    result = run_focused_checks(*tokenizers)
    assert result["status"] == "passed"
    assert result["actual_indices"]["N-1"] == {"base": [16, 20], "source": [20, 16]}
