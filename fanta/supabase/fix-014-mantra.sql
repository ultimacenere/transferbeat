-- FantaTB fix 014: MANTRA (kb/FANTATB.md §13, pending 9). Da incollare nell'SQL Editor di Supabase in un editor VUOTO.
-- Idempotente: si puo' rilanciare.
--
-- COSA FA
--   Il pending Mantra era dato per bloccato perche' "i ruoli Mantra non esistono in nessuna API". Non e' piu' vero:
--   scripts/fanta_quotazioni.py legge la colonna RM del listone ufficiale di Fantacalcio.it e la scrive in
--   players.role_mantra[] (schema.sql riga 33). Il DATO c'e' gia': qui manca solo il MODO DI GIOCO. Questo fix aggiunge
--   A) l'opzione di lega  leagues.settings.modalita = 'classic' | 'mantra'  (default CLASSIC, vedi "REGOLA NUMERO UNO");
--   B) le tabelle dati mantra_roles (11 ruoli ufficiali) e mantra_modules (17 moduli con gli 11 slot ciascuno);
--   C) la validazione lato server di una formazione Mantra (mantra_check), con il perche' quando non e' valida;
--   D) save_lineup che smista: lega classic -> corpo identico a oggi; lega mantra -> save_lineup_mantra;
--   E) compute_matchday con le sostituzioni dalla panchina per SLOT Mantra invece che per ruolo Classic;
--   F) grant e RLS; G) le query di verifica.
--
-- REGOLA NUMERO UNO: nessuna lega esistente cambia comportamento.
--   leagues.settings non ha oggi la chiave 'modalita': league_mode() la legge con default 'classic' e qualunque valore
--   sconosciuto ricade su 'classic'. Il corpo Classic di save_lineup e' copiato IDENTICO dal fix 005. In compute_matchday
--   la strada Mantra si apre solo se la formazione ha lineups.slots valorizzato, e slots lo scrive SOLO save_lineup_mantra:
--   su tutte le formazioni gia' salvate slots e' NULL e la sostituzione resta quella per ruolo Classic, riga per riga.
--
-- COSA PRESUPPONE
--   * schema.sql + fix 001..012 gia' eseguiti. Il fix 013 (lega) e' indipendente: non ridefinisce ne' compute_matchday
--     ne' save_lineup ne' update_league_settings, quindi 014 si puo' eseguire prima o dopo il 013, indifferentemente.
--   * ATTENZIONE PER I FIX FUTURI: la sezione E ridefinisce compute_matchday partendo dalla versione del FIX 012
--     (6 politico + fix 010 live + fix 011 modificatori). Rispetto al 012 cambiano quattro cose e basta:
--       1. tre variabili in piu' (idx, slot, sub_r);  2. un contatore di posizione nel ciclo dei titolari;
--       3. la riga della panchina  "continue when ... (select role from players where id = bp) <> r"
--          diventa                 "continue when bp = any(used) or not sub_eligible(slot, bp, r)";
--       4. il dettaglio del giocatore porta anche 'slot' e quello della squadra anche 'modalita'.
--     Tutto il resto (fantavoti, modificatori, gol a soglie, scontri diretti) e' copiato riga per riga dal 012: il
--     confronto e' verificabile con un diff fra i due file, ed e' proprio quello che serve per fidarsi del punto 4.
--     Se un giorno esce un fix 015+ che riscrive compute_matchday, si parte da QUESTA versione (o si riporta a mano
--     il diff qui sopra), altrimenti le sostituzioni Mantra tornano a ragionare per ruolo Classic.
--     Stessa cosa per save_lineup: il ramo Classic e' il corpo del FIX 005, con in piu' lo smistamento in testa e
--     "slots = null" nella insert/update.
--   * Il calcolo dei punti NON cambia fra Classic e Mantra: bonus, malus, modificatori, gol a soglie, fattore casa
--     restano identici. L'unica differenza e' CHI puo' entrare al posto di chi.
--
-- I RUOLI MANTRA (codici ufficiali della colonna RM del listone Fantacalcio.it, separati da ';' — es. "Dd;Ds", "E;W;A")
--   Por  portiere                        Dd  difensore destro          Dc  difensore centrale     Ds  difensore sinistro
--   E    esterno basso (a tutta fascia)   M   mediano                   C   centrocampista centrale
--   W    ala (esterno alto)               T   trequartista              A   attaccante (2a punta / esterno offensivo)
--   Pc   punta centrale
--   Un giocatore ne ha PIU' DI UNO: per questo role_mantra e' un array. Il confronto e' tollerante sulle maiuscole e
--   sui caratteri sporchi (mantra_norm): "PC", "pc", "Pc*" diventano tutti 'Pc'. Nessun UPDATE su players: i dati del
--   listone restano come li scrive fanta_quotazioni.py.
--
-- I MODULI: i codici dei RUOLI sono ufficiali; la composizione degli SLOT di ogni modulo (quali ruoli accetta lo slot
--   numero 5 di un 4-3-3, per dire) e' la nostra lettura dello schema Mantra. Per questo mantra_modules e' una tabella
--   DATI e non codice: se un modulo va corretto basta un UPDATE su una riga, senza rifare le funzioni.
--   Regole seguite: difesa a 3 = tre Dc; difesa a 4 = Dd, Dc, Dc, Ds; difesa a 5 = i due esterni accettano Dd/E e Ds/E;
--   centrali di centrocampo = M o C; esterni di centrocampo = E con la difesa a 3 (devono coprire tutta la fascia),
--   E o W con la difesa a 4; tridente = W/A, Pc, W/A; coppia d'attacco = A/Pc + Pc; punta unica = Pc.
--
-- COSA NON FA (scelta esplicita, non dimenticanza)
--   Niente "adattamento": in questo fix un giocatore occupa uno slot solo se uno dei suoi ruoli Mantra e' fra quelli
--   ammessi dallo slot, punto. L'adattamento con malus si potra' aggiungere dopo, come opzione di lega, senza toccare
--   il resto (servirebbe un matching a costo minimo, non il matching binario di qui).
--   Niente vincoli Mantra sulla ROSA: gli slot d'asta (settings.slots = {"P":3,"D":8,...}) restano sui ruoli Classic,
--   che nel listone ci sono sempre. Cambiare anche quelli e' un'altra partita.
--
-- COME SI VERIFICA CHE SIA ANDATO A BUON FINE: vedi la SEZIONE G in fondo al file.

