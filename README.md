# León FE Knowledge Base MVP

A local prototype of the automated project knowledge base, built on dummy data so it can run before any SharePoint or Azure access is approved. Every local piece mirrors an Azure piece, so each one can be swapped out later without rewriting the rest.

| Local piece (now) | Azure piece (later) |
| --- | --- |
| `corpus/week1`, `corpus/week2` folders | SharePoint project folders |
| Comparing two snapshots | Microsoft Graph delta query |
| Local JSON / SQLite store | Azure AI Search + SharePoint Lists |
| Mock model adapter | Azure OpenAI or Foundry |
| CSV output tables | SharePoint Lists |
| Power BI Desktop on CSVs | Power BI on SharePoint Lists |

## Setup

```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Phase 1: dummy corpus

```
python scripts/generate_corpus.py
python tests/check_corpus.py
```

This creates three invented projects (Medical Records OCR, Pharmacy Delivery, Clinical AI), each with a kickoff deck, a weekly status doc and a phase report, in two weekly snapshots. Week 2 contains deliberate test cases:

Real changes: a go live date moves, a status turns at risk, a courier vendor is replaced, a blocker is resolved, new decisions appear.

Noise: one deck changes font size only, and one sentence is reworded without changing its meaning. The system should ignore both.

Contradictions: two decks still say something the newer status doc contradicts. The system should surface these, not quietly pick one.

`corpus/answer_key.json` holds the ground truth that the evaluation step scores against. To change the test data, edit `scripts/corpus_content.py` and rerun the generator.

## Project layout

```
scripts/   corpus generator and its content
kb/        pipeline code (phases 2 to 5)
corpus/    generated documents and answer key
output/    generated tables and reports
tests/     checks for each phase
```
