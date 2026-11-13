# Data model

All tables live in our existing Supabase project, prefixed `sage_`, created by
`supabase/migrations/20261113120000_sage_engine_core.sql`. Row level security is on with no
policies, so only the engine (service role) can reach them; the app always goes through the engine.

`user_id` everywhere is the Firebase Auth uid.

| Table | What it holds |
|---|---|
| `sage_conversations` | One row per conversation: owner, status, model and engine version, when it was summarized |
| `sage_messages` | Every message in a conversation (user, assistant, tool), as model-neutral JSON |
| `sage_user_profiles` | What Sage remembers about a person: facts and preferences |
| `sage_session_summaries` | Short recap of each finished conversation, written by the background model |
| `sage_knowledge_chunks` | Searchable knowledge with embeddings: our corpus, PubMed, curated sources |
| `sage_turn_logs` | Per-turn tokens, cost, timing, tools used, safety level, errors |
| `sage_eval_runs` | Scorecards from each eval run |

## Built-in guard rails

- **A message can't be filed under the wrong user.** A trigger rejects any `sage_messages`
  row whose `user_id` doesn't match its conversation's owner.
- **No duplicate knowledge.** `content_hash` is unique, so the same chunk can't be indexed twice.
- **Deleting a conversation deletes its messages and summary.** Turn logs keep their numbers
  but drop the link.
- **Search is service-role only.** `sage_match_knowledge()` can't be called by app users directly.

## Search

```python
supabase.rpc(
    "sage_match_knowledge",
    {
        "query_embedding": embedding,  # 768 numbers
        "match_count": 8,
        "source_types": ["pubmed", "curated"],  # optional filter
        "min_similarity": 0.3,  # optional
    },
).execute()
```

## Things to revisit

- **Embedding size** is 768. If WS3 picks a model with a different size, the column, index
  and function change together in a new migration.
- **Sensitive facts in profiles.** The app's rule is that sensitive labels are encrypted at
  rest and never surfaced unprompted. Supabase encrypts the whole disk; whether profile facts
  also need field-level encryption is an open decision in `docs/decisions.md`.
- **Retention.** How long conversations are kept is still to be decided (WS5).

## Applying the migrations

Run each file in `supabase/migrations/` in order (oldest first): Supabase dashboard > SQL
Editor > New query > paste > Run. Each one is safe to run again. It's safe to
run again. If it stops with a message about pgvector being in another schema, the message
says exactly what to change.
