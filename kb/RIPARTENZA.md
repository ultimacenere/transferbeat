# TransferBeat — KB di RIPARTENZA
*Come essere operativi al 100% su QUALSIASI computer, e come funziona tutto. Aggiornata: 2026-09-02.*

> **Stato attuale del sito: CAMPIONATI E COPPE.** Il mercato estivo europeo ha chiuso il 2026-09-02.
> La macchina del calciomercato **non è stata cancellata, è sospesa**: vocabolari, prompt, feed e
> modello di estrazione sono tutti conservati. Si riaccende in mezz'ora seguendo la **§7**.
> Prossime riaperture: **finestra invernale (gennaio)** e **fine campionato (giugno)**.

## 0. La verità fondamentale
**Il sito NON dipende da nessun computer.** Fonte di verità: GitHub (`ultimacenere/transferbeat`).
Vercel pubblica da lì (dominio transferbeat.com via Register.it). I cron girano su GitHub Actions,
innescati da cron-job.org **e da una pianificazione interna a `update.yml`** (ridondanza utile: se
cron-job.org si ferma, l'aggiornamento dati parte comunque). **A PC spento il sito continua ad
aggiornarsi da solo.** Il computer serve solo per: modifiche al codice, articoli scritti da Claude, push.

> **FantaTB (fantacalcio, online su /fanta/ dal 2026-09-02): KB dedicata in `kb/FANTATB.md`.** Supabase + API-Football, script `scripts/fanta_*.py`, workflow `fanta.yml`.

## 1. Architettura in 60 secondi
- **Feed 1 (testate, ogni 2 ore 06-22 UTC)**: `update.yml` → `scripts/build.py` interroga Google News
  (query = `teams.json["kw"][lang]` + `squadra["search"]`, es. "notizie calcio Inter Milan") più i feed
  RSS diretti di `data/sources.json`; classifica con le regole di `rules/keywords.<lang>.json`
  → `data/<lang>/board.json`, `home.json` → commit su `main` → deploy Vercel.
  Per le prime voci di ogni squadra risolve il link reale di Google News (**gnewsdecoder**) ed
  estrae la og:image per la copertina.
- **Estrazione movimenti da→a (modello scout): SOSPESA.** `extract_movements_global` esce subito
  con `SCOUT_OFF=1` (default). Il campo `nomi` di board.json si svuota da solo per decadimento.
  Il guscio tecnico (batch da 24, retry sui 429, JSON mode) è intatto. Vedi §7.
- **Feed 2 (Telegram esperti, ogni 5 min)**: `fast.yml` → `scripts/fastlane.py` legge t.me/s/<canale>,
  classifica con Groq → `data/ultimora.json` sul **branch `live`** (niente deploy: il front-end lo legge
  da raw.githubusercontent con auto-refresh 60s).
- **Articoli**: li scrive **Claude** (non Groq). `data/articles/*.json` → `scripts/render_articles.py`
  genera `articoli/<lang>/*.html` + index.json + sitemap. Tre pianificate: 12:00, 16:00, 20:00 (vedi
  `kb/PIANIFICATE.md`).
- **Sezione Mondiale**: `scripts/mondiali.py` (fonte gratis openfootball) → `data/mondiali.json`,
  pagina `mondiali.html`. Bandiere via flagcdn.
  Contiene gironi, **classifiche calcolate**, calendario, risultati, marcatori e news dedicate.
  Pronta per cartellini e rose se si attiva **BALLDONTLIE GOAT**.
- **Cervello**: `scripts/brain.py` = carta editoriale, glossario alias, esempi, blacklist allenatori.
- **Dati ufficiali**: `scripts/rosters.py` scarica le rose da football-data.org → `data/rosters.json`
  (refresh se più vecchio di 5 giorni, o con `FORCE_ROSTERS=1`).

### Modelli Groq (chiave in groq_key.txt)
**Tutti i modelli llama sono stati dismessi da Groq intorno al 2026-07-20** e rispondono 404.
Lo strato AI del sito è rimasto morto per sei settimane senza che nulla lo segnalasse. Sostituiti il
2026-09-02. Ogni script ha ora la **sua** variabile d'ambiente (prima condividevano `LLM_MODEL`):

| Script | Variabile | Default attuale | Note |
|---|---|---|---|
| `build.py` | `SCOUT_MODEL` | `groq/compound-mini` | 70k token/min |
| `fastlane.py` | `FAST_MODEL` | `groq/compound-mini` | 70k token/min |
| `articles.py` | `ARTICLE_MODEL` | `openai/gpt-oss-120b` | fallback `gpt-oss-20b`, poi `compound-mini` |

Verificati col JSON mode che il codice richiede: `qwen/qwen3.6-27b` emette blocchi think e rompe il
parsing, `groq/compound` ignora il JSON mode. **Prima di cambiare modello, testare sempre con
response_format json_object.** Elenco aggiornato: `GET https://api.groq.com/openai/v1/models`.

## 2. Nuovo computer: checklist (20 minuti)
1. Installa **Git for Windows** (git-scm.com, opzioni default) e **Python 3.12+**.
2. Clona: `git clone https://github.com/ultimacenere/transferbeat.git Calciomercato` (es. sul Desktop).
   **Preferisci un percorso CORTO** (vedi §3, limite MAX_PATH).
3. `pip install -r requirements.txt`
4. **SEGRETI** (NON sono nel repo, gitignorati!): copia nella cartella `groq_key.txt`,
   `github_token.txt` e `football_data_key.txt` dal file privato su Drive ("TransferBeat-segreti").
5. Login GitHub nel browser Chrome (serve per Actions/azioni manuali).
6. In **Cowork**: seleziona la cartella clonata. Claude rilegge questa KB ed è operativo.
7. **Ricrea le tre pianificate** (vivono sulla macchina, non nel repo): i prompt sono in
   `kb/PIANIFICATE.md`.
  Copertine per formato: `img/cover-lunch.svg` (ambra, LUNCH BREAK), `img/cover-storia.svg` (blu,
  FOCUS MERCATO), `img/cover-recap.svg` (verde, RECAP DI GIORNATA). Primo giro: usa "Run now" per pre-approvare i permessi.
8. Test: chiedi a Claude di verificare lo stato (git fetch + apertura sito).

## 3. Regole operative per Claude (IMPORTANTI)
- **La cartella locale va in deriva: la verità è `origin/main`.** La copia su Google Drive può restare
  indietro di settimane senza che nulla lo segnali. **Prima di analizzare o decidere qualsiasi cosa,
  leggere i file con `git show origin/main:<file>`, non dal disco.** Un'analisi fatta sui file locali
  può concludere che il sito è morto mentre è perfettamente vivo.
- **Mai scrivere file con Write/Edit dell'host**: il mount tronca i file. Sempre bash (heredoc) o python.
- **Commit sempre col pattern plumbing** sopra `origin/main` aggiornato (i cron committano spesso):
  `GIT_INDEX_FILE` temporaneo → `read-tree origin/main` → `update-index --add` dei SOLI file voluti →
  `write-tree` → `commit-tree -p origin/main` → `update-ref refs/heads/main` → poi riallineare
  (`rm .git/index`, `git read-tree HEAD`, `git checkout-index -a -f`). Questo pattern è
  **indispensabile** proprio perché la copia locale è in deriva: `git add -A` committerebbe file vecchi.
- **Mai committare** `data/ultimora.json` (gitignorato) né sovrascrivere `data/<lang>/*.json` con
  copie vecchie. Il `guard.py` blocca i troncamenti dei sorgenti (ma vedi §5, ha due difetti).
- **Push AUTOMATICO**: `bash scripts/pubblica.sh` (usa github_token.txt, non stampa il token).
  Lo usano le pianificate per pubblicarsi da sole; l'utente può sempre usare `pubblica-ora.bat`
  oppure `carica-modifiche.bat`.
- Se un push è "rejected (fetch first)": un cron è passato prima → ricostruire il commit sopra il
  nuovo origin/main (stesso pattern plumbing) e ripushare.
- **Lock git stale**: se un comando git dice "Another git process seems to be running", su Drive
  restano file di lock vecchi di mesi (`.git/index.lock`, `.git/refs/remotes/origin/<branch>.lock`).
  Controllare la data: se è vecchia e non ci sono processi git attivi, si rimuovono.
- **Limite MAX_PATH (260 caratteri)**: su Windows `os.listdir` e `glob` vedono i file ma `open()`
  fallisce con FileNotFoundError se il percorso completo supera i 260 caratteri. Capita con le cartelle
  di lavoro temporanee lunghe. Rimedio: usare una cartella di lavoro dal nome corto.
- **Console Windows**: `py script.py` che stampa accenti muore con UnicodeEncodeError (cp1252).
  Anteporre `PYTHONIOENCODING=utf-8`.

## 4. Account e pannelli
- **GitHub**: repo `ultimacenere/transferbeat` (Actions → "Aggiorna dati"/"Ultim'ora", bottone Run workflow).
- **Vercel**: progetto collegato al repo, deploy automatico su push a `main` (branch `live` escluso via vercel.json).
- **cron-job.org**: 2 job — "TransferBeat Ultim'ora" (ogni 5 min) e "TransferBeat Aggiorna dati"
  (08/12/20 italiane). Chiamano l'API GitHub col token (header Authorization Bearer).
- **Register.it**: DNS del dominio (A record apex → 216.198.79.1, www CNAME Vercel).
- **Groq console** (console.groq.com): chiave API, limiti per modello.
- **football-data.org**: chiave in `football_data_key.txt`. Tier gratuito: calendario, classifiche,
  risultati, marcatori, rose, arbitri. **NON espone le formazioni** (nessun campo lineup o formation):
  le probabili sono per forza editoriali, non un dato.
- **Token GitHub**: fine-grained, rigenerato il 2026-09-02, SENZA scadenza. Permessi: Actions, Contents,
  Workflows (tutti Read+write). Servono per: lanciare i cron, push automatico, modificare i workflow.
  ATTENZIONE: "Regenerate" cambia il VALORE del token e revoca il vecchio all'istante (la voce nella
  lista resta la stessa, quindi sembra invariato): dopo ogni rigenerazione i 2 job cron-job.org restano
  fermi finché non incolli il nuovo valore nell'header. Verifica: TEST RUN sul job deve dare HTTP 204.

