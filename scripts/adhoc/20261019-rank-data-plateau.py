"""Why GPT-2 Medium layer-14 IIA barely moves with rank or training size.

Reads saved outputs only (no model). Usage:
    python -B scripts/adhoc/20261019-rank-data-plateau.py
Prints: loss plateau per run, learned-subspace overlaps, train vs validation
switch-required IIA, and the validation outcome breakdown.
"""
import collections
import glob
import json
import statistics as st
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / 'outputs/data-scale'
RS = ROOT / 'outputs/rank-sweep'


def jsonl(path):
    return [json.loads(line) for line in open(path)]


def seeds(run, layer=14):
    return sorted(glob.glob(str(run / f'conditions/intervention.layer={layer}/seed=*')))


def projection(path):
    from pyvene.models.layers import LowRankRotateLayer
    state = next(iter(torch.load(path, map_location='cpu', weights_only=False)['interventions'].values()))
    n, m = state['rotate_layer.parametrizations.weight.original'].shape
    layer = torch.nn.utils.parametrizations.orthogonal(LowRankRotateLayer(n, m))
    layer.load_state_dict({k.removeprefix('rotate_layer.'): v for k, v in state.items() if k.startswith('rotate_layer.')})
    return layer.weight.detach()


def cosines(a, b):
    return torch.linalg.svdvals(torch.linalg.qr(a)[0].T @ torch.linalg.qr(b)[0]).tolist()


runs = [p for p in sorted(DS.glob('20261019-gpt2-medium-rank*'))
        if json.load(open(p / 'run.json'))['status'] == 'complete']

print('Loss plateau at layer 14 (mean of seeds, mean loss over the last 10% of updates)')
for run in runs:
    tails, train_sw, val = [], [], []
    for sd in seeds(run):
        loss = [r['loss'] for r in jsonl(f'{sd}/training_steps.jsonl')]
        tails.append(st.mean(loss[-max(1, len(loss) // 10):]))
        sw = [r for r in jsonl(f'{sd}/train_predictions.jsonl') if r['switch_required']]
        train_sw.append(sum(r['counterfactual_correct'] for r in sw) / len(sw))
        vs = jsonl(f'{sd}/validation_predictions.jsonl')
        val.append(sum(r['counterfactual_correct'] for r in vs) / len(vs))
    print(f'  {run.name:48s} updates {len(loss):5d}  loss {st.mean(tails):.3f}  '
          f'train switch-required {st.mean(train_sw):.3f}  validation {st.mean(val):.3f}')

print('\nSubspace overlap at layer 14, seed 42 (cosines of principal angles)')
P = {}
for run in runs:
    sd = seeds(run)[0]
    P[run.name] = (projection(f'{sd}/initial_alignment.pt'), projection(f'{sd}/alignment.pt'))
for name, (init, final) in P.items():
    print(f'  {name:48s} initial vs trained {[round(c, 3) for c in cosines(init, final)]}')
rank1 = {k: v[1] for k, v in P.items() if '-rank1-' in k}
for name, (_, final) in P.items():
    ref = rank1.get(name.replace(name.split('-')[3], 'rank1')) if final.shape[1] > 1 else None
    if ref is not None:
        print(f'  {name:48s} rank-1 direction inside this subspace: {torch.linalg.norm(torch.linalg.qr(final)[0].T @ ref[:, 0]).item():.3f}')
names = sorted(rank1)
for a in names:
    print(f'  |cos| {a:44s}', [round(abs(torch.dot(rank1[a][:, 0], rank1[b][:, 0]).item()), 3) for b in names])

print('\nValidation outcomes at layer 14, pooled over every complete run and seed')
paths = [f'{sd}/validation_predictions.jsonl' for run in runs + sorted(RS.glob('20261018-gpt2-medium-rank*')) for sd in seeds(run)]
outcomes, wins = collections.Counter(), collections.Counter()
for path in paths:
    for r in jsonl(path):
        if r['counterfactual_correct']:
            outcomes['S top-1 (success)'] += 1
            wins[r['sample_id']] += 1
        elif r['counterfactual_prediction']['token_id'] == r['factual_target_token_id']:
            outcomes['IO still top-1'] += 1
        else:
            outcomes['another token top-1'] += 1
total = sum(outcomes.values())
for key, count in outcomes.most_common():
    print(f'  {key:22s} {count / total:.3f}')
reference = jsonl(paths[0])
never = [r for r in reference if wins[r['sample_id']] == 0]
always = [r for r in reference if wins[r['sample_id']] == len(paths)]
print(f'  conditions {len(paths)}; examples never flipped {len(never)}, always flipped {len(always)} of {len(reference)}')
for label, rows in (('all', reference), ('never', never), ('always', always)):
    print(f'  {label:6s} factual top-1 accuracy {sum(r["factual_correct"] for r in rows) / len(rows):.2f}')

print('\nBy object ("gave a <object> to"), same pooled layer-14 conditions')
by_object = collections.defaultdict(collections.Counter)
for path in paths:
    for r in jsonl(path):
        counts = by_object[r['base_text'].split('gave a ')[1].split(' ')[0]]
        counts['total'] += 1
        counts['success'] += r['counterfactual_correct']
        counts['the'] += r['counterfactual_prediction']['continuation'] == ' the'
for name, counts in sorted(by_object.items()):
    factual_the = sum(r['factual_prediction']['continuation'] == ' the' for r in reference
                      if f'gave a {name} ' in r['base_text'])
    size = sum(f'gave a {name} ' in r['base_text'] for r in reference)
    print(f'  {name:10s} IIA {counts["success"] / counts["total"]:.2f}  " the" top-1 after DAS '
          f'{counts["the"] / counts["total"]:.2f}  " the" without intervention {factual_the}/{size}')
