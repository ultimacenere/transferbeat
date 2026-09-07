#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TransferBeat - bilancio.py
Ricostruisce il BILANCIO DEL MERCATO ESTIVO 2026 dallo storico gia' classificato della board e scrive
data/articles/bilancio-mercato-estate-2026.json (tipo editoriale "bilancio", gia' presente in render_articles.TIPI).

Perche' cosi' e non altrimenti - ogni scelta nasce da un difetto misurato della sorgente:
- FINESTRA fino al 2026-09-01 COMPRESO. Il 2026-09-02 (commit ce4df470) la tassonomia e' diventata bivalente e il
  secchio "done" ha iniziato ad assorbire i risultati di partita: dopo quella data "done" non vuol piu' dire
  "trasferimento fatto".
- Si legge feed[], NON colonne[]: build.py:552 mette in colonne[].link il src_href di Google News, che nel 99,1%
  dei casi e' la sola home della testata. feed[] ha invece l'URL profondo dell'articolo, cioe' una fonte citabile.
- Le date vengono da 'aggiornato' di primo livello dello snapshot (ora di Roma): il campo 'quando' delle voci e'
  una stringa relativa ("18 g fa") calcolata al build, inutilizzabile a posteriori.
- La chiave 'squadre' NON e' il club del trasferimento (team_match assegna il titolo a chi compare nel testo:
  "Cessione da record per il Venezia" sta sotto Barcelona): il club si riestrae dal titolo.
- Il dedup di build.py vale solo dentro un singolo build e usa i primi 5 token del titolo; aggregando 91 giorni lo
  stesso trasferimento ricompare con titoli diversi, quindi qui si aggrega per GIOCATORE, non per titolo.
- Niente diff fra le rose: gli snapshot delle rose riflettono le ri-registrazioni delle liste, non i trasferimenti
  (decisione del committente, kb/RIPARTENZA.md 8).
- DATA DELL'ARTICOLO, non del feed: Google News ripropone pezzi d'archivio e il filtro dei 30 giorni di build.py
  guarda la data del feed, cosi' nell'estate 2026 sono rientrati articoli del 2017, 2019, 2022, 2023, 2025 e delle
  finestre precedenti del 2026. Quando l'URL profondo scrive la data, la si legge e si scarta cio' che sta fuori
  dalla finestra; e la data mostrata accanto a una fonte e' quella dell'articolo, altrimenti non si mostra.
- "UFFICIALE" VUOL DIRE ANNUNCIATO: contano solo i titoli che danno l'operazione per conclusa. "e' fatta",
  "visite mediche" e "firma con" dicono che l'affare e' chiuso fra le parti o imminente, non che e' stato
  annunciato, e un titolo che dichiara l'attesa nella stessa riga esce anche se contiene "ufficiale".

Uso:  py -X utf8 scripts/bilancio.py [--dry]
      --dry stampa i conteggi senza scrivere il JSON.
"""
import os, re, sys, json, subprocess, unicodedata, collections
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = "data/it/board.json"                       # percorso git (POSIX): lo storico si legge con cat-file
# Di default si scrive nelle BOZZE, non nello store che finisce online: `articles.all_articles()` legge ogni .json
# di data/articles/ e il primo render lo pubblicherebbe, anche quello lanciato dalle pianificate. Questa pagina non
# e' ancora approvata (vedi data/articles/bozze/LEGGIMI.md). Con --pubblica si scrive nello store vero.
ARTDIR = os.path.join(ROOT, "data", "articles", "bozze")
ARTDIR_ONLINE = os.path.join(ROOT, "data", "articles")
SLUG = "bilancio-mercato-estate-2026"
ROSTERS = os.path.join(ROOT, "data", "rosters", "2026-08-31.json")   # baseline congelata pre-deadline
INIZIO, FINE = "2026-06-03", "2026-09-01"          # giorni estremi della finestra (compresi)
MESI_IT = {"06": "giugno", "07": "luglio", "08": "agosto", "09": "settembre"}


# ---------------------------------------------------------------- storico della board
def _git(args, inp=None):
    p = subprocess.run(["git", "-C", ROOT] + args, input=inp, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("git " + " ".join(args) + ": " + p.stderr.decode("utf-8", "replace")[:300])
    return p.stdout


def snapshots():
    """Ogni versione storica di data/it/board.json con 'aggiornato' <= FINE, dalla piu' vecchia alla piu' recente.
    Lettura in blocco con `git cat-file --batch`: 790 `git show` separati su Windows costano minuti, questo secondi.
    MAI rigenerare data/it/board.json per leggerlo: scripts/freshness.py impone eta' max 6 ore su quel file."""
    shas = _git(["log", "--format=%H", "--", BOARD]).decode().split()
    shas.reverse()
    out = _git(["cat-file", "--batch"], inp="".join(s + ":" + BOARD + "\n" for s in shas).encode())
    i = 0
    while i < len(out):
        j = out.index(b"\n", i)
        parts = out[i:j].decode().split()
        if len(parts) < 3:                      # riga di header "<sha> blob <size>"; altro = oggetto mancante
            break
        size = int(parts[2])
        raw = out[j + 1:j + 1 + size]
        i = j + 1 + size + 1                    # +1 per il \n che chiude ogni blob
        try:
            b = json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        agg = b.get("aggiornato") or ""
        if agg and agg[:10] <= FINE:
            yield agg, b


