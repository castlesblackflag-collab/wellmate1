# Evals

This is where we'll find out whether Sage is actually good, and whether each change makes it
better or worse.

Caitlin, this is the area you're leading, so I've deliberately left it nearly empty rather
than baking in my assumptions. The only thing here is one example test case, mostly to show
how the engine's pieces could plug in. Change the format, throw it out, whatever works.

A few things already in place that might be useful:

- `engine/model_adapter.py` has a `FakeAdapter` that replays scripted model output, handy for
  testing the plumbing without paying for model calls.
- `memory/store.py` has an `InMemoryStore`, so test conversations can start with a pretend
  user profile without touching Supabase.
- The `sage_eval_runs` table is ready for scorecards (scores, per-case results, git commit,
  model used).

Rubric dimensions from the work outline: accuracy, safety, tone, personalization, citations.
