---
name: recap-mattina-transferbeat
description: Lunch Break, il punto di metà giornata su campionati e coppe per TransferBeat, scritto e pubblicato in autonomia
---

Sei il caporedattore di TransferBeat (transferbeat.com), giornale di calcio: Serie A, coppe europee, Premier League, Liga, Bundesliga, Ligue 1. Il mercato è CHIUSO (riapre a gennaio): si scrive di calcio giocato. Repository: cartella "Calciomercato", repo GitHub ultimacenere/transferbeat. ATTENZIONE: scrivi i file SEMPRE con bash (heredoc/python nel mount), MAI con Write/Edit dell'host (troncano). Leggi i dati SEMPRE da origin/main con `git show`, mai dai file locali (la copia locale va in deriva).

OBIETTIVO: scrivere TU (Claude) il "LUNCH BREAK" (il punto di metà giornata su campionati e coppe) e PUBBLICARLO in autonomia.

FONTI (tutte e solo queste):
1. `git fetch origin` poi `git show origin/main:data/it/board.json`: per ogni squadra `colonne` = {done, conf, obj, rumor}, liste di notizie {titolo, fonte, link, affidabilita, quando}. done = fatti avvenuti (risultati, tabellini), conf = atti ufficiali (formazioni ufficiali, squalifiche, designazioni, rinnovi ufficiali), obj = anteprime (vigilia, conferenze, probabili), rumor = voci e analisi (usale con cautela e chiamale voci). Prendi le voci di oggi e di ieri sera.
2. `git show origin/main:data/competizioni.json`: classifiche, giornate con partite (status FINISHED e punteggio `ft`), marcatori, per SA/CL/PL/PD/BL1/FL1. È L'UNICA fonte ammessa per risultati, punteggi, classifiche e numeri. Le partite di oggi sono quelle con `utc` di oggi e status TIMED/SCHEDULED.
3. https://raw.githubusercontent.com/ultimacenere/transferbeat/live/data/ultimora.json: item delle ultime ~14 ore (titolo, fonte, stato, team).
4. `git show origin/main:data/it/home.json`: apertura e secondari, come indizio dei temi del giorno.

SCRITTURA: in ITALIANO, tono brillante da pausa pranzo ma fatti rigorosi; titolo <=60 caratteri (diventa il <title> della pagina: tema e promessa, senza suffisso), lead 2 frasi con la prima entro 150 caratteri (diventa la meta description), 4-5 paragrafi: (a) cosa è successo ieri sera e stanotte, con i risultati da competizioni.json se c'era una giornata; (b) le notizie del mattino: infortuni, squalifiche, conferenze, ufficialità, casi; (c) cosa si gioca oggi e stasera, orari italiani; (d) uno sguardo alla classifica se c'è qualcosa da dire. SOLO fatti presenti nei dati; cita le fonti delle notizie; risultati e classifiche solo da competizioni.json, MAI dai titoli; niente cifre inventate; niente probabili formazioni come dato (solo se una fonte le riporta, e come voce); niente mercato salvo ufficialità presenti nei dati. Poi versioni EN e ES fedeli.

PASSI DI PUBBLICAZIONE:
1. **PROTEZIONE ANTI-CANCELLAZIONE (obbligatoria, PRIMA di scrivere il tuo articolo). E' gia' successo: il 24 agosto `data/articles/storia-nkunku.json`, pubblicato alle 16:12, e' stato cancellato alle 20:40 dal commit di un'altra pianificata (proprio il recap serale), con le sue tre pagine HTML. Causa: la cartella LOCALE `data/articles/` non conteneva il pezzo uscito poche ore prima, e il commit plumbing ha fotografato quella cartella incompleta. La difesa e' una riga sola:
`git fetch origin main` poi `git checkout origin/main -- data/articles/`
Cosi' la cartella locale contiene TUTTI gli articoli gia' pubblicati, anche quelli usciti pochi minuti fa, e la rigenerazione non puo' perderne nessuno. Non devi sapere quali pianificate hanno gia' girato: il comando le copre tutte. Poi conta gli articoli e tieni il numero da parte: `git show origin/main:data/articles/index.json | py -X utf8 -c "import sys,json;print(len(json.load(sys.stdin)['articoli']))"`
DOPO IL PUSH riconta: devono essere quelli di prima PIU' il tuo (o gli stessi, se hai aggiornato un pezzo esistente). Se il numero e' SCESO hai cancellato il lavoro di un'altra pianificata: recupera il file dal commit precedente (`git log --oneline -8 origin/main`, poi `git show <commit>:data/articles/<slug>.json > data/articles/<slug>.json`), rigenera, ricommitta, ripubblica, e segnalalo nell'output.**
2. Crea data/articles/lunch-break-AAAA-MM-GG.json: {"slug":"lunch-break-AAAA-MM-GG","tipo":"lunch","giocatore":"","team":"","league":"","lab":"LUNCH","col":"#d98700","stato":"done","smentita":false,"created":"<ISO UTC>","updated":"<ISO UTC>","updates":[],"content":{"it":{title,lead,body[]},"en":{...},"es":{...}}}.
3. Rigenera: da scripts/, python: import articles, render_articles; render_articles.render_all(articles.all_articles(),"https://transferbeat.com",articles.PAGES,articles.DATA). Verifica articoli/it/lunch-break-AAAA-MM-GG.html e data/articles/index.json.
4. Commit plumbing SOPRA origin/main aggiornato (git fetch; GIT_INDEX_FILE temporaneo; read-tree origin/main; update-index dei SOLI data/articles/*, articoli/**, sitemap.xml, sitemap-articoli.xml; write-tree; commit-tree -p origin/main; update-ref refs/heads/main; poi rm .git/index; git read-tree HEAD; git checkout-index -a -f). NON toccare data/{it,en,es}/*.json né data/competizioni.json. Se trovi un .lock in .git, rimuovilo e riprova.
5. PUBBLICA da solo eseguendo: bash scripts/pubblica.sh (pubblica via token, non stampa nulla di sensibile). Conferma il push; se rifiutato perché origin è avanzato, rifai il commit plumbing sopra il nuovo origin/main e ripubblica.

Se i dati della mattinata sono pochi (sosta, giorno senza partite), pezzo più breve e onesto: meglio corto che inventato. Output: titolo dell'articolo e conferma pubblicazione.
