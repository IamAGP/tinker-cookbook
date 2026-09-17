"""Baseline inference for Legal RL — run the UNTRAINED base model with the search tool.

Establishes a baseline BEFORE any RL training: shows what the base model does
when given legal questions + the ChromaDB search tool. Prints full transcripts
(model reasoning, tool calls, retrieved passages, final answer, reward) so you
can see baseline behavior — does it use the tool? format correctly? get rewards?

Run AFTER build_index.py has populated the ChromaDB collection.

    python -m tinker_cookbook.recipes.legal_rl.baseline_inference
    python -m tinker_cookbook.recipes.legal_rl.baseline_inference num_questions=10

Required env vars:
    TINKER_API_KEY
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION
"""

import asyncio
import random

import chz
import tinker

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.completers import TinkerTokenCompleter
from tinker_cookbook.recipes.legal_rl.legal_env import (
    LEGAL_TASK_INSTRUCTIONS,
    load_legal_dataset,
)
from tinker_cookbook.recipes.legal_rl.tools import (
    ChromaTool,
    RetrievalConfig,
    TextAnswerReward,
)
from tinker_cookbook.renderers import get_renderer, get_text_content
from tinker_cookbook.rl.rollouts import do_single_rollout
from tinker_cookbook.tool_use import build_agent_tool_env


@chz.chz
class CLIConfig:
    model_name: str = "Qwen/Qwen3-4B-Instruct-2507"
    chroma_path: str = "/tmp/legal_chroma_db"
    collection_name: str = "legal_passages"
    aws_region: str = "us-east-1"
    hf_dataset_id: str = "isaacus/legal-rag-qa"
    num_questions: int = 5
    max_turns: int = 5
    max_tokens: int = 1024
    n_results: int = 3
    format_coef: float = 0.1
    seed: int = 42


def _print_transcript(idx: int, question: str, gold: list[str], history: list, reward: float, metrics: dict):
    print("\n" + "=" * 100)
    print(f"QUESTION {idx}: {question[:300]}")
    print(f"GOLD ANSWER: {gold[0][:300] if gold else '(none)'}")
    print("-" * 100)
    for msg in history:
        role = msg.get("role", "?")
        if role == "system":
            continue  # skip the long system prompt
        if role == "assistant":
            text = get_text_content(msg)
            tool_calls = msg.get("tool_calls") or []
            if text:
                print(f"\n[ASSISTANT]: {text[:800]}")
            for tc in tool_calls:
                print(f"\n[TOOL CALL]: {tc.function.name}({tc.function.arguments[:300]})")
        elif role == "tool":
            content = get_text_content(msg) if isinstance(msg.get("content"), list) else str(msg.get("content", ""))
            print(f"\n[TOOL RESULT]: {content[:500]}")
        elif role == "user":
            # Only print user messages after the first (the first is the question)
            pass
    print("-" * 100)
    print(f"REWARD: {reward:.3f}  |  format={metrics.get('format', 0)}  correct={metrics.get('correct', 0)}")
    print("=" * 100)


async def cli_main(config: CLIConfig) -> None:
    # Load dataset
    print(f"Loading legal QA dataset: {config.hf_dataset_id}")
    data = load_legal_dataset(hf_dataset_id=config.hf_dataset_id)
    rng = random.Random(config.seed)
    rng.shuffle(data)
    data = data[: config.num_questions]
    print(f"Evaluating {len(data)} questions with UNTRAINED base model: {config.model_name}")

    # Renderer
    tokenizer = tokenizer_utils.get_tokenizer(config.model_name)
    renderer_name = model_info.get_recommended_renderer_name(config.model_name)
    print(f"Using renderer: {renderer_name}")
    renderer = get_renderer(renderer_name, tokenizer)

    # Base model sampling client (no checkpoint — untrained)
    service_client = tinker.ServiceClient()
    sampling_client = service_client.create_sampling_client(base_model=config.model_name)
    policy = TinkerTokenCompleter(sampling_client, max_tokens=config.max_tokens)

    # Search tool
    chroma_tool = ChromaTool.build(
        chroma_path=config.chroma_path,
        collection_name=config.collection_name,
        aws_region=config.aws_region,
        retrieval_config=RetrievalConfig(n_results=config.n_results),
    )

    rewards: list[float] = []
    formats: list[float] = []
    corrects: list[float] = []
    turns: list[int] = []

    for idx, datum in enumerate(data, start=1):
        tool_schemas = [chroma_tool.search.to_spec()]
        initial_messages = renderer.create_conversation_prefix_with_tools(
            tools=tool_schemas,
            system_prompt=LEGAL_TASK_INSTRUCTIONS,
        ) + [{"role": "user", "content": datum["question"]}]

        env = build_agent_tool_env(
            renderer=renderer,
            tools=[chroma_tool.search],
            initial_messages=initial_messages,
            reward_fn=TextAnswerReward(gold_answers=datum["answer"], format_coef=config.format_coef),
            max_turns=config.max_turns,
        )

        trajectory = await do_single_rollout(policy, env)

        # Pull readable history + final reward/metrics from the message env
        history = env.message_env.history
        final_reward = 0.0
        final_metrics: dict = {}
        if trajectory.transitions:
            final_reward = trajectory.transitions[-1].reward
            final_metrics = trajectory.transitions[-1].metrics

        _print_transcript(idx, datum["question"], datum["answer"], history, final_reward, final_metrics)

        rewards.append(final_reward)
        formats.append(final_metrics.get("format", 0.0))
        corrects.append(final_metrics.get("correct", 0.0))
        turns.append(len(trajectory.transitions))

    # Baseline summary
    n = len(rewards)
    print("\n\n" + "#" * 100)
    print("BASELINE SUMMARY (untrained base model)")
    print("#" * 100)
    print(f"Questions evaluated:      {n}")
    print(f"Mean reward:              {sum(rewards) / n:.3f}")
    print(f"Format compliance rate:   {sum(formats) / n:.3f}  (fraction with 'Answer:' prefix)")
    print(f"Correctness rate:         {sum(corrects) / n:.3f}  (exact normalized match)")
    print(f"Mean turns per episode:   {sum(turns) / n:.2f}  (>1 means it used the search tool)")
    print("#" * 100)


if __name__ == "__main__":
    config = chz.entrypoint(CLIConfig)
    asyncio.run(cli_main(config))
