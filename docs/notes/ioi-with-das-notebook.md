# IOI with DAS: Hypotheses, Experimental Design, and Results

*Imported from the Notion research log on 2026-11-16. This file is now the maintained copy.*

**IOI with DAS: From the research question to experimental design and results**

**Goal:** Understand what the notebook tests, why each experiment is included, what the displayed results support, and how future changes could answer new research questions.

## I. The problem: performing IOI versus explaining how it works

**Q: What is IOI?**

A: Indirect Object Identification. For “Mary and John … John gave a book to \_\_\_,” the target is Mary. John is the subject S; Mary is the indirect object IO. GPT-2 always predicts the next token; it is not given a new natural-language instruction to answer “position.”

Varying names, order, and contexts tests ordinary task performance. This notebook goes further: which internal exchanges can control name selection and output?

**Q: What is the experimental hypothesis?**

A: The analysis proposes two high-level variables: position, the slot occupied by the correct IO among the first two names; and name, the IO identity to output. “Select a position, then retrieve/output its name” is a candidate account, not two pre-labelled fields inside the model.

DAS searches for internal subspaces whose interchange produces the counterfactual outputs predicted by these variables. This is an intervention test beyond observing correct behavior or decoding information with a probe.

## II. Experimental design: base, source, target labels, and learned directions

### 2.1 How can the same exchange procedure test two different variables?

The base receives the intervention; the source supplies the replacement representation. Fix the base to “Mary and John … John gave … to,” whose normal answer is Mary.

| Task | Example source | Normal source answer | Counterfactual base target |
| --- | --- | --- | --- |
| Position | John and Mary … John gave … to | Mary (second name) | John: select the base's second name |
| Name | Alice and David … Alice gave … to | David | David: transfer the source IO identity |

**Position transfers a selection slot into the base's name arrangement, not the source's answer identity.** Name targets the source identity. Neither intervention rewrites the base prompt text.

### 2.2 Where does this distinction enter the code?

aligning_variable controls helper sampling and target construction. Position pairs use the same identities in ABB/BAB patterns; name sources use different identities in CDD/DCD. Letters denote identities, not token indices: ABB has A and B initially, then repeats subject B.

Position test pairs are ABB→BAB and BAB→ABB; name test pairs are ABB→DCD and BAB→CDD. Arrows mean base→source. Training includes all four combinations of the respective two base and two source patterns; this does not mean the dataset contains only four sentences.

The position rule chooses the base IO or subject depending on whether base/source subject slots match. The name rule targets the source IO. Resampling name patterns retains the base context, and many examples test whether the effect generalizes.

### 2.3 The “positive feedback” intuition: targets and gradients

GPT-2 weights remain frozen. DAS initializes a direction/subspace, exchanges components, lets GPT-2 compute answer probabilities, calculates loss against counterfactual targets, and backpropagates to update the alignment.

It does not first know which direction encodes name or position. **Changing target labels changes the gradients guiding alignment learning.** This is supervised loss minimization, not reinforcement-learning reward.

The same sentence pair could support different experiments when trained against John versus David. If inputs, targets, learned directions, and exchange operations all stay fixed, merely renaming the experiment changes nothing.

### 2.4 What is exchanged, and what counts as “finding”?

The intervention changes activations: input-dependent intermediate vectors, not GPT-2 weights or all recorded computation after a token. Typically it selects layer + token + stream, obtains a source representation, modifies the base at that site, and recomputes affected downstream computation. Saving every activation of every sentence is unnecessary.

For a unit direction u, a one-dimensional interchange can be written:

$$
h_b'=h_b+u\,u^\top(h_s-h_b)
$$

It retains the base's orthogonal component while replacing its projection along u. A direction can combine many original units; it need not be a neuron. 20D exchanges a subspace spanned by 20 directions; vanilla replaces the entire selected representation; Boundless also learns exchange extent. See experiments 8, 9, and 11.

“Finding” means obtaining an effective counterfactual interchange on evaluation pairs. IIA (Interchange Intervention Accuracy) is the proportion of intervened predictions matching counterfactual targets, not ordinary accuracy, name frequency, or an information quantity.

Failure is conditional on site, method, capacity, and optimization; it does not establish absence. High IIA alone does not establish a unique or complete natural mechanism.

**Q: Are tokens fed in one at a time?**

A: A prompt is usually processed together, but causal attention allows token t to access only itself and earlier positions. The first token at layer 10 still cannot see later words. Tokens pass through the layers; the outer token/layer loops in find_variable_at instead repeat different intervention experiments, not sequential text generation.

