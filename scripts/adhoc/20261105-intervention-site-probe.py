"""Can pyvene 0.1.8 intervene on attention_output, mlp_output, mlp_activation, and one head?

Read-only, fixed weights, CPU, GPT-2 Small layer 8 (head 6), first 8 validation
pairs; writes nothing. Usage:
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -B scripts/adhoc/20261105-intervention-site-probe.py
Per site it compares VanillaIntervention with a manual forward-hook patch at N,
checks rank-1 identity (base as source) and alignment gradients, and compares a
full-rank rotation with the manual patch. Result on 2026-11-05: every site
matches the manual patch exactly (max |diff| 0); identity is bit-identical;
gradients are nonzero; rotation sizes 768 / 768 / 3072 / 64; full rank differs
from the exact patch by up to 6e-5.
"""
import json, sys
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from pyvene import IntervenableConfig, RepresentationConfig, LowRankRotatedSpaceIntervention, VanillaIntervention
from ioi_das.datasets import load_dataset
from ioi_das.tokenization import load_tokenizers
from ioi_das.intervention import ScopedIntervenableModel, load_model, prepare_batch, factual_forward

torch.manual_seed(0)
torch.set_float32_matmul_precision('highest')
cfg = json.loads((ROOT / 'outputs/layer-sweep/20261015-gpt2-small/resolved_config.json').read_text())
device = torch.device('cpu')
tokenizer, reference = load_tokenizers(cfg['tokenizer'])
model = load_model(cfg['model']['name'], cfg['model']['revision'], device)
pairs = load_dataset('val_indist_v1/validation', ROOT).pairs[:8]
batch = prepare_batch(pairs, tokenizer, reference, device, 'N')
B = len(pairs)
rows = torch.arange(B)
LAYER, HEAD, HD = 8, 6, 64


def build(component, unit, intervention_type, rank=None):
    rep = dict(layer=LAYER, component=component, unit=unit, max_number_of_units=1)
    if rank is not None:
        rep['low_rank_dimension'] = rank
    config = IntervenableConfig(representations=[RepresentationConfig(**rep)],
                                intervention_types=intervention_type, mode='parallel')
    model_ = ScopedIntervenableModel(config, model)
    model_.set_device(device, set_model=False)
    model_.disable_model_gradients()
    return model_


def locations(unit, source_inputs_positions, base_positions):
    if unit == 'pos':
        return {'sources->base': ([[[p] for p in source_inputs_positions]], [[[p] for p in base_positions]])}
    heads = [[HEAD]] * B
    return {'sources->base': ([[heads, [[p] for p in source_inputs_positions]]],
                              [[heads, [[p] for p in base_positions]]])}


def run(intervenable, unit, source_inputs, source_positions):
    try:
        _, out = intervenable(batch.base_inputs, [source_inputs],
                              unit_locations=locations(unit, source_positions, batch.base_positions),
                              output_original_output=False, use_cache=False)
        return out.logits[rows, batch.base_readout]
    finally:
        intervenable._cleanup_states()
        intervenable.full_intervention_outputs.clear()


def manual(module, hook_kind, select, replace):
    """Run source, cache the module's activation, then patch it into base at N."""
    cache = {}
    if hook_kind == 'pre':
        h = module.register_forward_pre_hook(lambda m, a: cache.__setitem__('x', a[0].detach().clone()))
    else:
        h = module.register_forward_hook(lambda m, a, o: cache.__setitem__('x', (o[0] if isinstance(o, tuple) else o).detach().clone()))
    with torch.no_grad():
        model(**batch.source_inputs, use_cache=False)
    h.remove()
    src = select(cache['x'], batch.source_positions)
    if hook_kind == 'pre':
        def patch(m, a):
            x = a[0].clone(); replace(x, batch.base_positions, src); return (x,) + tuple(a[1:])
        h = module.register_forward_pre_hook(patch)
    else:
        def patch(m, a, o):
            x = (o[0] if isinstance(o, tuple) else o).clone(); replace(x, batch.base_positions, src)
            return (x,) + tuple(o[1:]) if isinstance(o, tuple) else x
        h = module.register_forward_hook(patch)
    with torch.no_grad():
        out = model(**batch.base_inputs, use_cache=False).logits[rows, batch.base_readout]
    h.remove()
    return out


def pos_select(x, positions):
    return x[rows, torch.tensor(positions)]


def pos_replace(x, positions, src):
    x[rows, torch.tensor(positions)] = src


def head_select(x, positions):
    return x[rows, torch.tensor(positions), HEAD * HD:(HEAD + 1) * HD]


def head_replace(x, positions, src):
    x[rows, torch.tensor(positions), HEAD * HD:(HEAD + 1) * HD] = src


block = model.transformer.h[LAYER]
sites = {
    'attention_output': ('pos', block.attn.resid_dropout, 'post', pos_select, pos_replace, 768),
    'mlp_output': ('pos', block.mlp, 'post', pos_select, pos_replace, 768),
    'mlp_activation': ('pos', block.mlp.act, 'post', pos_select, pos_replace, 3072),
    'head_attention_value_output': ('h.pos', block.attn.c_proj, 'pre', head_select, head_replace, 64),
}
factual = factual_forward(model, batch).detach()
for component, (unit, module, kind, select, replace, dim) in sites.items():
    expected = manual(module, kind, select, replace)
    vanilla = build(component, unit, VanillaIntervention)
    with torch.no_grad():
        got = run(vanilla, unit, batch.source_inputs, batch.source_positions)
    vanilla_diff = (got - expected).abs().max().item()
    low = build(component, unit, LowRankRotatedSpaceIntervention, rank=1)
    embed = next(iter(low.interventions.values())).embed_dim
    with torch.no_grad():
        ident = run(low, unit, batch.base_inputs, list(batch.base_positions))
    identity_equal = torch.equal(ident, factual)
    logits = run(low, unit, batch.source_inputs, batch.source_positions)
    torch.nn.functional.cross_entropy(logits, batch.counterfactual_labels).backward()
    grad = next(iter(low.interventions.values())).rotate_layer.parametrizations.weight.original.grad
    full = build(component, unit, LowRankRotatedSpaceIntervention, rank=dim)
    with torch.no_grad():
        full_got = run(full, unit, batch.source_inputs, batch.source_positions)
    state = next(iter(full.interventions.values())).state_dict()
    print(f'{component:28s} embed_dim={embed} | vanilla vs manual max|diff|={vanilla_diff:.2e} | '
          f'rank-1 identity bit-equal={identity_equal} | rank-1 grad norm={grad.norm().item():.3e} | '
          f'full-rank vs manual max|diff|={(full_got - expected).abs().max().item():.2e} | '
          f'IIA manual {int((expected.argmax(-1) == batch.counterfactual_labels).sum())}/{B} | '
          f'state shapes {[tuple(v.shape) for v in state.values() if v.dim() > 0]}', flush=True)
    for m in (vanilla, low, full):
        m._remove_forward_hooks()
