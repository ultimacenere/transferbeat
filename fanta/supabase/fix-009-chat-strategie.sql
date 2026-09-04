-- FantaTB fix 009: (1) chat rapida utente <-> staff (tabella messages, staff); (2) strategie d'asta condivisibili (tabella strategies).
-- Da incollare nell'SQL Editor di Supabase in un editor VUOTO. Idempotente. Vedi kb/FANTATB.md §17.

-- ==================== 1) CHAT: una conversazione per utente ====================
create table if not exists public.staff (
  user_id uuid primary key references auth.users(id) on delete cascade,
  name text not null default ''
);
create table if not exists public.messages (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,     -- proprietario della conversazione (l'utente)
  author uuid not null references auth.users(id) on delete cascade,      -- chi ha scritto (l'utente o un membro dello staff)
  from_staff boolean not null default false,
  text text not null check (length(text) between 1 and 2000),
  page text not null default '',                                         -- vista da cui e' partito il messaggio
  read_by_staff boolean not null default false,
  read_by_user boolean not null default true,
  created_at timestamptz not null default now()
);
create index if not exists messages_user_idx on public.messages(user_id, created_at);
create or replace function public.is_staff() returns boolean
language sql security definer stable set search_path = public as $$
  select exists (select 1 from staff where user_id = auth.uid());
$$;
alter table public.staff enable row level security;
alter table public.messages enable row level security;
drop policy if exists staff_read on public.staff;
create policy staff_read on public.staff for select to authenticated using (user_id = auth.uid() or public.is_staff());
drop policy if exists messages_read on public.messages;
drop policy if exists messages_insert on public.messages;
drop policy if exists messages_update on public.messages;
create policy messages_read on public.messages for select to authenticated using (user_id = auth.uid() or public.is_staff());
create policy messages_insert on public.messages for insert to authenticated
  with check (author = auth.uid() and ((user_id = auth.uid() and from_staff = false) or (public.is_staff() and from_staff = true)));
create policy messages_update on public.messages for update to authenticated using (user_id = auth.uid() or public.is_staff());
grant select on public.staff to authenticated;
grant select, insert, update on public.messages to authenticated;
grant usage, select on sequence public.messages_id_seq to authenticated;
do $$ begin
  begin alter publication supabase_realtime add table public.messages; exception when duplicate_object then null; end;
end $$;
-- Lo staff (chi risponde): l'account dell'amministratore. Aggiungere altri con un altro insert.
insert into public.staff(user_id, name)
  select id, 'Pierluigi' from auth.users where email = 'pierluigicella85@gmail.com'
  on conflict (user_id) do nothing;

-- ==================== 2) STRATEGIE D'ASTA ====================
create table if not exists public.strategies (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  description text not null default '',
  author text not null default '',
  teams integer not null default 8 check (teams between 2 and 20),
  credits integer not null default 500 check (credits between 50 and 5000),
  slots jsonb not null default '{"P":3,"D":8,"C":8,"A":6}'::jsonb,
  budget jsonb not null default '{"P":8,"D":22,"C":25,"A":45}'::jsonb,       -- % del budget per ruolo
  targets jsonb not null default '{}'::jsonb,                                -- {"A":{"1":1,"2":1,"3":2}, ...} giocatori da prendere per tier
  list_id uuid references public.lists(id) on delete set null,               -- lista obiettivi collegata
  is_public boolean not null default false,
  featured boolean not null default false,                                   -- strategie consigliate (TransferBeat): a mano da SQL o da fanta_strategie.py
  share_code text not null unique default upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.strategies enable row level security;
drop policy if exists strategies_own on public.strategies;
drop policy if exists strategies_public on public.strategies;
create policy strategies_own on public.strategies for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy strategies_public on public.strategies for select to anon, authenticated using (is_public or featured);
grant select on public.strategies to anon, authenticated;
grant insert, update, delete on public.strategies to authenticated;

-- Copia una strategia condivisa (con la sua lista obiettivi, se non e' gia' mia) fra le proprie.
create or replace function public.copy_strategy(p_code text, p_name text default null)
returns uuid language plpgsql security definer set search_path = public as $$
declare src strategies%rowtype; nid uuid; lid uuid; l lists%rowtype;
begin
  if auth.uid() is null then raise exception 'non autenticato'; end if;
  select * into src from strategies where share_code = upper(trim(p_code)) and (is_public or featured or owner_id = auth.uid());
  if not found then raise exception 'strategia non trovata'; end if;
  lid := src.list_id;
  if lid is not null then
    select * into l from lists where id = lid;
    if found and l.owner_id <> auth.uid() then
      insert into lists(owner_id, name, description, author) values (auth.uid(), l.name || ' (copia)', l.description, '') returning id into lid;
      insert into list_items(list_id, player_id, tier, note) select lid, player_id, tier, note from list_items where list_id = l.id;
    end if;
  end if;
  insert into strategies(owner_id, name, description, author, teams, credits, slots, budget, targets, list_id)
    values (auth.uid(), coalesce(nullif(trim(p_name), ''), src.name || ' (copia)'), src.description, '', src.teams, src.credits, src.slots, src.budget, src.targets, lid)
    returning id into nid;
  return nid;
end $$;
grant execute on function public.copy_strategy(text, text) to authenticated;
grant execute on function public.is_staff() to anon, authenticated;
