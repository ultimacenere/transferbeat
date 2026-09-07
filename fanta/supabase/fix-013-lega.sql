-- FantaTB fix 013: quattro funzioni di lega (punti 3, 7, 8 e 9 del blocco C della lista di lavoro).
--   1) CORREZIONE VOTI: RPC per leggere/scrivere/cancellare le righe di rating_overrides dall'interfaccia admin.
--   2) FORMAZIONI NASCOSTE fino alla deadline: opzione di lega, applicata lato server (RLS + trigger), spenta di default.
--   3) CLASSIFICA PUBBLICA condivisibile con un codice non indovinabile, scelta dell'admin, spenta di default.
--   4) SCAMBI fra squadre e SVINCOLI con rimborso parziale, in una sola transazione.
--
-- PRESUPPONE: schema.sql e i fix 001-012 GIA' ESEGUITI. In particolare il 012, che contiene la versione buona di
-- compute_matchday (6 politico + fix 010 e 011).
-- NON RISCRIVE compute_matchday: non serve. Le correzioni dei voti entrano nel calcolo perche' fv_of (fix 004) legge
-- gia' rating_overrides; le formazioni nascoste si fermano al livello RLS, e compute_matchday e' security definer di
-- proprieta' del ruolo che possiede le tabelle, quindi continua a leggere TUTTE le formazioni come oggi; scambi e
-- svincoli toccano solo rosters/crediti/formazioni future. Se un giorno compute_matchday andra' rifatto, si parte dal 012.
--
-- Da incollare nell'SQL Editor di Supabase in un editor VUOTO. IDEMPOTENTE: si puo' rilanciare senza errori.
-- Il comportamento del sito NON cambia finche' l'admin non accende le nuove opzioni: tutti i default sono "come prima".
--
-- COME VERIFICARE che sia andato a buon fine (query da lanciare dopo, nello stesso editor):
--   a) funzioni nuove (attese 14 righe):
--      select proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
--       where n.nspname = 'public' and proname in ('league_overrides','set_rating_override','delete_rating_override',
--             'lineups_visible','lineups_status','set_standings_share','public_standings','matchday_running',
--             'clean_bonus','trade_apply','propose_trade','respond_trade','admin_trade','cancel_trade')
--       order by 1;
--      (piu' release_own_player: 15 con quella; e' elencata a parte perche' affianca la release_player esistente)
--   b) tabelle nuove: select tablename from pg_tables where schemaname='public' and tablename in ('trades','releases','league_shares');
--   c) RLS accesa su tutte e tre: select relname, relrowsecurity from pg_class where relname in ('trades','releases','league_shares');
--   d) policy delle formazioni riscritta: select qual from pg_policies where tablename='lineups' and policyname='lineups_read';
--      (deve contenere lineups_visible)
--   e) niente cambia a occhio nell'app: aprire una lega, scheda Schiera e Risultati devono funzionare come prima.


-- ############################################################################
-- ## 1) TABELLE
-- ############################################################################

-- 1.1 Correzione voti: rating_overrides esiste dallo schema base (league_id, matchday, player_id, voto, bonus).
-- Aggiungo solo il MOTIVO della correzione (l'admin deve poter spiegare ai partecipanti perche' ha toccato un voto)
-- e la tracciabilita' di chi/quando: senza queste due colonne una correzione e' indistinguibile da un errore.
-- Non aggiungo una colonna "malus": nel modello FantaTB il malus e' gia' dentro bonus (chiavi amm/esp/gol_subito/
-- autogol/rig_sbagliato con peso negativo in leagues.settings.bonus). Una seconda colonna avrebbe due sorgenti di
-- verita' per lo stesso numero e fv_of ne leggerebbe una sola.
alter table public.rating_overrides add column if not exists note text not null default '';
alter table public.rating_overrides add column if not exists created_by uuid references auth.users(id);
alter table public.rating_overrides add column if not exists updated_at timestamptz not null default now();

