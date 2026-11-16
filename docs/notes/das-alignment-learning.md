# Understanding DAS II: From Exchanging an Intermediate Value to Learning an Alignment

*Imported from the Notion research log on 2026-11-16. This file is now the maintained copy.*

Previous note: [DAS Foundations: Causal Abstraction, Interventions, and Hierarchical Equality](das-foundations.md)

This continuation follows one example through DAS. Symbols are introduced where they are needed. “Understanding notes” address questions raised during the discussion; they can be read after the main explanation. Colab implementation and results remain reserved for later.

## 1. Start with the question: Does the model actually use the steps we propose?

Suppose a neural network has learned a task involving four symbols. We propose a simple algorithm: compare the first pair, compare the second pair, and then check whether the two comparison results agree.

X denotes the complete input and a₁ through a₄ its four symbols:

$$
X=(a_1,a_2,a_3,a_4)
$$

$$
P=(a_1=a_2),\qquad Q=(a_3=a_4),\qquad O=(P=Q)
$$

P and Q are Boolean intermediate results; O is the final answer. This is the researcher-proposed **high-level causal model**. The trained network and its activations form the **low-level neural model**.

For X=(A,A,B,C), P=True and Q=False, so O=False. A network might answer correctly without first computing P and Q. DAS seeks evidence for the internal-computation hypothesis, rather than merely remeasuring task accuracy.

This continues the previous note: mechanistic interpretability seeks explanations of internal computation; causal abstraction provides a framework for comparing high- and low-level models; DAS searches for distributed alignments within that framework. The earlier truth table, causal diagram, and background glossary remain available in the previous note.

**Understanding note — Are P and Q inputs?**

No. The inputs are still the four symbols. P and Q are proposed intermediate variables. Defining them in a high-level model does not establish that the neural network has two corresponding labelled fields.

## 2. First determine what the answer should be if only P is replaced

To test P's causal role, start with an interchange intervention in the high-level model.

We need two inputs:

- **Base:** the main computation receiving the modification.
- **Source:** another computation supplying the replacement value.

Use the following example throughout:

$$
X_b=(A,B,C,C),\qquad X_s=(D,D,E,F)
$$

Subscripts b and s mean base and source. The base gives P_b=False and Q_b=True; the source gives P_s=True and Q_s=False. Both original outputs are False.

Replace only the base's P with the source's P:

$$
(P_b,Q_b)\longrightarrow(P_s,Q_b)=(\mathrm{True},\mathrm{True})
$$

The expected answer is now True. This is a **counterfactual output**: what should happen if the intermediate value is changed in this particular way?

Let y_cf denote the correct counterfactual label; cf abbreviates counterfactual:

$$
y_{\mathrm{cf}}=(P_s=Q_b)
$$

**Understanding note — Why not use the source's original answer?**

We borrow only its P, not its entire computation. Here the source originally answers False, while the intervened base should answer True.

## 3. The neural network has hidden activations, not a field labelled P

To perform a corresponding neural intervention, we must identify which internal representation plays P's role.

First choose an intervention site. In an MLP, this may be a hidden-layer vector. In a Transformer, specify a layer, token position, and component, such as the residual stream.

The activation there is:

$$
h=(h_1,h_2,\ldots,h_d)^\top
$$

h is the **hidden activation**; its coordinates are real numbers; d is its dimension. The superscript ᵀ denotes transpose, arranging the entries as a column vector here.

Running the base and source yields two vectors at the same site:

$$
h_b,\ h_s\in\mathbb R^d
$$

h_b belongs to the base and h_s to the source; R^d denotes d-dimensional real space. Their coordinates are not already partitioned into known P and Q fields.

A concept may be represented by a combination of many coordinates: a **distributed representation**. Searching only individual neurons or coordinate-aligned groups can miss an oblique direction. This makes the earlier limitation of localist alignment concrete.

**Understanding note — Is h random?**

It is not arbitrary noise. With fixed inputs and model, and stochastic operations such as dropout disabled, h is a computed result. Its lack of immediately readable semantics does not mean it lacks structure.

## 4. Change coordinates so a candidate representation becomes easier to exchange

