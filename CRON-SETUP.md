# TransferBeat — far partire i cron DA SOLI (pinger esterno gratuito)

Lo scheduler interno di GitHub Actions è inaffidabile (ritarda o salta, soprattutto il 5-min).
Soluzione: un servizio gratuito (**cron-job.org**) chiama l'API di GitHub all'orario esatto e fa
partire i workflow. Servono un **token GitHub** e **2 job** su cron-job.org.

## Passo 1 — Crea il token GitHub (fine-grained)

1. Vai su github.com → Settings → Developer settings → **Personal access tokens → Fine-grained tokens → Generate new token**
   (link diretto: https://github.com/settings/personal-access-tokens/new). Conferma identità se richiesto.
2. **Token name:** `transferbeat-cron`
3. **Expiration:** scegli "No expiration" (o 1 anno).
4. **Repository access:** "Only select repositories" → seleziona **ultimacenere/transferbeat**.
5. **Permissions → Repository permissions → Actions:** imposta su **Read and write**.
   (Lascia tutto il resto su "No access".)
6. **Generate token** → **copia** il token (inizia con `github_pat_…`). Si vede UNA volta sola.

## Passo 2 — Crea i job su cron-job.org (gratis)

Registrati su https://cron-job.org → "Create cronjob". Per ogni job imposta:

### Job A — Ultim'ora (ogni 5 minuti)
- **URL:** `https://api.github.com/repos/ultimacenere/transferbeat/actions/workflows/fast.yml/dispatches`
- **Schedule:** ogni 5 minuti (every 5 minutes)
- **Request method:** POST
- **Request body:** `{"ref":"main"}`
- **Headers** (sezione "Advanced" / "Headers"):
  - `Accept: application/vnd.github+json`
  - `Authorization: Bearer IL_TUO_TOKEN`
  - `X-GitHub-Api-Version: 2022-11-28`
  - `User-Agent: transferbeat-cron`
  - `Content-Type: application/json`

### Job B — Aggiorna dati (3 volte al giorno)
- **URL:** `https://api.github.com/repos/ultimacenere/transferbeat/actions/workflows/update.yml/dispatches`
- **Schedule:** alle **08:00, 12:00, 20:00** (orario italiano)
- Stessi **method / body / headers** del Job A.

## Note
- Una risposta **HTTP 204** dall'API = successo (il workflow è stato lanciato).
- Il token va incollato SOLO su cron-job.org (servizio fidato). Non condividerlo altrove.
- Se il token scade o lo revochi, basta rigenerarlo e aggiornarlo nei 2 job.
