"""Model adapters. The pipeline only ever calls `client.complete_json(...)`.

    MockLLM    runs offline with no key. It reads the same prompt a real model
               would get and fills the form with simple rules, so the rest of
               the pipeline can be built and tested today.
    ClaudeLLM  calls Claude through the Anthropic API. Needs ANTHROPIC_API_KEY.

Choose with the KB_MODEL setting: "mock" (default) or "claude".
Adding Claude through Azure Foundry later means one more small class here.
"""
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from kb.schema import empty_facts


def load_env(path=None):
    """Read KEY=value lines from kb_mvp/.env into the environment, if the file exists.
    Values already set in the shell win. .env is in .gitignore, so keys never get committed."""
    from pathlib import Path
    p = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    model: str


class LLMClient(ABC):
    name = "base"

    @abstractmethod
    def complete_json(self, system: str, user: str, context: dict) -> tuple[dict, Usage]:
        """Return the parsed JSON answer and token usage.

        `context` carries the raw chunks so the mock can work without parsing
        the prompt text back apart. Real models ignore it.
        """


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)   # rough rule of thumb: 4 characters per token


# ---------------------------------------------------------------- mock

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
GO_LIVE = re.compile(rf"go live[^.]*?(({MONTHS}) \d{{4}})", re.I)


def _item(chunk, text, evidence=None):
    return {"text": text, "sources": [chunk.chunk_id], "evidence": evidence or chunk.text}


def _after(prefix, text):
    return text.split(prefix, 1)[1].strip().rstrip(".")


class MockLLM(LLMClient):
    """Rule based stand in for a real model.

    It is deliberately limited: it only understands lines that start with
    labels like "Decision:" and it only spots go live date conflicts. That is
    useful later, because the evaluation will show exactly what a real model
    adds on top of simple rules.

    inject_error=True adds one invented next step with a fake citation, to
    prove the validator catches hallucinated sources.
    """
    name = "mock"

    def __init__(self, inject_error: bool = False):
        self.inject_error = inject_error

    def complete_json(self, system, user, context):
        chunks = context["chunks"]
        project = context["project"]
        facts = empty_facts(project)
        go_lives = []   # (chunk, date)

        for c in chunks:
            t = c.text
            if "Goal:" in t and facts["purpose"] is None:
                goal = re.split(r"[;]", t.split("Goal:", 1)[1])[0].strip()
                facts["purpose"] = _item(c, goal[0].upper() + goal[1:], goal)
            if t.startswith("Status:"):
                value = t.split("Status:", 1)[1].split(".")[0].strip()
                facts["status"] = _item(c, value, t.split(".")[0] + ".")
            for label, field in (("Decision:", "decisions"), ("Blocker:", "blockers"),
                                 ("Next:", "next_steps"), ("Risk:", "risks")):
                if t.startswith(label):
                    facts[field].append(_item(c, _after(label, t)))
            m = GO_LIVE.search(t)
            if m:
                go_lives.append((c, m.group(1)))

        if go_lives:
            # prefer the weekly status doc, as the prompt instructs
            go_lives.sort(key=lambda x: x[0].file != "weekly_status.docx")
            c, date = go_lives[0]
            facts["go_live"] = _item(c, date, GO_LIVE.search(c.text).group(0))
            dates = {d for _, d in go_lives}
            if len(dates) > 1:
                facts["conflicts"].append({
                    "text": "Go live date differs between documents: " + ", ".join(
                        f"{d} ({ch.file})" for ch, d in go_lives),
                    "sources": [ch.chunk_id for ch, _ in go_lives],
                })

        if self.inject_error:
            facts["next_steps"].append({
                "text": "Schedule a go live rehearsal with all clinics",
                "sources": [f"{project}/weekly_status.docx#next-steps-99"],
                "evidence": "Schedule a go live rehearsal with all clinics.",
            })

        out = json.dumps(facts)
        return facts, Usage(estimate_tokens(system + user), estimate_tokens(out), self.name)


# ---------------------------------------------------------------- Claude

class ClaudeLLM(LLMClient):
    name = "claude"

    def __init__(self, model: str | None = None):
        import anthropic   # imported here so the mock works without the package
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set. Use KB_MODEL=mock or add the key to .env")
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("KB_CLAUDE_MODEL", "claude-sonnet-5-5")

    def complete_json(self, system, user, context):
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        match = re.search(r"\{.*\}", text, re.S)   # tolerate stray words around the JSON
        if not match:
            raise ValueError(f"Model did not return JSON:\n{text[:500]}")
        return json.loads(match.group(0)), Usage(resp.usage.input_tokens, resp.usage.output_tokens, self.model)


def get_client(name: str | None = None, **kwargs) -> LLMClient:
    name = (name or os.environ.get("KB_MODEL", "mock")).lower()
    if name == "mock":
        return MockLLM(**kwargs)
    if name == "claude":
        return ClaudeLLM()
    raise SystemExit(f"Unknown model '{name}'. Use mock or claude.")
