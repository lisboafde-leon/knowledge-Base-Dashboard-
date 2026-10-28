"""Checks for Phase 3: extraction with citations and the validator.

Run from the kb_mvp folder (after python -m kb.ingest):
    python tests/check_extract.py

Uses the mock model, so no API key is needed.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kb.extract import STORE, extract_project  # noqa: E402
from kb.llm import MockLLM  # noqa: E402
from kb.validate import validate  # noqa: E402

key = json.loads((ROOT / "corpus" / "answer_key.json").read_text())["projects"]
results = []


def check(name, cond):
    results.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


clean = MockLLM()
facts = {p: extract_project("week2", p, clean) for p in key}

# 1. Clean run: every claim is supported, and the content matches the answer key.
for p, f in facts.items():
    exp = key[p]
    check(f"{p}: zero unsupported claims", f["validation"]["unsupported"] == 0)
    check(f"{p}: status is '{exp['status']}'", (f["status"] or {}).get("text") == exp["status"])
    check(f"{p}: {len(exp['decisions'])} decisions", len(f["decisions"]) == len(exp["decisions"]))
    check(f"{p}: {len(exp['blockers'])} blockers", len(f["blockers"]) == len(exp["blockers"]))
    check(f"{p}: {len(exp['next_steps'])} next steps", len(f["next_steps"]) == len(exp["next_steps"]))
    if "go_live" in exp:
        check(f"{p}: go live is {exp['go_live']} (status doc wins over deck)",
              (f["go_live"] or {}).get("text") == exp["go_live"])

check("OCR: March vs April conflict is surfaced, not hidden",
      len(facts["medical-records-ocr"]["conflicts"]) == 1)
check("Pharmacy: courier decision names MedDash, not the old vendor",
      any("MedDash" in d["text"] for d in facts["pharmacy-delivery"]["decisions"]))

# 2. Injected hallucination: the validator must catch it.
dirty = extract_project("week2", "medical-records-ocr", MockLLM(inject_error=True))
flagged = [p for p in dirty["validation"]["problems"] if "does not exist" in " ".join(p["issues"])]
check("validator flags a citation to a chunk that does not exist", len(flagged) == 1)

# 3. Other failure types, built by tampering with a good answer.
chunks = STORE.chunks("week2", "medical-records-ocr")
base = facts["medical-records-ocr"]


def tampered(fn):
    f = copy.deepcopy(base)
    f.pop("validation", None)
    fn(f)
    return validate(f, "medical-records-ocr", chunks)["validation"]["unsupported"]


check("validator flags evidence that is not in the cited chunk",
      tampered(lambda f: f["decisions"][0].update(evidence="Vendor chosen was ScanPro")) == 1)
check("validator flags a claim with no sources",
      tampered(lambda f: f["blockers"][0].update(sources=[])) == 1)
check("validator flags a citation from another project",
      tampered(lambda f: f["risks"][0].update(
          sources=["clinical-ai/weekly_status.docx#blockers-1"])) == 1)
check("validator flags a status outside the allowed values",
      tampered(lambda f: f["status"].update(text="Kind of okay")) == 1)

print(f"\n{sum(results)}/{len(results)} checks passed.")
