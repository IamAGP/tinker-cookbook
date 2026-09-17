"""SFT warmup on demonstration trajectories for the cricket Cypher agent.

Consumes her hard-trajectory JSONL (one full agent loop per line) and SFTs the 9B
to seed the hard ball-by-ball query patterns that pure RL (Exp R1) could not
durably learn. Output checkpoint then feeds RL via cricket_rl.py's
`load_checkpoint_path` (SFT→RL warmup).

Her JSONL line format (NO system prompt — we prepend the canonical one here):
  {"id","difficulty","type","messages":[user, assistant(reason+tool_call), tool, assistant(final)]}

Two pipeline subtleties handled here (verified against the renderer):
  1. tool_calls arrive as plain dicts from JSON → coerced to ToolCall.
  2. The Qwen3.5 renderer lacks the "extension property", so training a multi-
     assistant conversation with ALL_ASSISTANT_MESSAGES would give earlier
     assistant turns an OOD prefix. Fix: split each trajectory into one example
     PER assistant message (each conversation truncated to end at that assistant
     message) and train with LAST_ASSISTANT_MESSAGE. This keeps every trained
     turn's prefix identical to what generation would produce.

SFT LR = get_lr (~4.7e-4 for 9B LoRA) — the *SFT* value (NOT RL's 1e-5).

Run:
  python -m tinker_cookbook.recipes.cricket_kg_rl.cricket_sft \
      jsonl_path=/Users/.../cricket-analytics/data/sft/hard_trajectories.jsonl \
      wandb_project=cricket-rl log_path=/Users/.../cricket_rl_runs/sft1
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime

import chz
import tinker

from tinker_cookbook import checkpoint_utils, cli_utils, hyperparam_utils, model_info, tokenizer_utils
from tinker_cookbook.recipes.cricket_kg_rl.baseline_eval import SYSTEM_PROMPT
from tinker_cookbook.renderers import TrainOnWhat, get_renderer
from tinker_cookbook.renderers.base import Message, ToolCall
from tinker_cookbook.supervised import train as sft_train
from tinker_cookbook.supervised.data import conversation_to_datum
from tinker_cookbook.supervised.types import SupervisedDataset, SupervisedDatasetBuilder


def _coerce(raw: dict) -> Message:
    """Convert a JSON-loaded message into a renderer Message (tool_calls→ToolCall)."""
    m: Message = {"role": raw["role"], "content": raw.get("content", "")}
    if raw.get("tool_calls"):
        m["tool_calls"] = [ToolCall.model_validate(tc) for tc in raw["tool_calls"]]
    if "tool_call_id" in raw:
        m["tool_call_id"] = raw["tool_call_id"]
    if "name" in raw:
        m["name"] = raw["name"]
    return m


def _split_by_assistant(messages: list[Message]) -> list[list[Message]]:
    """One sub-conversation per assistant message, each ending at that message
    (so LAST_ASSISTANT_MESSAGE trains exactly it, with a generation-faithful prefix)."""
    return [messages[: i + 1] for i, m in enumerate(messages) if m["role"] == "assistant"]


class _ListDataset(SupervisedDataset):
    def __init__(self, data: list[tinker.Datum], batch_size: int):
        self.data = data
        self.batch_size = batch_size
        self._order = list(range(len(data)))

    def set_epoch(self, seed: int = 0):
        rng = random.Random(seed)
        self._order = list(range(len(self.data)))
        rng.shuffle(self._order)

    def __len__(self) -> int:
        return len(self.data) // self.batch_size

    def get_batch(self, index: int) -> list[tinker.Datum]:
        idxs = self._order[index * self.batch_size : (index + 1) * self.batch_size]
        return [self.data[i] for i in idxs]


@chz.chz
class CricketSFTDatasetBuilder(SupervisedDatasetBuilder):
    jsonl_paths: list[str]                    # one or more tier files (hard/medium/easy)
    model_name: str
    renderer_name: str | None = None
    max_length: int = 4096
    batch_size: int = 32
    difficulty_filter: str | None = None      # None = keep all difficulties (mixed)

    def __call__(self) -> tuple[SupervisedDataset, SupervisedDataset | None]:
        tok = tokenizer_utils.get_tokenizer(self.model_name)
        rname = self.renderer_name or model_info.get_recommended_renderer_name(self.model_name)
        renderer = get_renderer(rname, tok)

        rows: list[dict] = []
        for p in self.jsonl_paths:
            rows += [json.loads(l) for l in open(p) if l.strip()]
        if self.difficulty_filter:
            rows = [r for r in rows if r.get("difficulty") == self.difficulty_filter]

        from collections import Counter
        tier_counts = Counter(r.get("difficulty", "?") for r in rows)

        data: list[tinker.Datum] = []
        n_traj = 0
        for r in rows:
            convo: list[Message] = [{"role": "system", "content": SYSTEM_PROMPT}]
            convo += [_coerce(m) for m in r["messages"]]
            for sub in _split_by_assistant(convo):
                data.append(
                    conversation_to_datum(
                        sub, renderer, self.max_length,
                        train_on_what=TrainOnWhat.LAST_ASSISTANT_MESSAGE,
                    )
                )
            n_traj += 1
        print(f"SFT dataset: {n_traj} trajectories ({dict(tier_counts)}) -> {len(data)} "
              f"training examples (per-assistant split), batch_size={self.batch_size}, "
              f"{len(data) // self.batch_size} batches/epoch")
        return _ListDataset(data, self.batch_size), None


SFT_DIR = "/Users/adithyagiridharan/Desktop/PythonProjects/cricket-analytics/data/sft"


@chz.chz
class CLIConfig:
    # None -> mixed run: [hard, medium, easy]. Pass a subset to train on fewer tiers.
    jsonl_paths: list[str] | None = None
    model_name: str = "Qwen/Qwen3.5-9B"
    renderer_name: str | None = None
    lora_rank: int = 32
    learning_rate: float | None = None   # None -> get_lr (SFT value)
    lr_fraction: float = 1.0             # scale LR (e.g. 0.5 for milder mixed SFT)
    max_length: int = 4096
    batch_size: int = 32
    num_epochs: int = 2                  # milder than S1's 3 (which over-memorized)
    difficulty_filter: str | None = None
    save_every: int = 20
    log_path: str | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


async def cli_main(cfg: CLIConfig) -> None:
    renderer_name = await checkpoint_utils.resolve_renderer_name_from_checkpoint_or_default_async(
        model_name=cfg.model_name, explicit_renderer_name=cfg.renderer_name,
        load_checkpoint_path=None, base_url=None,
    )
    base_lr = cfg.learning_rate if cfg.learning_rate is not None else hyperparam_utils.get_lr(cfg.model_name)
    lr = base_lr * cfg.lr_fraction
    jsonl_paths = cfg.jsonl_paths or [
        f"{SFT_DIR}/hard_trajectories.jsonl",
        f"{SFT_DIR}/medium_trajectories.jsonl",
        f"{SFT_DIR}/easy_trajectories.jsonl",
        f"{SFT_DIR}/diverse_trajectories.jsonl",
    ]
    run_name = (
        f"cricket-sft-{cfg.model_name.replace('/', '-')}-{cfg.lora_rank}rank-{lr:.1e}lr"
        f"-{datetime.now().strftime('%Y-%m-%d-%H-%M')}"
    )
    log_path = cfg.log_path or f"/tmp/tinker-examples/cricket_sft/{run_name}"

    dataset_builder = CricketSFTDatasetBuilder(
        jsonl_paths=jsonl_paths, model_name=cfg.model_name, renderer_name=renderer_name,
        max_length=cfg.max_length, batch_size=cfg.batch_size, difficulty_filter=cfg.difficulty_filter,
    )
    config = sft_train.Config(
        log_path=log_path,
        model_name=cfg.model_name,
        recipe_name="cricket_kg_cypher_sft",
        renderer_name=renderer_name,
        dataset_builder=dataset_builder,
        learning_rate=lr,
        num_epochs=cfg.num_epochs,
        lora_rank=cfg.lora_rank,
        save_every=cfg.save_every,
        wandb_project=cfg.wandb_project,
        wandb_name=cfg.wandb_name or run_name,
    )
    cli_utils.check_log_dir(log_path, behavior_if_exists=cfg.behavior_if_log_dir_exists)
    await sft_train.main(config)


if __name__ == "__main__":
    asyncio.run(cli_main(chz.entrypoint(CLIConfig)))
