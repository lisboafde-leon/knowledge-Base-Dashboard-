"""Phase 3: turn a project's chunks into a validated, cited fact sheet.

Usage, from the kb_mvp folder:
    python -m kb.extract week2                  # mock model, all projects
    python -m kb.extract week2 --project clinical-ai
    KB_MODEL=claude python -m kb.extract week2  # real Claude, needs ANTHROPIC_API_KEY

Writes output/facts/<snapshot>/<project>.json and a run summary.
"""
import argparse
import json
from pathlib import Path

from kb.llm import get_client
from kb.schema import FORM_DESCRIPTION
from kb.store import JsonChunkStore
from kb.validate import validate

ROOT = Path(__file__).resolve().parent.parent
STORE = JsonChunkStore(ROOT / "output" / "store")
FACTS = ROOT / "output" / "facts"

SYSTEM = (
    "You are a careful project analyst at a healthcare organization's engineering team. "
    "You read project documents and fill in a fixed fact sheet. You never guess, never use "
    "outside knowledge, and you cite the exact chunk every claim comes from. When documents "
    "disagree, you report the conflict instead of resolving it.\n\n" + FORM_DESCRIPTION
)


def format_chunks(chunks) -> str:
    lines = []
    for c in chunks:
        where = ", ".join(f"{k} {v}" for k, v in c.location.items())
        lines.append(f"[{c.chunk_id}] ({c.file}, {where}, section: {c.section})\n{c.text}")
    return "\n\n".join(lines)


def build_prompt(project: str, chunks) -> str:
    return (f"Project folder: {project}\n"
            f"Number of chunks: {len(chunks)}\n\n"
            f"--- CHUNKS ---\n{format_chunks(chunks)}\n--- END CHUNKS ---\n\n"
            "Fill in the fact sheet for this project. Return only the JSON object.")


def extract_project(snapshot: str, project: str, client, store=STORE) -> dict:
    chunks = store.chunks(snapshot, project)
    if not chunks:
        raise SystemExit(f"No chunks for {project} in {snapshot}. Run python -m kb.ingest first.")
    user = build_prompt(project, chunks)
    raw, usage = client.complete_json(SYSTEM, user, {"project": project, "chunks": chunks})
    raw["project"] = project
    facts = validate(raw, project, chunks)
    facts["run"] = {"snapshot": snapshot, "model": usage.model, "chunks_sent": len(chunks),
                    "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    return facts


def projects_in(snapshot: str, store=STORE) -> list[str]:
    return sorted({c.project for c in store.chunks(snapshot)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", nargs="?", default="week2")
    ap.add_argument("--project")
    ap.add_argument("--model", help="mock or claude (default: KB_MODEL or mock)")
    ap.add_argument("--inject-error", action="store_true",
                    help="mock only: add one fake citation to prove the validator works")
    args = ap.parse_args()

    kwargs = {"inject_error": True} if args.inject_error else {}
    client = get_client(args.model, **kwargs)
    out_dir = FACTS / args.snapshot
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for project in [args.project] if args.project else projects_in(args.snapshot):
        facts = extract_project(args.snapshot, project, client)
        (out_dir / f"{project}.json").write_text(json.dumps(facts, indent=2))
        v, r = facts["validation"], facts["run"]
        status = (facts.get("status") or {}).get("text", "Unknown")
        print(f"{project}: status={status}, claims={v['claims']}, unsupported={v['unsupported']}, "
              f"conflicts={len(facts['conflicts'])}, tokens in/out={r['input_tokens']}/{r['output_tokens']}")
        for p in v["problems"]:
            print(f"   FLAGGED {p['field']}: {p['text']} -> {'; '.join(p['issues'])}")
        summary.append({"project": project, **v, **r, "status": status})

    (out_dir / "_run_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSaved to {out_dir}")


if __name__ == "__main__":
    main()
