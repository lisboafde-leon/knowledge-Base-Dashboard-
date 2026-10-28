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

## Phase 2: ingestion and chunking

```
python -m kb.ingest            # ingests week1 and week2
python tests/check_ingest.py
```

Each file becomes chunks with an exact source pointer: one chunk per slide for decks, one per paragraph for Word docs and PDFs, grouped under the nearest heading. PDF headings are detected by font size, and wrapped lines are joined back into whole paragraphs.

Every chunk carries two fingerprints. `file_hash` covers the whole file's bytes, and `text_hash` covers only the normalized text, so a formatting change alters the first but not the second. Chunk IDs are built from the section name plus position inside that section (for example `medical-records-ocr/weekly_status.docx#decisions-2`), so adding a paragraph to one section does not renumber every other section.

Results are written to `output/store/<snapshot>/chunks.jsonl` and `manifest.json` through the `ChunkStore` interface in `kb/store.py`. Moving to Azure means writing one new class with the same four methods.

## Phase 3: extraction with citations

```
python -m kb.extract week2                 # mock model, no key needed
python -m kb.extract week2 --inject-error  # adds one fake citation to watch the validator catch it
python tests/check_extract.py
```

For each project, every chunk goes to the model with a fixed form to fill in: purpose, status, go live, decisions, blockers, next steps, risks and conflicts (defined in `kb/schema.py`). Every claim must cite the chunk IDs it came from and include a short evidence quote copied from one of them.

The answer then goes through `kb/validate.py`, plain code with no AI, which checks that each cited chunk exists, belongs to the project, and actually contains the evidence quote. Claims that fail stay in the output marked `supported: false` with the reason, so a person reviews them instead of trusting them. Results are saved to `output/facts/<snapshot>/<project>.json`.

The model sits behind `kb/llm.py`. The mock fills the form with simple rules so everything runs offline. To use Claude, copy `.env.example` to `.env`, set `KB_MODEL=claude` and add an API key from León's company account, then rerun the same command.

## Phase 4: change detection

```
python -m kb.changes week1 week2
python tests/check_changes.py
```

Compares two snapshots in three layers, cheapest first. Layer 1 skips any file whose bytes are identical. Layer 2 catches files whose bytes changed but whose words did not (a font change, for example) and logs them as formatting only. Layer 3 finds the exact chunks that were added, removed or edited, and only those go to the model, which marks each one meaningful or minor and writes a one sentence summary.

The first two layers are plain code and cost nothing. A validator makes sure every changed chunk gets exactly one verdict: if the model skips one it is marked `needs_review`, and any chunk ID the model invents is ignored. Results are saved to `output/changes/<old>_to_<new>.json`, including token use compared with rerunning full extraction.

## Phase 5: outputs, reports and dashboard

```
python -m kb.run                    # the whole pipeline in order (what the 7 a.m. job will do)
streamlit run dashboard/app.py      # opens the dashboard in your browser
python tests/check_publish.py
```

`kb/publish.py` turns fact sheets and the change log into CSV tables in `output/tables` with the exact columns planned for SharePoint lists: Projects, Facts, Changes, Conflicts and ReportRequests. It also writes one Markdown page per project in `output/pages`, readable by people and by Claude or Copilot for questions.

`kb/report.py` builds a draft Word status report for one project, stamped DRAFT, with a numbered citation on every line and a Sources section quoting each location. It also handles the request flow planned for SharePoint: `--request <project>` queues a row as Pending, `--process` builds every pending report and marks it Ready.

`dashboard/app.py` is a Streamlit proof of concept that reads only the tables, the same way a SharePoint or Power BI page would. It shows headline numbers, project cards (most urgent first), what changed, conflicts, every fact with its source and quote, and a Generate report button with a download. It is a demo tool, not the final front end.

## Project layout

```
scripts/   corpus generator and its content
kb/        pipeline code (phases 2 to 5); kb/run.py runs it all
dashboard/ Streamlit proof of concept dashboard
corpus/    generated documents and answer key
output/    generated tables and reports
tests/     checks for each phase
```
