-- Economic Pulse: expanded profiles and a private evidence vault.
-- Apply after 20261121000000_initial_user_data.sql.

alter table public.profiles
  add column if not exists full_name text,
  add column if not exists phone text,
  add column if not exists account_type text not null default 'personal',
  add column if not exists job_title text,
  add column if not exists business_name text,
  add column if not exists business_website text,
  add column if not exists business_industry text,
  add column if not exists business_registration_no text,
  add column if not exists business_address text;

alter table public.profiles drop constraint if exists profiles_account_type_check;
alter table public.profiles add constraint profiles_account_type_check
  check (account_type in ('personal', 'business'));

update public.profiles set full_name = coalesce(full_name, display_name) where full_name is null;

create table if not exists public.evidence_files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  file_name text not null,
  storage_path text not null unique,
  mime_type text,
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 20971520),
  category text not null default 'general',
  created_at timestamptz not null default now()
);

alter table public.evidence_files enable row level security;

drop policy if exists "Users can read their own evidence metadata" on public.evidence_files;
create policy "Users can read their own evidence metadata"
  on public.evidence_files for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Users can insert their own evidence metadata" on public.evidence_files;
create policy "Users can insert their own evidence metadata"
  on public.evidence_files for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists "Users can delete their own evidence metadata" on public.evidence_files;
create policy "Users can delete their own evidence metadata"
  on public.evidence_files for delete to authenticated using (auth.uid() = user_id);

grant select, insert, delete on public.evidence_files to authenticated;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'evidence-vault', 'evidence-vault', false, 20971520,
  array[
    'application/pdf', 'image/jpeg', 'image/png', 'image/webp',
    'text/csv', 'text/plain', 'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ]
)
on conflict (id) do update set
  public = false,
  file_size_limit = 20971520,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Users can read files in their own evidence folder" on storage.objects;
create policy "Users can read files in their own evidence folder"
  on storage.objects for select to authenticated
  using (bucket_id = 'evidence-vault' and (storage.foldername(name))[1] = (select auth.uid()::text));

drop policy if exists "Users can upload files to their own evidence folder" on storage.objects;
create policy "Users can upload files to their own evidence folder"
  on storage.objects for insert to authenticated
  with check (bucket_id = 'evidence-vault' and (storage.foldername(name))[1] = (select auth.uid()::text));

drop policy if exists "Users can delete files in their own evidence folder" on storage.objects;
create policy "Users can delete files in their own evidence folder"
  on storage.objects for delete to authenticated
  using (bucket_id = 'evidence-vault' and (storage.foldername(name))[1] = (select auth.uid()::text));

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, full_name, phone, account_type)
  values (
    new.id,
    nullif(new.raw_user_meta_data ->> 'full_name', ''),
    nullif(new.raw_user_meta_data ->> 'full_name', ''),
    nullif(new.raw_user_meta_data ->> 'phone', ''),
    'personal'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;
