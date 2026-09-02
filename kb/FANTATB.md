# FantaTB — piano di prodotto (bozza 2026-09-02)

> Sezione fantacalcio di TransferBeat. Italia (Serie A) per il 2026-27, architettura replicabile su UK/ES.
> Non più "costo zero": si accettano costi per dati e backend. Nome: **FantaTB**.

## 1. Cosa deve fare (perimetro richiesto)
1. **Asta**: creazione lega, squadre partecipanti, listone, asta live (banditore + rilanci), rose salvate.
2. **Gestione lega**: accessi con email+password per ogni partecipante; chi crea la lega è **admin** e
   imposta le regole (Classic/Mantra, modificatori, crediti, numero rose, bonus/malus custom);
   calendario partite di lega (round robin, andata/ritorno); schieramento formazione con deadline;
   calcolo punteggio delle squadre schierate; classifica.

## 2. Stack proposto
| Strato | Scelta | Perché |
|---|---|---|
| Frontend | HTML/JS statico in `fanta/` dentro il repo, deploy Vercel come il resto del sito | nessun build step, stessa pipeline, stesso dominio (`transferbeat.com/fanta/`) |
| Backend | **Supabase** (Postgres + Auth + Realtime + Row Level Security) | login pronto, permessi per lega a livello DB, canale realtime per l'asta live |
| Dati calcio | **API-Football** (api-sports.io), piano Pro | rose, ruoli, calendario, formazioni, eventi (gol, assist, cartellini, rigori), minuti e **rating** per giocatore-partita |
| Motore voti/punteggi | script Python su **GitHub Actions** (infra già esistente) che legge API-Football e scrive su Supabase | riusa cron, segreti e pattern già collaudati del sito |

Alternative scartate: Cloudflare Workers+D1 (auth da costruire a mano), Firebase (query di punteggio più scomode senza SQL).

## 3. Costi stimati (mensili)
| Voce | Costo | Note |
|---|---|---|
| API-Football Pro | ~19 USD | 7.500 richieste/giorno; per la sola Serie A ne servono poche centinaia |
| Supabase | 0 in test → 25 USD (Pro) al lancio pubblico | il Free basta per la lega da 8 di quest'anno |
| Vercel, GitHub Actions, dominio | 0 | già in uso |
| **Totale** | **~20 USD/mese in test, ~45 USD/mese a regime** | |

## 4. Il nodo "voti" (verificato 2026-09-02)
I voti editoriali NON sono in vendita self-service con chiave API e listino. Esistono però in **licenza B2B**:
- **Atlanticmoon / Fantacalcio-Online (FCO)**: unico "Fantacalcio as a Service" italiano. Offre API,
  white label web+app, motore di calcolo, listone, multi-campionato. Fonti voti 2026/27 sul loro
  prodotto: **Fantacalcio.it** (ufficiale), **Corriere dello Sport (Roma)**, **Tuttosport (Torino)**,
  più i voti statistici propri. Partner: RCS/Gazzetta (Magic Leghe dal 2017), DAZN, Fiorentina.
  Nessun prezzo pubblico: contatto via form o tel. +39 011 2076222. https://www.atlanticmoon.com/fantacalcio/faas-fantacalcio-as-a-service/
- **Gazzetta dello Sport**: dal 2026/27 ha **ritirato la licenza** dei suoi voti alle piattaforme terze
  ("non ne abbiamo più i diritti di pubblicazione", FCO). Non contarci.
- **Fantacalcio.it (Quadronica, 51% Lega Serie A da feb 2026)**: i T&C vietano scraping e riuso senza
  autorizzazione scritta. Leghe Fantacalcio è la LORO piattaforma, non un'API per terzi. Una licenza
  diretta va negoziata con loro, oppure passa da FCO.
- **FantaMaster, FantaLab, Kickest**: voti **statistici** propri (algoritmi su dati Opta o simili), non redazionali.

**DECISIONE 2026-09-02: voto statistico puro.** Niente trattative per ora; una redazione FantaTB
(base statistica + ritocco umano) resta un'opzione di medio periodo. Vedi §9 per la formula.

## 5. Mantra: attenzione
API-Football dà solo 4 ruoli (Por, Dif, Cen, Att). I ruoli Mantra (Dd, Ds, Dc, E, M, C, W, T, A, Pc) vanno
assegnati a mano (~600 giocatori). Si parte **Classic**; Mantra in fase successiva con una tabella
ruoli editabile dall'admin FantaTB. Stesso discorso per le **quotazioni**: quelle ufficiali sono
copyright, le nostre saranno calcolate (minuti, rating, gol/assist stagione precedente) e ritoccabili.

## 6. Schema dati (bozza)
- `players` (id_api, nome, squadra, ruolo_classic, ruolo_mantra, quotazione, attivo)
- `leagues` (id, nome, admin_uid, regole JSON: tipo, crediti, n_rose P/D/C/A, modificatori, bonus/malus, deadline)
- `league_members` (league_id, uid, nome_squadra, ruolo: admin/member) · `league_invites` (codice invito)
- `auctions` (league_id, stato, turno, giocatore_in_asta, offerta_corrente, offerente) + `auction_bids`
- `rosters` (league_id, member, player_id, prezzo)
- `fixtures_league` (giornata, casa, ospite) · `lineups` (giornata, member, titolari, panchina, modulo)
- `matchdays` (giornata Serie A, data inizio, stato) · `player_ratings` (giornata, player_id, voto, bonus/malus, fantavoto)
- `results` (giornata, member, totale, gol, punti)
RLS: ogni riga di lega visibile solo ai membri; scrittura regole solo all'admin.