-- ==================== 0) LA COLONNA CHE TIENE INSIEME TUTTO ====================
-- Per ogni titolare, i ruoli ammessi dallo slot che occupa, separati da '|' (es. 'M|C'). NULL = formazione Classic.
-- Si tiene la stringa e non il numero dello slot perche' cosi' la formazione resta leggibile e valutabile da sola,
-- anche se domani la definizione del modulo in mantra_modules viene corretta: una giornata gia' giocata non deve
-- cambiare risultato perche' abbiamo ritoccato una tabella. Sta in cima perche' le funzioni qui sotto la usano.
alter table public.lineups add column if not exists slots text[];

-- ==================== A) MODALITA' DI LEGA ====================

-- Modalita' di una lega. Default 'classic' e qualunque valore non riconosciuto ricade su 'classic': una lega che non ha
-- mai sentito parlare di Mantra non deve poter finire in Mantra per un refuso nel jsonb.
create or replace function public.league_mode(p_league uuid) returns text
language sql stable security definer set search_path = public as $$
  select case lower(coalesce((select settings->>'modalita' from leagues where id = p_league), 'classic'))
           when 'mantra' then 'mantra' else 'classic' end;
$$;

-- Cambio di modalita'. Solo l'admin. Di default rifiuta se in lega esistono gia' formazioni salvate: passare da Classic
-- a Mantra a stagione in corso lascerebbe formazioni senza slot (e viceversa formazioni con slot che non c'entrano piu'),
-- quindi o si sceglie prima di giocare, o si accetta con p_force e si riscrivono le formazioni.
-- Passando a 'classic' gli slot vengono azzerati: cosi' compute_matchday torna a sostituire per ruolo Classic.
create or replace function public.set_league_mode(p_league uuid, p_mode text, p_force boolean default false)
returns jsonb language plpgsql security definer set search_path = public as $$
declare mo text; n integer; s jsonb;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin'; end if;
  mo := lower(btrim(coalesce(p_mode, '')));
  if mo not in ('classic', 'mantra') then raise exception 'modalita'' non valida: usare classic o mantra'; end if;
  select count(*) into n from lineups where league_id = p_league;
  if n > 0 and not p_force then
    raise exception 'ci sono gia'' % formazioni salvate: rilancia con p_force = true e riscrivile', n; end if;
  select settings into s from leagues where id = p_league;
  update leagues set settings = coalesce(s, '{}'::jsonb) || jsonb_build_object('modalita', mo) where id = p_league;
  if mo = 'classic' then update lineups set slots = null where league_id = p_league; end if;
  return jsonb_build_object('modalita', mo, 'formazioni_toccate', n);
end $$;