## 5. Runbook guasti rapidi
- **Guasto SILENZIOSO (il più pericoloso)**: quasi ogni percorso del codice degrada con un default
  (`classify` → "rumor", `reliability` → 1, `except Exception: pass`) e il workflow resta verde.
  Lo strato AI è rimasto morto **6 settimane** così. Controllo rapido di salute:
  `git show origin/main:data/it/board.json` → il campo `aggiornato` deve essere di poche ore fa.
- **Modelli Groq 404**: Groq dismette i modelli senza preavviso. Sintomo: `nomi` vuoto in board.json,
  titoli ultim'ora con le emoji originali (la ripulitura la fa il modello). Verifica con l'endpoint
  `/openai/v1/models`. Vedi la tabella in §1.
- **Ultim'ora ferma**: cron-job.org → cronologia job; GitHub Actions → "Ultim'ora TransferBeat".
  Test manuale del job deve dare HTTP 204. Se dà 401 il token è scaduto o revocato (vedi §4).
- **Board tutta in una colonna**: la classificazione è a regole; se le parole di `rules/keywords.*.json`
  non corrispondono al flusso di notizie del momento, tutto cade nel default "rumor".
- **Board vuota sul sito**: quasi sempre JS troncato → `node --check` sullo script estratto; vedi §3.
- **Duplicati in ultim'ora**: la dedup è sull'id del messaggio Telegram (`tg`) più il titolo
  normalizzato; la pulizia è automatica a ogni giro.
