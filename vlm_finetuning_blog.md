# Fine-Tuning Vision-Language Models: Turning a General-Purpose VLM Into a Domain-Specific Image Classifier

*A LoRA-based supervised fine-tuning pipeline adapts billion-parameter vision-language models for image classification, achieving high accuracy from as few as one example per class.*

Vision-language models understand images. They can describe a photograph, answer questions about a diagram, and reason about spatial relationships in a scene. What they cannot do out of the box is classify an image into one of 101 specific object categories with the single-word precision a production system requires. A general-purpose VLM asked "What is this?" will produce a conversational paragraph. A domain classifier needs to produce "accordion" or "dalmatian" — nothing more.

The gap between conversational visual understanding and structured classification represents a common deployment challenge. Custom vision models trained from scratch require massive labeled datasets and significant compute. Traditional transfer learning with CNNs or Vision Transformers lacks the flexible multi-modal interface that makes VLMs valuable. The question becomes whether the visual understanding already embedded in a billion-parameter VLM can be redirected toward a precise, domain-specific classification task with minimal training data.

**VLM fine-tuning** for classification answers this question directly. Using LoRA (Low-Rank Adaptation) to modify a fraction of the model's parameters, supervised fine-tuning reshapes the VLM's output distribution from open-ended conversation to deterministic label prediction. The [Tinker Cookbook](https://github.com/thinkingmachines/tinker-cookbook), an open-source fine-tuning recipe library built on the Tinker SDK, provides a complete implementation that demonstrates this technique across four standard benchmarks.

---

## The Multi-Modal Training Pipeline

Training a VLM classifier differs from text-only supervised fine-tuning in one fundamental respect: the input contains two modalities — images and text — that must be tokenized through different mechanisms and then interleaved into a single sequence.

An analogy from linguistics clarifies the challenge. Consider translating a document that mixes prose with embedded photographs. The text passes through a dictionary-based lookup, producing a sequence of word tokens. Each photograph passes through a separate perceptual encoding, producing a fixed-length sequence of visual tokens. The translator must interleave these two token streams into a coherent sequence where the visual tokens appear exactly where the photographs appeared in the original document. VLM rendering solves this same interleaving problem at the token level.

The Tinker Cookbook's `Qwen3VLRenderer` handles this transformation automatically. Each image in the input message passes through three stages: pixel-level preprocessing by the model's native image processor, conversion to JPEG bytes wrapped in an `ImageChunk`, and framing with special vision delimiter tokens. The renderer produces a `ModelInput` containing interleaved `EncodedTextChunk` and `ImageChunk` objects — a single sequence that the VLM's attention mechanism processes as a unified stream.

```python
# Wrapping images with vision tokens (from Qwen3VLRenderer)
chunks: list[ImagePart | TextPart] = []
for content_chunk in base_parts:
    if content_chunk["type"] == "image":
        chunks.append(TextPart(type="text", text="<|vision_start|>"))

    chunks.append(content_chunk)

    if content_chunk["type"] == "image":
        chunks.append(TextPart(type="text", text="<|vision_end|>"))
```

The `<|vision_start|>` and `<|vision_end|>` tokens tell the model where visual information begins and ends within the sequence. Between these delimiters, the image processor determines the exact number of visual tokens based on the image's dimensions — a 480-pixel image might encode to several hundred tokens, while a smaller image produces fewer. The `image_to_chunk` function calculates this count using the model's patch-based encoding:

```python
def image_to_chunk(image_or_str, image_processor):
    # Convert to RGB JPEG bytes
    pil_image = pil_image.convert("RGB")
    img_byte_arr = io.BytesIO()
    pil_image.save(img_byte_arr, format="JPEG")

    # Calculate expected tokens from image dimensions
    width, height = pil_image.size
    num_image_tokens = (
        image_processor.get_number_of_image_patches(height, width, images_kwargs={})
        // image_processor.merge_size ** 2
    )

    return tinker.types.ImageChunk(
        data=img_byte_arr.getvalue(),
        format="jpeg",
        expected_tokens=num_image_tokens,
    )
```

This token-counting step is essential. The Tinker backend uses `expected_tokens` to validate that the image will encode to the anticipated sequence length, catching dimension mismatches before they corrupt the training batch.

## Constructing Classification Examples

The data pipeline converts raw image-label pairs from HuggingFace datasets into multi-modal training conversations. Each example becomes a two-message exchange: a user message containing the image and a question, and an assistant message containing the class label.

The `ClassifierDataset` class in the Tinker Cookbook implements this transformation:

```python
user_parts: list[ContentPart] = [
    ImagePart(type="image", image=pil_image),
    TextPart(type="text", text="What is the name of the subject in this photo?"),
]

assistant_parts: list[ContentPart] = [
    TextPart(type="text", text=f"The subject in this photo is: {class_label_name}\n"),
]

messages = [
    Message(role="user", content=user_parts),
    Message(role="assistant", content=assistant_parts),
]
```

The user message contains a structured content list — an `ImagePart` holding the PIL image followed by a `TextPart` with the classification prompt. The assistant message contains only a `TextPart` with the ground-truth label embedded in a natural-language template. This conversational framing leverages the VLM's pre-trained understanding of multi-turn dialogue rather than requiring a separate classification head.

Two data augmentation steps improve generalization from small datasets. Images resize to a maximum dimension of 480 pixels (preserving aspect ratio) to standardize input resolution. A horizontal flip applies with 50% probability during training, doubling the effective visual diversity. The test set receives no augmentation — images resize but never flip.

The pipeline supports four standard benchmarks out of the box: Caltech-101 (101 object categories), Oxford Flowers 102 (102 flower species), Oxford-IIIT Pets (37 pet breeds), and Stanford Cars (196 car models). Each dataset builder handles HuggingFace-specific column mappings and class label encoding, presenting a uniform interface to the training loop.

---

## Loss Masking: Training Only on Labels

The loss configuration determines which tokens receive gradient signal during training. Setting `train_on_what=LAST_ASSISTANT_MESSAGE` assigns weight 1.0 exclusively to the assistant's response tokens and weight 0.0 to everything else — the system prompt, the user's image tokens, the question text, and the vision delimiters.

This selective masking has a precise purpose. The model observes the full multi-modal context (image + question) to build its internal representation, but receives gradient updates only from predicting the class label. The visual encoder and language model jointly process the image, but the optimization signal focuses entirely on mapping that visual representation to the correct category name. Without this masking, the model would waste capacity learning to reproduce the user's question and vision tokens — information that is identical across every example.

## Few-Shot Classification

The recipe includes explicit support for few-shot learning through the `examples_per_class` parameter. When set, the dataset builder samples exactly N examples from each class, creating a balanced miniature training set.

```python
def _sample_per_class(self, dataset):
    rng = random.Random(self.config.subset_seed)

    class_indices: dict[int, list[int]] = defaultdict(list)
    for idx, label in enumerate(dataset[self.config.label_column_name]):
        class_indices[label].append(idx)

    selected_indices: list[int] = []
    for label in sorted(class_indices.keys()):
        indices = class_indices[label]
        rng.shuffle(indices)
        selected_indices.extend(indices[: self.config.examples_per_class])

    return dataset.select(selected_indices)
```

With 1-shot learning on Caltech-101, the training set contains exactly 101 examples — one per category. To extract sufficient gradient signal from this minimal data, the recipe multiplies `num_repeats` proportionally: 16x for 1-shot, 8x for 2-shot, 4x for 4-shot. Each repeat shuffles the data with a different seed, ensuring varied batch composition across passes despite the tiny dataset size.

This scaling reflects a general principle of few-shot VLM fine-tuning: the model's pre-trained visual features already contain the discriminative information needed for classification. Fine-tuning does not teach the model to see — it teaches the model to name what it already sees.

## Evaluation: Sampling-Based Accuracy

Evaluation operates through the same multi-modal rendering pipeline as training but follows a generative protocol rather than a loss-computation protocol. The `ClassifierEvaluator` constructs a generation prompt with the image and question, then samples the model's completion:

```python
def build_generation_prompt(self, example):
    content_parts = [
        ImagePart(type="image", image=pil_image),
        TextPart(type="text", text="What is the name of the subject in this photo?"),
    ]
    messages = [Message(role="user", content=content_parts)]

    return self.renderer.build_generation_prompt(
        messages=messages, role="assistant",
        prefill="The subject in this photo is:"
    )
```

The `prefill` parameter pre-populates the assistant's response up to the colon, constraining the model to complete only the class name. The evaluator then extracts the predicted class by splitting on ":" and comparing against the ground truth. Evaluation runs with temperature 0.0 (greedy decoding) for deterministic predictions.

Parallel evaluation through `asyncio.Semaphore`-bounded concurrent requests processes up to 128 test examples simultaneously, keeping the evaluation phase efficient even on large test sets.

---

## Training Configuration

The default configuration balances training efficiency with classification accuracy:

- **Model:** Qwen/Qwen3-VL-235B-A22B-Instruct (235B MoE vision-language model)
- **LoRA rank:** 32
- **Learning rate:** 5e-4 with cosine decay
- **Epochs:** 3
- **Batch size:** 32
- **Max sequence length:** 8,192 tokens
- **Max image size:** 480 pixels
- **Augmentation:** 50% horizontal flip
- **Loss masking:** last assistant message only
- **Evaluation:** every 20 steps, 128 test examples

The learning rate of 5e-4 is notably higher than the 1e-5 typical of preference learning (DPO, RLHF) or the 1e-4 of standard text SFT. LoRA fine-tuning requires higher learning rates because the trainable parameter count is orders of magnitude smaller than the full model — the rank-32 adaptation modifies roughly 0.1% of total parameters. The cosine schedule decays this rate smoothly to zero, preventing late-training oscillation.

The model choice — Qwen3-VL-235B-A22B-Instruct — deserves attention. This is a mixture-of-experts architecture where only 22 billion parameters activate per token despite 235 billion total parameters. The MoE design provides the visual understanding capacity of a very large model at the inference cost of a much smaller one. The Tinker Cookbook also supports the smaller Qwen3-VL-30B-A3B-Instruct for faster experimentation.

## What Changes Between Text-Only and Vision Fine-Tuning

The architectural differences between text-only and vision-language fine-tuning concentrate in three areas.

**Content representation.** Text-only messages use plain strings. VLM messages use structured content lists containing `TextPart` and `ImagePart` objects. This list-based format allows arbitrary interleaving of modalities within a single message.

**Token encoding.** Text-only training produces sequences of `EncodedTextChunk` objects. VLM training produces mixed sequences of `EncodedTextChunk` and `ImageChunk` objects. The `ImageChunk` carries raw JPEG bytes plus an `expected_tokens` count, while `EncodedTextChunk` carries pre-tokenized integer sequences. The Tinker backend handles the heterogeneous encoding transparently.

**Truncation behavior.** When a training example exceeds `max_length`, text chunks truncate gracefully by dropping trailing tokens. Image chunks cannot be partially truncated — an image either fits entirely within the sequence budget or is removed completely. This all-or-nothing property makes the `max_length` parameter (8,192 by default) more consequential for VLM training than for text-only workloads.

---

## Practical Guidance

Several implementation details from the Tinker Cookbook apply broadly to VLM fine-tuning beyond the specific classification use case.

**Image resolution directly affects training cost.** The `max_image_size` parameter (default 480) controls the number of visual tokens per example. A 480-pixel image might produce several hundred tokens; a 960-pixel image could produce four times as many. Since attention scales quadratically with sequence length, doubling image resolution roughly quadruples the per-example compute cost. Start small and increase resolution only if classification accuracy plateaus.

**The conversational framing matters.** Wrapping classification in a natural Q&A format ("What is the name of the subject in this photo?" / "The subject in this photo is: dalmatian") leverages the VLM's pre-trained conversational abilities rather than fighting against them. The `prefill` mechanism during evaluation constrains the output format without additional training.

**Few-shot results scale predictably.** The sweep infrastructure (`sweep.py`) supports systematic evaluation across shot counts (1, 2, 4, 8, 16 examples per class) and multiple random seeds. Because VLMs bring substantial pre-trained visual knowledge, even 1-shot fine-tuning can produce meaningful classification accuracy — the model already knows what a dalmatian looks like; it only needs to learn which label to output.

## Conclusion

VLM fine-tuning for classification occupies a specific engineering niche — the intersection of rich visual understanding and constrained output requirements. The technique does not build visual perception from scratch. It redirects the perception a VLM already possesses toward a precise, application-specific output format, using LoRA to minimize both the training cost and the risk of degrading the model's broader capabilities.

The deeper significance lies in the multi-modal rendering architecture that makes this possible. The interleaving of `ImageChunk` and `EncodedTextChunk` objects into a single `ModelInput`, mediated by vision delimiter tokens and model-specific image processors, provides a clean abstraction over the substantial complexity of mixed-modality sequence construction. This same pipeline extends beyond classification to any task requiring structured visual reasoning — visual question answering, document understanding, medical image analysis, or satellite imagery interpretation.

The VLM does not learn to see during fine-tuning. It learns what to say about what it already sees.

---

**Sources and References**

- [Tinker Cookbook — VLM Classifier Recipe](https://github.com/thinkingmachines/tinker-cookbook/tree/main/tinker_cookbook/recipes/vlm_classifier) — Complete implementation including training, evaluation, and sweep scripts
- [Tinker SDK Documentation](https://tinker-docs.thinkingmachines.ai) — Platform documentation for the remote GPU training API
- [Tinker Cookbook — Rendering: Vision Inputs](https://tinker-docs.thinkingmachines.ai/rendering#vision-inputs) — Multi-modal rendering documentation
- [Hu et al., "LoRA: Low-Rank Adaptation of Large Language Models" (2021)](https://arxiv.org/abs/2106.09685) — The parameter-efficient fine-tuning method used in training
- [Qwen3-VL Model Documentation](https://qwen.readthedocs.io/en/latest/) — Architecture and chat template specifications
- [Caltech-101 Dataset](https://data.caltech.edu/records/mzrjq-6wc02) — Object recognition benchmark used as the default classification task
- [VLM Fine-Tuning Survey (2025)](https://www.sciencedirect.com/science/article/abs/pii/S1566253525006955) — Comprehensive survey of VLM adaptation techniques

---

*Tags: Vision-Language Models, Fine-Tuning, Image Classification, LoRA, Multi-Modal Learning, Machine Learning*
