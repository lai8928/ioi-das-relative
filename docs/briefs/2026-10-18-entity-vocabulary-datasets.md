# Brief: Object nouns in place of person names

- Branch: `feat/entity-vocabulary-datasets`
- Task: `object-names`
- Status: open — blocked on the decisions below; do not start until they
  are filled in
- Written: 2026-10-18, from [meeting 2026-10-15](../meetings/2026-10-15.md)
- Depends on: none

## Goal

Build IOI POSITION datasets in which the two person names are replaced by
two inanimate object nouns. Each object pair is matched one-to-one to a pair
in an existing name dataset, so template, template object, place, patterns,
and pairing are identical and only the entity words differ. Names and
objects can then be compared on the same examples.

## Decisions needed

Open items from the [2026-10-15 meeting](../meetings/2026-10-15.md)
(Undecided). Claude Code fills this section in once the user decides.

1. Vocabulary. Proposed: 40 inanimate nouns, each a single GPT-2 token in
   lowercase with a leading space (checked 2026-10-18). Excluded: nouns that
   can name a person (fan), verbs (watch, table), and every template object
   and place.
   - First half (train and validation): ball, shoe, cup, book, chair, lamp,
     box, hat, key, pen, bag, clock, bottle, plate, spoon, coin, bell,
     brush, phone, desk.
   - Second half (test): bowl, fork, knife, shirt, coat, wheel, drum, mirror,
     candle, stone, jar, bucket, hammer, button, wallet, belt, bench,
     helmet, jacket, mug.
2. Determiner.
   - (a) `the`: "Then, the ball and the shoe went to the store. The shoe
     gave a drink to the" → answer " ball". Grammatical, and the noun token
     is identical at every occurrence. But the prompt gains tokens, and the
     last token N becomes " the" instead of " to". This matters when a
     name-trained alignment is applied at N.
   - (b) bare, all lowercase: "Then, ball and shoe went to the store. shoe
     gave a drink to" → answer " ball". Every non-entity token and N stay
     identical to the name prompt, but the text is ungrammatical.
     Sentence-initial capitals must not be used: " Shoe" is two tokens and
     a different token from " shoe", which would break the repeated-subject
     signal.
   - (c) build both and report both.
3. Matched sources. Proposed: `val_indist_v1/validation`,
   `legacy_v1/train`, and `legacy_v1/test`.

## Context

- PLAN: [object-names](../PLAN.md). PROTOCOL: Data (spans tracked during
  construction; no truncation or answer appending; single-token answers;
  registered, immutable datasets).
- Names come from the upstream `names.json`, split into halves at
  `len // 2` (first half for the train source split, second half for test).
  `data.build_prompt` tracks the character span of each name field. Anchors
  (IO, S1, S2) are the last token of a span.
- Template objects: ring, kiss, bone, basketball, computer, necklace, drink,
  snack. Places: store, garden, restaurant, school, hospital, office,
  house, station.
- Dataset recipes are validated by `configs/datasets/schema.json`. The
  existing generators are `original_position` and `registered_subset`.
- A recorded change to the data rules needs a PROTOCOL change-log entry
  citing D2 of the 2026-10-15 meeting. Claude Code adds it with the
  decisions.

## Scope

- Vocabulary file `data/vocabularies/objects_v1.json`, listed in two halves.
  Its SHA-256 is recorded in every manifest built from it.
- New recipe generator `entity_substitution`. It takes:
  - a source dataset reference;
  - the vocabulary file;
  - the determiner mode;
  - a seed.
- Per pair, map the two names to two distinct nouns from the half matching
  the source split: train and validation use the first half, test the
  second. Apply the same mapping to base, source, and both counterfactual
  names. Save the source `sample_id` and the name→noun map in each record.
- Build prompts from templates so that:
  - entity spans cover only the noun;
  - in `the` mode, the determiner is capitalized only at sentence start and
    the prompt ends with " the";
  - no answer is ever appended.
- Recipes `configs/datasets/<name>.json` for each decided mode and source,
  built, audited, and registered in `data/registry.json`.

## Out of scope

- Evaluating or training on the new data (see
  [alignment-transfer-eval](2026-10-18-alignment-transfer-eval.md) and
  ordinary run configs).
- Changing name datasets or the original generator.
- Other entity categories (animals, places).

## Acceptance

1. `$PY -B -m pytest -q` passes, including the byte-identical `legacy_v1`
   regeneration.
2. Every new dataset passes `ioi-das data audit` with 0 unsupported answers.
3. Matching check for every pair:
   - reversing the noun map reproduces the source pair's text (bare mode),
     or does so after removing the determiner edits (`the` mode);
   - patterns, templates, objects, places, and counterfactual roles are
     unchanged.
4. Train or validation and test use disjoint vocabulary halves. No prompt
   text overlaps across splits.
