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
