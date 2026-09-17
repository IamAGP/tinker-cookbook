# research_blogs

Home for comprehensive, technical, figure-driven blog posts distilled from the
experiment work in this project.

## The journal → blog relationship (two different artifacts)

- **`../JOURNAL.md`** = the **lab notebook**: chronological, append-only, raw,
  complete. Every experiment with config, checkpoint id, observed numbers,
  interpretation, decision. It is the *source of truth* and is never curated.
- **`research_blogs/`** = the **narrative**: thematic, curated, iteratively
  rewritten, figure-first. Distilled *from* the journal. A post is built section
  by section over days — outline → draft a section → make its figure(s) → tighten
  the claim → move on → revisit. Intro and title are written last.

The journal feeds the blog; the blog is not the journal.

## Correlation key (journal ↔ run ↔ W&B ↔ figures)

Each experiment in the journal records its checkpoint id. The persistent run dir
(`~/Desktop/legal_rl_runs/expN/`) links that checkpoint to its W&B run and its
`metrics.jsonl`. So any figure can be traced back to an exact run + checkpoint +
journal entry.

| Exp | Checkpoint | Run dir / W&B |
|---|---|---|
| Exp 3 | tinker://54e51bd9… | legal_rl_runs/exp3 · wandb 9l3rmxvw |
| Exp 4 | tinker://ba82dc9c… | legal_rl_runs/exp4 · wandb 7jp0o05h |
| Exp 5 | tinker://4ab56487… | legal_rl_runs/exp5 · wandb vsrrzmop |

## Posts

- `legal_agentic_rl/` — "Can you RL a legal research agent?" — **FULL DRAFT DONE**
  - `draft.md` — the complete article (12 sections + TL;DR, figures embedded).
  - `figures/` — 9 generated charts.
  - `make_figures.py` — regenerates all figures from journal numbers + exp5 curve.
  - `OUTLINE.md` — the planning record (claim/evidence/figure per section).
  - Remaining: author voice pass + port to publishing platform.
