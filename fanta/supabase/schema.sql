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

-- ==================== FASE 2 (identico a fix-002-fase2.sql) ====================
-- FantaTB fase 2: formazioni con deadline, calendario di lega, calcolo punteggi e classifica.
-- Da incollare nell'SQL Editor dopo lo schema base. Idempotente.

-- le formazioni si scrivono SOLO via RPC (controllo deadline e validità lato server)
drop policy if exists lineups_self on public.lineups;
drop policy if exists lineups_self_upd on public.lineups;

-- fantavoto di un giocatore per una lega: voto e bonus (con override di lega) x pesi della lega
create or replace function public.fv_of(p_league uuid, p_season integer, p_matchday integer, p_player integer,
                                       out voto numeric, out fantavoto numeric)
language plpgsql security definer stable set search_path = public as $$
declare b jsonb; ov rating_overrides%rowtype; w jsonb; k text; acc numeric := 0;
begin
  select pr.voto, pr.bonus into voto, b from player_ratings pr
    where pr.season = p_season and pr.matchday = p_matchday and pr.player_id = p_player;
  select * into ov from rating_overrides where league_id = p_league and matchday = p_matchday and player_id = p_player;
  if found then
    if ov.voto is not null then voto := ov.voto; end if;
    if ov.bonus is not null then b := ov.bonus; end if;
  end if;
  if voto is null then fantavoto := null; return; end if;
  select coalesce(settings->'bonus', '{}'::jsonb) into w from leagues where id = p_league;
  for k in select jsonb_object_keys(coalesce(b, '{}'::jsonb)) loop
    acc := acc + (b->>k)::numeric * coalesce((w->>k)::numeric,
      case k when 'gol' then 3 when 'assist' then 1 when 'rig_sbagliato' then -3 when 'rig_parato' then 3
             when 'gol_subito' then -1 when 'autogol' then -2 when 'amm' then -0.5 when 'esp' then -1 else 0 end);
  end loop;
  fantavoto := voto + acc;
end $$;

-- salvataggio formazione: 11 titolari coerenti col modulo, tutti in rosa, panchina senza doppioni, prima della deadline
create or replace function public.save_lineup(p_league uuid, p_matchday integer, p_module text, p_starters integer[], p_bench integer[])
returns void language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; dl timestamptz; parts text[]; want jsonb; cnt jsonb; r text; n integer; pid integer;
begin
  if not is_member(p_league) then raise exception 'non sei in questa lega'; end if;
  select * into l from leagues where id = p_league;
  select starts_at into dl from matchdays where season = l.season and number = p_matchday;
  if dl is not null and now() > dl then raise exception 'formazioni chiuse: la giornata % è iniziata', p_matchday; end if;
  if p_module !~ '^[3-5]-[2-5]-[1-4]$' then raise exception 'modulo non valido'; end if;
  parts := string_to_array(p_module, '-');
  if parts[1]::int + parts[2]::int + parts[3]::int <> 10 then raise exception 'modulo non valido'; end if;
  if coalesce(array_length(p_starters, 1), 0) <> 11 then raise exception 'servono 11 titolari'; end if;
  if (select count(distinct x) from unnest(p_starters || p_bench) x) <> array_length(p_starters || p_bench, 1) then
    raise exception 'giocatore ripetuto tra titolari e panchina'; end if;
  if exists (select 1 from unnest(p_starters || p_bench) x where not exists
      (select 1 from rosters where league_id = p_league and user_id = auth.uid() and player_id = x)) then
    raise exception 'un giocatore non è nella tua rosa'; end if;
  want := jsonb_build_object('P', 1, 'D', parts[1]::int, 'C', parts[2]::int, 'A', parts[3]::int);
  for r in select unnest(array['P','D','C','A']) loop
    select count(*) into n from unnest(p_starters) x join players p on p.id = x where p.role = r;
    if n <> (want->>r)::int then raise exception 'modulo %: servono % %', p_module, want->>r, r; end if;
  end loop;
  insert into lineups(league_id, user_id, matchday, module, starters, bench, submitted_at)
    values (p_league, auth.uid(), p_matchday, p_module, p_starters, coalesce(p_bench, '{}'), now())
    on conflict (league_id, user_id, matchday) do update
      set module = excluded.module, starters = excluded.starters, bench = excluded.bench, submitted_at = now();
end $$;

-- calendario: girone all'italiana (Berger) sui membri in ordine di call_order; p_gironi = quante volte (2 = andata/ritorno)
create or replace function public.generate_calendar(p_league uuid, p_start integer, p_gironi integer)
returns integer language plpgsql security definer set search_path = public as $$
declare arr uuid[]; n integer; rounds integer; g integer; k integer; i integer; md integer; rnd integer := 0; created integer := 0;
  h uuid; a uuid; flip boolean;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin'; end if;
  select array_agg(user_id order by call_order, joined_at) into arr from league_members where league_id = p_league;
  n := coalesce(array_length(arr, 1), 0);
  if n < 2 then raise exception 'servono almeno 2 squadre'; end if;
  if n % 2 = 1 then arr := arr || null::uuid; n := n + 1; end if;
  rounds := n - 1;
  delete from results where league_id = p_league;
  delete from league_fixtures where league_id = p_league;
  for g in 1..greatest(p_gironi, 1) loop
    for k in 1..rounds loop
      rnd := rnd + 1; md := p_start + rnd - 1;
      exit when md > 38;
      for i in 1..n/2 loop
        h := arr[i]; a := arr[n + 1 - i];
        flip := ((k + g) % 2 = 0);
        if i = 1 then flip := not flip; end if;      -- la squadra fissa alterna casa/trasferta
        if flip then h := arr[n + 1 - i]; a := arr[i]; end if;
        if h is null then h := a; a := null; end if;  -- riposo
        insert into league_fixtures(league_id, round, matchday, home_id, away_id) values (p_league, rnd, md, h, a);
        created := created + 1;
      end loop;
      arr := arr[1:1] || arr[n:n] || arr[2:n-1];
    end loop;
  end loop;
  return created;
