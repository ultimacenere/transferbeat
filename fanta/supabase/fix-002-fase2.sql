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
  avgd numeric; modv numeric; goals integer; teams integer := 0; fx record; hg integer; ag integer; h_tot numeric; a_tot numeric;
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
    goals := case when tot >= goal_base then 1 + floor((tot - goal_base) / goal_step)::int else 0 end;
    insert into results(league_id, user_id, matchday, total, goals, points, detail)
      values (p_league, m.user_id, p_matchday, tot, goals, 0,
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
