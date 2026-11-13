-- Sage engine: core tables
--
-- Run once in the Supabase SQL editor (or with the Supabase CLI). Safe to re-run: every
-- statement checks whether its object already exists.
--
-- Conventions
--   * Every table is prefixed sage_ so it sits cleanly beside our existing goals/referrals tables.
--   * user_id is the Firebase Auth uid (text), same key the app uses everywhere else.
--   * Row level security is ON with no policies, so only the service role (the engine) can
--     read or write. The app never talks to these tables directly; it goes through the engine.
--   * Embedding size is 768, matching Vertex AI text embeddings at 768 dimensions. If we pick
--     a different embedding model in WS3, this column and the function below change with it.

create schema if not exists extensions;

-- If pgvector was already switched on in a different schema, stop with a clear message
-- rather than a confusing "type does not exist" error further down.
do $$
declare
  vector_schema text;
begin
  select n.nspname into vector_schema
  from pg_extension e join pg_namespace n on n.oid = e.extnamespace
  where e.extname = 'vector';
  if vector_schema is not null and vector_schema <> 'extensions' then
    raise exception 'pgvector is installed in schema "%" instead of "extensions". Either run: alter extension vector set schema extensions; or change extensions.vector in this file to %.vector', vector_schema, vector_schema;
  end if;
end;
$$;

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Shared helper: keep updated_at current
-- ---------------------------------------------------------------------------
create or replace function public.sage_set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Conversations and messages
-- ---------------------------------------------------------------------------
create table if not exists public.sage_conversations (
  id              uuid primary key default gen_random_uuid(),
  user_id         text not null,
  title           text,
  status          text not null default 'active' check (status in ('active', 'closed')),
  chat_model      text,
  engine_version  text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  closed_at       timestamptz
);
create index if not exists sage_conversations_user_recent_idx
  on public.sage_conversations (user_id, updated_at desc);

drop trigger if exists sage_conversations_updated_at on public.sage_conversations;
create trigger sage_conversations_updated_at
  before update on public.sage_conversations
  for each row execute function public.sage_set_updated_at();

create table if not exists public.sage_messages (
  id               uuid primary key default gen_random_uuid(),
  conversation_id  uuid not null references public.sage_conversations (id) on delete cascade,
  user_id          text not null,
  role             text not null check (role in ('user', 'assistant', 'tool')),
  -- Model-neutral message body: text, tool calls, tool results and citations (see engine/types.py)
  content          jsonb not null,
  created_at       timestamptz not null default now()
);
create index if not exists sage_messages_conversation_idx
  on public.sage_messages (conversation_id, created_at);

-- Guard rail: a message can only be stored under the same user as its conversation.
create or replace function public.sage_messages_check_user()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  owner text;
begin
  select user_id into owner from public.sage_conversations where id = new.conversation_id;
  if owner is distinct from new.user_id then
    raise exception 'sage_messages.user_id (%) does not match its conversation owner', new.user_id
      using errcode = '42501';
  end if;
  return new;
end;
$$;

drop trigger if exists sage_messages_user_guard on public.sage_messages;
create trigger sage_messages_user_guard
  before insert or update on public.sage_messages
  for each row execute function public.sage_messages_check_user();

