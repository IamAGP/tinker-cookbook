# On-Policy Distillation: Teaching Student Models From Their Own Mistakes

*An RL-based training technique replaces static teacher demonstrations with live student-generated text, achieving 10x compute efficiency gains and eliminating the compounding error problem in knowledge distillation.*

Distilling a large teacher model into a smaller student model typically follows a straightforward recipe: generate a dataset of teacher responses, then train the student on those responses through supervised fine-tuning. This approach — off-policy distillation — works. It also carries a structural flaw that becomes visible only at inference time.

The flaw is **exposure bias**. During training, the student sees only the teacher's text. During inference, the student generates its own text. If the student drifts even slightly from the teacher's phrasing at token five, every subsequent token conditions on a sequence the student never encountered during training. The error compounds. A student that appeared competent on teacher-generated text produces degraded outputs when generating freely. The training distribution and the inference distribution are fundamentally mismatched.

**On-policy distillation** resolves this mismatch by inverting the training paradigm. Instead of training on the teacher's text, the student generates its own text and the teacher evaluates it. The student learns from its own mistakes rather than memorizing the teacher's successes. First formalized as Generalized Knowledge Distillation (GKD) by Agarwal et al. (2024), the technique has since been shown by Park et al. (2026) to be a special case of KL-constrained reinforcement learning — unifying distillation and RL under a single theoretical framework.

---

## The Three Training Paradigms

Understanding on-policy distillation requires positioning it against the two methods it bridges.

An analogy from education illustrates the distinction. Off-policy distillation resembles a student copying a textbook — effective for absorbing structured knowledge, but the student never practices solving problems independently. Reinforcement learning resembles a student attempting problems with only a pass/fail grade at the end — powerful for developing strategy, but inefficient because a single binary signal carries almost no information about what went wrong. On-policy distillation resembles a student solving problems while a tutor watches over their shoulder, providing token-by-token feedback on every step. The student works in their own handwriting, but the tutor's dense supervision prevents compounding errors.

The three methods differ along two axes: where the training text comes from (sampling policy) and how much feedback each example provides (reward density). Supervised fine-tuning uses off-policy sampling with dense per-token supervision. Reinforcement learning uses on-policy sampling with sparse per-episode rewards. On-policy distillation combines the best of both — on-policy sampling with dense per-token supervision from the teacher model's probability distribution.

This combination explains the technique's efficiency. Sparse rewards provide approximately O(1) bits of information per episode — a single scalar for an entire generated sequence. Dense token-level KL divergence provides approximately O(N) bits, where N is the sequence length. For a 1,000-token generation, that represents a roughly thousandfold increase in gradient signal per training example.

## How It Works: Reverse KL as the Only Reward

The mechanism operates through a deliberately minimal environment. The student model receives a prompt, generates a complete response, and receives zero task-specific reward. No correctness checking. No format validation. The only training signal comes from comparing the student's token-level probability distribution against the teacher's.

