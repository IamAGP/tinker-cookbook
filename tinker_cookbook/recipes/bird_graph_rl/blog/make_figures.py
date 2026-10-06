"""Blog figures, regenerated from the run folders only. Every plotted number is also written to figures/numbers.json."""
import collections, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

R = os.path.expanduser("~/bird_rl_runs"); OUT = f"{R}/blog/figures"
BASE = ["e3_qwen3_5_9b", "e5_base9b_s2", "e5_base9b_s3", "e5_base9b_s4"]
RUN1 = [f"e7_186_s37_s{k}" for k in range(1, 5)]; RUN2 = [f"e9_186_s37_s{k}" for k in range(1, 5)]; RUN3 = [f"e10b_186_s37_s{k}" for k in range(1, 5)]
NH_BASE = [f"e10a_nohint_base_s{k}" for k in range(1, 5)]; NH_RUN2 = [f"e10a_nohint_run2_s{k}" for k in range(1, 5)]
C = {"base": "#8a8f98", "run1": "#2f6fb0", "run2": "#d9822b", "run3": "#7b4fa3", "ref": "#333333"}
NAME = {"base": "untrained", "run1": "run 1", "run2": "run 2", "run3": "run 3"}
ARMS = [("base", BASE), ("run1", RUN1), ("run2", RUN2), ("run3", RUN3)]
numbers = {}

def rows(folder): return [json.loads(l) for l in open(f"{R}/{folder}/results.jsonl")]
def per_q(folders, metric):
    acc = collections.defaultdict(list)
    for f in folders:
        for d in rows(f): acc[str(d["question_id"])].append(float(d[metric]))
    return {q: float(np.mean(v)) for q, v in acc.items()}
def ci(x, n=10_000, seed=0):
    x = np.asarray(x, float); rng = np.random.default_rng(seed); b = x[rng.integers(0, len(x), size=(n, len(x)))].mean(axis=1)
    return float(x.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))
def arr(d): return np.array([d[q] for q in sorted(d)])

# Figure 1: the 186 human questions, four arms
fig, ax = plt.subplots(figsize=(7.6, 4.4)); w = 0.2; numbers["fig1"] = {}
for j, (name, folders) in enumerate(ARMS):
    for i, metric in enumerate(["correct", "lenient"]):
        m, lo, hi = ci(arr(per_q(folders, metric))); numbers["fig1"][f"{name}_{metric}"] = [round(v, 4) for v in (m, lo, hi)]
        ax.bar(i + (j - 1.5) * w, m, w, color=C[name], yerr=[[m - lo], [hi - m]], capsize=3, label=("Qwen3.5-9B, " if name == "base" else "after RL, ") + NAME[name] if i == 0 else None)
        ax.text(i + (j - 1.5) * w, hi + 0.012, f"{m:.3f}", ha="center", fontsize=7.5)
ref = float(np.mean([d["correct"] for d in rows("e2_full_qwen3_8_27b")])); numbers["fig1"]["ref_27b_strict_one_sample"] = round(ref, 4)
ax.axhline(ref, xmin=0.02, xmax=0.48, color=C["ref"], ls="--", lw=1); ax.text(-0.45, ref + 0.008, f"Qwen3.8-27B, untrained: {ref:.3f}", fontsize=8)
ax.set_xticks([0, 1]); ax.set_xticklabels(["strict: exact rows", "lenient: right values,\nany shape"]); ax.set_ylim(0, 0.75)
ax.set_ylabel("accuracy on 186 human-written questions"); ax.set_title("Human-written questions: 4 samples per question, 95% bootstrap intervals", fontsize=10)
ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.16)); fig.tight_layout(); fig.savefig(f"{OUT}/fig1_human_questions.png", dpi=180); plt.close(fig)

# Figure 2: held-out generated questions across checkpoints
fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.8), sharey=True); numbers["fig2"] = {}
series = {"264 new instances of seen structures": {"run1": [("e6_hi_base", 0), ("e6_hi_s10", 10), ("e6_hi_s20", 20), ("e6_hi_s30", 30), ("e6_hi_s37", 37)], "run2": [("e6_hi_base", 0), ("e9_hi_s30", 30), ("e9_hi_s37", 37)]},
          "360 questions on unseen structures": {"run1": [("e8_hs_base", 0), ("e8_hs_s37", 37)], "run2": [("e8_hs_base", 0), ("e9_hs_s30", 30), ("e9_hs_s37", 37)], "run3": [("e8_hs_base", 0), ("e10b_hs_s37", 37)]}}