end $$;

-- calcolo di una giornata per una lega: fantavoti dei titolari, sostituzioni dalla panchina (stesso ruolo, in ordine),
-- modificatore difesa (portiere + 3 migliori difensori, con almeno 4 difensori), gol a soglie, punti scontri.
create or replace function public.compute_matchday(p_league uuid, p_matchday integer)
returns jsonb language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; s jsonb; max_subs integer; goal_base numeric; goal_step numeric; mod_def boolean;
  m record; lu lineups%rowtype; has_lu boolean; tot numeric; det jsonb; pid integer; orig integer; subid integer; r text;
  v numeric; fv numeric; subs integer; used integer[]; bp integer; bv numeric; bfv numeric; def_v numeric[]; gk_v numeric;
  avgd numeric; modv numeric; n_goals integer; teams integer := 0; fx record; hg integer; ag integer; h_tot numeric; a_tot numeric;
begin
  if not (is_admin(p_league) or coalesce(current_setting('request.jwt.claims', true)::jsonb->>'role', '') = 'service_role') then
    raise exception 'solo l''admin'; end if;
  select * into l from leagues where id = p_league; s := l.settings;
  max_subs := coalesce((s->>'max_subs')::int, 3); goal_base := coalesce((s->>'goal_base')::numeric, 66);
  goal_step := coalesce((s->>'goal_step')::numeric, 6); mod_def := coalesce((s->>'mod_difesa')::boolean, false);
  for m in select user_id from league_members where league_id = p_league loop
    tot := 0; det := '[]'::jsonb; subs := 0; used := '{}'; def_v := '{}'; gk_v := null; modv := 0;
    select * into lu from lineups where league_id = p_league and user_id = m.user_id and matchday = p_matchday;
    has_lu := found;
    if has_lu then
      foreach orig in array lu.starters loop
        pid := orig; subid := null;
        select role into r from players where id = pid;
        select voto, fantavoto into v, fv from fv_of(p_league, l.season, p_matchday, pid);
        if fv is null and subs < max_subs and lu.bench is not null then
          foreach bp in array lu.bench loop
            continue when bp = any(used) or (select role from players where id = bp) <> r;
            select voto, fantavoto into bv, bfv from fv_of(p_league, l.season, p_matchday, bp);
            if bfv is not null then
              used := used || bp; subs := subs + 1; subid := bp; pid := bp; v := bv; fv := bfv; exit;
            end if;
          end loop;
        end if;
        det := det || jsonb_build_object('player_id', orig, 'sub', subid, 'voto', v, 'fv', coalesce(fv, 0), 'role', r);
        tot := tot + coalesce(fv, 0);
        if v is not null then
          if r = 'P' then gk_v := v; elsif r = 'D' then def_v := def_v || v; end if;
        end if;
      end loop;
      if mod_def and gk_v is not null and coalesce(array_length(def_v, 1), 0) >= 4 then
        select avg(x) into avgd from (select x from unnest(def_v) x order by x desc limit 3) t;
        avgd := (avgd * 3 + gk_v) / 4;
        modv := case when avgd >= 7.25 then 6 when avgd >= 7 then 5 when avgd >= 6.75 then 4
                     when avgd >= 6.5 then 3 when avgd >= 6.25 then 2 when avgd >= 6 then 1 else 0 end;
        tot := tot + modv;
      end if;
    end if;
    n_goals := case when tot >= goal_base then 1 + floor((tot - goal_base) / goal_step)::int else 0 end;
    insert into results(league_id, user_id, matchday, total, goals, points, detail)
      values (p_league, m.user_id, p_matchday, tot, n_goals, 0,
              jsonb_build_object('players', det, 'subs', subs, 'mod_difesa', modv, 'lineup', has_lu))
      on conflict (league_id, user_id, matchday) do update
        set total = excluded.total, goals = excluded.goals, points = 0, detail = excluded.detail;
    teams := teams + 1;
  end loop;
  for fx in select * from league_fixtures where league_id = p_league and matchday = p_matchday loop
    select goals, total into hg, h_tot from results where league_id = p_league and user_id = fx.home_id and matchday = p_matchday;
    if fx.away_id is null then
      update league_fixtures set home_goals = hg, home_points = h_tot where league_id = p_league and round = fx.round and home_id = fx.home_id;
      continue;
    end if;
    select goals, total into ag, a_tot from results where league_id = p_league and user_id = fx.away_id and matchday = p_matchday;
    update league_fixtures set home_goals = hg, away_goals = ag, home_points = h_tot, away_points = a_tot
      where league_id = p_league and round = fx.round and home_id = fx.home_id;
    update results set points = case when hg > ag then 3 when hg = ag then 1 else 0 end
      where league_id = p_league and user_id = fx.home_id and matchday = p_matchday;
    update results set points = case when ag > hg then 3 when hg = ag then 1 else 0 end
      where league_id = p_league and user_id = fx.away_id and matchday = p_matchday;
  end loop;
  return jsonb_build_object('teams', teams, 'matchday', p_matchday);
end $$;

