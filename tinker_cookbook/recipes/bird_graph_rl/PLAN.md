# Plan — graph-agent post-training (hard stop 2026-10-17)

**Objective.** Take a smaller open model, measure its zero-shot baseline as a Cypher-writing
agent on the `codebase_community` graph, post-train it (RL), and measure how much ground it
gains toward a frontier reference. That result is the blog post: Fireworks first, Thinking
Machines after. Single source of truth for who does what; evidence lives in `JOURNAL.md`.

**Team.** Owner (product, decisions, spend) · Tinker agent (this repo: shared spec, RL on
Tinker) · Fireworks agent (Fireworks repo: same experiment on Fireworks) · Codex (this repo:
training-data generation). Research questions go to sub-agents restricted to official sources.

**Rules.** Official sources only. Shared code is imported and pinned by git blob hash, never
re-implemented from prose. BIRD's 186 questions are evaluation only and are never read by the
data generator. Preflight, opening balance and a cost stop before anything billed. **Every number is computed with a
tool** — measured, or calculated by a script from stated inputs and labelled an estimate — never
mental arithmetic or a predicted quantity, in messages between agents as much as in reports.

## Done
- D1 Graph built and reconciled: 649,846 nodes / 1,380,394 relationships.
- D2 Reference answers for 186 questions (gold SQL executed), exact rows for all 186.
- D3 Zero-shot baseline, Qwen/Qwen3.8-27B: strict 0.608 on Tinker and on Fireworks (paired,
  no framework effect). 22.6% of questions flip between two single samples.
- D4 Partial-credit reward (`reward.py`): row-level F1, 1.0 only when strictly correct.

## Tasks
| id | task | owner | due | done when |
|---|---|---|---|---|
| T1 | Training data, stage A: enumerate query structures, instantiate, execute, filter (`datagen/SPEC.md`) | Codex | Oct 4 | ≥150 structures, ≥1,500 verified instances, split by structure |
| T2 | Training data, stage B: natural-language question for each instance + ambiguity check | Codex + Tinker agent | Oct 5 | every instance has a question; 100 spot-checked |
| T3 | Frontier reference on the 186 through the same harness | Tinker agent | Oct 4 | number + cost in journal |
| T4 | RL environment + reward wired into the cookbook RL loop, hash-pinned | Tinker agent | Oct 5 | smoke run of 2 updates passes |
| T5 | Fireworks RL loop against the SDK, importing the pinned env/reward | Fireworks agent | Oct 5 | smoke run of 2 updates passes |
| T6 | Multi-sample baseline, k samples per question | both | Oct 5 | paired table at k |
| T7 | RL run 1 (verifiable reward) | Tinker agent, then Fireworks agent | Oct 7 | curve + gated checkpoint |
| T8 | Evaluate checkpoints: BIRD 186 (k samples) + held-out structures | both | Oct 9 | gain with paired test |
| T9 | ~~Decision-model judge as reward~~ — **parked by the owner 2026-10-03** (revisit after milestone 1) | — | — | — |
| T10 | Figures + blog draft (Fireworks) | all | Oct 15 | draft reviewed by owner |
| — | Buffer | — | Oct 16–17 | — |

## Milestone 1 (proposed)
Qwen/Qwen3.5-9B: zero-shot 0.425 strict → RL on Tinker with the verifiable partial-credit reward
→ gain toward the Qwen3.8-27B reference (0.608), judged by the pre-registered bar in `JOURNAL.md`.
Checkpoint selection on generated `heldout_instance`; never on the 186.

## Open decisions (owner)
0. **Student model** — proposed Qwen3.5-9B (see `JOURNAL.md` E3). On Fireworks the 9B trains only
   on hourly dedicated GPUs and the 4B not at all, so the platforms diverge: (A) 9B on both,
   Fireworks as one short dedicated run; (B) train on Tinker, Fireworks serves and verifies the
   adapter; (C) ask Fireworks for credits or per-token access to 9B training first.
1. Frontier reference model (T3) — pending official-source research.
2. k for evaluation (T6) — proposed 4.
3. Which model writes the natural-language questions in T2 (it becomes the "teacher").
4. Generated prompts carry a hint at the evaluation rate (172 of 186 evaluation questions do),
   written deterministically from the query's own structure — proposed, not yet built.

## Cut order if we slip
T9 → second-platform RL run → k=4 to k=2 on intermediate checks → ablations.
Never cut: the held-out-structure evaluation in T8.
