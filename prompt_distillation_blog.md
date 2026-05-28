# Prompt Distillation: Compiling LLM System Prompts Into Model Weights

*A two-stage fine-tuning technique eliminates thousand-token system prompts while preserving their exact behavior — reducing inference costs by 95%.*

Every production LLM deployment ships with a system prompt. These prompts encode business logic, classification rules, formatting constraints, and edge-case handling in natural language. A well-engineered system prompt for a moderately complex task easily spans 500 to 1,500 tokens. Those tokens travel with every single API request, unchanged, adding identical overhead to each call regardless of the input.

The economics become stark at scale. A classification service handling one million requests per day with a 1,000-token system prompt processes over one billion redundant input tokens daily. The prompt never changes. The model reads the same instructions a million times. Every token of that prompt adds latency to time-to-first-token and cost to the inference bill.

**Prompt distillation** — also known as **context distillation** — offers a direct solution. First described by Askell et al. (2021) and formalized by Snell et al. (2022), the technique fine-tunes a model to internalize a system prompt's behavior into its weights. After training, the model produces identical outputs without ever receiving the prompt. The instructions are no longer text that must be processed at runtime. They become learned parameters.

## The Two-Stage Distillation Process

The technique operates through a teacher-student paradigm with an intentional information asymmetry.

An analogy clarifies the mechanism: consider the difference between a chef who consults a detailed recipe card for every dish and one who has cooked the dish so many times the steps are automatic. Both produce the same output. The second chef simply no longer needs the card. Prompt distillation manufactures that expertise through supervised training rather than repetition.

Formally, a teacher model `f_T` generates responses using the full prompt `P` concatenated with each input query `q_i`, producing labeled pairs: `r_i = f_T([P, q_i])`. A student model `f_S` then trains to minimize the loss between its output given only `q_i` and the teacher's output: `ℓ(f_S(q_i), f_T([P, q_i]))`. The student never observes the prompt. It learns the prompt's behavioral effect purely from input-output examples.

This asymmetry is the core insight. The prompt's knowledge transfers from text (runtime overhead) to weights (zero-cost at inference).

---

## The Classification Challenge: A Working Implementation

