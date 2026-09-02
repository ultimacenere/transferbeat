-- Fix 001: codice invito senza pgcrypto (su Supabase l'estensione vive nello schema "extensions").
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
