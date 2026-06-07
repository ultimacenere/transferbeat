#!/usr/bin/env bash
# Pubblica su GitHub il commit corrente di 'main' usando il token (permesso Contents:write).
# NON stampa mai il token. Usato dalle pianificate per pubblicare in autonomia.
set -e
cd "$(dirname "$0")/.."
TOKEN=$(cat github_token.txt | tr -d '\n\r ')
git push "https://x-access-token:${TOKEN}@github.com/ultimacenere/transferbeat.git" HEAD:main 2>&1 | sed -E "s/${TOKEN}/***/g"
