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