## III. Full notebook outline

A “fit” below is a candidate configuration, usually requiring a newly trained alignment, not one sentence. The original helper uses approximately 200 training pairs, 100 test pairs, and 10 epochs per fit. Sweeps are expensive because training repeats; vanilla skips alignment training and is generally faster.

| Stage | Question and motivation | Original scale | Suggested execution order |
| --- | --- | --- | --- |
| 1. Set-up \| Establish the model | Load pretrained GPT-2, its tokenizer, pyvene, and data utilities. This establishes access to internal representations and intervention hooks; it does not train GPT-2 to perform IOI. | Once | Required |
| 2. Factual recall \| Check ordinary task performance | Evaluate GPT-2 on IOI prompts without intervention. Does the model exhibit the behavior that we want to explain? | One baseline evaluation | Required |
| 3. Position in residual and MLP representations \| Where can selection be controlled? | Both heatmaps test position: can a one-dimensional exchange at a particular token and layer make the base answer according to the source's name position? They compare block_output with mlp_activation. | 5 tokens × 12 layers × 2 streams = 120 fits | Start with one fit |
| 4. Multiple tokens at layer 7 \| Is a single site too restrictive? | Test whether position exchange at the earlier layer 7 requires access to representations across multiple tokens. | Joint tokens 0–16, one fit | Second pass |
| 5. Different streams \| Which within-layer stage supports exchange? | Hold endpoint token 17 fixed and ask which computational stages within each layer support position intervention. This follows directly from the heatmaps. | 8 streams × 12 layers = 96 fits | Start with a few sites |
| 6. Individual heads \| Is one head sufficient? | Successful intervention on the combined attention representation does not imply that one head suffices. The notebook tests each head at the endpoint in layers 7 and 8 for position alignment. | 12 heads × 2 layers = 24 fits | Second pass |
| 7. Head groups \| Joint representations and redundancy | If one head is insufficient, can a group support position alignment, and which representations help the joint fit? | 12 leave-one-out + 12 cumulative = 24 fits | Second pass |
| 8. Name with vanilla swap \| Can full replacement transfer the answer name? | Change the target from selecting a base name using the source position to outputting the source's IO name. Begin with full replacement as a comparison that requires no learned direction. | 96 evaluations, no alignment training | Useful early comparison |
| 9. Name with 20D DAS \| Is a smaller learned subspace sufficient? | Keep the name target and ask whether exchanging a learned 20-dimensional subspace, instead of the full representation, can transfer the name. | 8 streams × 12 layers = 96 fits | Start with one fit |
| 10. Trace Name Movers \| How might selection connect to name retrieval? | Test a candidate link: queries participate in deciding where to read, while attention-weighted outputs may carry the retrieved name. | Layers 9/10, 72 fits total | Expand after understanding |
| 11. Boundless DAS \| Does fixed dimensionality constrain the search? | Previously position used 1D and name used 20D. Now learn the exchange extent as well, testing sensitivity to fixed capacity. | 96 position + 96 name = 192 fits | Later |
| 12. Inspect learned weights \| Which head coordinates does DAS use? | Move from whether intervention works to how alignment weights are distributed over head coordinates. | Four additional fits + plots | Later |

## IV. Experiment-by-experiment: changes, expectations, and displayed evidence

**Evidence scope:** Expectations below are hypotheses reconstructed from the design, not claims about preregistration. Results refer to the author's saved charts/text, not our rerun. The inspected main-branch tutorial_data directory lacks the CSVs referenced by plotting cells. Numbers therefore come from displayed labels; unlabelled bars are approximate. We do not claim row-level CSV verification. Missing outputs are explicitly identified. Layer indices are zero-based throughout.

### 1. Set-up | Establish the model

**Q: What question does this experiment ask?**

Load pretrained GPT-2, its tokenizer, pyvene, and data utilities. This establishes access to internal representations and intervention hooks; it does not train GPT-2 to perform IOI.

**Q: What changes, why, and what is expected?**

Fix the model and processing pipeline to establish a common basis for comparison. CPU versus GPU mainly affects runtime; there is no layer or subspace comparison yet.

**Q: Do the displayed results match the expectation?**

The expected outcome is working tokenization and forward computation. The saved output confirms loading, not IOI competence; there is no IIA chart.

**Key clarification from our discussion**

