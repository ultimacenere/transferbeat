# TransferBeat — Guida di setup a costo zero

Documento operativo per montare il sito (home + board mercato) con aggiornamento automatico
3 volte al giorno, **senza spendere un euro** e senza server. Pensato per essere seguito da te o
passato a uno sviluppatore.

---

## 1. L'idea in una frase

Tre volte al giorno un processo automatico (gratis) legge le notizie da feed pubblici, le smista
nelle 4 categorie con un sistema a parole chiave, scrive il risultato in file `.json`, e il sito
statico li mostra. Nessun database, nessun server, nessun abbonamento.

```
[Feed RSS gratuiti]  ->  [Script di classificazione]  ->  [file JSON]  ->  [Sito statico]
   Google News             regole/keyword                 dati.json        HTML già pronto
   (per squadra)           (08:00 / 12:00 / 20:00)
                                  |
                          gira su GitHub Actions (cron gratis)
```

## 2. Lo stack (tutto con piano gratuito)

| Pezzo | Strumento gratuito | A cosa serve |
|---|---|---|
| Sorgente notizie | **Google News RSS** (per query) | Un feed per ogni squadra, gratis e affidabile |
| Esecuzione 3×/giorno | **GitHub Actions** (cron) | Lancia lo script agli orari fissi |
| Classificazione | **Script Python a regole** | Smista in Rumors / Obiettivi / Confermate / Concluse |
| Archivio dati | **File JSON nel repo** | "Database" a costo zero |
| Sito | **HTML statico** (i 2 file del prototipo) | Front-end |
| Hosting | **GitHub Pages** o **Cloudflare Pages** | Pubblicazione gratuita con dominio |

