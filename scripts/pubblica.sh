#!/usr/bin/env bash
# Pubblica su GitHub il commit corrente di 'main' usando il token (Contents:write).
# NON stampa mai il token. Push resistente: integra gli aggiornamenti remoti e ritenta.
set -o pipefail
cd "$(dirname "$0")/.."
TOKEN=$(cat github_token.txt | tr -d '\n\r ')
REMOTE="https://x-access-token:${TOKEN}@github.com/ultimacenere/transferbeat.git"
red(){ sed -E "s/${TOKEN}/***/g"; }
for i in 1 2 3 4 5; do
  if git push "$REMOTE" HEAD:main 2>&1 | red; then
    echo "Pubblicato (tentativo $i)."; exit 0
  fi
  echo "Push respinto: integro gli aggiornamenti remoti e ritento ($i)..."
  rm -f .git/index.lock
  git fetch "$REMOTE" main 2>&1 | red
  if ! git rebase FETCH_HEAD 2>&1 | red; then
    git rebase --abort 2>/dev/null
    rm -f .git/index; git read-tree HEAD 2>/dev/null
  fi
  sleep $(( (RANDOM % 6) + 3 ))
done
echo "ERRORE: push fallito dopo 5 tentativi."; exit 1
