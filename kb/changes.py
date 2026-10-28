"""Phase 4: what changed between two snapshots, and does it matter?

Usage, from the kb_mvp folder (after python -m kb.ingest):
    python -m kb.changes week1 week2
    KB_MODEL=claude python -m kb.changes week1 week2

Three layers, cheapest first:
  Layer 1  file hash identical            -> skip the file, nothing changed
  Layer 2  file hash changed, but every   -> "cosmetic": formatting only,
           chunk's text hash is identical     logged without calling the AI
  Layer 3  chunks whose words changed     -> added, removed or modified chunks
           (plain code finds them)            go to the AI, which says whether
                                              each one matters and explains it

Writes output/changes/<old>_to_<new>.json.
"""
import argparse
import json
import re
from pathlib import Path

from kb.llm import ClaudeLLM, LLMClient, MockLLM, Usage, estimate_tokens, get_client
from kb.store import JsonChunkStore

ROOT = Path(__file__).resolve().parent.parent
STORE = JsonChunkStore(ROOT / "output" / "store")
OUT = ROOT / "output" / "changes"


# ---------------------------------------------------------------- layers 1 to 3 (no AI)

def diff_snapshots(old: str, new: str, store=STORE) -> dict:
    old_files = {(m["project"], m["file"]): m for m in store.manifest(old)}
    new_files = {(m["project"], m["file"]): m for m in store.manifest(new)}
    old_chunks = {c.chunk_id: c for c in store.chunks(old)}
    new_chunks = {c.chunk_id: c for c in store.chunks(new)}

    report = {"unchanged_files": [], "cosmetic_files": [], "added_files": [],
              "removed_files": [], "changed_chunks": []}

    for key in sorted(old_files.keys() | new_files.keys()):
        project, file = key
        rel = f"{project}/{file}"
        o, n = old_files.get(key), new_files.get(key)
        if o and not n:
            report["removed_files"].append(rel)
        elif n and not o:
            report["added_files"].append(rel)
        if o and n and o["file_hash"] == n["file_hash"]:          # layer 1
            report["unchanged_files"].append(rel)
            continue

        def in_file(chunks):
            return {cid: c for cid, c in chunks.items() if c.project == project and c.file == file}

        oc, nc = in_file(old_chunks), in_file(new_chunks)
        pairs = []
        for cid in sorted(oc.keys() | nc.keys()):                 # layer 3
            a, b = oc.get(cid), nc.get(cid)
            if a and b and a.text_hash == b.text_hash:
                continue
            kind = "modified" if a and b else ("added" if b else "removed")
            ref = b or a
            pairs.append({"project": project, "file": file, "chunk_id": cid,
                          "section": ref.section, "location": ref.location, "kind": kind,
                          "old_text": a.text if a else None, "new_text": b.text if b else None})
        if o and n and not pairs:                                 # layer 2
            report["cosmetic_files"].append(rel)
        report["changed_chunks"] += pairs
    return report


# ---------------------------------------------------------------- interpretation (AI)

SYSTEM = """You review changes between two weekly versions of project documents for an
engineering team's leadership. For each changed chunk you get the old text and the new text.

For every chunk, decide:
  meaningful: true if a reader of a status report should know about it (dates, status,
              decisions, vendors, blockers, scope, numbers, new or removed items).
              false if it is rewording, formatting or style with the same meaning.
  summary:    one plain sentence saying what changed, e.g.
              "Go live moved from March 2027 to April 2027."

Return ONLY a JSON object:
{"changes": [{"chunk_id": str, "meaningful": bool, "summary": str}, ...]}
Include every chunk_id you were given, exactly once. Use only the text provided."""


def build_prompt(pairs) -> str:
    parts = []
    for p in pairs:
        parts.append(f"[{p['chunk_id']}] ({p['kind']}, section: {p['section']})\n"
                     f"OLD: {p['old_text'] or '(did not exist)'}\n"
                     f"NEW: {p['new_text'] or '(removed)'}")
    return "Changed chunks:\n\n" + "\n\n".join(parts)


WORD = re.compile(r"[A-Za-z0-9]+")


