"""
Launch the AdamW/Dimuon sweep as parallel processes and watch them.

The watchdog kills every run if any run's log goes quiet for ``stall_minutes``, or if the
token-based spend estimate passes ``budget_usd``. Re-running the same command resumes each
run from its last state checkpoint.

Example:
    python -m tinker_cookbook.recipes.dimuon_sft.sweep
    python -m tinker_cookbook.recipes.dimuon_sft.sweep smoke=True
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import chz

from tinker_cookbook import cli_utils

ADAMW_LR = 4.7297908091376354e-4  # hyperparam_utils.get_lr("Qwen/Qwen3-8B")
RUNS: list[tuple[str, float]] = [
    ("adamw", 0.5 * ADAMW_LR), ("adamw", ADAMW_LR), ("adamw", 2 * ADAMW_LR),
    ("dimuon", 1e-3), ("dimuon", 5 * ADAMW_LR), ("dimuon", 15 * ADAMW_LR),
]


@chz.chz
class Config:
    smoke: bool = False
    root: str = cli_utils.runs_path("dimuon_sft")
    price_per_mtok: float = 0.44  # Qwen3-8B training price, tinker-docs models page
    eval_tokens: int = 81_620  # tokens in one eval pass (121 examples), counted locally
    budget_usd: float = 4.50
    stall_minutes: float = 15.0
    poll_seconds: float = 30.0


def spent_usd(log_dir: Path, cfg: Config) -> float:
    path = log_dir / "metrics.jsonl"
    if not path.exists():
        return 0.0
    tokens = 0
    for line in path.read_text().splitlines():
        row = json.loads(line)
        tokens += int(row.get("num_tokens", 0)) + (cfg.eval_tokens if "eval_nll" in row else 0)
    return tokens * cfg.price_per_mtok / 1e6


def main(cfg: Config) -> None:
    runs = [RUNS[3]] if cfg.smoke else RUNS
    procs: dict[str, tuple[subprocess.Popen, Path]] = {}
    for opt, lr in runs:
        name = f"{'smoke_' if cfg.smoke else ''}{opt}_lr{lr:.2e}"
        log_dir = Path(cfg.root) / name
        log_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-m", "tinker_cookbook.recipes.dimuon_sft.train",
               f"optimizer={opt}", f"learning_rate={lr!r}", f"log_path={log_dir}"]
        if cfg.smoke:
            cmd.append("max_steps=3")
        out = open(log_dir / "stdout.log", "a")  # noqa: SIM115 (lives as long as the child)
        procs[name] = (subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True), log_dir)
        print(f"[{time.strftime('%H:%M:%S')}] launched {name} pid={procs[name][0].pid}", flush=True)

    def kill_all(reason: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] WATCHDOG: {reason}; killing all runs", flush=True)
        for p, _ in procs.values():
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)

    while any(p.poll() is None for p, _ in procs.values()):
        time.sleep(cfg.poll_seconds)
        total = sum(spent_usd(d, cfg) for _, d in procs.values())
        status = []
        for name, (p, d) in procs.items():
            quiet = (time.time() - (d / "stdout.log").stat().st_mtime) / 60
            status.append(f"{name}:{'run' if p.poll() is None else p.returncode}/{quiet:.0f}m")
            if p.poll() is None and quiet > cfg.stall_minutes:
                kill_all(f"{name} silent for {quiet:.0f} min")
        print(f"[{time.strftime('%H:%M:%S')}] est_spend=${total:.3f} " + " ".join(status), flush=True)
        if total > cfg.budget_usd:
            kill_all(f"spend estimate ${total:.2f} > budget ${cfg.budget_usd:.2f}")

    print(f"[{time.strftime('%H:%M:%S')}] all runs exited: "
          + " ".join(f"{n}={p.returncode}" for n, (p, _) in procs.items()), flush=True)


if __name__ == "__main__":
    chz.nested_entrypoint(main)
