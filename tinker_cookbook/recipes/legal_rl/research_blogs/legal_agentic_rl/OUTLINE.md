# OUTLINE — "Can you RL a legal research agent?"

> STATUS (2026-06-24): **Full draft COMPLETE** in `draft.md` — all 12 sections
> written, all 9 figures generated (`make_figures.py` → `figures/`). Remaining:
> the author's voice pass + porting to the publishing platform. The outline below
> is kept as the planning record.

> Working title. Final title written last (once we know what the story became).
> A confound-hunting detective story: each section makes a CLAIM, shows EVIDENCE
> (a figure/number traceable to a journal entry), and lands a TAKEAWAY. The
> reversals are the spine — they're what carry a 20-minute read.

Status legend: ☐ not started · ◐ drafting · ☑ drafted · ★ figure made

---

## Narrative arc (one sentence)
I tried to improve a legal RAG agent with RL; every "success" turned out to be a
measurement artifact, and chasing down *why* taught me more than any win would have.

---

## Section plan

### 0. Hook / intro  ☐  (write LAST)
- Open on the most dramatic reversal (the judge that lied — Exp4→A5), then promise
  the journey. Set the question: *does RL actually make an agentic RAG model better,
  and how would you even know?*

### 1. The setup  ☐
- Claim: agentic RAG = multi-turn search-then-answer; reward must grade the answer.
- Evidence: architecture diagram (agent ↔ search tool ↔ ChromaDB/Titan ↔ judge).
- Figure needed: ★ schematic of the loop. (no data — a drawn diagram)
- Source: Exp 0, recipe code.

### 2. Naive reward → the agent games it  ☐
- Claim: an exact-match/format reward gets hacked — the model learned to ALWAYS
  format and *stopped using the search tool*.
- Evidence: turns_per_episode 1.69 → 1.0; reward came only from the format term.
- Figure needed: ★ turns_per_episode & reward vs step (Exp 1). Data: exp1 metrics.
- Source: Exp 1.

### 3. Fix the reward: LLM-as-judge  ☐
- Claim: a model judge of semantic correctness restores a real learning signal.
- Evidence: frac_mixed recovers; training reward rises.
- Figure needed: ★ training reward / correct vs step (Exp 2).
- Source: Exp 2.

### 4. The trap: training reward ≠ learning  ☐  (KEY)
- Claim: high training reward fooled me; a frozen held-out set showed no gain.
- Evidence: held-out correct 0.50 → 0.50.
- Figure needed: ★ training-reward curve vs held-out bar (the gap).
- Source: Exp 3.

### 5. Is the tool even doing anything?  ☐
- Claim: before blaming the model, check the plumbing — retriever works, and the
  model genuinely uses it.
- Evidence: recall@3 = 0.775 (audit); correctness drops 0.50→0.29 without retrieval.
- Figure needed: ★ recall@k bars; ★ with-vs-without-retrieval bars.
- Source: A1, A3.

### 6. Maybe the model's too small?  ☐
- Claim: a bigger base has headroom — but RL on it looked like a *regression*.
- Evidence: 30B base 0.64 > 4B 0.50; but 30B+RL appeared to drop to 0.50.
- Figure needed: ★ base-vs-RL bars across 4B / 30B.
- Source: A4, Exp 4.

### 7. The judge was lying  ☐  (CLIMAX)
- Claim: the "regression" was an artifact — a weak (4B) judge grading a 30B agent
  inverted the result. Grader must be ≥ the graded.
- Evidence: same models, Δ flips from −0.14 (4B judge) to +0.07 (235B judge).
- Figure needed: ★ the sign-flip chart (Δ under 4B vs 235B judge).
- Source: A5.

### 8. The clean run  ☐
- Claim: removing every confound (big data, strong judge, big eval, tuned LR, KL)
  gives a trustworthy answer — and it's a null.
- Evidence: 236-Q held-out, base 0.619 vs RL 0.606 (within noise).
- Figure needed: ★ base-vs-RL bars with error bars (n=236).
- Source: Exp 5.

### 9. So *why* does it fail?  ☐
- Claim: the failures aren't about tool-use — 47% reasoning, 35% retriever-ceiling,
  only 18% agent-query (the sole RL-addressable slice).
- Evidence: 3-way failure breakdown.
- Figure needed: ★ failure-mode bar/pie.
- Source: A6.

### 10. One dataset was poisoning retrieval  ☐
- Claim: per-source audit found legal-rag-bench at recall@3=0.35 dragging the index.
- Evidence: per-source recall@k table.
- Figure needed: ★ per-source recall@k grouped bars.
- Source: A7.

### 11. Lessons & honest open questions  ☐
- Claim: the meta-lessons — measure on held-out, grader ≥ graded, smoke-test first,
  diagnose before iterating, RL needs headroom + a tool-bottlenecked task.
- Evidence: callbacks to each reversal.
- Source: whole arc.

---

## Figures to generate (master list)
From `~/Desktop/legal_rl_runs/*/metrics.jsonl` and the eval/audit tables in JOURNAL.md:
1. ☐ Exp 1 — turns_per_episode + reward vs step (hacking collapse)
2. ☐ Exp 2 — training reward/correct vs step
3. ☐ Exp 3 — training-reward vs held-out gap
4. ☐ A1 — recall@k bars; A3 — with/without retrieval bars
5. ☐ Exp4/A4 — base-vs-RL across model sizes
6. ☐ A5 — judge sign-flip (Δ under 4B vs 235B)
7. ☐ Exp 5 — base-vs-RL on 236-Q held-out (error bars)
8. ☐ A6 — failure-mode 3-way
9. ☐ A7 — per-source recall@k

## Process notes
- Build section-by-section; don't draft linearly front-to-back.
- Each figure traceable to a run dir + checkpoint (see ../README.md correlation key).
- Keep the reversals honest and prominent — they're the point.
