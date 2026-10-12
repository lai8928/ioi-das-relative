"""Focused semantic and persistence checks for the original IOI POSITION data."""

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from ioi_das.data import (
    build_prompt,
    counterfactual_names,
    generate_pairs,
    load_pairs,
    write_pairs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_DIR = PROJECT_ROOT / "vendor" / "pyvene_upstream"
TEMPLATE = "Then, {name_A} and {name_B} went to the {place}. {name_C} gave a {object} to"


def prompt(names, pattern, template=TEMPLATE):
    return build_prompt(names, template, 0, pattern, "ring", "store")


class PromptSemanticsTests(unittest.TestCase):
    def test_hand_checked_abb_and_bab_roles(self):
        abb = prompt(("Alice", "Bob", "Bob"), "ABB")
        self.assertEqual((abb.io_name, abb.subject_name, abb.io_pos, abb.s1_pos), ("Alice", "Bob", 0, 1))
        self.assertEqual([(item.role, item.occurrence) for item in abb.occurrences], [("IO", 1), ("S1", 1), ("S2", 2)])
        self.assertEqual([item.char_span for item in abb.occurrences], [(6, 11), (16, 19), (39, 42)])
        bab = prompt(("Bob", "Alice", "Bob"), "BAB")
        self.assertEqual((bab.io_name, bab.subject_name, bab.io_pos, bab.s1_pos), ("Alice", "Bob", 1, 0))
        self.assertEqual([(item.role, item.occurrence) for item in bab.occurrences], [("S1", 1), ("IO", 1), ("S2", 2)])
        self.assertEqual([item.char_span for item in bab.occurrences], [(6, 9), (14, 19), (39, 42)])

    def test_name_fields_define_spans_despite_other_matching_strings(self):
        text_template = "Bob remembers {name_A} and {name_B}. {name_C} gave {object} to"
        record = build_prompt(("Alice", "Bob", "Bob"), text_template, 0, "ABB", "Bob", "store")
        subject_spans = [item.char_span for item in record.occurrences if item.role in ("S1", "S2")]
        self.assertEqual(subject_spans, [(24, 27), (29, 32)])
        self.assertNotEqual(subject_spans[0][0], record.text.find("Bob"))
        for occurrence in record.occurrences:
            start, end = occurrence.char_span
            self.assertEqual(record.text[start:end], occurrence.name)

    def test_position_counterfactual_uses_base_names_with_unrelated_source_names(self):
        base = prompt(("Alice", "Bob", "Bob"), "ABB")
        same_position_source = prompt(("Carol", "Dave", "Dave"), "ABB")
        changed_position_source = prompt(("Carol", "Dave", "Carol"), "BAB")
        self.assertEqual(counterfactual_names(base, same_position_source), ("Alice", "Bob"))
        self.assertEqual(counterfactual_names(base, changed_position_source), ("Bob", "Alice"))
        self.assertNotEqual(counterfactual_names(base, changed_position_source)[0], changed_position_source.io_name)


class OriginalSamplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pairs = generate_pairs(UPSTREAM_DIR, seed=42)
        cls.resources = {}
        resource_dir = UPSTREAM_DIR / "tutorials" / "advanced_tutorials" / "tutorial_data"
        for name in ("names", "objects", "places", "templates"):
            cls.resources[name] = json.loads((resource_dir / f"{name}.json").read_text(encoding="utf-8"))

    def test_original_counts_split_boundaries_and_source_remapping(self):
        self.assertEqual(len(self.resources["names"]), 99)
        expected_combinations = {
            "train": [("ABB", "ABB"), ("ABB", "BAB"), ("BAB", "ABB"), ("BAB", "BAB")],
            "test": [("ABB", "BAB"), ("BAB", "ABB")],
        }
        for split, records in self.pairs.items():
            expected = expected_combinations[split]
            self.assertEqual(Counter((pair.base.pattern, pair.source.pattern) for pair in records), Counter({item: 50 for item in expected}))
            self.assertEqual([(records[index * 50].base.pattern, records[index * 50].source.pattern) for index in range(len(expected))], expected)
            for index, pair in enumerate(records):
                self.assertEqual(pair.sample_id, f"{split}-{index:04d}")
                for key, field in (("names", None), ("objects", "obj"), ("places", "place")):
                    values = self.resources[key]
                    allowed = values[:len(values) // 2] if split == "train" else values[len(values) // 2:]
                    actual = pair.base.names if field is None else (getattr(pair.base, field),)
                    self.assertTrue(set(actual).issubset(allowed))
                self.assertIn(pair.base.template_id, range(2) if split == "train" else range(2, len(self.resources["templates"])))
                self.assertEqual(pair.base.template, self.resources["templates"][pair.base.template_id])
                self.assertEqual((pair.source.template_id, pair.source.template, pair.source.obj, pair.source.place), (pair.base.template_id, pair.base.template, pair.base.obj, pair.base.place))
                name_mapping = dict(zip(pair.base.pattern, pair.base.names))
                self.assertEqual(pair.source.names, tuple(name_mapping[symbol] for symbol in pair.source.pattern))

    def test_saved_data_roundtrip_and_corruption_diagnostics(self):
        records = self.pairs["train"][:2]
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.jsonl"
            second = Path(directory) / "second.jsonl"
            write_pairs(first, records)
            write_pairs(second, generate_pairs(UPSTREAM_DIR, seed=42)["train"][:2])
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(load_pairs(first), records)
            corruptions = [
                ("text", lambda record: record["base"].update(text="Changed input")),
                ("span", lambda record: record["base"]["occurrences"][0].update(char_span=[0, 1])),
                ("role", lambda record: record["source"]["occurrences"][0].update(role="S2")),
                ("pattern", lambda record: record["base"].update(pattern="BAB")),
                ("counterfactual", lambda record: record.update(counterfactual_answer="Wrong")),
            ]
            for description, mutate in corruptions:
                with self.subTest(description=description):
                    record = asdict(records[0])
                    mutate(record)
                    first.write_text(json.dumps(record) + "\n", encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, r"first\.jsonl:1: sample 'train-0000'"):
                        load_pairs(first)


if __name__ == "__main__":
    unittest.main()
