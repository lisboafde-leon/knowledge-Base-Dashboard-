"""Checks for Phase 4: change detection.

Run from the kb_mvp folder (after python -m kb.ingest):
    python tests/check_changes.py

Uses the mock model, so no API key is needed.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kb.changes import detect_changes, interpret  # noqa: E402
from kb.llm import LLMClient, MockLLM, Usage  # noqa: E402

key = json.loads((ROOT / "corpus" / "answer_key.json").read_text())
results = []


def check(name, cond):
    results.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


r = detect_changes("week1", "week2", MockLLM())
changes, stats = r["changes"], r["stats"]
by_id = {c["chunk_id"]: c for c in changes}

# Layer 1 and 2: no AI for files whose words did not change
check("layer 1 skips exactly the 5 unchanged files",
      sorted(r["unchanged_files"]) == sorted(key["unchanged_files"]))
check("layer 2 marks the font size deck as formatting only",
      r["cosmetic_files"] == ["medical-records-ocr/kickoff_deck.pptx"])
sent_files = {f"{c['project']}/{c['file']}" for c in changes}
check("no chunk from an unchanged or cosmetic file is sent to the AI",
      not sent_files & set(key["unchanged_files"] + r["cosmetic_files"]))
check("only the 3 weekly status docs have chunks sent to the AI",
      sent_files == {f"{p}/weekly_status.docx" for p in key["projects"]})

# Layer 3: the right chunks, classified correctly
check("12 changed chunks found out of 35", stats["chunks_sent_to_ai"] == 12)
check("OCR go live change is meaningful and mentions April 2027",
      by_id["medical-records-ocr/weekly_status.docx#current-status-2"]["meaningful"]
      and "April 2027" in by_id["medical-records-ocr/weekly_status.docx#current-status-2"]["new_text"])
check("OCR new rate limit blocker detected as added",
      by_id["medical-records-ocr/weekly_status.docx#blockers-2"]["kind"] == "added")
check("pharmacy courier switch to MedDash is meaningful",
      by_id["pharmacy-delivery/weekly_status.docx#decisions-1"]["meaningful"])
check("pharmacy 'will run' to 'plans to run' is classified as minor",
      not by_id["pharmacy-delivery/weekly_status.docx#next-steps-1"]["meaningful"])
check("clinical AI resolved blocker is meaningful",
      by_id["clinical-ai/weekly_status.docx#blockers-1"]["meaningful"])
check("clinical AI new rubric decision detected as added",
      by_id["clinical-ai/weekly_status.docx#decisions-2"]["kind"] == "added")
check("exactly 1 minor change and nothing left for review",
      stats["minor"] == 1 and stats["needs_review"] == 0)
check("every meaningful change in the answer key maps to a project with a meaningful chunk",
      all(any(c["project"] == k["project"] and c["meaningful"] for c in changes)
          for k in key["changes"] if k["meaningful"]))

# Efficiency
check("change review uses fewer input tokens than rerunning full extraction",
      stats["input_tokens"] < stats["est_input_tokens_full_reextraction"])

# No changes at all: comparing a snapshot with itself sends nothing to the AI
same = detect_changes("week2", "week2", MockLLM())
check("comparing a snapshot with itself finds no changes and costs zero tokens",
      not same["changes"] and same["stats"]["input_tokens"] == 0)


# A model that skips one chunk and invents another must be caught
class SloppyModel(LLMClient):
    name = "sloppy"

    def complete_json(self, system, user, context):
        pairs = context["pairs"]
        out = [{"chunk_id": p["chunk_id"], "meaningful": True, "summary": "x"} for p in pairs[1:]]
        out.append({"chunk_id": "made-up/chunk#1", "meaningful": True, "summary": "invented"})
        return {"changes": out}, Usage(1, 1, "sloppy")


FIELDS = ("project", "file", "chunk_id", "section", "location", "kind", "old_text", "new_text")
three_pairs = [{k: c[k] for k in FIELDS} for c in changes[:3]]
checked, _ = interpret(three_pairs, SloppyModel())
check("a skipped chunk is marked needs_review instead of disappearing",
      checked[0]["needs_review"] and sum(c["needs_review"] for c in checked) == 1)
check("an invented chunk ID from the model is ignored",
      all(c["chunk_id"] != "made-up/chunk#1" for c in checked))

print(f"\n{sum(results)}/{len(results)} checks passed.")
