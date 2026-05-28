"""CLI entry point for Cricket KG RL training."""

import logging
from datetime import datetime
from pathlib import Path

import chz

_RECIPE_DIR = Path(__file__).parent

from tinker_cookbook import cli_utils, hyperparam_utils, model_info
from tinker_cookbook.recipes.cricket_kg_rl.neo4j_env import CricketKGDatasetBuilder
from tinker_cookbook.rl.train import AsyncConfig, Config, KLReferenceConfig, main

logger = logging.getLogger(__name__)


@chz.chz
class CLIConfig:
    """Command-line configuration for Cricket KG RL training."""

    # Model
    model_name: str = "Qwen/Qwen3-30B-A3B"
    lora_rank: int = 16
    renderer_name: str | None = "qwen3_disable_thinking"
    # Run 6: load from step 10 checkpoint (best from Run 5, before format collapse)
    # load_checkpoint_path: str | None = "tinker://3685091a-8e6d-5820-939d-12f550336650:train:0/weights/000010"
    # Run 7: load from Run 6 step 30 (best stable checkpoint)
    load_checkpoint_path: str | None = "tinker://e6c3eb80-28f6-56d5-88dd-3f35f6dea45a:train:0/weights/000030"
    max_tokens: int = 2048
    temperature: float = 1.0

    # Dataset
    questions_path: str = str(_RECIPE_DIR / "output" / "questions_20260316_164926.json")
    max_questions: int | None = None   # None = all 100 questions
    categories: list[str] | None = None

    # Environment
    max_turns: int = 8
    max_trajectory_tokens: int = 16 * 1024

    # Training hyperparameters
    group_size: int = 4
    groups_per_batch: int = 4
    learning_rate: float | None = None   # None = auto via get_lr
    kl_penalty_coef: float = 0.05        # Run 6: prevent Qwen3 format collapse
    num_substeps: int = 1

    # Logging / eval / checkpoints
    log_path: str | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None
    eval_every: int = 0       # 0 = skip eval (no sandbox spin-up delay)
    save_every: int = 5       # finer granularity to catch best step

    # Service
    base_url: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"

    # Async rollout
    max_steps_off_policy: int | None = None
    # max_steps: int | None = 100        # Run 6: more budget now that cycling works
    max_steps: int | None = 100        # Run 7: double the steps to push season-filter learning


async def cli_main(cli_config: CLIConfig) -> None:
    renderer_name = cli_config.renderer_name or model_info.get_recommended_renderer_name(
        cli_config.model_name
    )

    lr = cli_config.learning_rate or hyperparam_utils.get_lr(cli_config.model_name, is_lora=True)

    model_tag = cli_config.model_name.replace("/", "-")
    run_name = (
        f"cricket-kg-{model_tag}-{cli_config.lora_rank}rank-"
        f"{lr}lr-{cli_config.group_size}group-"
        f"{cli_config.groups_per_batch}batch-"
        f"{datetime.now().strftime('%Y-%m-%d-%H-%M')}"
    )

    log_path = cli_config.log_path or f"/tmp/tinker-examples/cricket_kg_rl/{run_name}"
    wandb_name = cli_config.wandb_name or run_name

    logger.info("Run name: %s", run_name)
    logger.info("Questions path: %s", cli_config.questions_path)
    logger.info("max_questions: %s", cli_config.max_questions)
    logger.info("Learning rate: %s", lr)

    dataset_builder = CricketKGDatasetBuilder(
        questions_path=cli_config.questions_path,
        model_name=cli_config.model_name,
        batch_size=cli_config.groups_per_batch,
        group_size=cli_config.group_size,
        renderer_name=renderer_name,
        max_turns=cli_config.max_turns,
        max_trajectory_tokens=cli_config.max_trajectory_tokens,
        categories=cli_config.categories,
        max_questions=cli_config.max_questions,
        log_path=log_path,
    )

    config = Config(
        learning_rate=lr,
        dataset_builder=dataset_builder,
        model_name=cli_config.model_name,
        lora_rank=cli_config.lora_rank,
        max_tokens=cli_config.max_tokens,
        temperature=cli_config.temperature,
        wandb_project=cli_config.wandb_project,
        wandb_name=wandb_name,
        log_path=log_path,
        base_url=cli_config.base_url,
        load_checkpoint_path=cli_config.load_checkpoint_path,
        kl_penalty_coef=cli_config.kl_penalty_coef,
        kl_reference_config=KLReferenceConfig(base_model=cli_config.model_name)
        if cli_config.kl_penalty_coef > 0
        else None,
        num_substeps=cli_config.num_substeps,
        eval_every=cli_config.eval_every,
        save_every=cli_config.save_every,
        async_config=AsyncConfig(
            max_steps_off_policy=cli_config.max_steps_off_policy,
            groups_per_batch=cli_config.groups_per_batch,
        )
        if cli_config.max_steps_off_policy is not None
        else None,
        max_steps=cli_config.max_steps,
    )

    cli_utils.check_log_dir(log_path, behavior_if_exists=cli_config.behavior_if_log_dir_exists)

    await main(config)
