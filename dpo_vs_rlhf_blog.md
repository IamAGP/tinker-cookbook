# DPO vs RLHF: Two Paths to Aligning Language Models With Human Preferences

*A comparative dissection of Direct Preference Optimization and Reinforcement Learning from Human Feedback — their architectures, tradeoffs, and when each approach fits.*

Language models can generate fluent text, but fluency alone does not guarantee usefulness. A model that produces grammatically perfect responses may still be unhelpful, evasive, or unsafe. Bridging this gap — training models to behave in ways humans actually prefer — is the central problem of alignment, and it has spawned two dominant approaches that start from the same data but diverge sharply in method.

Both **Direct Preference Optimization (DPO)** and **Reinforcement Learning from Human Feedback (RLHF)** begin with pairwise preference data: given two model responses to the same prompt, a human (or an evaluator model) indicates which one is better. From this shared starting point, the two techniques take fundamentally different paths. DPO collapses the alignment problem into a single supervised loss function. RLHF decomposes it into a multi-stage pipeline — training a reward model, then optimizing the policy against it through reinforcement learning.

The choice between them involves real engineering tradeoffs in complexity, flexibility, compute cost, and training stability. This post examines both approaches through working implementations from the [Tinker Cookbook](https://github.com/thinkingmachines/tinker-cookbook), an open-source fine-tuning recipe library built on the Tinker SDK, to make the comparison concrete rather than theoretical.

---

## The Shared Foundation: Preference Data

Both DPO and RLHF consume the same input: a dataset of labeled comparisons. Each example consists of a prompt, a **chosen** response (the one humans preferred), and a **rejected** response. The Tinker Cookbook supports several standard preference datasets — Anthropic's Helpful-Harmless-Honest (HHH) dataset, NVIDIA's HelpSteer3, and the UltraFeedback corpus.

Under the hood, these datasets flow through a unified `ComparisonDatasetBuilder` abstraction. Each dataset-specific builder (e.g., `HHHComparisonBuilder`) loads the raw HuggingFace data and converts each example into a `LabeledComparison` object containing the prompt conversation, completion A, completion B, and a label indicating which is preferred.

```python
@dataclass
class Comparison:
    prompt_conversation: list[Message]
    completion_A: list[Message]
    completion_B: list[Message]

@dataclass
class LabeledComparison:
    comparison: Comparison
    label: Literal["A", "B", "Tie"]
```

This shared data format is where the paths diverge. DPO consumes these comparisons directly during training. RLHF uses them to train an intermediate reward model, then discards the preference labels entirely during policy optimization.

## DPO: The Single-Stage Approach

### The Core Idea

DPO, introduced by Rafailov et al. (2023), eliminates the reward model entirely. The key insight is mathematical: the optimal policy under the standard RLHF objective (reward maximization with a KL penalty against a reference policy) has a closed-form relationship with the reward function. DPO exploits this relationship to derive a loss function that operates directly on preference pairs.

An analogy clarifies the difference: RLHF is like hiring a food critic (the reward model) and then iteratively refining recipes based on their scores. DPO skips the critic and instead directly compares pairs of dishes, learning which cooking techniques lead to preferred outcomes. Both improve the menu, but DPO avoids the overhead and potential biases of the intermediary.

### The DPO Loss Function

The DPO loss operates on the log probability ratio between the current policy and a frozen reference model (typically the initial model before training):

```
L = -E[log σ(β * (log π_θ(y_chosen|x)/π_ref(y_chosen|x)
                  - log π_θ(y_rejected|x)/π_ref(y_rejected|x)))]
```

The parameter **β** (beta) controls the strength of the KL constraint against the reference policy. A higher β keeps the trained policy closer to its starting point; a lower β allows more aggressive optimization toward the preferences. The Tinker Cookbook defaults to `β = 0.1`.

The implementation in `train_dpo.py` computes this loss through several steps. For each preference pair, the system computes log probabilities of both chosen and rejected responses under both the current policy and the reference model. The reference log probabilities are computed efficiently using a separate sampling client created from the initial weights:

```python
def compute_dpo_loss(chosen_logprobs, rejected_logprobs,
                     chosen_ref_logprobs, rejected_ref_logprobs,
                     dpo_beta):
    chosen_log_ratio = torch.stack(
        [lp - rlp for lp, rlp
         in zip(chosen_logprobs, chosen_ref_logprobs)]
    )
    rejected_log_ratio = torch.stack(
        [lp - rlp for lp, rlp
         in zip(rejected_logprobs, rejected_ref_logprobs)]
    )

    losses = -F.logsigmoid(
        dpo_beta * (chosen_log_ratio - rejected_log_ratio)
    )
    return losses.mean()
```

The loss function effectively asks: relative to where the model started, has the policy increased the likelihood of chosen responses more than rejected ones? Training pushes chosen log ratios up and rejected log ratios down.

### DPO Training Configuration

The Tinker Cookbook's DPO recipe uses the following defaults:

- **Model:** meta-llama/Llama-3.2-1B
- **Learning rate:** 1e-5 (notably lower than SFT's typical 1e-4)
- **Beta:** 0.1
- **Batch size:** 256 preference pairs
- **LoRA rank:** 32
- **Schedule:** Linear decay
- **Epochs:** 1

The training loop processes each batch by splitting it into alternating chosen/rejected pairs, computing reference logprobs through the frozen sampling client, applying the custom DPO loss via `forward_backward_custom`, and updating weights with Adam. Key metrics tracked during training include the DPO loss, implicit reward accuracy (whether the model assigns higher reward to chosen responses), and the margin between chosen and rejected rewards.

---

## RLHF: The Three-Stage Pipeline

### The Architecture

The RLHF pipeline in the Tinker Cookbook follows the methodology from InstructGPT (Ouyang et al., 2022) and consists of three sequential stages, each building on the output of the previous one.

**Stage 1: Supervised Fine-Tuning (SFT).** The base model trains on a high-quality instruction-following dataset — in this case, the [no_robots](https://huggingface.co/datasets/HuggingFaceH4/no_robots) dataset, which contains human-written responses designed to match InstructGPT's methodology. This gives the policy a solid foundation of instruction-following behavior before preference optimization begins.

**Stage 2: Reward Model Training.** A second model trains on the preference data to predict which of two responses a human would prefer. Using the Anthropic HHH dataset, the reward model learns to see a pair of completions and output which one is preferred. The Tinker Cookbook implements this through the `ComparisonRendererFromChatRenderer` class, which formats comparisons into a specific template:

```
[Prompt conversation]
==== Completion A ====
[Response A]
==== Completion B ====
[Response B]
==== Preference ====
[A or B]
```

The reward model trains with standard cross-entropy loss — it is essentially a classifier that predicts "A" or "B."

**Stage 3: Policy Optimization with RL.** The SFT-initialized policy generates multiple completions for each prompt. These completions are scored using a **tournament system**: the preference model evaluates all pairwise matchups between completions in each group. The policy's reward for each completion is its win rate across these matchups. The policy then optimizes against these rewards using importance sampling (a policy gradient method similar to GRPO).

### The Tournament Reward Mechanism

The RLHF stage's reward computation is where the implementation gets architecturally interesting. The `PairwisePreferenceGroupBuilder` constructs a group of environments for each prompt. Multiple completions are sampled, and the preference model scores all pairs:

```python
comparison_indices_pairs = get_pairs_chunked(
    len(response_messages),
    self.tournament_pattern,
    self.matchup_group_size
)

for comparison in j_comparisons:
    reward = await self.preference_model(comparison)
    j_rewards.append(reward)
```

Each completion's reward is computed as its net win-minus-loss score across all matchups, normalized by the number of matchups. A format validity bonus is also applied — completions that fail to parse correctly receive a penalty. This tournament structure provides richer gradient signal than a simple scalar reward, as the model learns not just whether a response is good but whether it is better than specific alternatives.

The advantages are then centered within each group (standard GRPO), and the policy updates via the `importance_sampling` loss function:

```python
advantages_G = rewards_G - rewards_G.mean()
```

### RLHF Configuration

The pipeline's default configuration:

- **Base model:** meta-llama/Llama-3.2-3B
- **SFT stage:** lr=2e-4, 1 epoch on no_robots
- **RM stage:** lr=3e-4, 1 epoch on Anthropic HHH
- **RL stage:** lr=1e-5, group_size=4, batch_size=256
- **LoRA rank:** 64 (higher than DPO's default of 32)
- **Tournament:** ALL_PAIRS_BOTH_WAYS (every pair scored in both orderings)
- **Max tokens:** 1024 per completion

---

## The Structural Comparison

### Complexity

DPO is a single training run. The `train_dpo.main()` function handles everything — data loading, reference logprob computation, loss calculation, and weight updates — in one loop. The total codebase for the DPO implementation spans roughly 400 lines across `train_dpo.py` and the dataset builder.

RLHF requires orchestrating three separate training runs plus a live inference system. The `rlhf_pipeline.py` coordinates the SFT stage, the reward model stage, and the RL stage, each with its own configuration. The RL stage alone is substantially more complex, involving trajectory rollouts, tournament scoring, advantage computation, and policy gradient optimization. The RL training loop in `rl/train.py` spans over 1,200 lines.

### Compute Cost

DPO requires four forward passes per preference pair per training step: the current policy's logprobs on chosen and rejected responses, and the reference model's logprobs on both. These are pure inference operations — no rollout generation, no reward model inference.

RLHF requires forward passes through three separate models at various stages: the SFT model during stage 1, the reward model during stage 2, and during stage 3, both the policy (for generation and training) and the reward model (for scoring). The RL stage also requires generating multiple complete responses per prompt, which is far more expensive than computing logprobs on fixed sequences.

### Flexibility

DPO is constrained to offline preference data. The chosen and rejected responses must exist in the dataset before training begins. The quality of training depends entirely on the quality and coverage of the preference pairs.

RLHF generates its own training data on-policy during stage 3. The policy samples fresh completions at each training step, and these are scored by the reward model in real time. This means the reward signal adapts to the policy's current behavior — as the model improves, it receives comparisons between its own increasingly strong outputs rather than comparing against fixed historical responses.

The Tinker Cookbook's RLHF implementation supports three training modes: fully synchronous on-policy training, streaming minibatch training (overlapping sampling and training for throughput), and async off-policy training (allowing slightly stale trajectories for even higher throughput). DPO has no equivalent design space — it is inherently synchronous and offline.

### Stability

DPO training tends to be more stable. The loss function is a well-behaved classification objective (logsigmoid), and the reference model provides implicit regularization. The main risks are distribution mismatch between the preference data and the model's actual outputs, and the β parameter being miscalibrated.

RLHF carries the usual instabilities of reinforcement learning: reward hacking (the policy exploiting quirks in the reward model), high variance in policy gradient estimates, and KL divergence blowup between the sampling and training policies. The Tinker Cookbook monitors this through two KL divergence estimators (`kl_sample_train_v1` and `kl_sample_train_v2`), with training considered stable when KL stays below 0.01.

---

## When to Use Which

### Choose DPO When:

- **Simplicity matters.** A single training run is easier to debug, reproduce, and maintain than a three-stage pipeline.
- **Compute budget is limited.** DPO avoids the cost of training a reward model and generating on-policy rollouts.
- **High-quality preference data already exists.** If the preference pairs are in-distribution with the base model's capabilities, DPO can extract strong alignment signal without online generation.
- **Iteration speed is important.** DPO experiments complete faster, enabling more rapid hyperparameter sweeps.

### Choose RLHF When:

- **The preference signal is complex or noisy.** A learned reward model can generalize from noisy preferences better than DPO's direct optimization. The reward model acts as a denoising layer between raw preferences and policy updates.
- **On-policy data matters.** For tasks where the model's distribution shifts significantly during training, RLHF's online generation ensures the reward signal remains relevant to the model's current behavior.
- **The reward model has other uses.** Once trained, the reward model can serve as a standalone evaluator, a filter for synthetic data generation, or a component in best-of-N sampling.
- **Maximum alignment performance is the goal.** Empirically, well-tuned RLHF pipelines tend to achieve stronger alignment than DPO on complex tasks, though the gap narrows on simpler preference distributions.

### The Hybrid Middle Ground

The Tinker Cookbook also includes a "shorter" recipe that demonstrates an RLHF-style pipeline with a hand-coded preference function (preferring shorter responses) instead of a learned reward model. This pattern — RL with a programmatic or heuristic reward — provides RLHF's on-policy benefits without the overhead of reward model training. It works when the preference criterion can be expressed as a simple function rather than learned from data.

---

## Practical Guidance

Several implementation details from the Tinker Cookbook are worth highlighting for practitioners considering either approach.

**Start with DPO.** The documentation explicitly recommends DPO as the simpler starting point. Default parameters of `β = 0.1` and `lr = 1e-5` provide a reasonable baseline. If DPO underperforms, the preference data or distribution mismatch is likely the bottleneck, and switching to RLHF may help.

**SFT before DPO matters.** The DPO documentation notes that the base model should already be in-distribution with the preference data. A sharp distribution mismatch between the model's natural outputs and the preference dataset's responses creates pathological training dynamics. A light SFT phase before DPO, or collecting on-policy preferences, mitigates this.

**LoRA rank scales with task complexity.** DPO defaults to rank 32; RLHF uses rank 64. The more complex optimization landscape of RL training benefits from additional parameter capacity.

**Learning rates differ by an order of magnitude between stages.** SFT uses ~2e-4, reward model training uses ~3e-4, and both DPO and the RL policy stage use ~1e-5. The alignment-specific stages require gentler optimization to avoid catastrophic forgetting of the base capabilities.

**The tournament structure in RLHF is configurable.** `ALL_PAIRS_BOTH_WAYS` provides the richest signal (every pair scored in both orderings) but has O(n^2) cost. The `matchup_group_size` parameter caps this by dividing large groups into smaller tournament brackets, providing a throughput-quality tradeoff.

## Conclusion

DPO and RLHF represent two points on a complexity-capability spectrum for preference learning. DPO achieves surprising effectiveness by collapsing the alignment objective into a single loss function, eliminating the reward model, the rollout infrastructure, and the instabilities of policy gradient methods. RLHF pays for its complexity with genuine capabilities DPO cannot match: on-policy data generation, a reusable reward model, and the ability to explore beyond the static preference dataset.

The deeper insight is that these approaches are not competitors but complements. DPO serves as an efficient first pass at preference alignment — fast to train, easy to iterate on, and often sufficient for well-specified preference distributions. RLHF becomes necessary when the alignment task demands the full power of online exploration and learned reward generalization.

As preference learning matures, the boundary between these approaches continues to blur. Techniques like iterative DPO (generating new preference pairs from the current policy) and offline RL methods borrow ideas from both camps. The Tinker Cookbook's unified data abstraction — where the same `ComparisonDatasetBuilder` feeds both DPO and RLHF pipelines — reflects this convergence at the implementation level.

---

**Sources and References**

- [Tinker Cookbook — DPO Recipe](https://github.com/thinkingmachines/tinker-cookbook/tree/main/tinker_cookbook/recipes/preference/dpo) — Complete DPO training implementation with CLI interface
- [Tinker Cookbook — RLHF Pipeline](https://github.com/thinkingmachines/tinker-cookbook/tree/main/tinker_cookbook/recipes/preference/rlhf) — Three-stage RLHF pipeline implementation
- [Tinker SDK Documentation](https://tinker-docs.thinkingmachines.ai) — Platform documentation for the remote GPU training API
- [Rafailov et al., "Direct Preference Optimization: Your Language Model is Secretly a Reward Model" (2023)](https://arxiv.org/abs/2305.18290) — The original DPO paper
- [Ouyang et al., "Training Language Models to Follow Instructions with Human Feedback" (2022)](https://arxiv.org/abs/2203.02155) — The InstructGPT paper establishing the RLHF pipeline
- [Anthropic HH-RLHF Dataset](https://huggingface.co/datasets/Anthropic/hh-rlhf) — The preference dataset used in both implementations
- [Schulman, "Approximating KL Divergence" (2020)](http://joschu.net/blog/kl-approx.html) — KL divergence estimation methods used in training monitoring

---

*Tags: LLM Alignment, RLHF, Direct Preference Optimization, Reinforcement Learning, Machine Learning*
