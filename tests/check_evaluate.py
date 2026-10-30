"""Checks for Phase 6: the evaluation harness.

Run from the kb_mvp folder:
    python tests/check_evaluate.py

Uses the mock model, so no API key is needed.
"""
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kb.changes import detect_changes  # noqa: E402
from kb.evaluate import EVAL, KEY_PATH, evaluate_model, score_changes, similarity, write_report  # noqa: E402
from kb.ingest import ingest  # noqa: E402
from kb.llm import MockLLM  # noqa: E402

key = json.loads(KEY_PATH.read_text())
results = []


def check(name, cond):
    results.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


for snap in ("week1", "week2"):
    ingest(snap)

# The matcher: paraphrases match, wrong names or numbers do not
check("paraphrase matches ('Confidence threshold for human review set at 0.85')",
      similarity("Human review confidence threshold 0.85", "Confidence threshold for human review set at 0.85") >= 0.6)
check("stale vendor does not match the new one",
      similarity("MedDash is the courier partner (replaced SwiftRoute)", "SwiftRoute selected as the courier partner") == 0)
check("wrong number does not match",
      similarity("Expand test batch to 500 forms", "Expand the test batch to 300 forms") == 0)

# Mock baseline
mock = evaluate_model("mock")
e, c, ch = mock["extraction"], mock["conflicts"], mock["changes"]
check("mock: status and go live 100% correct", e["status_accuracy"] == 1 and e["go_live_accuracy"] == 1)
check("mock: decisions, blockers and next steps F1 is 100%", e["items_f1"] == 1)
check("mock: zero unsupported claims", e["unsupported"] == 0)
check("mock: finds 1 of 2 contradictions and misses the clinic count one",
      c["conflict_recall"] == 0.5 and "clinics" in c["missed"][0])
check("mock: all 12 changed chunks detected, none extra",
      ch["detection_recall"] == 1 and ch["detection_precision"] == 1)
check("mock: every change classified correctly, rewording marked minor",
      ch["classification_accuracy"] == 1 and ch["noise_marked_minor"] == ch["noise_total"] == 1)
check("mock: formatting only deck caught", ch["cosmetic_files_ok"])

# The scores react to errors
noisy = evaluate_model("mock-noisy")
check("noisy mock: invented next steps raise the unsupported rate", noisy["extraction"]["unsupported_per_100"] > 0)
check("noisy mock: invented items lower precision but not recall",
      noisy["extraction"]["items_precision"] < 1 and noisy["extraction"]["items_recall"] == 1)

changes = detect_changes("week1", "week2", MockLLM())
bad = copy.deepcopy(changes)
for row in bad["changes"]:
    if row["chunk_id"] == "pharmacy-delivery/weekly_status.docx#next-steps-1":
        row["meaningful"] = True
check("a model that calls the rewording meaningful scores 11 of 12",
      abs(score_changes(bad, key)["classification_accuracy"] - 11 / 12) < 0.01)

# Missing keys: skipped, not crashed, and named in the report
saved = {k: os.environ.pop(k, None) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_FOUNDRY_API_KEY")}
skipped = evaluate_model("claude:claude-haiku-5-5")
foundry = evaluate_model("foundry:sonnet")
for k, v in saved.items():
    if v:
        os.environ[k] = v
check("Claude without a key is skipped with a reason", skipped["skipped"] and "ANTHROPIC_API_KEY" in skipped["reason"])
check("Foundry without a key is skipped with a reason", foundry["skipped"] and "FOUNDRY" in foundry["reason"])

write_report([mock, noisy, skipped])
report = (EVAL / "comparison.md").read_text()
check("comparison report written with both models and the skip note",
      "| mock | mock-noisy |" in report and "skipped" in report and (EVAL / "comparison.csv").exists())
check("per model results saved (facts, changes, score)",
      all((EVAL / "mock" / f).exists() for f in ("score.json", "changes.json", "facts")))

print(f"\n{sum(results)}/{len(results)} checks passed.")
