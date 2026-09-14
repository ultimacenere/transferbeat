# Pianificate degli articoli

Dieci pianificate alimentano il palinsesto editoriale: **tre generaliste** (calcio giocato, dal 2026-09-03), **sei di fantacalcio**
(dal 2026-09-07, `kb/FANTATB.md`) e il **DOPOPARTITA** delle 23 (dal 2026-09-14). Ogni pezzo esce in IT/EN/ES, quindi tre pagine
per articolo. Regola comune: risultati mai dai titoli, voci chiamate voci, **meglio corto che inventato**.
**SEO (`kb/SEO.md` §0.2)**: titolo ≤60 caratteri (diventa il `<title>` così com'è) e prima frase del lead ≤150 (diventa la meta
description). Dal 2026-09-14 non è più una raccomandazione: `scripts/redazione.py` rifiuta il JSON che sfora.

**I prompt completi sono in `kb/pianificate/*.md`: sono la fonte.** Il nome del file (senza `.md`) è anche l'id della pianificata e
il valore di `--pianificata`. Se si modifica un prompt, va aggiornata anche la pianificata registrata (vedi sotto dove vive).

## Dove girano (dal 2026-09-14)

**Nello scheduler della app Claude (sezione Code), non più in Cowork.** Motivo misurato: dal 9 al 14 settembre le tre pianificate
Cowork non hanno prodotto un solo articolo, mentre nello stesso periodo lo scheduler della app ha eseguito regolarmente il suo
compito serale (9, 10, 11 e 14 settembre). In più lo scheduler della app si può creare, modificare e **controllare** da una sessione
(`list_scheduled_tasks`, e per ogni pianificata lo storico delle esecuzioni con esito), cosa che per Cowork non è possibile.
Vivono in `C:/Users/User/.claude/scheduled-tasks/<nome>/SKILL.md`; il cron è in ora LOCALE del PC.
Le tre copie Cowork (`C:/Users/User/Documents/Claude/Scheduled/<nome>/SKILL.md`) sono state **dismesse**: il loro prompt ora dice
solo di non fare niente (originali in `backup/pianificate-2026-09-14/`). Se tornassero a girare con il prompt vecchio, il controllo
«già pubblicato oggi» di `redazione.py` non le fermerebbe (non lo usano): per questo il prompt è stato svuotato. Vanno comunque
eliminate dall'interfaccia di Cowork.

**Limite che resta:** la app deve essere aperta. Se è chiusa all'orario, la pianificata parte alla riapertura.
Per i tre slot quotidiani c'è la rete di sicurezza `palinsesto.yml` su GitHub Actions (vedi "Limiti noti").

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
| 23:00 | ogni giorno, esce solo se c'è una partita della sera | `dopopartita` | DOPOPARTITA | `scripts/dopopartita.py` (API-Football, al momento) |

Cron: `0 9 * * *` · `30 10 * * 2` · `0 12 * * *` · `0 14 * * 3` · `0 14 * * 4` · `0 14 * * 6` · `0 15 * * 5` · `0 16 * * *` · `0 20 * * *` · `0 23 * * *`.
Fra due pianificate passano almeno un'ora e mezza; se una sfora, la successiva aspetta il turno (vedi sotto).

## La procedura comune: `scripts/redazione.py` (dal 2026-09-14)

**Perché esiste.** L'8 settembre le tre pianificate del giorno (12:45, 16:15, 20:42) hanno rigenerato gli articoli con gli script di
una copia locale ferma a qualche giorno prima, senza la grafica nuova: **609 pagine di `articoli/` sono tornate alla veste
precedente e ci sono rimaste sei giorni**, mentre ognuna dichiarava "pubblicato". `guard.py` lo avrebbe visto (609 pagine) ma le
pianificate non lo lanciano. La procedura di pubblicazione stava scritta a parole in nove prompt e ognuno la eseguiva a modo suo.
Ora è codice, uguale per tutti.

- **Passo 0 — `prepara --pianificata NOME`.** Lo script si prende da `origin/main` (`git show origin/main:scripts/redazione.py >
  .git/redazione_boot.py`), perché una copia vecchia potrebbe non averlo. Poi: fetch; se questa pianificata ha già pubblicato per il
  **giorno di redazione** di oggi esce con **3** (campo `giorno` nel JSON: NON l'ora di pubblicazione, altrimenti un Dopopartita delle
  23 uscito alle 00:10 bloccherebbe quello della sera dopo); prende il **turno** `.git/redazione.lock` (creazione atomica, una
  pianificata alla volta, attesa massima 8 minuti, poi **4**); salva in `refs/backup/redazione/` le modifiche ai file tracciati e un
  eventuale commit locale mai pubblicato (tenuti 14 giorni); **sposta in `.git/redazione-avanzi/<data>/` i file non tracciati sotto
  `data/articles/` e `articoli/`** (bozze abbandonate da un giro fallito: lasciate lì, bloccherebbero ogni giro successivo con 7);
  **riallinea la copia a `origin/main` con un reset**; controlla la grafica delle pagine già su main.
