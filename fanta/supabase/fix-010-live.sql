-- FantaTB fix 010: risultati LIVE. compute_matchday distingue "partita non ancora giocata" (nessuna riga in player_ratings:
-- il titolare resta in attesa, fantavoto 0 provvisorio, nessuna sostituzione) da "ha giocato senza voto" (riga con voto null:
-- sostituito dalla panchina). A giornata 'rated' il comportamento è quello di prima. detail.players[].pending e detail.live
-- permettono al frontend di mostrare "in attesa" e "risultato provvisorio". Il cron (fanta_voti.py) ricalcola le leghe anche
-- a giornata 'live', ogni 30 minuti nei giorni di partita (fanta.yml task=live).
create or replace function public.compute_matchday(p_league uuid, p_matchday integer)
returns jsonb language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; s jsonb; max_subs integer; goal_base numeric; goal_step numeric;
  mod_def boolean; mod_mid boolean; mod_att boolean; home_b numeric; away_b numeric; clean_b numeric;
  m record; lu lineups%rowtype; has_lu boolean; base numeric; tot numeric; det jsonb; bdet jsonb; extras jsonb; pid integer; orig integer; subid integer; r text;
  v numeric; fv numeric; b jsonb; mins integer; subs integer; used integer[]; bp integer; bv numeric; bfv numeric; bb jsonb; bm integer;
  def_v numeric[]; att_v numeric[]; mid_v numeric[]; gk_v numeric; gk_clean boolean; avgd numeric; modv numeric; mid_avg numeric;
  teams integer := 0; fx record; hr results%rowtype; ar results%rowtype; h_tot numeric; a_tot numeric; h_ex jsonb; a_ex jsonb;
  diff numeric; mb numeric; hg integer; ag integer; hm numeric; am numeric; md_status text; played boolean;
begin
  if not (is_admin(p_league) or coalesce(current_setting('request.jwt.claims', true)::jsonb->>'role', '') = 'service_role') then
    raise exception 'solo l''admin'; end if;
  select * into l from leagues where id = p_league; s := l.settings;
  select status into md_status from matchdays where season = l.season and number = p_matchday;
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
        -- live: chi non ha ancora una riga di voto (partita non finita) resta "in attesa" e non viene sostituito;
        -- a giornata rated (tutte le partite finite) chi manca del tutto (non convocato) viene sostituito come prima
        select exists(select 1 from player_ratings where season = l.season and matchday = p_matchday and player_id = pid) into played;
        if fv is null and (md_status = 'rated' or played) and subs < max_subs and lu.bench is not null then
          foreach bp in array lu.bench loop
            continue when bp = any(used) or (select role from players where id = bp) <> r;
            select voto, fantavoto, bonus, minutes into bv, bfv, bb, bm from fv_of(p_league, l.season, p_matchday, bp);
            if bfv is not null then
              used := used || bp; subs := subs + 1; subid := bp; pid := bp; v := bv; fv := bfv; b := bb; mins := bm; exit;
            end if;
          end loop;
        end if;
        det := det || jsonb_build_object('player_id', orig, 'sub', subid, 'voto', v, 'fv', coalesce(fv, 0), 'role', r,
                                         'bonus', coalesce(b, '{}'::jsonb), 'min', coalesce(mins, 0),
                                         'pending', (md_status is distinct from 'rated' and not played and subid is null));
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
              jsonb_build_object('players', det, 'bench', bdet, 'subs', subs, 'extras', extras, 'base', base, 'mid_avg', mid_avg, 'lineup', has_lu,
                                 'live', (md_status is distinct from 'rated')))
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
