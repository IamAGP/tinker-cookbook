"""
Live inference smoke test — ask the model a cricket question and watch it tool-call.

This is NOT training. It runs one episode of inference so you can see:
  - Does the model call get_schema?
  - Does it write valid Cypher?
  - Does it call final_answer with a sensible answer?

Usage:
    uv run python -m tinker_cookbook.recipes.cricket_kg_rl.smoke_inference

Requires:
    TINKER_API_KEY in .env
    NEO4J_URI / NEO4J_PASSWORD in .env
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import IO

import tinker
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

# Silence Neo4j's noisy "propertyTypes format will change" notifications
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)

OUTPUT_DIR = Path(__file__).parent / "output"


class _Tee:
    """Write to multiple file-like objects simultaneously."""

    def __init__(self, *files: IO[str]) -> None:
        self._files = files

    def write(self, data: str) -> int:
        for f in self._files:
            f.write(data)
        return len(data)

    def flush(self) -> None:
        for f in self._files:
            f.flush()

from tinker_cookbook.completers import TinkerTokenCompleter
import tinker_cookbook.recipes.cricket_kg_rl.neo4j_env as _neo4j_env
from tinker_cookbook.recipes.cricket_kg_rl.neo4j_env import (
    SYSTEM_PROMPT,
    Neo4jTools,
    make_reward_fn,
)
from tinker_cookbook.renderers import get_renderer
from tinker_cookbook.rl.rollouts import do_single_rollout
from tinker_cookbook.tool_use import build_agent_tool_env
from tinker_cookbook.tokenizer_utils import get_tokenizer

load_dotenv()

# ── Tee: write all Rich output to timestamped + fixed "latest" log files ──────
OUTPUT_DIR.mkdir(exist_ok=True)
_log_path = OUTPUT_DIR / f"smoke_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
_latest_path = OUTPUT_DIR / "smoke_latest.log"
_log_file = open(_log_path, "w", encoding="utf-8")      # noqa: SIM115
_latest_file = open(_latest_path, "w", encoding="utf-8")  # noqa: SIM115
console = Console(file=_Tee(sys.stdout, _log_file, _latest_file))
console.print(f"[dim]Logging to: {_log_path}[/dim]")
console.print(f"[dim]Latest log: {_latest_path}[/dim]")

# ── Model config ──────────────────────────────────────────────────────────────
# Thinking OFF — we want to verify raw tool-calling ability first
MODEL_NAME = "Qwen/Qwen3-30B-A3B"
RENDERER_NAME = "qwen3_disable_thinking"
MAX_TOKENS = 2048
MAX_TURNS = 6

# ── Test question + known answer ─────────────────────────────────────────────
# QUESTION = "Who scored the most runs in IPL 2019?"
# GROUND_TRUTH = "DA Warner with 692 runs"


# ---------------------------------------------------------------------------
# Pretty-print the trajectory
# ---------------------------------------------------------------------------

def _print_trajectory(trajectory, tokenizer) -> None:
    console.print("\n")
    console.rule("[bold cyan]EPISODE TRANSCRIPT")
    console.print(f"[dim]Total transitions in trajectory: {len(trajectory.transitions)}[/dim]\n")

    prev_chunk_count = 0

    for i, transition in enumerate(trajectory.transitions):
        ob_chunks = getattr(transition.ob, "chunks", []) or []

        # ── Tool result: decode the NEW chunks added since last turn ──────────
        new_chunks = ob_chunks[prev_chunk_count:]
        if new_chunks:
            tool_result_tokens: list[int] = []
            for chunk in new_chunks:
                if getattr(chunk, "type", None) == "encoded_text":
                    tool_result_tokens.extend(chunk.tokens)
            if tool_result_tokens:
                tool_result_text = tokenizer.decode(tool_result_tokens)
                console.print(Panel(
                    tool_result_text,
                    title=f"[blue]Turn {i+1} — TOOL RESULT ({len(tool_result_tokens)} tokens, {len(new_chunks)} new chunk(s))",
                    border_style="blue",
                ))
        prev_chunk_count = len(ob_chunks)

        # ── Model action: decode what the model generated this turn ───────────
        n_tokens = len(transition.ac.tokens) if transition.ac.tokens else 0
        console.print(f"[dim]Turn {i+1}: model generating {n_tokens} action tokens...[/dim]")

        raw_text = tokenizer.decode(transition.ac.tokens)
        console.print(Panel(
            raw_text,
            title=f"[yellow]Turn {i+1} — MODEL OUTPUT ({n_tokens} tokens)",
            border_style="yellow",
        ))

        console.print(f"  [dim]Observation total: {len(ob_chunks)} chunk(s) in ModelInput[/dim]")

        if transition.reward != 0.0:
            console.print(f"  [bold green]Reward:[/bold green] {transition.reward}")
        else:
            console.print(f"  [dim]Reward: {transition.reward}[/dim]")

        if transition.metrics:
            console.print(f"  [bold]Metrics:[/bold] {transition.metrics}")

        if transition.logs:
            console.print(f"  [dim]Logs:[/dim] {transition.logs}")

        console.print()  # blank line between turns

    console.rule("[bold cyan]END")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_smoke_test(sampling_client: tinker.SamplingClient, question: str) -> None:
    console.print(Panel(
        f"[bold]Model:[/bold] {MODEL_NAME}\n"
        f"[bold]Renderer:[/bold] {RENDERER_NAME} (thinking OFF)\n"
        f"[bold]Question:[/bold] {question}",
        title="[bold cyan]Cricket KG Inference Smoke Test",
        border_style="cyan",
    ))

    # ── Neo4j connection ───────────────────────────────────────────────────────
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    console.print(f"[dim]NEO4J_URI: {uri}[/dim]")
    if not uri or not password:
        console.print("[red]ERROR: NEO4J_URI and NEO4J_PASSWORD must be set in .env")
        return

    console.print("[dim]Creating Neo4j async driver...[/dim]")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    console.print("[green]Neo4j driver created.[/green]")

    # ── Policy ─────────────────────────────────────────────────────────────────
    console.print(f"[dim]Creating TinkerTokenCompleter (max_tokens={MAX_TOKENS})...[/dim]")
    policy = TinkerTokenCompleter(sampling_client, max_tokens=MAX_TOKENS)
    console.print("[green]Policy ready.[/green]")

    # ── Renderer + tokenizer ───────────────────────────────────────────────────
    console.print(f"[dim]Loading tokenizer for {MODEL_NAME}...[/dim]")
    tokenizer = get_tokenizer(MODEL_NAME)
    console.print(f"[green]Tokenizer loaded. Vocab size: {tokenizer.vocab_size}[/green]")

    console.print(f"[dim]Building renderer '{RENDERER_NAME}'...[/dim]")
    renderer = get_renderer(RENDERER_NAME, tokenizer)
    console.print(f"[green]Renderer ready: {type(renderer).__name__}[/green]")

    # ── Tools ──────────────────────────────────────────────────────────────────
    # Clear schema cache so it re-fetches with the latest formatting
    _neo4j_env._SCHEMA_CACHE = None
    console.print("[dim]Instantiating Neo4jTools (get_schema / run_cypher / final_answer)...[/dim]")
    neo4j_tools = Neo4jTools(driver=driver)
    tool_specs = [
        neo4j_tools.get_schema.to_spec(),
        neo4j_tools.run_cypher.to_spec(),
        neo4j_tools.final_answer.to_spec(),
    ]
    console.print(f"[green]Tool specs built: {tool_specs}[/green]")

    # ── Initial messages ───────────────────────────────────────────────────────
    console.print("[dim]Building initial message sequence...[/dim]")
    initial_messages = renderer.create_conversation_prefix_with_tools(
        tools=tool_specs,
        system_prompt=SYSTEM_PROMPT,
    ) + [{"role": "user", "content": question}]
    console.print(f"[dim]Initial messages: {len(initial_messages)} message(s)[/dim]")
    for j, msg in enumerate(initial_messages):
        role = msg.get("role", "?")
        content_preview = str(msg.get("content", ""))[:120].replace("\n", " ")
        console.print(f"  [dim][{j}] role={role}  content={content_preview!r}...[/dim]")

    # ── Environment ────────────────────────────────────────────────────────────
    console.print("[dim]Building AgentToolEnv...[/dim]")
    env = build_agent_tool_env(
        renderer=renderer,
        tools=[neo4j_tools.get_schema, neo4j_tools.run_cypher, neo4j_tools.final_answer],
        initial_messages=initial_messages,
        reward_fn=make_reward_fn(question=question, ground_truth="", conv_log_path=None),
        max_turns=MAX_TURNS,
    )
    console.print(f"[green]Env ready: {type(env).__name__}[/green]")

    # ── Rollout ────────────────────────────────────────────────────────────────
    console.print("\n[bold]Running episode (do_single_rollout)...[/bold]\n")
    trajectory = await do_single_rollout(policy, env)
    console.print(f"[green]Rollout complete. Transitions: {len(trajectory.transitions)}[/green]")

    _print_trajectory(trajectory, tokenizer)

    # ── Summary ────────────────────────────────────────────────────────────────
    total_reward = sum(t.reward for t in trajectory.transitions)
    n_turns = len(trajectory.transitions)
    console.print(Panel(
        f"Turns: {n_turns}\n"
        f"Final reward: {total_reward}\n"
        f"Result: {'[bold green]PASS' if total_reward > 0 else '[bold red]FAIL'}",
        title="[bold]Summary",
    ))

    console.print("[dim]Closing Neo4j driver...[/dim]")
    await driver.close()
    console.print("[dim]Done.[/dim]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cricket KG inference smoke test")
    parser.add_argument(
        "--checkpoint",
        type=str,
        # default=None,  # Run 5 step 10: tinker://3685091a-8e6d-5820-939d-12f550336650:train:0/sampler_weights/000010
        default="tinker://e6c3eb80-28f6-56d5-88dd-3f35f6dea45a:train:0/sampler_weights/000030",  # Run 6 step 30
        help="Tinker sampler_weights path to load. Omit to use the base model.",
    )
    parser.add_argument(
        "--question",
        type=str,
        required=True,
        help="The cricket question to ask the model.",
    )
    args = parser.parse_args()

    console.print("[bold]Connecting to Tinker...[/bold]")
    service_client = tinker.ServiceClient()

    if args.checkpoint:
        console.print(f"[bold yellow]Mode: CHECKPOINT[/bold yellow] — {args.checkpoint}")
        sampling_client = service_client.create_sampling_client(
            model_path=args.checkpoint,
        )
    else:
        console.print(f"[bold yellow]Mode: BASE MODEL[/bold yellow] — {MODEL_NAME}")
        sampling_client = service_client.create_sampling_client(base_model=MODEL_NAME)

    console.print(f"[green]Sampling client ready: {type(sampling_client).__name__}[/green]\n")

    asyncio.run(run_smoke_test(sampling_client, args.question))