-- tutte le leghe (usata dal cron con la service key)
create or replace function public.compute_all_leagues(p_matchday integer)
returns integer language plpgsql security definer set search_path = public as $$
declare lid uuid; n integer := 0;
begin
  if coalesce(current_setting('request.jwt.claims', true)::jsonb->>'role', '') <> 'service_role' then raise exception 'solo il servizio'; end if;
  for lid in select id from leagues loop
    perform compute_matchday(lid, p_matchday); n := n + 1;
  end loop;
  return n;
end $$;

grant execute on all functions in schema public to authenticated;

-- ==================== FIX 004 (regole estese, identico a fix-004-regole.sql) ====================
-- FantaTB fix 004: regole estese. Modificatori difesa/centrocampo/attacco, porta inviolata, fattore casa/trasferta,
-- pesi bonus/malus, soglie gol e sostituzioni personalizzabili. Dettaglio risultati con bonus per giocatore ed extra.
-- Chiavi in leagues.settings: mod_difesa, mod_centrocampo, mod_attacco (bool) · bonus_casa, bonus_trasferta (numeric)
-- · bonus {gol, assist, rig_sbagliato, rig_parato, gol_subito, autogol, amm, esp, porta_inviolata} · goal_base, goal_step, max_subs · phase.

create or replace function public.mod_table(avg_v numeric) returns numeric
language sql immutable as $$
  select case when avg_v >= 7.25 then 6 when avg_v >= 7 then 5 when avg_v >= 6.75 then 4
              when avg_v >= 6.5 then 3 when avg_v >= 6.25 then 2 when avg_v >= 6 then 1 else 0 end;
$$;
create or replace function public.goals_of(tot numeric, base numeric, step numeric) returns integer
language sql immutable as $$
  select case when tot >= base then 1 + floor((tot - base) / greatest(step, 0.5))::int else 0 end;
$$;

drop function if exists public.fv_of(uuid, integer, integer, integer);
create or replace function public.fv_of(p_league uuid, p_season integer, p_matchday integer, p_player integer,
                                       out voto numeric, out fantavoto numeric, out bonus jsonb, out minutes integer)
language plpgsql security definer stable set search_path = public as $$
declare ov rating_overrides%rowtype; w jsonb; k text; acc numeric := 0;
begin
  select pr.voto, pr.bonus, pr.minutes into voto, bonus, minutes from player_ratings pr
    where pr.season = p_season and pr.matchday = p_matchday and pr.player_id = p_player;
  select * into ov from rating_overrides where league_id = p_league and matchday = p_matchday and player_id = p_player;
  if found then
    if ov.voto is not null then voto := ov.voto; end if;
    if ov.bonus is not null then bonus := ov.bonus; end if;
  end if;
  bonus := coalesce(bonus, '{}'::jsonb); minutes := coalesce(minutes, 0);
  if voto is null then fantavoto := null; return; end if;
  select coalesce(settings->'bonus', '{}'::jsonb) into w from leagues where id = p_league;
  for k in select jsonb_object_keys(bonus) loop
    acc := acc + (bonus->>k)::numeric * coalesce((w->>k)::numeric,
      case k when 'gol' then 3 when 'assist' then 1 when 'rig_sbagliato' then -3 when 'rig_parato' then 3
             when 'gol_subito' then -1 when 'autogol' then -2 when 'amm' then -0.5 when 'esp' then -1 else 0 end);
  end loop;
  fantavoto := voto + acc;
end $$;

create or replace function public.compute_matchday(p_league uuid, p_matchday integer)
returns jsonb language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; s jsonb; max_subs integer; goal_base numeric; goal_step numeric;
  mod_def boolean; mod_mid boolean; mod_att boolean; home_b numeric; away_b numeric; clean_b numeric;
  m record; lu lineups%rowtype; has_lu boolean; base numeric; tot numeric; det jsonb; extras jsonb; pid integer; orig integer; subid integer; r text;
  v numeric; fv numeric; b jsonb; mins integer; subs integer; used integer[]; bp integer; bv numeric; bfv numeric; bb jsonb; bm integer;
  def_v numeric[]; att_v numeric[]; mid_v numeric[]; gk_v numeric; gk_clean boolean; avgd numeric; modv numeric; mid_avg numeric;
  teams integer := 0; fx record; hr results%rowtype; ar results%rowtype; h_tot numeric; a_tot numeric; h_ex jsonb; a_ex jsonb;
  diff numeric; mb numeric; hg integer; ag integer;