If P is represented along distributed directions, we can describe the vector in a different **basis**, or set of coordinate axes.

DAS uses a matrix R:

$$
z_b=Rh_b,\qquad z_s=Rh_s
$$

R is a d×d **rotation/alignment matrix**. z_b and z_s are the corresponding d-dimensional representations in the new coordinates. Both use the same R so their coordinates are comparable. R is the alignment DAS learns.

For a four-dimensional space, suppose we designate the first two coordinates as the candidate P region. Their directions span a **subspace**:

$$
\mathcal S_P=\{(\alpha,\beta,0,0)^\top:\alpha,\beta\in\mathbb R\}
$$

S_P names this candidate subspace; α and β are arbitrary real numbers. It is the entire plane spanned by those directions, not one example's activation.

Let k denote the subspace dimension: here k=2 and d=4. DAS adjusts R so intervention on this designated region can play P's causal role.

**Understanding note — Do the first two numbers equal Boolean P?**

No. They jointly form a candidate representation and need not equal 0 or 1. Before training, the correspondence is unknown; afterward, intervention tests must support it.

**Understanding note — If R starts randomly, aren't the z vectors random too?**

Random initialization means the initial axes have no designated semantics. Given fixed R and h, however, z=Rh is determined. As training changes R, the same h acquires different z coordinates.

## 5. Use a mask: selected coordinates from the source, everything else from the base

To exchange the first two rotated coordinates, mark them with a **mask**.

The most direct notation is a vector:

$$
m=(1,1,0,0)^\top
$$

m is a d-dimensional binary vector. A 1 means “replace this coordinate with the source”; a 0 means “keep the base.” In the next equation, ⊙ means elementwise multiplication and 1_d is the d-dimensional all-ones vector:

$$
z_{\mathrm{int}}=m\odot z_s+(\mathbf1_d-m)\odot z_b
$$

int abbreviates intervention; z_int is the exchanged vector.

Using illustrative numbers:

$$
z_b=(10,20,30,40)^\top,\qquad z_s=(1,2,3,4)^\top
$$

The selected source part is (1,2,0,0), and the retained base part is (0,0,30,40). Adding them gives:

$$
z_{\mathrm{int}}=(1,2,30,40)^\top
$$

This is replacement: exchange the first two coordinates and retain the last two. The numbers only illustrate the operation; they are not evidence that those coordinates encode P.

### Relating this to the matrix formula

Put the entries of m on a diagonal to form a d×d matrix M:

$$
M=\operatorname{diag}(1,1,0,0)
$$

diag constructs a diagonal matrix with zeros elsewhere. I_d is the d×d identity. The same exchange is:

$$
z_{\mathrm{int}}=Mz_s+(I_d-M)z_b
$$

Lowercase m consistently means the vector mask; uppercase M means the matrix mask.

**Understanding note — Is M the source's P plus the base's Q?**

No. M is a selector; Mz_s is the selected source representation. I−M retains all unexchanged base coordinates, not just Q. Whether this functionally preserves Q must be tested.

**Understanding note — Why M for the source and I−M for the base?**

They select complementary regions. Using M for both would add values in the same region and erase the rest. Interchange is not adding the base's and source's P representations together.

**Understanding note — Do we learn M or R?**

In the standard-DAS formulation used here, k and the mask are specified and R is learned. M chooses slots in rotated coordinates; R determines which original directions enter those slots. Boundless DAS additionally learns subspace boundaries; it does not automatically remove every layer and position choice.

## 6. Return to the original coordinates and continue the base computation

The exchange occurred in our new coordinate system, while the network's remaining computation expects the original coordinates.

R is constrained to be **orthogonal**:

$$
R^\top R=I_d,\qquad R^{-1}=R^\top
$$

R⁻¹ is the inverse matrix. Orthogonality makes the inverse equal to the transpose and preserves lengths and angles under the coordinate transformation.

$$
h_{\mathrm{int}}=R^\top z_{\mathrm{int}}
$$

h_int is the intervened activation in the original coordinates. Insert it into the chosen base location and recompute downstream output.

