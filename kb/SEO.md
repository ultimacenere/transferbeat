# SEO e GEO — regola, diagnosi e piano di intervento
*Creato il 2026-09-03. Da leggere PRIMA di qualsiasi lavoro sul sito. Vale per TransferBeat e per FantaTB.*

## 0. LA REGOLA (decisione del committente, 2026-09-03)
**Il posizionamento su Google e la citabilità dalle intelligenze artificiali (GEO) hanno la massima priorità su tutto il resto.**
Ogni pagina nuova, ogni script che genera HTML, ogni articolo, ogni funzione di FantaTB nasce rispettando questa lista:
1. **Contenuto nell'HTML statico**, non solo caricato via JavaScript: testo, tabelle, link devono esistere nel file servito.
2. **Title con tema e promessa** (max ~60 caratteri) e **meta description specifica** (max ~155), diversi per ogni pagina.
3. **Una URL per lingua**: niente `?lang=` come versione "indicizzabile"; le pagine hub sono solo in italiano (decisione, §3.2).
4. **Canonical proprio**, breadcrumb, H1 unico e testuale, link interni verso squadre, competizioni e articoli correlati.
5. **Dati strutturati** coerenti: NewsArticle con `author` di tipo Person, Organization con `founder`, BreadcrumbList, SportsTeam,
   SportsEvent, Dataset per listone e voti, FAQPage dove ci sono domande.
6. **Sitemap con lastmod vero** (data reale di modifica), spezzata per tipo, e ping **IndexNow** a ogni pubblicazione.
7. **Dati originali prima delle riscritture**: classifiche, listone, voti FantaTB, titolarità, infortuni sono contenuto proprio e
   citabile; un riassunto di notizie altrui no.
8. **Entità riconoscibile**: pagina chi siamo, persone con nome, profili collegati (`sameAs`), `llms.txt` aggiornato.
9. Ogni consegna al committente dice cosa ha fatto per il posizionamento; se non c'è nulla, lo dice.

## 1. Dove sono i report
- **Diagnosi SEO/GEO** ("Perché TransferBeat non si posiziona"): artifact https://claude.ai/code/artifact/0012674e-620d-4c55-a6a0-2dbc7bb8150b
  · copia nel repo: `kb/report/seo-geo-2026-09-03.html` (aprire nel browser).
- **Analisi di mercato fantacalcio** ("Fantacalcio in Italia 2026"): artifact https://claude.ai/code/artifact/434f627c-ae22-4180-9f80-492387c711d0
  · copia: `kb/report/mercato-fantacalcio-2026-09-03.html`; appunti grezzi delle ricerche in `kb/report/*.md`.
- In una nuova chat: `/artifacts` elenca gli artifact dell'utente; oppure aprire i file `kb/report/*.html`.

## 2. Diagnosi in breve (dati Search Console via GA4, giugno-settembre 2026)
316 impressioni, 43 clic (39 sulla home = ricerca del nome), 72 pagine con impressioni, 22 query tutte code lunghe su giocatori
minori ("atta fiore", "anan khalaili inter"), posizione media 43, zero query tematiche. **Indicizzato ma non competitivo.**
Cause per impatto: (ALTO) contenuto derivato dalle testate che vincono le stesse query · dominio di giugno 2026 senza menzioni né
link (una ricerca di "transferbeat" non trova nulla; `site:transferbeat.com` vuoto su Bing) · home/board/campionati vuote per i
motori (330/232/187 caratteri di testo statico, tutto via JS) · (MEDIO) tre lingue sulla stessa URL con lo stesso canonical ·
title senza tema ("TransferBeat — Home") · sitemap con lastmod "oggi" su 559 URL ogni giorno · nessuna entità (autore
"Redazione TransferBeat", niente chi siamo) · (BASSO) struttura piatta senza pagine squadra/competizione · riconversione recente.
GEO: assente da Bing (quindi da ChatGPT e Copilot), niente llms.txt, niente FAQ, dati originali non pubblicati come pagine.

## 3. Piano di intervento (approvato dal committente: punti 1-7). Ordine di esecuzione: 3 → 2 → 1 → 4 → 7 → 5 → 6
### 3.1 Pagine hub con testo vero (punto 1) — codice
Nuovo script `scripts/render_site.py`, eseguito da `update.yml` DOPO `build.py` e `competizioni.py` e PRIMA del commit:
- **Iniezione statica** in `index.html`, `board.html`, `campionati.html`: riempire i contenitori vuoti (`#apertura`, `#ticker`,
  `#miniBoard`, `#worldRow`, board per squadra, `#view` dei campionati) con HTML generato da `data/it/home.json`,
  `data/it/board.json`, `data/competizioni.json`. Il JavaScript esistente sovrascrive con `innerHTML`, quindi non si rompe nulla.
  Usare marcatori `<!-- static:inizio --> ... <!-- static:fine -->` per rigenerare senza duplicare.