begin
  if not (is_admin(p_league) or coalesce(current_setting('request.jwt.claims', true)::jsonb->>'role', '') = 'service_role') then
    raise exception 'solo l''admin'; end if;
  select * into l from leagues where id = p_league; s := l.settings;
  max_subs := coalesce((s->>'max_subs')::int, 3); goal_base := coalesce((s->>'goal_base')::numeric, 66);
  goal_step := coalesce((s->>'goal_step')::numeric, 6);
  mod_def := coalesce((s->>'mod_difesa')::boolean, false); mod_mid := coalesce((s->>'mod_centrocampo')::boolean, false);
  mod_att := coalesce((s->>'mod_attacco')::boolean, false);
  home_b := coalesce((s->>'bonus_casa')::numeric, 0); away_b := coalesce((s->>'bonus_trasferta')::numeric, 0);
  clean_b := coalesce((s->'bonus'->>'porta_inviolata')::numeric, 0);
  for m in select user_id from league_members where league_id = p_league loop
    base := 0; tot := 0; det := '[]'::jsonb; extras := '[]'::jsonb; subs := 0; used := '{}'; def_v := '{}'; att_v := '{}'; mid_v := '{}';
    gk_v := null; gk_clean := false; mid_avg := null;
    select * into lu from lineups where league_id = p_league and user_id = m.user_id and matchday = p_matchday;
    has_lu := found;
    if has_lu then
      foreach orig in array lu.starters loop
        pid := orig; subid := null;
        select role into r from players where id = pid;
        select voto, fantavoto, bonus, minutes into v, fv, b, mins from fv_of(p_league, l.season, p_matchday, pid);
        if fv is null and subs < max_subs and lu.bench is not null then
          foreach bp in array lu.bench loop
            continue when bp = any(used) or (select role from players where id = bp) <> r;
            select voto, fantavoto, bonus, minutes into bv, bfv, bb, bm from fv_of(p_league, l.season, p_matchday, bp);
            if bfv is not null then
              used := used || bp; subs := subs + 1; subid := bp; pid := bp; v := bv; fv := bfv; b := bb; mins := bm; exit;
            end if;
          end loop;
        end if;
        det := det || jsonb_build_object('player_id', orig, 'sub', subid, 'voto', v, 'fv', coalesce(fv, 0), 'role', r,
                                         'bonus', coalesce(b, '{}'::jsonb), 'min', coalesce(mins, 0));
        base := base + coalesce(fv, 0);
        if v is not null then
          if r = 'P' then gk_v := v; gk_clean := (coalesce(mins, 0) >= 60 and coalesce((b->>'gol_subito')::int, 0) = 0);
          elsif r = 'D' then def_v := def_v || v; elsif r = 'C' then mid_v := mid_v || v; else att_v := att_v || v; end if;
        end if;
      end loop;
      tot := base;
      if clean_b <> 0 and gk_clean then
        tot := tot + clean_b; extras := extras || jsonb_build_object('k', 'porta_inviolata', 'label', 'Porta inviolata', 'v', clean_b); end if;
      if mod_def and gk_v is not null and coalesce(array_length(def_v, 1), 0) >= 4 then
        select avg(x) into avgd from (select x from unnest(def_v) x order by x desc limit 3) t;
        modv := mod_table((avgd * 3 + gk_v) / 4);
        if modv <> 0 then tot := tot + modv; extras := extras || jsonb_build_object('k', 'mod_difesa', 'label', 'Modificatore difesa', 'v', modv); end if;
      end if;
      if mod_att and coalesce(array_length(att_v, 1), 0) >= 2 then
        select avg(x) into avgd from unnest(att_v) x; modv := mod_table(avgd);
        if modv <> 0 then tot := tot + modv; extras := extras || jsonb_build_object('k', 'mod_attacco', 'label', 'Modificatore attacco', 'v', modv); end if;
      end if;
      if coalesce(array_length(mid_v, 1), 0) >= 3 then select avg(x) into mid_avg from unnest(mid_v) x; end if;
    end if;
    insert into results(league_id, user_id, matchday, total, goals, points, detail)
      values (p_league, m.user_id, p_matchday, tot, goals_of(tot, goal_base, goal_step), 0,
              jsonb_build_object('players', det, 'subs', subs, 'extras', extras, 'base', base, 'mid_avg', mid_avg, 'lineup', has_lu))
      on conflict (league_id, user_id, matchday) do update
        set total = excluded.total, goals = excluded.goals, points = 0, detail = excluded.detail;
    teams := teams + 1;
  end loop;
  for fx in select * from league_fixtures where league_id = p_league and matchday = p_matchday loop
    select * into hr from results where league_id = p_league and user_id = fx.home_id and matchday = p_matchday;
    h_tot := hr.total; h_ex := coalesce(hr.detail->'extras', '[]'::jsonb);
    if fx.away_id is null then
      update league_fixtures set home_goals = hr.goals, home_points = h_tot where league_id = p_league and round = fx.round and home_id = fx.home_id;
      continue;
    end if;
    select * into ar from results where league_id = p_league and user_id = fx.away_id and matchday = p_matchday;
    a_tot := ar.total; a_ex := coalesce(ar.detail->'extras', '[]'::jsonb);
    if mod_mid and (hr.detail->>'mid_avg') is not null and (ar.detail->>'mid_avg') is not null then
      diff := (hr.detail->>'mid_avg')::numeric - (ar.detail->>'mid_avg')::numeric;
      mb := case when abs(diff) >= 2 then 6 when abs(diff) >= 1.5 then 5 when abs(diff) >= 1 then 4
                 when abs(diff) >= 0.75 then 3 when abs(diff) >= 0.5 then 2 when abs(diff) >= 0.25 then 1 else 0 end;
      if mb > 0 and diff > 0 then h_tot := h_tot + mb; h_ex := h_ex || jsonb_build_object('k', 'mod_centrocampo', 'label', 'Modificatore centrocampo', 'v', mb);
      elsif mb > 0 then a_tot := a_tot + mb; a_ex := a_ex || jsonb_build_object('k', 'mod_centrocampo', 'label', 'Modificatore centrocampo', 'v', mb); end if;
    end if;
    if home_b <> 0 and (hr.detail->>'lineup')::boolean then h_tot := h_tot + home_b; h_ex := h_ex || jsonb_build_object('k', 'casa', 'label', 'Fattore casa', 'v', home_b); end if;
    if away_b <> 0 and (ar.detail->>'lineup')::boolean then a_tot := a_tot + away_b; a_ex := a_ex || jsonb_build_object('k', 'trasferta', 'label', 'Fattore trasferta', 'v', away_b); end if;
    hg := goals_of(h_tot, goal_base, goal_step); ag := goals_of(a_tot, goal_base, goal_step);
    update results set total = h_tot, goals = hg, points = case when hg > ag then 3 when hg = ag then 1 else 0 end,
      detail = detail || jsonb_build_object('extras', h_ex) where league_id = p_league and user_id = fx.home_id and matchday = p_matchday;
    update results set total = a_tot, goals = ag, points = case when ag > hg then 3 when hg = ag then 1 else 0 end,
      detail = detail || jsonb_build_object('extras', a_ex) where league_id = p_league and user_id = fx.away_id and matchday = p_matchday;
    update league_fixtures set home_goals = hg, away_goals = ag, home_points = h_tot, away_points = a_tot
      where league_id = p_league and round = fx.round and home_id = fx.home_id;
  end loop;
  return jsonb_build_object('teams', teams, 'matchday', p_matchday);
