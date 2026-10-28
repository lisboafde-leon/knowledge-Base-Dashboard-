"""Where chunks live.

ChunkStore is the interface every later phase talks to. JsonChunkStore is the
local version for the MVP. When the team moves to Azure, a new class such as
AzureSearchChunkStore implements the same four methods, and nothing else in
the pipeline changes.
"""
import json
from abc import ABC, abstractmethod
from pathlib import Path

from kb.models import Chunk, FileRecord


class ChunkStore(ABC):
    @abstractmethod
    def save(self, snapshot: str, chunks: list[Chunk], manifest: list[FileRecord]) -> None: ...

    @abstractmethod
    def chunks(self, snapshot: str, project: str | None = None) -> list[Chunk]: ...

    @abstractmethod
    def manifest(self, snapshot: str) -> list[dict]: ...

    @abstractmethod
    def snapshots(self) -> list[str]: ...


class JsonChunkStore(ChunkStore):
    """Stores each snapshot as output/store/<snapshot>/chunks.jsonl + manifest.json."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _dir(self, snapshot: str) -> Path:
        return self.root / snapshot

    def save(self, snapshot, chunks, manifest):
        d = self._dir(snapshot)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "chunks.jsonl", "w") as f:
            for c in chunks:
                f.write(json.dumps(c.to_dict()) + "\n")
        (d / "manifest.json").write_text(json.dumps([vars(m) for m in manifest], indent=2))

    def chunks(self, snapshot, project=None):
        path = self._dir(snapshot) / "chunks.jsonl"
        if not path.exists():
            return []
        out = [Chunk.from_dict(json.loads(line)) for line in path.read_text().splitlines() if line]
        return [c for c in out if project is None or c.project == project]

    def manifest(self, snapshot):
        path = self._dir(snapshot) / "manifest.json"
        return json.loads(path.read_text()) if path.exists() else []

    def snapshots(self):
        return sorted(p.name for p in self.root.iterdir() if p.is_dir()) if self.root.exists() else []
