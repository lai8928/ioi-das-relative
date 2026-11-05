"""Full-vector patch map for GPT-2 Small: branch outputs per layer and every head's Z, Q, K, V.

Read-only, fixed weights, no training, validation split (val_indist_v1) only. Usage:
    CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -B scripts/adhoc/20261105-full-patch-map.py [--csv PATH]
At each site the whole activation (for a head site, that head's 64 dimensions) at
the token location is replaced with the source's (pyvene VanillaIntervention):
block_output, attention_output, mlp_output, Z (head output before W_O), and Q at N;
K and V at S2. Base and source positions are resolved separately; readout at base N.
Scores: full-vocabulary argmax == counterfactual answer (the pipeline's IIA),
logit(S) > logit(IO) (names only), and IO still top-1.
"""
import argparse, csv, json, sys
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from pyvene import IntervenableConfig, RepresentationConfig, VanillaIntervention
from ioi_das.datasets import load_dataset
from ioi_das.tokenization import load_tokenizers
from ioi_das.intervention import ScopedIntervenableModel, load_model, prepare_batch, factual_forward

parser = argparse.ArgumentParser()
parser.add_argument('--csv', type=Path, help='optional path for the full per-site table')
args = parser.parse_args()
cfg = json.loads((ROOT / 'outputs/layer-sweep/20261015-gpt2-small/resolved_config.json').read_text())
device = torch.device('cuda:0')
torch.set_float32_matmul_precision('highest')
tokenizer, reference = load_tokenizers(cfg['tokenizer'])
model = load_model(cfg['model']['name'], cfg['model']['revision'], device)
pairs = load_dataset('val_indist_v1/validation', ROOT).pairs
batches = {location: [prepare_batch(pairs[i:i + 20], tokenizer, reference, device, location)
                      for i in range(0, len(pairs), 20)] for location in ('N', 'S2')}
LAYERS, HEADS = model.config.n_layer, model.config.n_head
HEAD_SITES = (('Z', 'head_attention_value_output', 'N'), ('Q', 'head_query_output', 'N'),
              ('K', 'head_key_output', 'S2'), ('V', 'head_value_output', 'S2'))


def counts(logit_fn, location):
    full = names = io_top = 0
    with torch.no_grad():
        for batch in batches[location]:
            logits = logit_fn(batch)
            rows = torch.arange(len(batch.pairs), device=device)
            top = logits.argmax(-1)
            full += (top == batch.counterfactual_labels).sum().item()
            names += (logits[rows, batch.counterfactual_labels] > logits[rows, batch.factual_labels]).sum().item()
            io_top += (top == batch.factual_labels).sum().item()
    return full, names, io_top


def patch(component, layer, head, location):
    unit = 'pos' if head is None else 'h.pos'
    wrapped = ScopedIntervenableModel(IntervenableConfig(
        representations=[RepresentationConfig(layer=layer, component=component, unit=unit, max_number_of_units=1)],
        intervention_types=VanillaIntervention, mode='parallel'), model)
    wrapped.set_device(device, set_model=False)
    wrapped.disable_model_gradients()

    def logit_fn(batch):
        if head is None:
            source_units, base_units = [[[p] for p in batch.source_positions]], [[[p] for p in batch.base_positions]]
        else:
            heads = [[head]] * len(batch.pairs)
            source_units = [[heads, [[p] for p in batch.source_positions]]]
            base_units = [[heads, [[p] for p in batch.base_positions]]]
        try:
            _, out = wrapped(batch.base_inputs, [batch.source_inputs], unit_locations={'sources->base': (source_units, base_units)},
                             output_original_output=False, use_cache=False)
        finally:
            wrapped._cleanup_states()
            wrapped.full_intervention_outputs.clear()
        return out.logits[torch.arange(len(batch.pairs), device=device), batch.base_readout]
    try:
        return counts(logit_fn, location)
    finally:
        wrapped._remove_forward_hooks()


rows = []
total = len(pairs)
baseline = counts(lambda batch: factual_forward(model, batch), 'N')
rows.append({'site': 'none', 'component': 'none', 'layer': '', 'head': '', 'location': 'N',
             'iia_correct': baseline[0], 'names_only_correct': baseline[1], 'io_top1': baseline[2], 'total': total})
for layer in range(LAYERS):
    for component in ('block_output', 'attention_output', 'mlp_output'):
        full, names, io_top = patch(component, layer, None, 'N')
        rows.append({'site': component, 'component': component, 'layer': layer, 'head': '', 'location': 'N',
                     'iia_correct': full, 'names_only_correct': names, 'io_top1': io_top, 'total': total})
    for head in range(HEADS):
        for site, component, location in HEAD_SITES:
            full, names, io_top = patch(component, layer, head, location)
            rows.append({'site': site, 'component': component, 'layer': layer, 'head': head, 'location': location,
                         'iia_correct': full, 'names_only_correct': names, 'io_top1': io_top, 'total': total})
    print(f'layer {layer} done', flush=True)

if args.csv:
    with args.csv.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
print(f'\nNo intervention: IIA {baseline[0]}/{total}, names-only {baseline[1]}/{total}, IO top-1 {baseline[2]}/{total}')
print('\nWhole-vector patch at N, IIA (names-only) out of', total)
print('layer | block_output | attention_output | mlp_output')
for layer in range(LAYERS):
    cells = {row['site']: row for row in rows if row['layer'] == layer and row['head'] == ''}
    print(f'{layer:5d} | ' + ' | '.join(f"{cells[c]['iia_correct']:3d} ({cells[c]['names_only_correct']:3d})"
                                       for c in ('block_output', 'attention_output', 'mlp_output')))
for site, _, location in HEAD_SITES:
    ranked = sorted((row for row in rows if row['site'] == site),
                    key=lambda row: (-row['iia_correct'], -row['names_only_correct'], row['layer'], row['head']))
    print(f'\n{site} at {location}: top 10 heads, IIA (names-only) out of {total}')
    print(', '.join(f"{row['layer']}.{row['head']} {row['iia_correct']} ({row['names_only_correct']})" for row in ranked[:10]))
    grid = {(row['layer'], row['head']): row['iia_correct'] for row in rows if row['site'] == site}
    print('layer\\head ' + ' '.join(f'{head:4d}' for head in range(HEADS)))
    for layer in range(LAYERS):
        print(f'{layer:10d} ' + ' '.join(f'{grid[(layer, head)]:4d}' for head in range(HEADS)))