The [Tinker Cookbook](https://github.com/thinkingmachines/tinker-cookbook), an open-source fine-tuning recipe library built on the Tinker SDK, implements this through a `PromptOnlyEnv` that explicitly returns zero reward for every action:

```python
class PromptOnlyEnv(ProblemEnv):
    def check_format(self, sample_str: str) -> bool:
        return True  # No format checking for distillation

    def check_answer(self, sample_str: str) -> bool:
        return False  # No answer checking for distillation

    async def step(self, action: Action) -> StepResult:
        return StepResult(
            reward=0.0,
            episode_done=True,
            next_observation=tinker.ModelInput.empty(),
            next_stop_condition=self.stop_condition,
            metrics={},
        )
```

The supervision arrives entirely through the `incorporate_kl_penalty` function, which computes the **reverse KL divergence** between the student's and teacher's token distributions. For each token in the student's generated sequence, the function computes `log p_student - log p_teacher` — measuring how much the student's probability assignment diverges from the teacher's:

```python
reverse_kl = [
    (sampled_logprobs - torch.tensor(teacher_logprobs[1:])) * mask
    for teacher_logprobs, sampled_logprobs, mask in safezip(
        teacher_logprobs_D, sampled_logprobs_D, float_masks
    )
]

for i, datum in enumerate(data_D):
    kl_advantages = -kl_penalty_coef * float_masks[i] * reverse_kl[i]
    datum.loss_fn_inputs["advantages"] = tinker.TensorData.from_torch(
        datum.loss_fn_inputs["advantages"].to_torch() + kl_advantages
    )
```

The negative sign converts divergence into reward: tokens where the student closely matches the teacher receive near-zero penalty, while tokens where the student diverges sharply receive large negative advantages. The policy gradient optimizer (importance sampling, following GRPO-style advantage centering) then pushes the student toward the teacher's distribution at precisely those tokens where the gap is largest.

The choice of **reverse** KL (student || teacher) rather than forward KL (teacher || student) is deliberate. Reverse KL produces mode-seeking behavior — the student concentrates on the teacher's high-probability regions rather than spreading across all of them. This yields focused, high-quality outputs rather than hedged, uncertain ones.

## The Training Pipeline

The full training loop follows standard RL structure with one critical addition. At each training step, the student generates multiple completions per prompt (group size of 4 by default). These completions pass through GRPO-style advantage centering within each group, then the KL penalty is incorporated before the policy gradient update.

The Tinker Cookbook's default configuration for reasoning tasks reflects this architecture:

- **Student model:** Qwen/Qwen3-8B-Base
- **Teacher model:** Qwen/Qwen3-8B
- **Learning rate:** 1e-4
- **Group size:** 4 rollouts per prompt
- **Batch size:** 1,024 groups per step
- **Max tokens:** 4,096 per completion
- **KL penalty coefficient:** 1.0
- **Loss function:** importance sampling
- **LoRA rank:** 128

The pipeline typically begins from an SFT-initialized checkpoint rather than a raw base model. This initialization provides a reasonable starting distribution, ensuring the student's early generations are coherent enough for the KL penalty to provide meaningful signal. Training then proceeds on prompt-only datasets — the DeepMath-103K corpus for reasoning tasks, or the Tulu3 mixture for general instruction following — where the teacher provides live supervision without any static demonstration data.

---

## Concrete Results: 10x More Efficient Than RL

The performance gains measured by Thinking Machines Lab on the AIME 2024 benchmark demonstrate the technique's efficiency advantage over both alternatives.

Starting from a supervised fine-tuning checkpoint scoring approximately 60% on AIME'24, reinforcement learning with verifiable rewards reached 67.6% — requiring 17,920 GPU hours. On-policy distillation from the same starting checkpoint reached **74.4%** in approximately **1,800 GPU hours**. That represents a 10x compute efficiency improvement while achieving a higher final score.

The comparison against off-policy distillation is equally striking. Standard SFT on the OpenThoughts3 dataset achieves approximately 55% on AIME'24 after 3,000 gradient steps. On-policy distillation reaches 65% after just 100 steps — a 30x reduction in training iterations for a 10-percentage-point improvement. The difference stems directly from eliminating exposure bias: the student trains on its own distribution from the start, so the training signal remains relevant throughout optimization.

## Multi-Teacher Distillation: Domain-Specific Expertise

The architecture generalizes naturally to scenarios requiring different expertise across domains. The Tinker Cookbook's `CompositeDataset` class interleaves batches from multiple datasets, each paired with its own teacher model:

```python
deepmath_teacher_config = TeacherConfig(
    base_model="Qwen/Qwen3-32B"
)
tulu3_teacher_config = TeacherConfig(
    base_model="Qwen/Qwen3-235B-A22B-Instruct-2507"
)
```

In this configuration, a Qwen3-8B student learns mathematical reasoning from a 32-billion-parameter teacher while simultaneously learning general instruction following from a 235-billion-parameter teacher. Each teacher supervises only its domain. The `CompositeDataset` concatenates the per-dataset batches and tracks which teacher corresponds to each datum, ensuring KL penalties are computed against the correct teacher distribution.

This multi-teacher pattern enables building specialist student models that combine capabilities from teachers of different sizes and training backgrounds — a capability that would require complex data mixing and careful curriculum design under off-policy distillation.

## Recovering Lost Capabilities: The Personalization Case

Beyond improving raw performance, on-policy distillation addresses a common production failure mode: catastrophic forgetting during domain adaptation.

Thinking Machines Lab demonstrated this with an internal company assistant. Fine-tuning on domain-specific documents boosted internal QA performance but devastated general instruction-following ability — the IF-eval score dropped from 85% to 45%. The model gained domain knowledge at the cost of its conversational competence.

On-policy distillation recovered the lost capability. Using the pre-fine-tuning model as teacher, the technique restored instruction-following to 83% within approximately 100 training steps while preserving the newly acquired domain knowledge at 41% on internal QA. The teacher's role here is not to teach new capabilities but to re-invoke capabilities that were disrupted during fine-tuning — functioning as a behavioral anchor rather than a knowledge source.

---

## When On-Policy Distillation Fits

The technique delivers its strongest advantages under specific conditions. A capable teacher model must be available, since the quality of supervision directly determines the student's ceiling. The task must benefit from sequential reasoning where exposure bias would otherwise compound — mathematical problem-solving, multi-step instruction following, and long-form generation are natural candidates. And the training infrastructure must support simultaneous student rollouts and teacher logprob computation, which the Tinker SDK handles through its separation of CPU-side orchestration and GPU-side computation.

The technique is less appropriate when no suitable teacher exists, when the target behavior diverges significantly from any available teacher (requiring genuine exploration rather than imitation), or when the task is simple enough that exposure bias does not meaningfully degrade off-policy SFT performance. Classification tasks with single-token outputs, for example, gain little from on-policy sampling.

## Conclusion

On-policy distillation occupies a precise position in the training methodology landscape — the intersection of reinforcement learning's distribution-matching property and supervised learning's dense gradient signal. The theoretical insight, confirmed by Park et al. (2026), that on-policy distillation is a special case of KL-constrained RL with the teacher's distribution as the reward signal, reveals that the boundary between distillation and reinforcement learning is thinner than traditionally assumed.

The practical significance is equally clear. Dense token-level teacher supervision eliminates the information bottleneck of sparse rewards. On-policy sampling eliminates the distribution mismatch of off-policy data. The combination achieves what neither approach accomplishes alone: rapid convergence to strong performance without the fragility of RL reward hacking or the exposure bias of static demonstrations. The student model does not memorize the teacher's answers. It learns to think like the teacher while writing in its own voice.

---

**Sources and References**

- [Thinking Machines Lab — On-Policy Distillation Blog Post](https://thinkingmachines.ai/blog/on-policy-distillation/) — Original results and methodology description
- [Tinker Cookbook — Distillation Recipes](https://github.com/thinkingmachines/tinker-cookbook/tree/main/tinker_cookbook/recipes/distillation) — Complete implementation including single-teacher and multi-teacher scripts
- [Tinker SDK Documentation](https://tinker-docs.thinkingmachines.ai) — Platform documentation for the remote GPU training API
- [Agarwal et al., "On-Policy Distillation of Language Models: Learning from Self-Generated Mistakes" (ICLR 2024)](https://arxiv.org/abs/2306.13649) — Generalized Knowledge Distillation (GKD) formalization
- [Park et al., "Generalized On-Policy Distillation" (2026)](https://arxiv.org/abs/2505.19828) — Proof that on-policy distillation is a special case of KL-constrained RL
- [Gu et al., "MiniLLM: Knowledge Distillation of Large Language Models" (ICLR 2024)](https://arxiv.org/abs/2306.08543) — Reverse KL minimization for language model distillation
- [DeepMath-103K Dataset](https://huggingface.co/datasets/zwhe99/DeepMath-103K) — Mathematical reasoning prompt dataset used in training
- [Tulu3 SFT Mixture](https://huggingface.co/datasets/allenai/tulu-3-sft-mixture) — General instruction-following dataset used for personalization

---

*Tags: Knowledge Distillation, Reinforcement Learning, LLM Fine-Tuning, On-Policy Training, Machine Learning*