- **Groq 429**: leggere il messaggio. "per minute" = aspettare un minuto. "per day (TPD)" = quel
  modello è esaurito fino alle **00:00 UTC** (02:00 italiane). Gli articoli hanno **fallback
  automatico** sulla lista `ARTICLE_MODELS`.
- **Nomi sbagliati nella board** (oggi non applicabile, lo scout è sospeso: torna valido con la §7):
  l'estrazione globale da→a usa il **match ESATTO** dei club, più la blacklist allenatori di
  `brain.py`. Caso noto già risolto: **"Milan" non deve mai matchare l'Inter**, il cui campo `search`
  è "Inter Milan".
- **Push impossibile / repo locale incasinato**: il repo locale è sacrificabile! Se serve:
  ri-clonare da zero (la verità è su GitHub) e rimettere i 3 file segreti.

### Difetti noti, non ancora corretti (2026-09-02)
- **`guard.py` — via di fuga inesistente**: il messaggio dice di sbloccare con una variabile TB_FORCE
  ma lo script non la legge mai. Non c'è modo di forzare una riduzione voluta.
- **`guard.py` — crash su Windows**: usa `subprocess.run(text=True)` senza `encoding`, quindi con
  locale italiano decodifica in cp1252 e muore su un byte non mappabile. Colpisce `carica-modifiche.bat`.
- **`brain.is_coach()` — falsi positivi gravi**: confronta il solo cognome contro una lista che contiene
  "simeone" e "italiano", quindi **Giovanni Simeone e Vincenzo Italiano risultano allenatori** e
  verrebbero cancellati in silenzio da tabellini, board e articoli. Da svuotare o ribaltare.
- **`rosters.py` — perdita silenziosa di leghe**: ogni competizione è dentro un try/except che fa
  continue, quindi una chiamata fallita fa sparire un'intera lega senza segnalarlo; con `_is_fresh(5)`
  il buco resta congelato 5 giorni. Gli snapshot storici oscillano fra 165 e 36 club per questo motivo.
- **`rosters.py` — chiamata sprecata**: il codice `CL` restituisce 36 club con **0 giocatori**.
- **`rosters.py` — id buttato**: l'id football-data del giocatore viene scartato, quindi i confronti
  fra rose si possono fare solo sul nome.