The examples are generated from names, objects, places, and templates by the helper, rather than downloaded as a completed QA dataset. GPT-2 exposes activations, so this is not a strictly input/output-only black-box API.

### 2. Factual recall | Check ordinary task performance

**Q: What question does this experiment ask?**

Evaluate GPT-2 on IOI prompts without intervention. Does the model exhibit the behavior that we want to explain?

**Q: What changes, why, and what is expected?**

Names and contexts vary across examples, but no internal exchange occurs. Measuring ordinary accuracy helps distinguish intervention failure from lack of baseline competence.

**Q: Do the displayed results match the expectation?**

Most examples should be answered correctly. The saved accuracy is 0.91, supporting IOI competence on that batch. This is task accuracy, not IIA or the result of your local run.

**Key clarification from our discussion**

Downloading/loading is setup; evaluating unmodified answers is the baseline. The 91% figure does not guarantee equal performance on every later data split.

### 3. Position in residual and MLP representations | Where can selection be controlled?

**Q: What question does this experiment ask?**

Both heatmaps test position: can a one-dimensional exchange at a particular token and layer make the base answer according to the source's name position? They compare block_output with mlp_activation.

**Q: What changes, why, and what is expected?**

Sweep tokens 13–17 and layers 0–11, comparing the accumulated residual state with internal MLP features. If position becomes accessible at the endpoint late in processing, some endpoint layers should score higher. Strong MLP scores would support a comparable one-dimensional alignment there.

**Q: Do the displayed results match the expectation?**

At token 17, the residual heatmap shows 0.11 at layer 7, 0.70 at 8, 0.44 at 9, and 0.04 at 10. Most other cells are near zero. MLP is not entirely zero: layer 8 reaches 0.04, and layers 7/9 reach 0.02 at token 17. This supports stronger residual alignment near layer 8, not equally effective one-dimensional MLP alignment. Referenced files: block_out_df.csv and mlp_activation_df.csv.

**Key clarification from our discussion**

These are not name-frequency maps. The token axis identifies where to intervene; the position variable identifies which name slot to select. Each cell generally trains a fresh alignment. Low IIA does not prove absence. The residual stream is an accumulated state; MLP activation is an internal nonlinear feature representation in one branch.

### 4. Multiple tokens at layer 7 | Is a single site too restrictive?

**Q: What question does this experiment ask?**

Test whether position exchange at the earlier layer 7 requires access to representations across multiple tokens.

**Q: What changes, why, and what is expected?**

A nested list of tokens 0–16 specifies one joint intervention rather than separate token tests. If distribution across tokens explains weak single-site results, a comparable joint intervention should improve performance.

**Q: Do the displayed results match the expectation?**

The cell has no saved result or corresponding displayed CSV chart. Its title does not establish success; the design is visible, but its score cannot be verified from the saved notebook.

**Key clarification from our discussion**

“Not found at a token” means that the selected representation did not yield an effective alignment under the method, not that a word was absent. Joint access also increases available coordinates and intervention scope; improvement would not prove every token necessary.

### 5. Different streams | Which within-layer stage supports exchange?

**Q: What question does this experiment ask?**

Hold endpoint token 17 fixed and ask which computational stages within each layer support position intervention. This follows directly from the heatmaps.

**Q: What changes, why, and what is expected?**

Compare attention_input (entering attention), attention_value_output (weighted head outputs before output projection), attention_output (the projected attention-branch result), and block_output (the completed block), plus MLP sites and block input, for eight streams total. If attention makes the target alignment more accessible, post-attention IIA should be higher.

**Q: Do the displayed results match the expectation?**

At layer 8, the saved plot shows approximately 0 for attention input, 0.48 for attention value output, 0.30 for attention output, and 0.69 for block output; MLP activation peaks around 0.04. This supports stronger post-attention interventions there. Attention input also reaches 0.23 at layer 10, so position is not exclusively localized to layer 8. Plot source: all_streams_df.csv.

**Key clarification from our discussion**

Not every stream is the residual stream itself; some are internal branch representations. attention_value_output is not raw V. IIA differences are not information quantities. The heatmap's 0.70 and this plot's 0.69 should not be assumed to come from one identical run.

### 6. Individual heads | Is one head sufficient?

**Q: What question does this experiment ask?**

Successful intervention on the combined attention representation does not imply that one head suffices. The notebook tests each head at the endpoint in layers 7 and 8 for position alignment.

**Q: What changes, why, and what is expected?**

Restrict DAS to one head representation at a time. A head sufficient for the intervention should achieve a clearly higher IIA.