- **`pubblica --pianificata NOME --slug SLUG [--corpo MIN-MAX]`.** Valida il JSON senza importare niente del sito (slug solo a-z,
  cifre e trattini; date ISO **con fuso**; `stato`; tre lingue con titolo, lead e paragrafi di testo; titolo italiano ≤60; prima frase
  del lead ≤150; corpo nel range; un `--corpo` scritto male è un errore, non un controllo spento); aggiunge `pianificata` e `giorno`.
  Poi, a ogni tentativo: fetch, e **se main è avanzato dal passo 0 riallinea la copia prima di rigenerare**; riprende da main gli
  articoli e sposta gli avanzi; **rigenera e controlla in un SOTTOPROCESSO nuovo** (`_rigenera`), perché un processo che ha già
  importato i moduli continuerebbe a usare quelli vecchi anche dopo il riallineamento — sarebbe l'incidente dell'8 settembre dentro lo
  script. Il sottoprocesso rifiuta con **6** se una qualsiasi pagina non ha la grafica di `origin/main` (impronta presa da
  `origin/main`, non dal file locale) e con **7** se gli articoli non tornano: attesi = JSON su main + quello nuovo, con l'elenco dei
  file spariti o in più. Il commit contiene i SOLI file consentiti (i file del pezzo, gli indici, le sitemap, le pagine degli articoli
  già su main), è verificato prima del push (niente cancellazioni, anche mascherate da rinomina; la pagina nel commit deve avere la
  grafica di main) e se l'articolo è identico a quello pubblicato non si committa (**2**). Push con `pubblica.sh HEAD:refs/heads/main`
  (il ramo senza rebase), verifica che il commit sia davvero in main, IndexNow, e **verifica online della VERSIONE** (grafica
  corrente e `dateModified` uguale a `updated`: una pagina vecchia in cache non basta) per al massimo 4 minuti, poi **8**.
  Ritenta fino a 3 volte se main avanza. Sulle uscite 6, 7, 8, 9 e sugli errori imprevisti il turno si libera da solo.
  `--prova` fa tutto tranne commit e push, e lascia bozza e turno per la pubblicazione vera.
- **`rilascia --pianificata NOME [--slug SLUG]`** libera il turno (solo il proprio) e, con `--slug`, toglie la bozza non pubblicata.
  **`stato`** mostra turno, distanza da main e avanzi.
- **Nessuna attesa supera 8 minuti**: le pianificate lanciano i comandi con lo strumento Bash (timeout massimo 10 minuti); un comando
  più lungo viene staccato e la pianificata non riceve mai l'uscita. Per lo stesso motivo il turno si considera abbandonato dopo 60
  minuti senza segni di vita (la data di modifica del file del turno, aggiornata da ogni comando e da `dopopartita.py` mentre aspetta),
  non 60 minuti dall'inizio.
- Codici di uscita: 0 fatto · 2 JSON o argomenti non validi (si corregge e si rilancia) · 3 già pubblicato per oggi · 4 turno occupato ·
  5 turno non preso · 6 grafica non uniforme · 7 articoli che non tornano · 8 pubblicato ma versione non online · 9 git, rete o imprevisto.

**Perché le pianificate Cowork si erano fermate dal 9 settembre (trovato il 14).** Nella copia del Desktop c'era
`.git/HEAD.lock` datato **8 settembre 20:42**, lo stesso minuto dell'ultimo commit del RECAP: quel commit si è interrotto a metà e
ha lasciato il lock. Da allora ogni pianificata, arrivata al commit, falliva su "cannot lock ref 'HEAD'", e per sei giorni non è
uscito un articolo senza che nulla lo segnalasse. `redazione.py` ora toglie a ogni riallineamento i lock di git più vecchi di 10
minuti (in `.git/`, `refs/heads/`, `refs/remotes/origin/`) e lo scrive in una riga ATTENZIONE.