end $$;

grant execute on all functions in schema public to authenticated;

-- ==================== FIX 005 (panchina, identico a fix-005-panchina.sql) ====================
-- FantaTB fix 005: panchina limitata (settings.bench_size, default 7), panchina nel dettaglio risultati,
-- subtotali sempre presenti per i modificatori attivi anche quando valgono 0.

create or replace function public.save_lineup(p_league uuid, p_matchday integer, p_module text, p_starters integer[], p_bench integer[])
returns void language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; dl timestamptz; parts text[]; want jsonb; r text; n integer; bmax integer;
begin
  if not is_member(p_league) then raise exception 'non sei in questa lega'; end if;
  select * into l from leagues where id = p_league;
  select starts_at into dl from matchdays where season = l.season and number = p_matchday;
  if dl is not null and now() > dl then raise exception 'formazioni chiuse: la giornata % è iniziata', p_matchday; end if;
  if p_module !~ '^[3-5]-[2-5]-[1-4]$' then raise exception 'modulo non valido'; end if;
  parts := string_to_array(p_module, '-');
  if parts[1]::int + parts[2]::int + parts[3]::int <> 10 then raise exception 'modulo non valido'; end if;
  if coalesce(array_length(p_starters, 1), 0) <> 11 then raise exception 'servono 11 titolari'; end if;
  bmax := coalesce((l.settings->>'bench_size')::int, 7);
  if coalesce(array_length(p_bench, 1), 0) > bmax then raise exception 'panchina: massimo % giocatori', bmax; end if;
  if (select count(distinct x) from unnest(p_starters || p_bench) x) <> array_length(p_starters || p_bench, 1) then
    raise exception 'giocatore ripetuto tra titolari e panchina'; end if;
  if exists (select 1 from unnest(p_starters || p_bench) x where not exists
      (select 1 from rosters where league_id = p_league and user_id = auth.uid() and player_id = x)) then
    raise exception 'un giocatore non è nella tua rosa'; end if;
  want := jsonb_build_object('P', 1, 'D', parts[1]::int, 'C', parts[2]::int, 'A', parts[3]::int);
  for r in select unnest(array['P','D','C','A']) loop
    select count(*) into n from unnest(p_starters) x join players p on p.id = x where p.role = r;
    if n <> (want->>r)::int then raise exception 'modulo %: servono % %', p_module, want->>r, r; end if;
  end loop;
  insert into lineups(league_id, user_id, matchday, module, starters, bench, submitted_at)
    values (p_league, auth.uid(), p_matchday, p_module, p_starters, coalesce(p_bench, '{}'), now())
    on conflict (league_id, user_id, matchday) do update
      set module = excluded.module, starters = excluded.starters, bench = excluded.bench, submitted_at = now();
end $$;

create or replace function public.compute_matchday(p_league uuid, p_matchday integer)
returns jsonb language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; s jsonb; max_subs integer; goal_base numeric; goal_step numeric;
  mod_def boolean; mod_mid boolean; mod_att boolean; home_b numeric; away_b numeric; clean_b numeric;
  m record; lu lineups%rowtype; has_lu boolean; base numeric; tot numeric; det jsonb; bdet jsonb; extras jsonb; pid integer; orig integer; subid integer; r text;
  v numeric; fv numeric; b jsonb; mins integer; subs integer; used integer[]; bp integer; bv numeric; bfv numeric; bb jsonb; bm integer;
  def_v numeric[]; att_v numeric[]; mid_v numeric[]; gk_v numeric; gk_clean boolean; avgd numeric; modv numeric; mid_avg numeric;
  teams integer := 0; fx record; hr results%rowtype; ar results%rowtype; h_tot numeric; a_tot numeric; h_ex jsonb; a_ex jsonb;
  diff numeric; mb numeric; hg integer; ag integer; hm numeric; am numeric;