-- ---------------------------------------------------------------------------
-- Memory
-- ---------------------------------------------------------------------------
create table if not exists public.sage_user_profiles (
  user_id      text primary key,
  facts        jsonb not null default '[]'::jsonb,   -- [{key, value, source, updated_at}]
  preferences  jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

drop trigger if exists sage_user_profiles_updated_at on public.sage_user_profiles;
create trigger sage_user_profiles_updated_at
  before update on public.sage_user_profiles
  for each row execute function public.sage_set_updated_at();

create table if not exists public.sage_session_summaries (
  id               uuid primary key default gen_random_uuid(),
  user_id          text not null,
  conversation_id  uuid references public.sage_conversations (id) on delete cascade,
  summary          text not null,
  highlights       jsonb not null default '[]'::jsonb,
  model            text,
  created_at       timestamptz not null default now()
);
create index if not exists sage_session_summaries_user_recent_idx
  on public.sage_session_summaries (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Knowledge (search with citations)
-- ---------------------------------------------------------------------------
create table if not exists public.sage_knowledge_chunks (
  id               uuid primary key default gen_random_uuid(),
  source_type      text not null check (source_type in ('corpus', 'pubmed', 'curated', 'web')),
  source_id        text,                 -- e.g. corpus row ID, PMID, DOI
  title            text,
  url              text,
  content          text not null,
  content_hash     text not null unique, -- sha256 of normalized content, stops duplicates at the door
  metadata         jsonb not null default '{}'::jsonb,
  embedding        extensions.vector(768),
  embedding_model  text,
  created_at       timestamptz not null default now()
);
create index if not exists sage_knowledge_chunks_embedding_idx
  on public.sage_knowledge_chunks
  using hnsw (embedding extensions.vector_cosine_ops);
create index if not exists sage_knowledge_chunks_source_idx
  on public.sage_knowledge_chunks (source_type);

-- Nearest-neighbour search, called by the engine through supabase.rpc('sage_match_knowledge', ...)
create or replace function public.sage_match_knowledge(
  query_embedding    extensions.vector(768),
  match_count        int default 8,
  source_types       text[] default null,
  min_similarity     float default 0.0
)
returns table (
  id           uuid,
  source_type  text,
  source_id    text,
  title        text,
  url          text,
  content      text,
  metadata     jsonb,
  similarity   float
)
language sql
stable
set search_path = public, extensions
as $$
  select c.id, c.source_type, c.source_id, c.title, c.url, c.content, c.metadata,
         1 - (c.embedding <=> query_embedding) as similarity
  from public.sage_knowledge_chunks c
  where c.embedding is not null
    and (source_types is null or c.source_type = any (source_types))
    and 1 - (c.embedding <=> query_embedding) >= min_similarity
  order by c.embedding <=> query_embedding
  limit least(greatest(match_count, 1), 50);
$$;

-- ---------------------------------------------------------------------------
-- Monitoring and evals
-- ---------------------------------------------------------------------------
create table if not exists public.sage_turn_logs (
  id                 uuid primary key default gen_random_uuid(),
  conversation_id    uuid references public.sage_conversations (id) on delete set null,
  user_id            text not null,
  request_id         text,
  model              text,
  input_tokens       int not null default 0,
  output_tokens      int not null default 0,
  cache_read_tokens  int not null default 0,
  cost_usd           numeric(12, 6),
  first_token_ms     int,
  total_ms           int,
  tools_used         text[] not null default '{}',
  safety_level       text check (safety_level in ('none', 'concern', 'crisis')),
  error_code         text,
  created_at         timestamptz not null default now()
);
create index if not exists sage_turn_logs_created_idx on public.sage_turn_logs (created_at desc);
create index if not exists sage_turn_logs_conversation_idx on public.sage_turn_logs (conversation_id);

create table if not exists public.sage_eval_runs (
  id              uuid primary key default gen_random_uuid(),
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  git_sha         text,
  engine_version  text,
  chat_model      text,
  case_count      int,
  scores          jsonb not null default '{}'::jsonb,   -- per-dimension averages
  results         jsonb not null default '[]'::jsonb,   -- per-case detail
  notes           text
);

-- ---------------------------------------------------------------------------
-- Lock everything down to the service role
-- ---------------------------------------------------------------------------
alter table public.sage_conversations      enable row level security;
alter table public.sage_messages           enable row level security;
alter table public.sage_user_profiles      enable row level security;
alter table public.sage_session_summaries  enable row level security;
alter table public.sage_knowledge_chunks   enable row level security;
alter table public.sage_turn_logs          enable row level security;
alter table public.sage_eval_runs          enable row level security;

revoke all on function public.sage_match_knowledge(extensions.vector, int, text[], float) from public, anon, authenticated;
grant execute on function public.sage_match_knowledge(extensions.vector, int, text[], float) to service_role;