-- Il modulo "impostazioni" dell'app manda l'INTERO jsonb settings. Se un giorno salva le impostazioni senza la chiave
-- 'modalita' (perche' il form non la conosce), una lega Mantra tornerebbe Classic a meta' stagione senza dire niente.
-- Qui la chiave si conserva quando il chiamante non la manda. Per il resto e' la update_league_settings dello schema.
create or replace function public.update_league_settings(p_league uuid, p_settings jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare old jsonb; ns jsonb;
begin
  if not is_admin(p_league) then raise exception 'solo l''admin'; end if;
  select settings into old from leagues where id = p_league;
  ns := coalesce(p_settings, '{}'::jsonb);
  if not (ns ? 'modalita') and coalesce(old, '{}'::jsonb) ? 'modalita' then
    ns := ns || jsonb_build_object('modalita', old->>'modalita'); end if;
  update leagues set settings = ns where id = p_league;
  update auctions set timer_seconds = coalesce((ns->>'timer')::int, timer_seconds) where league_id = p_league;
end $$;

-- ==================== B) RUOLI E MODULI MANTRA (tabelle dati) ====================

create table if not exists public.mantra_roles (
  code text primary key,          -- sigla ufficiale della colonna RM del listone
  ord  integer not null,          -- ordine di lettura, dal portiere alla punta
  label text not null
);
insert into public.mantra_roles(code, ord, label) values
  ('Por', 1, 'Portiere'),
  ('Dd',  2, 'Difensore destro'),
  ('Dc',  3, 'Difensore centrale'),
  ('Ds',  4, 'Difensore sinistro'),
  ('E',   5, 'Esterno basso (a tutta fascia)'),
  ('M',   6, 'Mediano'),
  ('C',   7, 'Centrocampista centrale'),
  ('W',   8, 'Ala (esterno alto)'),
  ('T',   9, 'Trequartista'),
  ('A',  10, 'Attaccante (seconda punta, esterno offensivo)'),
  ('Pc', 11, 'Punta centrale')
on conflict (code) do update set ord = excluded.ord, label = excluded.label;

-- Un modulo Mantra = 11 slot ordinati. Ogni slot: n (posizione 1..11), line (P/D/C/T/A, serve solo a disegnare il campo),
-- roles (i ruoli Mantra ammessi). L'ORDINE degli slot conta: lineups.slots viene allineato ai titolari usando queste
-- posizioni. Tabella dati: per correggere un modulo basta un update su slots.
create table if not exists public.mantra_modules (
  code text primary key,          -- '4-3-3', '4-2-3-1', ... (nel Mantra le linee possono essere quattro)
  ord integer not null default 0, -- ordine in cui mostrarli nella tendina
  slots jsonb not null,
  active boolean not null default true
);

insert into public.mantra_modules(code, ord, slots) values
('3-4-3', 10, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dc"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},
  {"n":5,"line":"C","roles":["E"]},{"n":6,"line":"C","roles":["M","C"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["E"]},
  {"n":9,"line":"A","roles":["W","A"]},{"n":10,"line":"A","roles":["Pc"]},{"n":11,"line":"A","roles":["W","A"]}]'::jsonb),
('3-4-1-2', 20, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dc"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},
  {"n":5,"line":"C","roles":["E"]},{"n":6,"line":"C","roles":["M","C"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["E"]},
  {"n":9,"line":"T","roles":["T"]},
  {"n":10,"line":"A","roles":["A","Pc"]},{"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('3-4-2-1', 30, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dc"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},
  {"n":5,"line":"C","roles":["E"]},{"n":6,"line":"C","roles":["M","C"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["E"]},
  {"n":9,"line":"T","roles":["T","W"]},{"n":10,"line":"T","roles":["T","W"]},
  {"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('3-5-2', 40, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dc"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},
  {"n":5,"line":"C","roles":["E"]},{"n":6,"line":"C","roles":["M","C"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},{"n":9,"line":"C","roles":["E"]},
  {"n":10,"line":"A","roles":["A","Pc"]},{"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('3-5-1-1', 50, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dc"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},
  {"n":5,"line":"C","roles":["E"]},{"n":6,"line":"C","roles":["M","C"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},{"n":9,"line":"C","roles":["E"]},
  {"n":10,"line":"T","roles":["T","A"]},
  {"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('4-4-2', 60, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Ds"]},
  {"n":6,"line":"C","roles":["E","W"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},{"n":9,"line":"C","roles":["E","W"]},
  {"n":10,"line":"A","roles":["A","Pc"]},{"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('4-4-1-1', 70, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Ds"]},
  {"n":6,"line":"C","roles":["E","W"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},{"n":9,"line":"C","roles":["E","W"]},
  {"n":10,"line":"T","roles":["T","A"]},
  {"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('4-3-3', 80, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Ds"]},
  {"n":6,"line":"C","roles":["M","C"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},
  {"n":9,"line":"A","roles":["W","A"]},{"n":10,"line":"A","roles":["Pc"]},{"n":11,"line":"A","roles":["W","A"]}]'::jsonb),
('4-3-1-2', 90, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Ds"]},
  {"n":6,"line":"C","roles":["M","C"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},
  {"n":9,"line":"T","roles":["T"]},
  {"n":10,"line":"A","roles":["A","Pc"]},{"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('4-3-2-1', 100, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Ds"]},
  {"n":6,"line":"C","roles":["M","C"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},
  {"n":9,"line":"T","roles":["T","W"]},{"n":10,"line":"T","roles":["T","W"]},
  {"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('4-2-3-1', 110, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Ds"]},
  {"n":6,"line":"C","roles":["M","C"]},{"n":7,"line":"C","roles":["M","C"]},
  {"n":8,"line":"T","roles":["W","T"]},{"n":9,"line":"T","roles":["T"]},{"n":10,"line":"T","roles":["W","T"]},
  {"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('4-1-4-1', 120, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Ds"]},
  {"n":6,"line":"C","roles":["M"]},
  {"n":7,"line":"C","roles":["E","W"]},{"n":8,"line":"C","roles":["M","C"]},{"n":9,"line":"C","roles":["M","C"]},{"n":10,"line":"C","roles":["E","W"]},
  {"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('4-5-1', 130, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Ds"]},
  {"n":6,"line":"C","roles":["E","W"]},{"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},{"n":9,"line":"C","roles":["M","C"]},{"n":10,"line":"C","roles":["E","W"]},
  {"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('5-3-2', 140, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd","E"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Dc"]},{"n":6,"line":"D","roles":["Ds","E"]},
  {"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},{"n":9,"line":"C","roles":["M","C"]},
  {"n":10,"line":"A","roles":["A","Pc"]},{"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('5-4-1', 150, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd","E"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Dc"]},{"n":6,"line":"D","roles":["Ds","E"]},
  {"n":7,"line":"C","roles":["W","T"]},{"n":8,"line":"C","roles":["M","C"]},{"n":9,"line":"C","roles":["M","C"]},{"n":10,"line":"C","roles":["W","T"]},
  {"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('5-3-1-1', 160, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd","E"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Dc"]},{"n":6,"line":"D","roles":["Ds","E"]},
  {"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},{"n":9,"line":"C","roles":["M","C"]},
  {"n":10,"line":"T","roles":["T","A"]},
  {"n":11,"line":"A","roles":["Pc"]}]'::jsonb),
('5-2-1-2', 170, '[{"n":1,"line":"P","roles":["Por"]},
  {"n":2,"line":"D","roles":["Dd","E"]},{"n":3,"line":"D","roles":["Dc"]},{"n":4,"line":"D","roles":["Dc"]},{"n":5,"line":"D","roles":["Dc"]},{"n":6,"line":"D","roles":["Ds","E"]},
  {"n":7,"line":"C","roles":["M","C"]},{"n":8,"line":"C","roles":["M","C"]},
  {"n":9,"line":"T","roles":["T"]},
  {"n":10,"line":"A","roles":["A","Pc"]},{"n":11,"line":"A","roles":["Pc"]}]'::jsonb)
on conflict (code) do update set ord = excluded.ord, slots = excluded.slots, active = true;

-- Rete di sicurezza sui dati appena inseriti: un modulo con 10 o 12 slot manderebbe in errore ogni salvataggio,
-- e il momento per accorgersene e' adesso, non al primo utente che prova a schierare.
do $$
declare bad text;
begin
  select string_agg(code, ', ') into bad from mantra_modules where jsonb_array_length(slots) <> 11;
  if bad is not null then raise exception 'moduli Mantra con un numero di slot diverso da 11: %', bad; end if;
  select string_agg(distinct t.rc, ', ') into bad
    from mantra_modules m
    cross join lateral jsonb_array_elements(m.slots) s
    cross join lateral jsonb_array_elements_text(s->'roles') t(rc)
    where t.rc not in (select mr.code from mantra_roles mr);
  if bad is not null then raise exception 'ruoli Mantra sconosciuti nei moduli: %', bad; end if;
end $$;

-- ==================== C) VALIDAZIONE LATO SERVER ====================

-- Normalizza le sigle del listone: toglie tutto cio' che non e' lettera e ignora le maiuscole, poi tiene solo i codici
-- che esistono davvero. Cosi' "PC", "pc ", "Pc*" sono tutti 'Pc' e non serve alcun UPDATE su players.
create or replace function public.mantra_norm(p text[]) returns text[]
language sql stable set search_path = public as $$
  select coalesce(array_agg(distinct r.code), '{}'::text[])
    from unnest(coalesce(p, '{}'::text[])) x
    join mantra_roles r on lower(r.code) = lower(regexp_replace(x, '[^A-Za-z]', '', 'g'));
$$;

-- Un giocatore puo' occupare uno slot? Uno dei suoi ruoli Mantra deve essere fra quelli ammessi. Niente adattamenti.
create or replace function public.mantra_fits(p_player integer, p_slot text) returns boolean
language sql stable set search_path = public as $$
  select coalesce((select mantra_norm(p.role_mantra) && string_to_array(p_slot, '|') from players p where p.id = p_player), false);
$$;

-- Passo dell'algoritmo di Kuhn (matching bipartito, 11 giocatori x 11 slot): prova ad assegnare il giocatore p_i a uno
-- slot libero e, se sono tutti occupati, prova a spostare chi li occupa. Serve un matching vero e non un'assegnazione
-- avida: con quattro difensori che sanno fare Dd/Dc/Ds l'ordine con cui li piazzi decide se la formazione "risulta"
-- valida o no, e una formazione legittima non deve essere rifiutata per l'ordine in cui l'utente ha cliccato i nomi.
-- p_adj e' un array jsonb: p_adj[i-1] = elenco degli slot che il giocatore i puo' occupare.
create or replace function public.mantra_augment(
  p_i integer, p_adj jsonb, inout p_match integer[], inout p_seen boolean[], out p_ok boolean)
language plpgsql stable set search_path = public as $$
declare j integer; r record;
begin
  p_ok := false;
  for j in select value::int from jsonb_array_elements_text(p_adj->(p_i - 1)) loop
    if not coalesce(p_seen[j], false) then
      p_seen[j] := true;
      if coalesce(p_match[j], 0) = 0 then
        p_match[j] := p_i; p_ok := true; return;
      end if;
      -- lo slot e' occupato: chiedo all'occupante di spostarsi altrove
      select * into r from public.mantra_augment(p_match[j], p_adj, p_match, p_seen);
      p_match := r.p_match; p_seen := r.p_seen;
      if r.p_ok then p_match[j] := p_i; p_ok := true; return; end if;
    end if;
  end loop;
end $$;

-- LA funzione: dato un modulo e 11 giocatori dice se la formazione e' valida e, se no, perche'.
-- Ritorna {"ok":bool, "module":..., "assign":[{"n","slot","player_id","name"}], "slots":[...allineati a p_players...],
--          "errors":[testo in italiano]}.
-- 'slots' e' l'array da salvare in lineups.slots: slots[i] = ruoli ammessi dallo slot toccato a p_players[i].
create or replace function public.mantra_check(p_module text, p_players integer[])
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare mo mantra_modules%rowtype; n integer; i integer; j integer;
  sr text[] := '{}'; pm text[] := '{}'; pn text[] := '{}';
  adj jsonb := '[]'::jsonb; row_adj jsonb;
  mt integer[]; sn boolean[]; res record; ok boolean := true;
  assign jsonb := '[]'::jsonb; errs jsonb := '[]'::jsonb; out_slots text[];
  vrm text[]; vname text; placed boolean[];
begin
  if auth.uid() is null then raise exception 'non autenticato'; end if;
  select * into mo from mantra_modules where code = btrim(coalesce(p_module, '')) and active;
  if not found then
    return jsonb_build_object('ok', false, 'module', p_module, 'assign', '[]'::jsonb, 'slots', null,
      'errors', jsonb_build_array(format('modulo Mantra sconosciuto: %s', coalesce(p_module, '(vuoto)'))));
  end if;
  n := jsonb_array_length(mo.slots);
  if coalesce(array_length(p_players, 1), 0) <> n then
    return jsonb_build_object('ok', false, 'module', mo.code, 'assign', '[]'::jsonb, 'slots', null,
      'errors', jsonb_build_array(format('servono %s titolari, ne sono arrivati %s', n, coalesce(array_length(p_players, 1), 0))));
  end if;
  if (select count(distinct x) from unnest(p_players) x) <> n then
    return jsonb_build_object('ok', false, 'module', mo.code, 'assign', '[]'::jsonb, 'slots', null,
      'errors', jsonb_build_array('un giocatore compare due volte fra i titolari'));
  end if;

  -- ruoli ammessi da ogni slot, nell'ordine in cui il modulo li elenca
  for j in 1..n loop
    sr[j] := (select string_agg(t.value, '|' order by t.ord)
                from jsonb_array_elements_text(mo.slots->(j-1)->'roles') with ordinality t(value, ord));
  end loop;
  -- ruoli Mantra (normalizzati) e nome di ogni titolare; il nome serve solo a scrivere errori leggibili
  for i in 1..n loop
    select mantra_norm(p.role_mantra), p.name into vrm, vname from players p where p.id = p_players[i];
    if vname is null then
      return jsonb_build_object('ok', false, 'module', mo.code, 'assign', '[]'::jsonb, 'slots', null,
        'errors', jsonb_build_array(format('giocatore %s non presente nel listone', p_players[i])));
    end if;
    pm[i] := array_to_string(coalesce(vrm, '{}'::text[]), '|'); pn[i] := vname;
  end loop;

  -- adiacenze giocatore -> slot
  for i in 1..n loop
    row_adj := '[]'::jsonb;
    for j in 1..n loop
      if pm[i] <> '' and string_to_array(pm[i], '|') && string_to_array(sr[j], '|') then
        row_adj := row_adj || to_jsonb(j);
      end if;
    end loop;
    adj := adj || jsonb_build_array(row_adj);
  end loop;

  -- matching
  mt := array_fill(0, array[n]); placed := array_fill(false, array[n]);
  for i in 1..n loop
    sn := array_fill(false, array[n]);
    select * into res from public.mantra_augment(i, adj, mt, sn);
    mt := res.p_match;
    if res.p_ok then placed[i] := true; else ok := false; end if;
  end loop;

  -- esito
  out_slots := array_fill(null::text, array[n]);
  for j in 1..n loop
    if coalesce(mt[j], 0) > 0 then
      out_slots[mt[j]] := sr[j];
      assign := assign || jsonb_build_object('n', j, 'slot', sr[j], 'player_id', p_players[mt[j]], 'name', pn[mt[j]]);
    else
      errs := errs || to_jsonb(format('slot %s (%s) resta scoperto', j, replace(sr[j], '|', '/')));
    end if;
  end loop;
  for i in 1..n loop
    if not placed[i] then
      errs := errs || to_jsonb(format('%s (%s) non entra in nessuno slot libero del %s', pn[i],
        case when pm[i] = '' then 'senza ruoli Mantra' else replace(pm[i], '|', '/') end, mo.code));
    end if;
  end loop;
  return jsonb_build_object('ok', ok, 'module', mo.code, 'assign', assign,
    'slots', case when ok then to_jsonb(out_slots) else null end, 'errors', errs);
end $$;

-- ==================== D) SALVATAGGIO DELLA FORMAZIONE ====================

-- Salvataggio Mantra. Stessi controlli del Classic (membro, deadline, 11 titolari, panchina nei limiti, niente doppioni,
-- tutti in rosa), poi al posto del conteggio P/D/C/A c'e' il matching sugli slot. Scrive lineups.slots: e' quello che
-- permette a compute_matchday di sostituire per slot senza dover ricalcolare niente a giornata in corso.
create or replace function public.save_lineup_mantra(p_league uuid, p_matchday integer, p_module text,
  p_starters integer[], p_bench integer[])
returns jsonb language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; dl timestamptz; bmax integer; chk jsonb; sl text[]; msg text;
begin
  if not is_member(p_league) then raise exception 'non sei in questa lega'; end if;
  if league_mode(p_league) <> 'mantra' then raise exception 'questa lega non e'' in modalita'' Mantra'; end if;
  select * into l from leagues where id = p_league;
  select starts_at into dl from matchdays where season = l.season and number = p_matchday;
  if dl is not null and now() > dl then raise exception 'formazioni chiuse: la giornata % è iniziata', p_matchday; end if;
  if coalesce(array_length(p_starters, 1), 0) <> 11 then raise exception 'servono 11 titolari'; end if;
  bmax := coalesce((l.settings->>'bench_size')::int, 7);
  if coalesce(array_length(p_bench, 1), 0) > bmax then raise exception 'panchina: massimo % giocatori', bmax; end if;
  if (select count(distinct x) from unnest(p_starters || p_bench) x) <> array_length(p_starters || p_bench, 1) then
    raise exception 'giocatore ripetuto tra titolari e panchina'; end if;
  if exists (select 1 from unnest(p_starters || p_bench) x where not exists
      (select 1 from rosters where league_id = p_league and user_id = auth.uid() and player_id = x)) then
    raise exception 'un giocatore non è nella tua rosa'; end if;

  chk := mantra_check(p_module, p_starters);
  if not (chk->>'ok')::boolean then
    -- il perche' arriva all'utente: l'app deve poterlo mostrare cosi' com'e'
    select string_agg(t.value, '; ') into msg from jsonb_array_elements_text(chk->'errors') t(value);
    raise exception 'formazione Mantra non valida (%): %', p_module, coalesce(msg, 'motivo ignoto');
  end if;
  select array_agg(t.value order by t.ord) into sl
    from jsonb_array_elements_text(chk->'slots') with ordinality t(value, ord);

  insert into lineups(league_id, user_id, matchday, module, starters, bench, slots, submitted_at)
    values (p_league, auth.uid(), p_matchday, p_module, p_starters, coalesce(p_bench, '{}'), sl, now())
    on conflict (league_id, user_id, matchday) do update
      set module = excluded.module, starters = excluded.starters, bench = excluded.bench,
          slots = excluded.slots, submitted_at = now();
  return chk;
end $$;

-- save_lineup resta la porta d'ingresso unica per l'app: in una lega Classic il corpo e' quello del fix 005, riga per
-- riga; in una lega Mantra passa la palla a save_lineup_mantra. Cosi' fanta/app.js continua a funzionare com'e' e le
-- leghe esistenti non si accorgono di nulla. Nota: nel ramo Classic slots viene azzerato, cosi' una formazione salvata
-- in Mantra e poi risalvata in Classic non si porta dietro slot che non c'entrano piu'.
create or replace function public.save_lineup(p_league uuid, p_matchday integer, p_module text, p_starters integer[], p_bench integer[])
returns void language plpgsql security definer set search_path = public as $$
declare l leagues%rowtype; dl timestamptz; parts text[]; want jsonb; r text; n integer; bmax integer;
begin
  if not is_member(p_league) then raise exception 'non sei in questa lega'; end if;
  if league_mode(p_league) = 'mantra' then
    perform save_lineup_mantra(p_league, p_matchday, p_module, p_starters, p_bench);
    return;
  end if;
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
  insert into lineups(league_id, user_id, matchday, module, starters, bench, slots, submitted_at)
    values (p_league, auth.uid(), p_matchday, p_module, p_starters, coalesce(p_bench, '{}'), null, now())
    on conflict (league_id, user_id, matchday) do update
      set module = excluded.module, starters = excluded.starters, bench = excluded.bench,
          slots = null, submitted_at = now();
end $$;

-- ==================== E) COMPUTE_MATCHDAY: SOSTITUZIONI PER SLOT ====================

-- Chi puo' entrare al posto di chi. Se lo slot e' NULL (formazione Classic, cioe' tutte quelle salvate finora) vale la
-- regola di sempre: stesso ruolo Classic. Se lo slot c'e' (formazione Mantra) vale il Mantra: uno dei ruoli del
-- subentrante deve essere fra quelli ammessi dallo slot lasciato scoperto. Nessun altro ramo: e' la sola differenza.
create or replace function public.sub_eligible(p_slot text, p_bench integer, p_role text) returns boolean
language sql stable set search_path = public as $$
  select case when p_slot is null or p_slot = ''
              then coalesce((select p.role = p_role from players p where p.id = p_bench), false)
              else mantra_fits(p_bench, p_slot) end;
$$;

-- compute_matchday: copia della versione del FIX 012 (6 politico + fix 010 live + fix 011 modificatori). Rispetto al 012
-- cambiano SOLO: le variabili idx/slot, il contatore di posizione nel ciclo dei titolari, la riga che sceglie il
-- subentrante (sub_eligible al posto del confronto sul ruolo Classic) e il campo 'slot' nel dettaglio del giocatore.
-- Il calcolo dei punti e' identico: bonus, malus, modificatori, gol a soglie, fattore casa/trasferta, tutto invariato.
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
  idx integer; slot text;      -- fix 014: posizione del titolare e ruoli ammessi dal suo slot Mantra (NULL = Classic)
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
    def_v := '{}'; att_v := '{}'; mid_v := '{}'; gk_v := null; gk_clean := false; mid_avg := null; idx := 0;
    select * into lu from lineups where league_id = p_league and user_id = m.user_id and matchday = p_matchday;
    has_lu := found;
    if has_lu then
      foreach orig in array lu.starters loop
        idx := idx + 1;
        -- slot Mantra del titolare in posizione idx; se la formazione e' Classic (slots NULL) resta NULL
        slot := case when lu.slots is not null and coalesce(array_length(lu.slots, 1), 0) >= idx then lu.slots[idx] else null end;
        pid := orig; subid := null; pend := false;
        select role into r from players where id = pid;
        select voto, fantavoto, bonus, minutes into v, fv, b, mins from fv_of(p_league, l.season, p_matchday, pid);
        select exists(select 1 from player_ratings where season = l.season and matchday = p_matchday and player_id = pid) into played;
        if fv is null and not played and md_status is distinct from 'rated' then
          -- live (fix 012): partita non ancora giocata -> 6 politico, nessuna sostituzione
          pend := true; v := 6; fv := 6; b := '{}'::jsonb; mins := 0;
        elsif fv is null and subs < max_subs and lu.bench is not null then
          -- ha giocato senza voto (o giornata rated e non convocato): sostituzione dalla panchina.
          -- fix 014: nel Mantra il subentrante deve poter occupare lo SLOT rimasto scoperto, non il ruolo Classic.
          foreach bp in array lu.bench loop
            continue when bp = any(used) or not sub_eligible(slot, bp, r);
            select voto, fantavoto, bonus, minutes into bv, bfv, bb, bm from fv_of(p_league, l.season, p_matchday, bp);
            if bfv is not null then
              used := used || bp; subs := subs + 1; subid := bp; pid := bp; v := bv; fv := bfv; b := bb; mins := bm; exit;
            end if;
          end loop;
        end if;
        det := det || jsonb_build_object('player_id', orig, 'sub', subid, 'voto', v, 'fv', coalesce(fv, 0), 'role', r,
                                         'bonus', coalesce(b, '{}'::jsonb), 'min', coalesce(mins, 0), 'pending', pend,
                                         'slot', slot);
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
                                 'live', (md_status is distinct from 'rated'), 'mod_def_v', mdv,
                                 'modalita', case when lu.slots is not null then 'mantra' else 'classic' end))
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

-- ==================== F) RLS E GRANT ====================

-- Ruoli e moduli sono dati di gioco pubblici come il listone: lettura a tutti, scrittura a nessuno via API
-- (si correggono dall'SQL Editor, come il resto della configurazione).
alter table public.mantra_roles enable row level security;
alter table public.mantra_modules enable row level security;
drop policy if exists mantra_roles_read on public.mantra_roles;
create policy mantra_roles_read on public.mantra_roles for select to anon, authenticated using (true);
drop policy if exists mantra_modules_read on public.mantra_modules;
create policy mantra_modules_read on public.mantra_modules for select to anon, authenticated using (true);
grant select on public.mantra_roles, public.mantra_modules to anon, authenticated;

grant execute on function public.league_mode(uuid) to authenticated;
grant execute on function public.set_league_mode(uuid, text, boolean) to authenticated;
grant execute on function public.update_league_settings(uuid, jsonb) to authenticated;
grant execute on function public.mantra_norm(text[]) to anon, authenticated;
grant execute on function public.mantra_fits(integer, text) to anon, authenticated;
grant execute on function public.mantra_check(text, integer[]) to authenticated;
grant execute on function public.save_lineup_mantra(uuid, integer, text, integer[], integer[]) to authenticated;
grant execute on function public.save_lineup(uuid, integer, text, integer[], integer[]) to authenticated;
grant execute on function public.sub_eligible(text, integer, text) to authenticated;
-- mantra_augment e' l'interno dell'algoritmo: la usa mantra_check (security definer), non serve esporla.
revoke all on function public.mantra_augment(integer, jsonb, integer[], boolean[]) from public;
revoke all on function public.mantra_augment(integer, jsonb, integer[], boolean[]) from anon, authenticated;
-- compute_matchday resta com'era: il controllo di chi chiama e' dentro la funzione (admin di lega o service_role).
grant execute on function public.compute_matchday(uuid, integer) to authenticated;

-- ==================== G) VERIFICHE ====================
-- Da lanciare nell'SQL Editor dopo aver eseguito il file. In ordine:
--
-- 1) i moduli ci sono e hanno 11 slot ciascuno (attese: 17 righe, tutte con 11)
--    select code, jsonb_array_length(slots) as slot from public.mantra_modules order by ord;
--
-- 2) I RUOLI MANTRA SONO DAVVERO POPOLATI? (questa e' la domanda che decide se il Mantra e' giocabile oggi)
--    select count(*) filter (where coalesce(array_length(role_mantra,1),0) > 0) as con_mantra,
--           count(*) as attivi
--      from public.players where active;
--    Atteso: con_mantra ~= attivi (il listone ufficiale ha la colonna RM per tutti). Se con_mantra e' 0 o molto basso,
--    ripassare il listone:  py -X utf8 scripts/fanta_quotazioni.py <file Excel del listone>
--    Per vedere le sigle davvero presenti (devono essere quelle di mantra_roles):
--    select unnest(role_mantra) as rm, count(*) from public.players where active group by 1 order by 2 desc;
--    Le sigle fuori elenco si vedono cosi' (atteso: zero righe):
--    select id, name, role_mantra from public.players
--     where active and coalesce(array_length(role_mantra,1),0) > 0
--       and coalesce(array_length(public.mantra_norm(role_mantra),1),0) < array_length(role_mantra,1);
--
-- 3) nessuna lega e' cambiata (atteso: tutte 'classic', finche' non si usa set_league_mode)
--    select id, name, public.league_mode(id) from public.leagues;
--
-- 4) la validazione risponde. Con un utente loggato (mantra_check chiede auth.uid()), presi 11 id di una rosa:
--    select public.mantra_check('4-3-3', array[<11 id>]);
--    -> {"ok": true, "assign": [...], "slots": ["Por","Dd",...]}  oppure  ok:false con 'errors' che dice chi non entra.
--
-- 5) accendere il Mantra su una lega di prova e schierare:
--    select public.set_league_mode('<uuid lega>', 'mantra');
--    select public.save_lineup_mantra('<uuid lega>', 1, '3-4-2-1', array[<11 titolari>], array[<panchina>]);
--    select module, slots from public.lineups where league_id = '<uuid lega>' and matchday = 1;   -- slots valorizzato
--
-- 6) il Classic non si e' mosso: su una lega classic, salvare una formazione come sempre e controllare che
--    slots resti NULL, poi ricalcolare una giornata gia' chiusa e confrontare i totali con quelli di prima:
--    select user_id, total, goals from public.results where league_id = '<uuid lega classic>' and matchday = <n>;
--    select public.compute_matchday('<uuid lega classic>', <n>);
--    (gli stessi totali di prima: il calcolo dei punti non e' stato toccato)
