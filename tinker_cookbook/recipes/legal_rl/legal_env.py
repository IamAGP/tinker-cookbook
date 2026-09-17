"""Legal RL environment — multi-turn tool-use RL for legal QA.

The agent receives a legal question and must answer it by calling
the search tool to retrieve relevant passages from a ChromaDB index,
then submitting a final answer with the "Answer:" prefix.

Mirrors search_tool/search_env.py with ChromaDB + Titan replacing ChromaDB + Gemini.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TypedDict

import chz
import tinker
from datasets import load_dataset

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.completers import MessageCompleter, TinkerMessageCompleter
from tinker_cookbook.recipes.legal_rl.tools import (
    ChromaTool,
    LLMJudgeReward,
    RetrievalConfig,
    TextAnswerReward,
)
from tinker_cookbook.renderers import get_renderer
from tinker_cookbook.renderers.base import Message, Renderer
from tinker_cookbook.rl.types import Env, EnvGroupBuilder, RLDataset, RLDatasetBuilder
from tinker_cookbook.tool_use import build_agent_tool_env

LEGAL_TASK_INSTRUCTIONS = """You are an expert legal assistant with access to a legal document search tool.

Here are instructions for how to answer a legal question:
1. Think step by step about what information you need to answer the question.
2. Call the search tool with relevant queries to retrieve legal passages.
3. Think step by step again after reviewing the results. If you have enough information, proceed to answer.
4. Otherwise, search again with more specific queries based on what you found.
5. Include your final answer after the "Answer:" prefix. Be concise and precise.

Example:
"What is the limitation period for filing a contract dispute claim?"

