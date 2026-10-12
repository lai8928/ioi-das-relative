"""Verify original sampling semantics directly against the preserved upstream."""

import ast
from collections import OrderedDict
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import typing
import unittest

from ioi_das.data import generate_pairs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_DIR = PROJECT_ROOT / "vendor" / "pyvene_upstream"


class UpstreamParityTests(unittest.TestCase):
    def test_all_pairs_match_extracted_upstream_sampling_and_labels(self):
        """Execute only original stdlib data methods, with the declared set fix."""
        utility = UPSTREAM_DIR / "tutorials/advanced_tutorials/tutorial_ioi_utils.py"
        original = utility.read_text(encoding="utf-8")
        unordered = "unique_ids = list(set(pattern))"
        self.assertEqual(original.count(unordered), 1)
        reference_text = original.replace(unordered, "unique_ids = list(dict.fromkeys(pattern))")
        definitions = []
        for node in ast.parse(reference_text).body:
            if isinstance(node, ast.ClassDef) and node.name in ("Prompt", "PromptDistribution"):
                if node.name == "PromptDistribution":
                    node.body = [
                        method for method in node.body
                        if not isinstance(method, ast.FunctionDef) or method.name in ("__init__", "sample_one")
                    ]
                definitions.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name == "load_data":
                definitions.append(node)
        self.assertEqual(len(definitions), 3)
        namespace = dict(vars(typing))
        namespace.update(OrderedDict=OrderedDict, Path=Path, random=random.Random(42), json=json)
        # Importing the full utility would introduce model/pyvene dependencies.
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(utility), "exec"), namespace)
        resources = {}
        for key in ("names", "objects", "places", "templates"):
            path = UPSTREAM_DIR / f"tutorials/advanced_tutorials/tutorial_data/{key}.json"
            resources[key] = json.loads(path.read_text(encoding="utf-8"))
        generated = generate_pairs(UPSTREAM_DIR, seed=42)
        checked = 0
        for split in ("train", "test"):
            options = {}
            for key in ("names", "objects", "places"):
                midpoint = len(resources[key]) // 2
                options[key] = resources[key][:midpoint] if split == "train" else resources[key][midpoint:]
            options["templates"] = resources["templates"][:2] if split == "train" else resources["templates"][2:]
            distribution = namespace["PromptDistribution"](**options)
            combinations = (
                [("ABB", "ABB"), ("ABB", "BAB"), ("BAB", "ABB"), ("BAB", "BAB")]
                if split == "train" else [("ABB", "BAB"), ("BAB", "ABB")]
            )
            index = 0
            for base_pattern, source_pattern in combinations:
                bases = [distribution.sample_one(base_pattern) for _ in range(50)]
                sources = [
                    base.resample_pattern(base_pattern, source_pattern, options["names"])
                    for base in bases
                ]
                for base, source in zip(bases, sources):
                    pair = generated[split][index]
                    with self.subTest(sample_id=pair.sample_id):
                        for reference, record in ((base, pair.base), (source, pair.source)):
                            self.assertEqual(
                                (reference.sentence, reference.names, reference.io_name, reference.s_name, reference.io_pos, reference.s1_pos, reference.obj, reference.place),
                                (record.text, record.names, record.io_name, record.subject_name, record.io_pos, record.s1_pos, record.obj, record.place),
                            )
                        expected = (base.io_name, base.s_name) if base.s1_pos == source.s1_pos else (base.s_name, base.io_name)
                        self.assertEqual((pair.counterfactual_answer, pair.counterfactual_alternative), expected)
                    index += 1
                    checked += 1
        self.assertEqual(checked, 300)

    def test_full_saved_datasets_are_deterministic_across_hash_seeds(self):
        script = """
import json
from pathlib import Path
import sys
import tempfile
from ioi_das.data import generate_pairs, sha256_file, write_pairs
datasets = generate_pairs(Path(sys.argv[1]), seed=42)
with tempfile.TemporaryDirectory() as directory:
    hashes = {}
    for split, pairs in datasets.items():
        path = Path(directory) / (split + '.jsonl')
        write_pairs(path, pairs)
        hashes[split] = sha256_file(path)
    print(json.dumps(hashes, sort_keys=True))
"""
        digests = []
        for hash_seed in ("1", "982451653"):
            environment = dict(os.environ)
            environment["PYTHONHASHSEED"] = hash_seed
            environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
            result = subprocess.run(
                [sys.executable, "-B", "-c", script, str(UPSTREAM_DIR)],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            digests.append(json.loads(result.stdout))
        self.assertEqual(set(digests[0]), {"train", "test"})
        self.assertEqual(digests[0], digests[1])


if __name__ == "__main__":
    unittest.main()
