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

## 4. Il nodo "voti"
I voti editoriali (Gazzetta, Corriere, Fantacalcio.it) NON sono acquistabili via API. Il **voto FantaTB** sarà:
- **voto base** = rating API-Football (scala 1-10 stile SofaScore) riportato nella scala 4-8 italiana con formula trasparente;
- **bonus/malus** automatici da eventi reali: gol, assist, rigore segnato/sbagliato/parato, gol subito (portiere), ammonizione, espulsione, autogol, "senza voto" sotto i minuti minimi;
- **override manuale** dell'admin di lega, per chi vuole usare i voti del proprio giornale.
Va detto chiaramente agli utenti: non coincidono con i voti Gazzetta.

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

## 8. Cose che deve fare l'utente (non può farle Claude)
1. Creare il progetto **Supabase** (supabase.com, login GitHub) e salvare URL + anon key + service key in `supabase_keys.txt` (gitignorato).
2. Attivare **API-Football** piano Pro (dashboard.api-football.com) e salvare la chiave in `apifootball_key.txt` (gitignorato).
3. Aggiungere le due chiavi come secret su GitHub Actions.
Fatto questo, Claude scrive schema, frontend e cron.
