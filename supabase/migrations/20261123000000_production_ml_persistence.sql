-- Economic Pulse: durable datasets, training jobs, model artifacts and publications.
-- Apply after the two existing profile/evidence migrations.

create table if not exists public.datasets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  file_name text not null,
  storage_path text not null unique,
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 20971520),
  source_name text not null,
  rights_tag text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.training_jobs (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  dataset_id uuid not null references public.datasets(id) on delete restrict,
  series_id text not null,
  source_name text not null,
  rights_tag text not null,
  status text not null default 'queued'
    check (status in ('queued','training','completed','failed','interrupted')),
  result jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists training_jobs_user_created_idx
  on public.training_jobs(user_id, created_at desc);

create table if not exists public.model_artifacts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  training_job_id uuid not null references public.training_jobs(id) on delete cascade,
  artifact_type text not null,
  storage_path text not null unique,
  size_bytes bigint not null check (size_bytes > 0),
  checksum_sha256 text,
  created_at timestamptz not null default now()
);

create table if not exists public.published_bundles (
  id uuid primary key default gen_random_uuid(),
  training_job_id uuid not null references public.training_jobs(id) on delete restrict,
  series_id text not null,
  storage_path text not null unique,
  manifest jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists published_bundles_latest_idx
  on public.published_bundles(created_at desc);

alter table public.datasets enable row level security;
alter table public.training_jobs enable row level security;
alter table public.model_artifacts enable row level security;
alter table public.published_bundles enable row level security;

drop policy if exists "Users can read their own datasets" on public.datasets;
create policy "Users can read their own datasets" on public.datasets
  for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Users can insert their own datasets" on public.datasets;
create policy "Users can insert their own datasets" on public.datasets
  for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists "Users can delete their own datasets" on public.datasets;
create policy "Users can delete their own datasets" on public.datasets
  for delete to authenticated using (auth.uid() = user_id);

drop policy if exists "Users can read their own training jobs" on public.training_jobs;
create policy "Users can read their own training jobs" on public.training_jobs
  for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Users can insert their own training jobs" on public.training_jobs;
create policy "Users can insert their own training jobs" on public.training_jobs
  for insert to authenticated with check (auth.uid() = user_id);

drop policy if exists "Users can read their own model artifacts" on public.model_artifacts;
create policy "Users can read their own model artifacts" on public.model_artifacts
  for select to authenticated using (auth.uid() = user_id);

drop policy if exists "Published bundles are readable" on public.published_bundles;
create policy "Published bundles are readable" on public.published_bundles
  for select to authenticated using (true);

grant select, insert, delete on public.datasets to authenticated;
grant select, insert on public.training_jobs to authenticated;
grant select on public.model_artifacts, public.published_bundles to authenticated;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('economic-datasets','economic-datasets',false,20971520,array['text/csv','application/vnd.ms-excel','application/octet-stream']),
  ('model-artifacts','model-artifacts',false,104857600,array['application/json','application/zip','application/octet-stream'])
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Users can read their own economic datasets" on storage.objects;
create policy "Users can read their own economic datasets" on storage.objects
  for select to authenticated using (
    bucket_id = 'economic-datasets' and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can upload their own economic datasets" on storage.objects;
create policy "Users can upload their own economic datasets" on storage.objects
  for insert to authenticated with check (
    bucket_id = 'economic-datasets' and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can delete their own economic datasets" on storage.objects;
create policy "Users can delete their own economic datasets" on storage.objects
  for delete to authenticated using (
    bucket_id = 'economic-datasets' and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

drop policy if exists "Users can read their own model artifacts" on storage.objects;
create policy "Users can read their own model artifacts" on storage.objects
  for select to authenticated using (
    bucket_id = 'model-artifacts' and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can upload their own model artifacts" on storage.objects;
create policy "Users can upload their own model artifacts" on storage.objects
  for insert to authenticated with check (
    bucket_id = 'model-artifacts' and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can delete their own model artifacts" on storage.objects;
create policy "Users can delete their own model artifacts" on storage.objects
  for delete to authenticated using (
    bucket_id = 'model-artifacts' and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