for ax, (title, runs) in zip(axes, series.items()):
    for k, (name, pts) in enumerate(runs.items()):
        xs = [s + (k - 1) * 0.5 if s else s for _, s in pts]; stats = [ci([float(d["correct"]) for d in rows(f)]) for f, _ in pts]
        numbers["fig2"][f"{title}|{name}"] = {str(s): round(st[0], 4) for (_, s), st in zip(pts, stats)}
        ax.errorbar(xs, [s[0] for s in stats], yerr=[[s[0] - s[1] for s in stats], [s[2] - s[0] for s in stats]], color=C[name], marker="o", capsize=3, label=NAME[name], ls={"run1": "-", "run2": "--", "run3": ":"}[name])
    ax.set_title(title, fontsize=9); ax.set_xlabel("training step")
axes[0].set_ylabel("strict accuracy, 1 sample"); axes[1].legend(frameon=False, fontsize=8, loc="lower right"); fig.tight_layout(); fig.savefig(f"{OUT}/fig2_generated_heldout.png", dpi=180); plt.close(fig)

# Figure 3: where the samples go on the human questions
def outcome(d):
    if d["correct"] == 1: return "strictly correct"
    if d["lenient"] == 1: return "right values, wrong shape"
    return "wrong: ran out of turns" if d["stop_reason"] == "max_turns" else "wrong"
order = ["strictly correct", "right values, wrong shape", "wrong", "wrong: ran out of turns"]; cols = ["#2e8b57", "#9ccc65", "#c0504d", "#7f3b39"]
fig, ax = plt.subplots(figsize=(7.2, 3.6)); numbers["fig3"] = {}
for y, (name, folders) in enumerate(ARMS):
    c = collections.Counter(outcome(d) for f in folders for d in rows(f)); left = 0; numbers["fig3"][NAME[name]] = {k: c[k] for k in order}
    for k, col in zip(order, cols):
        ax.barh(y, c[k], left=left, color=col, label=k if y == 0 else None); ax.text(left + c[k] / 2, y, str(c[k]), ha="center", va="center", fontsize=8, color="white"); left += c[k]
ax.set_yticks(range(4)); ax.set_yticklabels([NAME[n] for n, _ in ARMS]); ax.invert_yaxis(); ax.set_xlabel("samples (186 questions × 4)")
ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.28)); fig.tight_layout(); fig.savefig(f"{OUT}/fig3_outcomes.png", dpi=180); plt.close(fig)

# Figure 4: what kind of question is asked
def klass(a): return "lookup" if a == "none" else "how many" if a in ("count", "count distinct", "count_distinct") else "more than one" if a in ("multiple", "more than one aggregate") else "sum / avg / min / max"
human = json.load(open(f"{R}/bird_train_filtered_shapes.json")); hm = collections.Counter()
for e in human["aggregation"]: hm[klass(e["value"])] += e["share"]
sig = {json.loads(l)["structure_id"]: json.loads(json.loads(l)["signature"])["aggregation"][0] for l in open(f"{R}/datagen_v3/structures.snapshot.jsonl")}
s1 = collections.Counter(klass(sig[json.loads(l)["structure_id"]]) for l in open(f"{R}/datagen_v3/train_300.jsonl"))
ids = {json.loads(l)["instance_id"] for l in open(f"{R}/datagen_v4/train_320.jsonl")}
s2 = collections.Counter(klass(json.loads(l)["shape"]["aggregation"]) for l in open(f"{R}/datagen_v4/instances_v4_train.jsonl") if json.loads(l)["instance_id"] in ids)
cats = ["lookup", "how many", "sum / avg / min / max", "more than one"]; fig, ax = plt.subplots(figsize=(7.2, 3.6)); numbers["fig4"] = {}; w4 = 0.26
for j, (name, c, col) in enumerate([("human-written (6,601, other databases)", hm, C["ref"]), ("training set 1 (run 1)", s1, C["run1"]), ("training set 2 (runs 2 and 3)", s2, C["run2"])]):
    tot = sum(c.values()); sh = [c[k] / tot for k in cats]; numbers["fig4"][name] = {k: round(v, 4) for k, v in zip(cats, sh)}
    ax.bar(np.arange(4) + (j - 1) * w4, sh, w4, color=col, label=name)