## 7. Fasi
- **Fase 1 (settimana 1)**: progetto Supabase, schema, auth, crea lega + inviti, listone FantaTB da API-Football, **asta live** con rose salvate. Obiettivo: fare l'asta della lega da 8 con FantaTB.
- **Fase 2 (settimane 2-3)**: calendario lega, schieramento formazioni con deadline, regole Classic (moduli, modificatore difesa, panchina/sostituzioni automatiche).
- **Fase 3 (settimane 3-4)**: cron voti da API-Football, calcolo punteggi e classifica, pagina voti pubblica.
- **Fase 4**: Mantra, scambi/mercato di riparazione, statistiche, poi UK/ES (API-Football copre PL e LaLiga con lo stesso schema).

## 7b. Abbonamenti attivi
- **API-Football Pro, mensile, attivato il 2026-09-02**: scade intorno al **2026-10-02**. Va rinnovato o i voti si fermano.
- Supabase: piano Free.

## 8. Cose che deve fare l'utente (non può farle Claude)
1. Creare il progetto **Supabase** (supabase.com, login GitHub) e salvare URL + anon key + service key in `supabase_keys.txt` (gitignorato).
2. Attivare **API-Football** piano Pro (dashboard.api-football.com) e salvare la chiave in `apifootball_key.txt` (gitignorato).
3. Aggiungere le due chiavi come secret su GitHub Actions.
Fatto questo, Claude scrive schema, frontend e cron.

## 9. Voto FantaTB: formula (trasparente, ritoccabile)
Fonte: API-Football, endpoint `fixtures/players` (rating, minuti, gol, assist, cartellini, rigori,
gol subiti/parate per i portieri) e `fixtures/events` (autogol). Script: `scripts/fanta_voti.py`.
- **Senza voto (s.v.)** se minuti < 15. Il giocatore non entra nel calcolo (sostituzione automatica dalla panchina).
- **Voto base** = rating API-Football − 0,8, arrotondato al mezzo punto, limitato tra 4 e 8,5.
  (Il rating medio di un titolare è ~6,8: la traslazione lo porta sul 6 italiano.) Se il rating manca ma
  i minuti sono ≥ 15: voto 6.
- **Bonus/malus di default** (Classic, override nelle regole di lega): gol +3 · assist +1 · rigore
  sbagliato −3 · rigore parato +3 · gol subito (portiere) −1 · autogol −2 · ammonizione −0,5 · espulsione −1.
  Il rigore segnato è già un gol. Il "gol vittoria/pareggio" è opzionale e spento di default.
- **Fantavoto** = voto base + bonus − malus.
- Il rating grezzo, i minuti e gli eventi restano salvati in `player_ratings.raw` per ricalcoli futuri.

## 10. Quotazioni FantaTB: formula
Script: `scripts/fanta_players.py`. Per ogni giocatore delle 20 rose Serie A (endpoint `players/squads`),
statistiche della stagione precedente (`players?league=135&season=2025`) e, se assenti, della corrente.
- base per ruolo: P 1 · D 1 · C 1 · A 2
- + presenze/38 × (P 8 · D 10 · C 12 · A 14)
- + gol × (P 0 · D 3 · C 2 · A 1,2) + assist × (D 1 · C 1 · A 0,8)
- + (rating medio − 6,5) × 10 se rating > 6,5 (con almeno 10 presenze)
- portieri: + clean sheet stimati (presenze × 0,3 se gol subiti/presenza < 1)
- limite 1..60, arrotondato all'intero. Ritoccabile a mano nella tabella `players.price`.
Ruoli Classic dalla posizione API (Goalkeeper→P, Defender→D, Midfielder→C, Attacker→A); ruoli Mantra
vuoti (`role_mantra`), da assegnare a mano in fase 4.

## 11. Stato lavori (aggiornare)
- 2026-09-02: fase 1 e fase 2 COMPLETE e testate sul progetto Supabase reale `transferbeat-fantatb`
  (ref gtmvoxowayecsalfuobc). Schema eseguito nell'SQL Editor: `schema.sql` + `fix-001` + `fix-002` + `fix-003`
  (le correzioni sono già integrate in `schema.sql` per installazioni nuove).
  Test automatici superati: creazione lega, inviti, asta con controlli crediti/slot, aggiudicazione, rilascio;
  calendario con riposo, formazioni validate, calcolo con sostituzione, modificatore difesa, gol, punti scontri.
- Chiavi: `supabase_keys.txt` presente in locale (cartella principale e worktree). `fanta/config.js` collegato.
- MANCANO: chiave API-Football (`apifootball_key.txt`) per listone e voti reali; i 3 secret su GitHub Actions
  (APIFOOTBALL_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY); merge della PR #1 su main per pubblicare `/fanta/`.
- Prossimi passi: fase 3 = primo listone reale + prima giornata di voti dal cron; poi modifica regole
  post-creazione, correzione voti dall'interfaccia admin, link FantaTB nel menu del sito.