- **`build.py:544-546` — trappola KeyError**: le colonne sono costruite con le quattro chiavi letterali
  e indicizzate col risultato di `classify()`. **Una categoria nuova fa morire il job**, e siccome lo
  step build di `update.yml` è l'unico senza rete di sicurezza, muore prima del commit e il sito si
  congela all'ultima versione buona.
- **`mondo_home` non è per lingua**: `fetch(m["search"])` usa la stessa stringa per it/en/es, quindi
  con locale italiano tornano fonti inglesi. Si corregge solo toccando `build.py`.
- **sitemap**: `mondiali.html` e `fonti.html` non compaiono fra i 554 URL.

## 6. Cosa NON è nel repo (backup su Drive, file privato)
- `groq_key.txt` (chiave Groq)
- `github_token.txt` (token GitHub fine-grained)
- `football_data_key.txt` (chiave football-data.org)
- Credenziali account: GitHub, Vercel, cron-job.org, Register.it, Google (analytics)

## 7. RIATTIVARE IL CALCIOMERCATO (finestra invernale / fine campionato)
Niente è stato cancellato. La riaccensione è una sequenza di modifiche **reversibili**, tutte già
documentate qui. Punto di ritorno dell'intera riconversione: tag **`pre-riconversione`** (sha
`dfc45f8`), che rappresenta il sito con il motore di mercato ancora attivo e i modelli già riparati.

**1. Riaccendere l'estrazione dei movimenti da→a.**
Aggiungere `SCOUT_OFF: "0"` fra le variabili d'ambiente dello step "Genera i dati" di
`.github/workflows/update.yml`, accanto a GROQ_API_KEY. Non serve toccare `build.py`: la riga di
uscita anticipata in `extract_movements_global` legge quella variabile.

**2. Rimettere la parola chiave di mercato** in `data/teams.json`, campo `kw`:
- it: da `notizie calcio` a `calciomercato`
- en: da `football news` a `football transfer`
- es: da `noticias fútbol` a `fichajes`

**3. Rimettere i feed di mercato** in `data/sources.json`. Quelli rimossi il 2026-09-02:
- Guardian transfer-window — `https://www.theguardian.com/football/transfer-window/rss` (tier 3, en) — era vivo
- Marca mercado-fichajes — `https://e00-marca.uecdn.es/rss/futbol/mercado-fichajes.xml` (tier 3, es) — era vivo
- Gazzetta calciomercato — `https://www.gazzetta.it/rss/calciomercato.xml` — **NON rimetterlo: è morto
  dal 2023-11-14.** Tutti i feed Gazzetta sono fermi (`calcio.xml` a marzo 2026, `serie-a.xml` al 2023).

**Regola d'oro prima di aggiungere un feed**: `build.py` scarta gli item senza data valida
(`age_days(None)` torna 9999, oltre il filtro dei 30 giorni). Verificare con feedparser che
`published_parsed` non sia None, altrimenti il feed non porta **nulla** e non lo segnala nessuno.
È il caso di Sky Sport Italia, che pubblica le date in italiano: inutilizzabile come feed diretto
(e comunque superfluo, perché Sky arriva già come seconda fonte del sito via Google News).

**4. La tassonomia NON va toccata.** I vocabolari di `rules/keywords.*.json` sono l'**unione** dei
termini di mercato e di quelli di campionato: le parole di mercato sono già tutte lì, nella loro
casella originale. I quattro slot sono una scala di concretezza che regge entrambi i domini:
done = fatto avvenuto, conf = atto ufficiale, obj = imminente o anteprima, rumor = analisi (default).

**5. Facoltativo — "Dal mondo"**: `mondo_home` in `teams.json` è oggi sulle coppe europee (Champions,
Europa, Conference, Bundesliga). Le voci di mercato precedenti erano: `Brazil football` (Brasile),
`Saudi Pro League` (Arabia Saudita), `MLS Messi` (MLS), `national team World Cup` (Nazionali).

**6. Verifica dopo la riaccensione**: al primo build, `git show origin/main:data/it/board.json` deve
mostrare il campo `nomi` di nuovo popolato. Se resta vuoto, controllare i modelli Groq (§1) prima
di ogni altra cosa: è il guasto che si ripete.

### Date utili
- Finestra invernale: **gennaio**. Fine campionato e finestra estiva: **giugno**.
- Baseline rose pre-deadline dell'estate 2026: `data/rosters/2026-08-31.json` (155 club, 4833 giocatori),
  congelata perché `_is_fresh(5)` riscrive `data/rosters.json` ogni 5 giorni.
- Archivio del mercato estivo 2026: lo storico di `data/it/board.json` ha oltre 770 versioni dal
  2026-06-03, ognuna con le notizie già classificate e con le fonti. È la sorgente giusta per un
  bilancio del mercato, molto più affidabile del diff fra le rose (che riflette le ri-registrazioni
  delle liste, non i trasferimenti).
