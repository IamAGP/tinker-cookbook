"""Held-out evaluation for Legal RL (Exp 3).

Runs a model — either the untrained base model OR a trained checkpoint — on the
FROZEN held-out eval split (never seen during training when training uses
split_role="train"), grades each episode with the same frozen LLM judge used in
training, and reports aggregate metrics.

This is the measurement that separates "the policy improved" from "later training
batches were easier". Run it twice — once on the base model, once on the trained
checkpoint — and compare on the SAME held-out questions.

Examples:
    # Baseline (untrained):
    python -m tinker_cookbook.recipes.legal_rl.evaluate

    # A trained checkpoint:
    python -m tinker_cookbook.recipes.legal_rl.evaluate \
        model_path=tinker://<run-id>:train:0/weights/final

Required env vars: TINKER_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
"""

import asyncio
import logging

import chz
import tinker

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.completers import TinkerMessageCompleter, TinkerTokenCompleter
from tinker_cookbook.recipes.legal_rl.legal_env import (
    LEGAL_TASK_INSTRUCTIONS,
    load_legal_dataset,
)
from tinker_cookbook.recipes.legal_rl.tools import (
    ChromaTool,
    LLMJudgeReward,
    RetrievalConfig,
)
from tinker_cookbook.renderers import get_renderer
from tinker_cookbook.rl.rollouts import do_single_rollout
from tinker_cookbook.tool_use import build_agent_tool_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@chz.chz
class CLIConfig:
    # Model under test: leave model_path empty to eval the untrained base model.
    base_model: str = "Qwen/Qwen3-4B-Instruct-2507"
    model_path: str | None = None  # tinker:// checkpoint; None = untrained base

    # Frozen eval split (must match training's eval_frac to be the true held-out set)
    eval_frac: float = 0.2
    hf_dataset_id: str = "isaacus/legal-rag-qa"

    # Unified mode: eval on the multi-source held-out split + unified index.
    # Must match the training run's setting to be the true held-out set.
    use_unified: bool = False

    # Infra
    chroma_path: str = "/tmp/legal_chroma_db"
    collection_name: str = "legal_passages"
    aws_region: str = "us-east-1"
    n_results: int = 3

    # Grounding probe: when True, the search tool returns nothing. Compare
    # correctness with vs without retrieval — if it barely drops, the model is
    # answering from memory, not the tool.
    disable_retrieval: bool = False

    # Judge (must match training judge for comparable scores)
    judge_model: str = "Qwen/Qwen3-4B-Instruct-2507"
    judge_max_tokens: int = 64
    # Explicit judge renderer; needed for models model_info can't auto-resolve
    # (e.g. nvidia/NVIDIA-Nemotron-3-Ultra-550B → "nemotron3"). None = auto.
    judge_renderer_name: str | None = None

    # Rollout
    max_turns: int = 5
    max_tokens: int = 1024
    max_trajectory_tokens: int = 32 * 1024  # overflow guard (matches training)
    context_overflow_reward: float = -0.1
    concurrency: int = 8

    # Limit eval to the first N held-out questions (0 = all). Use for smoke tests.
    sample: int = 0
    sample_seed: int = 7


async def cli_main(config: CLIConfig) -> None:
    if config.use_unified:
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
        chroma_path = config.chroma_path
        collection_name = config.collection_name

    data = load_legal_dataset(
        hf_dataset_id=config.hf_dataset_id,
        split_role="eval",
        eval_frac=config.eval_frac,
        sources=sources,
    )
    if config.sample and config.sample < len(data):
        import random as _random

        _random.Random(config.sample_seed).shuffle(data)
        data = data[: config.sample]
    label = config.model_path or f"{config.base_model} (untrained base)"
    logger.info(f"Held-out eval: {len(data)} questions | model: {label}")

    service_client = tinker.ServiceClient()

    # Policy under test
    if config.model_path:
        sampling_client = service_client.create_sampling_client(model_path=config.model_path)
    else:
        sampling_client = service_client.create_sampling_client(base_model=config.base_model)
    policy = TinkerTokenCompleter(sampling_client, max_tokens=config.max_tokens)

    tokenizer = tokenizer_utils.get_tokenizer(config.base_model)
    renderer_name = model_info.get_recommended_renderer_name(config.base_model)
    renderer = get_renderer(renderer_name, tokenizer)

    # Frozen judge (same as training)
    judge_sampling_client = service_client.create_sampling_client(base_model=config.judge_model)
    judge_tokenizer = tokenizer_utils.get_tokenizer(config.judge_model)
    judge_rname = config.judge_renderer_name or model_info.get_recommended_renderer_name(
        config.judge_model
    )
    judge_renderer = get_renderer(judge_rname, judge_tokenizer)
    judge_completer = TinkerMessageCompleter(
        judge_sampling_client, judge_renderer, max_tokens=config.judge_max_tokens, temperature=0.0
    )

    # Search tool
    chroma_tool = ChromaTool.build(
        chroma_path=chroma_path,
        collection_name=collection_name,
        aws_region=config.aws_region,
        retrieval_config=RetrievalConfig(n_results=config.n_results),
        disabled=config.disable_retrieval,
    )

    semaphore = asyncio.Semaphore(config.concurrency)

    async def eval_one(datum) -> dict:
        tool_schemas = [chroma_tool.search.to_spec()]
        initial_messages = renderer.create_conversation_prefix_with_tools(
            tools=tool_schemas, system_prompt=LEGAL_TASK_INSTRUCTIONS
        ) + [{"role": "user", "content": datum["question"]}]
        env = build_agent_tool_env(
            renderer=renderer,
            tools=[chroma_tool.search],
            initial_messages=initial_messages,
            reward_fn=LLMJudgeReward(gold_answers=datum["answer"], judge_completer=judge_completer),
            max_turns=config.max_turns,
        )
        async with semaphore:
            traj = await do_single_rollout(policy, env)
        m = traj.transitions[-1].metrics if traj.transitions else {}
        r = traj.transitions[-1].reward if traj.transitions else 0.0
        return {
            "reward": r,
            "judge_score": m.get("judge_score", 0.0),
            "correct": m.get("correct", 0.0),
            "format": m.get("format", 0.0),
            "turns": len(traj.transitions),
        }

    results = await asyncio.gather(*[eval_one(d) for d in data])
    n = len(results)

    def mean(key: str) -> float:
        return sum(r[key] for r in results) / n

    print("\n" + "=" * 80)
    print("HELD-OUT EVALUATION RESULTS")
    print("=" * 80)
    print(f"Model:            {label}")
    print(f"Retrieval:        {'DISABLED (grounding probe)' if config.disable_retrieval else 'enabled'}")
    print(f"Eval questions:   {n}  (frozen held-out split, eval_frac={config.eval_frac})")
    print("-" * 80)
    print(f"  mean judge_score (reward): {mean('judge_score'):.3f}")
    print(f"  correctness rate:          {mean('correct'):.3f}")
    print(f"  format compliance:         {mean('format'):.3f}")
    print(f"  mean turns/episode:        {mean('turns'):.2f}")
    print("=" * 80)
    print("\nCompare this against the other model (base vs checkpoint) on the SAME split.")


if __name__ == "__main__":
    config = chz.entrypoint(CLIConfig)
    asyncio.run(cli_main(config))