The complete neural exchange is therefore:

$$
\boxed{h_{\mathrm{int}}=R^\top[MRh_s+(I_d-M)Rh_b]}
$$

Read it as: rotate both activations; use the selected source region and remaining base region; rotate back.

**Understanding note — Does rotating change the model's information?**

An invertible coordinate change alone neither adds nor discards information. The exchange in between changes the activation. Orthogonality does not guarantee the resulting vector is a naturally occurring neural state.

**Understanding note — Are all other neural states frozen?**

Untargeted base context is retained, but affected downstream computation is recomputed. A Transformer generally still requires other token states; one cannot discard everything except h_int.

## 7. How does DAS learn a good R?

So far, we assumed an R. Now ask which R makes the exchange meaningful.

In our running example, the high-level target is y_cf=True. If the intervened network still favors False, the current alignment has not reproduced that high-level intervention.

During training, encode False/True as classes 0/1. Let p be the two-class probabilities after neural intervention, and p[y_cf] the probability assigned to the correct counterfactual label:

$$
\mathcal L=-\log p[y_{\mathrm{cf}}]
$$

L is the loss and log is the natural logarithm. This is single-example cross-entropy; average over multiple pairs. A higher probability for the correct class means lower loss. If the target is True, a probability of 0.9 for True incurs less loss than 0.1.

DAS adjusts R through gradient-based optimization so neural interventions match high-level targets across many base/source pairs. The original neural-network weights remain frozen.

To preserve orthogonality, an implementation can parameterize R as R(θ) and update θ:

$$
\theta\leftarrow\theta-\eta\nabla_\theta\mathcal L
$$

θ denotes trainable parameters; η is the learning rate; ∇θL is the loss gradient. This is conceptual SGD notation; an implementation may use Adam. An arbitrary update to R does not automatically preserve orthogonality.

**Understanding note — How can learning occur if the original model is frozen?**

Frozen means its weights are not updated, not that its computation is bypassed. Gradients must still pass through the intervened downstream network to determine how the alignment should change. One learned R is reused across new pairs, rather than retrained for every input.

## 8. Now revisit the distinction between probing and DAS

After seeing the full procedure, the distinction is not simply whether activations are edited. It is **which objective identifies the direction**.

A probe adds a decoder that learns to predict P from h. DAS learns R so the original network's intervened output matches y_cf. One reads intermediate information; the other tests and learns its interventional role.

| Method | What is learned or tested |
| --- | --- |
| Probe | A decoder predicting P from h; decodability |
| Probe-guided intervention | A probe-derived direction followed by an intervention test |
| Localist alignment | Correspondences restricted to neuron-coordinate groups, evaluated by intervention |
| DAS | Distributed alignment learned through counterfactual intervention loss |
| Sparse autoencoder (SAE) | Features learned through reconstruction and sparsity; not by itself proof of P's causal role |

A probe-derived direction can also be used to edit activations: this is a probe-guided intervention. It may work, but its direction was initially learned through decodability rather than DAS's intervention loss.

**Understanding note — What did “split h into P and Q, then edit it” mean earlier?**

It described what we would like to do if an alignment had already been found. It did not explain how to find it. Treating the P/Q regions as known skips DAS's central search problem.

**Understanding note — Why doesn't decodability establish use?**

Information can be an incidental copy or correlate of what the model actually uses. The decoder's direction need not be the one used by downstream computation. This motivates examining intervened behavior.

## 9. How do we evaluate the learned alignment?

After training, use unseen pairs to ask how often neural intervention agrees with the high-level counterfactual answer. This is **Interchange Intervention Accuracy (IIA)**:

$$
\mathrm{IIA}=
\frac{\text{pairs with matching neural and high-level counterfactual answers}}
{\text{total test pairs}}
$$

Task accuracy measures original answers; probe accuracy measures whether P is decodable; IIA measures agreement after intervention.

The four examples below can be worked by hand before examining notebook labels. T=True and F=False. These are teaching examples, not neural experiment results.

