# Setup notes

A starting point for getting the engine running in Google Cloud and on our own machines.
Caitlin, setup is your area in the work outline, so treat what's here as a rough first pass and reshape it however makes sense once you've been through it for real. I've
written the console steps the way I understand them, but they haven't all been clicked
through yet, so anywhere the screens look different, your version wins.

The checklist of accounts and keys is in `config/secrets-inventory.md`.

## 1. Google Cloud (project `wellmate-i`)

**Turn on the APIs.** APIs & Services > Library, then enable:
Vertex AI API, Cloud Run Admin API, Cloud Build API, Secret Manager API.

**Model access.** Vertex AI > Model Garden > search "Claude" > open Claude Sonnet and Claude
Haiku > Enable. Note the exact model IDs shown (they include a version suffix) and the
regions offered; those go into `CHAT_MODEL`, `BACKGROUND_MODEL` and `MODEL_REGION`. Check
Gemini Flash shows as available too, for the bake-off.

**A service account for the engine.** IAM & Admin > Service Accounts > Create:
- Name: `sage-engine`
- Roles: Vertex AI User, Secret Manager Secret Accessor

**Secrets.** Security > Secret Manager > Create secret, one per key in the inventory. Use the
exact names from the inventory so they match the code.

## 2. Supabase

1. Database > Extensions > enable `vector` (choose the `extensions` schema if asked).
2. SQL Editor > New query > paste each file from `supabase/migrations/`, oldest first > Run.
3. Table Editor should now show seven `sage_` tables, and `sage_conversations` has a
   `summarized_at` column.
4. Project Settings > API: the Project URL goes in `SUPABASE_URL`, the `service_role` key
   goes into Secret Manager as `SUPABASE_SERVICE_KEY`.

## 3. Deploying to Cloud Run (from the console)

Cloud Run > Deploy container > Service > "Continuously deploy from a repository":
- Repository: `castlesblackflag-collab/wellmate1`, and the branch we deploy from
- Build context directory: `sage-engine` (the engine lives in this folder of the repo)
- Build type: Python via Google Cloud's buildpacks (it picks up the Procfile, no Dockerfile)
- Service name `sage-engine`, region `us-central1`
- Authentication: allow unauthenticated invocations (the engine checks Firebase sign-in itself)
- Security tab: service account `sage-engine`
- Variables & Secrets: plain variables `ENVIRONMENT=production`, `SUPABASE_URL`, model names;
  each secret added with "Reference a secret" using the same name as the variable

Once it's up, opening `<service URL>/health` should show `"status": "ok"`, and `/ready` shows
what's still missing.

## 4. Background job (Cloud Scheduler)

1. IAM & Admin > Service Accounts > Create `sage-scheduler` (no roles needed on the project).
2. Cloud Run > `sage-engine` > Permissions > grant `sage-scheduler` the **Cloud Run Invoker** role.
3. Cloud Scheduler > Create job:
   - Frequency `*/15 * * * *`, any time zone
   - Target: HTTP, POST, URL `<service URL>/internal/jobs/close-idle`
   - Auth header: **Add OIDC token**, service account `sage-scheduler`, audience = the service URL
4. On the Cloud Run service, set `JOB_AUDIENCE` to the service URL and `JOB_INVOKER_EMAIL` to
   the `sage-scheduler` account's email.
5. "Force run" the job once; its log should show `close_idle_conversations finished`.

## 5. Model prices

Fill `MODEL_PRICES` on the Cloud Run service with per-million-token prices from the Vertex AI
pricing page, for example
`{"claude-sonnet-5-5": {"input": 0, "output": 0, "cache_read": 0}}` with the real numbers.
Use the exact model IDs set in `CHAT_MODEL` and `BACKGROUND_MODEL`.

## 6. Running on your own machine

The easiest route is to ask Claude Code: "set up the sage-engine folder locally and run the
tests". Behind the scenes that's:

1. Install Python 3.12.
2. `pip install -r requirements-dev.txt`
3. Copy `.env.example` to `.env`, fill in what you have, and set `AUTH_DISABLED=true`.
4. `pytest` to run the tests, `uvicorn main:app --reload --port 8080` to run the server.
5. For model calls later: `gcloud auth application-default login` once, so your machine can
   reach Vertex AI with your own Google account.

## 7. GitHub

- Branch protection on the default branch: require a pull request and the "Sage engine CI" check to pass.
- Labels `WS1` to `WS9`, plus `bug` and `blocked`.
- A Project board with To do, In progress, Review, Done.
