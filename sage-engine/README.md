# sage-engine

The engine behind Sage, The Wellmate's conversational health guide.

The architecture is in place: streaming chat, the agent loop, model adapters, storage,
memory, logging and background summaries. Sage's own pieces (crisis screen, tools, Age Well
connection, tuned persona) plug into it next.

## Start here

- **New to the repo?** [`docs/architecture.md`](docs/architecture.md) shows how the pieces fit.
- **Setting up accounts and keys?** [`docs/setup.md`](docs/setup.md) and
  [`config/secrets-inventory.md`](config/secrets-inventory.md).
- **Connecting the app?** [`docs/endpoint-contract.md`](docs/endpoint-contract.md).
- **Database?** [`docs/data-model.md`](docs/data-model.md) and `supabase/migrations/`.
- **Why we chose what we chose?** [`docs/decisions.md`](docs/decisions.md).
- **Working with Claude Code?** It reads [`CLAUDE.md`](CLAUDE.md) automatically.

## What works today

| Endpoint | What it does |
|---|---|
| `GET /health` | Confirms the service is running. Used for Cloud Run health checks. |
| `GET /ready` | Shows which pieces are configured and reachable (names only, never values). |
| `POST /v1/chat` | Streams Sage's reply. Answers 501 until chat is switched on (see docs/architecture.md). |
| `GET /v1/conversations` | The user's recent conversations, plus one conversation's messages and a close call. |
| `POST /internal/jobs/close-idle` | Cloud Scheduler only: summarizes and closes quiet conversations. |
