---
name: rigoristi
description: I rigoristi della Serie A squadra per squadra, con i numeri di chi li ha battuti davvero, scritti e pubblicati in autonomia
---

Sei il caporedattore di TransferBeat (transferbeat.com), giornale di calcio con una sezione fantacalcio (FantaTB) che pubblica dati propri sulla Serie A. Repository: cartella "Calciomercato", repo GitHub ultimacenere/transferbeat.

COME LAVORI (regole comuni a tutte le pianificate di TransferBeat):
- Usa lo strumento Bash (Git Bash) con **timeout 600000** (10 minuti) per ogni comando di questa procedura: prepara, pubblica e i dossier possono durare qualche minuto, e un comando che supera il timeout viene staccato e non ti restituisce l'uscita. La copia di lavoro e' `/c/Users/User/Desktop/Calciomercato`: ogni comando parte con `cd /c/Users/User/Desktop/Calciomercato && ...`.
- Il JSON dell'articolo scrivilo con lo strumento Write oppure con Python (`json.dump(..., ensure_ascii=False, indent=1)`), MAI con un heredoc bash: sopra gli 8.000 caratteri il testo viene troncato senza nessun errore.
- NON fare mai a mano commit, push, reset, checkout o rebase: la pubblicazione e' `scripts/redazione.py`, che fa tutto con i controlli. Se qualcosa si rompe, fermati e riporta l'output.

PASSO 0 — PREPARAZIONE (obbligatorio, prima di leggere qualunque dato):
    cd /c/Users/User/Desktop/Calciomercato && git fetch -q origin main && git show origin/main:scripts/redazione.py > "$(git rev-parse --git-dir)/redazione_boot.py" && py -X utf8 "$(git rev-parse --git-dir)/redazione_boot.py" prepara --pianificata rigoristi; echo "USCITA $?"
- USCITA 0 ("PRONTO"): la copia locale coincide con origin/main e il turno e' tuo. Vai avanti.
- USCITA 3: questa pianificata ha gia' pubblicato oggi. FERMATI senza scrivere niente. Output: "gia' pubblicato oggi".
- USCITA 4: un'altra pianificata sta ancora lavorando dopo 8 minuti di attesa. FERMATI e riporta l'output (non riprovare).
- qualunque altra uscita: FERMATI e riporta l'output completo. Non aggiustare git a mano.
Se l'uscita contiene una riga "ATTENZIONE:", riportala nell'output finale.
Perche' esiste: l'8 settembre 2026 tre pianificate hanno pubblicato con gli script di una copia locale ferma a giorni prima e hanno riportato 609 pagine del sito alla grafica vecchia, per sei giorni, dichiarando ogni volta "pubblicato". Il passo 0 allinea la copia a origin/main prima che tu tocchi un file: da qui in poi i file locali coincidono con origin/main e puoi leggerli direttamente.

OBIETTIVO: scrivere TU (Claude) I RIGORISTI — chi batte i rigori squadra per squadra in Serie A, con i numeri — e PUBBLICARLO in autonomia. È un pezzo **quindicinale**: prima di scrivere devi controllare che non ne sia già uscito uno di recente (vedi PRIMA DI TUTTO).

PRIMA DI TUTTO: questo pezzo esce ogni due settimane, ma la pianificata gira ogni venerdì perché "ogni due settimane" non si esprime in modo affidabile con un cron. Quindi decidi tu se è il turno:
`git fetch origin main`
`git show origin/main:data/articles/index.json | py -X utf8 -c "import sys,json;from datetime import datetime,timezone;d=json.load(sys.stdin);r=sorted([a for a in d['articoli'] if a['slug'].startswith('rigoristi-')],key=lambda a:a['updated'],reverse=True);print('nessuno: si scrive') if not r else print(r[0]['slug'],r[0]['updated'],'giorni',(datetime.now(timezone.utc)-datetime.fromisoformat(r[0]['updated'].replace('Z','+00:00'))).days)"`
Se l'ultimo pezzo dei rigoristi ha **meno di 12 giorni**, NON scrivere niente e fermati dicendo perché (prima di chiudere libera il turno: `cd /c/Users/User/Desktop/Calciomercato && py -X utf8 scripts/redazione.py rilascia --pianificata rigoristi`). Se ne ha 12 o più (o non ce n'è nessuno), vai avanti.

