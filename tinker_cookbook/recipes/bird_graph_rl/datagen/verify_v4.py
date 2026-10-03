"""Independent checks of the second training set (amendment D), run by the training side.

Recomputes, from the files alone and from the live graph, what the generator reports about
itself: no training structure equals a held-out signature or uses a held-out component, no
instance is shared with a held-out set, every stored answer is what the query returns now, and
no counting query counts repeated matches of the same entity.
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
import re
from pathlib import Path
from typing import Any

import chz
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from tinker_cookbook.recipes.bird_graph_rl.baseline_eval import row_key

HERE = Path(__file__).parent


@chz.chz
class Config:
    frozen_dir: str = str(HERE / "out")
    v4_dir: str = str(HERE / "out" / "v4")
    suffix: str = ""  # "_batch2" for the second batch
    env_file: str = ".env"
    out_path: str | None = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def components(signature: str) -> set[str]:
    """Same decomposition as ``structures.components``, from the stored signature."""
    sig = json.loads(signature)
    values = [json.dumps([key, sig[key]], sort_keys=True) for key in ("path", "aggregation", "grouping", "ordering")]
    values += [json.dumps(["filter", item]) for item in sig["filters"]]
    values += [json.dumps(["extra", item]) for item in sig["extras"]]
    values.append(json.dumps(["aggregation_extras", sig["aggregation"], sig["extras"]]))
    return set(values)


def instance_key(inst: dict[str, Any]) -> str:
    return json.dumps([inst["cypher"], inst["params"]], sort_keys=True)


async def main(cfg: Config) -> None:
    frozen, v4 = Path(cfg.frozen_dir), Path(cfg.v4_dir)
    frozen_structures = {s["structure_id"]: s for s in read_jsonl(frozen / "structures.jsonl")}
    frozen_instances = read_jsonl(frozen / "instances.jsonl")
    instances = read_jsonl(v4 / f"instances_v4_train{cfg.suffix}.jsonl")
    structures = {s["structure_id"]: s for s in read_jsonl(v4 / "structures_v4_train.jsonl")}
    for extra in sorted(v4.glob("structures_v4_train_*.jsonl")):
        structures.update({s["structure_id"]: s for s in read_jsonl(extra)})
    used = {i["structure_id"] for i in instances}
    report: dict[str, Any] = {"instances": len(instances), "structures_used": len(used)}

    held_signatures = {s["signature"] for s in frozen_structures.values() if s["split"] != "train"}
    held_components = {c for s in frozen_structures.values() for c in s["unseen_components"]}
    report["structures_missing_definition"] = sorted(used - structures.keys())
    report["signature_collisions"] = sorted(
        sid for sid in used & structures.keys() if structures[sid]["signature"] in held_signatures
    )
    report["heldout_components_used"] = sorted(
        {c for sid in used & structures.keys() for c in components(structures[sid]["signature"]) & held_components}
    )
    report["reused_structures_not_in_training_split"] = sorted(
        sid for sid in used if sid in frozen_structures and frozen_structures[sid]["split"] != "train"
    )
    report["reused_structures"] = sum(1 for sid in used if sid in frozen_structures)
    report["new_structures"] = sum(1 for sid in used if sid not in frozen_structures)

    held_ids = {i["instance_id"] for i in frozen_instances if i["split"] != "train"}
    held_keys = {instance_key(i) for i in frozen_instances if i["split"] != "train"}
    report["instances_with_heldout_id"] = sorted(i["instance_id"] for i in instances if i["instance_id"] in held_ids)
    report["instances_equal_to_heldout_query"] = sorted(
        i["instance_id"] for i in instances if instance_key(i) in held_keys
    )
    report["duplicate_instance_ids"] = len(instances) - len({i["instance_id"] for i in instances})
    report["duplicate_queries"] = len(instances) - len({instance_key(i) for i in instances})
    per_structure = collections.Counter(i["structure_id"] for i in instances)
    report["max_instances_per_structure"] = max(per_structure.values())

    load_dotenv(cfg.env_file, override=True)
    driver = AsyncGraphDatabase.driver(
        os.environ["BIRD_NEO4J_URI"], auth=(os.environ["BIRD_NEO4J_USER"], os.environ["BIRD_NEO4J_PASSWORD"])
    )

    async def run(query: str, params: dict[str, Any]) -> list[list[Any]]:
        async with driver.session(database="neo4j") as session:
            result = await session.run(query, params)
            return [list(record.values()) async for record in result]

    mismatched: list[str] = []
    repeated_match_counts: list[dict[str, Any]] = []
    count_answers: collections.Counter[str] = collections.Counter()
    empty = 0
    for inst in instances:
        rows = await run(inst["cypher"], inst["params"])
        stored = [list(r.values()) if isinstance(r, dict) else r for r in inst["rows"]]
        if sorted(row_key(r) for r in rows) != sorted(row_key(r) for r in stored):
            mismatched.append(inst["instance_id"])
        empty += not rows
        # A plain count over a traversal counts matches; if counting distinct entities gives a
        # different number, the question wording decides which is right, so list it for reading.
        plain = re.findall(r"count\((n\d+)\)", inst["cypher"])
        if plain:
            distinct_rows = await run(re.sub(r"count\((n\d+)\)", r"count(DISTINCT \1)", inst["cypher"]), inst["params"])
            if sorted(row_key(r) for r in distinct_rows) != sorted(row_key(r) for r in rows):
                repeated_match_counts.append(
                    {"instance_id": inst["instance_id"], "cypher": inst["cypher"], "rows": rows[:3], "distinct_rows": distinct_rows[:3]}
                )
        if inst.get("shape", {}).get("aggregation") in ("count", "count distinct") and len(rows) == 1 and len(rows[0]) == 1:
            value = rows[0][0]
            count_answers["0" if value == 0 else "1" if value == 1 else "2-9" if value < 10 else "10+"] += 1
    await driver.close()
    report["answers_not_reproduced"] = mismatched
    report["empty_answers"] = empty
    report["plain_counts_checked"] = sum(1 for i in instances if re.search(r"count\(n\d+\)", i["cypher"]))
    report["plain_counts_that_differ_from_distinct"] = repeated_match_counts
    report["single_value_count_answers"] = dict(count_answers)
    report["range_filters_with_equal_bounds"] = sum(
        1 for i in instances if "lower" in i["params"] and i["params"].get("lower") == i["params"].get("upper")
    )
    report["rows_per_answer"] = dict(
        collections.Counter("1" if i["n_rows"] == 1 else "2-10" if i["n_rows"] <= 10 else "11-50" if i["n_rows"] <= 50 else "51+" for i in instances)
    )
    text = json.dumps(report, indent=1, default=str)
    if cfg.out_path:
        Path(cfg.out_path).expanduser().write_text(text)
    print(text)


if __name__ == "__main__":
    asyncio.run(main(chz.entrypoint(Config)))
