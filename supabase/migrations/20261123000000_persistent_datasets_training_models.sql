-- Persistent Economic Pulse dataset, training queue, model registry and forecasts.
-- Apply after the existing profile/evidence migrations.
create extension if not exists pgcrypto;

create table if not exists public.datasets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  series_id text not null check (length(trim(series_id)) > 0 and series_id not like 'demo\_%'),
  source_name text not null check (length(trim(source_name)) > 0),
  source_url text not null check (source_url like 'https://%'),
  rights_tag text not null check (length(trim(rights_tag)) > 0),
  file_name text not null,
  storage_path text not null unique,
  content_type text not null default 'text/csv',
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 20971520),
  sha256 text,
  status text not null default 'uploaded' check (status in ('uploaded','queued','training','completed','failed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.training_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  dataset_id uuid not null references public.datasets(id) on delete restrict,
  status text not null default 'queued' check (status in ('queued','running','completed','failed')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 2 check (max_attempts between 1 and 5),
  error text,
  result jsonb,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.model_versions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  dataset_id uuid not null references public.datasets(id) on delete restrict,
  training_job_id uuid not null unique references public.training_jobs(id) on delete restrict,
  series_id text not null,
  version text not null,
  status text not null check (status in ('candidate','published','rejected','failed')),
  is_published boolean not null default false,
  storage_path text not null,
  manifest jsonb not null,
  metrics jsonb not null default '{}'::jsonb,
  forecast_payload jsonb not null,
  observations_payload jsonb not null,
  model_card text not null,
  created_at timestamptz not null default now(),
  published_at timestamptz default now(),
  unique (user_id, series_id, version)
);

create table if not exists public.model_evaluations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  model_version_id uuid not null references public.model_versions(id) on delete cascade,
  report jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.forecasts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  model_version_id uuid not null references public.model_versions(id) on delete cascade,
  series_id text not null,
  target text not null,
  origin text not null,
  horizon_end text not null,
  median double precision not null,
  lower_bound double precision,
  upper_bound double precision,
  unit text not null,
  mode text not null default 'research',
  published_at timestamptz not null default now(),
  check (median >= 0),
  check ((lower_bound is null and upper_bound is null) or
         (lower_bound is not null and upper_bound is not null and 0 <= lower_bound and lower_bound <= median and median <= upper_bound))
);

create index if not exists datasets_user_created_idx on public.datasets(user_id, created_at desc);
create index if not exists training_jobs_queue_idx on public.training_jobs(status, created_at) where status = 'queued';
create index if not exists training_jobs_user_created_idx on public.training_jobs(user_id, created_at desc);
create index if not exists model_versions_user_series_idx on public.model_versions(user_id, series_id, published_at desc);
create index if not exists forecasts_user_series_idx on public.forecasts(user_id, series_id, published_at desc);

alter table public.datasets enable row level security;
alter table public.training_jobs enable row level security;
alter table public.model_versions enable row level security;
alter table public.model_evaluations enable row level security;
alter table public.forecasts enable row level security;

drop policy if exists "Owners read their datasets" on public.datasets;
create policy "Owners read their datasets" on public.datasets for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Owners register their datasets" on public.datasets;
create policy "Owners register their datasets" on public.datasets for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists "Owners delete their datasets" on public.datasets;
create policy "Owners delete their datasets" on public.datasets for delete to authenticated using (auth.uid() = user_id);

drop policy if exists "Owners read their training jobs" on public.training_jobs;
create policy "Owners read their training jobs" on public.training_jobs for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Owners enqueue their training jobs" on public.training_jobs;
create policy "Owners enqueue their training jobs" on public.training_jobs for insert to authenticated
with check (auth.uid() = user_id and exists (select 1 from public.datasets d where d.id = dataset_id and d.user_id = auth.uid()));

drop policy if exists "Owners read their model versions" on public.model_versions;
create policy "Owners read their model versions" on public.model_versions for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Owners read their evaluations" on public.model_evaluations;
create policy "Owners read their evaluations" on public.model_evaluations for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Owners read their forecasts" on public.forecasts;
create policy "Owners read their forecasts" on public.forecasts for select to authenticated using (auth.uid() = user_id);

-- Private buckets. Object names are prefixed with the authenticated user's UUID.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('economic-datasets','economic-datasets',false,20971520,array['text/csv','application/vnd.ms-excel','application/octet-stream'])
on conflict (id) do update set public=false, file_size_limit=20971520,
  allowed_mime_types=excluded.allowed_mime_types;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('model-artifacts','model-artifacts',false,104857600,array['application/json','text/plain','application/octet-stream'])
on conflict (id) do update set public=false, file_size_limit=104857600,
  allowed_mime_types=excluded.allowed_mime_types;

drop policy if exists "Users read own economic datasets" on storage.objects;
create policy "Users read own economic datasets" on storage.objects for select to authenticated
using (bucket_id='economic-datasets' and (storage.foldername(name))[1]=(select auth.uid()::text));
drop policy if exists "Users upload own economic datasets" on storage.objects;
create policy "Users upload own economic datasets" on storage.objects for insert to authenticated
with check (bucket_id='economic-datasets' and (storage.foldername(name))[1]=(select auth.uid()::text));
drop policy if exists "Users delete own economic datasets" on storage.objects;
create policy "Users delete own economic datasets" on storage.objects for delete to authenticated
using (bucket_id='economic-datasets' and (storage.foldername(name))[1]=(select auth.uid()::text));

drop policy if exists "Users read own model artifacts" on storage.objects;
create policy "Users read own model artifacts" on storage.objects for select to authenticated
using (bucket_id='model-artifacts' and (storage.foldername(name))[1]=(select auth.uid()::text));

-- A worker atomically claims one queued job. Service role only.
create or replace function public.claim_economic_pulse_training_job()
returns setof public.training_jobs
language sql
security definer
set search_path = public
as $$
  update public.training_jobs
     set status='running', started_at=coalesce(started_at, now()),
         attempt_count=attempt_count+1, updated_at=now()
   where id = (
     select id from public.training_jobs
      where (status='queued' or (status='running' and updated_at < now() - interval '30 minutes')) and attempt_count < max_attempts
      order by created_at
      for update skip locked
      limit 1
   )
  returning *;
$$;
revoke all on function public.claim_economic_pulse_training_job() from public, anon, authenticated;
grant execute on function public.claim_economic_pulse_training_job() to service_role;