- **Pagine squadra** `squadre/<slug>.html` per le 60 squadre di `data/teams.json` (slug = nome minuscolo senza accenti, spazi → `-`):
  title "Inter: notizie, classifica, calendario e rosa | TransferBeat"; H1; ultime notizie per concretezza (fatto/ufficiale/
  anteprima/voce) con fonte e link; riga di classifica e prossime partite da `competizioni.json` (mappare `team.short`/`name` ↔
  nome della board con una tabella alias); rosa da `data/rosters.json`; articoli correlati da `data/articles/index.json` (campo
  `team`); JSON-LD SportsTeam + BreadcrumbList; link a `board.html?team=` e alla pagina competizione. Indice `squadre/index.html`.
- **Pagine competizione** `campionati/<codice>.html` (serie-a, champions-league, premier-league, liga, bundesliga, ligue-1):
  classifica statica, ultima e prossima giornata, marcatori, link alle pagine squadra; JSON-LD SportsEvent per le partite.
- Nav: "Squadre" (→ `squadre/`) nei menu di home e board e nei piè di pagina di tutte le pagine.
### 3.2 Lingue (punto 2) — codice. DECISIONE: hub solo in italiano
- Togliere i tag `hreflang` da `index.html`, `board.html`, `campionati.html`, `fonti.html`, `fantatb.html` (restano i canonical).
- Il selettore IT/EN/ES nelle hub può restare come funzione ma non è più una pagina indicizzabile; valutare di toglierlo dalle
  hub e lasciarlo ad articoli e FantaTB. Gli articoli restano trilingue con URL separate (già corrette).
### 3.3 Title, description, sitemap (punto 3) — codice
- Title/description nuovi: home "Serie A e coppe: notizie, classifiche, risultati e FantaTB | TransferBeat"; board "Notizie di
  campionato squadra per squadra, classificate per concretezza | TransferBeat"; campionati "Classifica Serie A 2026-27,
  risultati, calendario e marcatori | TransferBeat"; fonti, fantatb, fanta/, squadre e competizioni generate.
- `sitemap.xml` diventa **sitemap index** → `sitemap-pagine.xml`, `sitemap-squadre.xml`, `sitemap-campionati.xml`,
  `sitemap-articoli.xml` (lastmod = campo `updated` dell'articolo), `sitemap-fanta.xml`. lastmod delle hub = `aggiornato` dei dati.
  Spostare la generazione da `render_articles.py` (oggi 559 URL con la data di oggi) a `render_site.py`; `render_articles`
  scrive solo `sitemap-articoli.xml`. `robots.txt` punta all'index.
### 3.4 Pagine dati originali (punto 4) — codice
Da `data/fanta/*.json` (committati dal workflow `fanta.yml`), generate da `render_site.py` in `fantacalcio/`:
- `fantacalcio/listone.html`: 651 giocatori con ruolo, squadra, quotazione FantaTB (tabella statica + JS di ordinamento);
  JSON-LD Dataset; intro con la formula (`kb/FANTATB.md` §6).
- `fantacalcio/voti-giornata-N.html` per ogni giornata `rated`: voto, bonus, fantavoto, minuti; intro con la formula (§5).
- `fantacalcio/titolari.html`: probabilità di titolarità, infortunati con rientro e squalificati della prossima giornata.
- `fantacalcio/index.html`: hub con link e FAQ con FAQPage ("come si calcola il voto FantaTB", "quanto costa", "serve un'app").
- Tutte linkate dalla landing `fantatb.html`, dall'app e dal menu.
### 3.5 Entità (punto 5) — codice + committente
- `chi-siamo.html`: cos'è TransferBeat, chi lo fa (nome del fondatore/direttore: **Pierluigi Cella**, DA CONFERMARE col
  committente prima di pubblicare), come si producono le notizie (aggregazione automatica con fonti citate e supervisione
  editoriale: dirlo, la trasparenza aiuta), contatti, profili social (`sameAs`). JSON-LD Organization con `founder` Person.
- Articoli: `author` = Person con `url` a chi-siamo; firma visibile. Serve dal committente: nome pubblico, bio di 3 righe,
  email di contatto, link ai profili social del sito.
### 3.6 Bing, IndexNow, llms.txt (punto 6) — committente + codice
- Committente: Bing Webmaster Tools → "Importa da Google Search Console" (5 minuti). Dopo 2 settimane verificare `site:transferbeat.com` su Bing.
- Codice: `scripts/indexnow.py` (chiave in `indexnow-<chiave>.txt` nella root del sito, ping a `api.indexnow.org` con le URL
  cambiate lette da `git diff --name-only`), chiamato da `scripts/pubblica.sh` e dallo step di commit di `update.yml` dopo il push.
- `llms.txt` nella root: cos'è il sito, sezioni con URL, dati disponibili (listone, voti, classifiche), contatti, condizioni d'uso.
### 3.7 Struttura interna (punto 7) — codice
- `render_articles.py`: blocco "Correlati" (stessa squadra, stesso tipo, ultimi 5), tag squadra con link alla pagina squadra,
  breadcrumb Home › Articoli › Squadra › Articolo con BreadcrumbList, link alla pagina competizione.
- Dalle pagine squadra agli articoli e viceversa; dalla board statica alle pagine squadra.
### 3.8 Statistiche squadra e schede giocatore (2026-09-03) — codice, vedi `kb/FANTATB.md` §14
- 670 pagine `giocatori/<slug>.html` (Serie A) con testo unico costruito dai dati, tabelle e grafici SVG inline (indicizzabili, niente JS),
  JSON-LD Person + BreadcrumbList, indice `giocatori/`, `sitemap-giocatori.xml`, voce "Giocatori" nel menu e nei sitelink. Le query lunghe
  sui nomi dei giocatori (unico traffico organico attuale, §2) ora hanno una pagina dedicata.