**Come è stato provato.** Una copia isolata con remoto finto il cui main contiene gli script nuovi, e copia di partenza vecchia e
sporca come quella del Desktop: 20 casi, fra cui bozza abbandonata spostata, turno conteso, `--corpo` scritto male, data senza fuso,
prova che conserva la bozza, **main che avanza fra passo 0 e pubblicazione** (commit finito sopra il nuovo main), pezzo di ieri uscito
dopo mezzanotte che non blocca quello di oggi, sito con una sola pagina sulla grafica vecchia (rifiutato, turno liberato).
**La revisione avversaria del 14 settembre** (46 agenti, 43 rilievi, 41 confermati) ha trovato sulla prima versione i difetti che
questa versione chiude: rigenerazione con moduli vecchi dopo un riallineamento, bozze abbandonate che bloccavano tutto a catena,
"già pubblicato" deciso dall'ora di uscita, attese più lunghe del timeout di Bash, turno non atomico, verifica online ingannabile da
una pagina in cache, `--corpo` ignorato in silenzio, commit identico dichiarato pubblicato, cancellazioni mascherate da rinomina.
Nella prima stesura la prova aveva già trovato che `commit-tree` falliva dove git non ha un'identità: ora lo script la imposta.

**La vecchia protezione contro le cancellazioni** (il `git checkout origin/main -- data/articles/` prima di rigenerare, nata dopo che
il 24 agosto il RECAP delle 20:40 cancellò `storia-nkunku.json` pubblicato alle 16:12) è ora dentro `pubblica`, insieme al conteggio:
non va più scritta nei prompt.

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

