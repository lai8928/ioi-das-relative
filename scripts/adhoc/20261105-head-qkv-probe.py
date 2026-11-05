"""Do pyvene 0.1.8 single-head Q, K, V interventions act where they should?

Read-only, fixed weights, CPU, GPT-2 Small layer 8 head 6, first 8 validation
pairs; Q at N, K and V at S2; writes nothing. Usage:
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -B scripts/adhoc/20261105-head-qkv-probe.py
Per site it compares VanillaIntervention with a manual patch of the c_attn output,
checks rank-1 identity (base as source), DAS and GPT-2 gradients, and the layer's
attention probabilities. Result on 2026-11-05 (transformers 4.57.6): all three
match the manual patch exactly; identity is bit-identical; DAS gradients are
nonzero and no GPT-2 parameter gets a gradient; Q changes only head 6's row at N,
K changes only head 6, V leaves every attention probability unchanged.
"""
import json, sys
from pathlib import Path
import torch
import transformers

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from pyvene import IntervenableConfig, RepresentationConfig, LowRankRotatedSpaceIntervention, VanillaIntervention
from ioi_das.datasets import load_dataset
from ioi_das.tokenization import load_tokenizers
from ioi_das.intervention import ScopedIntervenableModel, load_model, prepare_batch, factual_forward

print('transformers', transformers.__version__)
torch.manual_seed(0)
torch.set_float32_matmul_precision('highest')
cfg = json.loads((ROOT / 'outputs/layer-sweep/20261015-gpt2-small/resolved_config.json').read_text())
device = torch.device('cpu')
tokenizer, reference = load_tokenizers(cfg['tokenizer'])
model = load_model(cfg['model']['name'], cfg['model']['revision'], device)
pairs = load_dataset('val_indist_v1/validation', ROOT).pairs[:8]
B = len(pairs)
rows = torch.arange(B)
LAYER, HEAD, HD, D = 8, 6, 64, 768
attn = model.transformer.h[LAYER].attn
PART = {'head_query_output': 0, 'head_key_output': 1, 'head_value_output': 2}


def build(component, intervention_type, rank=None):
    rep = dict(layer=LAYER, component=component, unit='h.pos', max_number_of_units=1)
    if rank is not None:
        rep['low_rank_dimension'] = rank
    wrapped = ScopedIntervenableModel(IntervenableConfig(representations=[RepresentationConfig(**rep)],
                                                         intervention_types=intervention_type, mode='parallel'), model)
    wrapped.set_device(device, set_model=False)
    wrapped.disable_model_gradients()
    return wrapped


def run(wrapped, batch, source_inputs, source_positions, probs=None):
    heads = [[HEAD]] * B
    locations = {'sources->base': ([[heads, [[p] for p in source_positions]]],
                                   [[heads, [[p] for p in batch.base_positions]]])}
    handle = attn.attn_dropout.register_forward_hook(lambda m, a, o: probs.append(o.detach().clone())) if probs is not None else None
    try:
        _, out = wrapped(batch.base_inputs, [source_inputs], unit_locations=locations,
                         output_original_output=False, use_cache=False)
        return out.logits[rows, batch.base_readout]
    finally:
        if handle is not None:
            handle.remove()
        wrapped._cleanup_states()
        wrapped.full_intervention_outputs.clear()


def columns(component):
    start = PART[component] * D + HEAD * HD
    return slice(start, start + HD)


def manual(batch, component):
    cache = {}
    h = attn.c_attn.register_forward_hook(lambda m, a, o: cache.__setitem__('x', o.detach().clone()))
    with torch.no_grad():
        model(**batch.source_inputs, use_cache=False)
    h.remove()
    src = cache['x'][rows, torch.tensor(batch.source_positions), columns(component)]

    def patch(m, a, o):
        o = o.clone()
        o[rows, torch.tensor(batch.base_positions), columns(component)] = src
        return o
    h = attn.c_attn.register_forward_hook(patch)
    with torch.no_grad():
        out = model(**batch.base_inputs, use_cache=False).logits[rows, batch.base_readout]
    h.remove()
    return out


def base_probs(batch):
    probs = []
    h = attn.attn_dropout.register_forward_hook(lambda m, a, o: probs.append(o.detach().clone()))
    with torch.no_grad():
        model(**batch.base_inputs, use_cache=False)
    h.remove()
    return probs[-1]


for component, location in (('head_query_output', 'N'), ('head_key_output', 'S2'), ('head_value_output', 'S2')):
    batch = prepare_batch(pairs, tokenizer, reference, device, location)
    differs = [b != s for b, s in zip(batch.base_positions, batch.source_positions)]
    expected = manual(batch, component)
    vanilla = build(component, VanillaIntervention)
    probs = []
    with torch.no_grad():
        got = run(vanilla, batch, batch.source_inputs, batch.source_positions, probs)
    patched_probs, original = probs[-1], base_probs(batch)
    delta = (patched_probs - original).abs()
    other_heads = torch.cat([delta[:, :HEAD], delta[:, HEAD + 1:]], dim=1).max().item()
    this_head = delta[:, HEAD].max().item()
    if component == 'head_query_output':
        mask = torch.ones_like(delta[:, HEAD], dtype=torch.bool)
        mask[rows, torch.tensor(batch.base_positions)] = False  # only each base's N row may change
        outside = delta[:, HEAD][mask].max().item()
        where = 'outside the N row'
    elif component == 'head_key_output':
        mask = torch.ones_like(delta[:, HEAD], dtype=torch.bool)
        mask[rows, :, torch.tensor(batch.base_positions)] = False  # only the S2 column may change before renormalization
        outside = None
        where = ''
    else:
        outside = None
        where = ''
    low = build(component, LowRankRotatedSpaceIntervention, rank=1)
    embed = next(iter(low.interventions.values())).embed_dim
    with torch.no_grad():
        ident = run(low, batch, batch.base_inputs, list(batch.base_positions))
    logits = run(low, batch, batch.source_inputs, batch.source_positions)
    torch.nn.functional.cross_entropy(logits, batch.counterfactual_labels).backward()
    grad = next(iter(low.interventions.values())).rotate_layer.parametrizations.weight.original.grad
    model_grads = [p.grad for p in model.parameters() if p.grad is not None]
    print(f'{component} at {location} (base != source index in {sum(differs)}/{B}): embed_dim={embed} | '
          f'vanilla vs manual max|diff|={(got - expected).abs().max().item():.2e} | '
          f'rank-1 identity bit-equal={torch.equal(ident, factual_forward(model, batch))} | '
          f'grad norm={grad.norm().item():.3e} | GPT-2 grads={len(model_grads)} | '
          f'attention change: head {HEAD} max {this_head:.2e}, other heads max {other_heads:.2e}'
          + (f', head {HEAD} {where} max {outside:.2e}' if outside is not None else '')
          + f' | logits changed by patch: {not torch.equal(got, factual_forward(model, batch))}', flush=True)
    for m in (vanilla, low):
        m._remove_forward_hooks()
