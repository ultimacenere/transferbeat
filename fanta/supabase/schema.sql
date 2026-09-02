-- FantaTB — schema Supabase (Postgres). Eseguire nell'SQL Editor del progetto, una volta.
-- Idempotente: si può rilanciare. Tutte le scritture di gioco passano da funzioni RPC (security definer)
-- così le regole (crediti, slot, turni) sono verificate lato server e non nel browser.

create extension if not exists pgcrypto;

-- ---------- profili ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  username text not null,
  created_at timestamptz not null default now()
);
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles(id, username)
  values (new.id, coalesce(new.raw_user_meta_data->>'username', split_part(new.email,'@',1)))
  on conflict (id) do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------- giocatori (listone) ----------
create table if not exists public.players (
  id integer primary key,                 -- id API-Football
  season integer not null default 2026,
  name text not null,
  team text not null,
  team_id integer,
  role text not null check (role in ('P','D','C','A')),
  role_mantra text[] default '{}',
  price integer not null default 1,
  active boolean not null default true,
  stats jsonb default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
create index if not exists players_role_idx on public.players(role, price desc);

-- ---------- leghe ----------
create table if not exists public.leagues (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  admin_id uuid not null references auth.users(id),
  invite_code text not null unique,
  season integer not null default 2026,
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create table if not exists public.league_members (
  league_id uuid not null references public.leagues(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  team_name text not null,
  role text not null default 'member' check (role in ('admin','member')),
  credits integer not null default 500,
  call_order integer,
  joined_at timestamptz not null default now(),
  primary key (league_id, user_id)
);

-- ---------- asta ----------
create table if not exists public.auctions (
  league_id uuid primary key references public.leagues(id) on delete cascade,
  status text not null default 'idle' check (status in ('idle','live','closed')),
  player_id integer references public.players(id),
  current_bid integer,
  bidder_id uuid references auth.users(id),
  ends_at timestamptz,
  timer_seconds integer not null default 20,
  updated_at timestamptz not null default now()
);
create table if not exists public.auction_bids (
  id bigserial primary key,
  league_id uuid not null references public.leagues(id) on delete cascade,
  player_id integer not null references public.players(id),
  user_id uuid not null references auth.users(id),
  amount integer not null,
  created_at timestamptz not null default now()
);
create table if not exists public.rosters (
  league_id uuid not null references public.leagues(id) on delete cascade,
  player_id integer not null references public.players(id),
  user_id uuid not null references auth.users(id) on delete cascade,
  price integer not null default 0,
  acquired_at timestamptz not null default now(),
  primary key (league_id, player_id)
);
create index if not exists rosters_user_idx on public.rosters(league_id, user_id);

-- ---------- campionato di lega, formazioni, voti, risultati ----------
create table if not exists public.matchdays (
  season integer not null default 2026,
  number integer not null,
  starts_at timestamptz,
  ends_at timestamptz,
  status text not null default 'scheduled' check (status in ('scheduled','live','finished','rated')),
  primary key (season, number)
);
create table if not exists public.league_fixtures (
  league_id uuid not null references public.leagues(id) on delete cascade,
  round integer not null,
  matchday integer not null,
  home_id uuid not null references auth.users(id),
  away_id uuid references auth.users(id),      -- null = riposo
  home_goals integer, away_goals integer, home_points numeric, away_points numeric,
  primary key (league_id, round, home_id)
);
create table if not exists public.lineups (
  league_id uuid not null references public.leagues(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  matchday integer not null,
  module text not null default '4-3-3',
  starters integer[] not null default '{}',
  bench integer[] not null default '{}',
  submitted_at timestamptz not null default now(),
  primary key (league_id, user_id, matchday)
);
create table if not exists public.player_ratings (
  season integer not null default 2026,
  matchday integer not null,
  player_id integer not null references public.players(id),
  minutes integer not null default 0,
  voto numeric(4,2),                      -- null = senza voto
  bonus jsonb not null default '{}'::jsonb, -- {"gol":1,"assist":0,"amm":1,...}
  fantavoto numeric(5,2),
  source text not null default 'fantatb-stat',
  raw jsonb default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (season, matchday, player_id)
);
create table if not exists public.rating_overrides (   -- correzioni manuali dell'admin di lega
  league_id uuid not null references public.leagues(id) on delete cascade,
  matchday integer not null,
  player_id integer not null references public.players(id),
  voto numeric(4,2),
  bonus jsonb,
  primary key (league_id, matchday, player_id)
);
create table if not exists public.results (
  league_id uuid not null references public.leagues(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  matchday integer not null,
  total numeric(6,2) not null default 0,
  goals integer not null default 0,
  points integer not null default 0,
  detail jsonb default '{}'::jsonb,
  primary key (league_id, user_id, matchday)
);

-- ---------- helper ----------
create or replace function public.is_member(l uuid) returns boolean
language sql security definer stable set search_path = public as $$
  select exists (select 1 from league_members where league_id = l and user_id = auth.uid());
$$;
create or replace function public.is_admin(l uuid) returns boolean
language sql security definer stable set search_path = public as $$
  select exists (select 1 from league_members where league_id = l and user_id = auth.uid() and role = 'admin');
$$;

-- ---------- RLS ----------
alter table public.profiles enable row level security;
alter table public.players enable row level security;
alter table public.leagues enable row level security;
alter table public.league_members enable row level security;
alter table public.auctions enable row level security;
alter table public.auction_bids enable row level security;
alter table public.rosters enable row level security;
alter table public.matchdays enable row level security;
alter table public.league_fixtures enable row level security;
alter table public.lineups enable row level security;
alter table public.player_ratings enable row level security;
alter table public.rating_overrides enable row level security;
alter table public.results enable row level security;

drop policy if exists profiles_read on public.profiles;
create policy profiles_read on public.profiles for select to authenticated using (true);
drop policy if exists profiles_self on public.profiles;
create policy profiles_self on public.profiles for update to authenticated using (id = auth.uid());

drop policy if exists players_read on public.players;
create policy players_read on public.players for select to anon, authenticated using (true);
drop policy if exists matchdays_read on public.matchdays;
create policy matchdays_read on public.matchdays for select to anon, authenticated using (true);
drop policy if exists ratings_read on public.player_ratings;
create policy ratings_read on public.player_ratings for select to anon, authenticated using (true);

drop policy if exists leagues_read on public.leagues;
create policy leagues_read on public.leagues for select to authenticated using (public.is_member(id));
drop policy if exists leagues_admin_upd on public.leagues;
create policy leagues_admin_upd on public.leagues for update to authenticated using (public.is_admin(id));

drop policy if exists members_read on public.league_members;
create policy members_read on public.league_members for select to authenticated using (public.is_member(league_id));
drop policy if exists members_self_upd on public.league_members;
create policy members_self_upd on public.league_members for update to authenticated
  using (user_id = auth.uid() or public.is_admin(league_id));

drop policy if exists auctions_read on public.auctions;
create policy auctions_read on public.auctions for select to authenticated using (public.is_member(league_id));
drop policy if exists bids_read on public.auction_bids;
create policy bids_read on public.auction_bids for select to authenticated using (public.is_member(league_id));
drop policy if exists rosters_read on public.rosters;
create policy rosters_read on public.rosters for select to authenticated using (public.is_member(league_id));
drop policy if exists fixtures_read on public.league_fixtures;
create policy fixtures_read on public.league_fixtures for select to authenticated using (public.is_member(league_id));
drop policy if exists fixtures_admin on public.league_fixtures;
create policy fixtures_admin on public.league_fixtures for all to authenticated using (public.is_admin(league_id));
drop policy if exists lineups_read on public.lineups;
create policy lineups_read on public.lineups for select to authenticated using (public.is_member(league_id));
drop policy if exists lineups_self on public.lineups;
create policy lineups_self on public.lineups for insert to authenticated with check (user_id = auth.uid() and public.is_member(league_id));
drop policy if exists lineups_self_upd on public.lineups;
create policy lineups_self_upd on public.lineups for update to authenticated using (user_id = auth.uid());
drop policy if exists overrides_read on public.rating_overrides;
create policy overrides_read on public.rating_overrides for select to authenticated using (public.is_member(league_id));
drop policy if exists overrides_admin on public.rating_overrides;
create policy overrides_admin on public.rating_overrides for all to authenticated using (public.is_admin(league_id));
drop policy if exists results_read on public.results;
create policy results_read on public.results for select to authenticated using (public.is_member(league_id));

-- ---------- RPC: leghe ----------
create or replace function public.create_league(p_name text, p_team text, p_settings jsonb)
returns uuid language plpgsql security definer set search_path = public as $$
declare lid uuid; code text; cr integer;
begin
  if auth.uid() is null then raise exception 'non autenticato'; end if;
  code := upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8));
  cr := coalesce((p_settings->>'credits')::int, 500);
  insert into leagues(name, admin_id, invite_code, settings) values (p_name, auth.uid(), code, p_settings) returning id into lid;
  insert into league_members(league_id, user_id, team_name, role, credits, call_order) values (lid, auth.uid(), p_team, 'admin', cr, 1);
  insert into auctions(league_id, timer_seconds) values (lid, coalesce((p_settings->>'timer')::int, 20));
  return lid;
end $$;

create or replace function public.join_league(p_code text, p_team text)
returns uuid language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; n integer;
begin
  if auth.uid() is null then raise exception 'non autenticato'; end if;
  select * into l from leagues where invite_code = upper(trim(p_code));
  if not found then raise exception 'codice invito non valido'; end if;
  select count(*) into n from league_members where league_id = l.id;
  if n >= coalesce((l.settings->>'max_teams')::int, 20) then raise exception 'lega al completo'; end if;
  insert into league_members(league_id, user_id, team_name, role, credits, call_order)
    values (l.id, auth.uid(), p_team, 'member', coalesce((l.settings->>'credits')::int,500), n+1)
    on conflict do nothing;
  return l.id;
end $$;

create or replace function public.update_league_settings(p_league uuid, p_settings jsonb)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not is_admin(p_league) then raise exception 'solo l''admin'; end if;
  update leagues set settings = p_settings where id = p_league;
  update auctions set timer_seconds = coalesce((p_settings->>'timer')::int, timer_seconds) where league_id = p_league;
end $$;

-- ---------- RPC: asta ----------
-- slot liberi per ruolo di un membro, secondo le regole della lega (settings.slots = {"P":3,"D":8,"C":8,"A":6})
create or replace function public.slots_left(p_league uuid, p_user uuid, p_role text)
returns integer language plpgsql security definer stable set search_path = public as $$
declare mx integer; have integer;
begin
  select coalesce((settings->'slots'->>p_role)::int, case p_role when 'P' then 3 when 'D' then 8 when 'C' then 8 else 6 end)
    into mx from leagues where id = p_league;
  select count(*) into have from rosters r join players p on p.id = r.player_id
    where r.league_id = p_league and r.user_id = p_user and p.role = p_role;
  return mx - have;
end $$;

create or replace function public.start_auction(p_league uuid, p_player integer, p_start integer)
returns void language plpgsql security definer set search_path = public as $$
declare a auctions%rowtype;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin apre le aste'; end if;
  select * into a from auctions where league_id = p_league for update;
  if a.status = 'live' then raise exception 'asta già in corso'; end if;
  if exists (select 1 from rosters where league_id = p_league and player_id = p_player) then
    raise exception 'giocatore già assegnato'; end if;
  update auctions set status = 'live', player_id = p_player, current_bid = greatest(coalesce(p_start,1),1),
    bidder_id = null, ends_at = now() + make_interval(secs => timer_seconds), updated_at = now()
    where league_id = p_league;
end $$;

create or replace function public.place_bid(p_league uuid, p_amount integer)
returns void language plpgsql security definer set search_path = public as $$
declare a auctions%rowtype; m league_members%rowtype; r text; left_slots integer; total_slots integer;
begin
  if not is_member(p_league) then raise exception 'non sei in questa lega'; end if;
  select * into a from auctions where league_id = p_league for update;
  if a.status <> 'live' then raise exception 'nessuna asta in corso'; end if;
  if a.bidder_id is not null and p_amount <= a.current_bid then raise exception 'offerta troppo bassa'; end if;
  if a.bidder_id is null and p_amount < a.current_bid then raise exception 'offerta sotto la base'; end if;
  if a.bidder_id = auth.uid() then raise exception 'sei già il miglior offerente'; end if;
  select * into m from league_members where league_id = p_league and user_id = auth.uid();
  select role into r from players where id = a.player_id;
  left_slots := slots_left(p_league, auth.uid(), r);
  if left_slots <= 0 then raise exception 'rosa completa per il ruolo %', r; end if;
  -- deve restare almeno 1 credito per ogni altro slot ancora vuoto
  select coalesce(sum(slots_left(p_league, auth.uid(), x)),0) into total_slots from unnest(array['P','D','C','A']) x;
  if p_amount > m.credits - (total_slots - 1) then
    raise exception 'crediti insufficienti: devono restarne % per gli altri slot', total_slots - 1; end if;
  update auctions set current_bid = p_amount, bidder_id = auth.uid(),
    ends_at = greatest(ends_at, now() + make_interval(secs => timer_seconds)), updated_at = now()
    where league_id = p_league;
  insert into auction_bids(league_id, player_id, user_id, amount) values (p_league, a.player_id, auth.uid(), p_amount);
end $$;

create or replace function public.close_auction(p_league uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare a auctions%rowtype; res jsonb;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin chiude le aste'; end if;
  select * into a from auctions where league_id = p_league for update;
  if a.status <> 'live' then raise exception 'nessuna asta in corso'; end if;
  if a.bidder_id is not null then
    insert into rosters(league_id, player_id, user_id, price) values (p_league, a.player_id, a.bidder_id, a.current_bid);
    update league_members set credits = credits - a.current_bid where league_id = p_league and user_id = a.bidder_id;
    res := jsonb_build_object('assigned', true, 'player_id', a.player_id, 'user_id', a.bidder_id, 'price', a.current_bid);
  else
    res := jsonb_build_object('assigned', false, 'player_id', a.player_id);
  end if;
  update auctions set status = 'closed', updated_at = now() where league_id = p_league;
  return res;
end $$;

-- assegnazione diretta (asta fatta altrove, o correzione) e rimozione con rimborso
create or replace function public.assign_player(p_league uuid, p_player integer, p_user uuid, p_price integer)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not is_admin(p_league) then raise exception 'solo l''admin'; end if;
  insert into rosters(league_id, player_id, user_id, price) values (p_league, p_player, p_user, greatest(p_price,0));
  update league_members set credits = credits - greatest(p_price,0) where league_id = p_league and user_id = p_user;
end $$;
create or replace function public.release_player(p_league uuid, p_player integer)
returns void language plpgsql security definer set search_path = public as $$
declare r rosters%rowtype;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin'; end if;
  delete from rosters where league_id = p_league and player_id = p_player returning * into r;
  if found then update league_members set credits = credits + r.price where league_id = p_league and user_id = r.user_id; end if;
end $$;

-- ---------- realtime ----------
do $$ begin
  begin alter publication supabase_realtime add table public.auctions; exception when duplicate_object then null; end;
  begin alter publication supabase_realtime add table public.auction_bids; exception when duplicate_object then null; end;
  begin alter publication supabase_realtime add table public.rosters; exception when duplicate_object then null; end;
  begin alter publication supabase_realtime add table public.league_members; exception when duplicate_object then null; end;
end $$;

-- ---------- grant ----------
grant usage on schema public to anon, authenticated;
grant select on public.players, public.matchdays, public.player_ratings to anon, authenticated;
grant select on all tables in schema public to authenticated;
grant insert, update on public.lineups, public.rating_overrides, public.league_fixtures, public.profiles, public.league_members, public.leagues to authenticated;
grant execute on all functions in schema public to authenticated;
