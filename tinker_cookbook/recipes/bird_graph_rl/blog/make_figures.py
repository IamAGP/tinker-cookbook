"""Blog figures, regenerated from the run folders only. Every plotted number is also written to figures/numbers.json."""
import collections, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

R = os.path.expanduser("~/bird_rl_runs"); OUT = f"{R}/blog/figures"
BASE = ["e3_qwen3_5_9b", "e5_base9b_s2", "e5_base9b_s3", "e5_base9b_s4"]
RUN1 = [f"e7_186_s37_s{k}" for k in range(1, 5)]; RUN2 = [f"e9_186_s37_s{k}" for k in range(1, 5)]
C = {"base": "#8a8f98", "run1": "#2f6fb0", "run2": "#d9822b", "ref": "#333333"}
numbers = {}

def rows(folder): return [json.loads(l) for l in open(f"{R}/{folder}/results.jsonl")]
def per_q(folders, metric):
    acc = collections.defaultdict(list)
    for f in folders:
        for d in rows(f): acc[d["question_id"]].append(float(d[metric]))
    return np.array([np.mean(v) for _, v in sorted(acc.items(), key=lambda kv: str(kv[0]))])
def ci(x, n=10_000, seed=0):
    rng = np.random.default_rng(seed); b = x[rng.integers(0, len(x), size=(n, len(x)))].mean(axis=1)
    return float(x.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))

# Figure 1: the 186 human questions
fig, ax = plt.subplots(figsize=(7.2, 4.2)); w = 0.26; numbers["fig1"] = {}
for j, (name, folders) in enumerate([("base", BASE), ("run1", RUN1), ("run2", RUN2)]):
    for i, metric in enumerate(["correct", "lenient"]):
        m, lo, hi = ci(per_q(folders, metric)); numbers["fig1"][f"{name}_{metric}"] = [round(v, 4) for v in (m, lo, hi)]
        ax.bar(i + (j - 1) * w, m, w, color=C[name], yerr=[[m - lo], [hi - m]], capsize=3,
               label={"base": "Qwen3.5-9B, untrained", "run1": "after RL, run 1", "run2": "after RL, run 2"}[name] if i == 0 else None)
        ax.text(i + (j - 1) * w, hi + 0.012, f"{m:.3f}", ha="center", fontsize=8)
ref = float(np.mean([d["correct"] for d in rows("e2_full_qwen3_8_27b")])); numbers["fig1"]["ref_27b_strict"] = round(ref, 4)
ax.axhline(ref, xmin=0.02, xmax=0.48, color=C["ref"], ls="--", lw=1); ax.text(-0.42, ref + 0.008, f"Qwen3.8-27B, untrained: {ref:.3f}", fontsize=8)
ax.set_xticks([0, 1]); ax.set_xticklabels(["strict: exact rows", "lenient: right values,\nany shape"]); ax.set_ylim(0, 0.75)
ax.set_ylabel("accuracy on 186 human-written questions"); ax.set_title("Human-written questions: 4 samples per question, 95% bootstrap intervals", fontsize=10)
ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.16)); fig.tight_layout(); fig.savefig(f"{OUT}/fig1_human_questions.png", dpi=180); plt.close(fig)

# Figure 2: held-out generated questions across checkpoints
fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.8), sharey=True); numbers["fig2"] = {}
series = {"264 new instances of seen structures": ([("e6_hi_base", 0), ("e6_hi_s10", 10), ("e6_hi_s20", 20), ("e6_hi_s30", 30), ("e6_hi_s37", 37)], [("e6_hi_base", 0), ("e9_hi_s30", 30), ("e9_hi_s37", 37)]),
          "360 questions on unseen structures": ([("e8_hs_base", 0), ("e8_hs_s37", 37)], [("e8_hs_base", 0), ("e9_hs_s30", 30), ("e9_hs_s37", 37)])}
for ax, (title, (r1, r2)) in zip(axes, series.items()):
    for name, pts in (("run1", r1), ("run2", r2)):
        xs = [s for _, s in pts]; stats = [ci(np.array([float(d["correct"]) for d in rows(f)])) for f, _ in pts]
        numbers["fig2"][f"{title}|{name}"] = {str(s): round(st[0], 4) for s, st in zip(xs, stats)}
        ax.errorbar(xs, [s[0] for s in stats], yerr=[[s[0] - s[1] for s in stats], [s[2] - s[0] for s in stats]], color=C[name], marker="o", capsize=3,
                    label={"run1": "run 1", "run2": "run 2"}[name], ls="-" if name == "run1" else "--")
    ax.set_title(title, fontsize=9); ax.set_xlabel("training step")