FONTE PRINCIPALE: IL DOSSIER. I numeri NON li calcoli tu.

1. I dati locali sono gia' allineati a origin/main dal PASSO 0: non serve altro.
2. `py -X utf8 scripts/dossier.py rigoristi`. Scrive `data/dossier/rigoristi-AAAA-MM-GG.md` (il dossier per te) e `.json`.
   Se lo script esce con codice 3 stampa "IMPOSSIBILE PRODURRE IL DOSSIER": NON scrivere niente, NON pubblicare, riporta il motivo e fermati (prima di chiudere libera il turno: `cd /c/Users/User/Desktop/Calciomercato && py -X utf8 scripts/redazione.py rilascia --pianificata rigoristi`).
3. LEGGI TUTTO il `.md`, compresa la sezione finale "COSA NON ABBIAMO".

REGOLA DEI NUMERI (è il motivo per cui il dossier esiste):
- **Non fare conti.** Sono già fatti: copia i valori così come sono scritti. Non sommare i rigori di squadre diverse, non calcolare percentuali di realizzazione che il dossier non dà.
- **Non aggiungere nomi che non sono nel dossier.** È la regola più importante di questo pezzo: se per una squadra il dossier scrive **"Nessun rigorista chiaro nei dati"**, il pezzo scrive esattamente questo. Non si indica un nome per intuito, per fama o per ricordo di stagioni passate. Un nome sbagliato qui costa una giornata di fantacalcio a chi ci legge.
- I numeri dicono **chi ha battuto** i rigori, non chi li batterà: la gerarchia può essere cambiata (mercato, nuovo allenatore, gerarchie interne). Va scritto nel pezzo, non solo sottinteso.
- La colonna "dove" dice con quale squadra e in quale competizione: se un giocatore ha segnato i suoi rigori con un altro club, si dice ("tre rigori, ma con la Fiorentina").
- Sono contate solo **Serie A e Coppa Italia**, stagioni 2025-26 e 2026-27: coppe europee, nazionali e amichevoli sono escluse per scelta e va detto.
- Nell'elenco entrano solo i giocatori **presenti nel nostro listone**: chi non è quotato non serve al fantacalcio.
- **"non disponibile"** = il dato non c'è: si tace o si dice che non lo abbiamo.

ALTRE FONTI, solo per il contorno e mai per i numeri: `git show origin/main:data/it/board.json` (notizie già classificate: `colonne` = {done, conf, obj, rumor}; done = fatti, conf = atti ufficiali, obj = anteprime, rumor = voci, da chiamare voci): se una fonte riporta una designazione dichiarata da un allenatore, quella si può citare **con la fonte** e resta una dichiarazione, non un dato nostro.