- Pagine squadra: sezione "Statistiche" (title e description aggiornati: "notizie, statistiche, classifica…"), rosa con link alle schede,
  stemma con i colori sociali. Listone, voti e titolari linkano i nomi alle schede (maglia interna a tre livelli: squadra → giocatore → voti).
- Dati `data/stats/*.json` da `scripts/stats_pull.py` (API-Football), rigenerazione in `fanta.yml`. Foto dei giocatori ATTIVE dal 2026-09-08 (licenza ancora da verificare, decisione di Pierluigi): 570 schede su 681, le altre 111 restano senza perché il CDN serve una sagoma anonima al posto del ritratto (vedi kb/FANTATB.md §14 e scripts/foto_check.py).

## 4. Verifica dopo ogni intervento
- `py -X utf8 scripts/render_site.py` deve finire con `render_site OK`; poi `node --check` sugli script inline delle hub e `grep -c '&lt;p&gt;'` a zero.
- **`py -X utf8 scripts/seo_audit.py`** (dal 2026-09-05): audit di tutte le pagine HTML contro §0 (title ≤60, description ≤155, canonical, hreflang, H1 unico,
  JSON-LD, breadcrumb, testo statico, `?lang=`, coerenza pagine/sitemap). Deve dare zero title >60, zero description >155, zero duplicati, H1 ≠ 1 nessuno.
- **Workflow**: prima di pushare un file in `.github/workflows/`, `py -c "import yaml,sys;yaml.safe_load(open(sys.argv[1],encoding='utf-8'))" <file>`.
  Un workflow invalido non avvisa: GitHub crea run FALLITI SENZA JOB (evento `push`) e ferma cron e `workflow_dispatch`. Controllo:
  `GET /repos/ultimacenere/transferbeat/actions/workflows/update.yml/runs?per_page=3` deve mostrare eventi `schedule` recenti con esito success.
- Testo statico sulle hub misurato (obiettivo migliaia di caratteri); `node --check` sul JS; pagine aperte senza `undefined`.
- Search Console: rapporto Pagine (indicizzate/escluse e perché), Prestazioni con query tematiche; rivedere ogni mese.
- Bing Webmaster: pagine indicizzate. Test `site:transferbeat.com` su Google e Bing.
- Mai toccare `data/{it,en,es}/*.json` a mano; i cron committano ogni 2 ore: integrare `origin/main` prima di pubblicare
  (`bash scripts/pubblica.sh` fa già fetch e rebase).

## 5. Cosa NON fare
Cambiare dominio · comprare link · moltiplicare gli articoli riassuntivi · tradurre di più le hub · caricare contenuto solo via JS.

## 6. Stato
- 2026-09-03 (mattina): diagnosi e piano scritti.
- 2026-09-03 (pomeriggio): **eseguiti i punti 1-7** e **PUBBLICATI su main** (commit `24c556d`, deploy Vercel verificato: 16 URL nuove su 16 rispondono 200,
  title nuovi, zero hreflang). Il primo ping IndexNow risponde 403 `SiteVerificationNotCompleted` finché Bing non completa la verifica della chiave
  (asincrona anche con `indexnow-<chiave>.txt` già online): i ping successivi dei cron passano da soli; se il 403 dura più di un giorno, controllare
  che la URL della chiave risponda 200 col solo valore della chiave. In sintesi:
  - `scripts/site_common.py` (costanti, alias squadre teams.json ↔ football-data ↔ listone, date italiane senza tzdata, template pagina, sitemap, lastmod con hash)
    e `scripts/render_site.py` (punti 1, 3, 4, 5-codice, 6-codice). Girano in `update.yml` dopo `competizioni.py` e in `fanta.yml`, PRIMA del commit.
    A mano: `py -X utf8 scripts/render_site.py` (3 secondi, nessuna rete, legge solo i JSON).
  - Hub: testo statico iniettato fra i marcatori `<!--static:NOME-->…<!--/static:NOME-->` di index/board/campionati (home 5.600 caratteri di testo, board 32.000,
    campionati 7.600, prima 200-330); title e description nuovi; `hreflang` e selettore lingua tolti da tutte le hub (solo IT; il JS accetta ancora `?lang=` ma nessun
    link lo usa); H1 unico (i titoli dinamici sono diventati H2); menu "Squadre"; piè di pagina con Squadre, Fantacalcio, Chi siamo.
  - `squadre/<slug>.html` (60) + `squadre/index.html`; `campionati/<slug>.html` (6) + indice; `fantacalcio/{index,listone,voti-giornata-N,titolari}.html`
    (Dataset con link ai JSON, FAQPage nell'indice); `chi-siamo.html` (AboutPage, Organization con `founder`, Person); `llms.txt`.
  - Sitemap: `sitemap.xml` è un INDICE di `sitemap-pagine/squadre/campionati/articoli/fanta.xml`; lastmod veri: `data/lastmod.json` tiene l'hash di ogni pagina
    (senza orari e "2 ore fa") e la data dell'ultimo cambiamento; gli articoli usano il campo `updated`. `render_articles.py` scrive solo `sitemap-articoli.xml`
    e richiama `write_sitemap_index()`; le pianificate committano anche `sitemap-articoli.xml`.
  - Articoli (`render_articles.py`): `author` Person → chi-siamo con firma visibile, breadcrumb Home › Articoli › Squadra › Articolo (anche BreadcrumbList),
    tag squadra e competizione linkati alle pagine statiche, blocco "Articoli correlati" (stessa squadra, poi stesso tipo, 5), menu hub senza `?lang=`.
  - IndexNow: `scripts/indexnow.py` + chiave `indexnow-<chiave>.txt` in root; chiamato da `update.yml`, `fanta.yml` e `pubblica.sh` dopo ogni push riuscito
    (URL dei file cambiati). `freshness.py` ha `check_render()`: fallisce se mancano le pagine statiche o la home ha l'apertura vuota.
  - `board.html?team=Inter` apre direttamente una squadra (le pagine squadra ci puntano); nella board il blocco statico squadra per squadra resta visibile
    (filtrato per lega/squadra dal JS) perché la vista "movimenti" a mercato chiuso è vuota.
- **Serve dal committente** (§3.5-3.6): 1) ~~conferma del nome pubblico~~ confermato il 2026-09-03: LinkedIn in `sameAs` (AUTHOR/PERSON_LD in `site_common.py`,
  chi-siamo, autore degli articoli, founder in `index.html`); 2) email di contatto da aggiungere a chi-siamo; 3) Bing Webmaster Tools → importa da Search Console;
  4) dopo 2 settimane `site:transferbeat.com` su Bing e rapporto Pagine in Search Console (le nuove URL: squadre/, campionati/, fantacalcio/, chi-siamo).
