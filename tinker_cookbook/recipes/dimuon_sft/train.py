"""
Dimuon vs AdamW: LoRA SFT on text-to-Cypher pairs.

Trains Qwen3-8B (LoRA) to map a natural-language question about the BIRD
codebase_community graph to a single Cypher query, with either AdamW or Dimuon.
The train/eval split is by query structure, so eval queries have shapes the
model never trained on. Eval NLL is computed on the held-out set every
``eval_every`` steps.

Every step writes a timestamped log line and a row to ``metrics.jsonl``; a
resumable state checkpoint is saved at every eval step.

Example:
    python -m tinker_cookbook.recipes.dimuon_sft.train optimizer=dimuon learning_rate=1e-3
"""

import asyncio
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Literal

import chz
import tinker
from tinker import types

from tinker_cookbook import checkpoint_utils, cli_utils, model_info, renderers
from tinker_cookbook.recipes.bird_graph_rl.baseline_eval import SYSTEM_PROMPT as AGENT_SYSTEM_PROMPT
from tinker_cookbook.renderers import Message
from tinker_cookbook.supervised.common import compute_mean_nll
from tinker_cookbook.supervised.data import conversation_to_datum
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook.utils import ml_log

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARN)

DATA_DIR = Path(__file__).parent.parent / "bird_graph_rl" / "datagen" / "out" / "v4"
DATA_FILES = [("questions_v4_train.jsonl", "instances_v4_train.jsonl"),
              ("questions_v4_train_batch2.jsonl", "instances_v4_train_batch2.jsonl")]

# Schema and conventions from the agent prompt; the tool-use instructions are replaced
# because this model answers with one query and no tool calls.
SCHEMA = AGENT_SYSTEM_PROMPT.split("\n\nWork step by step")[0].split("\n\n", 1)[1]
SYSTEM_PROMPT = (
    "You translate questions about a Stack Exchange community (statistics Q&A) into a single "
    "Cypher query over a Neo4j graph.\n\n" + SCHEMA +
    "\n\nReply with exactly one Cypher query that returns what the question asks for, and nothing else."
)


@chz.chz
class Config:
    optimizer: Literal["adamw", "dimuon"]
    learning_rate: float
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    batch_size: int = 32
    n_epochs: int = 3
    eval_fraction: float = 0.2
    eval_every: int = 9
    split_seed: int = 0
    max_steps: int | None = None  # smoke tests
    log_path: str | None = None
    ttl_seconds: int | None = 7 * 24 * 3600


def _cypher_literal(v: object) -> str:
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
    raise TypeError(f"unsupported param type {type(v)}")


def inline_params(cypher: str, params: dict[str, object]) -> str:
    """Replace $name with a literal; longest names first so $date does not eat $date_end."""
    for name in sorted(params, key=len, reverse=True):
        cypher = re.sub(rf"\${re.escape(name)}\b", lambda _m, n=name: _cypher_literal(params[n]), cypher)
    assert "$" not in cypher, cypher
    return cypher


def load_examples() -> list[dict]:
    rows = []
    for qf, inf in DATA_FILES:
        insts = {(r := json.loads(line))["instance_id"]: r
                 for line in (DATA_DIR / inf).read_text().splitlines()}
        for line in (DATA_DIR / qf).read_text().splitlines():
            q = json.loads(line)
            inst = insts[q["instance_id"]]
            user = q["question"] + (f"\n\nHint: {inst['hint']}" if inst.get("hint") else "")
            rows.append({
                "instance_id": q["instance_id"],
                "structure_id": inst["structure_id"],
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": inline_params(inst["cypher"], inst["params"])},
                ],
            })
    return rows


def split_by_structure(rows: list[dict], eval_fraction: float, seed: int) -> tuple[list[dict], list[dict]]:
    structures = sorted({r["structure_id"] for r in rows})
    random.Random(seed).shuffle(structures)
    target = int(len(rows) * eval_fraction)
    held: set[str] = set()
    n = 0
    for s in structures:
        if n >= target:
            break
        held.add(s)
        n += sum(r["structure_id"] == s for r in rows)
    return [r for r in rows if r["structure_id"] not in held], [r for r in rows if r["structure_id"] in held]


async def eval_nll(training_client: tinker.TrainingClient, data: list[tinker.Datum], chunk: int) -> float:
    futures = [await training_client.forward_async(data[i:i + chunk], loss_fn="cross_entropy")
               for i in range(0, len(data), chunk)]
    results = [await f.result_async() for f in futures]
    logprobs = [o["logprobs"] for r in results for o in r.loss_fn_outputs]
    return compute_mean_nll(logprobs, [d.loss_fn_inputs["weights"] for d in data])


