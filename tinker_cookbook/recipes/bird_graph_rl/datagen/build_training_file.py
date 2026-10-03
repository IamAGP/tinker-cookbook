"""Join generated instances with their questions and hints into the file the RL environment reads.

Input: ``out/instances.jsonl`` (query, parameters, complete answer rows, split) and a questions
file (``instance_id``, ``question``, optional ``hint``). Output: one ``GraphQADatum`` per line.
Instances without a question are skipped and counted, never invented.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import chz


@chz.chz
class Config:
    instances_path: str
    questions_path: str
    out_path: str


def main(cfg: Config) -> None:
    questions: dict[str, dict[str, str]] = {}
    for line in Path(cfg.questions_path).expanduser().read_text().splitlines():
        if line.strip():
            q = json.loads(line)
            questions[q["instance_id"]] = q
    kept: collections.Counter[str] = collections.Counter()
    skipped = 0
    out = Path(cfg.out_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for line in Path(cfg.instances_path).expanduser().read_text().splitlines():
            if not line.strip():
                continue
            inst = json.loads(line)
            q = questions.get(inst["instance_id"])
            if q is None or not q.get("question", "").strip():
                skipped += 1
                continue
            rows = [list(r.values()) if isinstance(r, dict) else list(r) for r in inst["rows"]]
            f.write(json.dumps({
                "instance_id": inst["instance_id"], "question": q["question"].strip(),
                # Hints are generated per instance; a questions file may override one.
                "hint": (q.get("hint") or inst.get("hint") or "").strip(), "rows": rows, "n_rows": inst["n_rows"],
                "structure_id": inst["structure_id"], "hops": inst["hops"], "split": inst["split"],
            }, default=str) + "\n")
            kept[inst["split"]] += 1
    print(json.dumps({"written": dict(kept), "total": sum(kept.values()), "skipped_no_question": skipped}))


if __name__ == "__main__":
    main(chz.entrypoint(Config))