**Q: Do the displayed results match the expectation?**

The next section reports that individual heads did not localize the variable and proposes distribution across heads. No per-head output/chart is preserved here, so exact scores are unavailable and distribution is not established as the only explanation.

**Key clarification from our discussion**

A head is a learned reading mechanism: compare Q with token keys K, then use the resulting weights to aggregate values V. GPT-2 small has 12 parallel heads per layer, each operating at many token positions. One head is not one word, and heads do not execute as a sequential chain. Q/K/V roughly correspond to search criteria, matching features, and returned content.

### 7. Head groups | Joint representations and redundancy

**Q: What question does this experiment ask?**

If one head is insufficient, can a group support position alignment, and which representations help the joint fit?

**Q: What changes, why, and what is expected?**

At layer 7, leave one head representation out of the intervention (LOO), then cumulatively add heads in ranked order. Omitting helpful representations may lower IIA; adding them may improve it. Each set is retrained, so monotonicity is not guaranteed.

**Q: Do the displayed results match the expectation?**

Neither set of cells retains result plots, so the trend cannot be checked. The code's anchor_acc=0.48 is hard-coded, not a newly measured all-head layer-7 baseline.

**Key clarification from our discussion**

LOO does not disable a head: omitted heads still run normally, but DAS does not intervene on them. Because every set is retrained, score differences are not fixed independent causal contributions.

### 8. Name with vanilla swap | Can full replacement transfer the answer name?

**Q: What question does this experiment ask?**

Change the target from selecting a base name using the source position to outputting the source's IO name. Begin with full replacement as a comparison that requires no learned direction.

**Q: What changes, why, and what is expected?**

Along with name pairing/labels, enable do_vanilla_intervention. For a 768-dimensional block_output at the selected token and layer, replace all 768 values with the source vector. Later sites should work better if they carry transferable answer content.

**Q: Do the displayed results match the expectation?**

Saved block-output IIA is 0.16 at layer 9, 0.83 at 10, and 0.85 at 11; the three MLP curves display 0.00. This supports stronger late-stage name transfer. These charts use an in-memory dataframe, not a dedicated CSV read.

**Key clarification from our discussion**

Vanilla replaces activations, not model weights, and learns no u; targets are used for evaluation. Earlier position experiments already train 1D DAS. Vanilla is possible for position too, but full replacement can bring the source answer and unrelated information, rather than only its position. This motivates comparison but is not an explicitly stated exclusive author rationale. High vanilla IIA does not isolate a pure name variable.

### 9. Name with 20D DAS | Is a smaller learned subspace sufficient?

**Q: What question does this experiment ask?**

Keep the name target and ask whether exchanging a learned 20-dimensional subspace, instead of the full representation, can transfer the name.

**Q: What changes, why, and what is expected?**

Use DAS with low_rank_dimension=20. For a 768-dimensional block output, learn 20 orthogonal directions, exchange projected components, and retain the orthogonal complement. Some sites may improve or retain performance, but capacity and optimization limits can also reduce scores.

**Q: Do the displayed results match the expectation?**

In the saved plot associated with all_streams_io_name_df.csv, block output is about 0.32 at layer 9 (versus vanilla 0.16), 0.83 at layer 10 (equal), and 0.77 at layer 11 (below 0.85). MLP still displays 0.00. Improvements are site-dependent. The MLP chart title says Name Position, but the code reads name results.

**Key clarification from our discussion**

Twenty names describes the identity vocabulary; 20D describes exchange capacity. It is neither one dimension per name nor replacement of original units 1–20. A direction can combine many units. Name train/test share the first 20 names while splitting contexts/templates, so this does not establish unseen-name generalization. Twenty dimensions is a chosen capacity, not a mathematical necessity.

### 10. Trace Name Movers | How might selection connect to name retrieval?

**Q: What question does this experiment ask?**

Test a candidate link: queries participate in deciding where to read, while attention-weighted outputs may carry the retrieved name.

**Q: What changes, why, and what is expected?**

In layers 9/10, test queries with position labels using LOO; test head_attention_value_output with name labels and 20D DAS using LOO and cumulative groups. If candidate heads support these alignments, excluding their representations should weaken them, while groups may restore performance.

**Q: Do the displayed results match the expectation?**

