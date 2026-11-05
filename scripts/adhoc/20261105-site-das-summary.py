"""Summarize the step-2 intervention-sites runs next to the step-0 full-patch counts.

Reads saved outputs only (no model). Usage:
    python -B scripts/adhoc/20261105-site-das-summary.py [FULL_PATCH_CSV]
FULL_PATCH_CSV is the --csv table of scripts/adhoc/20261105-full-patch-map.py;
without it the full-patch column is left empty. Counts are means over seeds.
"""
import csv, json, sys
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'outputs/intervention-sites'
SHORT = {'head_attention_value_output': 'Z', 'head_query_output': 'Q',
         'head_key_output': 'K', 'head_value_output': 'V'}
full = {}
if len(sys.argv) > 1:
    for row in csv.DictReader(open(sys.argv[1])):
        full[(row['component'], row['layer'], row['head'])] = int(row['iia_correct'])


def rows(run):
    """Return one record per condition with validation, untrained, test, and train fit."""
    meta = json.loads((run / 'run.json').read_text())
    post = {record['condition_path']: record for record in meta.get('post_lock', [])}
    records = []
    for condition in meta['conditions']:
        result = json.loads((run / condition['path'] / 'result.json').read_text())
        metrics = result['metrics']
        test_path = run / post[condition['path']]['path'] / 'result.json' if condition['path'] in post else None
        test = json.loads(test_path.read_text())['metrics']['test'] if test_path and test_path.is_file() else None
        records.append({'layer': result['condition']['layer'], 'seed': result['seed'],
                        'val': metrics['validation']['iia_correct'],
                        'untrained': metrics['initial_validation']['iia_correct'],
                        'test': test['iia_correct'] if test else None,
                        'train_switch': metrics['train']['groups']['switch_required']['iia']})
    return meta, records


def fmt(values, scale=1):
    values = [v * scale for v in values if v is not None]
    if not values:
        return '-'
    return f'{mean(values):.1f}' + (f' ± {stdev(values):.1f}' if len(values) > 1 else '')


for run in sorted(RUNS.glob('2026*-gpt2-small-*-output')):
    meta, records = rows(run)
    component = meta['resolved_config']['intervention']['component']
    selected = json.loads((run / 'selection.json').read_text())['selected_layer']
    print(f'\n{component} ({run.name}); selected layer {selected}; counts out of 200 (test out of 100)')
    print('layer | DAS val | untrained val | full patch val | test | train switch-required (%)')
    for layer in sorted({r['layer'] for r in records}):
        cell = [r for r in records if r['layer'] == layer]
        print(f"{layer:5d} | {fmt([r['val'] for r in cell])} | {fmt([r['untrained'] for r in cell])} | "
              f"{full.get((component, str(layer), ''), '-')} | {fmt([r['test'] for r in cell])} | "
              f"{fmt([r['train_switch'] for r in cell], 100)}")

print('\nHeads; counts out of 200 (test out of 100), mean ± seed SD')
print('head | site | location | DAS val | untrained val | full patch val | test | train switch-required (%)')
for run in sorted(RUNS.glob('2026*-gpt2-small-l*h*-*')):
    meta, records = rows(run)
    intervention = meta['resolved_config']['intervention']
    key = (intervention['component'], str(intervention['layer']), str(intervention['head']))
    print(f"{intervention['layer']}.{intervention['head']} | {SHORT[intervention['component']]} | "
          f"{intervention['location']} | {fmt([r['val'] for r in records])} | "
          f"{fmt([r['untrained'] for r in records])} | {full.get(key, '-')} | "
          f"{fmt([r['test'] for r in records])} | {fmt([r['train_switch'] for r in records], 100)}")
