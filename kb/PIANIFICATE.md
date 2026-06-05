# Pianificate Cowork (da ricreare su ogni macchina)
Tre pianificate alimentano il palinsesto editoriale (3 articoli/giorno = 9 pagine IT/EN/ES).
Formati e copertine: lunch (ambra, img/cover-lunch.svg) · storia/focus (blu, img/cover-storia.svg) · recap serale (verde, img/cover-recap.svg).
I prompt completi e aggiornati sono nei file SKILL.md in C:\Users\<utente>\Documents\Claude\Scheduled\<taskId>\ — per ricrearle su un'altra macchina, copiare il prompt dal SKILL.md corrispondente (o chiedere a Claude di rigenerarle da questa KB).

## 1) recap-mattina-transferbeat — "LUNCH BREAK" — ogni giorno 12:00 (cron: 0 12 * * *)
Punto di metà giornata. Slug lunch-break-AAAA-MM-GG, tipo "lunch", lab LUNCH, col #d98700.
Fonti: nomi di oggi da origin/main:data/it/board.json + ultim'ora live (ultime ~14h). Claude scrive (no Groq), IT+EN+ES, regole anti-invenzione, fonti citate. Render con render_articles, commit plumbing su origin/main, push se possibile altrimenti avviso pubblica-ora.bat.

## 2) focus-mercato-transferbeat — "FOCUS MERCATO" — ogni giorno 16:00 (cron: 0 16 * * *)
Articolo-storia sulla trattativa più rilevante del giorno (curatela: stato avanzato > club di peso > numero fonti > clamore). Slug storia-<cognome>, tipo "storia", team/league/lab/col del club da data/teams.json. Se l'articolo esiste già per quel giocatore: AGGIORNARLO (sviluppi + updated), non duplicare. IT+EN+ES.

## 3) recap-serale-transferbeat — "RECAP DI GIORNATA" — ogni giorno 20:00 (cron: 0 20 * * *)
Recap completo della giornata. Slug recap-AAAA-MM-GG, tipo "recap", lab RECAP, col #0a9d57. Stesse regole.