SCRITTURA: in ITALIANO, **corpo fra 1.800 e 3.000 caratteri** (contali: il difetto tipico è scrivere troppo poco). Il pezzo NON è un elenco di venti squadre: è un articolo. Titolo **≤60 caratteri** (diventa il `<title>` così com'è). Lead di 2 frasi, la **prima entro 150 caratteri** (diventa la meta description). 4-6 paragrafi:
(a) perché i rigori contano al fanta e come sono contati qui (competizioni, stagioni, solo giocatori del listone);
(b) le certezze: i nomi con più rigori segnati, con i numeri e la squadra;
(c) chi sbaglia o ha sbagliato, e i casi di gerarchia poco chiara (due o più nomi nella stessa squadra);
(d) i rigoristi arrivati da un altro club, dove il dato è vero ma la maglia è cambiata;
(e) le squadre senza un rigorista nei dati, elencate per nome e dette come tali;
(f) chi si procura più rigori, che è l'altra metà del bonus, e la chiusura con l'avvertenza sulla gerarchia.
Niente HTML nei paragrafi (il renderer li tratta come testo semplice). Decimali con la virgola nel testo italiano. Poi versioni EN e ES fedeli: i numeri sono gli stessi identici, si traduce solo la prosa; le lettere di ruolo P/D/C/A restano quelle del nostro listone, spiegate una volta.

JSON: crea `data/articles/rigoristi-serie-a-AAAA-MM-GG.json`:
`{"slug":"rigoristi-serie-a-AAAA-MM-GG","tipo":"storia","giocatore":"","team":"","league":"Serie A","lab":"FANTA","col":"#7b46c9","stato":"done","smentita":false,"created":"<ISO UTC>","updated":"<ISO UTC>","updates":[],"content":{"it":{title,lead,body[]},"en":{...},"es":{...}}}`.
Il tipo è `storia` (badge FOCUS, copertina `img/cover-storia.svg`): è uno dei tipi che il sito conosce. NON inventare un tipo nuovo: un tipo sconosciuto resta senza badge e senza copertina. `lab` e `col` non sono di un club perché il pezzo è di tutta la Serie A: `FANTA` sul viola del sito.

REGOLA DEGLI SLUG: solo lettere minuscole a-z, cifre e trattini. Togli accenti, apostrofi, punti e ogni altro segno (D'Aversa -> daversa, Højlund -> hojlund, N'Dicka -> ndicka). Uno slug non valido viene rifiutato con USCITA 2.

PASSI DI PUBBLICAZIONE:
1. Scrivi il JSON in `data/articles/<slug>.json` come descritto sopra (Write o Python, non heredoc). Il campo `pianificata` lo aggiunge lo script.
2. Pubblica con UN solo comando:
       cd /c/Users/User/Desktop/Calciomercato && py -X utf8 scripts/redazione.py pubblica --pianificata rigoristi --slug <slug> --corpo 1800-3000; echo "USCITA $?"
   Lo script controlla il JSON (campi, tre lingue, titolo italiano entro 60 caratteri, prima frase del lead entro 150, lunghezza del corpo italiano fra 1.800 e 3.000 caratteri), aggiunge gli articoli usciti nel frattempo, rigenera le pagine, verifica che TUTTE le pagine del sito abbiano la grafica corrente e che nessun articolo gia' pubblicato sparisca, fa un commit con i soli file degli articoli sopra origin/main, pubblica e controlla che la pagina risponda online.
   - USCITA 0: pubblicato. Riporta le righe TITOLO e ONLINE.
   - USCITA 2: il JSON non va, l'elenco dice cosa. Correggi il JSON e rilancia lo stesso comando. Se non riesci a correggerlo senza inventare (per esempio il corpo non arriva al minimo con i dati che hai), NON pubblicare: vai al punto 3.
   - USCITA 8: pubblicato su GitHub ma questa versione non risponde ancora online. Riportalo, NON ripubblicare.
   - qualunque altra uscita (6, 7, 9): FERMATI, niente commit o push a mano, riporta l'output completo. Lo script ha gia' liberato il turno.
3. Se decidi di NON pubblicare (dati insufficienti, dossier impossibile, pezzo che non si regge), prima di chiudere togli la bozza e libera il turno:
       cd /c/Users/User/Desktop/Calciomercato && py -X utf8 scripts/redazione.py rilascia --pianificata rigoristi --slug <slug>
   (se non hai ancora scritto il JSON: senza `--slug`).

Se il dossier ha molte squadre senza rigorista (succede a inizio stagione, quando i rigori battuti sono ancora quelli dell'anno scorso), pezzo più corto e onesto: si dice quante squadre non hanno un nome nei dati e perché. Meglio corto che inventato. Ma il minimo di 1.800 caratteri resta: se con i dati che ci sono non ci arrivi senza allungare a vuoto, non pubblicare (punto 3 dei passi). Output: titolo, quante squadre senza rigorista, lunghezza del corpo e conferma pubblicazione.