axes[0].set_ylabel("strict accuracy, 1 sample"); axes[0].legend(frameon=False, fontsize=8); fig.tight_layout(); fig.savefig(f"{OUT}/fig2_generated_heldout.png", dpi=180); plt.close(fig)

# Figure 3: where the samples go on the human questions
def outcome(d):
    if d["correct"] == 1: return "strictly correct"
    if d["lenient"] == 1: return "right values, wrong shape"
    return "wrong: ran out of turns" if d["stop_reason"] == "max_turns" else "wrong"
order = ["strictly correct", "right values, wrong shape", "wrong", "wrong: ran out of turns"]; cols = ["#2e8b57", "#9ccc65", "#c0504d", "#7f3b39"]
fig, ax = plt.subplots(figsize=(7.2, 3.2)); numbers["fig3"] = {}
for y, (name, folders) in enumerate([("untrained", BASE), ("run 1", RUN1), ("run 2", RUN2)]):
    c = collections.Counter(outcome(d) for f in folders for d in rows(f)); left = 0; numbers["fig3"][name] = {k: c[k] for k in order}
    for k, col in zip(order, cols):
        ax.barh(y, c[k], left=left, color=col, label=k if y == 0 else None); ax.text(left + c[k] / 2, y, str(c[k]), ha="center", va="center", fontsize=8, color="white"); left += c[k]
ax.set_yticks([0, 1, 2]); ax.set_yticklabels(["untrained", "run 1", "run 2"]); ax.invert_yaxis(); ax.set_xlabel("samples (186 questions × 4)")
ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.32)); fig.tight_layout(); fig.savefig(f"{OUT}/fig3_outcomes.png", dpi=180); plt.close(fig)

# Figure 4: what kind of question is asked
def klass(a): return "lookup" if a == "none" else "how many" if a in ("count", "count distinct", "count_distinct") else "more than one" if a in ("multiple", "more than one aggregate") else "sum / avg / min / max"
human = json.load(open(f"{R}/bird_train_filtered_shapes.json")); hm = collections.Counter()
for e in human["aggregation"]: hm[klass(e["value"])] += e["share"]
sig = {json.loads(l)["structure_id"]: json.loads(json.loads(l)["signature"])["aggregation"][0] for l in open(f"{R}/datagen_v3/structures.snapshot.jsonl")}
s1 = collections.Counter(klass(sig[json.loads(l)["structure_id"]]) for l in open(f"{R}/datagen_v3/train_300.jsonl"))
ids = {json.loads(l)["instance_id"] for l in open(f"{R}/datagen_v4/train_320.jsonl")}
s2 = collections.Counter(klass(json.loads(l)["shape"]["aggregation"]) for l in open(f"{R}/datagen_v4/instances_v4_train.jsonl") if json.loads(l)["instance_id"] in ids)
cats = ["lookup", "how many", "sum / avg / min / max", "more than one"]; fig, ax = plt.subplots(figsize=(7.2, 3.6)); numbers["fig4"] = {}
for j, (name, c, col) in enumerate([("human-written (6,601, other databases)", hm, C["ref"]), ("training set 1", s1, C["run1"]), ("training set 2", s2, C["run2"])]):
    tot = sum(c.values()); sh = [c[k] / tot for k in cats]; numbers["fig4"][name] = {k: round(v, 4) for k, v in zip(cats, sh)}
    ax.bar(np.arange(4) + (j - 1) * w, sh, w, color=col, label=name)
ax.set_xticks(range(4)); ax.set_xticklabels(cats); ax.set_ylabel("share of questions"); ax.legend(frameon=False, fontsize=8); fig.tight_layout(); fig.savefig(f"{OUT}/fig4_question_mix.png", dpi=180); plt.close(fig)

# Figure 5: training curves of both runs
fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2)); numbers["fig5"] = {}
for name, run in (("run1", "e4b_rl_base"), ("run2", "e9_rl_v4")):
    M = [json.loads(l) for l in open(f"{R}/{run}/metrics.jsonl")]; numbers["fig5"][name] = {"steps": len(M)}
    for ax, (key, title) in zip(axes, [("env/all/reward/total", "mean reward of the step's rollouts"), ("env/all/correct", "share strictly correct"), ("optim/kl_sample_train_v1", "sampler vs trainer KL")]):
        ax.plot([m.get(key, np.nan) for m in M], color=C[name], label={"run1": "run 1", "run2": "run 2"}[name], lw=1.2); ax.set_title(title, fontsize=9); ax.set_xlabel("training step")
axes[0].legend(frameon=False, fontsize=8); fig.tight_layout(); fig.savefig(f"{OUT}/fig5_training_curves.png", dpi=180); plt.close(fig)
json.dump(numbers, open(f"{OUT}/numbers.json", "w"), indent=1); print(json.dumps(numbers, indent=1))