# ---------------------------------------------------------------- normalizzazione
def norm(s):
    """Minuscolo, senza accenti, solo lettere e cifre, con uno spazio in testa e in coda.
    I bordi servono a cercare parole intere con un semplice `in`: su 800 titoli x 4000 cognomi
    le regex costerebbero un ordine di grandezza in piu'."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii").lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", s).strip() + " "


def has(tn, w):
    """True se la parola/frase w (gia' normalizzata, senza bordi) compare intera in tn."""
    return (" " + w + " ") in tn


# ---------------------------------------------------------------- filtri sul titolo
# Marcatori di ufficialita': senza uno di questi il titolo resta fuori anche se la board lo ha messo in "done".
# "annuncio" da solo non basta ("l'annuncio di Paratici sul futuro di Kean" non e' un trasferimento):
# resta solo "annuncia", che ha per soggetto il club.
# Qui stanno SOLO i marcatori di un atto compiuto e annunciato. Sono stati tolti "e fatta", "visite mediche",
# "firma con" e "firma per": dicono che l'affare e' chiuso fra le parti o imminente, non che e' stato
# annunciato, e ammettevano titoli come "Fortini e' in citta': visite mediche e poi la firma" o "Akor Adams
# al Venezia: trattativa molto avanzata". Il progetto ha una scala di concretezza proprio per non confondere
# "fatto" con "quasi fatto": chiamare "ufficiali" quei titoli gonfiava il totale dell'11%.
UFFICIALE = ("ufficiale", "ufficiali", "ufficialmente", "comunicato", "ha firmato", "annuncia", "here we go")
# Titoli che, pur contenendo un marcatore, dichiarano che l'atto deve ancora arrivare ("Inter, Stones ha
# firmato il contratto. Atteso l'annuncio ufficiale"). Il confine e' su parole intere: senza \b "frattesi"
# contiene "attesi" e "Lazio, ufficiale l'arrivo di Frattesi" verrebbe buttato via.
# Restano fuori "si avvicina", "piu' vicino", "verso il": nei titoli-raccolta ("Roma, De Roon e' ufficiale.
# E si avvicina Luiz Henrique") riguardano un ALTRO affare, e butterebbero via un'operazione davvero annunciata.
ATTESA = re.compile(r"\b(atteso|attesa|attesi|attese|in attesa|manca solo|manca l ufficialita|"
                    r"e poi la firma|poi la firma|molto avanzata|trattativa avanzata|"
                    r"nelle prossime ore|ore decisive|pronto a firmare)\b")
# Da escludere per decisione editoriale: non sono trasferimenti di calciatori.
# rinnovo/prolungamento, riscatto, risoluzione/rescissione, panchine e dirigenza, calcio non maschile di club,
# e le notizie di campo che gia' prima del 2026-09-02 finivano in "done" (formazioni, squalifiche, infortuni).
ESCLUDI = re.compile(r"(rinnov|prolung|riscatt|controriscatt|risoluzion|risolt|risolut|rescis|"
                     r"allenator|tecnic|panchin|esoner|dimission|commissario tecnico|direttore sportivo|"
                     r"direttore generale|presidente|nuovo ad |vicepresident|procurator|arbitr|"
                     r"femminil|primavera|under 1|nazionale|formazion|convocati|squalific|infortun|amichevol|"
                     r"sostituto di|si separano|separazione consensuale|saldo zero|"
                     # un'OFFERTA ufficiale non e' un trasferimento fatto; "niente"/"resta" negano il movimento
                     r"offerta ufficiale|niente |resta al |resta alla |resta in |si complica|futuro di|"
                     r"chief football officer|dirigent|nuovo ds|dice no)")
# Allenatori e dirigenti comparsi nello storico dell'estate 2026 che brain.COACHES non copre: senza questa rete
# passerebbero come "movimenti" perche' un calciatore in rosa porta lo stesso cognome (Grosso, Silva, Conte...).
PANCHINE = {"grosso", "amorim", "aquilani", "abate", "carnevali", "rangnick", "longo", "vanoli", "dionisi",
            "cuesta", "juric", "runjaic", "zanetti", "nicola", "pisacane", "chivu", "farioli", "fabregas",
            "tedesco", "gilardino", "mancini", "spalletti", "daversa", "possanzini", "stroppa", "glasner",
            "maresca", "massara", "paratici", "giuntoli", "marotta", "manna", "tare", "baroni", "palladino",
            "italiano", "tudor", "iraola", "flick", "mourinho", "sarri", "allegri", "conte", "gasperini",
            "ancelotti", "guardiola", "arteta", "slot", "postecoglou", "motta", "pioli", "inzaghi", "fonseca",
            # calcio femminile: i nomi arrivano dal campo 'nomi', che non distingue maschile e femminile
            "walti", "pelova"}


def ufficiale(tn):
    return any(has(tn, w) for w in UFFICIALE)


def attesa(tn):
    """True se il titolo dichiara che l'operazione deve ancora essere perfezionata o annunciata."""
    return bool(ATTESA.search(tn))


# ---------------------------------------------------------------- data dell'articolo (non del feed)
# Google News ripropone articoli d'archivio: nel feed dell'estate 2026 sono arrivati pezzi del 2017, 2019,
# 2022, 2023, 2025 e delle finestre precedenti del 2026 (gennaio, aprile, maggio). Il filtro dei 30 giorni di
# build.py non li ferma perche' guarda la data del FEED, non quella dell'articolo. L'unica data verificabile a
# posteriori, senza rete, e' quella che molte testate scrivono nell'URL profondo.
DATA_YMD = re.compile(r"[/_-](19\d\d|20\d\d)[/_-](0[1-9]|1[0-2])[/_-](0[1-9]|[12]\d|3[01])(?![0-9])")
DATA_DMY = re.compile(r"[/_-](0[1-9]|[12]\d|3[01])[/_-](0[1-9]|1[0-2])[/_-](19\d\d|20\d\d)(?![0-9])")
# Eurosport non mette la data ma la STAGIONE ("/calciomercato/2022-2023/..."): basta per capire che l'articolo
# non e' di quest'estate. Il mercato estivo 2026 apre la stagione 2026-2027, quindi solo quella e' accettabile.
DATA_STAGIONE = re.compile(r"[/_-](19\d\d|20\d\d)-(19\d\d|20\d\d)[/_-]")


def data_articolo(link):
    """('AAAA-MM-GG', 'esatta') | ('AAAA', 'stagione') | ('', '') se l'URL non dice nulla sulla data.
    Nessuna euristica sul contenuto: o la data e' scritta nell'URL, o si dichiara di non saperla."""
    m = DATA_YMD.search(link or "")
    if m:
        return "%s-%s-%s" % m.groups(), "esatta"
    m = DATA_DMY.search(link or "")            # gazzetta.it e fantacalcio.it scrivono GG-MM-AAAA / GG_MM_AAAA
    if m:
        return "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)), "esatta"
    m = DATA_STAGIONE.search(link or "")
    if m:
        return m.group(1), "stagione"
    return "", ""


def fuori_finestra(link):
    """True solo se l'URL dice con certezza che l'articolo e' di un'altra finestra di mercato.
    Un URL muto non fa scartare nulla: si scarta cio' che si puo' provare vecchio, non cio' che non si puo'
    datare (altrimenti sparirebbero le 162 fonti su 315 che non scrivono la data nell'URL)."""
    d, tipo = data_articolo(link)
    if tipo == "esatta":
        return d < INIZIO or d > FINE
    if tipo == "stagione":
        return d != INIZIO[:4]
    return False


def escluso(tn):
    return bool(ESCLUDI.search(tn))


def panchina(tn, chiave, full):
    """True se il titolo parla di un allenatore o di un dirigente. Il controllo e' su TRE livelli perche' uno
    solo non basta: brain.is_coach() non conosce Grosso o Glasner; il cognome del match puo' essere quello di
    un calciatore omonimo; e in "Enzo Maresca al Manchester City" il match cade su un altro nome ancora, quindi
    serve anche la scansione dell'intero titolo."""
    for n in (full, chiave):
        if n and (brain.is_coach(n) or n in PANCHINE or n.split()[-1] in PANCHINE):
            return True
    return any(has(tn, w) for w in PANCHINE)


# ---------------------------------------------------------------- dizionario dei calciatori
def dizionario_giocatori():
    """(FULL, SUR, CLUB) dai nomi delle rose congelate al 2026-08-31 (155 club, la baseline pre-deadline).
    FULL: nome completo normalizzato -> club; SUR: cognome (e doppio cognome) -> set di nomi completi.
    Il club serve solo a disambiguare gli omonimi: NON viene usato per dedurre la direzione del movimento
    (vedi la nota piu' avanti)."""
    rose = json.load(open(ROSTERS, encoding="utf-8"))["rose"]
    FULL, SUR = {}, collections.defaultdict(set)
    for club, nomi in rose.items():
        for nm in nomi:
            n = norm(nm).strip()
            if not n:
                continue
            FULL.setdefault(n, set()).add(club)
            p = n.split()
            SUR[p[-1]].add(n)
            if len(p) > 2:                      # "de winter", "loftus cheek": anche il doppio cognome
                SUR[" ".join(p[-2:])].add(n)
    return FULL, SUR


def aggiungi_nomi(SUR, FULL, nomi_storici):
    """Aggiunge al dizionario i calciatori estratti dall'LLM nel campo 'nomi' della board (segnale in piu':
    copre giugno e meta' luglio). Servono per riconoscere chi ha lasciato le tre leghe e quindi non compare
    piu' in nessuna rosa della baseline (Hojlund, Banega, Muriqi...). Nessun club associato: solo il nome."""
    add = 0
    for nm in nomi_storici:
        n = norm(nm).strip()
        if not n or len(n) < 4 or brain.is_coach(nm):
            continue
        if n not in FULL:
            FULL.setdefault(n, set())
            add += 1
        p = n.split()
        SUR[p[-1]].add(n)
    return add


# ---------------------------------------------------------------- dizionario dei club
# Come i titoli italiani chiamano i 60 club del perimetro estivo (Serie A, La Liga, Premier). Il perimetro passa
# a 69 squadre il 2026-09-03: per l'estate quello giusto e' il 60, ed e' esattamente quello che si legge negli
# snapshot dentro la finestra, quindi i nomi canonici vengono presi da li' e qui si aggiungono solo gli alias.
ALIAS_CLUB = {
    "juve": "Juventus", "vecchia signora": "Juventus", "hellas verona": "Verona", "hellas": "Verona",
    # "atletico" da solo no: nei titoli e' quasi sempre l'Atletico Mineiro o un'altra omonima
    "atletico madrid": "Atlético Madrid", "atletico de madrid": "Atlético Madrid",
    "barcellona": "Barcelona", "barca": "Barcelona", "blaugrana": "Barcelona",
    "siviglia": "Sevilla", "athletic bilbao": "Athletic Club", "bilbao": "Athletic Club", "athletic": "Athletic Club",
    "betis": "Real Betis", "celta": "Celta Vigo", "celta de vigo": "Celta Vigo", "oviedo": "Real Oviedo",
    "rayo": "Rayo Vallecano", "sociedad": "Real Sociedad", "alaves": "Alavés", "maiorca": "Mallorca",
    "manchester city": "Man City", "manchester united": "Man United", "man utd": "Man United",
    "manchester utd": "Man United", "spurs": "Tottenham", "wolverhampton": "Wolves",
    "nottingham": "Nottingham Forest", "leeds united": "Leeds", "newcastle united": "Newcastle",
    "west ham united": "West Ham", "aston villa": "Aston Villa", "crystal palace": "Crystal Palace",
    "brighton hove albion": "Brighton",
}
# Cognomi che sono anche nomi di club, citta' o parole comuni dei titoli: da soli non identificano un calciatore.
STOP_COGNOMI = set("""milan inter roma napoli lazio torino como genoa parma lecce monza sassuolo verona pisa
cremonese juventus atalanta bologna cagliari fiorentina udinese empoli venezia salernitana frosinone
arsenal chelsea everton fulham burnley leeds brighton brentford liverpool tottenham sunderland southampton
wolves villa palace forest newcastle bournemouth barcelona sevilla valencia getafe elche levante osasuna
girona alaves espanyol mallorca betis celta oviedo vigo bilbao madrid sociedad
bayern dortmund porto benfica sporting ajax psv feyenoord marsiglia monaco lens lille nizza lione
serie liga premier calcio mercato calciomercato news video live ufficiale gol rigore derby capitano
santos silva junior neto dos san jr
primo secondo terzo ultimo nuovo nuova colpo affare dettagli cifre contratto prestito titolo campo mister
capitano bomber gioiello talento giornata stagione squadra panchina esordio addio ritorno arrivo acquisto
cessione rinforzo visite firma accordo annuncio comunicato club tifosi euro milioni bonus record niente
ecco anche dopo prima ora oggi ancora sempre""".split())


def mappa_club(perimetro):
    """alias normalizzato -> nome canonico, ordinati dal piu' lungo al piu' corto (i titoli scrivono
    "Manchester United", non "United": il match lungo deve vincere su quello corto)."""
    m = {}
    for nome in perimetro:
        m[norm(nome).strip()] = nome
    for a, nome in ALIAS_CLUB.items():
        if nome in perimetro:                   # nessun alias verso club fuori perimetro
            m[a] = nome
    return sorted(m.items(), key=lambda kv: -len(kv[0]))


def trova_club(tn, mappa):
    """[(posizione nel titolo, club canonico)] senza ripetizioni, saltando gli alias contenuti in un match
    piu' lungo gia' trovato (cosi' "Manchester City" non produce anche un secondo club)."""
    out, presi = [], []
    for alias, nome in mappa:
        p = tn.find(" " + alias + " ")
        if p < 0:
            continue
        if any(p >= a and p + len(alias) <= b for a, b in presi):
            continue
        presi.append((p, p + len(alias) + 2))
        if nome not in [n for _, n in out]:
            out.append((p, nome))
    return sorted(out)


def trova_giocatore(tn, FULL, SUR):
    """(chiave, nome_completo|'', posizione) del calciatore citato nel titolo, oppure (None, motivo).
    Prima i nomi completi (piu' affidabili), poi i cognomi; i match contenuti dentro un match piu' lungo
    vengono scartati ("de winter" annulla "winter", "rafael leao" annulla "leao").
    Se restano PIU' calciatori diversi si torna None con motivo 'multi': lo schema a un record per titolo
    sbaglia l'abbinamento del club nei titoli-raccolta ("Ufficiali: Ndiaye al City, Sanchez al Como"),
    e attribuire male e' peggio che non attribuire."""
    cand = []                                    # (inizio, fine, chiave, nome_completo)
    for full in FULL:
        p = tn.find(" " + full + " ")
        if p >= 0:
            cand.append((p, p + len(full), full, full))
    for cog, fulls in SUR.items():
        if cog in STOP_COGNOMI or len(cog) < 4:
            continue
        p = tn.find(" " + cog + " ")
        if p >= 0:
            cand.append((p, p + len(cog), cog, sorted(fulls)[0] if len(fulls) == 1 else ""))
    tenuti = []
    for a, b, k, full in sorted(cand, key=lambda c: -(c[1] - c[0])):
        if not any(x <= a and b <= y for x, y, _, _ in tenuti):
            tenuti.append((a, b, k, full))
    if not tenuti:
        return None, "assente"
    if len(tenuti) > 1:
        return None, "multi"
    a, _, k, full = tenuti[0]
    return (k, full, a), ""


# NOTA sulla direzione del movimento. Un primo tentativo di ricostruire chi arriva e chi parte (preposizioni
# del titolo piu' la rosa di arrivo della baseline) e' stato tolto perche' sbagliava troppo: "Di Gregorio dalla
# Juve al Bournemouth" e "Bournemouth, ufficiale Di Gregorio" descrivono lo stesso affare in ordine opposto, e
# la baseline delle rose non fa da giudice perche' fotografa le liste depositate, non i trasferimenti (e' la
# stessa ragione per cui il diff fra le rose e' stato scartato in partenza). Il bilancio conta quindi le
# OPERAZIONI e i CLUB coinvolti, e dichiara in pagina di non ricostruire il verso.


# ---------------------------------------------------------------- raccolta e ricostruzione
def raccogli():
    """Legge lo storico una volta sola e torna (voci, perimetro, nomi_llm, meta).
    voci: una per TITOLO distinto in stato 'done' del feed, con la prima data in cui e' comparso.
    perimetro: club -> lega, cosi' come stava nella board dentro la finestra (60 squadre).
    nomi_llm: i nomi di calciatore estratti dall'LLM nel campo 'nomi' (segnale in piu' per il dizionario)."""
    voci, perimetro, nomi_llm = {}, {}, set()
    n_snap, giorni = 0, set()
    for agg, b in snapshots():
        n_snap += 1
        giorni.add(agg[:10])
        for team, td in (b.get("squadre") or {}).items():
            perimetro.setdefault(team, td.get("league") or "")
            for m in (td.get("nomi") or {}).values():
                for x in (m or []):
                    if x.get("giocatore"):
                        nomi_llm.add(x["giocatore"])
            for it in (td.get("feed") or []):
                if it.get("stato") != "done":
                    continue
                t = (it.get("titolo") or "").strip()
                if not t or t in voci:
                    continue
                voci[t] = {"titolo": t, "fonte": it.get("fonte") or "", "link": it.get("link") or "",
                           "affidabilita": int(it.get("affidabilita") or 1), "ts": agg, "giorno": agg[:10]}
    meta = {"snapshot": n_snap, "giorni": len(giorni),
            "primo": min(giorni) if giorni else "", "ultimo": max(giorni) if giorni else ""}
    return voci, perimetro, nomi_llm, meta


def ricostruisci():
    """Dallo storico ai movimenti aggregati per calciatore. Torna (movimenti, scarti, meta)."""
    voci, perimetro, nomi_llm, meta = raccogli()
    FULL, SUR = dizionario_giocatori()
    meta["nomi_llm"] = aggiungi_nomi(SUR, FULL, nomi_llm)
    meta["perimetro"] = len(perimetro)
    meta["titoli_done"] = len(voci)
    mappa = mappa_club(perimetro)
    scarti = collections.Counter()
    mov = {}
    for t, v in sorted(voci.items(), key=lambda kv: kv[1]["ts"]):
        tn = norm(t)
        if not ufficiale(tn):
            scarti["senza marcatore di ufficialita'"] += 1; continue
        if attesa(tn):
            scarti["dato per imminente, non ancora concluso"] += 1; continue
        if escluso(tn):
            scarti["rinnovo, riscatto, risoluzione, panchina o notizia di campo"] += 1; continue
        g, motivo = trova_giocatore(tn, FULL, SUR)
        if g is None:
            scarti["nessun calciatore riconosciuto" if motivo == "assente" else "piu' calciatori nello stesso titolo"] += 1
            continue
        chiave, full, _ = g
        if panchina(tn, chiave, full):
            scarti["allenatore o dirigente"] += 1; continue
        clubs = trova_club(tn, mappa)
        if not clubs:
            scarti["nessun club del perimetro nel titolo"] += 1; continue
        # Ultimo filtro, e apposta l'ultimo: cosi' il conteggio dice quanti titoli SAREBBERO stati contati
        # come mercato 2026 pur essendo articoli d'archivio ripescati da Google News.
        if fuori_finestra(v["link"]):
            scarti["articolo di una finestra precedente"] += 1; continue
        # Chiave di aggregazione: il COGNOME, non il titolo. dedupe() di build.py confronta i primi 5 token del
        # titolo e vale solo dentro un singolo build: su 91 giorni lo stesso trasferimento ricompare con titoli
        # diversi ("Vojvoda del Como", "Mergim Vojvoda e' un nuovo giocatore dell'Udinese"), e il nome a volte
        # c'e' e a volte no. Aggregare per cognome li rimette insieme; il prezzo e' che due omonimi si fondono.
        base = full or chiave
        k = base.split()[-1]
        if k in STOP_COGNOMI:                   # "Bernardo Silva" e "Marco Silva" non sono la stessa persona
            k = base
        m = mov.get(k)
        if m is None:
            m = mov[k] = {"chiave": k, "giocatore": full or chiave, "club": [],
                          "primo": v["giorno"], "ultimo": v["giorno"], "fonti": []}
        if full and len(m["giocatore"].split()) < len(full.split()):
            m["giocatore"] = full                # tieni la forma piu' completa del nome incontrata
        for _, cn in clubs:
            if cn not in m["club"]:
                m["club"].append(cn)
        m["ultimo"] = max(m["ultimo"], v["giorno"])
        m["primo"] = min(m["primo"], v["giorno"])
        m["fonti"].append(v)
    for m in mov.values():
        m["fonti"].sort(key=lambda f: (-f["affidabilita"], f["ts"]))
        m["affidabilita"] = m["fonti"][0]["affidabilita"]
        m["testate"] = sorted({f["fonte"] for f in m["fonti"]})
        m["leghe"] = sorted({perimetro.get(x, "") for x in m["club"]} - {""})
    meta["perimetro_mappa"] = perimetro
    return sorted(mov.values(), key=lambda m: (m["primo"], m["giocatore"])), scarti, meta


# ---------------------------------------------------------------- conteggi
LEGHE = ("Serie A", "La Liga", "Premier")
LEGA_IT = {"Serie A": "Serie A", "La Liga": "Liga", "Premier": "Premier League"}
LEGA_EN = {"Serie A": "Serie A", "La Liga": "LaLiga", "Premier": "Premier League"}


def conteggi(mov, meta, scarti):
    """Tutti i numeri che l'articolo puo' citare. Nessuno e' una stima: ognuno e' un conteggio rifacibile
    lanciando di nuovo lo script sullo stesso storico.
    NON si contano arrivi e partenze. La direzione del movimento non e' ricostruibile in modo affidabile:
    i titoli la scrivono in ogni ordine ("Di Gregorio dalla Juve al Bournemouth" contro "Bournemouth, ufficiale
    Di Gregorio") e la baseline delle rose, unico ancoraggio alternativo, riflette le ri-registrazioni delle
    liste e non i trasferimenti (e' la ragione per cui il diff fra le rose e' stato scartato in partenza).
    Si conta quindi cio' che la fonte dice davvero: quante operazioni ufficiali, con quali club, quando,
    dette da chi."""
    c = {"totale": len(mov), "meta": meta, "scarti": scarti}
    c["mese"] = collections.Counter(MESI_IT.get(m["primo"][5:7], m["primo"][5:7]) for m in mov)
    c["giorno"] = collections.Counter(m["primo"] for m in mov)
    c["fonti"] = collections.Counter(f["fonte"] for m in mov for f in m["fonti"])
    c["testate"] = len(c["fonti"])
    c["titoli_usati"] = sum(len(m["fonti"]) for m in mov)
    # quanti dei titoli superstiti portano nell'URL una data verificabile: e' la quota di materiale su cui il
    # controllo della finestra ha davvero potuto pronunciarsi, e va detta in pagina.
    c["datati"] = sum(1 for m in mov for f in m["fonti"] if data_articolo(f["link"])[1] == "esatta")
    # affidabilita' della fonte migliore di ogni operazione (campo 'affidabilita' della board: 3 = testata
    # primaria, 2 = quotidiano sportivo, 1 = aggregatore o sito minore)
    c["affidabilita"] = collections.Counter(m["affidabilita"] for m in mov)
    # corroborazione: quante TESTATE DIVERSE hanno dato la stessa operazione
    c["testate_per_op"] = collections.Counter(min(len(m["testate"]), 3) for m in mov)
    lega = {L: sum(1 for m in mov if L in m["leghe"]) for L in LEGHE}
    c["lega"] = lega
    c["due_leghe"] = sum(1 for m in mov if len(m["leghe"]) > 1)
    club = collections.Counter()
    for m in mov:
        for x in m["club"]:
            club[x] += 1
    c["club"] = club
    c["club_coinvolti"] = len(club)
    c["un_solo_club"] = sum(1 for m in mov if len(m["club"]) == 1)
    return c


def stampa(mov, scarti, c):
    """Diagnostica su stdout: e' il contratto di questo script, i numeri dell'articolo si leggono qui."""
    mt = c["meta"]
    print("finestra:", mt["primo"], "->", mt["ultimo"], "|", mt["snapshot"], "snapshot in", mt["giorni"], "giorni")
    print("perimetro:", mt["perimetro"], "squadre | titoli 'done' distinti nel feed:", mt["titoli_done"],
          "| nomi aggiunti dal campo 'nomi':", mt["nomi_llm"])
    print("scartati:")
    for k, n in scarti.most_common():
        print("   %5d  %s" % (n, k))
    print("titoli superstiti con data verificabile nell'URL:", c["datati"], "su", c["titoli_usati"])
    print("OPERAZIONI UFFICIALI RICOSTRUITE:", c["totale"], "| titoli che le sostengono:", c["titoli_usati"],
          "| club coinvolti:", c["club_coinvolti"], "| testate:", c["testate"])
    print("per lega (almeno un club della lega):",
          "  ".join("%s %d" % (L, c["lega"][L]) for L in LEGHE), "| fra due leghe diverse:", c["due_leghe"])
    print("affidabilita della fonte migliore:", dict(sorted(c["affidabilita"].items())))
    print("testate diverse per operazione (1 / 2 / 3+):",
          [c["testate_per_op"].get(k, 0) for k in (1, 2, 3)])
    print("mese di prima comparsa:", dict(c["mese"]))
    print("club piu' citati:", c["club"].most_common(12))
    print("fonti piu' citate:", c["fonti"].most_common(10))
    print("operazioni con un solo club nel titolo:", c["un_solo_club"])


# ---------------------------------------------------------------- testo dell'articolo
def _elenco(coppie, ultimo=" e "):
    """"Parma (17), Torino (16) e Roma (14)": elenco leggibile di coppie (nome, numero)."""
    v = ["%s (%d)" % (n, k) for n, k in coppie]
    return (", ".join(v[:-1]) + ultimo + v[-1]) if len(v) > 1 else (v[0] if v else "")


def _q(n, sing, plur):
    """"1 titolo" / "16 titoli": i conteggi degli scarti sono vivi e possono valere 1, quindi il plurale non
    puo' stare scritto nella frase."""
    return "%d %s" % (n, sing if n == 1 else plur)


def numeri(c):
    """Valori gia' formattati per il testo: ogni cifra che finisce in una frase passa di qui, cosi' non ce ne
    sono di scritte a mano. Se un dato non c'e', non esiste la frase che lo cita."""
    mt = c["meta"]
    top = c["club"].most_common(4)
    sc = c["scarti"]
    return {
        "tot": c["totale"], "titoli": c["titoli_usati"], "club": c["club_coinvolti"],
        "testate": c["testate"], "snapshot": mt["snapshot"], "giorni": mt["giorni"],
        "done": mt["titoli_done"], "perimetro": mt["perimetro"],
        "sa": c["lega"]["Serie A"], "liga": c["lega"]["La Liga"], "pl": c["lega"]["Premier"],
        "incrocio": c["due_leghe"],
        "giu": c["mese"].get("giugno", 0), "lug": c["mese"].get("luglio", 0),
        "ago": c["mese"].get("agosto", 0), "set": c["mese"].get("settembre", 0),
        "top": _elenco(top[1:]), "top_en": _elenco(top[1:], " and "), "top_es": _elenco(top[1:], " y "),
        "primo_club": top[0][0], "primo_club_n": top[0][1],
        "aff3": c["affidabilita"].get(3, 0), "aff2": c["affidabilita"].get(2, 0),
        "aff1": c["affidabilita"].get(1, 0),
        "due": c["testate_per_op"].get(2, 0) + c["testate_per_op"].get(3, 0),
        "tre": c["testate_per_op"].get(3, 0),
        "f1": _elenco(c["fonti"].most_common(3)), "f1_en": _elenco(c["fonti"].most_common(3), " and "),
        "f1_es": _elenco(c["fonti"].most_common(3), " y "),
        "multi": sc.get("piu' calciatori nello stesso titolo", 0),
        "senza_nome": sc.get("nessun calciatore riconosciuto", 0),
        "senza_club": sc.get("nessun club del perimetro nel titolo", 0),
        "senza_uff": sc.get("senza marcatore di ufficialita'", 0),
        "esclusi": sc.get("rinnovo, riscatto, risoluzione, panchina o notizia di campo", 0),
        "attesa": sc.get("dato per imminente, non ancora concluso", 0),
        "archivio": sc.get("articolo di una finestra precedente", 0),
        "datati": c["datati"],
        "attesa_it": _q(sc.get("dato per imminente, non ancora concluso", 0), "titolo", "titoli"),
        "attesa_en": _q(sc.get("dato per imminente, non ancora concluso", 0), "headline", "headlines"),
        "attesa_es": _q(sc.get("dato per imminente, non ancora concluso", 0), "titular", "titulares"),
        "archivio_it": _q(sc.get("articolo di una finestra precedente", 0), "titolo", "titoli"),
        "archivio_en": _q(sc.get("articolo di una finestra precedente", 0), "headline", "headlines"),
        "archivio_es": _q(sc.get("articolo di una finestra precedente", 0), "titular", "titulares"),
    }


def testo_it(n):
    """Testo italiano. Scritto sui conteggi di numeri(): nessuna chiamata a un LLM, nessuna cifra che lo script
    non sappia rifare, nessun aggettivo che i dati non reggano."""
    return {
        "title": "Mercato estivo 2026: il bilancio in {tot} operazioni".format(**n),
        "lead": ("Dal 3 giugno al 1 settembre 2026 TransferBeat ha classificato {tot} operazioni di mercato "
                 "ufficiali che coinvolgono {club} club. Ecco i numeri, e i limiti della ricostruzione.").format(**n),
        "body": [
            ("Il bilancio nasce dall'archivio del sito: {snapshot} versioni della board delle notizie salvate in "
             "{giorni} giorni, una per ogni aggiornamento. Da quelle versioni escono {done} titoli distinti che il "
             "sito aveva già classificato come fatto compiuto. Restano solo quelli che annunciano l'operazione "
             "come conclusa — «ufficiale», «il comunicato», «annuncia», «ha firmato» — e non quelli che la danno "
             "per imminente: «è fatta», «visite mediche» e «attesa la firma» dicono che l'affare non è ancora "
             "stato annunciato. Per questo escono {senza_uff} titoli senza nessun marcatore di operazione "
             "conclusa, e {attesa_it} in cui il marcatore c'è ma la frase se lo riprende («ha firmato il "
             "contratto, atteso l'annuncio ufficiale»). Via anche "
             "rinnovi, riscatti, risoluzioni, cambi di panchina e notizie di campo ({esclusi} titoli). Restano "
             "{titoli} titoli utili: rimessi insieme i doppioni sullo stesso giocatore diventano {tot} operazioni "
             "distinte.").format(**n),
            ("Un controllo in più riguarda la data dell'articolo, che non è quella in cui la notizia è comparsa "
             "nel feed. Google News ripropone pezzi d'archivio, e il filtro sull'età che il sito applica in "
             "raccolta guarda la data del feed: così nell'estate 2026 sono rientrati articoli del 2017, del 2019, "
             "del 2022 e delle finestre precedenti del 2026. Quando l'URL dell'articolo contiene la data — accade "
             "per {datati} dei {titoli} titoli usati — quella data viene letta e ciò che sta fuori dalla finestra "
             "viene scartato: {archivio_it}, fra cui la cessione di Muriqi al Mallorca del luglio 2022 e "
             "quella di Banega al Siviglia del 2017. Per la stessa ragione, nell'elenco delle fonti in fondo alla "
             "pagina la data compare solo quando è quella dell'articolo: dove non è verificabile, non viene "
             "mostrata.").format(**n),
            ("Delle {tot} operazioni, {sa} coinvolgono almeno un club di Serie A, {pl} almeno un club di Premier "
             "League e {liga} almeno un club della Liga. {incrocio} mettono in contatto due campionati diversi fra "
             "i tre seguiti dal sito. I club nominati sono {club} sui {perimetro} del perimetro estivo.").format(**n),
            ("La curva segue il calendario della finestra: {giu} operazioni compaiono per la prima volta a giugno, "
             "{lug} a luglio, {ago} ad agosto e {set} il 1 settembre, ultimo giorno coperto. Il club citato più "
             "spesso è il {primo_club} con {primo_club_n} operazioni; dietro, {top}. La graduatoria dice quali club "
             "sono stati più nominati dalle fonti del sito, non quali hanno speso di più: pesa anche il fatto "
             "che alcune squadre hanno fra le fonti una testata locale dedicata.").format(**n),
            ("Le {tot} operazioni poggiano su {titoli} titoli di {testate} testate diverse: le più presenti sono "
             "{f1}. Per {aff3} operazioni la fonte migliore è una testata di primo livello, per {aff2} un "
             "quotidiano sportivo, per {aff1} un aggregatore o un sito minore. {due} operazioni sono state "
             "riportate da almeno due testate diverse, {tre} da tre o più.").format(**n),
            ("Che cosa questo bilancio non è. Non è l'elenco completo dei trasferimenti dell'estate 2026: è il "
             "bilancio di ciò che TransferBeat ha intercettato e classificato fra il 3 giugno e il 1 settembre "
             "2026. Restano fuori {multi} titoli che citano più di un giocatore insieme e non sono attribuibili a "
             "una sola operazione, {senza_nome} in cui nessun nome è riconoscibile e {senza_club} che non nominano "
             "nessun club del perimetro.").format(**n),
            ("Due cose il bilancio non prova nemmeno a dire. La prima è la direzione: «Di Gregorio dalla Juve "
             "al Bournemouth» e «Bournemouth, ufficiale Di Gregorio» sono lo stesso affare scritto "
             "al contrario, e le rose registrate non lo risolvono perché fotografano le liste depositate, non i "
             "trasferimenti. La seconda sono le cifre, che i titoli riportano in modo discontinuo. La finestra si "
             "chiude il 1 settembre 2026 per una ragione tecnica: dal giorno dopo la classificazione del sito è "
             "cambiata e lo stato «fatto» ha iniziato a comprendere anche i risultati delle partite, "
             "quindi i due periodi non sono confrontabili.").format(**n),
        ]}


def testo_en(n):
    return {
        "title": "Summer 2026 transfers: {tot} official deals".format(**n),
        "lead": ("Between 3 June and 1 September 2026 TransferBeat classified {tot} official transfer stories "
                 "involving {club} clubs. Here are the numbers, and the limits of the reconstruction.").format(**n),
        "body": [
            ("The review is built from the site's own archive: {snapshot} saved versions of the news board over "
             "{giorni} days, one per update. They contain {done} distinct headlines already classified as done "
             "deals. Only headlines announcing a completed move are kept — «official», «the club statement», "
             "«has signed» — and not those calling it imminent: «done deal agreed», «medical booked» and "
             "«signature awaited» all say the move has not been announced yet. That drops {senza_uff} headlines "
             "with no marker of a completed move, plus {attesa_en} carrying a marker the same sentence takes "
             "back («has signed the contract, official announcement awaited»). Contract renewals, buy-out options, terminations, managerial changes "
             "and match news go too ({esclusi} headlines). {titoli} usable headlines remain: once duplicates about "
             "the same player are merged, they become {tot} distinct deals.").format(**n),
            ("One further check is the date of the article itself, which is not the date the story showed up in "
             "the feed. Google News resurfaces archive pieces, and the age filter applied at collection time looks "
             "at the feed date: that is how articles from 2017, 2019, 2022 and from earlier 2026 windows came back "
             "in the summer of 2026. Whenever the article URL carries its date — true for {datati} of the {titoli} "
             "headlines used — that date is read and anything outside the window is dropped: {archivio_en}, "
             "among them Muriqi's July 2022 move to Mallorca and Banega's 2017 move to Sevilla. For the same "
             "reason, in the source list at the foot of the page a date is shown only when it is the article's "
             "own: where it cannot be verified, none is shown.").format(**n),
            ("Of the {tot} deals, {sa} involve at least one Serie A club, {pl} at least one Premier League club and "
             "{liga} at least one LaLiga club. {incrocio} connect two different leagues among the three the site "
             "follows. {club} of the {perimetro} clubs in the summer perimeter are named.").format(**n),
            ("The curve follows the window: {giu} deals first appear in June, {lug} in July, {ago} in August and "
             "{set} on 1 September, the last day covered. The most frequently named club is {primo_club} with "
             "{primo_club_n} deals, ahead of {top_en}. The ranking says which clubs the site's sources mentioned most, "
             "not which ones spent most: some clubs have a dedicated local outlet among those sources.").format(**n),
            ("The {tot} deals rest on {titoli} headlines from {testate} different outlets, most often {f1_en}. For "
             "{aff3} deals the best source is a first-tier outlet, for {aff2} a sports daily, for {aff1} an "
             "aggregator or a smaller site. {due} deals were reported by at least two different outlets, {tre} by "
             "three or more.").format(**n),
            ("What this review is not. It is not the complete list of the 2026 summer transfers: it is the record "
             "of what TransferBeat picked up and classified between 3 June and 1 September 2026. Left out are "
             "{multi} headlines naming more than one player at once, {senza_nome} with no recognisable name and "
             "{senza_club} naming no club of the perimeter.").format(**n),
            ("Two things the review does not attempt. The first is direction: «Di Gregorio from Juventus to "
             "Bournemouth» and «Bournemouth sign Di Gregorio» are the same deal written both ways, "
             "and registered squad lists do not settle it because they record filed lists, not transfers. The "
             "second is fees, which headlines report inconsistently. The window closes on 1 September 2026 for a "
             "technical reason: from the next day the site's classification changed and the «done» state "
             "started to include match results, so the two periods are not comparable.").format(**n),
        ]}


def testo_es(n):
    return {
        "title": "Mercado verano 2026: {tot} operaciones".format(**n),
        "lead": ("Del 3 de junio al 1 de septiembre de 2026 TransferBeat clasificó {tot} operaciones de "
                 "mercado oficiales con {club} clubes. Estos son los números y los límites de la "
                 "reconstrucción.").format(**n),
        "body": [
            ("El balance sale del archivo del propio sitio: {snapshot} versiones del tablón de noticias "
             "guardadas en {giorni} días, una por cada actualización. De ahí salen {done} titulares "
             "distintos ya clasificados como hecho consumado. Solo se conservan los que anuncian la operación "
             "como cerrada — «oficial», «el comunicado», «ha firmado» — y no los que la dan por inminente: "
             "«está hecho», «reconocimiento médico» y «a la espera de la firma» dicen que el fichaje aún no se "
             "ha anunciado. Por eso quedan fuera {senza_uff} titulares sin ninguna marca de operación cerrada, "
             "y {attesa_es} más, donde la marca está pero la propia frase la desmiente («ha firmado el "
             "contrato, se espera el anuncio oficial»). Fuera también "
             "renovaciones, opciones de compra, rescisiones, cambios de banquillo y noticias de campo ({esclusi} "
             "titulares). Quedan {titoli} titulares útiles: al unir los duplicados del mismo jugador se "
             "convierten en {tot} operaciones distintas.").format(**n),
            ("Hay un control más: la fecha del artículo, que no es la fecha en que la noticia apareció en el "
             "feed. Google News reflota piezas de archivo, y el filtro de antigüedad que el sitio aplica al "
             "recoger mira la fecha del feed: así en el verano de 2026 volvieron artículos de 2017, de 2019, de "
             "2022 y de ventanas anteriores de 2026. Cuando la URL del artículo lleva su fecha —ocurre en "
             "{datati} de los {titoli} titulares usados— esa fecha se lee y lo que cae fuera de la ventana se "
             "descarta: {archivio_es}, entre ellos el traspaso de Muriqi al Mallorca de julio de 2022 y el "
             "de Banega al Sevilla de 2017. Por la misma razón, en la lista de fuentes del pie de página la fecha "
             "solo aparece cuando es la del artículo: donde no se puede verificar, no se muestra.").format(**n),
            ("De las {tot} operaciones, {sa} implican al menos a un club de la Serie A, {pl} al menos a uno de la "
             "Premier League y {liga} al menos a uno de LaLiga. {incrocio} conectan dos ligas distintas entre las "
             "tres que sigue el sitio. Se nombran {club} de los {perimetro} clubes del perímetro de "
             "verano.").format(**n),
            ("La curva sigue el calendario: {giu} operaciones aparecen por primera vez en junio, {lug} en julio, "
             "{ago} en agosto y {set} el 1 de septiembre, último día cubierto. El club más citado es "
             "el {primo_club} con {primo_club_n} operaciones; detrás, {top_es}. La clasificación dice a qué "
             "clubes citaron más las fuentes del sitio, no cuáles gastaron más: algunos tienen entre "
             "esas fuentes un medio local dedicado.").format(**n),
            ("Las {tot} operaciones se apoyan en {titoli} titulares de {testate} medios distintos, sobre todo "
             "{f1_es}. En {aff3} operaciones la mejor fuente es un medio de primer nivel, en {aff2} un diario "
             "deportivo y en {aff1} un agregador o un sitio menor. {due} operaciones las dieron al menos dos medios "
             "distintos y {tre}, tres o más.").format(**n),
            ("Lo que este balance no es. No es la lista completa de los fichajes del verano de 2026: es el registro "
             "de lo que TransferBeat capturó y clasificó entre el 3 de junio y el 1 de septiembre de "
             "2026. Quedan fuera {multi} titulares que citan a más de un jugador a la vez, {senza_nome} sin "
             "ningún nombre reconocible y {senza_club} que no nombran a ningún club del "
             "perímetro.").format(**n),
            ("Dos cosas que el balance no intenta decir. La primera es la dirección: «Di Gregorio de la "
             "Juve al Bournemouth» y «Bournemouth, oficial Di Gregorio» son el mismo fichaje escrito "
             "al revés, y las plantillas registradas no lo resuelven porque reflejan listas depositadas, no "
             "traspasos. La segunda son las cifras, que los titulares dan de forma discontinua. La ventana se "
             "cierra el 1 de septiembre de 2026 por una razón técnica: desde el día siguiente "
             "cambió la clasificación del sitio y el estado «hecho» pasó a incluir "
             "también los resultados de los partidos, así que los dos periodos no son "
             "comparables.").format(**n),
        ]}


# ---------------------------------------------------------------- scrittura del file dell'articolo
def fonti_citate(mov, quante=12):
    """Le voci di `updates`: senza di loro la pagina esce SENZA fonti e il JSON-LD senza `citation`
    (render_articles.render_article costruisce le citazioni proprio da qui).
    Si scelgono le operazioni con la fonte piu' affidabile e piu' corroborata, un link per testata.
    La data accanto alla fonte e' quella dell'ARTICOLO letta dall'URL, non quella in cui la notizia e'
    comparsa nel feed: prima erano la stessa cosa, e un pezzo del 2022 ripescato da Google News si
    presentava in pagina con una data del 2026. Se l'URL non dice la data, la voce esce senza data
    (render_articles stampa la stringa vuota): meglio nessuna data che una data inventata.
    Per lo stesso motivo si preferiscono le fonti databili, e si scende a quelle mute solo se non bastano."""
    out, visti, testate = [], set(), set()
    ordine = sorted(mov, key=lambda m: (-m["affidabilita"], -len(m["testate"]), m["primo"]))
    for esigi_data in (True, False):
        for m in ordine:
            for f in m["fonti"]:            # le fonti dell'operazione sono gia' ordinate per affidabilita'
                if not f["link"] or f["link"] in visti or f["fonte"] in testate:
                    continue
                d, tipo = data_articolo(f["link"])
                if esigi_data and tipo != "esatta":
                    continue
                visti.add(f["link"]); testate.add(f["fonte"])
                out.append({"ts": d if tipo == "esatta" else "", "fonte": f["fonte"],
                            "tier": f["affidabilita"], "link": f["link"],
                            "stato": "done", "smentita": False, "testo": f["titolo"][:300]})
                break
            if len(out) >= quante:
                break
        if len(out) >= quante:
            break
    out.sort(key=lambda u: u["ts"], reverse=True)
    return out


def articolo(mov, c):
    """Il dizionario da salvare in data/articles/<slug>.json, nella forma che si aspetta render_articles."""
    n = numeri(c)
    cont = {"it": testo_it(n), "en": testo_en(n), "es": testo_es(n)}
    for lang, t in cont.items():
        # kb/SEO.md 0.2: il title deve stare in 60 caratteri e la prima frase del lead in 150.
        assert len(t["title"]) <= 60, "title " + lang + " di " + str(len(t["title"])) + " caratteri"
        prima = t["lead"].split(". ")[0] + "."
        assert len(prima) <= 150, "lead " + lang + ": prima frase di " + str(len(prima)) + " caratteri"
    return {"slug": SLUG, "tipo": "bilancio", "giocatore": "", "team": "", "league": "",
            "lab": "BILANCIO", "col": "#4b1d95", "stato": "done", "smentita": False,
            "updates": fonti_citate(mov), "content": cont,
            # traccia dei conteggi da cui nasce il testo: serve a rifare i conti senza rilanciare lo script
            # elenchi gia' composti fuori (servono solo alle frasi), il resto sono i conteggi grezzi
            "numeri": {k: v for k, v in n.items()
                       if k not in ("top", "top_en", "top_es", "f1", "f1_en", "f1_es",
                                    "attesa_it", "attesa_en", "attesa_es",
                                    "archivio_it", "archivio_en", "archivio_es")}}


def scrivi(art):
    """Scrive il JSON. `created`/`updated` restano quelli di prima se il contenuto non e' cambiato: rilanciare
    lo script non deve far ballare la data dell'articolo (finisce nel lastmod della sitemap)."""
    dest = ARTDIR_ONLINE if "--pubblica" in sys.argv else ARTDIR
    os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, SLUG + ".json")
    import hashlib
    sig = hashlib.md5(json.dumps([art["content"], art["updates"]], sort_keys=True,
                                 ensure_ascii=False).encode("utf-8")).hexdigest()
    ora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    vecchio = None
    if os.path.exists(path):
        try:
            vecchio = json.load(open(path, encoding="utf-8"))
        except Exception:
            vecchio = None
    art["created"] = (vecchio or {}).get("created") or ora
    art["updated"] = (vecchio or {}).get("updated") if (vecchio or {}).get("_sig") == sig else ora
    art["_sig"] = sig
    json.dump(art, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    mov, scarti, meta = ricostruisci()
    c = conteggi(mov, meta, scarti)
    stampa(mov, scarti, c)
    if "--elenco" in sys.argv:
        for m in mov:
            print("  %-10s %-24s %-32s %s" % (m["primo"], m["giocatore"][:24], ", ".join(m["club"])[:32],
                                              m["fonti"][0]["titolo"][:70]))
    art = articolo(mov, c)
    print("titolo IT (%d car.):" % len(art["content"]["it"]["title"]), art["content"]["it"]["title"])
    print("fonti citate:", len(art["updates"]), "| paragrafi:", len(art["content"]["it"]["body"]))
    if "--dry" in sys.argv:
        print("--dry: nessun file scritto")
    else:
        print("scritto:", scrivi(art))