Costo totale ricorrente: **0 €/mese**. (Un dominio `.it` o `.com` è opzionale, ~10 €/anno, se non
ti basta l'indirizzo gratuito `nomeutente.github.io`.)

---

## 3. La sorgente dati gratuita: Google News RSS

È il cuore del trucco. Google News espone un feed RSS per qualsiasi ricerca, gratis e senza chiave.
Costruisci un feed per ogni squadra così:

```
https://news.google.com/rss/search?q=calciomercato+%22Inter%22&hl=it&gl=IT&ceid=IT:it
```

- `q=` la query (es. `calciomercato "Inter"`). Le virgolette tengono insieme il nome squadra.
- `hl=it&gl=IT&ceid=IT:it` forza risultati in italiano.

Ottieni così, **per ogni squadra**, un flusso di titoli + link + data + testata, già pronto da
leggere. Per le notizie generali della home aggiungi feed con query tipo `calciomercato Serie A`,
`Champions League`, `Copa America`, ecc.

> **Perché questo e non scraping?** Lo scraping dei siti (es. Transfermarkt) viola i loro termini
> d'uso ed è fragile. Google News RSS è pubblico, stabile e gratuito. In più ti dà già la **testata**
> della fonte, che ci serve per il punteggio di affidabilità (vedi §6).

Feed aggiuntivi utili come backup, sempre gratuiti: gli RSS ufficiali delle testate (Gazzetta, Sky
Sport, TuttoMercatoWeb, Calciomercato.com). Verifica l'URL RSS attuale sul singolo sito, perché
cambiano nel tempo.

---

## 4. Struttura del progetto (cartelle e file)

```
mercatolive/
├─ index.html              # la home (file già pronto)
├─ board.html              # la board mercato (file già pronto)
├─ data/
│  ├─ teams.json           # elenco squadre + config feed
│  ├─ board.json           # dati delle 4 colonne per squadra  <-- generato
│  └─ home.json            # notizie home + ticker             <-- generato
├─ scripts/
│  └─ build.py             # lo script che legge RSS e scrive i JSON
├─ rules/
│  └─ keywords.json        # dizionario parole chiave (classificazione + affidabilità)
└─ .github/
   └─ workflows/
      └─ update.yml        # il cron 3×/giorno di GitHub Actions
```

I file `board.json` e `home.json` sono **prodotti dallo script**: il sito legge solo quelli.

---

## 5. Il modello dati (cosa contengono i JSON)

Lo script deve produrre JSON con questa forma, così il front-end li legge senza modifiche grosse.

**`board.json`** — una voce per ogni trattativa:

```json
{
  "aggiornato": "2024-07-15T12:00:00",
  "squadre": {
    "Inter": [
      {
        "stato": "done",
        "giocatore": "Petar Sucic",
        "da": "Dinamo Zagabria",
        "cifra": "€14M",
        "ruolo": "Centrocampista",
        "affidabilita": 3,
        "nota": "definito",
        "fonte": "Sky Sport",
        "link": "https://..."
      }
    ]
  }
}
```

`stato` assume i 4 valori: `rumor`, `obj` (obiettivo), `conf` (confermata), `done` (conclusa).

**`home.json`** — apertura, secondari, ticker, più letti:

```json
{
  "aggiornato": "2024-07-15T12:00:00",
  "ticker": ["UFFICIALE — Sucic all'Inter...", "..."],
  "apertura": { "categoria": "Serie A", "titolo": "...", "sommario": "...", "link": "..." },
  "secondari": [ { "categoria": "...", "titolo": "...", "link": "..." } ],
  "mondo": [ { "categoria": "Brasile", "titolo": "...", "link": "..." } ]
}
```

---

## 6. Il cuore: classificazione a regole (100% gratis)

Niente AI, niente chiavi API. Lo script applica due dizionari di parole chiave: uno decide **in quale
delle 4 colonne** finisce la notizia, l'altro assegna l'**affidabilità** in base alla testata.

### 6a. Da titolo → categoria

Si controlla il titolo (minuscolo) cercando le parole chiave, **dalla più forte alla più debole**:

| Stato | Parole chiave (esempi) | Esempio di titolo |
|---|---|---|
| **done** (Conclusa) | `ufficiale`, `è fatta`, `firma`, `comunicato`, `here we go`, `visite mediche superate` | "Ufficiale: Sucic è dell'Inter" |
| **conf** (Confermata) | `accordo`, `intesa raggiunta`, `fumata bianca`, `ha detto sì`, `visite mediche` | "Pavlović, intesa col Salisburgo" |
| **obj** (Obiettivo) | `obiettivo`, `priorità`, `pista`, `in pressing`, `trattativa`, `contatti`, `summit` | "Lukaku, Conte spinge: contatti col Chelsea" |
| **rumor** (Rumor) | `sondaggio`, `idea`, `suggestione`, `interesse`, `sogno`, `può`, `nel mirino`, `clausola` | "Suggestione Bernardo Silva per il Barça" |

Regola: si parte da `done` e si scende. Il **primo** gruppo che trova una parola chiave vince. Se non
trova nulla → default `rumor`. (Logica volutamente "prudente": una notizia incerta resta un rumor
finché una parola forte non la promuove.)

### 6b. Da testata → affidabilità (1–3 pallini)

| Affidabilità | Testate (tier) |
|---|---|
| **3 / alto** | Comunicati ufficiali dei club, Fabrizio Romano, Gianluca Di Marzio, Sky Sport, The Athletic, L'Équipe |
| **2 / medio** | Gazzetta, Corriere dello Sport, Tuttosport, Marca, Calciomercato.com, TuttoMercatoWeb |
| **1 / basso** | Aggregatori, siti di rumor, testate minori non in lista |

Lo script confronta il campo "fonte" del feed con queste liste. Sono i 3 pallini del prototipo: è la
feature che ti distingue dalla concorrenza, e qui costa zero.

### 6c. Deduplica

La stessa notizia arriva da 10 testate. Regola semplice e gratuita: se due voci hanno lo **stesso
giocatore + stessa squadra** entro la stessa giornata, tieni quella con **affidabilità più alta** e
scarta le altre. (Per il nome giocatore basta confrontare cognomi in minuscolo.)

> Tutto questo vive nel file `rules/keywords.json`, così aggiorni le parole chiave senza toccare il
> codice. Più lo usi, più lo affini: è normale partire all'80% di precisione e migliorare.

---

## 7. L'automazione 3×/giorno (GitHub Actions, gratis)

Un solo file, `.github/workflows/update.yml`, fa partire lo script agli orari giusti. Esempio di
configurazione del cron (orari in UTC: l'Italia d'estate è UTC+2, quindi 08:00/12:00/20:00 italiane =
06:00/10:00/18:00 UTC):

```yaml
on:
  schedule:
    - cron: "0 6,10,18 * * *"   # 08:00, 12:00, 20:00 ora italiana (estate)
  workflow_dispatch:            # bottone per lanciarlo a mano quando vuoi
```

Il workflow: installa Python → esegue `scripts/build.py` → fa commit dei JSON aggiornati nel repo. Il
sito su GitHub Pages si aggiorna da solo a ogni commit. **Tutto incluso nel piano gratuito** (i minuti
di Actions gratuiti coprono ampiamente 3 esecuzioni brevi al giorno).

> Nota: il cron di GitHub a volte parte con qualche minuto di ritardo. Per la *tabella* va benissimo.
> Per l'ultim'ora vera vedi i limiti al §10.

---

## 8. Collegare il sito ai dati

I due file HTML del prototipo oggi hanno i dati scritti dentro. Unica modifica: invece della costante
`DATA` interna, leggono il JSON generato. In pratica, all'avvio della pagina:

```js
fetch('data/board.json')
  .then(r => r.json())
  .then(d => render(d));   // stessa funzione di disegno di adesso
```

La parte grafica (colonne, card, feed, ticker) resta identica: cambia solo **da dove** arrivano i dati.

---

## 9. Pubblicazione (deploy gratuito)

Percorso più semplice, tutto gratis:

1. Crea un account **GitHub** e un repository (es. `mercatolive`).
2. Carica i file della struttura del §4.
3. In *Settings → Pages*, attiva GitHub Pages sul branch principale.
4. Il sito è online su `https://tuonome.github.io/mercatolive/`.
5. (Opzionale) Colleghi un dominio tuo nelle impostazioni Pages.

Alternativa equivalente: **Cloudflare Pages**, anch'esso gratuito, con build automatica a ogni commit.

---

## 10. I limiti del costo zero (e quando salire)

Onestà sul modello gratuito, così sai cosa aspettarti:

- **Latenza.** Con il cron 3×/giorno la tabella non è "in tempo reale": l'ufficialità delle 12:05 la
  vedi alle 20:00. Per il prodotto-tabella va bene; per battere i concorrenti sull'ultim'ora servirà
  poi un trigger event-driven (a pagamento, ma piccolo).
- **Precisione.** Le regole a parole chiave sbagliano qualche classificazione. Si accetta all'inizio e
  si raffina il dizionario. Il salto di qualità vero è l'LLM (passo successivo, quasi gratis con i
  tier free).
