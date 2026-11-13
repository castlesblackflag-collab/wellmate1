# CLAUDE.md: sage-engine

This folder lives inside the `wellmate1` repo, alongside the Provider Finder service in
`app/`. Everything for Sage stays inside `sage-engine/`; the shared GitHub files (CI, PR and
issue templates) are in the repo's top-level `.github/`.

Read at the start of every Claude Code session in this repo. Castle and Caitlin both work
here, each with their own Claude Code session, so this file is how both sessions stay on the
same page. Either of us can update it. If something here turns out to be wrong, fix it here first.

## What this is

The engine behind **Sage**, The Wellmate's conversational health guide. It replaces the old
Dialogflow CX / Playbooks agent. A hosted model does the talking; everything around it
(context, tools, memory, retrieval, safety, logging) is our own Python in this repo.

The goal is a thoughtful, personal, free-thinking guide, not a routed bot. Dialogflow-era
structures (hub-and-spoke playbooks, routing rules, duplicated instruction blocks) are not
something to recreate here.

## Stack

- Python 3.12, FastAPI, served by uvicorn
- Cloud Run in GCP project `wellmate-i`, region `us-central1`, **deployed from source** via the
  Procfile. **No Dockerfile.**
- Models on Vertex AI through `engine/model_adapter.py`: Claude Sonnet for conversation,
  Claude Haiku for background jobs, Gemini Flash kept available for comparison. Model access
  uses the Cloud Run service account, not API keys.
- Supabase (Postgres + pgvector). Tables are prefixed `sage_`; schema in `supabase/migrations/`.
- Users are identified by their **Firebase Auth uid** (same key the app uses everywhere).

## Where things live

| Folder | What's in it | Usually led by |
|---|---|---|
| `engine/` | App setup, settings, auth, errors, logging, model adapter, (later) the agent loop | Castle |
| `persona/` | Sage's voice and guidance | Castle, with Caitlin on tone and examples |
| `tools/` | Tools Sage can call (`tools/README.md` explains the pattern) | Castle (`agewell` tool: Caitlin) |
| `memory/` | User profile and session summaries | Castle |
| `safety/` | Crisis screen and guidance rules | Castle |
| `evals/` | Eval runner, test conversations, red-team set, scorecards | Caitlin |
| `data/` | Corpus cleanup and indexing scripts | Caitlin |
| `config/` | Secrets inventory (names only), setup helpers | Caitlin |
| `docs/` | Architecture, endpoint contract, data model, decisions, setup | Both |
| `supabase/` | SQL migrations | Castle |
| `tests/` | Tests for everything above | Both |

"Usually led by" just means who's most likely to be in there. Anyone can work anywhere;
mention it in the GitHub issue so we don't edit the same file at the same time.

## How we work

- Each person works on their own branch (`castle/...`, `caitlin/...`) and merges into `main`
  through a pull request into the repo's default branch. Don't commit directly to it.
- One GitHub issue per task, labeled `WS1` to `WS9` (see the work outline).
- Before opening a PR: tests and lint pass (CI runs both). Once the eval suite exists, evals
  pass too.
- Neither of us loves the terminal. When a command is needed, run it yourself and explain
  what happened in plain language, rather than handing over a list of commands.

## Rules for the code

1. **No agent frameworks** (LangChain, LlamaIndex, CrewAI, etc.). Call model SDKs directly
   through `engine/model_adapter.py`, so every behavior is visible in our own code.
2. **Nothing fails silently.** No bare `except: pass`, no returning empty results to hide an
   error. Raise a `SageError` subclass from `engine/errors.py`, or log the full error and say
   why in a comment. Every user-facing error has the standard shape with a request ID.
3. **Three hard rails, everything else is Sage's judgment:**
   - Every user message passes the crisis screen (`safety/`) before the model sees it.
   - Every tool call is validated against the tool's `Input` model before it runs.
   - Age Well scoring is never computed here. Sage reads results from the Age Well engine and
     explains them; it doesn't do the math.
4. **Every query on user data filters by the signed-in user's uid.** The engine uses the
   Supabase service key, which bypasses row level security, so this is on us.
5. **No secrets in the repo, ever.** Not in code, tests, docs, commit messages or issues. Real
   values live in Secret Manager and the shared vault; `config/secrets-inventory.md` lists
   names only. If a key leaks, rotate it and update the inventory.
6. **Citations must be real.** Every health claim Sage makes from a source traces to a
   checkable citation. No placeholder or invented references, in code, tests or examples.
7. **Diagnose before fixing.** Look at what the code actually does and confirm the cause before
   changing it. Check that a file is actually imported before assuming it's live.
8. **Say "unverified" when it is.** Don't state how something is deployed or configured unless
   it was checked in this session.
9. Every new module gets tests. Settings come from environment variables via `engine/settings.py`.

## Content rules Sage inherits from the app

- Health information is educational, not medical advice.
- No weight or body-size targets; goals about weight become behavior-based (walking, sleep,
  vegetables, strength sessions).
- Sensitive topics (suicidality, self-harm, trauma, IPV, substance use, eating-disorder history,
  sexual orientation, gender identity) are never brought up unprompted.

## Commands

Run these from the `sage-engine/` folder (Claude Code can run them for you):

```
pip install -r requirements-dev.txt   # one-time setup
pytest                                # all tests
ruff check . && ruff format --check . # lint and formatting
uvicorn main:app --reload --port 8080 # run locally, then open http://localhost:8080/docs
```

Local runs read a `.env` file (copy `.env.example`). Set `AUTH_DISABLED=true` there to skip
sign-in on your own machine; the app refuses to start with it in production.

## Status

The full architecture is built and tested: streaming chat, the agent loop, Claude and Gemini
adapters, conversations, memory, turn logging, background summaries, embeddings. What's
missing is what makes Sage *Sage*: the crisis screen, the tools, the Age Well source and a
tuned persona. `/v1/chat` stays off (501) until `CHAT_ENABLED=true` **and** a crisis screen
is registered. `docs/architecture.md` has the list of what's left.

Not yet verified: calls to live Vertex AI and live Supabase (all tests use fakes).