The [Tinker Cookbook](https://github.com/thinkingmachines/tinker-cookbook), an open-source fine-tuning recipe library built on the Tinker SDK, provides a complete prompt distillation implementation. The example task is multilingual language classification: given a line of text, output its ISO 639-1 language code from a closed set of 13 languages (ar, de, el, en, es, fr, hi, ru, tr, ur, vi, zh) or "ot" for other.

Language classification appears straightforward until edge cases surface. The word "Bonjour" in isolation could indicate French text or an English speaker using a common loanword. A line like `print("Привет мир")` contains Russian embedded in Python syntax. Pure numeric strings like "3.14159" carry no linguistic signal. Sentences such as "José went to the café" blend Spanish proper nouns with French loanwords in English syntax. Each of these cases requires explicit disambiguation rules.

The Tinker Cookbook's teacher prompt addresses this complexity across approximately 75 lines. It specifies script-based detection shortcuts (Devanagari maps to Hindi, Cyrillic to Russian, Greek script to Greek), Latin-script heuristic chains using diacritics and stop-word frequency, special handling for code with embedded natural-language strings, named entity context resolution, and ambiguity fallback rules. This prompt represents significant engineering effort — and it must accompany every classification request unless distilled.

## Stage One: Teacher-Generated Training Data

The data generation pipeline sends 2,100 multilingual sentences through the teacher model — `Qwen/Qwen3-30B-A3B`, a 30-billion parameter mixture-of-experts model — with the full classification prompt attached. The following code, simplified from the repository's `create_data.py`, illustrates the core logic:

```python
async def classify_sentence(sentence, sampling_client, renderer):
    messages = [
        {"role": "user",
         "content": CLASSIFICATION_PROMPT + sentence}
    ]

    prompt = renderer.build_generation_prompt(messages)
    response = await sampling_client.sample(
        prompt,
        temperature=0.15,
        max_tokens=1000,
    )

    match = re.search(r"Final Answer:\s*(\w+)", response_text)
    label = match.group(1).lower()

    return {
        "messages": [
            {"role": "user", "content": sentence},
            {"role": "assistant", "content": label}
        ]
    }
```

The critical operation occurs in the return statement. The saved output retains only the raw sentence and the two-character label. The 75-line classification prompt is deliberately excluded. The resulting JSONL file contains entries like:

```json
{"messages": [{"role": "user", "content": "Và anh ấy nói, Mẹ ơi, con về rồi"}, {"role": "assistant", "content": "vi"}]}
{"messages": [{"role": "user", "content": "他说，妈妈，我回来了"}, {"role": "assistant", "content": "zh"}]}
{"messages": [{"role": "user", "content": "And he said, Mama, I'm home"}, {"role": "assistant", "content": "en"}]}
```

No prompt. No reasoning chain. No classification rules. The student's entire curriculum consists of these bare input-output pairs. The teacher's temperature of 0.15 ensures consistent, decisive labels — low enough for classification reliability, high enough to avoid degenerate repetition.

## Stage Two: Supervised Fine-Tuning Without the Prompt

The student is the same base architecture — `Qwen/Qwen3-30B-A3B` — fine-tuned using **LoRA** (Low-Rank Adaptation) at rank 32. LoRA freezes the original model weights and introduces small trainable matrices into each attention layer, modifying roughly 0.1% of total parameters. This approach prevents catastrophic forgetting of the model's general capabilities while efficiently learning the new classification behavior.

The training configuration reflects standard supervised fine-tuning practices:

- **Loss:** cross-entropy (next-token prediction)
- **Learning rate:** 1e-4 with linear decay to zero
- **Optimizer:** Adam (β₁=0.9, β₂=0.95, ε=1e-8)
- **Epochs:** 4 passes over the dataset
- **Batch size:** 128 examples per gradient step
- **Loss masking:** assistant tokens only

The loss masking deserves attention. The `train_on_what=ALL_ASSISTANT_MESSAGES` setting assigns weight 1.0 to assistant response tokens and weight 0.0 to user input tokens. The model observes the full conversation as context but receives gradient signal exclusively from predicting the label. This constraint focuses the optimization entirely on the classification mapping rather than on reproducing user text.

The dataset reshuffles at each epoch boundary using the epoch index as a random seed. This ensures different batch compositions across passes, reducing the risk of overfitting to ordering artifacts within the relatively small 2,100-example dataset.

## The Data Pipeline: From Conversations to Gradient Signals

The transformation from JSONL conversations to training-ready tensors passes through several well-defined stages, each implemented as a composable abstraction in the Tinker Cookbook's supervised learning module.

The `FromConversationFileBuilder` class loads the JSONL file and wraps it in a HuggingFace `Dataset` object. When the training loop requests a batch, each conversation passes through `conversation_to_datum()`, which delegates to two lower-level operations.

The **renderer** tokenizes the conversation using the model's native chat template — Qwen3 format with its specific special tokens — and produces a `ModelInput` (the token sequence) alongside a `weights` tensor (1.0 for assistant tokens, 0.0 elsewhere). The `datum_from_model_input_weights` function then performs the next-token prediction transformation: it truncates to `max_length` if necessary, right-shifts the input (removing the last token), left-shifts the targets (removing the first token), and aligns the weight mask with the target positions.

The output is a `tinker.Datum` containing three aligned sequences: input tokens the model will process, target tokens it must predict, and per-token weights controlling which predictions contribute to the loss. This three-part structure cleanly separates the model's input from its optimization signal.

## Pipelined Execution for Hardware Efficiency

The Tinker Cookbook's training loop employs a pipeline strategy that overlaps GPU computation with CPU-side data preparation. While the accelerator processes step N's forward pass, backward pass, and optimizer update, the CPU prepares step N+1's batch and submits it to the request queue:

```
submit_batch(step=0)  ->  [GPU: forward + backward + optimizer]
submit_batch(step=1)  ->  [GPU: queued]
finish_batch(step=0)  <-  [results ready, log metrics]
submit_batch(step=2)  ->  [GPU: queued]
finish_batch(step=1)  <-  ...
```

This overlapping prevents the GPU from idling between steps. Evaluations execute before each training step at configured intervals (every 5 steps in this recipe), snapshotting the current weights to ensure evaluation measures a consistent checkpoint rather than weights in mid-update.

The entire training run — 2,100 examples, batch size 128, 4 epochs — completes in approximately 65 gradient steps. On Tinker's managed infrastructure, this represents minutes of wall-clock time.

## Quantifying the Efficiency Gains

The arithmetic of prompt distillation is straightforward. With the full system prompt, each request carries approximately 1,100 input tokens: the ~1,000-token prompt plus the input sentence. After distillation, each request carries only the sentence — roughly 50 tokens.

That represents a **95% reduction in per-request input tokens**. At one million daily requests, processing drops from 1.1 billion input tokens to 50 million. The latency improvement compounds this cost saving: fewer input tokens means shorter time-to-first-token, directly improving user-facing response times.

The training investment to achieve these savings is minimal — a single fine-tuning run of ~65 steps with LoRA on a 30B-parameter model. The amortization period is measured in hours of production traffic, not weeks.

## When Distillation Fits and When It Does Not

Prompt distillation delivers the strongest returns under specific conditions. The system prompt must be **stable** — retraining after every prompt edit negates the efficiency gains. The prompt should be **long relative to the input**, creating meaningful per-request overhead. The deployment should involve **high request volume** where token costs compound. And the task should be **well-defined enough** that input-output pairs capture the prompt's full behavioral specification.

The technique is less appropriate when prompts change frequently, when runtime flexibility to adjust behavior through prompt editing is required, when the task demands explicit chain-of-thought reasoning that benefits from in-context instructions, or when insufficient training examples exist to cover the prompt's behavioral surface area.

## Broader Applications

The Tinker Cookbook uses language classification as a pedagogical example, but the underlying pattern generalizes to any task with a stable, lengthy system prompt. Content moderation systems can distill detailed policy documents into model weights. Data extraction pipelines can internalize schema-aware parsing instructions. Style transfer applications can absorb brand voice guidelines. Tool routing logic and summarization criteria are equally viable candidates.

The recipe remains consistent across domains: engineer the prompt, generate labeled data with a teacher, strip the prompt from the training set, and fine-tune the student on bare input-output pairs.

## Conclusion

Prompt distillation occupies a precise niche in the LLM deployment toolkit — the intersection of stable behavioral requirements and high-volume inference. The technique converts natural language instructions from a runtime cost into a one-time training cost, achieving dramatic efficiency improvements through standard supervised fine-tuning rather than exotic training objectives.

The deeper architectural significance lies in what the technique reveals about prompt-model interaction. A system prompt does not teach a capable base model new knowledge. It activates existing capabilities along a specific behavioral axis. Distillation simply makes that activation permanent, shifting it from the context window to the weight space. The model does not learn to classify languages through training. It learns to classify languages *by default*.

As system prompts grow longer and more complex across the industry — driven by the push toward more reliable, precisely specified model behavior — the overhead they impose at inference time will continue to compound. Prompt distillation offers a principled escape valve: compile the instructions once, deploy without them forever.

---

**Sources and References**

- [Tinker Cookbook — Prompt Distillation Recipe](https://github.com/thinkingmachines/tinker-cookbook/tree/main/tinker_cookbook/recipes/prompt_distillation) — Complete implementation including data generation and training scripts
- [Tinker SDK Documentation](https://tinker-docs.thinkingmachines.ai) — Platform documentation for the remote GPU training API
- [Askell et al., "A General Language Assistant as a Laboratory for Alignment" (2021)](https://arxiv.org/abs/2112.00861) — Original description of context distillation for alignment
- [Snell et al., "Learning by Distilling Context" (2022)](https://arxiv.org/abs/2209.15189) — Formalization of prompt distillation as a fine-tuning technique
- [Hu et al., "LoRA: Low-Rank Adaptation of Large Language Models" (2021)](https://arxiv.org/abs/2106.09685) — The parameter-efficient fine-tuning method used in the training stage

---

*Tags: LLM Fine-Tuning, Prompt Engineering, Machine Learning, Natural Language Processing, Model Optimization*
