# Pianificate Cowork (da ricreare su ogni macchina)
Tre pianificate alimentano il palinsesto editoriale (3 articoli/giorno = 9 pagine IT/EN/ES). **Riscritte il 2026-09-03 per il
calcio giocato** (mercato chiuso): fonti = notizie classificate della board (`colonne`), `data/competizioni.json` (unica fonte per
risultati, classifiche e numeri), ultim'ora del branch `live`. Regola: risultati mai dai titoli, voci chiamate voci, meglio corto che inventato.
**Dal 2026-09-05 (SEO, `kb/SEO.md` §0.2)**: titolo ≤60 caratteri (diventa il `<title>` così com'è, senza suffisso) e prima frase del lead ≤150 caratteri
(diventa la meta description; oltre, `render_articles` taglia a fine frase o a fine parola con "…"). Prompt aggiornati in entrambe le copie.
Formati e copertine: lunch (ambra, img/cover-lunch.svg) · storia/FOCUS (blu, img/cover-storia.svg) · recap serale (verde, img/cover-recap.svg).
Pubblicano da sole con `bash scripts/pubblica.sh` (token Contents:write).
**Dal 2026-09-03** `render_articles.render_all` scrive `sitemap-articoli.xml` (lastmod = data dell'articolo) e rigenera l'indice `sitemap.xml`:
il commit plumbing include `sitemap.xml, sitemap-articoli.xml` (prompt aggiornati in entrambe le copie). Le hub e le pagine squadra si aggiornano
da sole al giro successivo di `update.yml` (`render_site.py`), quindi le pianificate NON devono lanciarlo.

**I prompt completi sono copiati in `kb/pianificate/*.md`** (identici ai SKILL.md in
`C:/Users/<utente>/Documents/Claude/Scheduled/<nome>/SKILL.md`). Per ricrearle su un'altra macchina: nuova pianificata in Cowork
con lo stesso nome, orario e prompt. Se si modifica un prompt, aggiornare ENTRAMBE le copie.

## 1) recap-mattina-transferbeat — "LUNCH BREAK" — ogni giorno 12:00 (cron: 0 12 * * *)
Punto di metà giornata su campionati e coppe: ieri sera e stanotte (risultati da competizioni.json), notizie del mattino, cosa si gioca
oggi, classifica. Slug lunch-break-AAAA-MM-GG, tipo "lunch", lab LUNCH, col #d98700.

## 2) focus-mercato-transferbeat — "FOCUS" — ogni giorno 16:00 (cron: 0 16 * * *)
La storia del giorno: partita chiave, giocatore in forma, allenatore, caso, o un'ufficialità presente nei dati. Slug storia-<cognome>
o storia-<club>-<tema>, tipo "storia", lab/col/lega del club da data/teams.json. Se esiste già: aggiornare, non duplicare.
(Il nome della pianificata resta "focus-mercato-transferbeat" per non perdere lo storico; il badge sul sito è FOCUS.)

## 3) recap-serale-transferbeat — "RECAP DI GIORNATA" — ogni giorno 20:00 (cron: 0 20 * * *)
Risultati veri del giorno per competizione, classifica, notizie principali, partite in corso o in programma, domani. Alle 20 le partite
serali non sono finite: il prompt impone di dirlo e di non inventare. Slug recap-AAAA-MM-GG, tipo "recap", lab RECAP, col #0a9d57.

## Limite noto (2026-09-03)
Le pianificate girano nel clone `C:/Users/User/Desktop/Calciomercato` (non nella cartella su Drive): il loro `github_token.txt` è quello.
Dal 2026-09-03 `pubblica.sh` recupera da solo un token valido dalle altre copie (vedi `kb/RIPARTENZA.md` §3), ma dopo un "Regenerate"
conviene comunque aggiornare entrambe le copie e i job cron-job.org.
Le pianificate girano solo se il PC è acceso con Cowork aperto: buchi il 29-31/8 e il 2/9. Alternativa da valutare: routine cloud a orario fisso.