def _mock_verdict(p) -> tuple[bool, str]:
    """Simple rules standing in for a model. Added or removed chunks always matter.
    For edits, a change matters if the words that differ include a number or a
    capitalized word (names, dates, statuses). Otherwise it is treated as rewording."""
    if p["kind"] == "added":
        return True, f"New in {p['section']}: {p['new_text']}"
    if p["kind"] == "removed":
        return True, f"Removed from {p['section']}: {p['old_text']}"
    old_w, new_w = WORD.findall(p["old_text"]), WORD.findall(p["new_text"])
    diff = set(old_w) ^ set(new_w)
    important = [w for w in diff if any(ch.isdigit() for ch in w) or w[0].isupper()]
    if important:
        return True, f"{p['section']} now reads: \"{p['new_text']}\" (was: \"{p['old_text']}\")"
    return False, f"Rewording in {p['section']} with no change in meaning."


def interpret(pairs, client: LLMClient) -> tuple[list[dict], Usage | None]:
    if not pairs:
        return [], None
    user = build_prompt(pairs)
    if isinstance(client, MockLLM):
        answer = {"changes": [{"chunk_id": p["chunk_id"], "meaningful": m, "summary": s}
                              for p in pairs for m, s in [_mock_verdict(p)]]}
        usage = Usage(estimate_tokens(SYSTEM + user), estimate_tokens(json.dumps(answer)), "mock")
    else:
        answer, usage = client.complete_json(SYSTEM, user, {"pairs": pairs})

    # validate: every changed chunk gets exactly one verdict, no invented IDs
    verdicts = {}
    for v in answer.get("changes", []):
        if v.get("chunk_id") in {p["chunk_id"] for p in pairs}:
            verdicts.setdefault(v["chunk_id"], v)
    out = []
    for p in pairs:
        v = verdicts.get(p["chunk_id"])
        out.append({**p,
                    "meaningful": bool(v["meaningful"]) if v else True,
                    "summary": v["summary"] if v else "Model gave no verdict; needs human review.",
                    "needs_review": v is None})
    return out, usage


def detect_changes(old: str, new: str, client: LLMClient, store=STORE) -> dict:
    report = diff_snapshots(old, new, store)
    changes, usage = interpret(report["changed_chunks"], client)
    total_new = len(store.chunks(new))
    # Fair baseline: what it would cost to rerun the full Phase 3 extraction on every project.
    from kb.extract import SYSTEM as EXTRACT_SYSTEM, build_prompt as extract_prompt, projects_in
    full_reread = sum(estimate_tokens(EXTRACT_SYSTEM + extract_prompt(p, store.chunks(new, p)))
                      for p in projects_in(new, store))
    return {
        "from": old, "to": new,
        "changes": changes,
        "unchanged_files": report["unchanged_files"],
        "cosmetic_files": report["cosmetic_files"],
        "added_files": report["added_files"],
        "removed_files": report["removed_files"],
        "stats": {
            "files_compared": len(store.manifest(new)),
            "files_skipped_unchanged": len(report["unchanged_files"]),
            "files_cosmetic_only": len(report["cosmetic_files"]),
            "chunks_in_new_snapshot": total_new,
            "chunks_sent_to_ai": len(changes),
            "meaningful": sum(c["meaningful"] for c in changes),
            "minor": sum(not c["meaningful"] for c in changes),
            "needs_review": sum(c["needs_review"] for c in changes),
            "input_tokens": usage.input_tokens if usage else 0,
            "output_tokens": usage.output_tokens if usage else 0,
            "est_input_tokens_full_reextraction": full_reread,
            "model": usage.model if usage else "none",
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old", nargs="?", default="week1")
    ap.add_argument("new", nargs="?", default="week2")
    ap.add_argument("--model", help="mock or claude (default: KB_MODEL or mock)")
    args = ap.parse_args()

    result = detect_changes(args.old, args.new, get_client(args.model))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.old}_to_{args.new}.json"
    path.write_text(json.dumps(result, indent=2))

    s = result["stats"]
    print(f"{args.old} -> {args.new}: {s['files_compared']} files compared")
    print(f"   layer 1 skipped {s['files_skipped_unchanged']} unchanged files")
    print(f"   layer 2 marked {s['files_cosmetic_only']} file(s) as formatting only: {', '.join(result['cosmetic_files']) or 'none'}")
    print(f"   layer 3 sent {s['chunks_sent_to_ai']} of {s['chunks_in_new_snapshot']} chunks to the AI")
    print(f"   result: {s['meaningful']} meaningful, {s['minor']} minor, {s['needs_review']} need review")
    print(f"   tokens in/out {s['input_tokens']}/{s['output_tokens']} "
          f"(rerunning full extraction on every project would be about {s['est_input_tokens_full_reextraction']} in)\n")
    for c in result["changes"]:
        tag = "MEANINGFUL" if c["meaningful"] else "minor     "
        print(f"   {tag} {c['project']}: {c['summary']}")
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
