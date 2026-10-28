"""Ingest one snapshot folder into the store.

Usage, from the kb_mvp folder:
    python -m kb.ingest week1
    python -m kb.ingest week2

Expects corpus/<snapshot>/<project>/<files>. Later, the same function gets its
file list from Microsoft Graph instead of a local folder.
"""
import hashlib
import sys
from pathlib import Path

from kb.models import FileRecord
from kb.parsers import PARSERS, parse_file
from kb.store import JsonChunkStore

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
STORE = JsonChunkStore(ROOT / "output" / "store")


def ingest(snapshot: str, corpus: Path = CORPUS, store=STORE):
    base = corpus / snapshot
    if not base.exists():
        raise SystemExit(f"No folder at {base}. Run scripts/generate_corpus.py first.")
    all_chunks, manifest = [], []
    for project_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for path in sorted(project_dir.iterdir()):
            if path.suffix.lower() not in PARSERS:
                continue
            data = path.read_bytes()
            fhash = hashlib.sha256(data).hexdigest()[:16]
            chunks = parse_file(path, project_dir.name)
            for c in chunks:
                c.snapshot, c.file_hash = snapshot, fhash
            all_chunks += chunks
            manifest.append(FileRecord(project_dir.name, path.name, path.suffix[1:], fhash,
                                       len(data), len(chunks), snapshot))
    store.save(snapshot, all_chunks, manifest)
    return all_chunks, manifest


def main():
    snapshots = sys.argv[1:] or ["week1", "week2"]
    for snap in snapshots:
        chunks, manifest = ingest(snap)
        print(f"{snap}: {len(manifest)} files, {len(chunks)} chunks")
        for m in manifest:
            print(f"   {m.project}/{m.file}: {m.chunk_count} chunks")


if __name__ == "__main__":
    main()
