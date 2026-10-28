"""Plain code that checks the AI's answer. No AI involved.

For every claim it asks:
  1. Does it cite at least one source?
  2. Does every cited chunk ID actually exist?
  3. Does every cited chunk belong to this project?
  4. Does the evidence quote really appear in one of the cited chunks?
  5. For status, is the value one of the allowed options?

Claims that fail are kept but marked supported = false with the reason, so
they show up for human review instead of silently disappearing.
"""
import re

from kb.schema import LIST_FIELDS, SINGLE_FIELDS, STATUS_VALUES


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower().rstrip(".")


def check_item(item: dict, field: str, project: str, chunk_map: dict) -> list[str]:
    issues = []
    sources = item.get("sources") or []
    if not item.get("text"):
        issues.append("empty claim")
    if not sources:
        issues.append("no source cited")
    for sid in sources:
        if sid not in chunk_map:
            issues.append(f"cited chunk does not exist: {sid}")
        elif chunk_map[sid].project != project:
            issues.append(f"cited chunk belongs to another project: {sid}")
    real = [chunk_map[s] for s in sources if s in chunk_map]
    if real and field != "conflicts":
        ev = _norm(item.get("evidence"))
        if not ev:
            issues.append("no evidence quote")
        elif not any(ev in _norm(c.text) for c in real):
            issues.append("evidence quote not found in cited chunks")
    if field == "conflicts" and len(set(sources)) < 2:
        issues.append("a conflict must cite at least two chunks")
    if field == "status" and item.get("text") not in STATUS_VALUES:
        issues.append(f"status '{item.get('text')}' is not one of {STATUS_VALUES}")
    return issues


def validate(facts: dict, project: str, chunks: list) -> dict:
    chunk_map = {c.chunk_id: c for c in chunks}
    total = supported = 0
    problems = []

    def visit(item, field):
        nonlocal total, supported
        issues = check_item(item, field, project, chunk_map)
        item["supported"] = not issues
        item["issues"] = issues
        total += 1
        supported += not issues
        if issues:
            problems.append({"field": field, "text": item.get("text"), "issues": issues})

    for f in SINGLE_FIELDS:
        if facts.get(f):
            visit(facts[f], f)
    for f in LIST_FIELDS + ["conflicts"]:
        for item in facts.get(f) or []:
            visit(item, f)

    facts["validation"] = {
        "claims": total,
        "supported": supported,
        "unsupported": total - supported,
        "problems": problems,
    }
    return facts