begin
  if not (is_admin(p_league) or coalesce(current_setting('request.jwt.claims', true)::jsonb->>'role', '') = 'service_role') then
    raise exception 'solo l''admin'; end if;
  select * into l from leagues where id = p_league; s := l.settings;
  max_subs := coalesce((s->>'max_subs')::int, 3); goal_base := coalesce((s->>'goal_base')::numeric, 66);
  goal_step := coalesce((s->>'goal_step')::numeric, 6);
  mod_def := coalesce((s->>'mod_difesa')::boolean, false); mod_mid := coalesce((s->>'mod_centrocampo')::boolean, false);
  mod_att := coalesce((s->>'mod_attacco')::boolean, false);
  home_b := coalesce((s->>'bonus_casa')::numeric, 0); away_b := coalesce((s->>'bonus_trasferta')::numeric, 0);
  clean_b := coalesce((s->'bonus'->>'porta_inviolata')::numeric, 0);
  for m in select user_id from league_members where league_id = p_league loop
    base := 0; tot := 0; det := '[]'::jsonb; bdet := '[]'::jsonb; extras := '[]'::jsonb; subs := 0; used := '{}';
    def_v := '{}'; att_v := '{}'; mid_v := '{}'; gk_v := null; gk_clean := false; mid_avg := null;
    select * into lu from lineups where league_id = p_league and user_id = m.user_id and matchday = p_matchday;
    has_lu := found;
    if has_lu then
      foreach orig in array lu.starters loop
        pid := orig; subid := null;
        select role into r from players where id = pid;
        select voto, fantavoto, bonus, minutes into v, fv, b, mins from fv_of(p_league, l.season, p_matchday, pid);
        if fv is null and subs < max_subs and lu.bench is not null then
          foreach bp in array lu.bench loop
            continue when bp = any(used) or (select role from players where id = bp) <> r;
            select voto, fantavoto, bonus, minutes into bv, bfv, bb, bm from fv_of(p_league, l.season, p_matchday, bp);
            if bfv is not null then
              used := used || bp; subs := subs + 1; subid := bp; pid := bp; v := bv; fv := bfv; b := bb; mins := bm; exit;
            end if;
          end loop;
        end if;
        det := det || jsonb_build_object('player_id', orig, 'sub', subid, 'voto', v, 'fv', coalesce(fv, 0), 'role', r,
                                         'bonus', coalesce(b, '{}'::jsonb), 'min', coalesce(mins, 0));
        base := base + coalesce(fv, 0);
        if v is not null then
          if r = 'P' then gk_v := v; gk_clean := (coalesce(mins, 0) >= 60 and coalesce((b->>'gol_subito')::int, 0) = 0);
          elsif r = 'D' then def_v := def_v || v; elsif r = 'C' then mid_v := mid_v || v; else att_v := att_v || v; end if;
        end if;
      end loop;
      if lu.bench is not null then
        foreach bp in array lu.bench loop
          select voto, fantavoto, bonus, minutes into bv, bfv, bb, bm from fv_of(p_league, l.season, p_matchday, bp);
          select role into r from players where id = bp;
          bdet := bdet || jsonb_build_object('player_id', bp, 'voto', bv, 'fv', bfv, 'role', r, 'bonus', coalesce(bb, '{}'::jsonb),
                                             'min', coalesce(bm, 0), 'used', bp = any(used));
        end loop;
      end if;
      tot := base;
      if clean_b <> 0 then
        modv := case when gk_clean then clean_b else 0 end; tot := tot + modv;
        extras := extras || jsonb_build_object('k', 'porta_inviolata', 'label', 'Porta inviolata', 'v', modv); end if;
      if mod_def then
        modv := 0;
        if gk_v is not null and coalesce(array_length(def_v, 1), 0) >= 4 then
          select avg(x) into avgd from (select x from unnest(def_v) x order by x desc limit 3) t;
          modv := mod_table((avgd * 3 + gk_v) / 4); end if;
        tot := tot + modv; extras := extras || jsonb_build_object('k', 'mod_difesa', 'label', 'Modificatore difesa', 'v', modv); end if;
      if mod_att then
        modv := 0;
        if coalesce(array_length(att_v, 1), 0) >= 2 then select avg(x) into avgd from unnest(att_v) x; modv := mod_table(avgd); end if;
        tot := tot + modv; extras := extras || jsonb_build_object('k', 'mod_attacco', 'label', 'Modificatore attacco', 'v', modv); end if;
      if coalesce(array_length(mid_v, 1), 0) >= 3 then select avg(x) into mid_avg from unnest(mid_v) x; end if;
    end if;
    insert into results(league_id, user_id, matchday, total, goals, points, detail)
      values (p_league, m.user_id, p_matchday, tot, goals_of(tot, goal_base, goal_step), 0,
              jsonb_build_object('players', det, 'bench', bdet, 'subs', subs, 'extras', extras, 'base', base, 'mid_avg', mid_avg, 'lineup', has_lu))
      on conflict (league_id, user_id, matchday) do update
        set total = excluded.total, goals = excluded.goals, points = 0, detail = excluded.detail;
    teams := teams + 1;
  end loop;
  for fx in select * from league_fixtures where league_id = p_league and matchday = p_matchday loop
    select * into hr from results where league_id = p_league and user_id = fx.home_id and matchday = p_matchday;
    h_tot := hr.total; h_ex := coalesce(hr.detail->'extras', '[]'::jsonb);
    if fx.away_id is null then
      update league_fixtures set home_goals = hr.goals, home_points = h_tot where league_id = p_league and round = fx.round and home_id = fx.home_id;
      continue;
    end if;
    select * into ar from results where league_id = p_league and user_id = fx.away_id and matchday = p_matchday;
    a_tot := ar.total; a_ex := coalesce(ar.detail->'extras', '[]'::jsonb);
    if mod_mid then
      hm := 0; am := 0;
      if (hr.detail->>'mid_avg') is not null and (ar.detail->>'mid_avg') is not null then
        diff := (hr.detail->>'mid_avg')::numeric - (ar.detail->>'mid_avg')::numeric;
        mb := case when abs(diff) >= 2 then 6 when abs(diff) >= 1.5 then 5 when abs(diff) >= 1 then 4
                   when abs(diff) >= 0.75 then 3 when abs(diff) >= 0.5 then 2 when abs(diff) >= 0.25 then 1 else 0 end;
        if diff > 0 then hm := mb; elsif diff < 0 then am := mb; end if;
      end if;
      h_tot := h_tot + hm; a_tot := a_tot + am;
      h_ex := h_ex || jsonb_build_object('k', 'mod_centrocampo', 'label', 'Modificatore centrocampo', 'v', hm);
      a_ex := a_ex || jsonb_build_object('k', 'mod_centrocampo', 'label', 'Modificatore centrocampo', 'v', am);
    end if;
    if home_b <> 0 and (hr.detail->>'lineup')::boolean then h_tot := h_tot + home_b; h_ex := h_ex || jsonb_build_object('k', 'casa', 'label', 'Fattore casa', 'v', home_b); end if;
    if away_b <> 0 and (ar.detail->>'lineup')::boolean then a_tot := a_tot + away_b; a_ex := a_ex || jsonb_build_object('k', 'trasferta', 'label', 'Fattore trasferta', 'v', away_b); end if;
    hg := goals_of(h_tot, goal_base, goal_step); ag := goals_of(a_tot, goal_base, goal_step);
    update results set total = h_tot, goals = hg, points = case when hg > ag then 3 when hg = ag then 1 else 0 end,
      detail = detail || jsonb_build_object('extras', h_ex) where league_id = p_league and user_id = fx.home_id and matchday = p_matchday;
    update results set total = a_tot, goals = ag, points = case when ag > hg then 3 when hg = ag then 1 else 0 end,
      detail = detail || jsonb_build_object('extras', a_ex) where league_id = p_league and user_id = fx.away_id and matchday = p_matchday;
    update league_fixtures set home_goals = hg, away_goals = ag, home_points = h_tot, away_points = a_tot
      where league_id = p_league and round = fx.round and home_id = fx.home_id;
  end loop;
  return jsonb_build_object('teams', teams, 'matchday', p_matchday);
