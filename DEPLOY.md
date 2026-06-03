# TransferBeat — messa online (GitHub + Vercel + Register.it)

Guida passo-passo. Tempo stimato: ~20 minuti la prima volta. Tutto gratuito (a parte il dominio
che hai già su Register.it).

## 1. Prerequisiti

- **Account GitHub** (gratis) su github.com
- **Git installato** su Windows: https://git-scm.com/download/win (installazione "Next, Next…")
- **Account Vercel** (gratis) su vercel.com — fai "Sign up with GitHub", è la via più semplice

## 2. Carica il codice su GitHub

1. Su github.com → **New repository** → nome `transferbeat` → **NON** spuntare README/.gitignore →
   *Create repository*.
2. Copia l'indirizzo `.git` che ti mostra (es. `https://github.com/tuonome/transferbeat.git`).
3. Doppio clic su **`pubblica.bat`** nella cartella del progetto, incolla l'indirizzo, premi Invio.
   - Al primo `push` Git potrebbe aprire una finestra per fare login su GitHub: autorizza.
4. Ricarica la pagina del repo su GitHub: vedrai tutti i file caricati.

## 3. Pubblica su Vercel

1. Su vercel.com → **Add New… → Project** → **Import** il repository `transferbeat`.
2. Framework Preset: **Other** (è un sito statico, nessuna build necessaria).
   - Build Command: lascia vuoto · Output Directory: lascia vuoto (root).
3. **Deploy**. Dopo ~1 minuto il sito è online su un indirizzo `transferbeat.vercel.app`.

## 4. Collega il dominio transferbeat.com

1. Su Vercel → progetto → **Settings → Domains** → aggiungi `transferbeat.com` (e `www.transferbeat.com`).
2. Vercel ti mostra i record DNS da impostare (di solito un record **A** verso `76.76.21.21` e/o un
   **CNAME** per `www` verso `cname.vercel-dns.com`). Copiali.
3. Su **Register.it** → area clienti → dominio `transferbeat.com` → **Gestione DNS** → inserisci i
   record indicati da Vercel (sostituendo eventuali record A/CNAME esistenti sulla root).
4. Aspetta la propagazione (da pochi minuti a qualche ora). Vercel mette l'HTTPS in automatico.
5. Per **transferbeat.it**: o lo punti uguale a Vercel, oppure su Register.it imposti un **redirect**
   verso `transferbeat.com`. (Consiglio: un dominio principale, l'altro che reindirizza.)

## 5. Attiva gli aggiornamenti automatici (cron) e la vista Nomi

1. Su GitHub → repo → **Settings → Secrets and variables → Actions → New repository secret**:
   nome `GROQ_API_KEY`, valore la tua chiave gratuita di console.groq.com. (Abilita la vista "Nomi".)
2. Su GitHub → **Settings → Actions → General** → "Workflow permissions" → **Read and write**.
3. Tab **Actions** → workflow "Aggiorna dati TransferBeat" → **Run workflow** per il primo giro.
   Da lì parte da solo 3 volte al giorno; a ogni aggiornamento Vercel ripubblica in automatico.

## Riepilogo flusso a regime

```
GitHub Actions (3×/giorno)  →  rigenera data/it·en·es  →  commit  →  Vercel ripubblica  →  utenti
```

Nessun server, nessun costo ricorrente oltre al dominio. Per aggiornare il codice in futuro:
`git add . && git commit -m "..." && git push` (o ri-lancia i comandi da `pubblica.bat`).
