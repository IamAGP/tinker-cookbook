"""
Launch Cricket KG RL training — smoke run with 30 questions.

Usage:
    uv run python -m tinker_cookbook.recipes.cricket_kg_rl.launch_cricket_kg

Override any CLIConfig field via CLI, e.g.:
    uv run python -m tinker_cookbook.recipes.cricket_kg_rl.launch_cricket_kg \
        max_questions=10 group_size=2 groups_per_batch=2 max_steps=5
"""

import asyncio
import logging

import chz

from tinker_cookbook.recipes.cricket_kg_rl.train import CLIConfig, cli_main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

if __name__ == "__main__":
    # chz.entrypoint parses any CLI overrides into CLIConfig.
    # Smoke-run defaults are baked into CLIConfig already:
    #   max_questions=30, eval_every=0, max_steps=5
    # Override from the command line as needed.
    cli_config = chz.entrypoint(CLIConfig)
    asyncio.run(cli_main(cli_config))
