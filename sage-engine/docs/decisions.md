# Decisions

A running log of choices we've made and why, so neither of us has to remember the reasoning
later. Add new ones at the bottom. If we change our minds, add a new entry rather than
editing the old one.

---

### D1. Build our own engine instead of Dialogflow (Nov 2026)
Dialogflow's playbooks, routing and console-only editing forced workarounds. We own the
framework and rent the model. Behavior lives in versioned code and prompts we can read and test.

### D2. No agent frameworks
LangChain and similar tools bring their own abstractions and upgrade churn, which recreates
the problem we're leaving. Direct SDK calls keep the engine small enough to read in one go.

### D3. Claude on Vertex AI, with a bake-off before locking in
Sonnet for conversation, Haiku for background jobs, through Vertex AI so billing and access
stay in `wellmate-i` and no API key is needed. Gemini Flash stays available through the same
adapter; the WS6 bake-off makes the final call on evidence.

### D4. One agent, not hub-and-spoke
Listening, care planning and progress reviews are modes Sage moves between, described in the
persona, not separate bots with handoffs.

### D5. Python FastAPI on Cloud Run, deployed from source
Same deployment style as our other services, no Dockerfile. Python because the evals, data
work and literature tools are most comfortable there.

### D6. Supabase for engine data, tables prefixed `sage_`
Sits alongside goals and referrals. pgvector handles search. RLS on, service role only.

### D7. Firebase uid is the user ID
Matches the app's sign-in and Firestore `users` collection, so nothing needs mapping.

### D8. Secrets as environment variables from Secret Manager
The code reads settings from the environment and never calls Secret Manager itself. Simple
to test, and Cloud Run handles the wiring.

### D9. Request IDs on every response and log line
Any error a user sees carries an ID we can find in the logs immediately.

### D10. The chat endpoint stays off until the crisis screen exists
There's no placeholder crisis screen that could be wired in by accident.

---

## Open

- Final model choice (after the bake-off)
- Web search provider
- Embedding model (sets the vector size, currently 768)
- Field-level encryption for sensitive profile facts
- Conversation retention period and consent wording
- BAA coverage for the chosen model on Vertex AI
- Whether the cleaned corpus fully replaces the Firestore copy
