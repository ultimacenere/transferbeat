#!/usr/bin/env bash
# Pubblica su GitHub il commit corrente (HEAD -> main) usando il token fine-grained (Contents:write).
# NON stampa mai il token. Push resistente: integra gli aggiornamenti remoti e ritenta.
#
# TOKEN: viene cercato in più posti perché su questa macchina il repo esiste in più copie
# (clone sul Desktop usato dalle pianificate, cartella su Google Drive usata dalle sessioni,
# worktree in .claude/worktrees/ che NON contengono i file gitignorati). Dopo un "Regenerate"
# su GitHub il vecchio valore è revocato all'istante: basta aggiornare UNA copia, questo script
# prova ogni candidato contro l'API e riallinea da solo il file github_token.txt della cartella
# corrente con il primo valore valido. Variabile TB_TOKEN_FILE = percorso esplicito, ha la precedenza.
set -o pipefail
cd "$(dirname "$0")/.."
REPO_DIR="$(pwd)"
REPO_SLUG="ultimacenere/transferbeat"
LOCAL_FILE="$REPO_DIR/github_token.txt"

# Radice del worktree principale (se siamo in un worktree secondario)
COMMON="$(git rev-parse --git-common-dir 2>/dev/null)"
MAIN_ROOT=""
if [ -n "$COMMON" ]; then
  MAIN_ROOT="$(cd "$COMMON/.." 2>/dev/null && pwd)"
fi

CANDIDATES=()
[ -n "$TB_TOKEN_FILE" ] && CANDIDATES+=("$TB_TOKEN_FILE")
CANDIDATES+=("$LOCAL_FILE")
[ -n "$MAIN_ROOT" ] && CANDIDATES+=("$MAIN_ROOT/github_token.txt")
CANDIDATES+=("$HOME/Desktop/Calciomercato/github_token.txt")
CANDIDATES+=("/g/Il mio Drive/Calciomercato/github_token.txt")
CANDIDATES+=("G:/Il mio Drive/Calciomercato/github_token.txt")

read_token(){ tr -d '\n\r ' < "$1" 2>/dev/null; }

# Ritorna il codice HTTP dell'API con quel token (000 = rete/curl assente)
check_token(){
  command -v curl >/dev/null 2>&1 || { echo "000"; return; }
  curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
    -H "Authorization: Bearer $1" -H "User-Agent: transferbeat-pubblica" \
    "https://api.github.com/repos/$REPO_SLUG" 2>/dev/null || echo "000"
}

TOKEN=""; TOKEN_FROM=""; REPORT=""
SEEN=""
for f in "${CANDIDATES[@]}"; do
  case "|$SEEN|" in *"|$f|"*) continue;; esac
  SEEN="$SEEN|$f"
  if [ ! -s "$f" ]; then REPORT="$REPORT\n  - $f: assente"; continue; fi
  t="$(read_token "$f")"
  if [ -z "$t" ]; then REPORT="$REPORT\n  - $f: vuoto"; continue; fi
  code="$(check_token "$t")"
  case "$code" in
    200) TOKEN="$t"; TOKEN_FROM="$f"; REPORT="$REPORT\n  - $f: VALIDO"; break;;
    000) # impossibile verificare (niente curl o niente rete): usa il primo non vuoto
         TOKEN="$t"; TOKEN_FROM="$f"; REPORT="$REPORT\n  - $f: non verificabile (uso questo)"; break;;
    *)   REPORT="$REPORT\n  - $f: NON valido (HTTP $code, revocato o scaduto)";;
  esac
done

if [ -z "$TOKEN" ]; then
  echo "ERRORE: nessun token GitHub valido trovato. File controllati:"
  printf "%b\n" "$REPORT"
  echo "Rimedio: su GitHub (Settings > Developer settings > Fine-grained tokens) rigenera il token"
  echo "e incolla il NUOVO valore in github_token.txt di questa cartella ($REPO_DIR)."
  echo "ATTENZIONE: 'Regenerate' revoca subito il vecchio valore: aggiorna anche l'header"
  echo "Authorization dei due job su cron-job.org (test run deve dare HTTP 204)."
  exit 1
fi

if [ "$TOKEN_FROM" != "$LOCAL_FILE" ]; then
  if printf '%s\n' "$TOKEN" > "$LOCAL_FILE" 2>/dev/null; then
    echo "Token: github_token.txt di questa cartella era assente o non valido; riallineato con il valore valido di $TOKEN_FROM."
  else
    echo "Token: uso il valore valido di $TOKEN_FROM (impossibile scrivere $LOCAL_FILE)."
  fi
fi

REMOTE="https://x-access-token:${TOKEN}@github.com/${REPO_SLUG}.git"
red(){ sed -E "s/${TOKEN}/***/g"; }
BEFORE=$(git ls-remote "$REMOTE" refs/heads/main 2>/dev/null | cut -f1)   # per IndexNow: URL cambiate rispetto a quanto era online
PY=$(command -v py || command -v python3 || command -v python)
for i in 1 2 3 4 5; do
  if git push "$REMOTE" HEAD:main 2>&1 | red; then
    echo "Pubblicato (tentativo $i)."
    [ -n "$PY" ] && "$PY" -X utf8 scripts/indexnow.py "$BEFORE" HEAD 2>&1 | tail -3
    exit 0
  fi
  echo "Push respinto: integro gli aggiornamenti remoti e ritento ($i)..."
  rm -f "$(git rev-parse --git-dir)/index.lock"
  git fetch "$REMOTE" main 2>&1 | red
  if ! git rebase FETCH_HEAD 2>&1 | red; then
    git rebase --abort 2>/dev/null
    rm -f "$(git rev-parse --git-dir)/index"; git read-tree HEAD 2>/dev/null
  fi
  sleep $(( (RANDOM % 6) + 3 ))
done
echo "ERRORE: push fallito dopo 5 tentativi."; exit 1
