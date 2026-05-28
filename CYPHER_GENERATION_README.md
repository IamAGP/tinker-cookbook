# Cypher Generation Fine-Tuning

This guide walks you through fine-tuning a model to generate Neo4j Cypher queries from natural language questions.

## 📊 Dataset Overview

- **Source**: `results.csv` (270 samples from BuzzOverflow Q&A platform)
- **Training**: 250 samples
- **Testing**: 20 samples
- **Domain**: Stack Overflow-like questions → Neo4j Cypher queries

### Query Complexity Distribution:
- Medium: 81 samples
- Complex: 73 samples
- Simple: 62 samples
- Multi-hop: 54 samples

## 🚀 Quick Start

### Step 1: Prepare the Data

```bash
python create_cypher_data.py
```

This will:
- Read `results.csv`
- Split into 250 train + 20 test samples
- Create JSONL files at:
  - `/tmp/tinker-datasets/cypher_train.jsonl`
  - `/tmp/tinker-datasets/cypher_test.jsonl`

### Step 2: Train the Model

```bash
python train_cypher.py
```

**Default configuration:**
- Model: `Qwen/Qwen3-8B`
- Batch size: 32
- Learning rate: 1e-4
- Epochs: 4
- LoRA rank: 32
- Max length: 8192 tokens

**Custom configuration:**
```bash
# Adjust hyperparameters
python train_cypher.py num_epochs=6 learning_rate=2e-4 batch_size=16

# Use different model
python train_cypher.py model_name="Qwen/Qwen3-30B-A3B"

# Resume from checkpoint
python train_cypher.py load_checkpoint_path="tinker://abc123/state/checkpoint"
```

**Training will:**
- Create logs at `/tmp/tinker-cookbook/cypher_generation/<run_name>/`
- Save checkpoints every 20 steps
- Evaluate every 5 steps
- Save final checkpoint at the end

### Step 3: Test the Fine-Tuned Model

Once training completes, you'll get a checkpoint path like:
```
tinker://your-run-id/sampler_weights/final
```

Test it:
```bash
python test_cypher_model.py tinker://your-run-id/sampler_weights/final
```

This will:
- Load the 20 test samples
- Generate Cypher queries for each question
- Calculate exact match and similarity metrics
- Show detailed results

## 📁 Files Created

1. **`create_cypher_data.py`** - Converts CSV to JSONL format
2. **`train_cypher.py`** - Training script with configuration
3. **`test_cypher_model.py`** - Testing/evaluation script

## 🔍 Example Data Format

**Input (Natural Language):**
```
What are the top 5 tags with the most questions?
```

**Output (Cypher Query):**
```cypher
MATCH (q:Question)-[:TAGGED]->(t:Tag)
RETURN t.name, count(q) AS question_count
ORDER BY question_count DESC
LIMIT 5
```

## 📊 Expected Results

After training on 250 samples for 4 epochs, you should see:
- Good performance on simple/medium queries
- Reasonable performance on complex queries
- Learning of common patterns (MATCH, RETURN, ORDER BY, LIMIT)

## 🎯 Next Steps

### Option 1: Improve Training
- Increase epochs: `num_epochs=8`
- Adjust learning rate: `learning_rate=5e-5`
- Increase LoRA rank: `lora_rank=64`

### Option 2: True Prompt Distillation
Add a comprehensive system prompt with schema information and examples, then:
1. Use teacher model to generate queries WITH the prompt
2. Train student to replicate WITHOUT the prompt
3. Compare results

### Option 3: Add Schema Information
Update the training data to include graph schema in a system message:
```json
{
  "messages": [
    {
      "role": "system",
      "content": "Graph schema: User(display_name, reputation), Question(score, upVotes), Tag(name)..."
    },
    {
      "role": "user",
      "content": "Find top users"
    },
    {
      "role": "assistant",
      "content": "MATCH (u:User)..."
    }
  ]
}
```

## 🐛 Troubleshooting

**Data file not found:**
```bash
# Make sure you ran the data creation script
python create_cypher_data.py
```

**Checkpoint not loading:**
- Verify the checkpoint path starts with `tinker://`
- Check that the training run completed successfully

**Poor results:**
- Try training for more epochs
- Increase the LoRA rank
- Check if test examples are similar to training examples

## 📝 Notes

- This is **supervised fine-tuning**, not true prompt distillation
- The model learns from your validated Cypher queries
- No long prompt is compressed into model weights (that's the next experiment!)
- Current approach: direct question → Cypher mapping

---

**Happy training! 🚀**
