"""Content for the dummy corpus. All names, vendors and dates are invented.

Each project has three documents:
  deck   -> kickoff deck (.pptx), list of slides (title, bullets)
  status -> weekly status doc (.docx), list of (heading, paragraphs)
  report -> phase report (.pdf), list of (heading, paragraphs)

WEEK1 holds the baseline. WEEK2_OVERRIDES holds only the documents that change
in week 2, plus a "cosmetic" flag for files that change bytes but not text.
"""

WEEK1 = {
    "medical-records-ocr": {
        "title": "Medical Records OCR",
        "deck": [
            ("Medical Records OCR: Project Kickoff", [
                "Goal: digitize incoming paper records and extract key fields automatically",
                "Sponsor: Operations; technical owner: FE team",
            ]),
            ("Scope and Timeline", [
                "Phase 1 covers intake forms from two clinics",
                "Target go live: March 2027",
            ]),
            ("Approach", [
                "Vendor: ClearScan OCR engine with a custom field extraction layer",
                "Human review queue for low confidence fields",
            ]),
        ],
        "status": [
            ("Current Status", [
                "Status: On track. Field extraction prototype reaches 91 percent accuracy on the test batch.",
                "Target go live remains March 2027.",
            ]),
            ("Decisions", [
                "Decision: ClearScan selected as the OCR engine after a two week bake off.",
                "Decision: Confidence threshold for human review set at 0.85.",
            ]),
            ("Blockers", [
                "Blocker: Waiting on scanner hardware delivery for the second clinic.",
            ]),
            ("Next Steps", [
                "Next: Expand the test batch to 500 forms.",
                "Next: Draft the review queue workflow with clinic staff.",
            ]),
        ],
        "report": [
            ("Phase 1 Summary", [
                "The OCR pilot processed 320 sample forms during the first evaluation cycle.",
                "Average processing time per form was 4.2 seconds.",
            ]),
            ("Risks", [
                "Risk: Handwritten fields remain the weakest category at 74 percent accuracy.",
            ]),
        ],
    },
    "pharmacy-delivery": {
        "title": "Pharmacy Delivery",
        "deck": [
            ("Pharmacy Delivery Pilot: Kickoff", [
                "Goal: same day medication delivery for members within 10 miles",
                "Sponsor: Pharmacy Operations",
            ]),
            ("Pilot Design", [
                "Pilot clinics: North and West",
                "Measure: on time delivery rate and member satisfaction",
            ]),
        ],
        "status": [
            ("Current Status", [
                "Status: On track. On time delivery rate is 93 percent across both pilot clinics.",
            ]),
            ("Decisions", [
                "Decision: SwiftRoute selected as the courier partner for the pilot.",
                "Decision: Delivery window set to 2 to 6 PM.",
            ]),
            ("Blockers", [
                "Blocker: Address validation fails for about 6 percent of member records.",
            ]),
            ("Next Steps", [
                "Next: The team will run a member satisfaction survey in week 3.",
                "Next: Clean member address data with the data team.",
            ]),
        ],
        "report": [
            ("Field Findings", [
                "Field visits found that most delays happen during pharmacy handoff, not transit.",
                "Average handoff wait time was 18 minutes.",
            ]),
        ],
    },
    "clinical-ai": {
        "title": "Clinical AI",
        "deck": [
            ("Clinical AI Initiatives: Overview", [
                "Goal: evaluate AI assistance for clinical documentation",
                "Two workstreams: note summarization and coding suggestions",
            ]),
            ("Standards", [
                "Every model output must cite the source note section",
                "No model output reaches a chart without clinician sign off",
            ]),
        ],
        "status": [
            ("Current Status", [
                "Status: At risk. Work is paused pending de identified data access approval.",
            ]),
            ("Decisions", [
                "Decision: Note summarization is the first workstream to pilot.",
            ]),
            ("Blockers", [
                "Blocker: De identified dataset access is awaiting compliance approval.",
            ]),
            ("Next Steps", [
                "Next: Finalize the evaluation rubric with two clinician reviewers.",
            ]),
        ],
        "report": [
            ("Evaluation Plan", [
                "The evaluation will compare model summaries against clinician written summaries.",
                "Primary metric: factual consistency scored by clinician reviewers.",
            ]),
        ],
    },
}

# Week 2: only the documents that change. "cosmetic" means regenerate with a
# formatting change only, so bytes differ but extracted text stays identical.
WEEK2_OVERRIDES = {
    "medical-records-ocr": {
        "status": [
            ("Current Status", [
                "Status: At risk. Field extraction accuracy improved to 93 percent on the test batch.",
                "Target go live moved to April 2027 because of the scanner delay.",
            ]),
            ("Decisions", [
                "Decision: ClearScan selected as the OCR engine after a two week bake off.",
                "Decision: Confidence threshold for human review set at 0.85.",
            ]),
            ("Blockers", [
                "Blocker: Waiting on scanner hardware delivery for the second clinic.",
                "Blocker: ClearScan API rate limit caps throughput at 200 forms per hour.",
            ]),
            ("Next Steps", [
                "Next: Expand the test batch to 500 forms.",
                "Next: Draft the review queue workflow with clinic staff.",
                "Next: Request a higher API rate limit from ClearScan.",
            ]),
        ],
        # Deck still says March 2027: this creates a planted contradiction.
        "deck_cosmetic": True,
    },
    "pharmacy-delivery": {
        "status": [
            ("Current Status", [
                "Status: On track. On time delivery rate is 95 percent across three pilot clinics.",
                "The pilot expanded to the South clinic this week.",
            ]),
            ("Decisions", [
                "Decision: MedDash replaces SwiftRoute as the courier partner after a pricing review.",
                "Decision: Delivery window set to 2 to 6 PM.",
            ]),
            ("Blockers", [
                "Blocker: Address validation fails for about 6 percent of member records.",
            ]),
            ("Next Steps", [
                "Next: The team plans to run a member satisfaction survey in week 3.",
                "Next: Clean member address data with the data team.",
            ]),
        ],
    },
    "clinical-ai": {
        "status": [
            ("Current Status", [
                "Status: On track. De identified data access was approved and work has resumed.",
            ]),
            ("Decisions", [
                "Decision: Note summarization is the first workstream to pilot.",
                "Decision: Evaluation rubric approved with five scoring criteria.",
            ]),
            ("Blockers", [
                "No open blockers.",
            ]),
            ("Next Steps", [
                "Next: Run the first evaluation round on 50 de identified notes.",
            ]),
        ],
    },
}
