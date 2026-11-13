-- Track which conversations have been summarized, so the background job can pick up both
-- conversations that went quiet and ones the user closed themselves. Safe to re-run.

alter table public.sage_conversations
  add column if not exists summarized_at timestamptz;

create index if not exists sage_conversations_needs_summary_idx
  on public.sage_conversations (updated_at)
  where summarized_at is null;
