# Secrets inventory

**Names and locations only. Never put an actual key or password in this file.**

Real values live in two places:
- **Google Secret Manager** (project `wellmate-i`) for anything the engine reads at runtime.
- **Our shared password vault** for account logins, recovery codes, and a copy of each key.

Both of us should be able to get into every account and every secret. The last column is
how we know that's true: once a key is set up, Castle checks he can see it in both places and
ticks it.

## Runtime secrets (Secret Manager → Cloud Run env vars)

| Name | What it's for | Created by | Date | In vault | Castle confirmed |
|---|---|---|---|---|---|
| `SUPABASE_SERVICE_KEY` | Engine access to the sage_ tables | | | [ ] | [ ] |
| `NCBI_API_KEY` | PubMed literature search | | | [ ] | [ ] |
| `WEB_SEARCH_API_KEY` | Web search tool (provider to be chosen) | | | [ ] | [ ] |
| `GOOGLE_PLACES_API_KEY` | Provider Finder (existing key, now shared with the engine) | | | [ ] | [ ] |

## Plain settings (not secret, set as Cloud Run variables)

`ENVIRONMENT`, `SUPABASE_URL`, `GCP_PROJECT_ID`, `MODEL_REGION`, `CHAT_PROVIDER`,
`CHAT_MODEL`, `BACKGROUND_PROVIDER`, `BACKGROUND_MODEL`, `FIREBASE_PROJECT_ID`,
`ALLOWED_ORIGIN_REGEX`

## No key needed

| What | How access works |
|---|---|
| Claude and Gemini on Vertex AI | The `sage-engine` service account's Vertex AI User role |
| Verifying user sign-in | Firebase project ID plus Google's public certificates |

## Accounts (logins in the vault, both of us as owner/admin)

| Service | Account | Both have admin | 2FA on | Recovery codes in vault |
|---|---|---|---|---|
| GitHub (`castlesblackflag-collab`) | | [ ] | [ ] | [ ] |
| Google Cloud (`wellmate-i`) | | [ ] | [ ] | [ ] |
| Supabase | | [ ] | [ ] | [ ] |
| NCBI | | [ ] | [ ] | [ ] |
| Web search provider | | [ ] | [ ] | [ ] |
| Password vault itself | | [ ] | [ ] | [ ] |

## If a key leaks

Rotate it straight away (either of us, no need to ask first), update Secret Manager and the
vault, redeploy, and add a line below.

| Date | Key | What happened | Rotated by |
|---|---|---|---|
