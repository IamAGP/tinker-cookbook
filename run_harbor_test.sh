#!/bin/bash
# Harbor RL - minimal test run (3 steps, just to see the loop work)
# Model: Qwen/Qwen3-8B (small, cheap - we're watching infra not training quality)
# To use Kimi-K2-Thinking (the real model), swap model_name below

set -e

echo "======================================"
echo "  Harbor RL Test Run (3 steps only)"
echo "======================================"

uv run python -m tinker_cookbook.recipes.harbor_rl.launch_terminal_bench \
    model_name="Qwen/Qwen3-8B" \
    renderer_name="qwen3_disable_thinking" \
    group_size=2 \
    groups_per_batch=2 \
    learning_rate=1e-4 \
    lora_rank=8 \
    max_tokens=2048 \
    max_steps=3 \
    eval_every=0 \
    sandbox_timeout=120 \
    2>&1 | tee harbor_run.log

echo ""
echo "======================================"
echo "  Done! Full log saved to harbor_run.log"
echo "======================================"
