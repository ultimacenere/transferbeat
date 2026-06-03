# TransferBeat

Sito verticale sul calciomercato: una **home stile giornale** e una **board** che smista le
trattative di ogni squadra in 4 categorie (Rumors → Obiettivi → Confermate → Concluse), con
**feed di giornata** e affidabilità della fonte. Aggiornamento automatico **3 volte al giorno**,
a **costo zero**: nessun server, nessun abbonamento.

## Come funziona

```
Google News RSS  →  scripts/build.py  →  data/board.json + data/home.json  →  index.html / board.html
 (un feed/squadra)   classifica a keyword     "database" in JSON                sito statico
                     + affidabilità per testata
        ▲
   GitHub Actions (cron 3×/giorno: 08:00 · 12:00 · 20:00)
```

## Struttura

```
.
├─ index.html               # home stile giornale (legge data/home.json)
├─ board.html               # board mercato 4 colonne (legge data/board.json)
├─ data/
│  ├─ teams.json            # squadre + query localizzate IT/EN/ES (config principale)
│  ├─ it/ · en/ · es/       # board.json + home.json per lingua (GENERATI)
├─ rules/
│  ├─ keywords.it.json      # dizionari per lingua (parole chiave + affidabilità)
│  ├─ keywords.en.json
│  └─ keywords.es.json
├─ scripts/build.py         # ingestione RSS + classificazione + movimenti + scrittura JSON
├─ requirements.txt         # feedparser, googlenewsdecoder, requests
└─ .github/workflows/update.yml   # cron 3×/giorno
```

## Provarlo in locale

I browser bloccano la lettura dei JSON se apri il file con doppio clic. Serve un mini-server:

```bash
pip install -r requirements.txt
python scripts/build.py          # genera i dati freschi
python -m http.server            # poi apri http://localhost:8000
```

## Pubblicarlo gratis (GitHub Pages)

1. Crea un repository su GitHub e carica questi file.
2. *Settings → Pages* → Source: branch `main`, cartella `/root` → Save.
3. Il sito è online su `https://TUONOME.github.io/NOMEREPO/`.
4. *Settings → Actions → General* → abilita "Read and write permissions".
5. Vai nella tab **Actions**, apri "Aggiorna dati TransferBeat" e premi **Run workflow** per il primo
   aggiornamento. Da lì in poi parte da solo 3 volte al giorno.

## Personalizzare

- **Aggiungere squadre:** aggiungi una riga in `data/teams.json` (nome, sigla, colore, lega, query).
- **Migliorare la classificazione:** modifica le parole chiave in `rules/keywords.json`. Non serve
  toccare il codice.
- **Cambiare gli orari:** modifica il `cron` in `.github/workflows/update.yml` (ricorda: orari in UTC).
- **Fonti dirette:** aggiungi RSS di testate/giornalisti in `data/sources.json` (`nome`, `url`, `tier` 1-3, `lang`). Vengono letti oltre a Google News e agganciati alle squadre citate nel titolo.
- **Fonti di fiducia:** aggiungi nomi di testate/giornalisti in `rules/keywords.<lang>.json` sotto `affidabilita` → `"3"` per dargli 3 pallini.

## Multilingua (IT / EN / ES)

Il sito nasce internazionale. Il selettore lingua in alto (IT · EN · ES) cambia interfaccia e
contenuti; la lingua resta memorizzata e si può forzare con `?lang=en` o `?lang=es` nell'URL
(usato anche per gli `hreflang`, utili alla SEO internazionale).

Come funziona: lo script `build.py` gira per ogni lingua con i **feed Google News localizzati**
(parametri `hl`/`gl`) e il **dizionario di classificazione di quella lingua**
(`rules/keywords.<lang>.json`), e scrive i dati in `data/it/`, `data/en/`, `data/es/`. Aggiungere
una lingua = aggiungere la sua riga in `data/teams.json` (campo `kw`, `label`) e un file
`keywords.<lang>.json`. L'architettura è già pronta: il costo per lingua è quasi nullo.

## Vista "Nomi" (movimenti estratti con LLM gratuito)

Nella board, lo switch **📰 Notizie ⇄ 🔁 Nomi** trasforma le colonne: invece dei titoli,
mostra i movimenti puliti, es. *(USCITA) Dumfries → Real Madrid*, *(ENTRATA) Mancini ← Roma*.

I movimenti vengono estratti dai titoli con un LLM gratuito (**Groq**). È opzionale: senza
chiave, la vista Notizie funziona comunque e la vista Nomi resta vuota (con avviso).

Per attivarla:

1. Crea una chiave gratuita su **console.groq.com** (Login → API Keys → Create).
2. **In locale:** crea un file `groq_key.txt` nella cartella del progetto e incollaci dentro
   solo la chiave. `aggiorna-dati.bat` la legge in automatico. (Il file è già in `.gitignore`,
   non finisce su GitHub.)
3. **Su GitHub (per il cron):** repo → *Settings → Secrets and variables → Actions → New
   repository secret*, nome `GROQ_API_KEY`, valore la chiave. Il workflow la usa già.

Modello predefinito: `llama-3.3-70b-versatile` (cambiabile con la variabile `LLM_MODEL`).
Una chiamata per squadra a ogni aggiornamento: ampiamente dentro i limiti del piano gratuito.

## Limiti attuali (versione costo zero) e prossimi passi

- La tabella si aggiorna 3×/giorno, **non in tempo reale**: ottima per la fotografia, non ancora per
  battere tutti sull'ultim'ora.
- La classificazione a parole chiave sbaglia qualche notizia: si affina aggiornando il dizionario.
- Google News dà titoli e fonti, non cifre/valori strutturati.

Upgrade futuri a basso costo: classificazione con LLM free-tier, API struttura per rose e valori,
trigger event-driven per le ufficialità. Vedi `TransferBeat-setup-costo-zero.md`.

---
*Mostra sempre titolo + fonte + link, mai il testo integrale degli articoli (copyright).*
