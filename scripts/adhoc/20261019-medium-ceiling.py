"""Full-residual patching at N vs saved DAS alignments, scored two ways.

Read-only, fixed weights, validation split only; writes nothing. Usage:
    CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 python -B scripts/adhoc/20261019-medium-ceiling.py medium|small
Scores: full-vocabulary argmax == S (the pipeline's IIA) and logit(S) > logit(IO).
"""
import json, sys
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ioi_das.datasets import load_dataset
from ioi_das.tokenization import load_tokenizers
from ioi_das.intervention import (load_model, prepare_batch, build_intervention,
                                  intervention_forward, factual_forward, cleanup_intervention)

model_key = sys.argv[1]  # medium | small
cfg = json.loads((ROOT / ('outputs/data-scale/20261019-gpt2-medium-rank1-n200/resolved_config.json' if model_key == 'medium'
                          else 'outputs/layer-sweep/20261015-gpt2-small/resolved_config.json')).read_text())
device = torch.device('cuda:0')
torch.set_float32_matmul_precision('highest')
tokenizer, reference = load_tokenizers(cfg['tokenizer'])
m = cfg['model']
model = load_model(m['name'], m['revision'], device)
pairs = load_dataset('val_indist_v1/validation', ROOT).pairs
batches = [prepare_batch(pairs[i:i + 20], tokenizer, reference, device, 'N') for i in range(0, len(pairs), 20)]
the_id = tokenizer.encode(' the')[0]


def score(logit_fn, tag):
    full = names = 0; diffs = []; p_the_top = 0; n = 0
    with torch.no_grad():
        for b in batches:
            lg = logit_fn(b)
            rows = torch.arange(len(b.pairs), device=device)
            s, io = lg[rows, b.counterfactual_labels], lg[rows, b.factual_labels]
            full += (lg.argmax(-1) == b.counterfactual_labels).sum().item()
            names += (s > io).sum().item()
            p_the_top += (lg.argmax(-1) == the_id).sum().item()
            diffs += (s - io).tolist(); n += len(b.pairs)
    diffs.sort()
    print(f'{tag:44s} full-vocab IIA {full / n:.3f} | name-only IIA (S>IO) {names / n:.3f} | '
          f'median logit(S)-logit(IO) {diffs[n // 2]:+.2f} | " the" top-1 {p_the_top / n:.3f}', flush=True)


score(lambda b: factual_forward(model, b), 'no intervention')


def full_patch(layer):
    def fn(b):
        cache = {}
        h = model.transformer.h[layer].register_forward_hook(lambda mod, i, o: cache.__setitem__('src', o[0].detach()))
        model(**b.source_inputs, use_cache=False); h.remove()
        rows = torch.arange(len(b.pairs), device=device)
        src = cache['src'][rows, torch.tensor(b.source_positions, device=device)]
        def patch(mod, i, o):
            hs = o[0].clone(); hs[rows, torch.tensor(b.base_positions, device=device)] = src
            return (hs,) + tuple(o[1:])
        h = model.transformer.h[layer].register_forward_hook(patch)
        try:
            out = model(**b.base_inputs, use_cache=False)
        finally:
            h.remove()
        return out.logits[rows, b.base_readout]
    return fn


layers = range(11, 21) if model_key == 'medium' else range(6, 11)
for L in layers:
    score(full_patch(L), f'full residual patch at N, layer {L}')


def saved(path, layer, rank, tag):
    iv = build_intervention(model, layer, rank)
    ck = torch.load(ROOT / path, map_location=device, weights_only=True)
    for k, i in iv.interventions.items():
        i.load_state_dict(ck['interventions'][k])
    try:
        score(lambda b: intervention_forward(iv, b), tag)
    finally:
        cleanup_intervention(iv)


if model_key == 'medium':
    for run, rank in [('data-scale/20261019-gpt2-medium-rank1-n200', 1), ('data-scale/20261019-gpt2-medium-rank1-n200-updates2500', 1),
                      ('data-scale/20261019-gpt2-medium-rank1-n5000', 1), ('rank-sweep/20261018-gpt2-medium-rank8', 8),
                      ('data-scale/20261019-gpt2-medium-rank8-n1000', 8), ('data-scale/20261019-gpt2-medium-rank8-n5000', 8)]:
        d = f'outputs/{run}/conditions/intervention.layer=14/seed=42'
        if run.endswith('rank1-n200'):
            saved(f'{d}/initial_alignment.pt', 14, rank, 'DAS L14 rank1 UNTRAINED (random init)')
        saved(f'{d}/alignment.pt', 14, rank, f'DAS L14 {run.split("medium-")[1]} s42')
else:
    saved('outputs/layer-sweep/20261015-gpt2-small/conditions/intervention.layer=8/seed=42/alignment.pt', 8, 1, 'DAS L8 rank1 legacy s42')
