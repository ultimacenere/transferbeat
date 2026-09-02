-- Fix 003: variabile 'goals' ambigua con la colonna results.goals -> rinominata n_goals.
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

