"""Phase 6: score the pipeline against the answer key, one or more models side by side.

Usage, from the kb_mvp folder:
    python -m kb.evaluate                                   # mock only
    python -m kb.evaluate --models mock mock-noisy          # shows the scores react to errors
    python -m kb.evaluate --models mock claude:claude-haiku-5-5 claude:claude-sonnet-5-5
    python -m kb.evaluate --models mock foundry:<deployment-name>

A model that cannot start (no key yet) is reported as SKIPPED; the others still run.
Writes output/eval/<model>/ (facts, changes, score.json) and output/eval/comparison.md + .csv.

What is scored, all against corpus/answer_key.json:
  Extraction      status and go live exact match; decisions, blockers and next steps
                  matched item by item (precision, recall, F1)
  Grounding       unsupported claims per 100 (validator failures)
  Conflicts       planted contradictions found (recall) and false alarms (precision)
  Change review   changed chunks found, cosmetic file caught, meaningful vs minor accuracy
  Cost            measured tokens, estimated dollars, seconds per run
"""
import argparse
import csv
import json
import re
import time
from pathlib import Path

from kb.changes import detect_changes
from kb.extract import extract_project, projects_in
from kb.ingest import ingest
from kb.llm import MockLLM, get_client
from kb.store import JsonChunkStore

ROOT = Path(__file__).resolve().parent.parent
KEY_PATH = ROOT / "corpus" / "answer_key.json"
EVAL = ROOT / "output" / "eval"
STORE = JsonChunkStore(ROOT / "output" / "store")
LIST_FIELDS = ["decisions", "blockers", "next_steps"]

# Dollars per million tokens (input, output). Anthropic list prices, checked Oct 2026:
# https://platform.claude.com/docs/en/about-claude/pricing . Foundry bills the same rates
# (1.1x for US Data Zone deployments). Update when prices change.
PRICES = {"haiku-5-5": (0.10, 0.50), "sonnet-5-5": (2.0, 10.0), "opus-5-5": (4.0, 20.0)}


# ---------------------------------------------------------------- matching helpers

STOP = set("a an the of for to in on at by with and or is are was be as from that this its it after "
           "about per will plans run set has have".split())


def tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9.]+", (text or "").lower()):
        w = w.strip(".")
        if not w or w in STOP:
            continue
        for suffix in ("ing", "ed", "es", "s"):           # crude stemming: replaced ~ replaces
            if len(w) > 4 and w.endswith(suffix):
                w = w[: -len(suffix)]
                break
        out.add(w)
    return out


def critical(text: str) -> set[str]:
    """Names and numbers that must match exactly: words with a digit, an inner capital
    (MedDash, ClearScan), or a capital anywhere but the first word (API, PM)."""
    out = set()
    for i, w in enumerate(re.findall(r"[A-Za-z0-9.]+", text or "")):
        w = w.strip(".")
        if w and (any(ch.isdigit() for ch in w) or any(ch.isupper() for ch in w[1:])
                  or (i > 0 and w[0].isupper())):
            out |= tokens(w)
    return out


def similarity(expected: str, found: str) -> float:
    """Share of the expected item's key words found, or 0 if any name or number is missing."""
    e, f = tokens(expected), tokens(found)
    if not e or not critical(expected) <= f:
        return 0.0
    return len(e & f) / len(e)


def match_items(expected: list[str], found: list[str], threshold=0.6):
    """Greedy one to one matching. Returns (matched pairs, missed expected, extra found)."""
    pairs, used = [], set()
    scored = sorted(((similarity(e, f), i, j) for i, e in enumerate(expected) for j, f in enumerate(found)),
                    reverse=True)
    hit = set()
    for s, i, j in scored:
        if s >= threshold and i not in hit and j not in used:
            pairs.append((expected[i], found[j], round(s, 2)))
            hit.add(i)
            used.add(j)
    missed = [e for i, e in enumerate(expected) if i not in hit]
    extra = [f for j, f in enumerate(found) if j not in used]
    return pairs, missed, extra


