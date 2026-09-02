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
