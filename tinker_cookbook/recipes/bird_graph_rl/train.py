"""RL training entry point for the Cypher agent. Mirrors ``recipes/search_tool/train.py``.

    python -m tinker_cookbook.recipes.bird_graph_rl.train \\
        instances_path=~/bird_rl_runs/datagen_v1/train_instances.jsonl \\
        log_path=~/bird_rl_runs/rl_smoke max_steps=2 batch_size=4 group_size=4
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import chz

from tinker_cookbook import cli_utils
from tinker_cookbook.recipes.bird_graph_rl.rl_env import GraphQADatasetBuilder
from tinker_cookbook.rl import train


@chz.chz
class CLIConfig:
    # Model
    model_name: str = "Qwen/Qwen3.5-9B"
    renderer_name: str | None = None  # None -> model_info recommended default (same as the baseline)
    lora_rank: int = 32
    load_checkpoint_path: str | None = None

    # Data
    instances_path: str = ""
    train_split: str = "train"
    test_split: str | None = "heldout_instance"
    test_size: int = 64
    n_epochs: int = 1

    # Rollouts — identical caps to baseline_eval.py
    group_size: int = 8          # rollouts per question
    batch_size: int = 16         # question groups per iteration
    max_turns: int = 8
    max_tokens: int = 8192
    max_trajectory_tokens: int = 56 * 1024

    # Optimisation
    learning_rate: float = 1e-5
    loss_fn: train.LossFnType = "importance_sampling"
    kl_penalty_coef: float = 0.0
    remove_constant_reward_groups: bool = True
    seed: int = 0

    # Cadence and logging
    eval_every: int = 10
    save_every: int = 10
    max_steps: int | None = None
    log_path: str | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


async def cli_main(cfg: CLIConfig) -> None:
    builder = GraphQADatasetBuilder(
        instances_path=cfg.instances_path,
        model_name_for_tokenizer=cfg.model_name,
        batch_size=cfg.batch_size,
        group_size=cfg.group_size,
        renderer_name=cfg.renderer_name,
        train_split=cfg.train_split,
        test_split=cfg.test_split,
        test_size=cfg.test_size,
        n_epochs=cfg.n_epochs,
        max_turns=cfg.max_turns,
        max_trajectory_tokens=cfg.max_trajectory_tokens,
        seed=cfg.seed,
    )
    run_name = (
        f"bird_graph_{cfg.model_name.lower().replace('/', '-')}_bs{cfg.batch_size}_gs{cfg.group_size}_"
        f"lr{cfg.learning_rate}_rank{cfg.lora_rank}_{datetime.now().strftime('%Y-%m-%d-%H-%M')}"
    )
    log_path = cfg.log_path or f"/tmp/tinker-examples/bird_graph_rl/{run_name}"
    cli_utils.check_log_dir(log_path, behavior_if_exists=cfg.behavior_if_log_dir_exists)

    config = train.Config(
        model_name=cfg.model_name,
        recipe_name="recipe_bird_graph_rl",
        renderer_name=cfg.renderer_name,
        log_path=log_path,
        dataset_builder=builder,
        learning_rate=cfg.learning_rate,
        max_tokens=cfg.max_tokens,
        loss_fn=cfg.loss_fn,
        kl_penalty_coef=cfg.kl_penalty_coef,
        remove_constant_reward_groups=cfg.remove_constant_reward_groups,
        lora_rank=cfg.lora_rank,
        load_checkpoint_path=cfg.load_checkpoint_path,
        eval_every=cfg.eval_every,
        save_every=cfg.save_every,
        wandb_project=cfg.wandb_project,
        wandb_name=cfg.wandb_name or run_name,
        max_steps=cfg.max_steps,
    )
    await train.main(config)


if __name__ == "__main__":
    asyncio.run(cli_main(chz.entrypoint(CLIConfig)))
