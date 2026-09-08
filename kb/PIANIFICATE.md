# Pianificate Cowork (da ricreare su ogni macchina)

Nove pianificate alimentano il palinsesto editoriale: **tre generaliste** (calcio giocato, dal 2026-09-03) e **sei di fantacalcio**
(dal 2026-09-07, `kb/FANTATB.md`). Ogni pezzo esce in IT/EN/ES, quindi tre pagine per articolo.
Regola comune: risultati mai dai titoli, voci chiamate voci, **meglio corto che inventato**.
**Dal 2026-09-05 (SEO, `kb/SEO.md` §0.2)**: titolo ≤60 caratteri (diventa il `<title>` così com'è, senza suffisso) e prima frase del lead ≤150 caratteri
(diventa la meta description; oltre 155, `render_articles` taglia a fine frase o a fine parola con "…").
Pubblicano da sole con `bash scripts/pubblica.sh` (token Contents:write).
`render_articles.render_all` scrive anche `sitemap-articoli.xml` e rigenera l'indice `sitemap.xml`: il commit plumbing include
`sitemap.xml, sitemap-articoli.xml`. Le hub e le pagine squadra si aggiornano da sole al giro successivo di `update.yml`
(`render_site.py`), quindi le pianificate NON devono lanciarlo.

**I prompt completi sono in `kb/pianificate/*.md`** (identici ai `SKILL.md` in
`C:/Users/<utente>/Documents/Claude/Scheduled/<nome>/SKILL.md`). Per ricrearle su un'altra macchina: nuova pianificata in Cowork
con lo stesso nome, lo stesso orario e lo stesso prompt, copiato dal `.md` di questa cartella. Se si modifica un prompt, aggiornare ENTRAMBE le copie.

## Calendario (ora italiana)

| Ora | Giorni | Pianificata | Badge | Legge |
|---|---|---|---|---|
| 09:00 | ogni giorno | `giocatore-del-giorno` | FOCUS | dossier `giocatore` |
| 10:30 | martedì | `migliori-e-peggiori` | FOCUS | dossier `migliori` |
| 12:00 | ogni giorno | `recap-mattina-transferbeat` (LUNCH BREAK) | LUNCH BREAK | board, competizioni, ultimora |
| 14:00 | mercoledì | `confronto-x-o-y` | FOCUS | dossier `confronto` |
| 14:00 | giovedì | `partita-di-cartello` | FOCUS | dossier `cartello` |
| 14:00 | sabato | `sorprese` | FOCUS | dossier `sorprese` |
| 15:00 | venerdì | `rigoristi` (esce ogni due settimane, vedi sotto) | FOCUS | dossier `rigoristi` |
| 16:00 | ogni giorno | `focus-mercato-transferbeat` (FOCUS) | FOCUS | board, competizioni, ultimora |
| 20:00 | ogni giorno | `recap-serale-transferbeat` (RECAP) | RECAP DI GIORNATA | board, competizioni, ultimora |

Cron: `0 9 * * *` · `30 10 * * 2` · `0 12 * * *` · `0 14 * * 3` · `0 14 * * 4` · `0 14 * * 6` · `0 15 * * 5` · `0 16 * * *` · `0 20 * * *`.
Nessuna sovrapposizione: fra due pianificate passa almeno un'ora e mezza, e ogni giorno ne girano al massimo cinque (martedì: 09:00, 10:30, 12:00, 16:00, 20:00).

## 1) recap-mattina-transferbeat — "LUNCH BREAK" — ogni giorno 12:00
Punto di metà giornata su campionati e coppe: ieri sera e stanotte (risultati da `competizioni.json`), notizie del mattino, cosa si gioca
oggi, classifica. Slug `lunch-break-AAAA-MM-GG`, tipo `lunch`, lab LUNCH, col `#d98700`.

## 2) focus-mercato-transferbeat — "FOCUS" — ogni giorno 16:00
La storia del giorno: partita chiave, giocatore in forma, allenatore, caso, o un'ufficialità presente nei dati. Slug `storia-<cognome>`
o `storia-<club>-<tema>`, tipo `storia`, lab/col/lega del club da `data/teams.json`. Se esiste già: aggiornare, non duplicare.
(Il nome della pianificata resta "focus-mercato-transferbeat" per non perdere lo storico; il badge sul sito è FOCUS.)

## 3) recap-serale-transferbeat — "RECAP DI GIORNATA" — ogni giorno 20:00
Risultati veri del giorno per competizione, classifica, notizie principali, partite in corso o in programma, domani. Alle 20 le partite
serali non sono finite: il prompt impone di dirlo e di non inventare. Slug `recap-AAAA-MM-GG`, tipo `recap`, lab RECAP, col `#0a9d57`.

## 4) giocatore-del-giorno — ogni giorno 09:00
Approfondimento su un giocatore: stagione scorsa, questo inizio, il confronto per 90 minuti, i nostri numeri FantaTB, il contesto di squadra.
Corpo 2.500-4.000 caratteri. Il giocatore lo sceglie lo script in rotazione, dal più costoso del listone a scendere, soglia 8 crediti.
Slug `giocatore-del-giorno-<cognome>-AAAA-MM-GG` (il suffisso con la data evita di sovrascrivere il FOCUS, che usa `storia-<cognome>`),
tipo `storia`, lab/col del club.

## 5) migliori-e-peggiori — martedì 10:30
I migliori e i peggiori fantavoti FantaTB della giornata appena chiusa. Corpo 1.800-3.000 caratteri.
Slug `migliori-e-peggiori-gN`, tipo `storia`, lab FANTA, col `#7b46c9`.
**Perché martedì e non lunedì** (il committente aveva chiesto il lunedì): quando c'è il posticipo del lunedì sera la giornata non è chiusa,
e il dossier — che usa solo giornate chiuse — scriverebbe di quella di otto giorni prima. Misurato lunedì 2026-09-07: giornata 3 ancora
`live` con 8 partite su 10, ultima chiusa la 2. Martedì mattina la giornata è sempre completa. Se si preferisce comunque il lunedì,
va spostata a **lunedì 23:30** (dopo la fine del posticipo e dopo il giro di `update.yml` che calcola i voti), con più rischio di PC spento.

## 6) confronto-x-o-y — mercoledì 14:00
Due giocatori stesso ruolo e quotazione entro 3 crediti, confronto secco: chi schierare. Corpo 1.800-3.000 caratteri. Il pezzo deve
arrivare a una risposta. Slug `x-o-y-<cognome1>-<cognome2>-AAAA-MM-GG`, tipo `storia`, lab FANTA, col `#7b46c9`.

## 7) partita-di-cartello — giovedì 14:00
La partita clou del turno in arrivo letta in ottica fantacalcio: probabili formazioni, chi fa bonus, chi rischia malus, rigoristi,
indisponibili. Corpo 2.500-4.000 caratteri. La partita la sceglie lo script (somma più bassa delle posizioni in classifica).
Slug `partita-di-cartello-<casa>-<ospite>-gN`, tipo `storia`, lab/col del club di casa, `stato` `obj` (è un'anteprima).

## 8) rigoristi — venerdì 15:00, ma esce ogni due settimane
Chi batte i rigori squadra per squadra, con i numeri di Serie A e Coppa Italia. Corpo 1.800-3.000 caratteri.
Slug `rigoristi-serie-a-AAAA-MM-GG`, tipo `storia`, lab FANTA, col `#7b46c9`.
**Il "ogni due settimane" non è nel cron ma nel prompt**: un cron biosettimanale affidabile non esiste (con giorno del mese e giorno della
settimana entrambi ristretti, la maggior parte dei cron li mette in OR e la pianificata partirebbe molto più spesso). Quindi gira ogni
venerdì e la prima cosa che fa è cercare in `data/articles/index.json` l'ultimo `rigoristi-`: se ha meno di 12 giorni si ferma senza scrivere.

## 9) sorprese — sabato 14:00
Chi rende più e chi meno di quanto costa: fantamedia rapportata alla quotazione, e soprattutto scarto dalla mediana dei pari ruolo della
stessa fascia di prezzo. Corpo 1.800-3.000 caratteri. Slug `sorprese-fantacalcio-AAAA-MM-GG`, tipo `storia`, lab FANTA, col `#7b46c9`.

## I dossier: i numeri li prepara `scripts/dossier.py`

Decisione del 2026-09-07: **i numeri li prepara uno script, la prosa la scrive Cowork.** I sei formati di fantacalcio non leggono JSON
grezzi e non fanno aritmetica: leggono un dossier già calcolato, già arrotondato e già etichettato in italiano.

    py -X utf8 scripts/dossier.py {giocatore|cartello|migliori|confronto|rigoristi|sorprese}

Scrive `data/dossier/<formato>-AAAA-MM-GG.md` (per chi scrive) e `.json` (gli stessi dati per un programma). Opzioni utili: `--dry`
(stampa a video e non scrive niente), `--data AAAA-MM-GG`, `--out`, più le soglie (`--soglia-prezzo`, `--min-minuti-prev`,
`--min-minuti-cur`, `--tolleranza-prezzo`, `--min-presenze`, `--min-minuti-sorprese`, `--min-fascia`).

Cose da sapere, tutte verificate il 2026-09-07:
- **Legge i file LOCALI del repo, non `origin/main`.** Per questo ogni prompt comincia allineando i dati:
  `git fetch origin main` e poi, per ogni file di `data/fanta`, `data/stats` e `data/competizioni.json`, `git show origin/main:<file> > <file>`
  (sono 15 file, verificato il 2026-09-07). Senza questo passo il dossier può calcolare numeri veri su dati vecchi, che è il modo peggiore
  di sbagliare. Effetto collaterale da conoscere: `git show` scrive quei file con fine riga LF, quindi finché il giro non arriva al
  `git checkout-index -a -f` finale `git status` li mostra come modificati (è il solito attrito con `autocrlf`, vedi `kb/RIPARTENZA.md`).
  Sono dati di produzione: nessuna pianificata e nessuna sessione deve committarli da lì.
- **Se manca il presupposto del pezzo, esce con codice 3, non scrive niente e dice perché** (per esempio `migliori` senza una giornata
  chiusa). I prompt impongono di fermarsi: nessun articolo è meglio di un articolo con i numeri sbagliati.
- **Dove un dato non c'è scrive "non disponibile"**, dove i minuti sono troppo pochi scrive "campione troppo piccolo". Nessuno dei due
  va sostituito con uno zero o con una stima: è scritto in tutti e sei i prompt.
- **`giocatore` e `confronto` tengono una rotazione** in `data/dossier/_stato-rotazione.json`: chi è già uscito non torna finché il giro
  non si chiude, e due giri nello stesso giorno danno lo stesso giocatore e gli stessi numeri (l'unica differenza è una riga di nota in più
  nel `.md`). La rotazione avanza solo nei giri **senza** `--dry`.
- **`data/dossier/` non è nel repo e non va committata**: il commit plumbing tocca solo `data/articles/*`, `articoli/**` e le due sitemap.
  Lo stato della rotazione vive quindi solo sul PC che ospita le pianificate: se quella cartella si perde, la rotazione riparte dall'alto.
- **L'xG del singolo giocatore non esiste nei nostri dati** (solo di squadra e per partita): tutti e sei i dossier lo ripetono nella
  sezione "COSA NON ABBIAMO", e i prompt vietano di scriverlo.

## La protezione contro le cancellazioni (2026-09-08, in tutti e NOVE i prompt — verificato uno per uno)

Il 24 agosto `data/articles/storia-nkunku.json`, pubblicato dal FOCUS alle 16:12, è stato **cancellato alle 20:40**
dal commit del RECAP, con le sue tre pagine HTML. È l'unico file di articolo sparito nella storia del repo.

**La causa vera** non era un `origin/main` vecchio: era la cartella LOCALE `data/articles/`, che non conteneva il
pezzo delle 16:12. Il commit plumbing ha fotografato quella cartella incompleta e il file è uscito dall'albero.

**La difesa è una riga, non una lista da controllare a occhio.** Prima di rigenerare le pagine, ogni prompt esegue:

```
git fetch origin main
git checkout origin/main -- data/articles/
```

Così la cartella locale contiene TUTTI gli articoli già pubblicati, compresi quelli usciti pochi minuti prima, e
`render_all` non può perderne nessuno. Il JSON appena scritto non viene toccato: è un file nuovo, git non lo conosce
ancora. Dopo il push si ricontano gli articoli su `origin/main`: se il numero è SCESO, si è cancellato il lavoro di
un'altra pianificata e va recuperato subito dal commit precedente.

**Due errori commessi nella prima stesura di questa stessa protezione**, da non rifare:

1. Chiedeva di verificare che ci fossero «gli articoli delle altre pianificate che hanno già girato», elencandole
   tutte. Ma la prima del giorno gira alle 09:00 e quelle dopo non esistono ancora: con l'istruzione «MAI proseguire»
   quel giro non avrebbe pubblicato mai. La domanda giusta non è *chi ha già pubblicato*, è *non sto cancellando niente*.
2. Era finita DOPO la rigenerazione. In quella posizione il `checkout` riporta indietro `data/articles/index.json` e
   l'articolo appena scritto sparisce dall'indice e dalla sitemap, lasciando la pagina HTML orfana.
   **Deve stare prima di `render_all`**, ed è così in tutti e nove (verificato riga per riga).

## Limiti noti

**Il PC acceso.** Le pianificate girano solo se il PC del committente è acceso con Cowork aperto, nel clone
`C:/Users/User/Desktop/Calciomercato` (non nella cartella su Drive): il loro `github_token.txt` è quello. Dal 2026-09-03 `pubblica.sh`
recupera da solo un token valido dalle altre copie (vedi `kb/RIPARTENZA.md` §3), ma dopo un "Regenerate" conviene aggiornare entrambe
le copie e i job cron-job.org.
**Ogni pianificata in più moltiplica il rischio.** Misurato il 2026-09-07 sui due formati datati (lunch break e recap serale, che hanno
la data nello slug): dal 17 agosto al 7 settembre, 19 giorni su 22 con entrambi i pezzi, **tre giorni interi persi (29, 30 e 31 agosto)**.
Il FOCUS non è misurabile allo stesso modo perché aggiorna file già esistenti invece di crearne di nuovi. Con nove pianificate al giorno
di slot ce ne sono molti di più, e un giorno di PC spento adesso costa fino a cinque pezzi invece di tre. Non è un motivo per non farle:
è il motivo per cui i formati settimanali sono distribuiti su giorni diversi (nessun giorno perde più di un formato settimanale) e per cui
`rigoristi` decide da solo se è il suo turno invece di affidarsi al calendario. L'alternativa vera resta una routine cloud a orario fisso.