- **Trovato durante il lavoro, fuori piano**: `data/teams.json` contiene 9 club retrocessi (Verona, Cremonese, Pisa, Mallorca, Girona, Real Oviedo, West Ham,
  Wolves, Burnley) e non i 9 promossi 2026-27 presenti in football-data (Frosinone, Monza, Venezia, Deportivo, Málaga, Racing Santander, Coventry, Hull, Ipswich):
  le loro pagine squadra escono senza classifica e senza partite, e la board non raccoglie notizie sui promossi. Da aggiornare in `teams.json` (nome, search, lab,
  col, league, paese) e rilanciare build + render.
- 2026-09-05 (notte): **check delle regole §0 su tutto il sito e correzioni**. Trovato e corretto:
  - **`update.yml` INVALIDO dal push di `24c556d` (3/9)**: alla riga 44 l'`echo "render_site FALLITO: restano…"` conteneva `: ` in uno scalare YAML non quotato
    ("mapping values are not allowed here"). GitHub segnava "Invalid workflow file", creava un run fallito senza job a ogni push e non lanciava più né il cron
    né i `workflow_dispatch`: board, home e classifiche fermi al 3/9 (36 ore), home senza il recap del 4/9, sentinella `freshness.py` mai eseguita, niente IndexNow
    per hub e squadre. `fanta.yml` (valido) rigenerava le pagine statiche e ha mascherato il guasto. Corretto (virgola al posto dei due punti), validato con PyYAML,
    rilanciato con `workflow_dispatch`.
  - **Title e description (§0.2) fuori misura in tutti i generatori**: 18 title ≤60 e 8 description ≤155 su 1.334 pagine (articoli con il lead intero come description,
    fino a 441 caratteri). Ora `site_common.seo_title()` (suffisso " | TransferBeat" solo se il totale resta ≤60, altrimenti nessun suffisso: Google aggiunge da sé il
    nome del sito; oltre 60 taglio a fine parola) e `seo_desc()` (≤155: a fine frase se possibile, altrimenti a fine parola con "…"), applicati in `page()`,
    in `render_articles.head()` e agli og:*. Template accorciati: squadre ("Inter: notizie, statistiche e classifica"), competizioni ("Classifica Serie A 2026-27 e
    risultati"), listone, voti, titolari, indice fantacalcio, schede e indice giocatori, chi siamo; hub riscritte a mano (home "Serie A e coppe: notizie e classifiche",
    board "Notizie squadra per squadra, per concretezza", campionati.html "Campionati live: classifiche e risultati", non più uguale a serie-a). Prompt delle tre
    pianificate (kb + SKILL.md): titolo ≤60 e prima frase del lead ≤150.
  - Indici articoli con title/description propri e BreadcrumbList (erano "Articoli | TransferBeat"); `hreflang="x-default"` (→ IT) negli articoli; ES "Artículos";
    H1 unico in `fanta/index.html` (le viste usano `<h2 class="vh">` con lo stesso stile); `scripts/seo_audit.py` nel repo (§4).
  - Esito: 1.334 pagine, title max 60, description max 155, zero duplicati, H1 unico ovunque, JSON-LD senza errori. Senza suffisso restano i 573 articoli
    (titoli giornalistici lunghi) e ~85 pagine con nomi lunghi.
  - **Restano aperti**: `www.transferbeat.com` risponde con il certificato del solo apice (errore SSL nel browser): in Vercel → Settings → Domains aggiungere
    `www.transferbeat.com` con redirect a `transferbeat.com` (committente); email di contatto in chi-siamo; `fonti.html` (282 caratteri statici, fonti via JS) e
    `fantatb.html` (testi via JS) da rendere statici; retrocesse in `teams.json` (kb/FANTATB.md §13.13: 9 pagine magre, redirect 301 o testo onesto);
    og:image sulle pagine generate da `site_common` (serve un PNG); JSON-LD su board/campionati/fonti/fantatb; le sezioni del 3/9 non compaiono ancora su Bing
    (stima 60-90 URL indicizzate, solo pagine vecchie): ricontrollare dal 17/9 con Bing Webmaster Tools e Search Console.

