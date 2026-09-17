"""RL training (GRPO) for the cricket Cypher agent — Exp R1 (pure RL, no SFT).

Reuses the verified CypherTool + scorer from baseline_eval.py. Trains a small
model (Qwen3.5-9B) to write correct Cypher via a deterministic, verifiable reward
(entity + number match vs execution-verified gold; 0 if no DB query). Gate is the
frozen 228-question eval (run baseline_eval.py on the checkpoint).

Design (source-grounded against the post-merge skills, 2026-06-25):
  - LR ~1e-5 (multi-turn RL guidance — NOT get_lr's ~5e-4 SFT value).
  - on-policy + importance_sampling (clean first experiment).
  - KL anchor 0.05 (anti-collapse, carried from March attempt).
  - remove_constant_reward_groups=True (skip zero-gradient groups; easy tier is
    near-ceiling so many all-correct groups would waste compute).
  - GRPO grouping: each EnvGroupBuilder = ONE question, group_size identical
    rollouts (the dc8eea6 correctness requirement).

Run:
  python -m tinker_cookbook.recipes.cricket_kg_rl.cricket_rl \
      gold_path=/Users/.../cricket-analytics/data/gold/train.jsonl \
      wandb_project=cricket-rl log_path=/Users/.../cricket_rl_runs/r1

Required: TINKER_API_KEY; Aura creds read from the cricket-analytics file.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Sequence
from datetime import datetime

import chz

from tinker_cookbook import checkpoint_utils, cli_utils, model_info, tokenizer_utils
from tinker_cookbook.recipes.cricket_kg_rl.baseline_eval import (
    CREDS_FILE,
    SYSTEM_PROMPT,
    CypherTool,
    score,
)
from tinker_cookbook.renderers import Renderer, get_renderer
from tinker_cookbook.renderers.base import Message
from tinker_cookbook.rl.train import Config, KLReferenceConfig, main
from tinker_cookbook.rl.types import Env, EnvGroupBuilder, RLDataset, RLDatasetBuilder
from tinker_cookbook.tool_use import build_agent_tool_env


def make_reward_fn(gold: dict):
    """Number-gated deterministic reward: 0 if no query, else fraction of gold
    numbers that are correct. Entity match earns NOTHING — this closes the
    "confidently wrong" loophole (the old 0.4*entity gave free reward for echoing
    the question's player names with a bogus number; see Exp G1 held-out gaming).
    number_frac gives a dense signal (partial credit for partially-right answers);
    full credit only when every gold number is right (= a correct query).
    """
    async def reward_fn(history: list[Message]) -> tuple[float, dict[str, float]]:
        s = score(history, gold)
        if s["no_query"]:
            return 0.0, s
        return s["number_frac"], s
    return reward_fn


class CricketEnvGroupBuilder(EnvGroupBuilder):
    """ONE question → group_size identical rollouts (GRPO grouping requirement)."""

    def __init__(
        self,
        gold: dict,
        model_name: str,
        renderer_name: str | None,
        group_size: int,
        ctool: CypherTool,
        max_turns: int,
        max_trajectory_tokens: int,
    ):
        self.gold = gold
        self.model_name = model_name
        self.renderer_name = renderer_name
        self.group_size = group_size
        self.ctool = ctool
        self.max_turns = max_turns
        self.max_trajectory_tokens = max_trajectory_tokens

    async def make_envs(self) -> Sequence[Env]:
        tokenizer = tokenizer_utils.get_tokenizer(self.model_name)
        rname = self.renderer_name or model_info.get_recommended_renderer_name(self.model_name)
        renderer: Renderer = get_renderer(rname, tokenizer)
        msgs = renderer.create_conversation_prefix_with_tools(
            tools=[self.ctool.run_cypher.to_spec()], system_prompt=SYSTEM_PROMPT
        ) + [{"role": "user", "content": self.gold["question"]}]
        reward_fn = make_reward_fn(self.gold)
        return [
            build_agent_tool_env(
                renderer=renderer,
                tools=[self.ctool.run_cypher],
                initial_messages=msgs,
                reward_fn=reward_fn,
                max_turns=self.max_turns,
                max_trajectory_tokens=self.max_trajectory_tokens,
            )
            for _ in range(self.group_size)
        ]

    def logging_tags(self) -> list[str]:
        return [self.gold.get("difficulty", "?")]


class CricketRLDataset(RLDataset):
    def __init__(self, builders: list[CricketEnvGroupBuilder], batch_size: int):
        self.builders = builders
        self.batch_size = batch_size

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        start = index * self.batch_size
        return self.builders[start : start + self.batch_size]

    def __len__(self) -> int:
        return len(self.builders) // self.batch_size


@chz.chz
class CricketRLDatasetBuilder(RLDatasetBuilder):
    model_name_for_tokenizer: str
    gold_path: str
    creds_file: str = CREDS_FILE
    batch_size: int = 8          # groups_per_batch (unique questions per batch)
    group_size: int = 8
    renderer_name: str | None = None
    max_turns: int = 6
    max_trajectory_tokens: int = 32 * 1024
    seed: int = 0

    async def __call__(self) -> tuple[RLDataset, RLDataset | None]:
        ctool = CypherTool(self.creds_file)  # shared, pickle-safe (lazy driver)
        data = [json.loads(l) for l in open(self.gold_path) if l.strip()]
        random.Random(self.seed).shuffle(data)
        builders = [
            CricketEnvGroupBuilder(
                gold=g,
                model_name=self.model_name_for_tokenizer,
                renderer_name=self.renderer_name,
                group_size=self.group_size,
                ctool=ctool,
                max_turns=self.max_turns,
                max_trajectory_tokens=self.max_trajectory_tokens,
            )
            for g in data
        ]
        return CricketRLDataset(builders, self.batch_size), None


@chz.chz
class CLIConfig:
    model_name: str = "Qwen/Qwen3.5-9B"
    lora_rank: int = 32
    renderer_name: str | None = None
    gold_path: str = "/Users/adithyagiridharan/Desktop/PythonProjects/cricket-analytics/data/gold/train.jsonl"
    load_checkpoint_path: str | None = None   # SFT checkpoint state_path → RL warmup (SFT→RL)

    # Hyperparameters (source-grounded: multi-turn RL LR ~1e-5, KL 0.05)
    learning_rate: float = 1e-5
    kl_penalty_coef: float = 0.05
    group_size: int = 8
    groups_per_batch: int = 8
    max_tokens: int = 1024
    max_turns: int = 6
    max_trajectory_tokens: int = 32 * 1024
    temperature: float = 1.0
    num_substeps: int = 1
    loss_fn: str = "importance_sampling"
    remove_constant_reward_groups: bool = True

    eval_every: int = 0
    save_every: int = 10
    max_steps: int | None = 60

    log_path: str | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"
    seed: int = 0


async def cli_main(cfg: CLIConfig) -> None:
    renderer_name = await checkpoint_utils.resolve_renderer_name_from_checkpoint_or_default_async(
        model_name=cfg.model_name, explicit_renderer_name=cfg.renderer_name,
        load_checkpoint_path=cfg.load_checkpoint_path, base_url=None,
    )
    run_name = (
        f"cricket-rl-{cfg.model_name.replace('/', '-')}-{cfg.lora_rank}rank"
        f"-{cfg.learning_rate}lr-{cfg.group_size}x{cfg.groups_per_batch}"
        f"-{datetime.now().strftime('%Y-%m-%d-%H-%M')}"
    )
    log_path = cfg.log_path or f"/tmp/tinker-examples/cricket_rl/{run_name}"

    dataset_builder = CricketRLDatasetBuilder(
        model_name_for_tokenizer=cfg.model_name,
        gold_path=cfg.gold_path,
        batch_size=cfg.groups_per_batch,
        group_size=cfg.group_size,
        renderer_name=renderer_name,
        max_turns=cfg.max_turns,
        max_trajectory_tokens=cfg.max_trajectory_tokens,
        seed=cfg.seed,
    )

    config = Config(
        model_name=cfg.model_name,
        recipe_name="cricket_kg_cypher_rl",
        renderer_name=renderer_name,
        lora_rank=cfg.lora_rank,
        learning_rate=cfg.learning_rate,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        kl_penalty_coef=cfg.kl_penalty_coef,
        kl_reference_config=(
            KLReferenceConfig(base_model=cfg.model_name) if cfg.kl_penalty_coef > 0 else None
        ),
        num_substeps=cfg.num_substeps,
        loss_fn=cfg.loss_fn,
        load_checkpoint_path=cfg.load_checkpoint_path,
        remove_constant_reward_groups=cfg.remove_constant_reward_groups,
        dataset_builder=dataset_builder,
        log_path=log_path,
        wandb_project=cfg.wandb_project,
        wandb_name=cfg.wandb_name or run_name,
        eval_every=cfg.eval_every,
        save_every=cfg.save_every,
        max_steps=cfg.max_steps,
    )
    cli_utils.check_log_dir(log_path, behavior_if_exists=cfg.behavior_if_log_dir_exists)
    await main(config)


if __name__ == "__main__":
    asyncio.run(cli_main(chz.entrypoint(CLIConfig)))
