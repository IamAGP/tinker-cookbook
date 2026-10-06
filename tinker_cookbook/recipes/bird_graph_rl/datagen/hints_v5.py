"""Question-grounded hint overrides for Amendment E; never connects to Neo4j.

Only reads generated datagen artifacts. Every selected explanation keeps the
literal question span and the stored-query evidence that justified it.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "v4"
TARGET = OUT / "hints_v5.jsonl"
REPORT = OUT / "hints_v5_report.json"
CHECKPOINT = OUT / "CHECKPOINT.md"
ALLOWED = {TARGET, REPORT, CHECKPOINT}
STOP = set("a an the of to for from in on at by with and or as is are was were be been being its their it they this that those these which what how when give show return list each all any only once per no not than most least first second third one two three into among do does did have has had whose without both including include refers".split())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def frozen_hashes() -> dict[str, str]:
    return {str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((HERE / "out").rglob("*"))
            if path.is_file() and path not in ALLOWED}


def content_words(value: str) -> set[str]:
    # Literal spans already enforce stronger grounding than this diagnostic.
    return {word for word in re.findall(r"[a-z]+", value.casefold()) if word not in STOP}


@dataclass(frozen=True)
class Clause:
    phrase: str
    meaning: str
    kind: str
    evidence: tuple[str, ...]

    def text(self) -> str:
        return f"{self.phrase} refers to {self.meaning}"


def candidates(instance: dict, question: str) -> list[Clause]:
    query = instance["cypher"]
    params = instance["params"]
    masked = question
    # Do not mistake a word inside a quoted title or display name for an
    # attribute the question asks for. Preserve offsets into the original.
    for key in ("name", "other_name", "title"):
        value = params.get(key)
        if isinstance(value, str):
            literal = "'" + value + "'"
            masked = masked.replace(literal, " " * len(literal))
    result: list[Clause] = []

    def add(pattern: str, meaning: str, kind: str, evidence: tuple[str, ...]) -> None:
        match = re.search(pattern, masked, re.IGNORECASE)
        if match and all(fragment in query for fragment in evidence):
            phrase = question[match.start():match.end()]
            if ";" not in phrase and content_words(phrase):
                result.append(Clause(phrase, meaning, kind, evidence))

    date_root = re.search(r"\(n0:(\w+)\)", query)
    source_date = "CreaionDate" if date_root and date_root[1] in {"Post", "Question", "Answer"} else "CreationDate"
    if "date" in params:
        add(r"(?:joined|created) on " + re.escape(params["date"]),
            f"the calendar day of {source_date}, from midnight up to but excluding the next midnight",
            "calendar_day", ("n0.creationDate >= localdatetime($date", "n0.creationDate < localdatetime($date", "duration({days:1})"))

    field_names = {"reputation": "Reputation", "score": "Score", "stored usage count": "Count"}
    prop_names = {"reputation": "reputation", "score": "score", "stored usage count": "count"}
    for phrase, field in field_names.items():
        prop = prop_names[phrase]
        if "lower" in params and "upper" in params:
            if params["lower"] == params["upper"]:
                add(re.escape(phrase) + r" exactly " + re.escape(str(params["lower"])) + r"\b",
                    f"{field} equal to the stated number", "inclusive_range",
                    (f"n0.{prop} >= $lower", f"n0.{prop} <= $upper"))
            else:
                add(re.escape(phrase) + r" between " + re.escape(str(params["lower"])) + r" and " + re.escape(str(params["upper"])) + r" inclusive",
                    f"{field} within the stated range, including both endpoints", "inclusive_range",
                    (f"n0.{prop} >= $lower", f"n0.{prop} <= $upper"))

    if "measurement >= $condition" in query:
        metric = re.search(r"n\d+\.(\w+) AS measurement", query)
        if metric:
            field = {"score": "Score", "reputation": "Reputation", "count": "Count"}[metric[1]]
            number = re.escape(str(params["condition"]))
            add(r"(?:scores? (?:are |of )?(?:at least|no less than) " + number + r"|scoring " + number + r" or more|scores? of " + number + r" or (?:higher|more)|minimum score of " + number + r"|reach or exceed " + number + r" points|reputation (?:of |must be )?at least " + number + r"|meeting or exceeding " + number + r" reputation)",
                f"{field} greater than or equal to the stated threshold", "conditional_threshold", ("measurement >= $condition",))

    if "positive_percentage" in query:
        metric = re.search(r"n\d+\.(\w+) AS measurement", query)
        assert metric and metric[1] == "score"
        add(r"percentage|positive-score share|proportion",
            "the percentage of distinct matching Id values whose Score is above zero, with missing Score included in the total",
            "percentage", ("WITH DISTINCT", " AS identity", "measurement>0", "/count(*)"))

    if "title IS NULL" in query:
        add(r"no recorded title|untitled posts", "Title being absent", "null_filter", (".title IS NULL",))
    if "title IS NOT NULL" in query:
        add(r"(?:a )?recorded title|titled posts", "Title being present", "null_filter", (".title IS NOT NULL",))
    if "location IS NULL" in query:
        add(r"no recorded location", "Location being absent", "null_filter", (".location IS NULL",))

    if "RETURN DISTINCT" in query:
        add(r"distinct (?:stored usage count|view counts|scores|titles?|tag names|question titles|preview)|unique (?:list|titles|tag names)|different (?:titles?|scores|comment previews)|without repeated text|deduplicated title list|only once|suppress duplicate previews",
            "uniqueness of the returned values, so equal displayed values appear only once", "distinct_projection", ("RETURN DISTINCT",))
    elif "count(DISTINCT" in query:
        match = re.search(r"count\(DISTINCT n\d+\.(\w+)\)", query)
        noun = "comments" if match and match[1] == "commentId" else "answers"
        add(r"distinct (?:qualifying comments|answer counts)",
            f"different Id values of the {noun}, counted once per result group", "distinct_group_count", (match[0],) if match else ())
    elif "WITH DISTINCT" in query:
        add(r"distinct posts|distinct questions|different posts|different authors|distinct authors|distinct author|different tags|different tag|each user once per named user|each author once|each author only once|each post once|distinct comments|different comments",
            "different matching Id values counted once" + (" per named user" if " AS person," in query else ""),
            "distinct_entities", ("WITH DISTINCT", " AS identity"))

    # "First named" must mean first in the question, not merely $name. A
    # subtraction question can mention the subtrahend first; leave that wording
    # to the ordinary field/name clauses rather than reverse its meaning.
    if ("reputation_difference" in query
            and question.find("'" + params["name"] + "'")
            < question.find("'" + params["other_name"] + "'")):
        add(r"Subtract the second total from the first|Subtract the latter total|first (?:total )?minus the second|former minus the latter|difference in that order|reputation-total difference",
            "the total Reputation for the first named user minus that for the second, counting each matching Id once per named user",
            "comparison", ("person=$name", "person=$other_name", ")-sum(", "WITH DISTINCT n0.displayName AS person"))

    # Explain previews before ordinary field names because the length and the
    # source Body/Text distinction are useful information.
    preview = re.search(r"left\(n\d+\.(body|text),120\)", query)
    if preview:
        field = "Body" if preview[1] == "body" else "Text"
        add(r"(?:the )?(?:first|opening) 120 (?:(?:body|text) )?characters(?: of (?:its body|each comment|the comments))?|120-character body excerpts?|first-120-character body excerpts",
            f"the first 120 characters of {field}", "preview", (preview[0],))
        if field == "Text":
            add(r"beginnings|beginning|opening text|120-character previews", "the first 120 characters of Text", "preview", (preview[0],))
    fallback = re.search(r"coalesce\(n\d+\.title,left\(n\d+\.body,120\)\)", query)
    if fallback:
        add(r"\btitles?\b", "Title when present, otherwise the first 120 characters of Body",
            "title_fallback", (fallback[0],))

    # These words are selected only outside quoted parameters. The queried
    # property is checked even when the field is used as a filter rather than a
    # returned column. Source spelling comes from DATA_HANDOFF and hints.py.
    for pattern, prop, field in [
        (r"(?:stored (?:tag )?|recorded )usage counts?", "count", "Count"),
        (r"reputation|reputable", "reputation", "Reputation"),
        (r"scores?|scoring", "score", "Score"),
        (r"view counts?|views", "viewCount", "ViewCount"),
        (r"display names?", "displayName", "DisplayName"),
        (r"tag names?", "tagName", "TagName"),
        (r"location", "location", "Location"),
        (r"titled|titles?", "title", "Title"),
    ]:
        add(r"\b(?:" + pattern + r")\b", field, "field_" + prop, ("." + prop,))

    output_date = re.search(r"RETURN n(\d+)\.creationDate AS", query)
    if output_date:
        label = re.search(r"\(n" + output_date[1] + r":(\w+)\)", query)
        field = "CreaionDate" if label and label[1] in {"Post", "Question", "Answer"} else "CreationDate"
        add(r"creation dates? and times?|creation date and time|date and time|created",
            f"{field}, including its time of day", "timestamp", (output_date[0],))
    # Detail lookup with creation-date extras on comments uses a WITH alias.
    extra_date = re.search(r"n(\d+)\.creationDate AS extra_field", query)
    if not output_date and extra_date:
        label = re.search(r"\(n" + extra_date[1] + r":(\w+)\)", query)
        field = "CreaionDate" if label and label[1] in {"Post", "Question", "Answer"} else "CreationDate"
        add(r"creation dates?", f"{field}, including its time of day", "timestamp", (extra_date[0],))

    if "anchor" in params:
        add(r"ID " + re.escape(str(params["anchor"])) + r"\b", "the source Id used to select the named entity", "anchor_id", (" = $anchor",))
    for key in ("name", "other_name", "title"):
        value = params.get(key)
        if isinstance(value, str) and ";" not in value:
            literal = "'" + value + "'"
            if literal in question:
                source = "Title" if key == "title" else "TagName" if "n0.tagName" in query else "DisplayName"
                prop = {"Title": "title", "TagName": "tagName", "DisplayName": "displayName"}[source]
                if f"n0.{prop}" in query and content_words(literal):
                    result.append(Clause(literal, f"the selected {source}", "anchor_" + source, (f"n0.{prop}", "$" + key)))
    return result


def select_clauses(instance: dict, question: str) -> list[Clause]:
    choices = candidates(instance, question)
    selected: list[Clause] = []
    # A range already explains its metric; a fallback already explains Title.
    covered: set[str] = set()
    for clause in choices:
        fields = set(re.findall(r"\b(?:Reputation|Score|Count|Title|Body|Text|DisplayName|TagName|CreationDate|CreaionDate|Location|ViewCount)\b", clause.meaning))
        if clause.kind.startswith("field_") and fields <= covered:
            continue
        if any(prior.kind == clause.kind for prior in selected):
            continue
        selected.append(clause)
        covered |= fields
        if len(selected) == 3:
            break
    return selected


def inspect() -> tuple[list[dict], dict[str, str], dict[str, list[Clause]]]:
    instances = read_jsonl(OUT / "instances_v4_train.jsonl")
    questions = {row["instance_id"]: row["question"] for row in read_jsonl(OUT / "questions_v4_train.jsonl")}
    authored = {row["instance_id"]: select_clauses(row, questions[row["instance_id"]]) for row in instances if row.get("hint")}
    return instances, questions, authored


def audit(instances: list[dict], questions: dict[str, str], authored: dict[str, list[Clause]], rows: list[dict]) -> dict:
    by_id = {row["instance_id"]: row for row in instances}
    assert [row["instance_id"] for row in rows] == [row["instance_id"] for row in instances[:len(rows)]]
    failures: list[dict] = []
    zero_overlap: list[str] = []
    clause_counts: Counter[int] = Counter()
    kinds: Counter[str] = Counter()
    evidence: list[dict] = []
    stored_row_checks: Counter[str] = Counter()
    for row in rows:
        instance_id = row["instance_id"]
        instance = by_id[instance_id]
        clauses = authored.get(instance_id, [])
        if not instance.get("hint"):
            assert row["hint"] is None
            continue
        if not clauses:
            failures.append({"instance_id": instance_id, "reason": "No question-grounded clause with verified stored-query evidence."})
            continue
        assert row["hint"] == "; ".join(clause.text() for clause in clauses)
        assert 1 <= len(clauses) <= 3
        assert len(row["hint"].split(";")) == len(clauses)
        clause_counts[len(clauses)] += 1
        bad_overlap = False
        for clause in clauses:
            assert clause.phrase in questions[instance_id]
            assert all(fragment in instance["cypher"] for fragment in clause.evidence)
            assert " refers to " not in clause.phrase
            assert not re.search(r"CYPHER|MATCH|RETURN|WITH|\[:|\(n\d+:", clause.meaning)
            bad_overlap |= not (content_words(clause.phrase) & content_words(questions[instance_id]))
            kinds[clause.kind] += 1
        if bad_overlap:
            zero_overlap.append(instance_id)
        evidence.append({"instance_id": instance_id, "clauses": [{"phrase": c.phrase, "kind": c.kind, "stored_query_evidence": list(c.evidence)} for c in clauses], "stored_row_count_checked": len(instance["rows"])})
        assert len(instance["rows"]) == instance["n_rows"]
        if "RETURN DISTINCT" in instance["cypher"]:
            encoded = [json.dumps(value, sort_keys=True) for value in instance["rows"]]
            assert len(set(encoded)) == len(encoded)
            stored_row_checks["distinct_return_values"] += 1
        if "positive_percentage" in instance["cypher"]:
            for value in instance["rows"]:
                percentage = value["positive_percentage"]
                assert percentage is None or 0 <= percentage <= 100
            stored_row_checks["percentage_range"] += 1
        if any(c.kind == "preview" for c in clauses):
            for value in instance["rows"]:
                for key in ("comment_text", "answer_text"):
                    if key in value:
                        assert value[key] is None or len(value[key]) <= 120
            stored_row_checks["preview_length"] += 1
        if any(c.kind == "timestamp" for c in clauses):
            for value in instance["rows"]:
                if "created_on" in value and value["created_on"] is not None:
                    datetime.fromisoformat(value["created_on"])
            stored_row_checks["timestamp_format"] += 1
    hinted = sum(bool(row["hint"]) for row in rows)
    return {"records_written": len(rows), "hints_written": hinted, "without_hint": sum(row["hint"] is None for row in rows),
            "expected_records": len(instances), "original_hint_count": sum(bool(row.get("hint")) for row in instances),
            "hint_presence_preserved": all(bool(row["hint"]) == bool(by_id[row["instance_id"]].get("hint")) for row in rows),
            "clause_counts": dict(sorted(clause_counts.items())), "total_clauses": sum(k * v for k, v in clause_counts.items()),
            "explanation_kind_counts": dict(sorted(kinds.items())),
            "stored_row_check_counts": dict(sorted(stored_row_checks.items())),
            "hints_with_zero_content_word_overlap": len(zero_overlap), "zero_overlap_instance_ids": zero_overlap,
            "share_with_zero_content_word_overlap": len(zero_overlap) / hinted if hinted else None,
            "target_share_under": 0.05, "rule_2_unwritten": failures,
            "verification": "Literal question spans and stored Cypher evidence only; stored row counts checked, no graph connection or re-execution.",
            "content_word_rule": "Case-insensitive alphabetic tokens, excluding the helper's explicit stopword set; exact literal spans additionally required.",
            "clause_evidence": evidence}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--batch-size", type=int, default=80)
    args = parser.parse_args()
    instances, questions, authored = inspect()
    if args.preview:
        for index, instance in enumerate(instances):
            if instance.get("hint"):
                print(json.dumps({"index": index, "instance_id": instance["instance_id"], "question": questions[instance["instance_id"]], "hint": "; ".join(c.text() for c in authored[instance["instance_id"]])}, ensure_ascii=False))
        return
    prior_report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    baseline = prior_report.get("frozen_file_sha256", frozen_hashes())
    assert frozen_hashes() == baseline, "Frozen artifacts changed since the starting snapshot"
    rows = read_jsonl(TARGET) if TARGET.exists() else []
    audit(instances, questions, authored, rows)
    while len(rows) < len(instances):
        start = len(rows)
        batch = []
        for instance in instances[start:start + args.batch_size]:
            clauses = authored.get(instance["instance_id"], [])
            if instance.get("hint") and not clauses:
                raise ValueError(f"Cannot author hint under rule 2: {instance['instance_id']}")
            batch.append({"instance_id": instance["instance_id"], "hint": "; ".join(c.text() for c in clauses) if clauses else None})
        with TARGET.open("a") as stream:
            for row in batch:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
        rows.extend(batch)
        summary = audit(instances, questions, authored, rows)
        summary["frozen_file_sha256"] = baseline
        summary["frozen_files_unchanged"] = frozen_hashes() == baseline
        assert summary["frozen_files_unchanged"]
        summary["complete"] = len(rows) == len(instances)
        summary["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        REPORT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        with CHECKPOINT.open("a") as stream:
            stream.write(f"\n\n### Amendment E hint rewrite — {summary['updated_at_utc']}\n\n"
                         f"Saved {summary['records_written']} override records: {summary['hints_written']} hints, "
                         f"{summary['without_hint']} nulls. Content-word mismatch share: {summary['share_with_zero_content_word_overlap']:.6f}. "
                         f"Frozen-file hashes unchanged: {summary['frozen_files_unchanged']}. "
                         f"Remaining records: {len(instances) - len(rows)}. "
                         "Verified using stored question/query/rows only; no graph calls. "
                         "Next: finish batches and inspect the completed overrides.\n")
        print(json.dumps({k: summary[k] for k in ("records_written", "hints_written", "without_hint", "share_with_zero_content_word_overlap", "complete", "frozen_files_unchanged")}))


if __name__ == "__main__":
    main()
