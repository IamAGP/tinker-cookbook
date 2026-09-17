"""CLI entry point for Legal RL training.

Multi-turn agentic RL where a model learns to answer legal questions
by calling a ChromaDB search tool backed by AWS Bedrock Titan embeddings.

Required env vars:
    TINKER_API_KEY
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION

Example:
    python -m tinker_cookbook.recipes.legal_rl.train

    # With custom ChromaDB path:
    python -m tinker_cookbook.recipes.legal_rl.train chroma_host=localhost chroma_port=8000
"""

import asyncio
import logging
import os
from datetime import datetime

import chz

from tinker_cookbook import checkpoint_utils, cli_utils
from tinker_cookbook.recipes.legal_rl.legal_env import LegalRLDatasetBuilder
from tinker_cookbook.rl.train import Config, KLReferenceConfig, main

logger = logging.getLogger(__name__)


@chz.chz
class CLIConfig:
    """Command-line configuration for Legal RL training."""

    # Model
    model_name: str = "Qwen/Qwen3-4B-Instruct-2507"
    lora_rank: int = 32
    renderer_name: str | None = None
    load_checkpoint_path: str | None = None

    # ChromaDB
    chroma_path: str = "/tmp/legal_chroma_db"
    collection_name: str = "legal_passages"

    # AWS
    aws_region: str = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    # Dataset
    hf_dataset_id: str = "isaacus/legal-rag-qa"
    seed: int = 0

    # Environment
    max_turns: int = 5
    max_trajectory_tokens: int = 32 * 1024
    max_generation_tokens: int = 1024
    format_coef: float = 0.1
    context_overflow_reward: float = -0.1

    # Reward: "judge" = frozen LLM judge (semantic), "exact" = normalized string match
    reward_type: str = "judge"
    judge_model: str = "Qwen/Qwen3-4B-Instruct-2507"
    judge_max_tokens: int = 64
    # Explicit judge renderer for models model_info can't auto-resolve
    # (e.g. nvidia/NVIDIA-Nemotron-3-Ultra-550B → "nemotron3_disable_thinking").
    judge_renderer_name: str | None = None

    # Data split: "train" = train on non-held-out portion (for held-out eval experiments);
    # "all" = use all questions (no held-out set).
    split_role: str = "all"
    eval_frac: float = 0.2

    # Unified mode: True flips to the multi-source pool (US + Australian, ~2,362 QA)
    # + the unified index, in one switch. Overrides chroma_path/collection_name.
    use_unified: bool = False

    # Training hyperparameters
    group_size: int = 4
    groups_per_batch: int = 8
    learning_rate: float = 4e-5
    max_tokens: int = 1024
    temperature: float = 1.0
    kl_penalty_coef: float = 0.0

    # Logging
    log_path: str | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None

    # Eval / checkpointing
    eval_every: int = 0
    save_every: int = 10

    # Service
    base_url: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"
    max_steps: int | None = None


async def cli_main(cli_config: CLIConfig) -> None:
    renderer_name = await checkpoint_utils.resolve_renderer_name_from_checkpoint_or_default_async(
        model_name=cli_config.model_name,
        explicit_renderer_name=cli_config.renderer_name,
        load_checkpoint_path=cli_config.load_checkpoint_path,
        base_url=cli_config.base_url,
    )

    # Unified mode: one switch flips to the multi-source pool + unified index.
    if cli_config.use_unified:
        from tinker_cookbook.recipes.legal_rl.build_unified_index import (
            CHROMA_PATH as UNIFIED_PATH,
            COLLECTION_NAME as UNIFIED_COLLECTION,
        )
        from tinker_cookbook.recipes.legal_rl.legal_data import ALL_SOURCES

        sources = ALL_SOURCES
        chroma_path = UNIFIED_PATH
        collection_name = UNIFIED_COLLECTION
    else:
        sources = None
        chroma_path = cli_config.chroma_path
        collection_name = cli_config.collection_name

    model_name_slug = cli_config.model_name.replace("/", "-")
    run_name = (
        f"legal-rl-{model_name_slug}-{cli_config.lora_rank}rank"
        f"-{cli_config.learning_rate}lr-{cli_config.group_size}group"
        f"-{datetime.now().strftime('%Y-%m-%d-%H-%M')}"
    )
    log_path = cli_config.log_path or f"/tmp/tinker-examples/legal_rl/{run_name}"

    dataset_builder = LegalRLDatasetBuilder(
        model_name_for_tokenizer=cli_config.model_name,
        chroma_path=chroma_path,
        collection_name=collection_name,
        sources=sources,
        aws_region=cli_config.aws_region,
        hf_dataset_id=cli_config.hf_dataset_id,
        batch_size=cli_config.groups_per_batch,
        group_size=cli_config.group_size,
        renderer_name=renderer_name,
        max_turns=cli_config.max_turns,
        format_coef=cli_config.format_coef,
        max_trajectory_tokens=cli_config.max_trajectory_tokens,
        max_generation_tokens=cli_config.max_generation_tokens,
        context_overflow_reward=cli_config.context_overflow_reward,
        seed=cli_config.seed,
        reward_type=cli_config.reward_type,
        judge_model=cli_config.judge_model,
        judge_max_tokens=cli_config.judge_max_tokens,
        judge_renderer_name=cli_config.judge_renderer_name,
        split_role=cli_config.split_role,
        eval_frac=cli_config.eval_frac,
    )

    config = Config(
        model_name=cli_config.model_name,
        recipe_name="recipe_legal_rl",
        renderer_name=renderer_name,
        lora_rank=cli_config.lora_rank,
        learning_rate=cli_config.learning_rate,
        max_tokens=cli_config.max_tokens,
        temperature=cli_config.temperature,
        kl_penalty_coef=cli_config.kl_penalty_coef,
        kl_reference_config=(
            KLReferenceConfig(base_model=cli_config.model_name)
            if cli_config.kl_penalty_coef > 0
            else None
        ),
        dataset_builder=dataset_builder,
        log_path=log_path,
        wandb_project=cli_config.wandb_project,
        wandb_name=cli_config.wandb_name or run_name,
        base_url=cli_config.base_url,
        load_checkpoint_path=cli_config.load_checkpoint_path,
        eval_every=cli_config.eval_every,
        save_every=cli_config.save_every,
        max_steps=cli_config.max_steps,
    )

    cli_utils.check_log_dir(log_path, behavior_if_exists=cli_config.behavior_if_log_dir_exists)
    await main(config)


if __name__ == "__main__":
    cli_config = chz.entrypoint(CLIConfig)
    asyncio.run(cli_main(cli_config))
