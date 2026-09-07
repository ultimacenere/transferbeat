#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - palinsesto.py: la RETE DI SICUREZZA del palinsesto editoriale.

I tre articoli quotidiani (LUNCH BREAK 12:00, FOCUS 16:00, RECAP DI GIORNATA 20:00) li scrivono tre
pianificate Cowork che girano SOLO a PC acceso: il 29, 30, 31 agosto e il 2 settembre 2026 lo slot e'
rimasto vuoto e il sito e' rimasto senza contenuto proprio (kb/PIANIFICATE.md, "Limite noto").
Questo script gira su GitHub Actions (quindi anche a PC spento) e riempie lo slot SOLO se e' vuoto.

PERCHE' IL BOLLETTINO E' FATTO DI SOLI DATI (decisione di progetto, non negoziabile):
un articolo scritto da un modello con meno contesto sarebbe peggiore di quello di Cowork e, soprattutto,
potrebbe inventare. Un bollettino costruito dai numeri gia' nel repo non puo' sbagliare un risultato.
Meglio corto e vero che lungo e inventato: e' la regola editoriale del progetto. QUI NON SI CHIAMA
NESSUN MODELLO LINGUISTICO e non si fa NESSUNA chiamata di rete: solo file gia' committati.

FONTI (tutte e solo queste, gia' nel repo):
- data/competizioni.json  risultati, classifiche, marcatori, prossime partite (unica fonte per i numeri);
- data/<lang>/board.json  notizie gia' classificate per concretezza, con fonte e link;
- data/fanta/*.json       voti FantaTB, probabili, listone, indisponibili.

REGOLE RISPETTATE
- Non sovrascrive mai il lavoro delle pianificate: se per oggi esiste gia' un articolo di quel tipo, esce senza fare nulla.
- Pubblica solo dopo un margine di attesa (MARGINE_MIN) rispetto all'orario dello slot, in ora italiana.
- Si dichiara: "Bollettino dati" nel titolo (le liste articoli mostrano solo quello), la seconda frase del
  lead e l'ultimo paragrafo spiegano che e' generato dai dati e non scritto dalla redazione.
- SEO (kb/SEO.md 0.2): titolo entro 60 caratteri, prima frase del lead entro 150.
- Tre lingue (it, en, es): i numeri sono gli stessi, le frasi fisse sono tradotte qui sotto a mano.

USO (l'elenco autorevole dei flag e' FLAG_SEMPLICI/FLAG_CON_VALORE qui sotto: `uso()` stampa questo stesso
testo, e ARGOMENTI NON RICONOSCIUTI FERMANO LO SCRIPT con uscita 2 invece di far partire una pubblicazione)
  py -X utf8 scripts/palinsesto.py --dry                prova gli slot maturi, non scrive niente
  py -X utf8 scripts/palinsesto.py --dry --slot lunch   prova un solo slot (lunch | focus | recap)
  py -X utf8 scripts/palinsesto.py --dry --adesso 2026-09-07T18:40:00Z   simula un altro momento
  py -X utf8 scripts/palinsesto.py --dry --forza        ignora margine e copertura (mostra cosa produrrebbe
                                                        ogni slot); `--tutti` e' il sinonimo accettato
  py -X utf8 scripts/palinsesto.py --out <cartella>     scrive i JSON in quella cartella e NON rigenera le
                                                        pagine: e' il modo di provare fuori dal repo
                                                        (`--articoli` e' il sinonimo accettato)
  py -X utf8 scripts/palinsesto.py --aiuto              stampa questo elenco (anche --help, -h)
  py -X utf8 scripts/palinsesto.py                      PUBBLICA: scrive gli articoli mancanti in
                                                        data/articles e rigenera le pagine del sito
--forza/--tutti valgono SOLO con --dry: la rete di sicurezza non scavalca mai la redazione.
Codice di uscita 0 anche quando non c'e' niente da fare (slot gia' coperto o non ancora maturo):
il fallimento e' riservato agli errori veri, cosi' il workflow resta verde quando la redazione ha lavorato.
Uscita 2 per un uso sbagliato della riga di comando (flag sconosciuto, valore mancante, slot inesistente):
un refuso non deve MAI trasformare un'anteprima in una pubblicazione, quindi si ferma prima di leggere i dati.
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta

# La console italiana e' cp1252 e muore sugli accenti (kb/RIPARTENZA.md 3): lo script si difende da solo
# anche se qualcuno lo lancia senza -X utf8.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# site_common non ha dipendenze esterne e sa gia' convertire in ora italiana anche senza tzdata
# (Windows non ce l'ha): riusarlo evita una seconda implementazione della regola dell'ora legale.
from site_common import DATA, COMPS, MESI, load_json, parse_iso, to_rome

ARTDIR = os.path.join(DATA, "articles")
SITE = "https://transferbeat.com"
LANGS = ("it", "en", "es")
TITOLO_MAX = 60          # kb/SEO.md 0.2: il titolo diventa il <title> cosi' com'e'
LEAD1_MAX = 150          # kb/SEO.md 0.2: la prima frase del lead diventa la meta description
MARGINE_MIN = 90         # minuti di attesa dopo l'orario dello slot prima di considerarlo un buco
# Coda dopo la mezzanotte italiana: per quanti minuti dalla maturazione uno slot resta recuperabile anche
# quando il calendario italiano e' gia' passato al giorno dopo. Serve al RECAP: il cron delle 20:40 UTC cade
# alle 22:40 italiane d'estate e alle 21:40 d'inverno, ma GitHub Actions puo' far partire un run con ore di
# ritardo; superata la mezzanotte, `giorno_rome(adesso)` sarebbe gia' domani e lo slot delle 20:00 di IERI
# non lo coprirebbe piu' nessuno (il recap di domani non e' maturo, quello di ieri non viene piu' guardato):
# la giornata resterebbe muta SENZA nessun errore. Con la coda il bollettino esce, datato al giorno giusto.
# 360 minuti = il recap (maturo alle 21:30) e' recuperabile fino alle 03:30 italiane; focus e lunch, maturi
# molto prima, restano fuori dalla coda e non riemergono la notte dopo.
CODA_NOTTE_MIN = 360
ETA_NOTIZIE_MAX = 20     # ore: oltre, una voce della board non e' piu' "di oggi"
AFF_MIN_NOTIZIE = 2      # tier minimo preferito per le voci citate (3 = massima, 1 = da verificare)

# I tre slot, con l'ora italiana della pianificata che dovrebbe averli scritti.
# tipo/lab/col sono quelli dei formati esistenti (kb/PIANIFICATE.md): cosi' badge, copertina e colori della
# pagina restano quelli del formato e il bollettino non introduce un tipo nuovo da mantenere in render_articles.
SLOT = {
    "lunch": {"ora": 12, "tipo": "lunch",  "lab": "LUNCH", "col": "#d98700"},
    "focus": {"ora": 16, "tipo": "storia", "lab": "FOCUS", "col": "#1f4e9b"},
    "recap": {"ora": 20, "tipo": "recap",  "lab": "RECAP", "col": "#0a9d57"},
}
ORDINE = ("lunch", "focus", "recap")

MESI_LANG = {
    "it": MESI,
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
}

# ---------------------------------------------------------------- frasi fisse (tradotte a mano, nessun modello)
T = {
"it": {
  "data": "{g} {m}",
  "titolo": {"lunch": "Bollettino dati {d}: risultati e partite di oggi",
             "focus": "Bollettino dati {d}: classifiche e marcatori",
             "recap": "Bollettino dati {d}: i risultati della giornata"},
  "titolo_corto": "Bollettino dati {d}",
  "lead1": {"lunch": "Riepilogo automatico dai dati di TransferBeat: {a} e {b}.",
            "focus": "Riepilogo automatico dai dati di TransferBeat: classifiche, marcatori e prossime partite delle competizioni seguite.",
            "recap": "Riepilogo automatico dai dati di TransferBeat: {a}, classifiche aggiornate e il programma di domani."},
  "lead1_corto": "Riepilogo automatico dai dati di TransferBeat sulle sei competizioni seguite dal sito.",
  "lead2": "Non è un articolo della redazione: è un bollettino costruito dai dati già pubblicati sul sito, senza commenti e senza previsioni.",
  "finite24": {0: "nessuna partita finita nelle ultime 24 ore", 1: "1 partita finita nelle ultime 24 ore", "n": "{n} partite finite nelle ultime 24 ore"},
  "finite_oggi": {0: "nessuna partita finita oggi", 1: "1 partita finita oggi", "n": "{n} partite finite oggi"},
  "oggi_prog": {0: "nessuna partita in programma oggi", 1: "1 partita in programma oggi", "n": "{n} partite in programma oggi"},
  "h_ris": "I risultati.", "h_prog": "Cosa si gioca.", "h_domani": "Domani.", "h_cl": "Le classifiche.",
  "h_mar": "I marcatori.", "h_news": "Le notizie.", "h_fanta": "Fantacalcio.",
  "niente_ris": "Nei dati non risulta nessuna partita finita nel periodo: sosta o giornata senza calcio nelle competizioni seguite.",
  "niente_prog": "Nei dati non risulta nessuna partita in programma.",
  "giornata": "{n}ª giornata",
  "in_corso": "Iniziate ma senza risultato nei dati al momento del bollettino: {x}.",
  "ris_in_attesa": "Le partite del periodo ci sono in calendario, ma nei dati non risulta ancora nessun risultato finale.",
  "attesa_ieri": "i risultati di ieri non sono ancora nei dati", "attesa_oggi": "i risultati di oggi non sono ancora nei dati",
  "data_ora": "{d} alle {h}",
  "non_finite": "Le partite non ancora finite non hanno un risultato nei dati e qui non compaiono: nessun punteggio viene stimato.",
  "riga": "{comp}: {righe}",
  "cl_voce": "{pos}. {team} {pt} punti ({pg} giocate)",
  "mar_voce": "{name} ({team}) {g} gol",
  "news_intro": "Dalle notizie già classificate della board, aggiornate {q}:",
  "news_voce": "«{titolo}» ({fonte})",
  "news_nota": "Sono titoli delle fonti, riportati come tali e non verificati uno per uno.",
  "niente_news": "Nella board non ci sono notizie abbastanza recenti da riportare qui.",
  "fanta_voti": "voti FantaTB della giornata {n} ({f} partite su {t})",
  "fanta_top": "I fantavoti più alti: {x}.",
  "fanta_prob": "probabili formazioni della giornata {n} su {p} partite",
  "fanta_list": "listone con {n} giocatori quotati",
  "fanta_inj": "{n} tra infortunati e squalificati",
  "fanta_intro": "I dati originali di TransferBeat per il fantacalcio:",
  "nota_h": "Come è fatto questo bollettino.",
  "nota": ("Le tre firme quotidiane di TransferBeat (Lunch Break, Focus e Recap di giornata) le scrive la redazione. "
           "Quando lo slot resta vuoto, questa pagina lo riempie con un riepilogo generato dai dati già pubblicati sul sito: "
           "risultati, classifiche e marcatori da competizioni.json (aggiornato il {ts}), notizie e fonti dalla board, numeri dal "
           "fantacalcio FantaTB. Nessuna frase è scritta da un modello linguistico e nessun numero è stimato: se un dato non c'è, "
           "qui non c'è. Il bollettino non sostituisce l'articolo del giorno, gli fa da rete di sicurezza."),
  "ieri": "ieri", "oggi": "oggi", "domani": "domani", "e": " e ",
},
"en": {
  "data": "{g} {m}",
  "titolo": {"lunch": "Data bulletin, {d}: results and today's games",
             "focus": "Data bulletin, {d}: tables and top scorers",
             "recap": "Data bulletin, {d}: the day's results"},
  "titolo_corto": "Data bulletin, {d}",
  "lead1": {"lunch": "Automatic summary from TransferBeat data: {a} and {b}.",
            "focus": "Automatic summary from TransferBeat data: tables, top scorers and upcoming games in the competitions we follow.",
            "recap": "Automatic summary from TransferBeat data: {a}, updated tables and tomorrow's fixtures."},
  "lead1_corto": "Automatic summary from TransferBeat data on the six competitions the site follows.",
  "lead2": "This is not a newsroom article: it is a bulletin built from the data already published on the site, with no comment and no predictions.",
  "finite24": {0: "no match finished in the last 24 hours", 1: "1 match finished in the last 24 hours", "n": "{n} matches finished in the last 24 hours"},
  "finite_oggi": {0: "no match finished today", 1: "1 match finished today", "n": "{n} matches finished today"},
  "oggi_prog": {0: "no match scheduled today", 1: "1 match scheduled today", "n": "{n} matches scheduled today"},
  "h_ris": "The results.", "h_prog": "What is on.", "h_domani": "Tomorrow.", "h_cl": "The tables.",
  "h_mar": "Top scorers.", "h_news": "The news.", "h_fanta": "Fantasy football.",
  "niente_ris": "The data shows no finished match in this window: an international break or a day without football in the competitions we follow.",
  "niente_prog": "The data shows no scheduled match.",
  "giornata": "matchday {n}",
  "in_corso": "Started but with no score in the data when this bulletin was built: {x}.",
  "ris_in_attesa": "The fixtures are on the calendar, but the data does not carry any final score for this window yet.",
  "attesa_ieri": "yesterday's results are not in the data yet", "attesa_oggi": "today's results are not in the data yet",
  "data_ora": "{d} at {h}",
  "non_finite": "Matches that are not over have no score in the data and are not listed here: no result is ever estimated.",
  "riga": "{comp}: {righe}",
  "cl_voce": "{pos}. {team} {pt} points ({pg} played)",
  "mar_voce": "{name} ({team}) {g} goals",
  "news_intro": "From the already classified headlines on the board, updated {q}:",
  "news_voce": "“{titolo}” ({fonte})",
  "news_nota": "These are the sources' own headlines, quoted as such and not verified one by one.",
  "niente_news": "The board has no headline recent enough to be quoted here.",
  "fanta_voti": "matchday {n} FantaTB ratings ({f} of {t} matches)",
  "fanta_top": "Highest fantasy scores: {x}.",
  "fanta_prob": "matchday {n} predicted line-ups for {p} matches",
  "fanta_list": "a player list with {n} valuations",
  "fanta_inj": "{n} injured or suspended players",
  "fanta_intro": "TransferBeat's own Serie A fantasy football data:",
  "nota_h": "How this bulletin is made.",
  "nota": ("TransferBeat's three daily pieces (Lunch Break, Focus and Daily Recap) are written by the newsroom. "
           "When that slot stays empty, this page fills it with a summary generated from the data already published on the site: "
           "results, tables and scorers from competizioni.json (updated on {ts}), headlines and sources from the board, numbers from "
           "FantaTB fantasy football. No sentence is written by a language model and no number is estimated: if a figure is not in the "
           "data, it is not here. The bulletin does not replace the article of the day, it is its safety net."),
  "ieri": "yesterday", "oggi": "today", "domani": "tomorrow", "e": " and ",
},
"es": {
  "data": "{g} de {m}",
  "titolo": {"lunch": "Boletín de datos, {d}: resultados y partidos",
             "focus": "Boletín de datos, {d}: tablas y goleadores",
             "recap": "Boletín de datos, {d}: resultados del día"},
  "titolo_corto": "Boletín de datos, {d}",
  "lead1": {"lunch": "Resumen automático con los datos de TransferBeat: {a} y {b}.",
            "focus": "Resumen automático con los datos de TransferBeat: tablas, goleadores y próximos partidos de las competiciones seguidas.",
            "recap": "Resumen automático con los datos de TransferBeat: {a}, tablas actualizadas y el programa de mañana."},
  "lead1_corto": "Resumen automático con los datos de TransferBeat sobre las seis competiciones que sigue el sitio.",
  "lead2": "No es un artículo de la redacción: es un boletín construido con los datos ya publicados en el sitio, sin comentarios ni pronósticos.",
  "finite24": {0: "ningún partido terminado en las últimas 24 horas", 1: "1 partido terminado en las últimas 24 horas", "n": "{n} partidos terminados en las últimas 24 horas"},
  "finite_oggi": {0: "ningún partido terminado hoy", 1: "1 partido terminado hoy", "n": "{n} partidos terminados hoy"},
  "oggi_prog": {0: "ningún partido programado hoy", 1: "1 partido programado hoy", "n": "{n} partidos programados hoy"},
  "h_ris": "Los resultados.", "h_prog": "Qué se juega.", "h_domani": "Mañana.", "h_cl": "Las tablas.",
  "h_mar": "Los goleadores.", "h_news": "Las noticias.", "h_fanta": "Fantacalcio.",
  "niente_ris": "Los datos no registran ningún partido terminado en este periodo: parón o jornada sin fútbol en las competiciones seguidas.",
  "niente_prog": "Los datos no registran ningún partido programado.",
  "giornata": "jornada {n}",
  "in_corso": "Empezados pero sin resultado en los datos al construir el boletín: {x}.",
  "ris_in_attesa": "Los partidos están en el calendario, pero los datos todavía no traen ningún resultado final.",
  "attesa_ieri": "los resultados de ayer aún no están en los datos", "attesa_oggi": "los resultados de hoy aún no están en los datos",
  "data_ora": "{d} a las {h}",
  "non_finite": "Los partidos que no han terminado no tienen resultado en los datos y no aparecen aquí: ningún marcador se estima.",
  "riga": "{comp}: {righe}",
  "cl_voce": "{pos}. {team} {pt} puntos ({pg} jugados)",
  "mar_voce": "{name} ({team}) {g} goles",
  "news_intro": "De los titulares ya clasificados del board, actualizados {q}:",
  "news_voce": "«{titolo}» ({fonte})",
  "news_nota": "Son titulares de las fuentes, citados como tales y no verificados uno por uno.",
  "niente_news": "El board no tiene titulares lo bastante recientes para citarlos aquí.",
  "fanta_voti": "votos FantaTB de la jornada {n} ({f} de {t} partidos)",
  "fanta_top": "Los mejores fantavotos: {x}.",
  "fanta_prob": "alineaciones probables de la jornada {n} en {p} partidos",
  "fanta_list": "listado con {n} jugadores cotizados",
  "fanta_inj": "{n} lesionados o sancionados",
  "fanta_intro": "Los datos propios de TransferBeat para el fantacalcio:",
  "nota_h": "Cómo se hace este boletín.",
  "nota": ("Las tres piezas diarias de TransferBeat (Lunch Break, Focus y Recap del día) las escribe la redacción. "
           "Cuando ese hueco queda vacío, esta página lo llena con un resumen generado con los datos ya publicados en el sitio: "
           "resultados, tablas y goleadores de competizioni.json (actualizado el {ts}), titulares y fuentes del board, números del "
           "fantacalcio FantaTB. Ninguna frase la escribe un modelo de lenguaje y ningún número se estima: si un dato no está, aquí "
           "no aparece. El boletín no sustituye al artículo del día, es su red de seguridad."),
  "ieri": "ayer", "oggi": "hoy", "domani": "mañana", "e": " y ",
},
}

# ---------------------------------------------------------------- utilita' di base
def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def giorno_rome(dt):
    """Data italiana (date) di un istante UTC: e' il calendario del lettore, non quello di UTC."""
    return to_rome(dt).date()


def data_lunga(d, lang):
    """'7 settembre' / '7 September' / '7 de septiembre' (senza anno: sta nel titolo, che ha 60 caratteri)."""
    return T[lang]["data"].format(g=d.day, m=MESI_LANG[lang][d.month - 1])


def data_ora(dt, lang):
    """'6 settembre alle 09:18' (ora italiana): la nota finale deve dire quanto sono freschi i dati."""
    r = to_rome(dt)
    return T[lang]["data_ora"].format(d=data_lunga(r.date(), lang), h=r.strftime("%H:%M"))


def conta(lang, chiave, n):
    """Frase con il numero, con singolare e zero gia' scritti a mano nelle tre lingue."""
    tab = T[lang][chiave]
    if n in tab:
        return tab[n]
    return tab["n"].format(n=n)


def taglia(testo, limite):
    """Taglia a fine parola: serve solo come rete, le frasi qui sono gia' dimensionate."""
    t = re.sub(r"\s+", " ", testo or "").strip()
    if len(t) <= limite:
        return t
    t = t[:limite]
    sp = t.rfind(" ")
    return (t[:sp] if sp > limite * 0.6 else t).rstrip(" ,;:") + "."


def elenco(voci, lang):
    """'a, b e c' con la congiunzione della lingua giusta."""
    voci = [v for v in voci if v]
    if not voci:
        return ""
    if len(voci) == 1:
        return voci[0]
    return ", ".join(voci[:-1]) + T[lang]["e"] + voci[-1]


# ---------------------------------------------------------------- lettura dei dati (solo file del repo)
def carica_competizioni():
    return load_json(os.path.join(DATA, "competizioni.json"), {}) or {}


def partite(comp):
    """Tutte le partite di una competizione, deduplicate per id: le giornate si sovrappongono nel file."""
    out = {}
    for lista in (comp.get("giornate") or {}).values():
        for m in lista or []:
            if m.get("id") is not None:
                out[m["id"]] = m
    return list(out.values())


def nome_comp(comp, lang):
    n = comp.get("nome") or {}
    return n.get(lang) or n.get("it") or comp.get("code", "")


def nome_squadra(t):
    t = t or {}
    return t.get("short") or t.get("name") or ""


# Stati di football-data che indicano una partita che si deve giocare o si sta giocando.
# Fuori restano POSTPONED, SUSPENDED, CANCELLED e AWARDED: non sono partite in attesa di risultato.
APERTI = ("TIMED", "SCHEDULED", "IN_PLAY", "PAUSED", "LIVE")


def finite(comp, giorni):
    """Partite FINISHED giocate in uno dei giorni (date italiane) richiesti, in ordine di orario."""
    out = [m for m in partite(comp)
           if m.get("status") == "FINISHED" and m.get("ft") and giorno_rome(parse_iso(m.get("utc")) or now_utc()) in giorni]
    return sorted(out, key=lambda m: m.get("utc") or "")


def in_programma(comp, giorni, adesso):
    """Partite dei giorni richiesti che devono ancora cominciare: solo queste si annunciano con l'orario."""
    out = [m for m in partite(comp)
           if m.get("status") in ("TIMED", "SCHEDULED") and giorno_rome(parse_iso(m.get("utc")) or adesso) in giorni
           and (parse_iso(m.get("utc")) or adesso) > adesso]
    return sorted(out, key=lambda m: m.get("utc") or "")


def senza_risultato(comp, giorni, adesso):
    """Partite gia' cominciate che nei dati non hanno un risultato: o sono in corso, o competizioni.json
    non e' ancora stato aggiornato (gira ogni due ore). In entrambi i casi si dice cosi', senza inventare
    il punteggio: e' la regola del recap delle 20 delle pianificate, qui applicata ai dati.
    Rinviate, sospese e annullate restano fuori: non sono partite senza risultato, sono partite che non si giocano."""
    out = [m for m in partite(comp)
           if m.get("status") in APERTI and giorno_rome(parse_iso(m.get("utc")) or adesso) in giorni
           and (parse_iso(m.get("utc")) or adesso) <= adesso]
    return sorted(out, key=lambda m: m.get("utc") or "")


def previste(comp, giorni):
    """Partite dei giorni richiesti che risultano da giocare o gia' giocate: serve a distinguere la sosta
    (in calendario non c'e' niente) dai risultati che non sono ancora arrivati nei dati."""
    return [m for m in partite(comp)
            if m.get("status") in APERTI + ("FINISHED",) and giorno_rome(parse_iso(m.get("utc")) or now_utc()) in giorni]


def etichetta_giornata(ms, lang):
    """'3ª giornata' se le partite sono tutte della stessa giornata, altrimenti niente."""
    gg = {m.get("matchday") for m in ms if m.get("matchday")}
    return T[lang]["giornata"].format(n=list(gg)[0]) if len(gg) == 1 else ""


def ris(m):
    ft = m.get("ft") or [None, None]
    return nome_squadra(m.get("home")) + "-" + nome_squadra(m.get("away")) + " " + str(ft[0]) + "-" + str(ft[1])


def prog(m):
    """'Venezia-Fiorentina 20:45': l'orario e' quello italiano, come nel resto del sito."""
    d = parse_iso(m.get("utc"))
    ora = to_rome(d).strftime("%H:%M") if d else ""
    return nome_squadra(m.get("home")) + "-" + nome_squadra(m.get("away")) + (" " + ora if ora else "")


def vs(m):
    return nome_squadra(m.get("home")) + "-" + nome_squadra(m.get("away"))


# ---------------------------------------------------------------- paragrafi (uno per sezione, gia' in lingua)
def par_risultati(comps, giorni, lang, testa):
    """'I risultati. Serie A, 3ª giornata: Genoa-Como 1-4, Roma-Atalanta 2-1. Premier League: ...'"""
    righe = []
    for c in comps:
        ms = finite(c, giorni)
        if not ms:
            continue
        gg = etichetta_giornata(ms, lang)
        etichetta = nome_comp(c, lang) + (", " + gg if gg else "")
        righe.append(T[lang]["riga"].format(comp=etichetta, righe=", ".join(ris(m) for m in ms)))
    if righe:
        return testa + " " + ". ".join(righe) + "."
    # nessun risultato: dire "sosta" quando in calendario non c'e' niente, "dati non ancora arrivati" quando
    # invece le partite ci sono. Sono due cose diverse e confonderle sarebbe un errore, non una sfumatura.
    calendario = any(previste(c, giorni) for c in comps)
    return testa + " " + (T[lang]["ris_in_attesa"] if calendario else T[lang]["niente_ris"])


def par_programma(comps, giorni, lang, testa, adesso, oggi=None):
    """Partite ancora da giocare, con l'orario italiano; quelle gia' cominciate e senza punteggio nei dati
    sono dichiarate tali, mai completate a naso.
    Se la finestra copre piu' giorni, ogni gruppo porta il suo giorno: un orario da solo ("21:00") in un
    elenco che mescola oggi e domani farebbe credere che si giochi tutto stasera.
    `oggi` e' il giorno di RIFERIMENTO del bollettino, che dopo la mezzanotte non e' piu' quello dell'orologio:
    le etichette "oggi"/"domani" devono seguire la data del bollettino, non l'istante in cui gira lo script."""
    if oggi is None:
        oggi = giorno_rome(adesso)
    righe, aperte = [], []
    for giorno in sorted(giorni):
        blocchi = []
        for c in comps:
            ms = in_programma(c, {giorno}, adesso)
            if not ms:
                continue
            gg = etichetta_giornata(ms, lang)
            etichetta = nome_comp(c, lang) + (", " + gg if gg else "")
            blocchi.append(T[lang]["riga"].format(comp=etichetta, righe=", ".join(prog(m) for m in ms)))
        if not blocchi:
            continue
        if len(giorni) > 1:
            if giorno == oggi:
                q = T[lang]["oggi"]
            elif giorno == oggi + timedelta(days=1):
                q = T[lang]["domani"]
            else:
                q = data_lunga(giorno, lang)
            righe.append(q[0].upper() + q[1:] + " — " + ". ".join(blocchi))
        else:
            righe += blocchi
    for c in comps:
        aperte += [vs(m) for m in senza_risultato(c, giorni, adesso)]
    if righe:
        out = testa + " " + ". ".join(righe) + "."
    elif aperte:
        out = testa
    else:
        out = testa + " " + T[lang]["niente_prog"]
    if aperte:
        out += " " + T[lang]["in_corso"].format(x=", ".join(aperte)) + " " + T[lang]["non_finite"]
    return out


def par_classifiche(comps, lang, quante=3):
    """Le prime `quante` di ogni classifica presente nei dati (le coppe prima della fase a gironi non ce l'hanno)."""
    righe = []
    for c in comps:
        for gruppo in c.get("classifica") or []:
            tab = gruppo.get("table") or []
            if not tab:
                continue
            etichetta = nome_comp(c, lang)
            nome_gruppo = gruppo.get("group") or ""
            if len(c.get("classifica") or []) > 1 and nome_gruppo and nome_gruppo.lower() != "matchday":
                etichetta += " " + nome_gruppo
            voci = [T[lang]["cl_voce"].format(pos=r.get("pos"), team=nome_squadra(r.get("team")), pt=r.get("pt"), pg=r.get("pg"))
                    for r in tab[:quante]]
            righe.append(T[lang]["riga"].format(comp=etichetta, righe="; ".join(voci)))
    return (T[lang]["h_cl"] + " " + ". ".join(righe) + ".") if righe else ""


def par_marcatori(comps, lang, quanti=3):
    """Capocannonieri per competizione: sono dati, non giudizi, e sono contenuto originale citabile (kb/SEO.md 0.7)."""
    righe = []
    for c in comps:
        top = [m for m in (c.get("marcatori") or []) if (m.get("goals") or 0) > 0][:quanti]
        if not top:
            continue
        voci = [T[lang]["mar_voce"].format(name=m.get("name"), team=nome_squadra(m.get("team")), g=m.get("goals")) for m in top]
        righe.append(T[lang]["riga"].format(comp=nome_comp(c, lang), righe="; ".join(voci)))
    return (T[lang]["h_mar"] + " " + ". ".join(righe) + ".") if righe else ""


# ---------------------------------------------------------------- notizie dalla board
def _ore_fa(quando):
    """'11 ore fa' / '2h ago' / '15 d' -> ore. La board scrive tempi relativi (build.py, time_ago), non date."""
    s = str(quando or "").strip().lower()
    if not s:
        return None
    m = re.match(r"^(\d+)\s*([a-z]*)", s)
    if not m:
        return 0.0                      # 'poco fa' / 'just now' / 'ahora'
    n = int(m.group(1)); u = m.group(2)
    return n * 24.0 if u.startswith("g") or u.startswith("d") else float(n)


def notizie(board, quante=4):
    """Le notizie piu' concrete e piu' recenti della board, senza doppioni di link.
    L'eta' vera e' quella del titolo PIU' il tempo passato da quando la board e' stata costruita:
    i tempi nel file sono relativi a quel momento, non ad adesso."""
    if not board:
        return []
    agg = parse_iso(board.get("aggiornato"))
    ritardo = max(0.0, (now_utc() - agg).total_seconds() / 3600.0) if agg else 0.0
    viste, out = set(), []
    for colonna in ("done", "conf"):     # fatti e atti ufficiali: le voci non vanno in un bollettino di dati
        for nome, sq in (board.get("squadre") or {}).items():
            for it in ((sq.get("colonne") or {}).get(colonna) or []):
                link = it.get("link") or ""
                eta = _ore_fa(it.get("quando"))
                if not it.get("titolo") or link in viste or eta is None or eta + ritardo > ETA_NOTIZIE_MAX:
                    continue
                viste.add(link)
                out.append({"titolo": re.sub(r"\s+", " ", it["titolo"]).strip(), "fonte": it.get("fonte") or "",
                            "aff": int(it.get("affidabilita") or 0), "eta": eta + ritardo})
    out.sort(key=lambda x: (-x["aff"], x["eta"]))
    # Soglia di affidabilita' con ripiego. Ordinare per tier non basta: se in quel momento le uniche voci
    # abbastanza fresche sono di fonti minori, il bollettino quotidiano del sito finisce per citare una
    # Primavera 2 o un aggregatore straniero. Si prendono prima le fonti da 2 in su e si scende solo se
    # non bastano, cosi' la qualita' migliora quando i dati ci sono e la pagina non resta vuota quando non ci sono.
    buone = [x for x in out if x["aff"] >= AFF_MIN_NOTIZIE]
    if len(buone) >= quante:
        return buone[:quante]
    resto = [x for x in out if x["aff"] < AFF_MIN_NOTIZIE]
    return (buone + resto)[:quante]


def par_notizie(board, lang, quante=4):
    voci = notizie(board, quante)
    if not voci:
        return T[lang]["h_news"] + " " + T[lang]["niente_news"]
    titoli = "; ".join(T[lang]["news_voce"].format(titolo=v["titolo"], fonte=v["fonte"]) for v in voci)
    return T[lang]["h_news"] + " " + T[lang]["news_intro"].format(q=T[lang]["oggi"]) + " " + titoli + ". " + T[lang]["news_nota"]


# ---------------------------------------------------------------- fantacalcio (dati propri, contenuto originale)
def _ultimo(prefisso):
    """Ultimo data/fanta/<prefisso>-N.json con contenuto: (N, dati) oppure None."""
    cartella = os.path.join(DATA, "fanta")
    migliore = None
    if os.path.isdir(cartella):
        for fn in os.listdir(cartella):
            m = re.match(prefisso + r"-(\d+)\.json$", fn)
            if m and (migliore is None or int(m.group(1)) > migliore[0]):
                dati = load_json(os.path.join(cartella, fn))
                if dati:
                    migliore = (int(m.group(1)), dati)
    return migliore


def _numero(x, lang):
    """8.5 -> '8,5' in italiano e spagnolo, '8.5' in inglese."""
    s = ("%.1f" % float(x)).rstrip("0").rstrip(".")
    return s if lang == "en" else s.replace(".", ",")


def par_fanta(lang, con_top=False):
    """Numeri veri del ramo fantacalcio al momento del bollettino: voti, probabili, listone, indisponibili.
    Con `con_top` aggiunge i tre fantavoti piu' alti dell'ultima giornata votata (nomi dal listone)."""
    pezzi, coda = [], ""
    voti = _ultimo("voti")
    if voti and voti[1].get("ratings"):
        pezzi.append(T[lang]["fanta_voti"].format(n=voti[0], f=int(voti[1].get("finished") or 0), t=int(voti[1].get("total") or 0)))
        if con_top:
            nomi = {p.get("id"): p for p in ((load_json(os.path.join(DATA, "fanta", "listone.json"), {}) or {}).get("players") or [])}
            top = sorted([r for r in voti[1]["ratings"] if r.get("fantavoto") is not None],
                         key=lambda r: float(r["fantavoto"]), reverse=True)[:3]
            voci = []
            for r in top:
                p = nomi.get(r.get("player_id")) or {}
                if p.get("name"):
                    voci.append(p["name"] + " (" + (p.get("team") or "") + ") " + _numero(r["fantavoto"], lang))
            if voci:
                coda = " " + T[lang]["fanta_top"].format(x=elenco(voci, lang))
    prob = _ultimo("probabili")
    if prob and prob[1].get("fixtures"):
        pezzi.append(T[lang]["fanta_prob"].format(n=prob[0], p=len(prob[1]["fixtures"])))
    listone = load_json(os.path.join(DATA, "fanta", "listone.json"), {}) or {}
    if listone.get("players"):
        pezzi.append(T[lang]["fanta_list"].format(n=len(listone["players"])))
    tit = _ultimo("titolari")
    if tit and tit[1].get("status"):
        fuori = sum(1 for s in tit[1]["status"] if s.get("injury"))
        if fuori:
            pezzi.append(T[lang]["fanta_inj"].format(n=fuori))
    if not pezzi:
        return ""
    return T[lang]["h_fanta"] + " " + T[lang]["fanta_intro"] + " " + elenco(pezzi, lang) + "." + coda


# ---------------------------------------------------------------- composizione dell'articolo
def testo(slot, lang, dati, giorni, board, adesso):
    """Titolo, lead e paragrafi di uno slot in una lingua. Ogni paragrafo vuoto sparisce: meglio corto che riempito."""
    comps = [c for c in (dati.get("competizioni") or [])]
    # ordine di lettura: le competizioni nell'ordine di site_common (Serie A prima), le altre in coda
    peso = {c["code"]: i for i, c in enumerate(COMPS)}
    comps.sort(key=lambda c: peso.get(c.get("code"), 99))
    ieri, oggi, domani, dopo = giorni
    tt = T[lang]
    d = data_lunga(oggi, lang)

    titolo = tt["titolo"][slot].format(d=d)
    if len(titolo) > TITOLO_MAX:
        titolo = taglia(tt["titolo_corto"].format(d=d), TITOLO_MAX)

    n_fin24 = sum(len(finite(c, {ieri, oggi})) for c in comps)
    n_fin_oggi = sum(len(finite(c, {oggi})) for c in comps)
    n_prog_oggi = sum(len(in_programma(c, {oggi}, adesso)) for c in comps)
    attesa24 = (n_fin24 == 0 and any(previste(c, {ieri, oggi}) for c in comps))
    attesa_oggi = (n_fin_oggi == 0 and any(previste(c, {oggi}) for c in comps))
    if slot == "lunch":
        a = tt["attesa_ieri"] if attesa24 else conta(lang, "finite24", n_fin24)
        lead1 = tt["lead1"]["lunch"].format(a=a, b=conta(lang, "oggi_prog", n_prog_oggi))
    elif slot == "recap":
        a = tt["attesa_oggi"] if attesa_oggi else conta(lang, "finite_oggi", n_fin_oggi)
        lead1 = tt["lead1"]["recap"].format(a=a)
    else:
        lead1 = tt["lead1"]["focus"]
    if len(lead1) > LEAD1_MAX:
        lead1 = tt["lead1_corto"]           # rete: la meta description non deve mai essere tagliata a meta'
    lead = lead1 + " " + tt["lead2"]

    ts = data_ora(parse_iso(dati.get("aggiornato")) or adesso, lang)
    nota = tt["nota_h"] + " " + tt["nota"].format(ts=ts)
    if slot == "lunch":
        corpo = [par_risultati(comps, {ieri, oggi}, lang, tt["h_ris"]),
                 par_programma(comps, {oggi}, lang, tt["h_prog"], adesso, oggi),
                 par_classifiche(comps, lang, 3),
                 par_notizie(board, lang),
                 par_fanta(lang), nota]
    elif slot == "focus":
        corpo = [par_classifiche(comps, lang, 5),
                 par_marcatori(comps, lang, 3),
                 par_programma(comps, {oggi, domani, dopo}, lang, tt["h_prog"], adesso, oggi),
                 par_fanta(lang, con_top=True),
                 par_notizie(board, lang), nota]
    else:
        corpo = [par_risultati(comps, {oggi}, lang, tt["h_ris"]),
                 par_programma(comps, {oggi}, lang, tt["h_prog"], adesso, oggi),
                 par_classifiche(comps, lang, 3),
                 par_notizie(board, lang),
                 par_programma(comps, {domani}, lang, tt["h_domani"], adesso, oggi),
                 par_fanta(lang), nota]
    return {"title": titolo, "lead": lead, "body": [p for p in corpo if p]}


def costruisci(slot, adesso, dati, boards, giorno=None):
    """L'articolo completo, nella forma che si aspettano render_articles e data/articles/index.json.
    `giorno` e' la data italiana DELLO SLOT (vedi riferimento()): normalmente coincide con quella di `adesso`,
    ma un run che arriva dopo la mezzanotte deve scrivere il bollettino di IERI, con lo slug e i numeri di ieri,
    non un bollettino datato oggi con dentro le partite sbagliate."""
    oggi = giorno or giorno_rome(adesso)
    giorni = (oggi - timedelta(days=1), oggi, oggi + timedelta(days=1), oggi + timedelta(days=2))
    meta = SLOT[slot]
    art = {"slug": slug_bollettino(slot, oggi), "tipo": meta["tipo"],
           "giocatore": "", "team": "", "league": "", "lab": meta["lab"], "col": meta["col"],
           "stato": "done", "smentita": False, "created": iso(adesso), "updated": iso(adesso),
           "updates": [], "automatico": True,      # marchio: distingue il bollettino dagli articoli della redazione
           "content": {lang: testo(slot, lang, dati, giorni, boards.get(lang) or boards.get("it"), adesso) for lang in LANGS}}
    return art


# ---------------------------------------------------------------- lo slot e' gia' coperto? e' gia' maturo?
# Prefisso degli slug prodotti da questo script: e' cio' che distingue un bollettino da un pezzo della redazione.
PREFISSO_BOLLETTINO = "bollettino-"

def slug_bollettino(slot, giorno):
    """Lo slug del bollettino di uno slot in un giorno: uno solo, cosi' chi scrive e chi controlla la
    copertura guardano lo stesso nome e non si puo' scrivere due volte lo stesso bollettino."""
    return "bollettino-" + slot + "-" + giorno.isoformat()


def articoli(cartella):
    """Tutti gli articoli dello store (data/articles/*.json), index.json escluso."""
    out = []
    if not os.path.isdir(cartella):
        return out
    for fn in sorted(os.listdir(cartella)):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        a = load_json(os.path.join(cartella, fn))
        if isinstance(a, dict) and a.get("slug"):
            out.append(a)
    return out


def coperto(slot, giorno, arts):
    """Slug dell'articolo che copre gia' lo slot di quel giorno, oppure "".
    Vale sia il pezzo creato oggi sia quello aggiornato oggi: il FOCUS, quando la storia esiste gia',
    la pianificata la AGGIORNA invece di crearne una nuova (kb/pianificate/focus-mercato-transferbeat.md).
    Vale anche il bollettino con lo slug di quel giorno: un bollettino recuperato dopo la mezzanotte porta
    `created` del giorno dopo, e senza questo controllo un secondo run nella stessa coda notturna lo
    riscriverebbe da capo credendo che lo slot fosse ancora vuoto."""
    tipo = SLOT[slot]["tipo"]
    atteso = slug_bollettino(slot, giorno)
    for a in arts:
        slug = a.get("slug") or ""
        if slug == atteso:
            return slug
        if a.get("tipo") != tipo:
            continue
        # Un BOLLETTINO si riconosce SOLO dal suo slug, che porta il giorno vero. La data di creazione no:
        # un recap recuperato dopo la mezzanotte ha `created` del giorno DOPO, e giudicarlo da quella lo
        # farebbe passare per la copertura del giorno successivo - sopprimendo il bollettino di domani
        # in silenzio, con uscita 0. Il giorno di un bollettino sta nel nome, non nell'orologio.
        if slug.startswith(PREFISSO_BOLLETTINO):
            continue
        for campo in ("created", "updated"):
            d = parse_iso(a.get(campo))
            if d and giorno_rome(d) == giorno:
                return slug
    return ""


def riferimento(slot, adesso):
    """(giorno italiano dello slot, maturo, minuti che mancano alla maturazione).

    Il margine serve a non correre mai davanti alla redazione: la pianificata delle 12:00 puo' partire in ritardo.
    Il giorno NON e' sempre quello dell'orologio. Il cron gira alle 20:40 UTC, cioe' alle 22:40 italiane in ora
    legale e alle 21:40 in ora solare: gia' d'inverno restano 10 minuti di margine sulla maturazione del recap
    (21:30), e GitHub Actions puo' far partire un run con ore di ritardo. Passata la mezzanotte italiana lo slot
    delle 20:00 e' quello di IERI: senza la coda notturna lo script guarderebbe il recap di oggi (non maturo per
    quasi un giorno), non scriverebbe niente, uscirebbe 0 e la giornata resterebbe senza bollettino senza che
    nessuno se ne accorga. Con la coda si scrive il bollettino di ieri, datato ieri: mai uno datato domani,
    perche' il giorno restituito non supera mai la data italiana corrente."""
    r = to_rome(adesso)
    apertura = SLOT[slot]["ora"] * 60 + MARGINE_MIN                  # minuti dalla mezzanotte italiana
    ora_min = r.hour * 60 + r.minute + r.second / 60.0
    if ora_min >= apertura:
        return r.date(), True, 0
    # Prima della maturazione di oggi: lo slot di ieri e' ancora aperto solo se e' maturato da poco (coda).
    trascorsi = ora_min + 24 * 60 - apertura                          # minuti dalla maturazione di ieri
    if trascorsi <= CODA_NOTTE_MIN:
        return r.date() - timedelta(days=1), True, 0
    return r.date(), False, max(0, int(round(apertura - ora_min)))


# ---------------------------------------------------------------- riga di comando
# Elenco AUTOREVOLE dei flag: la vecchia lettura "cerca il flag in sys.argv" ingoiava in silenzio qualunque
# refuso (--articolo, --slot-lunch, --dryrun) e lo script proseguiva col giro normale, cioe' SCRIVEVA e
# PUBBLICAVA mentre l'utente credeva di aver chiesto un'anteprima. Qui ogni token deve essere riconosciuto,
# altrimenti si esce con 2 senza toccare niente: meglio fermarsi che indovinare.
# I sinonimi non sono un vezzo: sono i nomi che l'USO di questo file ha documentato, e cio' che e' scritto
# nel file deve fare quello che dice (un `--out` che non esiste manda i bollettini di prova in produzione).
FLAG_SEMPLICI = {
    "--dry":   "dry",
    "--forza": "forza",
    "--tutti": "forza",      # sinonimo documentato di --forza
}
FLAG_CON_VALORE = {
    "--slot":     "slot",
    "--adesso":   "adesso",
    "--articoli": "store",
    "--out":      "store",   # sinonimo documentato di --articoli
}
FLAG_AIUTO = ("--aiuto", "--help", "-h")


def uso():
    """L'USO in testa al file, stampato tale e quale: una sola fonte, cosi' non puo' divergere dal codice."""
    doc = __doc__ or ""
    i = doc.find("USO")
    return doc[i:].rstrip() if i >= 0 else ""


def leggi_argomenti(argv):
    """(opzioni, errore). `errore` non vuoto = riga di comando da rifiutare, nessuna scrittura.
    Valida anche i valori: un `--slot` senza valore (o seguito da un altro flag) e' un errore, non un None
    silenzioso che fa ripartire tutti e tre gli slot."""
    op = {"dry": False, "forza": False, "slot": None, "adesso": None, "store": None, "aiuto": False,
          "nome_store": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in FLAG_AIUTO:
            op["aiuto"] = True
        elif a in FLAG_SEMPLICI:
            op[FLAG_SEMPLICI[a]] = True
        elif a in FLAG_CON_VALORE:
            chiave = FLAG_CON_VALORE[a]
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                return op, "manca il valore di " + a
            valore = argv[i + 1]
            # --out e --articoli sono lo stesso posto: due valori diversi sarebbero un'ambiguita' su DOVE si
            # scrive, cioe' esattamente la domanda a cui questo script non puo' rispondere a caso.
            if op[chiave] is not None and op[chiave] != valore:
                return op, "valore doppio e diverso per " + a + " (" + str(op[chiave]) + " e " + valore + ")"
            op[chiave] = valore
            if chiave == "store":
                op["nome_store"] = a
            i += 1
        elif a.startswith("-"):
            return op, "flag sconosciuto: " + a
        else:
            return op, "argomento non riconosciuto: " + a
        i += 1
    if op["slot"] is not None and op["slot"] not in SLOT:
        return op, "slot sconosciuto: " + op["slot"] + " (ammessi: " + ", ".join(ORDINE) + ")"
    if op["adesso"] is not None and parse_iso(op["adesso"]) is None:
        return op, "data non valida per --adesso: " + op["adesso"] + " (attesa ISO, es. 2026-09-07T18:40:00Z)"
    if op["forza"] and not op["dry"]:
        return op, "--forza/--tutti valgono solo con --dry: la rete di sicurezza non scavalca mai la redazione"
    return op, ""


def anteprima(art):
    """Cosa finirebbe online, con le misure SEO in chiaro: e' la prova che si legge con --dry."""
    print("  slug:", art["slug"], "· tipo:", art["tipo"], "· lab:", art["lab"])
    for lang in LANGS:
        c = art["content"][lang]
        prima = re.split(r"(?<=[.!?]) ", c["lead"])[0]
        print("  [" + lang + "] titolo (" + str(len(c["title"])) + "/60): " + c["title"])
        print("       lead 1a frase (" + str(len(prima)) + "/150): " + prima)
        print("       lead 2a frase: " + c["lead"][len(prima):].strip())
        for i, p in enumerate(c["body"], 1):
            print("       par." + str(i) + " (" + str(len(p)) + "): " + p)
        print("")


def main():
    op, errore = leggi_argomenti(sys.argv[1:])
    if errore:
        # Uscita 2 PRIMA di leggere i dati e di scrivere qualsiasi cosa: un uso sbagliato non deve mai
        # degradare in una pubblicazione riuscita a meta'.
        print("palinsesto: " + errore, file=sys.stderr)
        print("", file=sys.stderr)
        print(uso(), file=sys.stderr)
        return 2
    if op["aiuto"]:
        print(uso())
        return 0
    dry = op["dry"]
    forza = op["forza"]              # solo con --dry: ignora margine e copertura per far vedere il testo
    solo = op["slot"]
    store = os.path.abspath(op["store"] or ARTDIR)
    ufficiale = (store == os.path.abspath(ARTDIR))
    adesso = parse_iso(op["adesso"]) if op["adesso"] else now_utc()

    dati = carica_competizioni()
    if not (dati.get("competizioni") or []):
        print("ERRORE: data/competizioni.json assente o vuoto: senza risultati non si scrive nessun bollettino.")
        return 1
    boards = {lang: load_json(os.path.join(DATA, lang, "board.json"), {}) for lang in LANGS}

    oggi = giorno_rome(adesso)
    arts = articoli(store)
    print("palinsesto: " + iso(adesso) + " (Italia " + to_rome(adesso).strftime("%Y-%m-%d %H:%M") + ") · giorno " + oggi.isoformat()
          + " · store " + store + ("" if ufficiale else " (FUORI dallo store ufficiale " + os.path.abspath(ARTDIR) + ": niente render)")
          + (" · PROVA A VUOTO (non scrive niente)" if dry else ""))
    scritti = []
    for slot in ([solo] if solo else list(ORDINE)):
        giorno, ok, mancano = riferimento(slot, adesso)
        gia = coperto(slot, giorno, arts)
        etichetta = slot.upper() + " (" + SLOT[slot]["tipo"] + ", pianificata delle " + str(SLOT[slot]["ora"]) + ":00)"
        if giorno != oggi:     # va detto: il bollettino porta la data di ieri, non quella dell'orologio
            etichetta += " del " + giorno.isoformat() + ", recuperato dopo la mezzanotte"
        if gia and not forza:
            print("- " + etichetta + ": GIA' COPERTO da " + gia + ", non faccio nulla.")
            continue
        if not ok and not forza:
            print("- " + etichetta + ": slot non ancora maturo, mancano " + str(mancano) + " minuti (margine " + str(MARGINE_MIN) + "').")
            continue
        art = costruisci(slot, adesso, dati, boards, giorno)
        if gia or not ok:      # ci si arriva solo con --forza, cioe' solo in prova: dire perche' non sarebbe partito
            motivo = ("gia' coperto da " + gia) if gia else ("non ancora maturo, mancano " + str(mancano) + " minuti")
            print("- " + etichetta + ": anteprima forzata (" + motivo + ") · bollettino " + art["slug"])
        else:
            print("- " + etichetta + ": BUCO · bollettino " + art["slug"])
        if dry:
            anteprima(art)
            continue
        percorso = os.path.join(store, art["slug"] + ".json")
        os.makedirs(store, exist_ok=True)
        with open(percorso, "w", encoding="utf-8", newline="\n") as f:
            json.dump(art, f, ensure_ascii=False, indent=2)
        print("  scritto " + percorso)
        scritti.append(art["slug"])

    if scritti and ufficiale:
        # stessa riga delle pianificate (kb/pianificate/*.md): pagine it/en/es, index.json e sitemap-articoli.xml
        import articles, render_articles
        n = render_articles.render_all(articles.all_articles(), SITE, articles.PAGES, articles.DATA)
        print("Pagine rigenerate: " + str(n) + " articoli totali.")
    elif scritti:
        print("Store fuori dal repo: niente render (le pagine si generano solo dallo store ufficiale).")
    print("Bollettini scritti: " + (", ".join(scritti) if scritti else "nessuno") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