1. Think: I need to find the statute of limitations for contract disputes.
2. <tool_call>{"name": "search", "arguments": {"query_list": ["statute of limitations contract dispute"]}}</tool_call>
3. Think: The results mention a 3-year period under the Limitation Act. Let me verify.
4. <tool_call>{"name": "search", "arguments": {"query_list": ["Limitation Act contract claim period years"]}}</tool_call>
5. Answer: 3 years from the date the cause of action arose.
"""


class LegalDatum(TypedDict):
    question: str
    answer: list[str]


# Fixed seed for the train/eval split. INDEPENDENT of the training data-shuffle
# seed so the held-out eval set is stable across all runs and configs.
SPLIT_SEED = 12345


def load_legal_dataset(
    hf_dataset_id: str = "isaacus/legal-rag-qa",
    split_role: str = "all",
    eval_frac: float = 0.2,
    sources: list[str] | None = None,
) -> list[LegalDatum]:
    """Load legal QA pairs, with a deterministic train/eval split.

    Two modes:
      - sources is None: single-source legacy path (the 'qa' config of
        `hf_dataset_id`, default isaacus/legal-rag-qa, 138 pairs). Kept for
        reproducing earlier experiments.
      - sources is a list (e.g. legal_data.ALL_SOURCES): UNIFIED multi-source
        pool via legal_data.load_qa (US + Australian, ~2,362 pairs).

    Args:
        split_role: "train" (1-eval_frac), "eval" (eval_frac), or "all".
        eval_frac: fraction held out for eval. Deterministic (SPLIT_SEED), so
            train/eval never overlap and are stable across runs regardless of the
            training seed.
        sources: when given, load the unified multi-source pool.
    """
    data: list[LegalDatum] = []
    if sources is not None:
        from tinker_cookbook.recipes.legal_rl.legal_data import load_qa

        for item in load_qa(sources):
            data.append({"question": item["question"], "answer": item["answer"]})
    else:
        ds = load_dataset(hf_dataset_id, "qa", split="test")
        for row in ds:
            answer = row["answer"]
            answers = [answer] if isinstance(answer, str) else list(answer)
            data.append({"question": row["question"], "answer": answers})

    if split_role == "all":
        return data

    # Deterministic shuffle + split, fixed seed independent of training seed.
    indices = list(range(len(data)))
    random.Random(SPLIT_SEED).shuffle(indices)
    n_eval = max(1, int(round(len(data) * eval_frac)))
    eval_idx = set(indices[:n_eval])

    if split_role == "eval":
        return [data[i] for i in range(len(data)) if i in eval_idx]
    elif split_role == "train":
        return [data[i] for i in range(len(data)) if i not in eval_idx]
    else:
        raise ValueError(f"split_role must be 'train', 'eval', or 'all'; got {split_role!r}")


def _initial_messages(
    datum: LegalDatum,
    renderer: Renderer,
    chroma_tool: ChromaTool,
) -> list[Message]:
    tool_schemas = [chroma_tool.search.to_spec()]
    prefix = renderer.create_conversation_prefix_with_tools(
        tools=tool_schemas,
        system_prompt=LEGAL_TASK_INSTRUCTIONS,
    )
    return prefix + [{"role": "user", "content": datum["question"]}]


class LegalEnvGroupBuilder(EnvGroupBuilder):
    """EnvGroupBuilder that creates legal search environments with a shared ChromaTool."""

    def __init__(
        self,
        datum: LegalDatum,
        model_name: str,
        renderer_name: str | None,
        max_turns: int,
        group_size: int,
        chroma_tool: ChromaTool,
        format_coef: float = 0.1,
        max_trajectory_tokens: int = 32 * 1024,
        max_generation_tokens: int | None = None,
        context_overflow_reward: float = -0.1,
        judge_completer: MessageCompleter | None = None,
    ):
        self.datum = datum
        self.model_name = model_name
        self.renderer_name = renderer_name
        self.max_turns = max_turns
        self.group_size = group_size
        self.chroma_tool = chroma_tool
        self.format_coef = format_coef
        self.max_trajectory_tokens = max_trajectory_tokens
        self.max_generation_tokens = max_generation_tokens
        self.context_overflow_reward = context_overflow_reward
        self.judge_completer = judge_completer

    async def make_envs(self) -> Sequence[Env]:
        tokenizer = tokenizer_utils.get_tokenizer(self.model_name)
        renderer_name = self.renderer_name or model_info.get_recommended_renderer_name(
            self.model_name
        )
        renderer = get_renderer(renderer_name, tokenizer)
        initial_messages = _initial_messages(self.datum, renderer, self.chroma_tool)
        if self.judge_completer is not None:
            reward_fn = LLMJudgeReward(
                gold_answers=self.datum["answer"],
                judge_completer=self.judge_completer,
            )
        else:
            reward_fn = TextAnswerReward(
                gold_answers=self.datum["answer"],
                format_coef=self.format_coef,
            )
        return [
            build_agent_tool_env(
                renderer=renderer,
                tools=[self.chroma_tool.search],
                initial_messages=initial_messages,
                reward_fn=reward_fn,
                max_turns=self.max_turns,
                max_trajectory_tokens=self.max_trajectory_tokens,
                max_generation_tokens=self.max_generation_tokens,
                context_overflow_reward=self.context_overflow_reward,
            )
            for _ in range(self.group_size)
        ]

    def logging_tags(self) -> list[str]:
        return ["legal"]


class LegalRLDataset(RLDataset):
    def __init__(
        self,
        env_group_builders: list[LegalEnvGroupBuilder],
        batch_size: int,
    ):
        self.env_group_builders = env_group_builders
        self.batch_size = batch_size

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        start = index * self.batch_size
        end = start + self.batch_size
        return self.env_group_builders[start:end]

    def __len__(self) -> int:
        return len(self.env_group_builders) // self.batch_size


@chz.chz
class LegalRLDatasetBuilder(RLDatasetBuilder):
    """Build an RL dataset over legal QA tasks with ChromaTool + Titan embeddings."""

    model_name_for_tokenizer: str
    chroma_path: str = "/tmp/legal_chroma_db"
    collection_name: str = "legal_passages"
    aws_region: str = "us-east-1"
    retrieval_config: RetrievalConfig = RetrievalConfig()
    hf_dataset_id: str = "isaacus/legal-rag-qa"
    batch_size: int = 8
    group_size: int = 4
    renderer_name: str | None = None
    max_turns: int = 5
    format_coef: float = 0.1
    max_trajectory_tokens: int = 32 * 1024
    max_generation_tokens: int | None = None
    context_overflow_reward: float = -0.1
    seed: int = 0
    # Reward: "judge" uses a frozen LLM judge; "exact" uses normalized string match.
    reward_type: str = "judge"
    judge_model: str = "Qwen/Qwen3-4B-Instruct-2507"
    judge_max_tokens: int = 64
    # Explicit judge renderer for models model_info can't auto-resolve
    # (e.g. nvidia/NVIDIA-Nemotron-3-Ultra-550B → "nemotron3_disable_thinking").
    judge_renderer_name: str | None = None
    # Data split: "train" trains on the non-held-out portion; "all" uses everything.
    split_role: str = "all"
    eval_frac: float = 0.2
    # Data sources: None = single-source legacy (hf_dataset_id). A list (e.g.
    # legal_data.ALL_SOURCES) = unified multi-source pool.
    sources: list[str] | None = None

    async def __call__(self) -> tuple[RLDataset, RLDataset | None]:
        chroma_tool = ChromaTool.build(
            chroma_path=self.chroma_path,
            collection_name=self.collection_name,
            aws_region=self.aws_region,
            retrieval_config=self.retrieval_config,
        )

        # Build the frozen judge (base model, no checkpoint) if requested.
        judge_completer: MessageCompleter | None = None
        if self.reward_type == "judge":
            service_client = tinker.ServiceClient()
            judge_sampling_client = service_client.create_sampling_client(
                base_model=self.judge_model
            )
            judge_tokenizer = tokenizer_utils.get_tokenizer(self.judge_model)
            judge_rname = self.judge_renderer_name or model_info.get_recommended_renderer_name(
                self.judge_model
            )
            judge_renderer = get_renderer(judge_rname, judge_tokenizer)
            judge_completer = TinkerMessageCompleter(
                judge_sampling_client,
                judge_renderer,
                max_tokens=self.judge_max_tokens,
                temperature=0.0,  # deterministic grading
            )

        data = load_legal_dataset(
            hf_dataset_id=self.hf_dataset_id,
            split_role=self.split_role,
            eval_frac=self.eval_frac,
            sources=self.sources,
        )
        rng = random.Random(self.seed)
        rng.shuffle(data)

        env_builders = [
            LegalEnvGroupBuilder(
                datum=datum,
                model_name=self.model_name_for_tokenizer,
                renderer_name=self.renderer_name,
                max_turns=self.max_turns,
                group_size=self.group_size,
                chroma_tool=chroma_tool,
                format_coef=self.format_coef,
                max_trajectory_tokens=self.max_trajectory_tokens,
                max_generation_tokens=self.max_generation_tokens,
                context_overflow_reward=self.context_overflow_reward,
                judge_completer=judge_completer,
            )
            for datum in data
        ]
        dataset = LegalRLDataset(
            env_group_builders=env_builders,
            batch_size=self.batch_size,
        )
        return dataset, None