end $$;

grant execute on all functions in schema public to authenticated;

-- ==================== FIX 007 (titolarità, identico a fix-007-titolari.sql) ====================
-- FantaTB fix 007: indice di titolarità per giornata + infortuni con data di rientro (scripts/fanta_titolari.py).
create table if not exists public.player_status (
  season integer not null default 2026,
  matchday integer not null,
  player_id integer not null references public.players(id),
  prob integer not null default 50,          -- 0..100
  reason text,
  injury text,                               -- null se disponibile; altrimenti "infortunio: ginocchio" / "squalifica"
  back_at date,                              -- rientro stimato (se noto)
  updated_at timestamptz not null default now(),
  primary key (season, matchday, player_id)
);
alter table public.player_status enable row level security;
drop policy if exists status_read on public.player_status;
create policy status_read on public.player_status for select to anon, authenticated using (true);
grant select on public.player_status to anon, authenticated;

-- ==================== FIX 008 (identico a fix-008-rose-liste.sql) ====================
-- FantaTB fix 008: (1) import rose da Excel con squadre "in attesa" reclamabili da chi entra col codice invito;
-- (2) liste obiettivi con tier 1-5, condivisibili per codice, con liste "consigliate" (featured).
-- Da incollare nell'SQL Editor di Supabase in un editor VUOTO. Idempotente. Vedi kb/FANTATB.md §15.

-- ==================== 1) ROSE IMPORTATE E SQUADRE IN ATTESA ====================
create table if not exists public.league_pending (
  league_id uuid not null references public.leagues(id) on delete cascade,
  team_name text not null,
  roster jsonb not null default '[]'::jsonb,        -- [{"player_id":123,"price":10}, ...]
  created_at timestamptz not null default now(),
  primary key (league_id, team_name)
);
alter table public.league_pending enable row level security;
drop policy if exists pending_read on public.league_pending;
create policy pending_read on public.league_pending for select to authenticated using (public.is_member(league_id));
grant select on public.league_pending to authenticated;

-- Admin: importa la rosa di una squadra. Se esiste gia' un membro con quel nome squadra (confronto senza maiuscole/spazi)
-- gli assegna i giocatori con i prezzi (p_replace = true svuota prima la rosa e rimborsa); altrimenti crea/aggiorna una
-- squadra in attesa, che verra' reclamata da chi entra con il codice invito. I giocatori gia' in un'altra rosa vengono saltati.
create or replace function public.import_roster(p_league uuid, p_team text, p_roster jsonb, p_replace boolean default true)
returns jsonb language plpgsql security definer set search_path = public as $$
declare m league_members%rowtype; it jsonb; pid int; pr int; n int := 0; skipped int := 0; refund int := 0;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin'; end if;
  select * into m from league_members where league_id = p_league and lower(trim(team_name)) = lower(trim(p_team));
  if not found then
    insert into league_pending(league_id, team_name, roster) values (p_league, trim(p_team), coalesce(p_roster, '[]'::jsonb))
      on conflict (league_id, team_name) do update set roster = excluded.roster, created_at = now();
    return jsonb_build_object('pending', true, 'team', trim(p_team), 'players', jsonb_array_length(coalesce(p_roster, '[]'::jsonb)));
  end if;
  if p_replace then
    select coalesce(sum(price), 0) into refund from rosters where league_id = p_league and user_id = m.user_id;
    delete from rosters where league_id = p_league and user_id = m.user_id;
    update league_members set credits = credits + refund where league_id = p_league and user_id = m.user_id;
  end if;
  for it in select * from jsonb_array_elements(coalesce(p_roster, '[]'::jsonb)) loop
    pid := (it->>'player_id')::int; pr := greatest(coalesce((it->>'price')::int, 0), 0);
    if pid is null or not exists (select 1 from players where id = pid) then skipped := skipped + 1; continue; end if;
    if exists (select 1 from rosters where league_id = p_league and player_id = pid) then skipped := skipped + 1; continue; end if;
    insert into rosters(league_id, player_id, user_id, price) values (p_league, pid, m.user_id, pr);
    update league_members set credits = credits - pr where league_id = p_league and user_id = m.user_id;
    n := n + 1;
  end loop;
  return jsonb_build_object('pending', false, 'team', m.team_name, 'players', n, 'skipped', skipped);
