"""Phase 5a: turn fact sheets and change logs into tables shaped like SharePoint lists.

Usage, from the kb_mvp folder:
    python -m kb.publish week1 week2

Reads  output/facts/<new>/*.json and output/changes/<old>_to_<new>.json
Writes output/tables/Projects.csv, Facts.csv, Changes.csv, Conflicts.csv,
       ReportRequests.csv (kept between runs), and output/pages/<project>.md

Each CSV has the exact columns a SharePoint list would have, so moving to
SharePoint later means creating lists with these columns and writing rows
through Microsoft Graph instead of to CSV.
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from kb.schema import LIST_FIELDS, SINGLE_FIELDS
from kb.store import JsonChunkStore

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
TABLES = OUTPUT / "tables"
PAGES = OUTPUT / "pages"
STORE = JsonChunkStore(OUTPUT / "store")

COLUMNS = {
    "Projects": ["ProjectID", "Title", "Status", "GoLive", "Purpose", "OpenBlockers", "Decisions",
                 "NextSteps", "Conflicts", "MeaningfulChanges", "UnsupportedClaims", "Snapshot",
                 "Model", "PublishedAt"],
    "Facts": ["FactID", "ProjectID", "Category", "Text", "Supported", "Issues", "ChunkID",
              "SourceFile", "SourceLocation", "Evidence"],
    "Changes": ["ChangeID", "ProjectID", "Meaningful", "Kind", "Summary", "Section", "SourceFile",
                "SourceLocation", "OldText", "NewText", "NeedsReview", "FromSnapshot", "ToSnapshot"],
    "Conflicts": ["ConflictID", "ProjectID", "Text", "ChunkIDs", "SourceFiles"],
    "ReportRequests": ["RequestID", "ProjectID", "RequestedBy", "RequestedAt", "Status",
                       "ReportFile", "CompletedAt"],
}

CATEGORY = {"purpose": "Purpose", "status": "Status", "go_live": "Go live", "decisions": "Decision",
            "blockers": "Blocker", "next_steps": "Next step", "risks": "Risk"}


def title_of(project: str) -> str:
    return project.replace("-", " ").title().replace("Ocr", "OCR").replace("Ai", "AI")


def where(location: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in location.items())


def write_table(name: str, rows: list[dict]):
    TABLES.mkdir(parents=True, exist_ok=True)
    with open(TABLES / f"{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS[name])
        w.writeheader()
        w.writerows(rows)


def read_table(name: str) -> list[dict]:
    path = TABLES / f"{name}.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_inputs(old: str, new: str):
    facts_dir = OUTPUT / "facts" / new
    facts = {p.stem: json.loads(p.read_text()) for p in sorted(facts_dir.glob("*.json"))
             if not p.name.startswith("_")}
    if not facts:
        raise SystemExit(f"No fact sheets in {facts_dir}. Run python -m kb.extract {new} first.")
    changes_path = OUTPUT / "changes" / f"{old}_to_{new}.json"
    changes = json.loads(changes_path.read_text()) if changes_path.exists() else {"changes": []}
    return facts, changes


def build_rows(old: str, new: str):
    facts, changes = load_inputs(old, new)
    chunk_map = {c.chunk_id: c for c in STORE.chunks(new)}
    now = datetime.now().isoformat(timespec="seconds")
    projects, fact_rows, change_rows, conflict_rows = [], [], [], []

    for pid, f in facts.items():
        def items(field):
            v = f.get(field)
            return [v] if isinstance(v, dict) else (v or [])

        n = 0
        for field in SINGLE_FIELDS + LIST_FIELDS:
            for item in items(field):
                for cid in item.get("sources") or [None]:
                    n += 1
                    c = chunk_map.get(cid)
                    fact_rows.append({
                        "FactID": f"{pid}-F{n:03d}", "ProjectID": pid, "Category": CATEGORY[field],
                        "Text": item.get("text", ""), "Supported": item.get("supported", False),
                        "Issues": "; ".join(item.get("issues", [])), "ChunkID": cid or "",
                        "SourceFile": c.file if c else "", "SourceLocation": where(c.location) if c else "",
                        "Evidence": item.get("evidence", ""),
                    })
        for i, conflict in enumerate(f.get("conflicts", []), start=1):
            conflict_rows.append({
                "ConflictID": f"{pid}-C{i:02d}", "ProjectID": pid, "Text": conflict["text"],
                "ChunkIDs": " | ".join(conflict["sources"]),
                "SourceFiles": " | ".join(sorted({chunk_map[s].file for s in conflict["sources"] if s in chunk_map})),
            })
        meaningful = sum(1 for c in changes["changes"] if c["project"] == pid and c["meaningful"])
        projects.append({
            "ProjectID": pid, "Title": title_of(pid),
            "Status": (f.get("status") or {}).get("text", "Unknown"),
            "GoLive": (f.get("go_live") or {}).get("text", ""),
            "Purpose": (f.get("purpose") or {}).get("text", ""),
            "OpenBlockers": len(f.get("blockers", [])), "Decisions": len(f.get("decisions", [])),
            "NextSteps": len(f.get("next_steps", [])), "Conflicts": len(f.get("conflicts", [])),
            "MeaningfulChanges": meaningful,
            "UnsupportedClaims": f.get("validation", {}).get("unsupported", 0),
            "Snapshot": new, "Model": f.get("run", {}).get("model", ""), "PublishedAt": now,
        })

    for i, c in enumerate(changes["changes"], start=1):
        change_rows.append({
            "ChangeID": f"CH{i:03d}", "ProjectID": c["project"], "Meaningful": c["meaningful"],
            "Kind": c["kind"], "Summary": c["summary"], "Section": c["section"],
            "SourceFile": c["file"], "SourceLocation": where(c["location"]),
            "OldText": c["old_text"] or "", "NewText": c["new_text"] or "",
            "NeedsReview": c.get("needs_review", False),
            "FromSnapshot": changes.get("from", old), "ToSnapshot": changes.get("to", new),
        })
    return projects, fact_rows, change_rows, conflict_rows


def write_page(project: dict, facts: list[dict], changes: list[dict], conflicts: list[dict]):
    """One markdown page per project. Readable by people, and by Claude or Copilot for Q&A."""
    PAGES.mkdir(parents=True, exist_ok=True)
    pid = project["ProjectID"]
    lines = [f"# {project['Title']}", "",
             f"**Status:** {project['Status']}  ",
             f"**Go live:** {project['GoLive'] or 'not stated'}  ",
             f"**Purpose:** {project['Purpose'] or 'not stated'}  ",
             f"*Generated from {project['Snapshot']} documents by {project['Model']}. "
             "Every line cites its source; verify before sharing.*", ""]

    def section(heading, category):
        rows = [f for f in facts if f["ProjectID"] == pid and f["Category"] == category]
        lines.append(f"## {heading}")
        if not rows:
            lines.append("None recorded.")
        for r in rows:
            flag = "" if str(r["Supported"]) == "True" else " **(unsupported: needs review)**"
            lines.append(f"- {r['Text']}{flag}  \n  _Source: {r['SourceFile']}, {r['SourceLocation']}_")
        lines.append("")

    section("Decisions", "Decision")
    section("Blockers", "Blocker")
    section("Next steps", "Next step")
    section("Risks", "Risk")
    lines.append("## Conflicts between documents")
    mine = [c for c in conflicts if c["ProjectID"] == pid]
    lines += [f"- {c['Text']}  \n  _Sources: {c['SourceFiles']}_" for c in mine] or ["None found."]
    lines += ["", "## What changed"]
    mc = [c for c in changes if c["ProjectID"] == pid and str(c["Meaningful"]) == "True"]
    lines += [f"- {c['Summary']}  \n  _Source: {c['SourceFile']}, {c['SourceLocation']}_" for c in mc] \
        or ["No meaningful changes."]
    (PAGES / f"{pid}.md").write_text("\n".join(lines) + "\n")


def publish(old: str, new: str):
    projects, facts, changes, conflicts = build_rows(old, new)
    write_table("Projects", projects)
    write_table("Facts", facts)
    write_table("Changes", changes)
    write_table("Conflicts", conflicts)
    if not (TABLES / "ReportRequests.csv").exists():     # keep request history between runs
        write_table("ReportRequests", [])
    for p in projects:
        write_page(p, facts, changes, conflicts)
    return projects, facts, changes, conflicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old", nargs="?", default="week1")
    ap.add_argument("new", nargs="?", default="week2")
    args = ap.parse_args()
    projects, facts, changes, conflicts = publish(args.old, args.new)
    print(f"Projects: {len(projects)} rows | Facts: {len(facts)} | Changes: {len(changes)} | "
          f"Conflicts: {len(conflicts)}")
    for p in projects:
        print(f"   {p['Title']}: {p['Status']}, go live {p['GoLive'] or 'n/a'}, "
              f"{p['OpenBlockers']} blockers, {p['MeaningfulChanges']} meaningful changes")
    print(f"Saved tables to {TABLES} and pages to {PAGES}")


if __name__ == "__main__":
    main()