ax.set_xticks(range(4)); ax.set_xticklabels(cats); ax.set_ylabel("share of questions"); ax.legend(frameon=False, fontsize=8); fig.tight_layout(); fig.savefig(f"{OUT}/fig4_question_mix.png", dpi=180); plt.close(fig)

# Figure 5: training curves of the three runs
fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2)); numbers["fig5"] = {}
for name, run in (("run1", "e4b_rl_base"), ("run2", "e9_rl_v4"), ("run3", "e10b_rl_hints_v5")):
    M = [json.loads(l) for l in open(f"{R}/{run}/metrics.jsonl")]; numbers["fig5"][name] = {"steps": len(M)}
    for ax, (key, title) in zip(axes, [("env/all/reward/total", "mean reward of the step's rollouts"), ("env/all/correct", "share strictly correct"), ("optim/kl_sample_train_v1", "sampler vs trainer KL")]):
        ax.plot([m.get(key, np.nan) for m in M], color=C[name], label=NAME[name], lw=1.1); ax.set_title(title, fontsize=9); ax.set_xlabel("training step")
axes[0].legend(frameon=False, fontsize=8); fig.tight_layout(); fig.savefig(f"{OUT}/fig5_training_curves.png", dpi=180); plt.close(fig)

# Figure 6: what a hint is worth, before and after training
res = json.load(open(f"{R}/e10_result.json")); lv = res["E10a_lenient"]["levels"]; numbers["fig6"] = {"levels_lenient": lv, "benefit_untrained": res["E10a_lenient"]["benefit_untrained_hinted_questions"], "benefit_run2": res["E10a_lenient"]["benefit_run2_hinted_questions"], "difference": res["E10a_lenient"]["difference_of_benefits_run2_minus_untrained"]}
fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.8), gridspec_kw={"width_ratios": [1.25, 1]})
ax = axes[0]
for name, (a, b) in (("base", (lv["untrained_without"], lv["untrained_with"])), ("run2", (lv["run2_without"], lv["run2_with"]))):
    ax.plot([0, 1], [a, b], marker="o", color=C[name], lw=2, label=NAME[name]); ax.text(-0.05, a, f"{a:.3f}", ha="right", va="center", fontsize=8, color=C[name]); ax.text(1.05, b, f"{b:.3f}", ha="left", va="center", fontsize=8, color=C[name])
ax.set_xticks([0, 1]); ax.set_xticklabels(["question only", "question + hint"]); ax.set_xlim(-0.35, 1.35); ax.set_ylim(0.40, 0.62); ax.set_ylabel("lenient accuracy, 186 questions"); ax.legend(frameon=False, fontsize=8, loc="upper left"); ax.set_title("The same questions, with and without their hints", fontsize=9)
ax = axes[1]
for i, (name, key) in enumerate((("base", "benefit_untrained"), ("run2", "benefit_run2"))):
    b = numbers["fig6"][key]; ax.bar(i, b["mean"], 0.55, color=C[name], yerr=[[b["mean"] - b["ci95"][0]], [b["ci95"][1] - b["mean"]]], capsize=4); ax.text(i, b["ci95"][1] + 0.006, f"+{b['mean']:.3f}", ha="center", fontsize=8)
ax.set_xticks([0, 1]); ax.set_xticklabels(["untrained", "run 2"]); ax.set_ylabel("what a hint adds (172 hinted questions)"); ax.set_ylim(0, 0.21); ax.set_title("Hint benefit, 95% intervals", fontsize=9)
fig.tight_layout(); fig.savefig(f"{OUT}/fig6_hint_reliance.png", dpi=180); plt.close(fig)
json.dump(numbers, open(f"{OUT}/numbers.json", "w"), indent=1); print("ok", sorted(os.listdir(OUT)))
