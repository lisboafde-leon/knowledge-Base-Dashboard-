"""Run the whole pipeline in order. This is what the 7 a.m. job will do later.

Usage, from the kb_mvp folder:
    python -m kb.run                    # week1 -> week2 with the mock model
    python -m kb.run week1 week2
    KB_MODEL=claude python -m kb.run    # same, with Claude

Steps: ingest both snapshots, extract fact sheets for the new one, detect
changes, publish tables and pages, then build any pending report requests.
"""
import argparse
import json

from kb.changes import OUT as CHANGES_DIR, detect_changes
from kb.extract import FACTS, extract_project, projects_in
from kb.ingest import ingest
from kb.llm import get_client
from kb.publish import publish
from kb.report import process_requests


def run(old: str, new: str, model: str | None = None):
    client = get_client(model)
    print(f"1/5 ingest {old} and {new}")
    for snap in (old, new):
        chunks, manifest = ingest(snap)
        print(f"     {snap}: {len(manifest)} files, {len(chunks)} chunks")

    print(f"2/5 extract fact sheets for {new} with {client.name}")
    out = FACTS / new
    out.mkdir(parents=True, exist_ok=True)
    for p in projects_in(new):
        facts = extract_project(new, p, client)
        (out / f"{p}.json").write_text(json.dumps(facts, indent=2))
        print(f"     {p}: {facts['validation']['claims']} claims, "
              f"{facts['validation']['unsupported']} unsupported")

    print(f"3/5 detect changes {old} -> {new}")
    result = detect_changes(old, new, client)
    CHANGES_DIR.mkdir(parents=True, exist_ok=True)
    (CHANGES_DIR / f"{old}_to_{new}.json").write_text(json.dumps(result, indent=2))
    s = result["stats"]
    print(f"     {s['chunks_sent_to_ai']} chunks reviewed: {s['meaningful']} meaningful, {s['minor']} minor")

    print("4/5 publish tables and project pages")
    projects, facts, changes, conflicts = publish(old, new)
    print(f"     {len(projects)} projects, {len(facts)} facts, {len(changes)} changes, {len(conflicts)} conflicts")

    print("5/5 build pending report requests")
    done = process_requests()
    print(f"     {len(done)} report(s) built")
    print("Done.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old", nargs="?", default="week1")
    ap.add_argument("new", nargs="?", default="week2")
    ap.add_argument("--model")
    args = ap.parse_args()
    run(args.old, args.new, args.model)


if __name__ == "__main__":
    main()
