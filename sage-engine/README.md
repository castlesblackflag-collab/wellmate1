# sage-engine

The engine behind Sage, The Wellmate's conversational health guide.

This is the groundwork: the service skeleton, configuration, sign-in, error handling,
logging, database schema, and the interfaces each part of Sage will plug into. The
conversation itself isn't built yet.

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
| `POST /v1/chat` | Checks sign-in and the request format, then answers 501 until the engine is built. |