Approximate bar heights: at layer 9, query LOO excluding head 9 is about 0.01; name-output LOO excluding head 9 is near zero and excluding head 6 is about 0.10. Name cumulative performance starts near zero with head 9 alone and reaches about 0.29 with more heads. At layer 10, query LOO is lowest excluding head 0 (\~0.07); name LOO excluding heads 2/6/10 is about 0.01/0.02/0.03, and cumulative name IIA ends around 0.14. These results motivate inspecting groups, but do not show single-head sufficiency or identical query/name rankings.

**Key clarification from our discussion**

The architecture does not guarantee position-only Q or name-only V. These separately trained alignments do not establish the full causal path. Cumulative orders are hard-coded. Chart references: layer_9/10_head_query_output_mo_data.csv, layer_9/10_head_attention_value_output_mo_data.csv, and DAS_IO_layer_9/10_head_attn_value_out_cumulative_data.csv.

### 11. Boundless DAS | Does fixed dimensionality constrain the search?

**Q: What question does this experiment ask?**

Previously position used 1D and name used 20D. Now learn the exchange extent as well, testing sensitivity to fixed capacity.

**Q: What changes, why, and what is expected?**

Enable do_boundless_das to learn the transformation and subspace boundary. If fixed capacity was a bottleneck, some scores should improve; robust localization should retain roughly similar peak regions.

**Q: Do the displayed results match the expectation?**

Position block output reaches 0.61 at layer 8 (fixed DAS: 0.69) and 0.50 at layer 9 (0.45): similar localization, mixed score changes. Name block output reaches 0.95/0.96 at layers 10/11 (20D: 0.83/0.77), a clearer improvement; MLP remains near zero. This supports the author's stronger name-alignment observation. Plot references: all_streams_boundless_das_df.csv and all_streams_io_name_boundless_das_df.csv.

**Key clarification from our discussion**

The boundary controls the exchanged region in transformed coordinates; it is not a layer boundary or automatic layer search. Its learned size depends on loss, regularization, and optimization, not just intrinsic concept dimensionality.

### 12. Inspect learned weights | Which head coordinates does DAS use?

**Q: What question does this experiment ask?**

Move from whether intervention works to how alignment weights are distributed over head coordinates.

**Q: What changes, why, and what is expected?**

Compare fixed DAS and Boundless for position at layer 8 and name at layer 9, grouping weights by head into histograms. Alignment with earlier head results could appear as stronger loadings on relevant heads; larger subspaces may look more distributed.

**Q: Do the displayed results match the expectation?**

The final author commentary says DAS weights align with head importance, mentions heads 6/10, and describes Boundless as more distributed. This is an author interpretation, not a new IIA measurement. The text follows layer-9 name plots but refers to name position, so the task label is inconsistent and cannot establish a precise position-head claim.

**Key clarification from our discussion**

The vector u can be called a learned direction or alignment direction; multiple directions span a learned subspace. Weight magnitude is not causal importance, and equivalent bases can change elementwise patterns in a multidimensional subspace. Intervention evidence is still needed.

## V. Interpreting the overall findings and starting your own research

The main displayed pattern is effective one-dimensional position alignment near the final token at layer 8, followed by stronger name transfer in layers 9–11. This is compatible with selecting a position and then retrieving a name, but separately trained alignments do not establish the full circuit connecting those steps.

20D DAS improves some sites rather than uniformly beating full replacement. Boundless improves name transfer more clearly, with mixed changes for position. Head-group tests also distinguish “excluding this head hurts” from “this head alone suffices.”

**Q: How does this differ from the earlier IOI circuit notes?**

A: Circuit notes focus on Name Mover, S-Inhibition, Induction, and related heads and paths. This notebook focuses on high-level variables, learned subspaces, and interchange effects. These are complementary forms of evidence. Running IOI_replication does not automatically generate the DAS results in this notebook.

**Q: What is a concrete first research question?**

A: For example: “Does the layer-8 position alignment generalize to templates of different lengths?” Fix the model, labels, training budget, and method; vary the template distribution and align semantic token positions. Report ordinary accuracy, held-out IIA, and multiple seeds, with no-intervention/random-subspace controls. Then vary dimension, head sets, or sites separately so changes remain interpretable.

## VI. Execution and plotting pitfalls

**Q: Why are there plots before I have run DAS?**

A: An ipynb stores previous outputs. Some plotting cells also load precomputed CSV results; redrawing a plot is not retraining. The earlier find_variable_at calls already train DAS by default; training does not wait until a later DAS heading. A fast or failed cell does not establish a completed sweep.

**Q: Where do the CSVs come from?**

