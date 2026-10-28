"""Core data shapes shared by every phase.

A Chunk is one traceable piece of source text: one slide, or one paragraph of a
Word doc or PDF. Its `location` is what lets every generated statement point
back to the exact spot it came from.
"""
import hashlib
import re
from dataclasses import asdict, dataclass, field


def normalize(text: str) -> str:
    """Collapse whitespace so formatting noise does not change the hash."""
    return re.sub(r"\s+", " ", text).strip()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "body"


@dataclass
class Chunk:
    project: str          # folder name, e.g. "medical-records-ocr"
    file: str             # file name, e.g. "weekly_status.docx"
    file_type: str        # "pptx" | "docx" | "pdf"
    section: str          # slide title or nearest heading
    position: int         # order of the chunk inside its section, starting at 1
    location: dict        # human readable pointer: {"slide": 2} or {"page": 1, "paragraph": 4}
    text: str             # normalized text
    snapshot: str = ""    # "week1", "week2", later a real timestamp
    file_hash: str = ""   # hash of the whole file's bytes
    text_hash: str = field(init=False)
    chunk_id: str = field(init=False)

    def __post_init__(self):
        self.text = normalize(self.text)
        self.text_hash = sha(self.text)
        # Section based ID: inserting a paragraph in one section does not
        # renumber chunks in every other section of the file.
        self.chunk_id = f"{self.project}/{self.file}#{slug(self.section)}-{self.position}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Chunk":
        c = cls(
            project=d["project"], file=d["file"], file_type=d["file_type"],
            section=d["section"], position=d["position"], location=d["location"],
            text=d["text"], snapshot=d.get("snapshot", ""), file_hash=d.get("file_hash", ""),
        )
        return c


@dataclass
class FileRecord:
    """One row of the document manifest."""
    project: str
    file: str
    file_type: str
    file_hash: str
    size_bytes: int
    chunk_count: int
    snapshot: str
