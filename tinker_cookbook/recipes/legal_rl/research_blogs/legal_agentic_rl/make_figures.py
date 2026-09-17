"""Generate all figures for the legal-agentic-RL blog post.

Numbers are hardcoded from JOURNAL.md (the final, verified results) so the figures
are reproducible even though the early /tmp run curves were wiped. The one live
curve (Exp 5 training) is read from the persistent metrics.jsonl.

Run:  python tinker_cookbook/recipes/legal_rl/research_blogs/legal_agentic_rl/make_figures.py
Output: figures/*.png
"""

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)
EXP5_METRICS = "/Users/adithyagiridharan/Desktop/legal_rl_runs/exp5/metrics.jsonl"

BLUE, RED, GREEN, GREY = "#2c6fbb", "#c0392b", "#27ae60", "#95a5a6"
plt.rcParams.update({"figure.dpi": 130, "font.size": 11, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.axisbelow": True})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, name), bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


# 1. Exp 1 — reward hacking: tool use collapses
def fig_reward_hacking():
    fig, ax = plt.subplots(figsize=(5, 3.6))
    steps = ["step 6", "step 16 (final)"]
    turns = [1.69, 1.00]
    bars = ax.bar(steps, turns, color=[BLUE, RED], width=0.5)
    ax.axhline(1.0, ls="--", color=GREY, lw=1)
    ax.set_ylabel("turns / episode")
    ax.set_title("Exp 1: exact-match reward → the agent abandons its tool\n"
                 "(correctness stayed 0.00 throughout)")
    ax.set_ylim(0, 2.2)
    for b, v in zip(bars, turns):
        ax.text(b.get_x() + b.get_width()/2, v + 0.05, f"{v:.2f}", ha="center")
    ax.text(1, 1.02, "1.0 = answers directly, never searches", color=RED, fontsize=9, ha="center")
    save(fig, "fig01_reward_hacking.png")


# 2. A3 — grounding probe: the model genuinely uses retrieval
def fig_grounding():
    fig, ax = plt.subplots(figsize=(5, 3.6))
    bars = ax.bar(["retrieval ON", "retrieval OFF"], [0.500, 0.286],
                  color=[GREEN, GREY], width=0.5)
    ax.set_ylabel("held-out correctness")
    ax.set_title("A3: take the tool away and correctness drops 43%\n(the agent isn't just memorizing)")
    ax.set_ylim(0, 0.7)
    for b, v in zip(bars, [0.500, 0.286]):
        ax.text(b.get_x()+b.get_width()/2, v+0.01, f"{v:.3f}", ha="center")
    save(fig, "fig03_grounding.png")


# 3. A5 — the judge sign-flip
def fig_judge_flip():
    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    labels = ["graded by 4B judge\n(grader < agent)", "graded by 235B judge\n(grader > agent)"]
    deltas = [-0.143, +0.072]
    colors = [RED, GREEN]
    bars = ax.bar(labels, deltas, color=colors, width=0.5)
    ax.axhline(0, color="black", lw=1)
    ax.set_ylabel("Δ correctness (RL − base), 30B")
    ax.set_title("A5: the SAME models, two judges — the result's sign flips")
    for b, v in zip(bars, deltas):
        ax.text(b.get_x()+b.get_width()/2, v + (0.008 if v > 0 else -0.018),
                f"{v:+.3f}", ha="center")
    save(fig, "fig05_judge_flip.png")


# 4. Exp 3 + Exp 5 — RL does not beat base on held-out
def fig_base_vs_rl():
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    groups = ["Exp 3: 4B\n(n=28)", "Exp 5: 30B\n(n=236)"]
    base = [0.500, 0.619]
    rl = [0.500, 0.606]
    err = [0.094, 0.031]
    x = range(len(groups))
    w = 0.36
    ax.bar([i - w/2 for i in x], base, w, yerr=err, capsize=4, label="base", color=GREY)
    ax.bar([i + w/2 for i in x], rl, w, yerr=err, capsize=4, label="after RL", color=BLUE)
    ax.set_xticks(list(x)); ax.set_xticklabels(groups)
    ax.set_ylabel("held-out correctness")
    ax.set_title("RL did not beat the base model on held-out questions")
    ax.set_ylim(0, 0.8); ax.legend()
    save(fig, "fig06_base_vs_rl.png")


# 5. A6 — failure-mode breakdown
def fig_failure_modes():
    fig, ax = plt.subplots(figsize=(6, 3.6))
    labels = ["reasoning\n(RL can't fix)", "retriever ceiling\n(infra)", "agent query\n(RL-addressable)"]
    vals = [47, 35, 18]
    colors = [RED, "#e67e22", GREEN]
    bars = ax.barh(labels, vals, color=colors)
    ax.set_xlabel("% of held-out errors (30B base)")
    ax.set_title("A6: why the base fails — only 18% is RL-addressable")
    ax.set_xlim(0, 55)
    for b, v in zip(bars, vals):
        ax.text(v + 1, b.get_y()+b.get_height()/2, f"{v}%", va="center")
    save(fig, "fig07_failure_modes.png")


# 6. A7 — per-source retrieval recall on the unified index
def fig_recall_per_source():
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ks = [1, 3, 5, 10]
    data = {
        "legal-rag-qa": [0.600, 0.733, 0.783, 0.817],
        "legal-rag-bench": [0.217, 0.350, 0.400, 0.500],
        "open-australian": [0.783, 0.833, 0.883, 0.917],
        "ALL": [0.533, 0.639, 0.689, 0.744],
    }
    colors = {"legal-rag-qa": BLUE, "legal-rag-bench": RED,
              "open-australian": GREEN, "ALL": "black"}
    for name, ys in data.items():
        ax.plot(ks, ys, marker="o", label=name, color=colors[name],
                lw=(2.5 if name == "ALL" else 1.6),
                ls=("--" if name == "ALL" else "-"))
    ax.set_xticks(ks); ax.set_xlabel("k (retrieved passages)")
    ax.set_ylabel("recall@k")
    ax.set_title("A7: one source (legal-rag-bench) poisons retrieval")
    ax.set_ylim(0, 1.0); ax.legend(fontsize=9)
    save(fig, "fig08_recall_per_source.png")


# 7. A8 — the judge 2x2 (scale vs judge leniency)
def fig_judge_2x2():
    fig, ax = plt.subplots(figsize=(6, 3.8))
    models = ["30B base", "397B base"]
    j235 = [0.619, None]   # 397B@235B only n=8 smoke → omit
    j550 = [0.653, 0.699]
    x = range(len(models)); w = 0.36
    ax.bar([i - w/2 for i in x], [v if v is not None else 0 for v in j235], w,
           label="235B judge", color=GREY)
    ax.bar([i + w/2 for i in x], j550, w, label="550B judge", color=BLUE)
    ax.set_xticks(list(x)); ax.set_xticklabels(models)
    ax.set_ylabel("held-out correctness (n=236)")
    ax.set_title("A8: the apparent +0.08 'scale win' = +0.034 judge leniency + +0.046 real")
    ax.set_ylim(0, 0.8); ax.legend()
    for i, v in enumerate(j550):
        ax.text(i + w/2, v + 0.01, f"{v:.3f}", ha="center")
    ax.text(0 - w/2, 0.619 + 0.01, "0.619", ha="center")
    ax.annotate("397B@235B was only an n=8 smoke", xy=(1-w/2, 0.05), fontsize=8, color=GREY, ha="center")
    save(fig, "fig09_judge_2x2.png")


# 8. Model-size lift (base, best-available comparable judge)
def fig_model_size():
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    models = ["4B", "30B", "397B"]
    vals = [0.500, 0.653, 0.699]
    bars = ax.bar(models, vals, color=[GREY, BLUE, GREEN], width=0.5)
    ax.set_ylabel("base held-out correctness")
    ax.set_title("Scale helps the BASE — real but diminishing\n(30B/397B under same 550B judge; 4B under 4B judge)")
    ax.set_ylim(0, 0.8)
    for b, v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v+0.01, f"{v:.3f}", ha="center")
    save(fig, "fig10_model_size.png")


# 9. Exp 5 training curve (from the live metrics.jsonl)
def fig_exp5_curve():
    if not os.path.exists(EXP5_METRICS):
        print("skip exp5 curve (metrics missing)"); return
    rows = [json.loads(l) for l in open(EXP5_METRICS)]
    b = [r.get("progress/batch", i) for i, r in enumerate(rows)]
    rew = [r.get("env/all/reward/total", 0) for r in rows]
    cor = [r.get("env/all/correct", 0) for r in rows]
    turns = [r.get("env/all/turns_per_episode", 0) for r in rows]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.plot(b, rew, label="reward", color=BLUE)
    ax.plot(b, cor, label="correct (train)", color=GREEN)
    ax.set_xlabel("training batch"); ax.set_ylabel("reward / correct")
    ax.set_ylim(0, 1.0)
    ax2 = ax.twinx()
    ax2.plot(b, turns, label="turns/episode", color="#e67e22", ls="--", alpha=0.8)
    ax2.set_ylabel("turns/episode"); ax2.set_ylim(0, 4); ax2.grid(False)
    ax.set_title("Exp 5 training (30B, 235B judge): healthy curve — that did NOT generalize")
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines], fontsize=9, loc="lower right")
    save(fig, "fig04_exp5_training.png")


if __name__ == "__main__":
    fig_reward_hacking()
    fig_grounding()
    fig_judge_flip()
    fig_base_vs_rl()
    fig_failure_modes()
    fig_recall_per_source()
    fig_judge_2x2()
    fig_model_size()
    fig_exp5_curve()
    print("\nAll figures in", FIG)