## 10) dopopartita — ogni giorno 23:00, esce solo se c'è una partita della sera
La partita o le partite della sera raccontate a fischio finale: gol con minuto, episodi (rigori, espulsioni, VAR), i numeri che
spiegano la partita (tiri, xG, possesso), migliori e peggiori per voto statistico, bonus e malus del regolamento FantaTB, classifica
di Serie A dopo la serata, le altre partite della sera in breve. Slug `dopopartita-AAAA-MM-GG`, tipo `dopopartita` (badge
DOPOPARTITA, copertina `img/cover-dopopartita.svg`, colore `#2c0f57`), corpo 2.000–3.500 caratteri.
**I dati NON vengono da `data/competizioni.json`**: alle 23 quel file è fermo al giro delle 22 di `update.yml`, partito con le partite
delle 20:45 ancora in corso. `scripts/dopopartita.py` li prende da API-Football in quel momento e, se una partita non è finita,
**aspetta** invece di lasciare un buco da riempire a occhio: `--attendi 8` per esecuzione (il timeout di Bash è 10 minuti), uscita
**12** "rilancia" finché non passa il tempo massimo della partita (calcio d'inizio + 2 ore e 45), poi procede con le finite. Il giorno
raccontato è quello del turno, anche se il rilancio arriva dopo mezzanotte. Scrive
`data/dossier/dopopartita-AAAA-MM-GG.md/.json` (la cartella `data/dossier/` è in `.gitignore`). Competizioni: Serie A; Italia
(qualificazioni, Nations League, fasi finali, amichevoli); Champions League; Coppa Italia e Supercoppa; Europa e Conference League
solo con squadre italiane (lette da `data/stats/teams.json`); Premier League, Liga, Bundesliga e Ligue 1 nel paragrafo finale.
"Della sera" = calcio d'inizio dalle 17:30 italiane (una partita delle 18 non è ancora nei dati del RECAP delle 20).
Uscite: 0 dossier pronto · 10 nessuna partita serale · 11 nessuna finita entro il tempo massimo · 12 ancora in corso, rilanciare ·
1 errore (dettaglio mancante di una partita, `teams.json` illeggibile: mai un dossier incompleto con uscita 0).
Ordine: Serie A, Italia, Champions **con italiane**, Coppa Italia, coppe europee con italiane; la Champions senza italiane va fra
"le altre" (una sera di coppa ne ha nove). Correzioni dalla revisione: la lotteria dei rigori è separata dai gol; gli autogol hanno
la squadra del giocatore e quella che ne beneficia; la doppia ammonizione non diventa "rosso diretto"; i gol subiti dei portieri,
che API-Football non dà in Champions e Coppa Italia, si ricavano se in porta ne ha giocato uno solo, altrimenti si dichiarano
mancanti; i nomi sono completi per id; la classifica è verificata contando le partite giocate PRIMA di stasera
(`data/stats/teams.json`) più una, perché il numero della giornata non vede i recuperi.
Controlli espliciti nel dossier: la sequenza dei gol deve portare al risultato ufficiale (se no, avviso e niente attribuzioni); la
classifica si scrive solo se le squadre di stasera risultano con la giornata già contata (l'API riporta come aggiornamento la
mezzanotte, quindi l'orario non basta); gli orari italiani si calcolano dal timestamp della partita. Quest'ultimo è nato da un
errore trovato alla prima prova: il dettaglio per id restituisce l'ora UTC e il dossier diceva "Napoli-Bologna ore 16:00" invece
delle 18:00.

## I dossier: i numeri li prepara `scripts/dossier.py`

Decisione del 2026-09-07: **i numeri li prepara uno script, la prosa la scrive Cowork.** I sei formati di fantacalcio non leggono JSON
grezzi e non fanno aritmetica: leggono un dossier già calcolato, già arrotondato e già etichettato in italiano.

    py -X utf8 scripts/dossier.py {giocatore|cartello|migliori|confronto|rigoristi|sorprese}

Scrive `data/dossier/<formato>-AAAA-MM-GG.md` (per chi scrive) e `.json` (gli stessi dati per un programma). Opzioni utili: `--dry`
(stampa a video e non scrive niente), `--data AAAA-MM-GG`, `--out`, più le soglie (`--soglia-prezzo`, `--min-minuti-prev`,
`--min-minuti-cur`, `--tolleranza-prezzo`, `--min-presenze`, `--min-minuti-sorprese`, `--min-fascia`).

Cose da sapere, tutte verificate il 2026-09-07:
- **Legge i file LOCALI del repo.** Dal 2026-09-14 non serve più allinearli a mano: il passo 0 (`redazione.py prepara`) riporta
  l'intera copia a `origin/main` prima che il dossier parta.
- **Se manca il presupposto del pezzo, esce con codice 3, non scrive niente e dice perché** (per esempio `migliori` senza una giornata
  chiusa). I prompt impongono di fermarsi: nessun articolo è meglio di un articolo con i numeri sbagliati.
- **Dove un dato non c'è scrive "non disponibile"**, dove i minuti sono troppo pochi scrive "campione troppo piccolo". Nessuno dei due
  va sostituito con uno zero o con una stima: è scritto in tutti e sei i prompt.
- **`giocatore` e `confronto` tengono una rotazione** in `data/dossier/_stato-rotazione.json`: chi è già uscito non torna finché il giro
  non si chiude, e due giri nello stesso giorno danno lo stesso giocatore e gli stessi numeri (l'unica differenza è una riga di nota in più
  nel `.md`). La rotazione avanza solo nei giri **senza** `--dry`.
- **`data/dossier/` non è nel repo** (è in `.gitignore`) e non entra nei commit: `redazione.py pubblica` committa solo i file degli articoli.
  Lo stato della rotazione vive quindi solo sul PC che ospita le pianificate: se quella cartella si perde, la rotazione riparte dall'alto.
- **L'xG del singolo giocatore non esiste nei nostri dati** (solo di squadra e per partita): tutti e sei i dossier lo ripetono nella
  sezione "COSA NON ABBIAMO", e i prompt vietano di scriverlo.

## Limiti noti

**La rete di sicurezza.** Dal 2026-09-14 `palinsesto.yml` è ACCESO: se uno dei tre slot quotidiani (12, 16, 20) resta vuoto,
dopo 90 minuti pubblica un bollettino di dati. Si spegne con la variabile di repository `PALINSESTO_ATTIVO = false` (il token delle
sessioni non può scrivere variabili, per questo l'interruttore è stato invertito nel codice). Riconosce lo slot coperto dalla firma
`pianificata`: il Giocatore del giorno, anche lui di tipo `storia`, non basta più a far credere coperto il FOCUS delle 16.
Il DOPOPARTITA e i formati settimanali NON hanno rete: se la app è chiusa, escono alla riapertura o non escono.

**Il PC acceso.** Le pianificate girano solo se il PC del committente è acceso con la app aperta, nel clone
`C:/Users/User/Desktop/Calciomercato` (non nella cartella su Drive): il loro `github_token.txt` è quello. Dal 2026-09-03 `pubblica.sh`
recupera da solo un token valido dalle altre copie (vedi `kb/RIPARTENZA.md` §3), ma dopo un "Regenerate" conviene aggiornare entrambe
le copie e i job cron-job.org.
**Ogni pianificata in più moltiplica il rischio.** Misurato il 2026-09-07 sui due formati datati (lunch break e recap serale, che hanno
la data nello slug): dal 17 agosto al 7 settembre, 19 giorni su 22 con entrambi i pezzi, **tre giorni interi persi (29, 30 e 31 agosto)**.
Il FOCUS non è misurabile allo stesso modo perché aggiorna file già esistenti invece di crearne di nuovi. Con nove pianificate al giorno
di slot ce ne sono molti di più, e un giorno di PC spento adesso costa fino a cinque pezzi invece di tre. Non è un motivo per non farle:
è il motivo per cui i formati settimanali sono distribuiti su giorni diversi (nessun giorno perde più di un formato settimanale) e per cui
`rigoristi` decide da solo se è il suo turno invece di affidarsi al calendario. L'alternativa vera resta una routine cloud a orario fisso.