def prf(tp, n_found, n_expected):
    precision = tp / n_found if n_found else (1.0 if n_expected == 0 else 0.0)
    recall = tp / n_expected if n_expected else (1.0 if n_found == 0 else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return round(precision, 3), round(recall, 3), round(f1, 3)


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ---------------------------------------------------------------- scoring

def score_extraction(facts: dict, key: dict) -> dict:
    per_project, tp = {}, {"found": 0, "expected": 0, "matched": 0}
    status_ok = go_live_ok = go_live_total = claims = unsupported = 0
    for pid, exp in key["projects"].items():
        f = facts[pid]
        status = (f.get("status") or {}).get("text")
        s_ok = status == exp["status"]
        status_ok += s_ok
        row = {"status": status, "status_ok": s_ok}
        if "go_live" in exp:
            go_live_total += 1
            g = (f.get("go_live") or {}).get("text")
            row.update(go_live=g, go_live_ok=norm(g) == norm(exp["go_live"]))
            go_live_ok += row["go_live_ok"]
        for field in LIST_FIELDS:
            found = [i["text"] for i in f.get(field, [])]
            pairs, missed, extra = match_items(exp[field], found)
            row[field] = {"precision_recall_f1": prf(len(pairs), len(found), len(exp[field])),
                          "missed": missed, "extra": extra}
            tp["found"] += len(found)
            tp["expected"] += len(exp[field])
            tp["matched"] += len(pairs)
        v = f.get("validation", {})
        claims += v.get("claims", 0)
        unsupported += v.get("unsupported", 0)
        row["unsupported"] = v.get("problems", [])
        per_project[pid] = row
    p, r, f1 = prf(tp["matched"], tp["found"], tp["expected"])
    n = len(key["projects"])
    return {
        "status_accuracy": round(status_ok / n, 3),
        "go_live_accuracy": round(go_live_ok / go_live_total, 3) if go_live_total else None,
        "items_precision": p, "items_recall": r, "items_f1": f1,
        "claims": claims, "unsupported": unsupported,
        "unsupported_per_100": round(100 * unsupported / claims, 1) if claims else 0.0,
        "per_project": per_project,
    }


def score_conflicts(facts: dict, key: dict) -> dict:
    found = []
    for pid, f in facts.items():
        for c in f.get("conflicts", []):
            files = {s.split("/")[1].split("#")[0] for s in c.get("sources", []) if "/" in s}
            found.append({"project": pid, "files": files, "text": c.get("text", "")})
    hits, matched_found = [], set()
    for k in key["contradictions"]:
        for i, c in enumerate(found):
            if i not in matched_found and c["project"] == k["project"] and set(k["files"]) <= c["files"]:
                hits.append(k["what"])
                matched_found.add(i)
                break
    missed = [k["what"] for k in key["contradictions"] if k["what"] not in hits]
    p, r, _ = prf(len(hits), len(found), len(key["contradictions"]))
    return {"conflict_precision": p, "conflict_recall": r, "found": len(found),
            "planted": len(key["contradictions"]), "missed": missed}


def score_changes(result: dict, key: dict) -> dict:
    expected = key["change_verdicts"]
    got = {c["chunk_id"]: c for c in result["changes"]}
    detected = set(got) & set(expected)
    correct = [cid for cid in detected if got[cid]["meaningful"] == expected[cid]]
    wrong = [{"chunk_id": cid, "expected": expected[cid], "summary": got[cid]["summary"]}
             for cid in detected if cid not in correct]
    noise = [cid for cid, m in expected.items() if not m]
    p, r, _ = prf(len(detected), len(got), len(expected))
    return {
        "detection_precision": p, "detection_recall": r,
        "classification_accuracy": round(len(correct) / len(expected), 3) if expected else 1.0,
        "noise_marked_minor": sum(1 for cid in noise if cid in got and not got[cid]["meaningful"]),
        "noise_total": len(noise),
        "cosmetic_files_ok": sorted(result["cosmetic_files"]) == sorted(key.get("cosmetic_files", [])),
        "needs_review": result["stats"]["needs_review"],
        "misclassified": wrong,
    }


def price_for(model: str):
    for k, v in PRICES.items():
        if k in model:
            return v
    return None


# ---------------------------------------------------------------- one model run

def evaluate_model(spec: str, old="week1", new="week2", key=None) -> dict:
    key = key or json.loads(KEY_PATH.read_text())
    label = spec.replace(":", "_").replace("/", "_")
    if spec == "mock":
        client = MockLLM()
    elif spec == "mock-noisy":
        client = MockLLM(inject_error=True)
    else:
        kind, _, model = spec.partition(":")
        try:
            client = get_client(kind, model or None)
        except SystemExit as e:
            return {"model": spec, "skipped": True, "reason": str(e)}

    t0 = time.time()
    try:
        facts, tok_in, tok_out = {}, 0, 0
        for pid in projects_in(new):
            f = extract_project(new, pid, client)
            facts[pid] = f
            tok_in += f["run"]["input_tokens"]
            tok_out += f["run"]["output_tokens"]
        changes = detect_changes(old, new, client)
    except Exception as e:                      # a model or network error should not kill the comparison
        return {"model": spec, "skipped": True, "reason": f"run failed: {e}"}
    tok_in += changes["stats"]["input_tokens"]
    tok_out += changes["stats"]["output_tokens"]
    seconds = round(time.time() - t0, 1)

    model_name = getattr(client, "model", client.name)
    prices = price_for(model_name)
    cost = round((tok_in * prices[0] + tok_out * prices[1]) / 1e6, 4) if prices else 0.0

    score = {
        "model": spec, "model_name": model_name, "skipped": False, "seconds": seconds,
        "input_tokens": tok_in, "output_tokens": tok_out, "est_cost_usd": cost,
        "tokens_are_estimates": isinstance(client, MockLLM),
        "extraction": score_extraction(facts, key),
        "conflicts": score_conflicts(facts, key),
        "changes": score_changes(changes, key),
    }
    out = EVAL / label
    (out / "facts").mkdir(parents=True, exist_ok=True)
    for pid, f in facts.items():
        (out / "facts" / f"{pid}.json").write_text(json.dumps(f, indent=2))
    (out / "changes.json").write_text(json.dumps(changes, indent=2))
    (out / "score.json").write_text(json.dumps(score, indent=2))
    return score


# ---------------------------------------------------------------- report

COLUMNS = [
    ("Status accuracy", lambda s: s["extraction"]["status_accuracy"], "pct"),
    ("Go live accuracy", lambda s: s["extraction"]["go_live_accuracy"], "pct"),
    ("Item F1 (decisions, blockers, next steps)", lambda s: s["extraction"]["items_f1"], "pct"),
    ("Unsupported claims per 100", lambda s: s["extraction"]["unsupported_per_100"], "num"),
    ("Conflict recall", lambda s: s["conflicts"]["conflict_recall"], "pct"),
    ("Change detection recall", lambda s: s["changes"]["detection_recall"], "pct"),
    ("Change classification accuracy", lambda s: s["changes"]["classification_accuracy"], "pct"),
    ("Formatting only file caught", lambda s: "yes" if s["changes"]["cosmetic_files_ok"] else "no", "txt"),
    ("Input / output tokens", lambda s: f"{s['input_tokens']:,} / {s['output_tokens']:,}"
     + (" (est.)" if s["tokens_are_estimates"] else ""), "txt"),
    ("Estimated cost per run (USD)", lambda s: f"${s['est_cost_usd']:.4f}", "txt"),
    ("Seconds per run", lambda s: s["seconds"], "num"),
]


def fmt(v, kind):
    if v is None:
        return "n/a"
    return f"{v * 100:.0f}%" if kind == "pct" else str(v)


def write_report(scores: list[dict]):
    EVAL.mkdir(parents=True, exist_ok=True)
    ran = [s for s in scores if not s["skipped"]]
    with open(EVAL / "comparison.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Metric"] + [s["model"] for s in ran])
        for name, get, kind in COLUMNS:
            w.writerow([name] + [fmt(get(s), kind) for s in ran])
    lines = ["# Phase 6 evaluation", "",
             "Scored against `corpus/answer_key.json` (3 projects, 12 changed chunks, 2 planted contradictions).", "",
             "| Metric | " + " | ".join(s["model"] for s in ran) + " |",
             "| --- |" + " --- |" * len(ran)]
    for name, get, kind in COLUMNS:
        lines.append(f"| {name} | " + " | ".join(fmt(get(s), kind) for s in ran) + " |")
    for s in scores:
        if s["skipped"]:
            lines += ["", f"**{s['model']} skipped:** {s['reason']}"]
    for s in ran:
        lines += ["", f"## {s['model']}: what it got wrong"]
        issues = []
        for pid, row in s["extraction"]["per_project"].items():
            if not row["status_ok"]:
                issues.append(f"{pid}: status was '{row['status']}'")
            if row.get("go_live_ok") is False:
                issues.append(f"{pid}: go live was '{row['go_live']}'")
            for field in LIST_FIELDS:
                for m in row[field]["missed"]:
                    issues.append(f"{pid}: missed {field[:-1].replace('_', ' ')} \"{m}\"")
                for x in row[field]["extra"]:
                    issues.append(f"{pid}: extra {field[:-1].replace('_', ' ')} \"{x}\"")
            for prob in row["unsupported"]:
                issues.append(f"{pid}: unsupported {prob['field']} \"{prob['text']}\" ({'; '.join(prob['issues'])})")
        issues += [f"missed contradiction: {m}" for m in s["conflicts"]["missed"]]
        issues += [f"misclassified change {m['chunk_id']} (expected {'meaningful' if m['expected'] else 'minor'})"
                   for m in s["changes"]["misclassified"]]
        lines += [f"- {i}" for i in issues] or ["- Nothing."]
    (EVAL / "comparison.md").write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["mock"],
                    help="mock, mock-noisy, claude:<model>, foundry:<deployment>")
    ap.add_argument("old", nargs="?", default="week1")
    ap.add_argument("new", nargs="?", default="week2")
    args = ap.parse_args()

    for snap in (args.old, args.new):
        ingest(snap)
    scores = []
    for spec in args.models:
        print(f"Evaluating {spec} ...")
        s = evaluate_model(spec, args.old, args.new)
        scores.append(s)
        if s["skipped"]:
            print(f"   SKIPPED: {s['reason']}")
            continue
        e, c, ch = s["extraction"], s["conflicts"], s["changes"]
        print(f"   status {e['status_accuracy']:.0%} | items F1 {e['items_f1']:.0%} | "
              f"unsupported {e['unsupported_per_100']}/100 | conflicts {c['conflict_recall']:.0%} | "
              f"change accuracy {ch['classification_accuracy']:.0%} | ${s['est_cost_usd']:.4f} | {s['seconds']}s")
    write_report(scores)
    print(f"\nReport: {EVAL / 'comparison.md'}  (CSV: {EVAL / 'comparison.csv'})")


if __name__ == "__main__":
    main()