| Operation | Base → (P,Q,O) | Source → (P,Q,O) | Intervened (P,Q) → O |
| --- | --- | --- | --- |
| 1. Replace P | (A,B,C,C) → (F,T,F) | (D,D,E,F) → (T,F,F) | (T,T) → T |
| 2. Replace P | (A,A,B,B) → (T,T,T) | (C,D,E,E) → (F,T,F) | (F,T) → F |
| 3. Replace Q | (A,A,B,B) → (T,T,T) | (C,D,E,F) → (F,F,T) | (T,F) → F |
| 4. Replace P/Q together | (A,A,B,B) → (T,T,T) | (C,D,E,E) → (F,T,F) | (F,T) → F |

Example 1 takes Ps=T and retains Qb=T, giving T. Example 2 takes Ps=F and retains Qb=T, giving F. Example 3 retains Pb=T and takes Qs=F, giving F. Example 4 takes both source values, giving F.

Add a no-change control: base=(A,A,B,B), source=(C,C,D,E), replace only P. Both P values are T; Qb stays T, so the output stays T.

**Understanding note — Must an intervention change the answer?**

No. It must match the high-level prediction, including no-change cases. However, for O=(P=Q), flipping one Boolean while holding the other fixed necessarily flips O. The no-change example exchanges the source of a value without changing that high-level value.

Credible evidence also requires random-rotation/no-intervention controls and new inputs or pairs. Use validation data to select sites/k, then reserved test data for evaluation. The relevant baseline is not automatically 50%; it depends on the dataset.

High IIA supports the specified alignment on the tested interventions. It is not automatically a proof of a unique mechanism or behavior on every possible input.

## 10. What choices and difficulties remain in practice?

There are two different searches:

1. **Location:** which layer, token, and component?
2. **Direction:** which R and subspace within that location?

A standard single-site experiment fixes the location before learning R. One can compare selected candidate sites; testing every layer is not mandatory. Multi-layer comparisons generally train and evaluate separate alignments.

**Understanding note — Does DAS automatically detect the mechanism across all layers?**

No. Gradient search mainly handles alignment within the selected representation space. Layers and positions usually still require choices. Several layers may work, and the highest-IIA layer is not necessarily where P first forms.

**Understanding note — Is training really easy?**

Not necessarily. A probe can train on cached activations; DAS repeatedly computes intervened downstream outputs and gradients. A full d×d rotation at d=4096 contains about 16.8 million matrix entries, subject to orthogonality constraints. More locations, k values, and seeds increase cost.

Low IIA can result from a poor site, an insufficient subspace, failed optimization, or an unsuitable high-level hypothesis. It does not by itself establish that the model lacks P.

P and Q also need not be represented at the same site. Joint intervention requires explicitly designed disjoint subspaces in a common representation or a multi-site setup. Independently learned, potentially overlapping directions cannot simply be combined.

## 11. From understanding to Colab: What exactly should be reproduced?

The pseudocode below summarizes the pipeline. It assumes the original model has already learned the task. If the notebook trains that model first, task training and DAS alignment training are separate stages.

```txt
Fix the high-level model, original neural model, site, and subspace size
Initialize orthogonal rotation R

For each batch of base/source pairs:
    Compute the high-level counterfactual labels
    Extract h_base and h_source at the same site
    Rotate both with the same R
    Use source values in the selected region and base values elsewhere
    Rotate back using R transpose
    Insert into the base and continue downstream neural computation
    Compute cross-entropy against the counterfactual labels
    Update alignment parameters while maintaining orthogonality

Freeze the learned alignment
Evaluate IIA, controls, and generalization on held-out data
```

**Colab**

**Execution status:** Pending; no experimental results recorded yet.

