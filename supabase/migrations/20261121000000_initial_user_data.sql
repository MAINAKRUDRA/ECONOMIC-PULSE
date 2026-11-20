-- Economic Pulse: user-owned application data.
-- Apply this migration in Supabase SQL Editor or with the Supabase CLI.

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.saved_series (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  series_id text not null,
  label text not null,
  created_at timestamptz not null default now(),
  constraint saved_series_user_series_unique unique (user_id, series_id)
);

alter table public.profiles enable row level security;
alter table public.saved_series enable row level security;

create policy "Users can read their own profile"
  on public.profiles for select
  to authenticated
  using (auth.uid() = id);

create policy "Users can insert their own profile"
  on public.profiles for insert
  to authenticated
  with check (auth.uid() = id);

create policy "Users can update their own profile"
  on public.profiles for update
  to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id);

create policy "Users can read their own saved series"
  on public.saved_series for select
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can insert their own saved series"
  on public.saved_series for insert
  to authenticated
  with check (auth.uid() = user_id);

create policy "Users can update their own saved series"
  on public.saved_series for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can delete their own saved series"
  on public.saved_series for delete
  to authenticated
  using (auth.uid() = user_id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    nullif(new.raw_user_meta_data ->> 'display_name', '')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

grant select, insert, update on public.profiles to authenticated;
grant select, insert, update, delete on public.saved_series to authenticated;
grant usage, select on all sequences in schema public to authenticated;
