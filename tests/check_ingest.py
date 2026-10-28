"""Checks for Phase 2: ingestion, chunking and the local store.

Run from the kb_mvp folder:
    python -m kb.ingest
    python tests/check_ingest.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kb.store import JsonChunkStore  # noqa: E402

store = JsonChunkStore(ROOT / "output" / "store")
key = json.loads((ROOT / "corpus" / "answer_key.json").read_text())
results = []


def check(name, cond):
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


w1, w2 = store.chunks("week1"), store.chunks("week2")
check("both snapshots ingested", bool(w1) and bool(w2))

for snap, chunks in (("week1", w1), ("week2", w2)):
    ids = [c.chunk_id for c in chunks]
    check(f"{snap}: chunk IDs are unique", len(ids) == len(set(ids)))
    check(f"{snap}: every chunk has text and a location",
          all(c.text and c.location for c in chunks))
    check(f"{snap}: every file in the manifest produced chunks",
          all(m["chunk_count"] > 0 for m in store.manifest(snap)))


def by_file(chunks, rel):
    project, file = rel.split("/")
    return sorted((c.chunk_id, c.text_hash) for c in chunks if c.project == project and c.file == file)


for rel in key["unchanged_files"]:
    check(f"unchanged file gives identical chunks: {rel}", by_file(w1, rel) == by_file(w2, rel))

deck = "medical-records-ocr/kickoff_deck.pptx"
fh1 = {c.file_hash for c in w1 if f"{c.project}/{c.file}" == deck}
fh2 = {c.file_hash for c in w2 if f"{c.project}/{c.file}" == deck}
check("cosmetic deck: file hash changed", fh1 != fh2)
check("cosmetic deck: chunk hashes unchanged", by_file(w1, deck) == by_file(w2, deck))

# Section based IDs: a blocker added in week 2 must not shift the Decisions chunks.
ocr = "medical-records-ocr/weekly_status.docx"
dec1 = [x for x in by_file(w1, ocr) if "#decisions-" in x[0]]
dec2 = [x for x in by_file(w2, ocr) if "#decisions-" in x[0]]
check("unchanged section keeps the same IDs and hashes after edits elsewhere", dec1 == dec2)

pdf_chunks = [c for c in w1 if c.file_type == "pdf"]
check("pdf headings detected as sections, not body text",
      all(c.section != "Body" for c in pdf_chunks) and not any(c.text.endswith("Phase Report") for c in pdf_chunks))

print(f"\n{sum(results)}/{len(results)} checks passed.")