[Official DAS introductory notebook](https://github.com/stanfordnlp/pyvene/blob/main/tutorials/advanced_tutorials/DAS_Main_Introduction.ipynb)

**Environment:** Python/PyTorch/Transformers/Pyvene versions and CPU/GPU:

**Experiment configuration:** model, task accuracy, layer/position/component, k, seed, data split, learning rate, batch size, epochs:

**Initial results:** last successful cell, outputs, loss/IIA:

**Implementation log:** error message, attempted fix, next step:

First verify imports, data, and the neural model; then locate base/source labels, intervention configuration, and the training loop. Running a batch is initial progress; full reproduction still requires evaluation and checking the setup.

This note provides derivations, examples, and the procedure. Next come independent verification, Colab execution, results, limitations, and a follow-up experiment. Written conceptual coverage does not mean execution is complete.

## 12. Questions that naturally follow from this understanding

These move beyond terminology toward what constitutes convincing research evidence. Prioritize the first three if meeting time is limited.

### 1. How do we distinguish output control from the mechanism the model already uses?

I understand that R is trained so interventions match counterfactual labels. I am still unsure whether this could identify a direction that controls downstream answers without faithfully representing the model's natural computation of P.

**Question:** How do we distinguish a subspace that genuinely reflects the model's computation of P from one that simply steers the output toward the desired counterfactual label? What controls would you consider most convincing?

This asks for an operational evidence standard rather than assuming that intervention alone proves the mechanism.

### 2. How do we verify that replacing P does not also alter Q's role?

I understand that I−M preserves a geometric complement. However, Q could be entangled with selected directions; preserving coordinates does not automatically establish high-level selectivity.

**Question:** The mask preserves the orthogonal complement, but how do we test whether the intervention selectively changes P while preserving Q? Would joint P/Q interventions or additional tests help establish that?

### 3. How should we distinguish a wrong hypothesis from a failed search?

I understand that layer, k, initialization, optimization, and the causal hypothesis can all matter. I am less clear about the diagnostic order and when to stop searching.

**Question:** If DAS gives low IIA, how should I distinguish an incorrect causal hypothesis from a poor intervention site, insufficient subspace dimension, or optimization failure? What diagnostic sequence would you recommend?

### 4. Why might a Boolean P require a multidimensional subspace?

P has only two possible values, but its neural implementation need not occupy one linear direction. I want to understand how to choose k without exchanging unrelated information.

**Question:** Since P is Boolean, how should I think about the dimensionality of its neural subspace? How would you choose k and assess whether a larger subspace is capturing extra, unrelated information?

### 5. What can successful alignment at several layers tell us about computation order?

The same interventional behavior may be supported at multiple layers. I want to distinguish where P forms from where it is preserved or transmitted.

**Question:** If several layers achieve high IIA for P, what can we conclude about where P is computed versus preserved or transmitted? What additional experiment would help distinguish these roles?

Finally, confirm scope: complete hierarchical equality first, or move to BERT/MoNLI/a specified task? Is the September 25 deliverable a stable reproduction or preliminary new-task results?

## Closing summary

DAS starts from a testable high-level hypothesis. For each base/source pair, it computes the answer expected after exchanging an intermediate variable, then performs a corresponding exchange in a candidate neural subspace. It learns R to improve counterfactual agreement and evaluates the alignment on unseen pairs and controls.

The previous note covers the planned background, terminology, introduction, truth table, and causal diagram. This continuation covers interventions, distributed representations/bases/rotations, mathematics and pseudocode, IIA/method comparison, implementation placeholders, research questions, and next steps. Execution and numerical results remain pending.

### Additional terminology

| Term | Working meaning |
| --- | --- |
| Activation | Numerical vector computed at a selected neural site |
| Basis / change of basis | Coordinate axes / describing a vector using different axes |
| Subspace | All linear combinations of a set of directions |
| Mask | A selector specifying which coordinates come from the source |
| Orthogonal matrix | A matrix whose transpose is its inverse |
| Counterfactual label | The target answer predicted after a high-level intervention |
| Cross-entropy | Loss determined by the predicted probability of the correct class |
| Held-out evaluation | Testing on data not used for training or tuning |
| IIA | The proportion of matching neural/high-level counterfactual answers |

### References

- [Original DAS paper](https://arxiv.org/abs/2303.02536)
- [Boundless DAS](https://arxiv.org/html/2305.08809v3)
- [Official Pyvene repository](https://github.com/stanfordnlp/pyvene)

These are learning notes from the discussion. Equations use a consistent single-site, single-variable teaching formulation. Numerical examples are not experimental results.