async def main(config: Config) -> None:
    log_path = config.log_path or cli_utils.runs_path(
        f"dimuon_sft/{config.optimizer}_lr{config.learning_rate:.2e}")
    ml_logger = ml_log.setup_logging(log_dir=log_path, config=config, do_configure_logging_module=True)

    tokenizer = get_tokenizer(config.model_name)
    renderer = renderers.get_renderer(model_info.get_recommended_renderer_name(config.model_name), tokenizer)

    train_rows, eval_rows = split_by_structure(load_examples(), config.eval_fraction, config.split_seed)
    to_datum = lambda r: conversation_to_datum(  # noqa: E731
        [Message(**m) for m in r["messages"]], renderer, None, renderers.TrainOnWhat.LAST_ASSISTANT_MESSAGE)
    train_data = [to_datum(r) for r in train_rows]
    eval_data = [to_datum(r) for r in eval_rows]
    steps_per_epoch = len(train_data) // config.batch_size
    total_steps = steps_per_epoch * config.n_epochs
    if config.max_steps is not None:
        total_steps = min(total_steps, config.max_steps)
    logger.info(f"train={len(train_data)} eval={len(eval_data)} steps/epoch={steps_per_epoch} total={total_steps} "
                f"train_tokens/epoch={sum(d.model_input.length for d in train_data)} "
                f"eval_tokens={sum(d.model_input.length for d in eval_data)}")

    service_client = tinker.ServiceClient()
    resume = checkpoint_utils.get_last_checkpoint(log_path)
    if resume:
        training_client = await service_client.create_training_client_from_state_with_optimizer_async(
            resume.state_path)
        start_step = resume.batch
        logger.info(f"resuming from step {start_step}")
    else:
        optimizer_config = (types.DimuonOptimizerConfig() if config.optimizer == "dimuon"
                            else types.AdamOptimizerConfig())
        training_client = await service_client.create_lora_training_client_async(
            base_model=config.model_name, rank=config.lora_rank, optimizer=optimizer_config)
        start_step = 0

    for step in range(start_step, total_steps + 1):
        t0 = time.time()
        metrics: dict[str, float] = {}
        if step % config.eval_every == 0 or step == total_steps:
            metrics["eval_nll"] = await eval_nll(training_client, eval_data, config.batch_size)
            if step > 0:
                await checkpoint_utils.save_checkpoint_async(
                    training_client=training_client, name=f"{step:06d}", log_path=log_path,
                    kind="state", loop_state={"batch": step}, ttl_seconds=config.ttl_seconds)
        if step == total_steps:
            ml_logger.log_metrics(metrics=metrics, step=step)
            logger.info(f"[{time.strftime('%H:%M:%S')}] step {step}/{total_steps} {metrics}")
            break

        epoch, idx = divmod(step, steps_per_epoch)
        order = list(range(len(train_data)))
        random.Random(1000 + epoch).shuffle(order)
        batch = [train_data[i] for i in order[idx * config.batch_size:(idx + 1) * config.batch_size]]
        lr = config.learning_rate * (1.0 - step / total_steps)
        optim_params = (types.DimuonParams(learning_rate=lr) if config.optimizer == "dimuon"
                        else types.AdamParams(learning_rate=lr, beta1=0.9, beta2=0.95, eps=1e-8))

        fwd_bwd_future = await training_client.forward_backward_async(batch, loss_fn="cross_entropy")
        optim_future = await training_client.optim_step_async(optim_params)
        fwd_bwd = await fwd_bwd_future.result_async()
        optim = await optim_future.result_async()
        if optim.metrics:
            metrics.update(optim.metrics)
        metrics.update(
            train_nll=compute_mean_nll([o["logprobs"] for o in fwd_bwd.loss_fn_outputs],
                                       [d.loss_fn_inputs["weights"] for d in batch]),
            learning_rate=lr, epoch=epoch,
            num_tokens=sum(d.model_input.length for d in batch),
            time_step=time.time() - t0,
        )
        ml_logger.log_metrics(metrics=metrics, step=step)
        logger.info(f"[{time.strftime('%H:%M:%S')}] step {step}/{total_steps} "
                    f"train_nll={metrics['train_nll']:.4f} eval_nll={metrics.get('eval_nll', float('nan')):.4f} "
                    f"lr={lr:.2e} {metrics['time_step']:.1f}s")

    ml_logger.close()
    logger.info("done")


if __name__ == "__main__":
    asyncio.run(main(chz.entrypoint(Config)))