end $$;

-- Chi sta entrando (non e' ancora membro) vede le squadre in attesa della lega di quel codice invito.
create or replace function public.pending_teams(p_code text)
returns table(team_name text, players integer) language sql security definer stable set search_path = public as $$
  select p.team_name, jsonb_array_length(p.roster)::int
  from league_pending p join leagues l on l.id = p.league_id
  where l.invite_code = upper(trim(p_code)) order by p.team_name;
$$;

-- Entra nella lega reclamando una squadra in attesa: nome, rosa e prezzi passano al nuovo membro, i crediti si scalano.
create or replace function public.join_league_claim(p_code text, p_team text)
returns uuid language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; p league_pending%rowtype; n int; it jsonb; pid int; pr int; spent int := 0;
begin
  if auth.uid() is null then raise exception 'non autenticato'; end if;
  select * into l from leagues where invite_code = upper(trim(p_code));
  if not found then raise exception 'codice invito non valido'; end if;
  select * into p from league_pending where league_id = l.id and lower(trim(team_name)) = lower(trim(p_team));
  if not found then raise exception 'squadra non disponibile'; end if;
  if exists (select 1 from league_members where league_id = l.id and user_id = auth.uid()) then raise exception 'sei gia'' in questa lega'; end if;
  select count(*) into n from league_members where league_id = l.id;
  if n >= coalesce((l.settings->>'max_teams')::int, 20) then raise exception 'lega al completo'; end if;
  insert into league_members(league_id, user_id, team_name, role, credits, call_order)
    values (l.id, auth.uid(), p.team_name, 'member', coalesce((l.settings->>'credits')::int, 500), n + 1);
  for it in select * from jsonb_array_elements(p.roster) loop
    pid := (it->>'player_id')::int; pr := greatest(coalesce((it->>'price')::int, 0), 0);
    if pid is null or exists (select 1 from rosters where league_id = l.id and player_id = pid) then continue; end if;
    insert into rosters(league_id, player_id, user_id, price) values (l.id, pid, auth.uid(), pr);
    spent := spent + pr;
  end loop;
  update league_members set credits = credits - spent where league_id = l.id and user_id = auth.uid();
  delete from league_pending where league_id = l.id and team_name = p.team_name;
  return l.id;
end $$;

create or replace function public.delete_pending(p_league uuid, p_team text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not is_admin(p_league) then raise exception 'solo l''admin'; end if;
  delete from league_pending where league_id = p_league and team_name = p_team;
end $$;

-- ==================== 2) LISTE OBIETTIVI CON TIER ====================
create table if not exists public.lists (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  description text not null default '',
  author text not null default '',                  -- nome pubblico mostrato sulle liste condivise
  is_public boolean not null default false,
  featured boolean not null default false,          -- liste consigliate (influencer, redazione): si imposta a mano da SQL
  share_code text not null unique default upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists public.list_items (
  list_id uuid not null references public.lists(id) on delete cascade,
  player_id integer not null references public.players(id),
  tier smallint not null default 3 check (tier between 1 and 5),
  note text not null default '',
  primary key (list_id, player_id)
);
alter table public.lists enable row level security;
alter table public.list_items enable row level security;
drop policy if exists lists_own on public.lists;
drop policy if exists lists_public on public.lists;
drop policy if exists items_own on public.list_items;
drop policy if exists items_public on public.list_items;
create policy lists_own on public.lists for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy lists_public on public.lists for select to anon, authenticated using (is_public or featured);
create policy items_own on public.list_items for all to authenticated
  using (exists (select 1 from public.lists l where l.id = list_id and l.owner_id = auth.uid()))
  with check (exists (select 1 from public.lists l where l.id = list_id and l.owner_id = auth.uid()));
create policy items_public on public.list_items for select to anon, authenticated
  using (exists (select 1 from public.lists l where l.id = list_id and (l.is_public or l.featured)));
grant select on public.lists, public.list_items to anon, authenticated;
grant insert, update, delete on public.lists, public.list_items to authenticated;

-- Copia una lista condivisa (o consigliata) fra le proprie.
create or replace function public.copy_list(p_code text, p_name text default null)
returns uuid language plpgsql security definer set search_path = public as $$
declare src lists%rowtype; nid uuid;
begin
  if auth.uid() is null then raise exception 'non autenticato'; end if;
  select * into src from lists where share_code = upper(trim(p_code)) and (is_public or featured or owner_id = auth.uid());
  if not found then raise exception 'lista non trovata'; end if;
  insert into lists(owner_id, name, description, author) values (auth.uid(), coalesce(nullif(trim(p_name), ''), src.name || ' (copia)'), src.description, '') returning id into nid;
  insert into list_items(list_id, player_id, tier, note) select nid, player_id, tier, note from list_items where list_id = src.id;
  return nid;
end $$;

grant execute on all functions in schema public to authenticated;
grant execute on function public.copy_list(text, text) to authenticated;

-- ==================== FIX 009 (identico a fix-009-chat-strategie.sql) ====================
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