-- 1.2 Classifica pubblica: tabella separata dalle leghe, non un flag dentro leagues.
-- Perche' separata: leagues, league_members e league_fixtures contengono id utente e vanno lasciate leggibili ai soli
-- membri. Qui dentro non c'e' nulla di personale, cosi' la superficie condivisa e' una tabella sola e piccola.
-- A differenza delle liste del fix 008 NON apro questa tabella ad anon: il visitatore senza login non legge nessuna
-- tabella, chiama una sola funzione (public_standings) che restituisce esclusivamente nome squadra, punti e fantapunti.
-- Codice di 12 caratteri e non 8 come invite_code/share_code: qui il codice e' l'UNICA serratura (non c'e' il login
-- dietro), quindi lo spazio da tentare deve essere piu' grande.
create table if not exists public.league_shares (
  league_id uuid primary key references public.leagues(id) on delete cascade,
  share_code text not null unique default upper(substr(md5(random()::text || clock_timestamp()::text), 1, 12)),
  enabled boolean not null default false,           -- spento di default: la condivisione e' una scelta esplicita dell'admin
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 1.3 Scambi fra squadre. Una riga per proposta, con la storia degli stati: serve per mostrare in app
-- "proposte ricevute / inviate / concluse" e per capire dopo mesi perche' un giocatore ha cambiato rosa.
-- give = giocatori che il proponente CEDE, get = giocatori che RICEVE, cash = crediti che il proponente
-- AGGIUNGE all'offerta (negativo = crediti che chiede in cambio).
create table if not exists public.trades (
  id uuid primary key default gen_random_uuid(),
  league_id uuid not null references public.leagues(id) on delete cascade,
  from_user uuid not null references auth.users(id) on delete cascade,
  to_user uuid not null references auth.users(id) on delete cascade,
  give_players integer[] not null default '{}',
  get_players integer[] not null default '{}',
  cash integer not null default 0,
  note text not null default '',
  status text not null default 'proposta'
    check (status in ('proposta','attesa_admin','in_esecuzione','conclusa','rifiutata','respinta','annullata')),
  decided_by uuid references auth.users(id),        -- chi ha chiuso la proposta (l'altra squadra o l'admin)
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  executed_at timestamptz
);
create index if not exists trades_league_idx on public.trades(league_id, status, created_at desc);

-- 1.4 Svincoli con rimborso parziale. Registro a parte perche' non e' uno scambio: serve per lo storico
-- ("chi ha svincolato chi e quanto ha recuperato") e per non perdere il prezzo pagato all'asta una volta
-- che la riga in rosters e' sparita.
create table if not exists public.releases (
  id uuid primary key default gen_random_uuid(),
  league_id uuid not null references public.leagues(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  player_id integer not null references public.players(id),
  price integer not null default 0,                 -- quanto era stato pagato
  refund integer not null default 0,                -- quanto e' tornato in cassa
  created_at timestamptz not null default now()
);
create index if not exists releases_league_idx on public.releases(league_id, created_at desc);


-- ############################################################################
-- ## 2) RLS E POLICY
-- ############################################################################

alter table public.league_shares enable row level security;
alter table public.trades enable row level security;
alter table public.releases enable row level security;

-- league_shares: la leggono i membri della lega (all'admin serve per mostrare il link, agli altri per sapere che la
-- classifica e' pubblica). Nessuna policy per anon: il pubblico passa solo dalla funzione public_standings.
drop policy if exists shares_read on public.league_shares;
create policy shares_read on public.league_shares for select to authenticated using (public.is_member(league_id));

-- trades e releases: lettura a tutti i membri della lega (nel fantacalcio il mercato e' pubblico dentro la lega, e i
-- membri vedono gia' rose e crediti). Nessuna policy di scrittura: si scrive SOLO dalle RPC security definer,
-- cosi' i vincoli (crediti, slot, fase, giornata) non sono aggirabili dal client.
drop policy if exists trades_read on public.trades;
create policy trades_read on public.trades for select to authenticated using (public.is_member(league_id));
drop policy if exists releases_read on public.releases;
create policy releases_read on public.releases for select to authenticated using (public.is_member(league_id));

grant select on public.league_shares, public.trades, public.releases to authenticated;


-- ############################################################################
-- ## 3) FUNZIONI DI SUPPORTO
-- ############################################################################

-- 3.1 Una giornata e' "in corso" se l'ultima giornata gia' iniziata non e' ancora chiusa ('rated').
-- Guardo solo l'ULTIMA iniziata e non "esiste una giornata non rated": una vecchia giornata rimasta senza status
-- (import a mano, script non arrivato in fondo) bloccherebbe il mercato per sempre.
create or replace function public.matchday_running(l uuid) returns boolean
language sql security definer stable set search_path = public as $$
  select coalesce((
    select m.status is distinct from 'rated'
      from matchdays m, leagues lg
     where lg.id = l and m.season = lg.season and m.starts_at is not null and m.starts_at <= now()
     order by m.number desc limit 1), false);
$$;

-- 3.2 Le formazioni altrui sono visibili? Sì sempre, TRANNE quando la lega ha acceso settings.formazioni_nascoste:
-- in quel caso solo dopo matchdays.starts_at. Se la giornata non ha una deadline (starts_at null) resta nascosta:
-- senza deadline le formazioni si possono ancora cambiare (vedi save_lineup del fix 005), quindi mostrarle sarebbe
-- esattamente il danno che l'opzione vuole evitare.
create or replace function public.lineups_visible(l uuid, md integer) returns boolean
language sql security definer stable set search_path = public as $$
  select case
    when not coalesce((select (lg.settings->>'formazioni_nascoste')::boolean from leagues lg where lg.id = l), false)
      then true
    else coalesce((
      select m.starts_at <= now() from matchdays m, leagues lg
       where lg.id = l and m.season = lg.season and m.number = md), false)
  end;
$$;

-- 3.3 Ripulisce il jsonb dei bonus/malus di un override: accetta solo le chiavi che fv_of sa pesare e solo conteggi
-- interi >= 0 (il segno sta nei pesi di lega, non qui). Serve a non far entrare spazzatura dal form dell'admin,
-- che poi finirebbe muta nel calcolo.
create or replace function public.clean_bonus(b jsonb) returns jsonb
language plpgsql immutable as $$
declare k text; v numeric; out_b jsonb := '{}'::jsonb;
  ok text[] := array['gol','assist','rig_sbagliato','rig_parato','gol_subito','autogol','amm','esp'];
begin
  if b is null or jsonb_typeof(b) <> 'object' then return '{}'::jsonb; end if;
  for k in select jsonb_object_keys(b) loop
    if not (k = any(ok)) then raise exception 'bonus/malus: chiave "%" non prevista (ammesse: %)', k, array_to_string(ok, ', '); end if;
    if jsonb_typeof(b->k) <> 'number' then raise exception 'bonus/malus: "%" deve essere un numero', k; end if;
    v := (b->>k)::numeric;
    if v < 0 or v <> floor(v) then raise exception 'bonus/malus: "%" deve essere un intero >= 0 (il segno lo mette il peso di lega)', k; end if;
    if v > 0 then out_b := out_b || jsonb_build_object(k, v::int); end if;   -- gli zeri non si salvano: sono il "niente"
  end loop;
  return out_b;
end $$;


-- ############################################################################
-- ## 4) CORREZIONE VOTI DALL'INTERFACCIA ADMIN (punto 3 del blocco C)
-- ############################################################################
-- Come entra nel calcolo: fv_of (fix 004) legge rating_overrides PRIMA di calcolare il fantavoto, quindi la
-- correzione vale per tutti i calcoli SUCCESSIVI. Le giornate gia' calcolate NON si aggiornano da sole: dopo un
-- override va rilanciato compute_matchday(lega, giornata) — dall'app e' il pulsante "Ricalcola" della scheda
-- Calendario. Per non dimenticarselo, set_rating_override e delete_rating_override hanno p_recompute (default false):
-- se true ricalcolano subito quella giornata e restituiscono l'esito del calcolo.

-- Elenco degli override di una giornata, affiancati al voto ufficiale: la UI deve poter mostrare "6.0 -> 6.5".
-- Lettura ai membri (la policy overrides_read gia' li autorizza): le correzioni devono essere verificabili da tutti,
-- non solo da chi le fa.
create or replace function public.league_overrides(p_league uuid, p_matchday integer)
returns table(player_id integer, name text, team text, role text,
              voto numeric, bonus jsonb, note text, updated_at timestamptz,
              base_voto numeric, base_bonus jsonb, base_minutes integer)
language sql security definer stable set search_path = public as $$
  -- voto/bonus escono cosi' come sono, null compreso: null vuol dire "questo campo non e' stato corretto",
  -- ed e' l'informazione che il form deve rimettere in pagina
  select o.player_id, p.name, p.team, p.role,
         o.voto, o.bonus, o.note, o.updated_at,
         r.voto, coalesce(r.bonus, '{}'::jsonb), coalesce(r.minutes, 0)
    from rating_overrides o
    join players p on p.id = o.player_id
    join leagues l on l.id = o.league_id
    left join player_ratings r on r.season = l.season and r.matchday = o.matchday and r.player_id = o.player_id
   where o.league_id = p_league and o.matchday = p_matchday and public.is_member(p_league)
   order by case p.role when 'P' then 1 when 'D' then 2 when 'C' then 3 else 4 end, p.name;
$$;

-- Inserisce o aggiorna un override. Due "non tocco niente" distinti, perche' fv_of tratta il null come
-- "tieni il dato ufficiale":
--   p_voto null                 -> resta il voto di player_ratings, si correggono solo i bonus;
--   p_bonus e p_malus ENTRAMBI null -> restano i bonus ufficiali (passare '{}' invece di null AZZERA gol e assist:
--                                   e' la differenza fra "non li tocco" e "dichiaro che non ce ne sono").
-- p_bonus e p_malus vengono fusi in un unico oggetto: sono due campi solo perche' nel form dell'admin stanno in due
-- colonne (sopra i bonus, sotto i malus), nel database e nel calcolo sono la stessa cosa (le chiavi ammesse sono le
-- otto che scrive fanta_voti.py e che fv_of sa pesare; il segno sta nei pesi di leagues.settings.bonus).
create or replace function public.set_rating_override(p_league uuid, p_matchday integer, p_player integer,
                                                     p_voto numeric default null, p_bonus jsonb default null,
                                                     p_malus jsonb default null, p_note text default '',
                                                     p_recompute boolean default false)
returns jsonb language plpgsql security definer set search_path = public as $$
declare b jsonb; calc jsonb;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin della lega puo'' correggere i voti'; end if;
  if not exists (select 1 from players where id = p_player) then raise exception 'giocatore inesistente'; end if;
  if p_matchday is null or p_matchday < 1 then raise exception 'giornata non valida'; end if;
  if p_voto is not null and (p_voto < 0 or p_voto > 10) then raise exception 'il voto deve stare tra 0 e 10'; end if;
  if p_bonus is null and p_malus is null then
    b := null;                                   -- nessuno dei due campi compilato: i bonus ufficiali restano intatti
  else
    b := clean_bonus(coalesce(p_bonus, '{}'::jsonb)) || clean_bonus(coalesce(p_malus, '{}'::jsonb));
  end if;
  if p_voto is null and b is null then raise exception 'override vuoto: indica almeno il voto o i bonus'; end if;
  insert into rating_overrides(league_id, matchday, player_id, voto, bonus, note, created_by, updated_at)
    values (p_league, p_matchday, p_player, p_voto, b, coalesce(trim(p_note), ''), auth.uid(), now())
    on conflict (league_id, matchday, player_id) do update
      set voto = excluded.voto, bonus = excluded.bonus, note = excluded.note,
          created_by = excluded.created_by, updated_at = now();
  if p_recompute then calc := compute_matchday(p_league, p_matchday); end if;
  return jsonb_build_object('ok', true, 'player_id', p_player, 'matchday', p_matchday,
                            'voto', p_voto, 'bonus', b, 'recomputed', coalesce(p_recompute, false), 'compute', calc);
end $$;

-- Cancella un override: il giocatore torna al voto ufficiale di player_ratings.
create or replace function public.delete_rating_override(p_league uuid, p_matchday integer, p_player integer,
                                                         p_recompute boolean default false)
returns jsonb language plpgsql security definer set search_path = public as $$
declare n integer; calc jsonb;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin della lega puo'' correggere i voti'; end if;
  delete from rating_overrides where league_id = p_league and matchday = p_matchday and player_id = p_player;
  get diagnostics n = row_count;
  if p_recompute and n > 0 then calc := compute_matchday(p_league, p_matchday); end if;
  return jsonb_build_object('ok', true, 'deleted', n, 'recomputed', (p_recompute and n > 0), 'compute', calc);
end $$;


-- ############################################################################
-- ## 5) FORMAZIONI NASCOSTE FINO ALLA DEADLINE (punto 7 del blocco C)
-- ############################################################################
-- DEFAULT INVARIATO: senza settings.formazioni_nascoste = true tutto resta come oggi (formazioni altrui visibili
-- prima della deadline, scelta esplicita dell'utente, kb/FANTATB.md §9). L'opzione si accende dalla scheda Regole,
-- come mod_difesa_tab e le altre chiavi di leagues.settings.
-- Applicata LATO SERVER in due punti, perche' nasconderle nel frontend non nasconde niente:
--   a) la policy di lettura di lineups: le righe altrui non escono proprio dal database;
--   b) un trigger su results: senza di questo l'admin potrebbe far comparire le formazioni altrui dentro
--      results.detail lanciando "Calcola" prima della deadline, aggirando la (a).

drop policy if exists lineups_read on public.lineups;
create policy lineups_read on public.lineups for select to authenticated
  using (public.is_member(league_id) and (user_id = auth.uid() or public.lineups_visible(league_id, matchday)));

-- La scheda Schiera mostra "inviata / non inviata" per gli avversari: quel dato non e' la formazione e resta
-- disponibile anche a opzione accesa. Restituisce chi ha consegnato e quando, mai i giocatori schierati.
create or replace function public.lineups_status(p_league uuid, p_matchday integer)
returns table(user_id uuid, team_name text, submitted_at timestamptz)
language sql security definer stable set search_path = public as $$
  select m.user_id, m.team_name, lu.submitted_at
    from league_members m
    left join lineups lu on lu.league_id = m.league_id and lu.user_id = m.user_id and lu.matchday = p_matchday
   where m.league_id = p_league and public.is_member(p_league)
   order by m.team_name;
$$;

-- Guardia sul calcolo: a opzione accesa non si calcola una giornata prima che sia iniziata, altrimenti
-- results.detail (leggibile da tutti i membri) conterrebbe le formazioni che la policy sta nascondendo.
-- Se la giornata non ha starts_at non blocco nulla: senza deadline nota non posso dire che sia "troppo presto",
-- e bloccare fermerebbe il motore anche nelle leghe che usano calendari importati a mano.
create or replace function public.results_hidden_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare st timestamptz; hid boolean;
begin
  select coalesce((settings->>'formazioni_nascoste')::boolean, false) into hid from leagues where id = new.league_id;
  if not coalesce(hid, false) then return new; end if;
  select m.starts_at into st from matchdays m, leagues lg
    where lg.id = new.league_id and m.season = lg.season and m.number = new.matchday;
  if st is not null and st > now() then
    raise exception 'formazioni nascoste: la giornata % non e'' ancora iniziata, il calcolo e'' bloccato', new.matchday;
  end if;
  return new;
end $$;
drop trigger if exists results_hidden_guard on public.results;
create trigger results_hidden_guard before insert or update on public.results
  for each row execute function public.results_hidden_guard();


-- ############################################################################
-- ## 6) CLASSIFICA DI LEGA PUBBLICA E CONDIVISIBILE (punto 8 del blocco C)
-- ############################################################################
-- Impianto copiato dalle liste obiettivi del fix 008 (codice casuale + flag acceso dall'utente + funzione di lettura),
-- con una differenza voluta: le liste sono dati di gioco e la loro tabella e' leggibile da anon; qui i dati di partenza
-- riguardano PERSONE, quindi anon non tocca nessuna tabella e riceve solo cio' che questa funzione decide di mettere
-- nel jsonb. Fuori escono nome squadra, punti, gol e fantapunti: MAI email, MAI id utente, MAI rose o formazioni.

-- Accende/spegne la condivisione e, se serve, rigenera il codice (il link vecchio smette subito di funzionare:
-- e' l'unico modo per "richiamare indietro" un link gia' girato in chat).
create or replace function public.set_standings_share(p_league uuid, p_enabled boolean, p_new_code boolean default false)
returns jsonb language plpgsql security definer set search_path = public as $$
declare sh league_shares%rowtype;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin della lega'; end if;
  insert into league_shares(league_id, enabled) values (p_league, coalesce(p_enabled, false))
    on conflict (league_id) do update set enabled = coalesce(p_enabled, false), updated_at = now();
  if coalesce(p_new_code, false) then
    update league_shares set share_code = upper(substr(md5(random()::text || clock_timestamp()::text), 1, 12)),
                             updated_at = now()
      where league_id = p_league;
  end if;
  select * into sh from league_shares where league_id = p_league;
  return jsonb_build_object('enabled', sh.enabled, 'share_code', sh.share_code);
end $$;

-- Lettura pubblica: nessun login. Il codice e' la sola credenziale, quindi se e' sbagliato o la condivisione e'
-- spenta l'errore e' identico in entrambi i casi ("classifica non disponibile"): non deve far capire se una lega
-- con quel codice esista.
-- Il conteggio ripete esattamente quello che fa renderStandings in fanta/app.js (solo partite calcolate, il riposo
-- non conta), cosi' la pagina pubblica e l'app non si contraddicono mai.
create or replace function public.public_standings(p_code text)
returns jsonb language plpgsql security definer stable set search_path = public as $$
declare sh league_shares%rowtype; l leagues%rowtype; rows_j jsonb;
begin
  select * into sh from league_shares where share_code = upper(trim(coalesce(p_code, ''))) and enabled;
  if not found then raise exception 'classifica non disponibile'; end if;
  select * into l from leagues where id = sh.league_id;
  -- da qui in poi user_id sparisce: nel jsonb finisce solo il nome della squadra
  select jsonb_agg(jsonb_build_object('pos', ord.pos, 'team', ord.team_name, 'pt', ord.pt, 'g', ord.g,
                                      'v', ord.v, 'n', ord.n, 'p', ord.p, 'gf', ord.gf, 'gs', ord.gs,
                                      'fp', round(ord.fp, 1)) order by ord.pos)
    into rows_j
    from (select agg.*, row_number() over (order by agg.pt desc, agg.fp desc, (agg.gf - agg.gs) desc, agg.team_name) as pos
            from (select s.user_id, s.team_name,
                         count(gi.uid)::int as g,
                         count(*) filter (where gi.gf > gi.ga)::int as v,
                         count(*) filter (where gi.gf = gi.ga)::int as n,
                         count(*) filter (where gi.gf < gi.ga)::int as p,
                         coalesce(sum(gi.gf), 0)::int as gf,
                         coalesce(sum(gi.ga), 0)::int as gs,
                         coalesce(sum(gi.fp), 0)::numeric as fp,
                         coalesce(sum(case when gi.gf > gi.ga then 3 when gi.gf = gi.ga then 1 else 0 end), 0)::int as pt
                    from (select m.user_id, m.team_name from league_members m where m.league_id = sh.league_id) s
                    left join (
                      select f.home_id as uid, f.home_goals as gf, f.away_goals as ga, f.home_points as fp
                        from league_fixtures f
                       where f.league_id = sh.league_id and f.away_id is not null and f.home_goals is not null
                      union all
                      select f.away_id, f.away_goals, f.home_goals, f.away_points
                        from league_fixtures f
                       where f.league_id = sh.league_id and f.away_id is not null and f.home_goals is not null
                    ) gi on gi.uid = s.user_id
                   group by s.user_id, s.team_name) agg) ord;
  return jsonb_build_object('league', l.name, 'season', l.season, 'teams', coalesce(rows_j, '[]'::jsonb),
                            'generated_at', now());
end $$;


-- ############################################################################
-- ## 7) SCAMBI FRA SQUADRE E SVINCOLI CON RIMBORSO PARZIALE (punto 9 del blocco C)
-- ############################################################################
-- Chiavi nuove in leagues.settings (tutte facoltative, con default che non cambiano il comportamento attuale):
--   scambi_admin        bool    false  -> se true lo scambio accettato passa comunque dall'approvazione dell'admin
--   svincolo_rimborso   numeric 0.5    -> quota del prezzo pagato che torna in cassa allo svincolo (DEFAULT 50%,
--                                         arrotondata per difetto). 50% e' la scelta: rimborso pieno renderebbe lo
--                                         svincolo gratuito e trasformerebbe l'asta in un parcheggio, rimborso zero
--                                         lo renderebbe inutile. Con 0.5 liberare uno slot costa la meta' del prezzo.
--   mercato_giornata_aperta bool false -> se true consente scambi/svincoli anche a giornata in corso (sconsigliato)
--
-- GIORNATA IN CORSO — la scelta: scambi e svincoli sono VIETATI dal momento in cui la giornata comincia
-- (matchdays.starts_at) fino a quando non e' chiusa ('rated'). Motivo: le formazioni sono congelate alla deadline
-- (save_lineup) mentre compute_matchday somma i fantavoti dei giocatori SCHIERATI. Uno scambio a giornata iniziata
-- lascerebbe il giocatore a punteggio per la vecchia squadra e indisponibile per la nuova: i punti di quella giornata
-- sarebbero falsati per entrambe. L'admin che ha davvero bisogno di forzare (correzione, lega ferma) accende
-- mercato_giornata_aperta, ma e' una deroga dichiarata, non il comportamento normale.
--
-- FORMAZIONI FUTURE — quando un giocatore cambia rosa, ogni formazione GIA' SALVATA per una giornata non ancora
-- iniziata che lo contiene viene CANCELLATA (per entrambe le squadre coinvolte). Altrimenti resterebbe schierato un
-- giocatore che non e' piu' in rosa, che save_lineup non avrebbe mai accettato, e compute_matchday lo conterebbe.
-- Chi subisce la cancellazione rischiera' prima della deadline: e' l'unica via che non falsa i punti.
--
-- ATOMICITA': ogni funzione qui sotto e' una sola transazione. Se un solo controllo finale fallisce (crediti sotto
-- zero, slot di ruolo sforato) l'intera operazione viene annullata dall'exception: non esiste uno stato a meta'.

-- Applicazione vera e propria di uno scambio. Funzione interna: la chiamano solo respond_trade e admin_trade,
-- dopo aver messo la proposta in stato 'in_esecuzione' nella stessa transazione. Doppia protezione: privilegio
-- revocato a tutti (sotto, in fondo al file) e stato obbligatorio 'in_esecuzione', che nessuno puo' osservare
-- dall'esterno perche' dura meno di una transazione.
create or replace function public.trade_apply(p_trade uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare t trades%rowtype; l leagues%rowtype; moved integer[]; pid integer; r text; removed integer := 0;
  cf integer; ct integer;
begin
  select * into t from trades where id = p_trade for update;
  if not found or t.status <> 'in_esecuzione' then raise exception 'scambio non eseguibile'; end if;
  select * into l from leagues where id = t.league_id;
  -- blocco le due squadre: due scambi in parallelo sugli stessi crediti devono mettersi in fila
  perform 1 from league_members where league_id = t.league_id and user_id in (t.from_user, t.to_user) order by user_id for update;

  -- i giocatori devono essere ANCORA nelle rose giuste: fra la proposta e l'accettazione possono essere stati
  -- svincolati o scambiati con un terzo
  foreach pid in array coalesce(t.give_players, '{}'::integer[]) loop
    if not exists (select 1 from rosters where league_id = t.league_id and player_id = pid and user_id = t.from_user) then
      raise exception 'il giocatore % non e'' piu'' nella rosa di chi propone', (select name from players where id = pid); end if;
  end loop;
  foreach pid in array coalesce(t.get_players, '{}'::integer[]) loop
    if not exists (select 1 from rosters where league_id = t.league_id and player_id = pid and user_id = t.to_user) then
      raise exception 'il giocatore % non e'' piu'' nella rosa dell''altra squadra', (select name from players where id = pid); end if;
  end loop;

  -- il prezzo segue il giocatore: resta il prezzo pagato all'asta, cosi' un eventuale svincolo futuro rimborsa una
  -- quota di quello che il giocatore e' costato davvero. In uno scambio a piu' giocatori + conguaglio non esiste un
  -- modo onesto di riattribuire i prezzi.
  update rosters set user_id = t.to_user, acquired_at = now()
    where league_id = t.league_id and player_id = any(coalesce(t.give_players, '{}'::integer[]));
  update rosters set user_id = t.from_user, acquired_at = now()
    where league_id = t.league_id and player_id = any(coalesce(t.get_players, '{}'::integer[]));

  if coalesce(t.cash, 0) <> 0 then
    update league_members set credits = credits - t.cash where league_id = t.league_id and user_id = t.from_user;
    update league_members set credits = credits + t.cash where league_id = t.league_id and user_id = t.to_user;
  end if;

  -- controlli finali con le REGOLE DELLA LEGA gia' esistenti (slots_left legge settings.slots)
  select credits into cf from league_members where league_id = t.league_id and user_id = t.from_user;
  select credits into ct from league_members where league_id = t.league_id and user_id = t.to_user;
  if cf < 0 or ct < 0 then raise exception 'crediti insufficienti per il conguaglio'; end if;
  foreach r in array array['P','D','C','A'] loop
    if slots_left(t.league_id, t.from_user, r) < 0 then raise exception 'chi propone sforerebbe gli slot di ruolo %', r; end if;
    if slots_left(t.league_id, t.to_user, r) < 0 then raise exception 'l''altra squadra sforerebbe gli slot di ruolo %', r; end if;
  end loop;

  -- formazioni future che contengono un giocatore appena passato di mano: via, vanno rifatte
  moved := coalesce(t.give_players, '{}'::integer[]) || coalesce(t.get_players, '{}'::integer[]);
  delete from lineups as lu
   where lu.league_id = t.league_id and lu.user_id in (t.from_user, t.to_user)
     and exists (select 1 from unnest(lu.starters || lu.bench) x where x = any(moved))
     and coalesce((select m.starts_at from matchdays m where m.season = l.season and m.number = lu.matchday),
                  'infinity'::timestamptz) > now();
  get diagnostics removed = row_count;

  update trades set status = 'conclusa', executed_at = now(), updated_at = now() where id = t.id;
  return jsonb_build_object('ok', true, 'trade', t.id, 'players_out', coalesce(array_length(t.give_players, 1), 0),
                            'players_in', coalesce(array_length(t.get_players, 1), 0), 'cash', t.cash,
                            'lineups_reset', removed);
end $$;

-- Propone uno scambio all'altra squadra. Qui si controlla tutto quello che si puo' controllare subito; i controlli
-- che dipendono dal momento (rose, crediti, slot) vengono ripetuti all'esecuzione, perche' nel frattempo il mondo cambia.
create or replace function public.propose_trade(p_league uuid, p_to uuid, p_give integer[], p_get integer[],
                                                p_cash integer default 0, p_note text default '')
returns uuid language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; pid integer; tid uuid; g integer[]; h integer[];
begin
  if auth.uid() is null then raise exception 'non autenticato'; end if;
  if not is_member(p_league) then raise exception 'non sei in questa lega'; end if;
  if p_to is not distinct from auth.uid() then raise exception 'non puoi scambiare con te stesso'; end if;
  if p_to is null then raise exception 'destinatario mancante'; end if;
  if not exists (select 1 from league_members where league_id = p_league and user_id = p_to) then
    raise exception 'la squadra destinataria non e'' in questa lega'; end if;
  select * into l from leagues where id = p_league;
  if coalesce(l.settings->>'phase', 'asta') = 'asta' then raise exception 'mercato chiuso: la lega e'' in fase d''asta'; end if;
  if exists (select 1 from auctions where league_id = p_league and status = 'live') then
    raise exception 'c''e'' un''asta in corso'; end if;
  if matchday_running(p_league) and not coalesce((l.settings->>'mercato_giornata_aperta')::boolean, false) then
    raise exception 'giornata in corso: gli scambi riaprono quando la giornata e'' chiusa'; end if;

  g := coalesce(p_give, '{}'::integer[]); h := coalesce(p_get, '{}'::integer[]);
  if coalesce(array_length(g, 1), 0) + coalesce(array_length(h, 1), 0) = 0 then
    raise exception 'lo scambio deve muovere almeno un giocatore'; end if;
  if (select count(distinct x) from unnest(g || h) x) <> coalesce(array_length(g || h, 1), 0) then
    raise exception 'giocatore ripetuto nella proposta'; end if;
  foreach pid in array g loop
    if not exists (select 1 from rosters where league_id = p_league and player_id = pid and user_id = auth.uid()) then
      raise exception 'il giocatore % non e'' nella tua rosa', pid; end if;
  end loop;
  foreach pid in array h loop
    if not exists (select 1 from rosters where league_id = p_league and player_id = pid and user_id = p_to) then
      raise exception 'il giocatore % non e'' nella rosa dell''altra squadra', pid; end if;
  end loop;
  -- il conguaglio non puo' superare i crediti che ho ora (il controllo definitivo e' comunque all'esecuzione)
  if coalesce(p_cash, 0) > (select credits from league_members where league_id = p_league and user_id = auth.uid()) then
    raise exception 'non hai abbastanza crediti per il conguaglio'; end if;

  insert into trades(league_id, from_user, to_user, give_players, get_players, cash, note)
    values (p_league, auth.uid(), p_to, g, h, coalesce(p_cash, 0), coalesce(trim(p_note), ''))
    returning id into tid;
  return tid;
end $$;

-- La squadra destinataria accetta o rifiuta. Se la lega richiede l'ultima parola dell'admin (settings.scambi_admin)
-- l'accettazione mette la proposta in attesa invece di eseguirla.
create or replace function public.respond_trade(p_trade uuid, p_accept boolean)
returns jsonb language plpgsql security definer set search_path = public as $$
declare t trades%rowtype; l leagues%rowtype;
begin
  if auth.uid() is null then raise exception 'non autenticato'; end if;
  select * into t from trades where id = p_trade for update;
  if not found then raise exception 'proposta inesistente'; end if;
  -- "is distinct from" e non "<>": con auth.uid() nullo il confronto normale vale NULL e il controllo NON scatterebbe
  if t.to_user is distinct from auth.uid() then raise exception 'la proposta non e'' indirizzata a te'; end if;
  if t.status <> 'proposta' then raise exception 'la proposta non e'' piu'' aperta (stato: %)', t.status; end if;
  if not coalesce(p_accept, false) then
    update trades set status = 'rifiutata', decided_by = auth.uid(), updated_at = now() where id = t.id;
    return jsonb_build_object('status', 'rifiutata');
  end if;
  select * into l from leagues where id = t.league_id;
  if coalesce(l.settings->>'phase', 'asta') = 'asta' then raise exception 'mercato chiuso: la lega e'' in fase d''asta'; end if;
  if matchday_running(t.league_id) and not coalesce((l.settings->>'mercato_giornata_aperta')::boolean, false) then
    raise exception 'giornata in corso: gli scambi riaprono quando la giornata e'' chiusa'; end if;
  if coalesce((l.settings->>'scambi_admin')::boolean, false) then
    update trades set status = 'attesa_admin', decided_by = auth.uid(), updated_at = now() where id = t.id;
    return jsonb_build_object('status', 'attesa_admin');
  end if;
  update trades set status = 'in_esecuzione', decided_by = auth.uid(), updated_at = now() where id = t.id;
  return jsonb_build_object('status', 'conclusa', 'result', trade_apply(t.id));
end $$;

-- L'admin approva o respinge una proposta gia' accettata (solo con settings.scambi_admin = true).
create or replace function public.admin_trade(p_trade uuid, p_approve boolean)
returns jsonb language plpgsql security definer set search_path = public as $$
declare t trades%rowtype; l leagues%rowtype;
begin
  select * into t from trades where id = p_trade for update;
  if not found then raise exception 'proposta inesistente'; end if;
  if not is_admin(t.league_id) then raise exception 'solo l''admin della lega'; end if;
  if t.status <> 'attesa_admin' then raise exception 'la proposta non e'' in attesa di approvazione (stato: %)', t.status; end if;
  if not coalesce(p_approve, false) then
    update trades set status = 'respinta', decided_by = auth.uid(), updated_at = now() where id = t.id;
    return jsonb_build_object('status', 'respinta');
  end if;
  select * into l from leagues where id = t.league_id;
  if matchday_running(t.league_id) and not coalesce((l.settings->>'mercato_giornata_aperta')::boolean, false) then
    raise exception 'giornata in corso: gli scambi riaprono quando la giornata e'' chiusa'; end if;
  update trades set status = 'in_esecuzione', decided_by = auth.uid(), updated_at = now() where id = t.id;
  return jsonb_build_object('status', 'conclusa', 'result', trade_apply(t.id));
end $$;

-- Il proponente ritira la proposta; l'admin puo' ritirarne una qualsiasi ancora aperta (moderazione).
create or replace function public.cancel_trade(p_trade uuid)
returns void language plpgsql security definer set search_path = public as $$
declare t trades%rowtype;
begin
  if auth.uid() is null then raise exception 'non autenticato'; end if;
  select * into t from trades where id = p_trade for update;
  if not found then raise exception 'proposta inesistente'; end if;
  -- "is distinct from" per lo stesso motivo di respond_trade: con uid nullo "<>" darebbe NULL e lascerebbe passare
  if t.from_user is distinct from auth.uid() and not is_admin(t.league_id) then raise exception 'non puoi annullare questa proposta'; end if;
  if t.status not in ('proposta', 'attesa_admin') then raise exception 'la proposta non e'' piu'' aperta (stato: %)', t.status; end if;
  update trades set status = 'annullata', decided_by = auth.uid(), updated_at = now() where id = t.id;
end $$;

-- SVINCOLO con rimborso parziale. Lo fa il proprietario della rosa; l'admin puo' farlo per un'altra squadra
-- passando p_user (serve per le correzioni: e' lo stesso ruolo che ha oggi release_player, che NON viene toccata
-- e continua a rimborsare il 100% come strumento di sola amministrazione).
create or replace function public.release_own_player(p_league uuid, p_player integer, p_user uuid default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; u uuid; q numeric; r rosters%rowtype; back integer; removed integer := 0;
begin
  u := coalesce(p_user, auth.uid());
  if u is null then raise exception 'non autenticato'; end if;
  if u is distinct from auth.uid() and not is_admin(p_league) then raise exception 'puoi svincolare solo i tuoi giocatori'; end if;
  if not is_member(p_league) then raise exception 'non sei in questa lega'; end if;
  select * into l from leagues where id = p_league;
  if coalesce(l.settings->>'phase', 'asta') = 'asta' then raise exception 'in fase d''asta si usa l''asta, non lo svincolo'; end if;
  if exists (select 1 from auctions where league_id = p_league and status = 'live') then
    raise exception 'c''e'' un''asta in corso'; end if;
  if matchday_running(p_league) and not coalesce((l.settings->>'mercato_giornata_aperta')::boolean, false) then
    raise exception 'giornata in corso: gli svincoli riaprono quando la giornata e'' chiusa'; end if;

  select * into r from rosters where league_id = p_league and player_id = p_player and user_id = u for update;
  if not found then raise exception 'il giocatore non e'' in quella rosa'; end if;

  q := coalesce((l.settings->>'svincolo_rimborso')::numeric, 0.5);
  if q < 0 then q := 0; end if;
  if q > 1 then q := 1; end if;
  back := floor(greatest(coalesce(r.price, 0), 0) * q)::int;   -- per difetto: la lega non regala crediti

  delete from rosters where league_id = p_league and player_id = p_player;
  update league_members set credits = credits + back where league_id = p_league and user_id = u;
  insert into releases(league_id, user_id, player_id, price, refund) values (p_league, u, p_player, coalesce(r.price, 0), back);

  -- stessa regola degli scambi: le formazioni future che lo contengono vanno rifatte
  delete from lineups as lu
   where lu.league_id = p_league and lu.user_id = u
     and (p_player = any(lu.starters) or p_player = any(lu.bench))
     and coalesce((select m.starts_at from matchdays m where m.season = l.season and m.number = lu.matchday),
                  'infinity'::timestamptz) > now();
  get diagnostics removed = row_count;

  return jsonb_build_object('ok', true, 'player_id', p_player, 'price', coalesce(r.price, 0), 'refund', back,
                            'quota', q, 'lineups_reset', removed);
end $$;


-- ############################################################################
-- ## 8) REALTIME
-- ############################################################################
-- Le proposte di scambio arrivano mentre l'altro e' in app: senza realtime servirebbe un refresh a mano.
do $$ begin
  begin alter publication supabase_realtime add table public.trades; exception when duplicate_object then null; end;
end $$;


-- ############################################################################
-- ## 9) PRIVILEGI
-- ############################################################################
-- In Postgres ogni funzione nuova nasce eseguibile da PUBLIC: qui i grant sono espliciti per dire chi deve poterla
-- chiamare, e trade_apply viene REVOCATA a tutti perche' e' un pezzo interno di respond_trade/admin_trade (che sono
-- security definer e la chiamano come proprietario). Senza la revoca un membro potrebbe eseguirla da solo.
revoke all on function public.trade_apply(uuid) from public;
revoke all on function public.trade_apply(uuid) from anon, authenticated;

grant execute on function public.matchday_running(uuid) to authenticated;
grant execute on function public.lineups_visible(uuid, integer) to anon, authenticated;
grant execute on function public.clean_bonus(jsonb) to authenticated;
grant execute on function public.league_overrides(uuid, integer) to authenticated;
grant execute on function public.set_rating_override(uuid, integer, integer, numeric, jsonb, jsonb, text, boolean) to authenticated;
grant execute on function public.delete_rating_override(uuid, integer, integer, boolean) to authenticated;
grant execute on function public.lineups_status(uuid, integer) to authenticated;
grant execute on function public.set_standings_share(uuid, boolean, boolean) to authenticated;
grant execute on function public.public_standings(text) to anon, authenticated;
grant execute on function public.propose_trade(uuid, uuid, integer[], integer[], integer, text) to authenticated;
grant execute on function public.respond_trade(uuid, boolean) to authenticated;
grant execute on function public.admin_trade(uuid, boolean) to authenticated;
grant execute on function public.cancel_trade(uuid) to authenticated;
grant execute on function public.release_own_player(uuid, integer, uuid) to authenticated;