A: The intended pipeline is find_variable_at result list → DataFrame → to_csv. Some original writing lines are commented out while read_csv loads old results. Other charts use in-memory dataframes. Running subsequent cells does not necessarily recreate missing files; enable the appropriate generation/writing steps or plot the current results directly.

**Q: Why did the localizing assert length==18 fail?**

A: The helper assumes 18 tokens per prompt, while the inspected prompts had 15 and 19. That alone explains the assertion without assuming GPT-2 changed. Removing the assertion alone can make token 17 refer to padding or a different semantic position. Use compatible fixed templates, or consistently update intervention/evaluation positions to valid dynamic endpoints or semantic positions.

%xmode Verbose only expands error reporting. find_variable_at is defined in `tutorial_ioi_utils.py` and imported into the notebook, so notebook-only search may not find its definition.

**Q: Does a prototype reproduce the author's findings?**

A: A prototype checks that the pipeline runs and produces inspectable output. Few-shot, short-training scores are not a localization replication. Label author figures, local smoke tests, and full reruns separately.

## Appendix A | find_variable_at parameter reference

```py
find_variable_at(
    gpt2, tokenizer, positions, layers, stream,
    heads=None, low_rank_dimension=1,
    aligning_variable="position",
    do_vanilla_intervention=False,
    do_boundless_das=False,
    seed=42, return_intervenable=False, debug=False,
)
```

| Parameter | Experimental choice | Important distinction |
| --- | --- | --- |
| gpt2 | Loaded model being investigated | DAS is trained; GPT-2 weights are frozen |
| tokenizer | Converts prompts and target names to token IDs | Locating a written name is not locating its causal representation |
| positions | Which token representations are available | [16,17] means separate runs; [[16,17]] means one joint run per layer |
| layers | Candidate layers tested independently | Zero-based indices; candidates, not discovered answers |
| stream | Which computational stage supplies the representation | Block output and MLP activation are different spaces |
| heads | Which head representations DAS may use | [6,10] is joint; other heads are not disabled in GPT-2 |
| low_rank_dimension | Capacity of a standard DAS subspace | One means one direction; 20 is not 20 tokens or one direction per name |
| aligning_variable | Whether to transfer position or name | Changes sampling and targets, not just a plot label |
| do_vanilla_intervention | Direct swap without learning directions | The swap is still limited by the chosen site and head set |
| do_boundless_das | Learn the subspace boundary as well | Do not combine with vanilla; low_rank_dimension is not its fixed size control |
| seed | Sampling and initialization randomness | Does not guarantee identical runs across all environments |
| return_intervenable | Return the learned intervention object in addition to results | For a sweep, the original returns only the last object |
| debug | Print the current search location | Not a fast mode; “finding…” is not a success report |

Both method flags false means standard DAS. Vanilla true skips training. Boundless true learns rotation and boundary parameters. Do not set both true: the helper would choose a Boundless intervention type but skip its training because of the vanilla flag.

Original sample count, batch size, epochs, and learning rate are internal constants, not call arguments: 200 training pairs, 100 test pairs, batch size 20, 10 epochs, initial learning rate 0.01.

## Appendix B | Key terminology

- Activation / hidden representation: an input-dependent intermediate vector, not a model parameter.
- Residual stream: the state accumulating updates across sublayers.
- Intervention site / stream: the location and computational stage being modified.
- Learned direction / alignment direction: the learned vector u.
- Subspace / projection: the vector space component selected for exchange.
- Interchange intervention: transferring source representation components into a base.
- Counterfactual target / target label: the answer specified by the high-level exchange rule.
- Loss / gradient / backpropagation: the objective and update mechanism used to learn the alignment.
- IIA: Interchange Intervention Accuracy.
- IO / S / S1 / S2 / END: indirect object, subject, first/second subject occurrence, and final valid input token.

## Sources

- [IOI_with_DAS.ipynb](https://github.com/stanfordnlp/pyvene/blob/main/tutorials/advanced_tutorials/IOI_with_DAS.ipynb)
- [tutorial_ioi_utils.py: sampling, labels, and find_variable_at](https://github.com/stanfordnlp/pyvene/blob/main/tutorials/advanced_tutorials/tutorial_ioi_utils.py)
- [tutorial_data: templates and saved figures](https://github.com/stanfordnlp/pyvene/tree/main/tutorials/advanced_tutorials/tutorial_data)
- Earlier IOI circuit notes: [IOI Circuit Paper Notes: Section-by-Section Outline](ioi-circuit-paper.md)
