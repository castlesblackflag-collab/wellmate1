# Data

Scripts and notes for cleaning and indexing Sage's knowledge sources. Raw files stay out of
git (`data/raw/` and `data/working/` are ignored); scripts and findings go here.

## What we have in the old Q&A files

I ran a quick comparison of the files from the Dialogflow days. Short version: there's a lot
less unique content than the file count suggests.

| File | Rows | What it really is |
|---|---|---|
| `MedicalQuestionAnswering.csv` | 16,406 | MedQuAD-style NIH Q&A: 14,297 unique questions, 16,358 unique question-answer pairs |
| The nine topic files (Cancer, Senior Health, etc.) | 16,406 total | Exactly the file above, split by topic |
| `medical QA 16K.csv` (uploaded twice) | 16,359 | Same questions again; the two copies are identical |
| `medical QA AI train.csv` | 16,407 | Same questions again |
| `QA 40K.xlsx` | 40,442 | The same 14,297 questions plus about 24,000 forum-style doctor replies |
| `mental health QA.csv` | 172 | Separate, small |
| `healthcare assist AI QA training.csv` | 500 | Separate, small |

So the core is roughly 14,300 NIH-sourced questions, plus a large set of forum answers that
would need a careful look before Sage cites them, since they're individual replies rather
than vetted references. The 38,889 pairs in Firestore are very likely mostly these same rows.

None of this covers cannabis or integrative care in any depth, which is where the curated
source list (WS3) comes in.

## Where it ends up

Cleaned, deduplicated chunks go into `sage_knowledge_chunks` with a `content_hash` (the table
rejects duplicates) and a real source URL for each one.
