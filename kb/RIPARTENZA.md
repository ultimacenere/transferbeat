# TransferBeat — KB di RIPARTENZA
*Come essere operativi al 100% su QUALSIASI computer, e come funziona tutto. Aggiornata: 2026-06-05.*

## 0. La verità fondamentale
**Il sito NON dipende da nessun computer.** Fonte di verità: GitHub (`ultimacenere/transferbeat`).
Vercel pubblica da lì (dominio transferbeat.com via Register.it). I cron girano su GitHub Actions,
innescati da cron-job.org. **A PC spento il sito continua ad aggiornarsi da solo.**
Il computer serve solo per: modifiche al codice, articoli scritti da Claude, push.

## 1. Architettura in 60 secondi
- **Feed 1 (testate, 3×/giorno 08/12/20)**: `update.yml` → `scripts/build.py` legge Google News+RSS,
  classifica (modello Groq 8b), estrae i movimenti `da→a` (modello scout) → `data/<lang>/board.json`,
  `home.json` → commit su `main` → deploy Vercel.
- **Feed 2 (Telegram esperti, ogni 5 min)**: `fast.yml` → `scripts/fastlane.py` legge t.me/s/<canale>,
  classifica (8b) → `data/ultimora.json` sul **branch `live`** (niente deploy: il front-end lo legge
  da raw.githubusercontent con auto-refresh 60s).
- **Articoli**: li scrive **Claude** (non Groq). Formato recap: `data/articles/recap-AAAA-MM-GG.json`
  → `scripts/render_articles.py` genera `articoli/<lang>/*.html` + index.json + sitemap.
  Copertina formato: `img/cover-recap.svg`.
- **Cervello**: `scripts/brain.py` = carta editoriale, glossario alias, esempi, blacklist allenatori.
- **Modelli Groq** (chiave in groq_key.txt): 8b=classificazione (500k token/g), scout=movimenti
  (30k token/min), 70b=scrittura riserva (100k token/g, reset 00:00 UTC). Limiti per-modello separati.

## 2. Nuovo computer: checklist (20 minuti)
1. Installa **Git for Windows** (git-scm.com, opzioni default).
2. Clona: `git clone https://github.com/ultimacenere/transferbeat.git Calciomercato` (es. sul Desktop).
3. **SEGRETI** (NON sono nel repo, gitignorati!): copia nella cartella `groq_key.txt` e
   `github_token.txt` dal file privato su Drive ("TransferBeat-segreti").
4. Login GitHub nel browser Chrome (serve per Actions/azioni manuali).
5. In **Cowork**: seleziona la cartella clonata. Claude rilegge questa KB ed è operativo.
6. **Ricrea la pianificata delle 20:00** (le pianificate vivono sulla macchina, non nel repo):
   chiedi a Claude "ricrea la pianificata del recap serale dalla KB" — il prompt completo è in
   `kb/PIANIFICATE.md`. Primo giro: usa "Run now" per pre-approvare i permessi.
7. Test: chiedi a Claude di verificare lo stato (git fetch + apertura sito).

## 3. Regole operative per Claude (IMPORTANTI)
- **Mai scrivere file con Write/Edit dell'host**: il mount tronca i file. Sempre bash
  (heredoc `cat > file <<'END'` o python) nel mount `/sessions/<sessione>/mnt/Calciomercato/`.
- **Commit sempre col pattern plumbing** sopra `origin/main` aggiornato (i cron committano spesso):
  `GIT_INDEX_FILE` temporaneo → `read-tree origin/main` → `update-index --add` dei SOLI file voluti →
  `write-tree` → `commit-tree -p origin/main` → `update-ref refs/heads/main` → poi riallineare
  (`rm .git/index; git read-tree HEAD; git checkout-index -a -f`).
- **Mai committare** `data/ultimora.json` (gitignorato) né sovrascrivere `data/<lang>/*.json` con
  copie vecchie. Il `guard.py` blocca i troncamenti dei sorgenti.
- **Push AUTOMATICO**: il token (Contents:write) consente di pubblicare senza credenziali Windows.
  Comando: `bash scripts/pubblica.sh` (usa github_token.txt, non stampa il token). Lo usano le pianificate
  per pubblicarsi da sole; l'utente puo' sempre usare `pubblica-ora.bat`/`carica-modifiche.bat`.
- Se un push è "rejected (fetch first)": un cron è passato prima → ricostruire il commit sopra il
  nuovo origin/main (stesso pattern plumbing) e ripushare.

## 4. Account e pannelli
- **GitHub**: repo `ultimacenere/transferbeat` (workflow: Actions → "Aggiorna dati"/"Ultim'ora", bottone Run workflow).
- **Vercel**: progetto collegato al repo, deploy automatico su push a `main` (branch `live` escluso via vercel.json).
- **cron-job.org**: 2 job — "TransferBeat Ultim'ora" (ogni 5 min) e "TransferBeat Aggiorna dati"
  (08/12/20 italiane). Chiamano l'API GitHub con il token (header Authorization: Bearer <github_token>).
- **Register.it**: DNS del dominio (A record apex → 216.198.79.1, www CNAME Vercel).
- **Groq console** (console.groq.com): chiave API, limiti per modello.
- **Token GitHub**: fine-grained, SCADE il 2026-09-02 → rigenerare (Actions Read+write; aggiungere
  "Contents Read+write" (gia' attivo: serve per il push automatico) e aggiornarlo nei 2 job cron-job.org
  e in github_token.txt.

## 5. Runbook guasti rapidi
- **Ultim'ora ferma**: cron-job.org → cronologia job; GitHub Actions → "Ultim'ora TransferBeat".
  Test manuale del job = "TEST DI ESECUZIONE" (deve dare HTTP 204).
- **Duplicati in ultim'ora**: la dedup è su id messaggio (`tg`) + titolo; pulizia automatica a ogni giro.
- **Nomi sbagliati nella board**: estrazione globale da→a con match ESATTO dei club; blacklist
  allenatori in brain.py. Caso noto risolto: "Milan" non deve mai matchare l'Inter (search "Inter Milan").
- **Groq 429**: guardare il messaggio — "per minute"=aspettare 1 min; "per day (TPD)"=quel modello è
  esaurito fino alle 00:00 UTC (02:00 italiane). Gli articoli hanno fallback automatico 70b→8b.
- **Board vuota sul sito**: quasi sempre JS troncato → `node --check` sullo script estratto; vedi regole §3.
- **Push impossibile / repo locale incasinato**: il repo locale è sacrificabile! Se serve:
  ri-clonare da zero (la verità è su GitHub) e rimettere i 2 file segreti.

## 6. Cosa NON è nel repo (backup su Drive, file privato)
- groq_key.txt (chiave Groq)
- github_token.txt (token GitHub fine-grained)
- Credenziali account: GitHub, Vercel, cron-job.org, Register.it, Google (analytics)