### 3.6 Probabili formazioni (2026-09-06)
`fantacalcio/probabili-formazioni.html` (URL fissa, ultima giornata) + `probabili-giornata-N.html` (archivio). Title "Probabili formazioni giornata N
Serie A 2026-27", H1 con "moduli, titolari e percentuali", ~3.000 parole di testo generato dai dati per giornata (un paragrafo per squadra),
FAQPage + Dataset, ancore per partita (#inter-udinese), link a squadre e schede giocatore. In sitemap-fanta e IndexNow come le altre pagine fanta.
Keyword: "probabili formazioni serie a", "probabili formazioni giornata N", "probabili formazioni fantacalcio". Aggiornata giovedì sera, venerdì
15 UTC, sabato 8 UTC e a ogni run voti; i title non cambiano tra un aggiornamento e l'altro.

## 7. Nuova veste del sito, alberatura e guscio unico (2026-09-06, commit `ca2e1872` su main, online e verificato)
Origine: audit di navigabilità/UX (10 problemi verificati: 9 menu diversi, "FantaTB" con tre destinazioni, tre pagine "cos'è FantaTB" in cannibalizzazione,
H1 non chiuso nelle probabili, 585 articoli vicolo cieco, schede giocatore senza ingresso dalla home, sezione fanta senza menu, 4 sistemi visivi, router
dell'app senza Indietro, doppioni index.html/campionati.html) + mockup approvati in direzione C (arancio #ff6a00 + viola #4b1d95, tela Claude Design:
https://claude.ai/code/artifact/fa39467d-b3c6-4321-885b-563cbcaf982d). Decisioni del committente: font di sistema + Georgia solo su H1 e logo (niente webfont),
via "BETA", via il promo fucsia-arancio-giallo e gli skyscraper, TUTTO indicizzabile (anche `/fanta/`), pagine nuove senza revisione, tier a 5 cromie,
prima il desktop poi l'app. Etichetta della board nel menu: "Notizie" (default; alternative "Live"/"Calciomercato" mai scelte).
### 7.1 Guscio unico (`scripts/site_common.py`)
- `NAV` a 6 voci (Notizie /board.html, Campionati /campionati/, Squadre, Giocatori, Fantacalcio /fantacalcio/, Articoli) + `CTA` "Gioca a FantaTB" → /fantatb.html;
  `FANTA_BAR` (Panoramica, Probabili formazioni, Voti /fantacalcio/voti.html, Listone, Infortunati e squalificati /fantacalcio/titolari.html, Regolamento,
  Guida all'asta); `CAMP_BAR` (Tutte + 6 competizioni + Mondiale 2026); `FOOTER` a 3 colonne (Sezioni, Fantacalcio, TransferBeat: chi siamo, fonti, dati aperti,
  EN/ES, archivio Mondiale) da cui deriva `SITELINKS`.
- Funzioni: `shell_header(here, bar, bar_here, cta)`, `section_bar`, `shell_footer`, `ribbon()` (48 px viola pieno --ink, CTA + X bianchi dal 2026-09-08, memoria 7 giorni in localStorage
  `tb_ribbon`; MAI nel ramo Fantacalcio), `breadcrumb_html`, `page(..., bar=, bar_here=)`, `apply_shell(path, here, bar, bar_here, promo)` per le pagine a mano.
  `here` accetta anche i nomi vecchi ("Live"→Notizie, "FantaTB"→Fantacalcio). `fanta/promo.js` ELIMINATO: nessuna pagina lo include più.
- Token CSS (`:root`, valori del 6 settembre, SUPERATI dalla variante calda del 2026-09-08: vedi §7.1b): --bg #f6f4fb, --card #fff, --line #e5e1ee, --txt #161b21, --txt2 #3d4750, --muted #5b6670, --brand #ff6a00 (mai testo bianco sopra:
  testo --ink #1b1140), --brand-ink #c24d00, --violet #4b1d95, --ok/--warn/--err, badge ruolo --rP/--rD/--rC/--rA, --grad (gradiente firma, al massimo uno per
  pagina); alias vecchi (--accent, --done, --rumor, --red) mantenuti. Componenti: .secbar, .kpis/.kpi, .rb (badge ruolo), .pill, .pol (6 politico), .door, .grad,
  .status, .tscroll (tabelle su mobile). Niente emoji nel markup generato.
- Pagine a mano (index, board, campionati, fonti, mondiali.html): tre marcatori `<!--shell:css-->`, `<!--shell:header-->`, `<!--shell:footer-->` riempiti da
  `apply_shell` a ogni `render_site.py` (prima delle inject `static:`); lo `<style>` proprio resta DOPO il blocco shell:css. La home ha il nuovo marcatore
  `<!--static:fanta-->` (blocco Fantacalcio) e linka /giocatori/; le tab campionato puntano alle URL statiche /campionati/<slug>.html.
### 7.1b Variante calda (2026-09-08, approvata da Pierluigi sulla tela di design)
Le superfici bianche sono diventate grigio chiaro e le superfici scure hanno preso un gradiente caldo. Token nuovi in `:root`:
- superfici: `--bg #e8e8ed` (fondo), `--card #f7f7f9` (schede), `--panel #eeeef2`, `--line #d8d8e0`, `--line2 #e3e3e9`.
  Lo stacco scheda/fondo sale da 1,09 a 1,14: le schede si distinguono un po' più di prima, non solo per il bordo.
- `--grad-bar: linear-gradient(100deg,#2c0f57,#5c1878 30%,#9c2743 62%,#a83a1a)` su `header.site` e `.foot`.
  La coda si ferma su un arancio bruciato per una ragione misurata: con `#c2410c` le voci del menu (#e7dcf9), il testo
  del footer (#e6dbf5) e il suo hover (#ffd7a8) stavano fra 3,83 e 4,32, cioè sotto 4,5. Con `#a83a1a` il peggiore è 4,73.
- `--grad` (blocchi promozionali `.grad` e `.lp-final`) RIDEFINITO: prima andava da arancio a viola e il bianco sopra
  l'arancio faceva 2,6. Ora `linear-gradient(105deg,#5b21b6,#a21caf 32%,#e11d48 62%,#c24d07)`: il testo bianco parte dal
  viola e nel punto peggiore fa 4,82.
- Sul caldo i pulsanti arancioni sparivano (arancio su arancio): `header.site a.cta` e `.ribbon .rb-cta` sono bianchi con
  testo `#2c0f57`. Nella barra di sezione, che resta chiara, il CTA arancione è rimasto.
- Il ribbon è rimasto viola pieno (`--ink`) e NON ha preso il gradiente: testata + ribbon + striscia rossa dell'ultim'ora
  facevano tre bande calde di fila. Il viola in mezzo fa da respiro. La barra di sezione resta chiara perché è sticky e
  non deve fare una seconda banda quando si attacca in alto.
- Il testo dentro la testata: logo `#fff` con la B `#ffb673`, voci `#e7dcf9`, voce attiva `#fff` con la sottolineatura
  `#ffb673`. Footer: titoli `#fff`, testo `#e6dbf5`, link `#f0e7fa`, hover `#ffd7a8`, riga del copyright `rgba(255,255,255,.22)`.
- Applicata anche fuori dal guscio: `.pcard` (render_site), `.lcard` (render_articles), `.pf-idx a` (render_probabili),
  `.lp-proof` e `.lp-final` (render_landing), e il CSS locale di index/board/campionati/fonti (17 superfici).
  Restano bianchi solo i pulsanti che stanno SOPRA una superficie scura: `.grad .btn`, `.lp-hero .btn`, i due CTA di cui sopra.
- Tutti i contrasti sono stati calcolati, non stimati: testo sulle schede 16,2; attenuato 5,5; link viola 10,3; hover 4,5;
  i quattro colori ruolo fra 4,56 e 5,20; ok/warn/err sui rispettivi fondi fra 4,54 e 4,80.

#### 7.1c Cosa è emerso dalla revisione (stesso giorno, 48 agenti in due passate)
- **594 pagine su 1375 erano rimaste alla veste vecchia**: tutti gli articoli (197 × 3 lingue + 3 indici). Causa: dopo un
  cambio del guscio va rilanciato OGNI generatore, e `render_articles.py` è a parte — nessun workflow lo chiama
  (`update.yml` e `fanta.yml` lanciano solo `render_site.py`). Nessun errore da nessuna parte, `git status` mostrava
  807 file cambiati senza il minimo segnale che ne mancasse un'intera sezione.
  **Rimedio strutturale**: `scripts/guard.py` ora estrae la riga `:root{--bg:…}` da `site_common.py` e BLOCCA il commit
  se una pagina non ce l'ha, elencando le cartelle indietro e il comando da lanciare. Escluse `fanta/` (guscio proprio,
  ora allineato a mano) e `kb/`. La guardia è testata in entrambe le direzioni: riconosce la pagina vecchia e, se non
  riesce a leggere il guscio, lo dichiara invece di approvare.
- **L'app FantaTB** (`fanta/style.css`) teneva una copia a mano dei token: allineata (superfici, `--brand-ink`, `--grad`
  invertito, `--grad-bar`, testata a gradiente con logo e voci schiariti, pulsante utente bianco).
- **Regressioni di contrasto chiuse**: `.lp-final .btn` era arancione sulla coda arancione del gradiente (2,23 → bianco);
  `nav.secbar` sticky aveva **esattamente** il colore delle schede che le scorrono sotto (1,00: aggiunti bordo inferiore
  e ombra); il ticker rosso della home si fondeva con la testata a ribbon chiuso (1,20: filetto chiaro sopra);
  `--brand-ink` #c24d00 → **#ad4400** (hover dei link: 3,95 → 4,77); serie dei grafici #a7b0ba → **#828d9a** (2,05 → 3,15)
  e #eb6834 → **#d4551f** (2,99 → 3,83), asse #c3c2b7 → #9a9a8f.
- **`<meta name="theme-color" content="#2c0f57">` e `<link rel="icon">`** su tutte le pagine (guscio, articoli, app):
  con la testata scura la barra del browser su mobile restava bianca.
- **`/favicon.png` non esisteva** ed era citato dal JSON-LD `Organization` di 608 pagine: 404. Ora lo genera
  `scripts/make_og.py` (gradiente della testata + "TB" in Georgia, 512px), insieme alle og:image.
- **Nota sul lastmod**: un cambio di guscio sposta il `lastmod` di tutte le pagine, perché `LastMod.touch` fa l'hash
  dell'HTML intero e il CSS è inline. È il comportamento voluto per un restyling (le pagine sono davvero cambiate),
  ma va saputo: non è "il contenuto è cambiato", è "la pagina è cambiata".
- Resta aperto e NON è colpa della veste: il pulsante arancione `--brand` non si stacca da nessuna delle due superfici
  (2,68 sulle schede, 2,35 sul fondo) — era 2,79 sul bianco. Serve un bordo o un arancio più scuro, da decidere.

### 7.2 Alberatura e URL (3 livelli, tutto entro 3 clic dalla home; una sola URL rinominata, vedi §7.3.13)
- Nuove: `/fantacalcio/voti.html` (URL fissa = ultima giornata; le `voti-giornata-N.html` restano archivio, quella della giornata corrente ha canonical su voti.html
  e sta fuori sitemap), `/fantacalcio/regolamento.html` (FAQPage), `/fantacalcio/guida-asta.html` (HowTo), `/fantacalcio/consigli.html` (ItemList, "chi schierare"
  dalle probabili ≥70% × fantamedia) — generate da `scripts/render_fanta_extra.py` (`render_all(D, T)`), agganciate in `render_site.main()` con try/except.
- `/fantatb.html` è GENERATA da `scripts/render_landing.py` (`render(D, T)`): testo statico ≥2.500 caratteri, WebApplication JSON-LD SOLO qui (tolto dall'hub),
  FAQPage, CTA a /fanta/#crea. `/fanta/` resta index,follow e in sitemap, con title distinto ("Accedi a FantaTB: le tue leghe, asta e formazioni"), senza CTA.
- `/fantacalcio/titolari.html` riposizionata su "Infortunati e squalificati"; dal 2026-09-07 l'URL e' `/fantacalcio/infortunati-e-squalificati.html`, con 301 dalla vecchia (§7.3.13). `campionati.html`: H1/title non cannibalizzano più serie-a;
  il 301 verso /campionati/ resta rimandato finché il committente non legge le impressioni in Search Console.
- Redirect in `vercel.json`: `/index.html` → `/` (308 verificato) oltre a `/home.json`.
- Ancore nelle probabili: `#partita-<slug casa>-<slug ospite>` e `#squadra-<slug>`; le schede giocatore e le pagine squadra le linkano.
- Articoli: `render_articles.py` usa shell_header (here Articoli, barra lingue Italiano/English/Español), ribbon solo in IT, footer del sito, card Fantacalcio
  contestuale; etichetta della board "Notizie/News/Noticias".
- Esito (seo_audit + controlli): 1.359 pagine, header/footer del guscio 1/1 ovunque, promo.js 0, H1 unico e chiuso ovunque, title ≤60, description ≤155,
  JSON-LD 0 errori, link interni rotti 0, IndexNow 200 su 1.366 URL.
### 7.3 Rifiniture del 2026-09-06 — TUTTE CHIUSE il 2026-09-07
1. ~~`consigli.html` orfana~~ **fatto**: "Chi schierare" è ora una voce di `FANTA_BAR` (quindi in tutte le pagine
   fantacalcio e nella colonna Fantacalcio del footer), una porta nell'hub e una porta nel blocco `static:fanta`
   della home. `bar_here` impostato su entrambe le varianti della pagina.
2. ~~i generatori linkano `voti-giornata-N.html` invece di `voti.html`~~ **fatto**: `site_common.voti_url(md, last_md)`
   e `voti_last(D)`, usate in `render_stats`, `render_landing`, `render_fanta_extra` e `render_probabili`.
   Zero stringhe `voti-giornata-` scritte a mano nei generatori.
3. ~~4 title e 2 description duplicati~~ **fatto**, e meglio di come chiedeva il pending: invece di scartare uno dei
   due gemelli, `clean_players` li **FONDE**. Mamedi Doucouré aveva la data di nascita su un id e la stagione
   scorsa sull'altro: ora è una scheda sola con entrambe. 676 pagine (erano 678), **zero duplicati**.
   Le 4 URL vecchie hanno un 301 in `vercel.json`; ogni fusione nuova stampa una riga che ricorda di aggiungerlo.
4. ~~`fanta/index.html` senza BreadcrumbList e JSON-LD~~ **fatto**: BreadcrumbList a 4 livelli + WebPage che cita
   l'applicazione per `@id`, più og:image. Resta senza breadcrumb VISIBILE (l'app non ne ha uno): da valutare.
5. ~~secondo `linear-gradient` nel CSS condiviso~~ **fatto**: la dissolvenza `.tabsw::after` è diventata un'ombra
   piatta. In tutto il sito resta un solo gradiente, quello firma (`--grad`).
6. ~~card fantavoti a capo male a 375 px~~ **fatto** (`flex-wrap` + baseline su `.lp-proof .h`).
7. ~~`regolamento.html` con un secondo WebApplication~~ **fatto**: la landing dichiara `@id` e chi la cita usa
   `{"@id": ...}`. In tutto il sito resta **un solo** oggetto WebApplication.
8. **og:image** ~~assente~~ **fatto**, ed era peggio di come sembrava: le pagine generate non ne avevano nessuna e
   i **573 articoli usavano una SVG**, che nessuno scraper social legge (Facebook, X, LinkedIn, WhatsApp, Telegram).
   Le anteprime degli articoli erano di fatto rotte. Ora `scripts/make_og.py` genera 4 anteprime di sezione
   (`og-default`, `og-fantacalcio`, `og-campionati`, `og-squadre`) e 5 gemelle PNG delle copertine articolo;
   `page()` sceglie l'immagine dalla sezione (`og_image(here)`), le pagine a mano la ricevono dal nuovo marcatore
   `<!--shell:og-->`, e `twitter:card` è passata a `summary_large_image`. **0 pagine senza og:image** su 1.356.
   Le immagini si rigenerano con `py scripts/make_og.py` se cambiano i colori del sito.
9. ~~JSON-LD su board, campionati, fonti~~ **fatto** (più l'archivio Mondiale): nuovo marcatore `<!--static:ld-->`
   riempito da `render_site`. Board → `CollectionPage` + `ItemList` delle 60 squadre coperte; campionati →
   `ItemList` delle competizioni; fonti → `ItemList` delle testate lette; Mondiale → `SportsEvent` con la data di fine.
   Scelta deliberata: si marcano **le nostre entità** (squadre, competizioni, fonti), non le notizie altrui.
10. ~~`fonti.html` quasi tutto via JS~~ **fatto**: l'elenco delle testate è **generato da `data/sources.json`**, lo
   stesso file che usa il programma di raccolta, quindi la pagina non può più mentire. Testo statico da 2.612 a 3.404
   caratteri. **Attenzione alla scala dei tier: 3 = massima affidabilità, 1 = da verificare** (è il numero che
   `dots()` trasforma in pallini pieni; l'avevo letta al contrario la prima volta).
11. ~~tabelle interattive in `/campionati/`~~ **fatto**: `table_html(..., sortable=True)` **solo** per le pagine
   competizione (le pagine squadra e l'hub non includono `FILTER_JS`: intestazioni cliccabili a vuoto sarebbero
   peggio di niente). Barra con filtro unico che agisce su classifica e marcatori insieme, contatore righe.
   Il DR con il `+` si ordina come numero grazie a `data-v`. **Le fasce colorate restano corrette dopo il riordino**
   perché tingono il testo della cella posizione, non lo sfondo della riga.
   Resta rimandato il **301 di `campionati.html` → `/campionati/`**: aspetta che il committente legga le impressioni in GSC.
12. ~~home "portale"~~ **fatto**: la home aveva già notizie e articoli ma **non la classifica di Serie A**, che è la
   cosa più cercata del dominio. Nuova fascia `static:classifica`: tutte e 20 le squadre + la giornata in corso
   con l'etichetta onesta ("in corso, 4 partite su 10"). Va messa fra le fasce a tutta larghezza, NON dentro la
   griglia di `div.main`, o finisce incolonnata nella colonna delle notizie.
13. ~~`/fantacalcio/titolari.html` su URL parlante~~ **fatto**: ora `/fantacalcio/infortunati-e-squalificati.html`,
   con 301 dalla vecchia. 23 riferimenti aggiornati in 8 file sorgente e **585 articoli rigenerati** (i link interni
   verso un redirect sono spreco di crawl budget).
14. ~~verifica dal vivo su mobile~~ **fatto**, in modo programmatico su 15 tipi di pagina a 375 px:
   **zero overflow orizzontale, zero tabelle compresse, tutte 200**. Le tabelle fuori da `.tscroll` (schede
   giocatore, pagine squadra, infortunati) stanno nei 310-347 px senza comprimersi: non serve intervenire.
15. ~~fase J, bilancio mercato~~ vedi `kb/RIPARTENZA.md` §8.

### 7.4 Restano aperti (SEO)
- **301 di `campionati.html`** verso `/campionati/`: decisione del committente dopo Search Console.
- **`fanta/index.html` senza breadcrumb visibile** (il JSON-LD c'è): Google preferisce che coincidano.
- **Le 9 squadre retrocesse** in `data/teams.json` (69 in tutto): decisione del committente, le URL sono indicizzate.
- **Titolo e H1 della board dicono "calciomercato"** ("Notizie di calciomercato squadra per squadra" /
  "Notizie di calciomercato in tempo reale") mentre il sito è stato riconvertito al calcio giocato e lo scout è
  spento: la pagina promette mercato e consegna campionati. Può essere una scelta di posizionamento sulla parola
  più cercata, ma va decisa: oggi title e contenuto non coincidono.
- **www → apice in Vercel**, **email in chi-siamo**, **Bing Webmaster Tools**: cose del committente (blocco A).
