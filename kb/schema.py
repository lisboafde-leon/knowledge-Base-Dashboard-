"""The fixed form the AI fills in for every project.

Every field is an Item (or a list of Items). An Item is one claim plus where it
came from:
    text      the claim, in plain words
    sources   chunk IDs the claim is based on (at least one)
    evidence  a short exact quote from one of those chunks, so a reviewer can
              confirm the claim in seconds and the validator can check it
"""

STATUS_VALUES = ["On track", "At risk", "Off track", "Paused", "Unknown"]

SINGLE_FIELDS = ["purpose", "status", "go_live"]
LIST_FIELDS = ["decisions", "blockers", "next_steps", "risks"]

FORM_DESCRIPTION = f"""Return ONLY a JSON object with exactly these keys:

  "purpose":    Item or null   what the project is for
  "status":     Item or null   text must be one of {STATUS_VALUES}
  "go_live":    Item or null   target go live date as written, e.g. "April 2027"
  "decisions":  [Item, ...]    decisions that have been made
  "blockers":   [Item, ...]    open blockers only; [] if none
  "next_steps": [Item, ...]
  "risks":      [Item, ...]
  "conflicts":  [Conflict, ...]

Item     = {{"text": str, "sources": [chunk_id, ...], "evidence": str}}
Conflict = {{"text": str, "sources": [chunk_id, chunk_id, ...]}}

Rules:
  1. Use only the chunks provided. Never use outside knowledge.
  2. Every Item must cite at least one chunk_id exactly as written in the input.
  3. "evidence" must be copied word for word from one of the cited chunks.
  4. If two chunks disagree, do NOT choose one. Add a Conflict citing both,
     and for the field itself prefer the most recent operational document
     (weekly status over kickoff deck).
  5. If something is not stated, use null or [] rather than guessing.
"""


def empty_facts(project: str) -> dict:
    facts = {"project": project}
    for f in SINGLE_FIELDS:
        facts[f] = None
    for f in LIST_FIELDS + ["conflicts"]:
        facts[f] = []
    return facts
