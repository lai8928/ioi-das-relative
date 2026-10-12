"""Deterministic original IOI POSITION data, roles, and saved pair records.

Adapted from stanfordnlp/pyvene at commit
9e333904dcf9e597ca76170010d17f4d4580de8d, whose dataset generator credits
https://github.com/amakelov/activation-patching-illusion. Extracted originals
and their license are retained in vendor/pyvene_upstream; see docs/UPSTREAM.md.

The sole sampling compatibility change is replacing ``list(set(pattern))``
with ``list(dict.fromkeys(pattern))``. This preserves uniform distinct-name
sampling while removing process-dependent symbol ordering. A saved dataset is
a new reproducible sample, not a reconstruction of historical tutorial samples.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import random
from string import Formatter
from typing import Iterable


GENERATOR_REVISION = "ioi-position-v1-ordered-symbols"
_PATTERNS = ("ABB", "BAB")
_NAME_FIELDS = ("name_A", "name_B", "name_C")


@dataclass(frozen=True)
class NameOccurrence:
    """A formatted name field and its input role, excluding surrounding spaces.

    ``occurrence`` is the 1-based occurrence of this name among formatted name
    fields; literal template text and object/place text do not define anchors.
    """

    field: str
    name: str
    role: str
    occurrence: int
    char_span: tuple[int, int]


@dataclass(frozen=True)
class PromptRecord:
    """A complete original input and semantic roles, without an appended answer.

    ``io_pos`` and ``s1_pos`` are positions among the first two NAME fields.
    They are not character indices or token indices.
    """

    text: str
    template_id: int
    template: str
    pattern: str
    names: tuple[str, str, str]
    obj: str
    place: str
    io_name: str
    subject_name: str
    io_pos: int
    s1_pos: int
    occurrences: tuple[NameOccurrence, ...]


@dataclass(frozen=True)
class PairRecord:
    """A factual base/source pair and POSITION counterfactual answer names."""

    sample_id: str
    split: str
    base: PromptRecord
    source: PromptRecord
    counterfactual_answer: str
    counterfactual_alternative: str
    target_variable: str = "position"


def build_prompt(
    names: tuple[str, str, str],
    template: str,
    template_id: int,
    pattern: str,
    obj: str,
    place: str,
) -> PromptRecord:
    """Format one IOI prompt while tracking the spans of its name fields.

    Each upstream template contains each of name_A, name_B, and name_C once,
    in that order. Tracking fields during formatting distinguishes S1 from S2
    even if a matching string occurs elsewhere in literal or object text.
    """
    names = tuple(names)
    if pattern not in _PATTERNS:
        raise ValueError(f"Unsupported IOI pattern {pattern!r}; expected ABB or BAB.")
    if len(names) != 3 or any(not isinstance(name, str) or not name for name in names):
        raise ValueError("An IOI prompt requires three nonempty name strings.")
    mapping = {}
    for symbol, name in zip(pattern, names):
        if symbol in mapping and mapping[symbol] != name:
            raise ValueError(f"Names {names!r} do not match pattern {pattern!r}.")
        mapping[symbol] = name
    if len(set(mapping.values())) != 2:
        raise ValueError("The IOI pattern requires two distinct names.")
    if isinstance(template_id, bool) or not isinstance(template_id, int) or template_id < 0:
        raise ValueError("template_id must be a nonnegative integer.")
    if not isinstance(template, str) or not template:
        raise ValueError("template must be a nonempty string.")
    if any(not isinstance(value, str) or not value for value in (obj, place)):
        raise ValueError("object and place must be nonempty strings.")

    subject_name = names[2]
    s1_pos = names[:2].index(subject_name)
    io_pos = 1 - s1_pos
    io_name = names[io_pos]
    values = dict(zip(_NAME_FIELDS, names))
    values.update(object=obj, place=place)
    roles = {io_pos: "IO", s1_pos: "S1", 2: "S2"}
    chunks = []
    occurrences = []
    name_counts: dict[str, int] = {}
    fields_seen = []
    length = 0
    for literal, field, format_spec, conversion in Formatter().parse(template):
        chunks.append(literal)
        length += len(literal)
        if field is None:
            continue
        if field not in values or format_spec or conversion:
            raise ValueError(f"Unsupported template field {field!r}; use original plain IOI fields.")
        value = values[field]
        if field in _NAME_FIELDS:
            fields_seen.append(field)
            index = _NAME_FIELDS.index(field)
            name_counts[value] = name_counts.get(value, 0) + 1
            occurrences.append(NameOccurrence(
                field=field,
                name=value,
                role=roles[index],
                occurrence=name_counts[value],
                char_span=(length, length + len(value)),
            ))
        chunks.append(value)
        length += len(value)
    if tuple(fields_seen) != _NAME_FIELDS:
        raise ValueError("An IOI template must contain name_A, name_B, and name_C once in that order.")
    return PromptRecord(
        text="".join(chunks),
        template_id=template_id,
        template=template,
        pattern=pattern,
        names=names,
        obj=obj,
        place=place,
        io_name=io_name,
        subject_name=subject_name,
        io_pos=io_pos,
        s1_pos=s1_pos,
        occurrences=tuple(occurrences),
    )


def counterfactual_names(base: PromptRecord, source: PromptRecord) -> tuple[str, str]:
    """Apply the source's NAME-order position variable to the base names.

    This is equivalent to upstream's comparison of base/source ``s1_pos``.
    The counterfactual can differ from the source factual answer when the
    source uses different names; it always belongs to the base's two names.
    """
    if source.io_pos not in (0, 1) or base.io_pos not in (0, 1):
        raise ValueError("POSITION counterfactuals require valid first/second NAME roles.")
    return base.names[source.io_pos], base.names[1 - source.io_pos]


def _read_distribution(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        values = json.load(handle)
    if not isinstance(values, list) or not values or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise ValueError(f"{path}: expected a nonempty JSON list of nonempty strings.")
    return values


def generate_pairs(upstream_dir: Path, seed: int = 42) -> dict[str, list[PairRecord]]:
    """Sample the original 200 training and 100 test POSITION pairs.

    One local Python RNG covers training then test, matching upstream random
    draw order. Sources remap their base's A/B names without any random draws;
    their template, object, and place remain those of their base.
    """
    upstream_dir = Path(upstream_dir)
    resource_dir = upstream_dir / "tutorials" / "advanced_tutorials" / "tutorial_data"
    resources = {
        key: _read_distribution(resource_dir / f"{key}.json")
        for key in ("names", "objects", "places", "templates")
    }
    if len(set(resources["names"])) != len(resources["names"]):
        raise ValueError("Upstream names must be distinct to preserve original name sampling.")
    if any(len(resources[key]) < 2 for key in ("names", "objects", "places")):
        raise ValueError("Upstream distributions must support nonempty first/second halves.")
    if len(resources["templates"]) < 3:
        raise ValueError("At least three templates are required for the original split.")
    rng = random.Random(seed)
    pairs: dict[str, list[PairRecord]] = {"train": [], "test": []}
    for split in ("train", "test"):
        distributions = {}
        for key in ("names", "objects", "places"):
            midpoint = len(resources[key]) // 2
            distributions[key] = resources[key][:midpoint] if split == "train" else resources[key][midpoint:]
        if len(distributions["names"]) < 2:
            raise ValueError(f"The {split} split needs at least two distinct names.")
        template_ids = list(range(2)) if split == "train" else list(range(2, len(resources["templates"])))
        combinations = (
            [(base, source) for base in _PATTERNS for source in _PATTERNS]
            if split == "train" else [("ABB", "BAB"), ("BAB", "ABB")]
        )
        for base_pattern, source_pattern in combinations:
            # Upstream samples each 50-base block before deriving its sources.
            bases = []
            for _ in range(50):
                template_id = rng.choice(template_ids)
                symbols = list(dict.fromkeys(base_pattern))
                sampled_names = rng.sample(distributions["names"], len(symbols))
                symbol_names = dict(zip(symbols, sampled_names))
                names = tuple(symbol_names[symbol] for symbol in base_pattern)
                obj = rng.choice(distributions["objects"])
                place = rng.choice(distributions["places"])
                bases.append(build_prompt(
                    names=names,
                    template=resources["templates"][template_id],
                    template_id=template_id,
                    pattern=base_pattern,
                    obj=obj,
                    place=place,
                ))
            for base in bases:
                name_mapping = dict(zip(base_pattern, base.names))
                source = build_prompt(
                    names=tuple(name_mapping[symbol] for symbol in source_pattern),
                    template=base.template,
                    template_id=base.template_id,
                    pattern=source_pattern,
                    obj=base.obj,
                    place=base.place,
                )
                answer, alternative = counterfactual_names(base, source)
                pairs[split].append(PairRecord(
                    sample_id=f"{split}-{len(pairs[split]):04d}",
                    split=split,
                    base=base,
                    source=source,
                    counterfactual_answer=answer,
                    counterfactual_alternative=alternative,
                ))
    return pairs


def _validate_pair(pair: PairRecord) -> None:
    if not isinstance(pair.sample_id, str) or not pair.sample_id:
        raise ValueError("sample_id must be a nonempty string.")
    if pair.split not in ("train", "test"):
        raise ValueError("split must be train or test.")
    if pair.target_variable != "position":
        raise ValueError("The Phase 1 dataset supports only target_variable='position'.")
    for side in ("base", "source"):
        prompt = getattr(pair, side)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (prompt.io_pos, prompt.s1_pos)):
            raise ValueError(f"{side} NAME-order positions must be integers.")
        for occurrence in prompt.occurrences:
            if isinstance(occurrence.occurrence, bool) or not isinstance(occurrence.occurrence, int):
                raise ValueError(f"{side} name occurrence numbers must be integers.")
            if len(occurrence.char_span) != 2 or any(
                isinstance(value, bool) or not isinstance(value, int) for value in occurrence.char_span
            ):
                raise ValueError(f"{side} name character spans must contain two integer offsets.")
        expected = build_prompt(
            names=prompt.names,
            template=prompt.template,
            template_id=prompt.template_id,
            pattern=prompt.pattern,
            obj=prompt.obj,
            place=prompt.place,
        )
        if prompt != expected:
            raise ValueError(f"{side} text, name spans, or role metadata does not match its template and names.")
    if (pair.counterfactual_answer, pair.counterfactual_alternative) != counterfactual_names(pair.base, pair.source):
        raise ValueError("Counterfactual metadata does not apply the source POSITION variable to the base names.")


def write_pairs(path: Path, pairs: Iterable[PairRecord]) -> None:
    """Write validated pair records as deterministic UTF-8 JSONL."""
    path = Path(path)
    records = list(pairs)
    identifiers = set()
    for pair in records:
        _validate_pair(pair)
        if pair.sample_id in identifiers:
            raise ValueError(f"Duplicate sample_id {pair.sample_id!r}.")
        identifiers.add(pair.sample_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for pair in records:
            handle.write(json.dumps(asdict(pair), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _prompt_from_dict(record: dict) -> PromptRecord:
    record = dict(record)
    record["names"] = tuple(record["names"])
    occurrences = []
    for occurrence in record["occurrences"]:
        occurrence = dict(occurrence)
        occurrence["char_span"] = tuple(occurrence["char_span"])
        occurrences.append(NameOccurrence(**occurrence))
    record["occurrences"] = tuple(occurrences)
    return PromptRecord(**record)


def load_pairs(path: Path) -> list[PairRecord]:
    """Load saved pairs, rejecting corruption with file/line/sample diagnostics."""
    path = Path(path)
    pairs = []
    identifiers = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            sample_id = "unknown"
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("Each JSONL record must be an object.")
                sample_id = record.get("sample_id", "unknown")
                record["base"] = _prompt_from_dict(record["base"])
                record["source"] = _prompt_from_dict(record["source"])
                pair = PairRecord(**record)
                _validate_pair(pair)
                if pair.sample_id in identifiers:
                    raise ValueError(f"Duplicate sample_id {pair.sample_id!r}.")
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                raise ValueError(f"{path}:{line_number}: sample {sample_id!r}: {error}") from error
            identifiers.add(pair.sample_id)
            pairs.append(pair)
    return pairs


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of the exact file bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
