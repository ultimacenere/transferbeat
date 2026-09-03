# FantaTB — KB operativa
*Sezione fantacalcio di TransferBeat. Aggiornata: 2026-09-03. Leggere PRIMA di toccare qualsiasi cosa in `fanta/` o `scripts/fanta_*.py`.*

> **Stato: ONLINE su https://transferbeat.com/fanta/** dal 2026-09-02 sera. Serie A 2026-27, regole Classic.
> Pubblico ridotto (lega dell'utente + amici) per la stagione di test; monetizzazione da valutare dopo.
> Il database è vuoto di leghe (lega test e bot eliminati): pronto per la lega vera e per le demo.

## 0. In 60 secondi
- **Cos'è**: leghe private con login, asta live in tempo reale, rose, formazioni con deadline, calendario di lega,
  calcolo punteggi con voto statistico FantaTB, classifica, regole configurabili dall'admin, listone e voti pubblici.
- **Stack**: frontend statico in `fanta/` (HTML/CSS/JS, nessun build, deploy Vercel col resto del sito) ·
  **Supabase** (Postgres + Auth + Realtime + RLS, progetto `transferbeat-fantatb`, ref `gtmvoxowayecsalfuobc`) ·
  **API-Football** piano Pro (rose, calendario, tabellini, rating, infortuni) · script Python + GitHub Actions per voti e listone.
- **Voti**: statistici, calcolati da noi (§5). Nessuna licenza redazionale (§9). L'utente valuta una redazione propria in futuro.
- **Chi decide**: l'utente (Pierluigi / account app "Picchio", email pierluigicella85@gmail.com) è admin della propria lega.

## 1. Mappa dei file
| Percorso | Ruolo |
|---|---|
| `fanta/index.html` | pagina unica: viste auth, home leghe, lega (schede), listone, voti, come funziona |
| `fanta/app.js` | tutta la logica (vanilla JS + supabase-js via CDN). Sezioni: regole/form, home, lega, asta, schiera, calendario, classifica/risultati, avvio |
| `fanta/style.css` | stile, coerente con la home del sito (verde #0a9d57), più campo, panchina, risultati, form regole |
| `fanta/config.js` | URL Supabase e **anon key** (pubblica per design: i permessi veri sono nelle RLS). Committato. |
| `fanta/supabase/schema.sql` | schema completo per installazioni nuove = base + fix-001..007 accodati (idempotente) |
| `fanta/supabase/fix-00N-*.sql` | i singoli blocchi già eseguiti sul progetto reale (storico) |
| `scripts/fanta_common.py` | chiavi, chiamate API-Football (paginazione, retry 429), upsert/get/rpc Supabase con service key |
| `scripts/fanta_players.py` | listone: rose attuali + statistiche stagione precedente → quotazione (§6) → `players` + `data/fanta/listone.json` |
| `scripts/fanta_voti.py` | voti di una giornata (§5) → `player_ratings`, `matchdays`, poi `compute_all_leagues` → `data/fanta/voti-NN.json` |
| `scripts/fanta_titolari.py` | indice titolarità + infortuni con rientro (§7) → `player_status` → `data/fanta/titolari-NN.json` |
| `scripts/fanta_demo.py` | strumento demo/test: bot, rose casuali, formazioni, pulizia, eliminazione lega (§11) |
| `.github/workflows/fanta.yml` | cron voti+titolarità (sere di campionato e mattine seguenti) e listone su richiesta (`task=listone`) |
| `data/fanta/*.json` | copie statiche dei dati generati (committate dal cron) |

## 2. Account, chiavi, costi
- **Supabase**: progetto `transferbeat-fantatb`, piano Free. Dashboard: supabase.com. URL `https://gtmvoxowayecsalfuobc.supabase.co`.
  Auth email+password con **conferma email disattivata** (per il test). Site URL impostato su transferbeat.com/fanta/.
- **API-Football** (dashboard.api-football.com): **piano Pro mensile attivato il 2026-09-02, scade ~2026-10-02**.
  7.500 richieste/giorno. Consumo reale: listone ~90, voti ~22/giornata, titolarità 1-80 (dipende dagli infortuni da verificare).
  **Il rinnovo va ricordato all'utente a fine settembre**, altrimenti voti e titolarità si fermano.
- **File locali (gitignorati, mai nel repo)**, nella cartella principale `G:\Il mio Drive\Calciomercato\` e copiati nel worktree:
  `supabase_keys.txt` (3 righe: URL, anon key, service key) · `apifootball_key.txt` (1 riga) · `github_token.txt`.
  Gli script cercano i file nella radice del repo da cui girano (`ROOT`), oppure le variabili `SUPABASE_URL`,
  `SUPABASE_SERVICE_KEY`, `APIFOOTBALL_KEY`.
- **Secret GitHub Actions**: `APIFOOTBALL_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`. **NON ANCORA INSERITI** (l'utente li
  mette "in un secondo momento"): finché mancano il workflow `fanta.yml` fallisce e i voti si lanciano a mano (§8).
- La service key è passata in chat il 2026-09-02: prima del lancio pubblico conviene rigenerarla (Project Settings → API Keys)
  e aggiornare file locale e secret.
- Costi: ~19 USD/mese API-Football; Supabase 0 (Free) → 25 USD se serve il Pro; Vercel/Actions/dominio 0.

## 3. Database (Supabase / Postgres)
**Tabelle** (tutte con RLS):
- `profiles` (id = auth.users.id, username) — creata dal trigger `handle_new_user` alla registrazione.
- `players` (id API-Football, name, team, team_id, role P/D/C/A, role_mantra[], price, active, stats jsonb). Lettura pubblica (anche anon).
  `active=false` = ha giocato ma non è più nelle rose (ceduto): serve per mostrare i voti, non compare in listone/asta.
- `leagues` (id, name, admin_id, invite_code 8 hex, season, settings jsonb) · `league_members` (league_id, user_id, team_name, role admin/member, credits, call_order).
- `auctions` (una riga per lega: status idle/live/closed, player_id, current_bid, bidder_id, ends_at, timer_seconds) · `auction_bids`.
- `rosters` (league_id, player_id, user_id, price) — PK (league_id, player_id): un giocatore per lega.
- `matchdays` (season, number, starts_at, ends_at, status scheduled/live/finished/rated) — date sincronizzate da `fanta_voti.py`.
- `league_fixtures` (league_id, round, matchday, home_id, away_id null=riposo, home/away_goals, home/away_points).
- `lineups` (league_id, user_id, matchday, module, starters int[11], bench int[]) — scrittura SOLO via RPC `save_lineup`.
- `player_ratings` (season, matchday, player_id, minutes, voto null=s.v., bonus jsonb, fantavoto, source, raw jsonb). Lettura pubblica.
- `rating_overrides` (league_id, matchday, player_id, voto, bonus) — correzioni manuali dell'admin (solo via API per ora, niente UI).
- `results` (league_id, user_id, matchday, total, goals, points, detail jsonb: players[], bench[], extras[], base, mid_avg, lineup).
- `player_status` (season, matchday, player_id, prob 0-100, reason, injury, back_at). Lettura pubblica.

**Funzioni RPC** (security definer: le regole si applicano lato server, il browser non può barare):
`create_league(name, team, settings)` · `join_league(code, team)` · `update_league_settings(league, settings)` (admin) ·
`start_auction(league, player, start)` (admin) · `place_bid(league, amount)` (controlli: asta live, rilancio > offerta, non su se stessi,
slot del ruolo libero, deve restare 1 credito per ogni altro slot vuoto; il timer si allunga a ogni rilancio) · `close_auction(league)`
(admin: assegna al miglior offerente e scala i crediti) · `assign_player` / `release_player` (admin, con rimborso) ·
`save_lineup(league, matchday, module, starters, bench)` (membro: 11 titolari coerenti col modulo, tutti in rosa, panchina ≤ bench_size,
prima di `matchdays.starts_at`) · `generate_calendar(league, start, gironi)` (admin: Berger, riposo con squadre dispari, cancella risultati) ·
`compute_matchday(league, matchday)` (admin o service role) · `compute_all_leagues(matchday)` (solo service role, usata dal cron) ·
helper `fv_of(league, season, matchday, player) → voto, fantavoto, bonus, minutes` (con override e pesi di lega; ridefinita con 4 output
dal fix-006 dopo `drop function`), `mod_table`, `goals_of`, `is_member`, `is_admin`, `slots_left`.

**RLS in sintesi**: righe di lega visibili solo ai membri (`is_member`); regole e calendario scrivibili solo dall'admin; players,
matchdays, player_ratings, player_status leggibili da tutti; formazioni scrivibili solo via RPC (policy di insert/update rimosse).
**Realtime** attivo su auctions, auction_bids, rosters, league_members (il frontend ha anche un polling di sicurezza ogni 7 s).

**Come si applicano modifiche SQL** (l'unica cosa che Claude NON può fare da solo):
1. L'utente apre SQL Editor su Supabase, **svuota l'editor (Ctrl+A, Canc) o apre "New query"**: mai accodare blocchi ai precedenti
   (il 2026-09-02 l'editor era arrivato a 737 righe e rieseguiva vecchie definizioni → errore 42P13 su fv_of).
2. Incolla il blocco, Run, atteso "Success. No rows returned". Se errore, incollarlo in chat.
3. Le funzioni con parametri OUT non si possono ridefinire con `create or replace`: serve `drop function ... cascade` prima (fatto per `fv_of` nel fix-006).
4. Ogni nuovo blocco va salvato come `fanta/supabase/fix-00N-*.sql` E accodato a `schema.sql`.

**Vincoli noti dello schema**: `league_fixtures.home_id/away_id` e `results.user_id` referenziano `auth.users` senza cascade →
per eliminare un utente bisogna prima eliminare la lega o le sue righe (lo fa `fanta_demo.py elimina/pulisci`).
`league_members` non ha FK verso `profiles`: i nomi utente si caricano con una seconda query (`attachProfiles`), non con l'embed PostgREST.

## 4. Regole di lega (`leagues.settings`) e motore di calcolo
Default (`DEFAULT_SETTINGS` in app.js, stessi default nelle funzioni SQL): `type classic` · `phase asta|campionato` · `credits 500` ·
`max_teams 8` · `slots {P3,D8,C8,A6}` · `timer 20` s · `max_subs 3` · `bench_size 7` · `goal_base 66` · `goal_step 6` ·
`mod_difesa true` · `mod_centrocampo false` · `mod_attacco false` · `bonus_casa 0` · `bonus_trasferta 0` ·
`bonus {gol 3, assist 1, rig_sbagliato -3, rig_parato 3, gol_subito -1, autogol -2, amm -0.5, esp -1, porta_inviolata 0}`.
Tutto impostabile alla creazione e modificabile dall'admin nella scheda Regole (form condiviso `settingsFormHtml/readSettingsForm`).
La **fase**: in `asta` la scheda Asta è visibile; "Chiudi l'asta e inizia il campionato" la nasconde (riapribile).

`compute_matchday` per ogni squadra: fantavoto dei titolari (`fv_of`: voto + Σ bonus×peso di lega, con `rating_overrides`);
**senza voto → entra il primo panchinaro dello stesso ruolo nell'ordine di panchina**, fino a `max_subs`; s.v. senza sostituto vale 0;
**porta inviolata** (+peso se il portiere ha ≥60' e 0 gol subiti); **modificatore difesa** (media di portiere + 3 migliori difensori,
solo con ≥4 difensori schierati, tabella ≥6→+1, 6.25→+2, 6.5→+3, 6.75→+4, 7→+5, 7.25→+6); **modificatore attacco** (media voto
attaccanti, ≥2, stessa tabella; definizione FantaTB); poi negli scontri **modificatore centrocampo** (differenza tra le MEDIE voto dei
centrocampisti delle due squadre, ≥3 per parte: 0.25→+1, 0.5→+2, 0.75→+3, 1→+4, 1.5→+5, 2→+6 a chi ha la media più alta; definizione
FantaTB, la media e non la somma per non premiare i moduli a 5 centrocampisti); **fattore casa/trasferta** (solo con formazione inviata);
**gol** = 1 al `goal_base`, +1 ogni `goal_step`; punti 3/1/0. **Le voci dei modificatori attivi compaiono sempre nel dettaglio, anche a 0**
(richiesta dell'utente per allineare le due colonne). Il riposo prende i fantapunti ma non punti. Tutto finisce in `results.detail`
e in `league_fixtures`. Le regole valgono dai calcoli successivi: per il passato → "Ricalcola" in Calendario.

## 5. Voto FantaTB (statistico)
Fonte API-Football `fixtures/players` (rating, minuti, gol, assist, cartellini, rigori, gol subiti) + `fixtures/events` (autogol).
- **s.v.** se minuti < 15. **Voto base** = rating − 0,8 arrotondato al mezzo punto, tra 4 e 8,5; senza rating ma ≥15' → 6.
- Bonus/malus registrati per giocatore in `player_ratings.bonus` (gol, assist, rig_sbagliato, rig_parato (portieri), gol_subito (portieri),
  autogol, amm, esp); il fantavoto in tabella usa i pesi di default, quello di lega viene ricalcolato da `fv_of` con i pesi della lega.
- Verificato sulla giornata 2: media voto 6,06, scala 5–7,5, 289 con voto su 483 righe. Non coincidono con i voti dei giornali: è detto
  nel footer e nella pagina "Come funziona".
- `fanta_voti.py [giornata]`: senza argomento prende l'ultima giornata con partite finite; sincronizza le date di TUTTE le giornate in
  `matchdays` (senza toccare lo status); deduplica i tabellini; i giocatori non in listone vengono aggiunti come `active=false`;
  a giornata completa (`rated`) chiama `compute_all_leagues`.

## 6. Quotazioni FantaTB (`fanta_players.py`)
Rose attuali (`players/squads`, 20 squadre) + statistiche stagione precedente (`players?league=135&season=2025`), fallback stagione corrente.
Formula: base per ruolo (P1 D1 C1 A2) + presenze/38 × (P8 D10 C12 A14) + gol × (D3 C2 A1.2) + assist × (D1 C1 A0.8) +
(rating medio − 6,5) × 10 se >6,5 con ≥10 presenze; portieri + presenze × 0,3 se <1 gol subito a partita; limite 1..60.
Esito 2026-09-02: 651 giocatori, prezzi 1–51 (Dimarco 51, N. Paz 50, Lautaro 44). Doppioni tra rose rimossi (tenuta la prima).
Ritoccabile a mano in `players.price`. Ruoli Mantra vuoti.

## 7. Indice di titolarità (`fanta_titolari.py`, tabella `player_status`)
Per la prossima giornata (ultima `rated` + 1). Da `player_ratings` delle ultime 3 giornate: 90% se titolare (≥60') in tutte;
altrimenti 15 + 25×titolare + 5×subentrato (5..95); mai in campo 10%; mai convocato 20%; espulso nell'ultima giornata 0% "squalifica".
Infortuni/squalifiche da API-Football `/injuries` (voci delle prossime partite + quelle dell'ultima giornata confermate da `/sidelined`,
che dà anche la data di rientro stimata → "rientro ~N sett."). Frontend: percentuale colorata (≥70 verde, 40-69 ambra, <40 rossa) e croce
rossa ✚ con tipo infortunio in Schiera e Risultati. **Limite**: l'API popola gli infortuni a ridosso della giornata; a metà settimana
la lista è quasi vuota. Le notizie/probabili formazioni (LLM) per affinare la % sono un'evoluzione prevista, non fatta.

## 8. Cron e operazioni ricorrenti
- `fanta.yml`: schedule `30 21 * * 6,0,1,2,3,4` e `0 7 * * 1,2,5` (UTC) → voti + titolarità; `workflow_dispatch` con `task=listone|voti`
  e `matchday`. Committa `data/fanta`. **Inattivo finché mancano i secret** (§2).
- **Lancio manuale** (dal worktree, cartella `scripts`, con `PYTHONIOENCODING=utf-8`): `py fanta_voti.py` (o `py fanta_voti.py N`),
  poi `py fanta_titolari.py`. Listone: `py fanta_players.py` (rifarlo dopo il mercato di gennaio; i prezzi cambiano solo se rilanciato).
- Ogni script stampa il numero di chiamate API usate.

## 9. Decisioni prese e perché (non riaprire senza motivo)
- **Voto statistico puro** (2026-09-02). I voti redazionali non hanno API self-service: Atlanticmoon/Fantacalcio-Online è l'unico
  "Fantacalcio as a Service" (Fantacalcio.it, Corriere dello Sport, Tuttosport in licenza; contatto solo via form/telefono);
  la Gazzetta ha ritirato le licenze dal 2026/27; Fantacalcio.it (51% Lega Serie A) vieta scraping. L'utente non crede all'accesso
  API di Atlanticmoon e preferisce valutare una **redazione propria** più avanti. FantaMaster/FantaLab/Kickest usano voti statistici.
- **Nome FantaTB**, non "Fantacalcio" (marchio registrato). Footer: "Non affiliato a Fantacalcio®".
- **Classic prima, Mantra dopo**: i ruoli Mantra non esistono in nessuna API (assegnazione manuale ~650 giocatori).
- **Formazioni visibili prima della deadline** nella scheda Risultati (giornata in corso): scelta esplicita dell'utente per vedere
  l'avversario. Nel fantacalcio classico restano nascoste: proposta un'opzione di lega, non ancora fatta.
- **Modificatore centrocampo sulle medie** (non sulle somme), attacco con la tabella della difesa: definizioni FantaTB, scritte in Regole.
- **Nessun account social/OAuth, nessun dato personale oltre email**: niente GDPR extra in fase di test.

## 10. Frontend: cosa c'è e come funziona
Viste: auth (login/registrazione) · **Le mie leghe** (lista, crea lega con form regole completo, unisciti con codice) · **Lega** con schede
dinamiche (`renderTabs`): Asta (solo in fase asta) · Schiera · Classifica · Calendario · Risultati · Regole · Partecipanti (tabella + rose).
- **Asta**: banditore = admin (cerca giocatore, base, apri); tutti rilanciano +1/+5/+10 o importo; timer che si riavvia a ogni rilancio,
  chiusura automatica dal browser dell'admin allo scadere; ultime offerte; crediti e slot liberi per squadra. Filtro e selezione del
  banditore sopravvivono agli aggiornamenti (`picker`, `auctionSig`: la scheda si ridisegna solo se cambiano i dati).
- **Schiera**: giornata e modulo (7 moduli), mezzo campo con slot per ruolo (A/C/D/P dall'alto), clic sulla rosa → campo se c'è posto
  nel ruolo, altrimenti panchina; clic in campo/panchina per togliere; panchina a slot numerati sotto il campo con frecce ◀▶; Svuota;
  deadline e stato; formazioni inviate dagli altri (solo "inviata/non inviata"); % titolarità e croce infortuni accanto ai nomi.
  Dati in cache (`S.luData`) e scroll conservato a ogni clic.
- **Calendario**: admin genera (prima giornata di Serie A, gironi) e calcola/ricalcola per turno; risultati e fantapunti.
- **Risultati**: menu con giornate calcolate + giornata in corso; partita per partita, punteggio grande, due schede allineate riga per riga
  (11 titolari con righe vuote se mancano, voci extra unione delle due squadre, panchina pareggiata), colonne V/FV, emoji ⚽👟🟨🟥🥅🙈❌🧤,
  🔁 per i subentrati, Totale parziale, extra, Totale. Giornata non calcolata → formazioni schierate finora.
- **Classifica**: Pt, G, V, N, P, GF, GS, fantapunti.
- **Listone** e **Voti** sono pubblici (senza login). "Come funziona" spiega voto e regole.
- **Promozione (2026-09-03)**: landing `fantatb.html` (root, it/en/es, punti forti + CTA "Crea la tua lega ora" → `fanta/#crea`,
  che nell'app porta al form di creazione o al login) e `fanta/promo.js`, incluso da home, board, campionati, fonti e da tutte le
  pagine articolo (template in `render_articles.py`): banner in testata sotto il menu (chiudibile per la sessione) e due banner
  laterali fissi visibili sopra 1540 px. Palette "sgargiante" richiesta dall'utente: fucsia #ff2e88 → arancio #ff7a1a → giallo
  #ffd400, bottoni blu notte #1b1140. Lo script non si carica dentro `/fanta/`.
- Login condiviso tra le finestre dello stesso browser (localStorage): per due account insieme serve incognito/altro browser/telefono.

## 11. Strumento demo (`py scripts/fanta_demo.py <comando> <CODICE_INVITO> ...`, dalla cartella scripts)
`bots CODICE [n]` crea/iscrive n bot (`botN@fantatb.test` / `fantatb-botN`, squadre "Real Marzapane", "Atletico Divano", …) ·
`rose CODICE` riempie le rose di tutte le squadre con giocatori casuali (slot e crediti rispettati) · `formazioni CODICE G [tutti]`
formazioni dei bot (o di tutti) per la giornata G (i più cari per ruolo, modulo casuale, panchina ≤ bench_size) ·
`pulisci CODICE` toglie bot, rose, formazioni, calendario, risultati e riporta l'admin ai crediti pieni · `elimina CODICE` cancella la lega.
Usa la service key: bypassa deadline e regole → solo per prove. La sera del 2026-09-02 l'utente presenta il progetto a un amico:
Claude esegue questi comandi a richiesta man mano che l'utente avanza (crea lega → bots → asta o rose → calendario → formazioni → calcola).

## 12. Regole operative per Claude su FantaTB
- Comandi Bash oltre ~8k caratteri vengono troncati: file lunghi a blocchi, poi `node --check fanta/app.js` e `py -m py_compile`.
- `git push origin` via https può restare appeso o essere bloccato: pubblicare con `bash scripts/pubblica.sh` (push di HEAD su **main**,
  quindi deploy immediato) oppure push col token nell'URL. Prima di pubblicare: `git fetch` + merge di `origin/main` (i cron committano spesso).
- Test end-to-end senza toccare l'utente: script Python con utenti temporanei via `/auth/v1/admin/users` e RPC con il loro JWT
  (vedi gli smoke test del 2026-09-02); pulire sempre alla fine. `fanta_demo.py` copre i casi ricorrenti.
- Dopo ogni modifica al frontend dire all'utente **Ctrl+F5** (cache del browser).
- Il cron `update.yml` del sito non tocca `fanta/`; `render_articles.py` rigenera `sitemap.xml` senza `/fanta/` (da aggiungere).

## 13. PENDING (in ordine di priorità)
1. **Secret GitHub Actions** (`APIFOOTBALL_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`) → cron voti/titolarità automatico. Finché mancano: lancio manuale (§8).
2. **Rinnovo API-Football** entro il 2026-10-02 (§2).
3. **Asta vera della lega dell'utente** (8 squadre): prima `pulisci`/`elimina` eventuali leghe demo; Supabase Free basta.
4. Correzione voti dall'interfaccia admin (`rating_overrides` esiste, manca la UI).
5. Probabili formazioni dalle notizie (LLM, stesso motore degli articoli) per affinare la % titolarità; alert deadline formazioni.
6. Opzione di lega "formazioni nascoste fino alla deadline".
7. `/fanta/` in `sitemap.xml`; meta/SEO della pagina; pagina pubblica "classifica di lega" condivisibile.
8. Scambi/mercato di riparazione tra squadre; svincoli con rimborso parziale.
9. Mantra (ruoli manuali + moduli Mantra); poi Premier/Liga (API-Football copre entrambe con lo stesso schema).
10. Rigenerare la service key Supabase prima dell'apertura al pubblico; valutare Supabase Pro se le leghe crescono.
11. Listone da rifare dopo il mercato di gennaio (`fanta_players.py`, o `task=listone` dal workflow).
