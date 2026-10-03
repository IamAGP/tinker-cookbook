"""Mirror a training run to object storage and draw its curves.

Storage is cheap and reruns are not, so everything a run writes is kept: metrics, rollout
summaries, transcripts, config, and the figures drawn from them. Run once after training, or
with ``watch_seconds`` alongside it so a killed run still leaves its curves behind.

    python -m tinker_cookbook.recipes.bird_graph_rl.monitor log_path=~/bird_rl_runs/rl_run1 run_name=rl_run1 watch_seconds=120

Destination comes from the environment (``BIRD_S3_BUCKET``, ``BIRD_S3_PREFIX``), never from code.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import chz
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dotenv import load_dotenv

# Substrings of metric names worth a panel, in display order.
PANELS = ["reward", "correct", "partial_credit", "no_query", "n_queries", "n_query_errors", "kl",
          "entropy", "loss", "turns", "ac_tokens", "ob_tokens", "episode_len", "frac", "time", "learning_rate"]


@chz.chz
class Config:
    log_path: str
    run_name: str
    env_file: str = ".env"
    watch_seconds: int = 0      # 0 = run once
    stop_file: str = ""         # with watch: stop when this file exists (e.g. the trainer's done marker)


def read_metrics(log_dir: Path) -> list[dict[str, float]]:
    path = log_dir / "metrics.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a line still being written
    return rows


def plot(log_dir: Path, run_name: str) -> list[Path]:
    rows = read_metrics(log_dir)
    if not rows:
        return []
    keys = sorted({k for r in rows for k, v in r.items() if isinstance(v, (int, float)) and k != "step"})
    chosen = [k for p in PANELS for k in keys if p in k.lower()]
    chosen = list(dict.fromkeys(chosen)) or keys
    out_dir = log_dir / "figures"
    out_dir.mkdir(exist_ok=True)
    written: list[Path] = []
    per_page = 12
    for page, start in enumerate(range(0, len(chosen), per_page)):
        batch = chosen[start : start + per_page]
        cols = 3
        n_rows = (len(batch) + cols - 1) // cols
        fig, axes = plt.subplots(n_rows, cols, figsize=(5 * cols, 3.2 * n_rows), squeeze=False)
        for ax, key in zip(axes.flat, batch):
            pts = [(r.get("step", i), r[key]) for i, r in enumerate(rows) if isinstance(r.get(key), (int, float))]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", markersize=3, linewidth=1.2)
            ax.set_title(key, fontsize=9)
            ax.set_xlabel("training step", fontsize=8)
            ax.grid(alpha=0.3)
        for ax in axes.flat[len(batch):]:
            ax.axis("off")
        fig.suptitle(f"{run_name} — {len(rows)} logged steps", fontsize=11)
        fig.tight_layout()
        target = out_dir / f"curves_{page:02d}.png"
        fig.savefig(target, dpi=130)
        plt.close(fig)
        written.append(target)
    (out_dir / "metric_keys.json").write_text(json.dumps(keys, indent=1))
    return written


def sync(log_dir: Path, run_name: str) -> str:
    bucket, prefix = os.environ["BIRD_S3_BUCKET"], os.environ.get("BIRD_S3_PREFIX", "")
    dest = f"s3://{bucket}/{prefix}/runs/{run_name}/".replace("//runs", "/runs")
    done = subprocess.run(["aws", "s3", "sync", str(log_dir), dest, "--only-show-errors"],
                          capture_output=True, text=True)
    return "ok" if done.returncode == 0 else f"FAILED: {done.stderr.strip()[:200]}"


def main(cfg: Config) -> None:
    load_dotenv(cfg.env_file, override=False)
    log_dir = Path(cfg.log_path).expanduser()
    while True:
        figures = plot(log_dir, cfg.run_name)
        status = sync(log_dir, cfg.run_name)
        print(f"[{time.strftime('%H:%M:%S')}] steps={len(read_metrics(log_dir))} figures={len(figures)} sync={status}", flush=True)
        if cfg.watch_seconds <= 0 or (cfg.stop_file and Path(cfg.stop_file).expanduser().exists()):
            break
        time.sleep(cfg.watch_seconds)


if __name__ == "__main__":
    main(chz.entrypoint(Config))