- **Profondità dati.** Google News dà titoli e fonti, non cifre/valori strutturati. Le cifre le
  estrai dal testo quando ci sono; per dati puliti (rose, valori) serviranno poi le API del §11.
- **Copyright.** Mostra **titolo riscritto + link + testata**, mai il testo integrale dell'articolo.
  Questo ti tiene al sicuro e dà traffico alle fonti.

## 11. Quando vorrai crescere (i primi upgrade a basso costo)

In ordine di priorità, quando il sito gira e ha pubblico:

1. **LLM free-tier** per la classificazione (precisione +affidabilità migliore) — quasi gratis.
2. **API struttura** (API-Football ~$19/mese o Sportmonks) per rose e valori puliti.
3. **Trigger ultim'ora** event-driven per pubblicare le ufficialità in minuti.

---

## 12. Checklist per andare online

- [ ] Account GitHub creato
- [ ] Repo `mercatolive` con la struttura del §4
- [ ] `teams.json` compilato con le squadre e le query Google News
- [ ] `keywords.json` con i dizionari del §6 (categoria + affidabilità)
- [ ] `build.py` che legge i feed, classifica, scrive `board.json` e `home.json`
- [ ] `update.yml` con il cron 3×/giorno
- [ ] `index.html` e `board.html` modificati per leggere i JSON (§8)
- [ ] GitHub Pages attivo → sito online
- [ ] Prova manuale con *workflow_dispatch* per vedere il primo aggiornamento

---

*TransferBeat — documento di setup, versione a costo zero. Tutti gli strumenti citati hanno un piano
gratuito sufficiente per partire. I passaggi a pagamento sono solo upgrade futuri opzionali.*
