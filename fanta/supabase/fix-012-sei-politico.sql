-- FantaTB fix 012: "6 politico" nelle giornate live (richiesta dell'utente, 2026-09-06). Sostituisce compute_matchday del fix 011.
-- A giornata non 'rated', chi non ha ancora una riga in player_ratings (partita non finita) riceve voto 6 e fantavoto 6 senza
-- bonus, marcato pending=true: il totale provvisorio e il modificatore difesa simulano il risultato come se prendesse 6.
-- A giornata 'rated' tutto come prima (chi manca del tutto viene sostituito dalla panchina). Include i fix 010 e 011.
create or replace function public.compute_matchday(p_league uuid, p_matchday integer)
returns jsonb language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; s jsonb; max_subs integer; goal_base numeric; goal_step numeric;
  mod_def boolean; mod_mid boolean; mod_att boolean; home_b numeric; away_b numeric; clean_b numeric;
  m record; lu lineups%rowtype; has_lu boolean; base numeric; tot numeric; det jsonb; bdet jsonb; extras jsonb; pid integer; orig integer; subid integer; r text;
  v numeric; fv numeric; b jsonb; mins integer; subs integer; used integer[]; bp integer; bv numeric; bfv numeric; bb jsonb; bm integer;
  def_v numeric[]; att_v numeric[]; mid_v numeric[]; gk_v numeric; gk_clean boolean; avgd numeric; modv numeric; mid_avg numeric;
  teams integer := 0; fx record; hr results%rowtype; ar results%rowtype; h_tot numeric; a_tot numeric; h_ex jsonb; a_ex jsonb;
  diff numeric; mb numeric; hg integer; ag integer; hm numeric; am numeric; md_status text; played boolean; pend boolean;
  def_tab jsonb; def_gk boolean; def_app text; mdv numeric;
begin
  if not (is_admin(p_league) or coalesce(current_setting('request.jwt.claims', true)::jsonb->>'role', '') = 'service_role') then
    raise exception 'solo l''admin'; end if;
  select * into l from leagues where id = p_league; s := l.settings;
  select status into md_status from matchdays where season = l.season and number = p_matchday;
  max_subs := coalesce((s->>'max_subs')::int, 3); goal_base := coalesce((s->>'goal_base')::numeric, 66);
  goal_step := coalesce((s->>'goal_step')::numeric, 6);
  mod_def := coalesce((s->>'mod_difesa')::boolean, false); mod_mid := coalesce((s->>'mod_centrocampo')::boolean, false);
  mod_att := coalesce((s->>'mod_attacco')::boolean, false);
  def_tab := coalesce(s->'mod_difesa_tab', '[{"min":6,"v":0.5},{"min":6.25,"v":1},{"min":6.5,"v":2},{"min":6.75,"v":3},{"min":7,"v":4.5},{"min":7.25,"v":6},{"min":7.5,"v":7.5}]'::jsonb);
  def_gk := coalesce((s->>'mod_difesa_portiere')::boolean, true);
  def_app := coalesce(s->>'mod_difesa_applica', 'propria');
  home_b := coalesce((s->>'bonus_casa')::numeric, 0); away_b := coalesce((s->>'bonus_trasferta')::numeric, 0);
  clean_b := coalesce((s->'bonus'->>'porta_inviolata')::numeric, 0);
  for m in select user_id from league_members where league_id = p_league loop
    base := 0; tot := 0; det := '[]'::jsonb; bdet := '[]'::jsonb; extras := '[]'::jsonb; subs := 0; used := '{}'; mdv := 0;
    def_v := '{}'; att_v := '{}'; mid_v := '{}'; gk_v := null; gk_clean := false; mid_avg := null;
    select * into lu from lineups where league_id = p_league and user_id = m.user_id and matchday = p_matchday;
    has_lu := found;
    if has_lu then
      foreach orig in array lu.starters loop
        pid := orig; subid := null; pend := false;
        select role into r from players where id = pid;
        select voto, fantavoto, bonus, minutes into v, fv, b, mins from fv_of(p_league, l.season, p_matchday, pid);
        select exists(select 1 from player_ratings where season = l.season and matchday = p_matchday and player_id = pid) into played;
        if fv is null and not played and md_status is distinct from 'rated' then
          -- live (fix 012): partita non ancora giocata -> 6 politico, nessuna sostituzione
          pend := true; v := 6; fv := 6; b := '{}'::jsonb; mins := 0;
        elsif fv is null and subs < max_subs and lu.bench is not null then
          -- ha giocato senza voto (o giornata rated e non convocato): sostituzione dalla panchina
          foreach bp in array lu.bench loop
            continue when bp = any(used) or (select role from players where id = bp) <> r;
            select voto, fantavoto, bonus, minutes into bv, bfv, bb, bm from fv_of(p_league, l.season, p_matchday, bp);
            if bfv is not null then
              used := used || bp; subs := subs + 1; subid := bp; pid := bp; v := bv; fv := bfv; b := bb; mins := bm; exit;
            end if;
          end loop;
        end if;
        det := det || jsonb_build_object('player_id', orig, 'sub', subid, 'voto', v, 'fv', coalesce(fv, 0), 'role', r,
                                         'bonus', coalesce(b, '{}'::jsonb), 'min', coalesce(mins, 0), 'pending', pend);
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
        if coalesce(array_length(def_v, 1), 0) >= 4 and (gk_v is not null or not def_gk) then
          if def_gk then
            select avg(x) into avgd from (select x from unnest(def_v) x order by x desc limit 3) t;
            modv := mod_lookup((avgd * 3 + gk_v) / 4, def_tab);
          else
            select avg(x) into avgd from (select x from unnest(def_v) x order by x desc limit 4) t;
            modv := mod_lookup(avgd, def_tab);
          end if;
        end if;
        mdv := modv;
        if def_app = 'avversaria' then
          extras := extras || jsonb_build_object('k', 'mod_difesa', 'label', 'Modificatore difesa (all''avversario)', 'v', modv, 'own', false);
        else
          tot := tot + modv; extras := extras || jsonb_build_object('k', 'mod_difesa', 'label', 'Modificatore difesa', 'v', modv);
        end if;
      end if;
      if mod_att then
        modv := 0;
        if coalesce(array_length(att_v, 1), 0) >= 2 then select avg(x) into avgd from unnest(att_v) x; modv := mod_table(avgd); end if;
        tot := tot + modv; extras := extras || jsonb_build_object('k', 'mod_attacco', 'label', 'Modificatore attacco', 'v', modv); end if;
      if coalesce(array_length(mid_v, 1), 0) >= 3 then select avg(x) into mid_avg from unnest(mid_v) x; end if;
    end if;
    insert into results(league_id, user_id, matchday, total, goals, points, detail)
      values (p_league, m.user_id, p_matchday, tot, goals_of(tot, goal_base, goal_step), 0,
              jsonb_build_object('players', det, 'bench', bdet, 'subs', subs, 'extras', extras, 'base', base, 'mid_avg', mid_avg, 'lineup', has_lu,
                                 'live', (md_status is distinct from 'rated'), 'mod_def_v', mdv))
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
    if mod_def and def_app = 'avversaria' then
      hm := coalesce((ar.detail->>'mod_def_v')::numeric, 0); am := coalesce((hr.detail->>'mod_def_v')::numeric, 0);
      h_tot := h_tot - hm; a_tot := a_tot - am;
      h_ex := h_ex || jsonb_build_object('k', 'malus_difesa', 'label', 'Malus difesa avversaria', 'v', -hm);
      a_ex := a_ex || jsonb_build_object('k', 'malus_difesa', 'label', 'Malus difesa avversaria', 'v', -am);
    end if;
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
