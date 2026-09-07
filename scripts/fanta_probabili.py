#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - probabili formazioni della prossima giornata, costruite SOLO dai nostri dati (kb/FANTATB.md §20).
Per ogni squadra: modulo e undici dell'ultima formazione ufficiale (API-Football /fixtures/lineups, con la griglia delle posizioni),
probabilità di ogni giocatore dalle ultime 3 formazioni ufficiali (pesi 0,5/0,3/0,2) fusa con l'indice di titolarità (titolari-NN.json),
indisponibili e squalificati dall'indice, sostituti scelti per posizione, ballottaggi quando l'alternativa è vicina.
Due correzioni sopra la base statistica (2026-09-07, chiudono i limiti dichiarati in kb/FANTATB.md §20):
  - turnover di coppa: se la squadra gioca in Europa nei giorni prima (calendario di data/competizioni.json), i titolari perdono
    qualche punto e le alternative lo guadagnano, a somma esattamente zero (§ "TURNOVER DI COPPA" qui sotto);
  - profilo dei giocatori con poche presenze: quotazione del listone e minuti giocati alzano di poco chi non ha formazioni
    recenti, senza mai superare il tasso base che misuriamo sui nostri stessi dati (§ "POCHE PRESENZE" qui sotto).
Nessuna delle due può produrre un numero che avrebbe bisogno di una nota a margine: la pagina (scripts/render_probabili.py)
pubblica solo `prob`, non legge né `note` né i motivi per giocatore, quindi ogni percentuale deve reggersi da sola.

Campi di data/fanta/probabili-NN.json aggiunti dalle due correzioni (dato pubblico CC BY 4.0: sono SEMPRE presenti, con
valore neutro quando non c'è nulla da dire, così il contratto verso chi lo consuma non cambia da una giornata all'altra):
  - `note` (stringa): come sono costruite le percentuali. Sempre valorizzata.
  - `coppe` (oggetto): {squadra: impegno europeo} per le squadre che ne hanno uno nella finestra; `{}` se nessuna.
  - `teams[X].coppa`: lo stesso impegno della squadra X, oppure null.
Il motivo per giocatore resta nel campo `why`, che esisteva già.

  py scripts/fanta_probabili.py [giornata] [--out CARTELLA] [--no-coppe] [--no-esordienti]
     scrive data/fanta/probabili-NN.json (giornata = ultima rated + 1 se omessa).
     --out scrive in un'altra cartella (anche la cache lineups.json): serve per provare senza toccare gli artefatti di produzione.
     --no-coppe / --no-esordienti disattivano una delle due correzioni: servono per il confronto A/B, non per l'uso normale.
Chiamate API: 1 (/fixtures della stagione) + 1 per ogni partita giocata non ancora in cache (data/fanta/lineups.json), quindi ~10 a settimana."""
import sys, os, json, time, datetime, re, unicodedata, math
from fanta_common import *

SPECIAL = str.maketrans({"ð": "d", "Ð": "D", "đ": "d", "Đ": "D", "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ß": "ss", "æ": "ae", "ı": "i", "İ": "I"})
def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").translate(SPECIAL)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def fix_moji(s):
    """Il feed consegna a volte nomi in UTF-8 letto come latin-1 ('OulaÃ¯', 'ObriÄ‡'): li riporto a UTF-8."""
    try:
        if any(ch in (s or "") for ch in ("Ã", "Ä", "Å", "Ð")):
            return s.encode("latin-1").decode("utf-8")
    except Exception:
        pass
    return s or ""

def make_canon(lst):
    """pid del feed -> pid del listone: stesso id, oppure stesso cognome nella stessa squadra (doppioni di id API, kb §16)."""
    by_team = {}
    for p in lst.values():
        by_team.setdefault(p.get("team"), []).append(p)
    cache = {}
    def canon(pid, name, team):
        if pid in lst:
            return pid
        k = (pid, team)
        if k in cache:
            return cache[k]
        toks = [t for t in norm(fix_moji(name)).split() if len(t) >= 3]
        best = None
        for p in by_team.get(team, []):
            ptoks = [t for t in norm(p["name"]).split() if len(t) >= 3]
            if toks and ptoks and (toks[-1] == ptoks[-1] or (len(toks[-1]) >= 5 and any(t.startswith(toks[-1]) or toks[-1].startswith(t) for t in ptoks if len(t) >= 5))):
                if best is None or len(p["name"]) < len(best["name"]):
                    best = p
        cache[k] = best["id"] if best else pid
        return cache[k]
    return canon

W = [0.5, 0.3, 0.2]                      # pesi delle ultime 3 formazioni ufficiali (dalla più recente)
POS_OF_ROLE = {"P": "G", "D": "D", "C": "M", "A": "F"}
ROLE_OF_POS = {"G": "P", "D": "D", "M": "C", "F": "A"}
CACHE = os.path.join(DATA, "lineups.json")

# ---------------------------------------------------------------- TURNOVER DI COPPA (limite 1) --------------------
# Le ultime 3 formazioni pesate 0,5/0,3/0,2 non sanno nulla del calendario: una squadra che ha giocato in Europa il mercoledì
# arriva alla domenica con tre giorni di recupero e ne cambia qualcuno. Non abbiamo (e non vogliamo) notizie dagli allenamenti,
# ma il calendario delle coppe è già nostro: data/competizioni.json (scritto da scripts/competizioni.py, fonte football-data.org).
# Al momento in cui si generano le probabili la partita di coppa spesso NON è ancora stata giocata: non possiamo sapere chi
# sarà stato titolare in coppa, quindi usiamo la nostra stessa stima come proxy (chi è più probabile in campionato è anche chi
# più probabilmente gioca in coppa, ed è quindi chi rischia di rifiatare). L'effetto è una compressione: il monte punti tolto ai
# titolari viene ridistribuito alle alternative. La somma per squadra non si sposta di un punto, nemmeno dopo l'arrotondamento
# a intero: la garanzia è nel codice di delta_turnover/interi_a_somma_zero, non solo in questo commento.
CUP_CODES = ("CL", "EL", "ECL")          # Champions, Europa, Conference in data/competizioni.json (le altre voci sono campionati)
# ATTENZIONE: oggi data/competizioni.json contiene SOLO la Champions fra queste tre, perche' scripts/competizioni.py
# scarica il set COMPS "SA,CL,PL,PD,BL1,FL1" e update.yml non lo cambia. Quindi la correzione del turnover si applica
# di fatto alle sole squadre di Champions: chi gioca Europa o Conference NON la riceve, e senza questo avviso non se ne
# accorgerebbe nessuno. Per estenderla davvero serve aggiungere EL ed ECL a COMPS (piu' chiamate a football-data e un
# competizioni.json piu' grande: e' una decisione, non un refuso). Finche' non si fa, la nota pubblicata lo dichiara.
# football-data.org usa le ragioni sociali complete; qui servono i nomi API-Football usati come chiavi di `teams`.
# Il riconoscimento normale è per sottoinsieme di token ("Napoli" ⊂ "SSC Napoli", "Como" ⊂ "Como 1907"): l'alias copre i casi
# in cui i due nomi non hanno token in comune, e va esteso se football-data cambia una ragione sociale.
ALIAS_COPPE = {"fc internazionale milano": "Inter"}
SOGLIA_TURNOVER = 55.0                   # sopra questa quota si è "titolari da far rifiatare"; sotto, si è un'alternativa
MALUS_TURNOVER = 12.0                    # punti tolti nel caso peggiore (giocatore da 95 con recupero cortissimo): correzione, non ribaltamento
TETTO_BONUS_TURNOVER = 55.0              # il solo calendario non promuove nessuno a titolare: il bonus si ferma alla soglia

def ore_fra(iso_a, iso_b):
    """Giorni fra due calci d'inizio. Entrambe le fonti danno UTC (football-data '…Z', API-Football '…+00:00'):
    taglio a 19 caratteri e confronto come naive, così non serve dateutil e non ci sono fusi di mezzo."""
    a = datetime.datetime.strptime(str(iso_a)[:19], "%Y-%m-%dT%H:%M:%S")
    b = datetime.datetime.strptime(str(iso_b)[:19], "%Y-%m-%dT%H:%M:%S")
    return (b - a).total_seconds() / 86400.0

def intensita_turnover(giorni):
    """Quanto pesa l'impegno europeo, in base ai giorni fra il calcio d'inizio di coppa e quello di campionato.
    Riferimenti reali: giovedì di Europa/Conference → domenica pomeriggio ≈ 2,9 giorni (recupero corto, rotazione pesante);
    mercoledì di Champions → domenica ≈ 3,9 giorni (il caso standard: qualche cambio, non mezza squadra);
    martedì → domenica ≈ 4,9 giorni; martedì → lunedì o mercoledì → sabato della settimana dopo ≥ 5,5 giorni: nessun effetto.
    Sotto i 3 giorni non si scende sotto il massimo perché più corto di così il calendario non lo fa mai."""
    if giorni < 0 or giorni > 7.0:
        return 0.0
    if giorni <= 3.0:
        return 1.0
    if giorni >= 5.5:
        return 0.0
    return (5.5 - giorni) / 2.5

def carica_coppe():
    """Calendario europeo da data/competizioni.json: lista di (nome football-data, kickoff UTC, competizione, avversario).
    Legge sia la fase a campionato (`giornate`) sia l'eliminazione diretta (`stages`). Se il file manca o è vecchio si torna
    a mani vuote e la correzione semplicemente non si applica: mai un errore bloccante su una fonte accessoria."""
    try:
        j = json.load(open(os.path.join(ROOT, "data", "competizioni.json"), encoding="utf-8"))
    except Exception:
        return []
    out = []
    presenti = {c.get("code") for c in j.get("competizioni", [])}
    mancanti = [k for k in CUP_CODES if k not in presenti]
    if mancanti:
        # rumoroso di proposito: una coppa configurata ma assente dai dati e' una correzione che non viene applicata
        # a nessuno, e il risultato sembra identico a "quella squadra non aveva impegni".
        print("  probabili: coppe configurate ma assenti da competizioni.json:", ", ".join(mancanti),
              "- le squadre che le giocano NON ricevono la correzione del turnover")
    for c in j.get("competizioni", []):
        if c.get("code") not in CUP_CODES:
            continue
        nome = (c.get("nome") or {}).get("it") or c.get("code")
        partite = [m for gm in (c.get("giornate") or {}).values() for m in gm] + [m for st in (c.get("stages") or {}).values() for m in st]
        for m in partite:
            if not m.get("utc") or m.get("status") in ("CANCELLED", "POSTPONED"):
                continue
            h = (m.get("home") or {}).get("name") or ""; a = (m.get("away") or {}).get("name") or ""
            out.append((h, m["utc"], nome, a))
            out.append((a, m["utc"], nome, h))
    return out

def match_squadra(fd_name, nostri):
    """Nome football-data → nome API-Football, o None se non è una delle nostre squadre di Serie A."""
    n = norm(fd_name)
    alias = ALIAS_COPPE.get(n)
    if alias and alias in nostri:
        return alias
    tok = set(n.split())
    for x in nostri:
        t = set(norm(x).split())
        if t and t <= tok:   # tutti i token del nostro nome compaiono in quello lungo: "Napoli" ⊂ {ssc, napoli}
            return x
    return None

def impegni_di_coppa(nostri, kickoff):
    """Per ogni squadra della giornata, la partita di coppa più vicina PRIMA del suo calcio d'inizio di campionato.
    `kickoff` è {nome squadra: data ISO della gara di campionato}. Restituisce {nome: dict con data, competizione, avversario,
    giorni e intensità}; le squadre senza impegni non compaiono, e per loro il calcolo resta identico a prima."""
    out = {}
    for fd, utc, comp, opp in carica_coppe():
        nostro = match_squadra(fd, nostri)
        if not nostro or nostro not in kickoff:
            continue
        giorni = ore_fra(utc, kickoff[nostro])
        if giorni <= 0 or giorni > 7.0:
            continue
        w = intensita_turnover(giorni)
        if w <= 0:
            continue
        # se ci fossero più impegni nella finestra tengo il più vicino, cioè quello che pesa di più
        if nostro not in out or giorni < out[nostro]["giorni"]:
            out[nostro] = {"data": utc, "competizione": comp, "avversario": opp, "giorni": round(giorni, 2), "intensita": round(w, 3)}
    return out

def interi_a_somma_zero(delta, capienza):
    """Da delta frazionari a somma zero a delta INTERI a somma zero (metodo del resto più grande).
    Serve perché il JSON pubblica percentuali intere: arrotondando un giocatore alla volta la somma per squadra
    si sposterebbe di qualche punto, ed è esattamente la deriva che vogliamo evitare. Parto dal pavimento di
    ogni delta e distribuisco i +1 mancanti a chi ha il resto più grande; salto chi sfonderebbe il proprio tetto
    di bonus (il suo +1 finisce su un titolare, cioè gli toglie un punto di malus: la somma resta zero)."""
    base = {pid: int(math.floor(d)) for pid, d in delta.items()}
    manca = -sum(base.values())   # la somma dei delta è 0, quindi questo è il numero di +1 da assegnare (0 ≤ manca < n)
    for pid in sorted(delta, key=lambda pid: (-(delta[pid] - base[pid]), pid)):
        if manca <= 0:
            break
        if pid in capienza and base[pid] + 1 > capienza[pid] + 1e-9:
            continue
        base[pid] += 1; manca -= 1
    return {pid: v for pid, v in base.items() if v}

def delta_turnover(prob, pos_of, intensita):
    """Variazioni {pid: delta intero} per un turno dopo la coppa, a somma ESATTAMENTE zero per squadra.
    Il malus cresce linearmente con la probabilità (da 0 alla soglia fino a MALUS_TURNOVER a quota 95) e il monte punti
    tolto viene ridistribuito alle alternative in proporzione alla loro probabilità: le riserve credibili prendono più
    di chi non gioca mai. I portieri restano fuori da entrambi i lati: il portiere di campionato non riposa per la coppa,
    semmai è in coppa che si ruota.
    Somma zero non è un dettaglio contabile: le probabili di squadre diverse finiscono nella stessa pagina e nelle stesse
    formazioni dei bot, e una squadra che perde punti "nel nulla" perché ha giocato in Europa risulterebbe sistematicamente
    più debole delle altre. Perciò il surplus non si butta via ma si ridistribuisce finché c'è capienza sotto il tetto, e
    se la capienza totale non basta si toglie DI MENO ai titolari (fattore di scala) invece di regalare punti al vuoto;
    se non c'è nessuna alternativa che possa ricevere (capienza zero) non si applica alcun malus."""
    malus = {pid: MALUS_TURNOVER * intensita * (p - SOGLIA_TURNOVER) / (95.0 - SOGLIA_TURNOVER)
             for pid, p in prob.items() if p > SOGLIA_TURNOVER and pos_of(pid) != "G"}
    monte = sum(malus.values())
    # capienza di ogni alternativa: quanti punti può ancora salire prima del tetto (il calendario non promuove a titolare)
    cap = {pid: TETTO_BONUS_TURNOVER - p for pid, p in prob.items()
           if 0 < p <= SOGLIA_TURNOVER and pos_of(pid) != "G" and TETTO_BONUS_TURNOVER - p > 0}
    totale = sum(cap.values())
    if monte <= 0 or totale <= 0:
        return {}
    fattore = min(1.0, totale / monte)
    delta = {pid: -v * fattore for pid, v in malus.items()}
    resto, bonus = monte * fattore, {pid: 0.0 for pid in cap}
    while resto > 1e-9:   # riparto proporzionale; chi tocca il tetto esce dal giro e il suo residuo torna agli altri
        aperti = {pid: prob[pid] for pid in cap if bonus[pid] < cap[pid] - 1e-9}
        peso = sum(aperti.values())
        if peso <= 0:
            break
        dato = 0.0
        for pid, p in aperti.items():
            q = min(resto * p / peso, cap[pid] - bonus[pid]); bonus[pid] += q; dato += q
        resto -= dato
        if dato <= 1e-9:
            break
    delta.update(bonus)   # le due liste sono disgiunte per costruzione (prob > soglia contro prob ≤ soglia)
    return interi_a_somma_zero(delta, cap)

# ---------------------------------------------------------------- POCHE PRESENZE (limite 2) -----------------------
# Chi non è mai partito titolare nelle ultime 3 giornate resta per costruzione fra 11 e 20, anche se è l'acquisto più caro
# del reparto: lo storico delle formazioni non ce l'ha, e l'indice di titolarità (che nasce dai minuti) nemmeno. Gli altri
# segnali che possediamo dicono però qualcosa: la quotazione ufficiale del listone (quanto vale rispetto ai titolari del suo
# ruolo nella sua squadra) e i minuti per presenza di data/stats/players.json (chi gioca 90' quando gioca è un titolare).
# La correzione alza soltanto: non abbassa mai nessuno, e si applica solo quando il segnale è netto.
#
# QUANTO IN ALTO SI PUÒ ARRIVARE. Non è una scelta di gusto: il tasso base è misurabile sulle formazioni ufficiali che
# abbiamo già in cache (data/fanta/lineups.json). Il conto si rifà in dieci righe: per ogni squadra si prendono i
# giocatori visti (undici + panchina) nelle giornate precedenti, si tengono quelli con zero titolarità e si guarda
# quanti partono titolari in quella dopo. Questi sono i numeri della stagione in corso al 2026-09-07:
#   - chi NON era titolare alla giornata precedente parte titolare in quella dopo 42 volte su 264 = 15,9%;
#     restringendo a chi è quotato almeno quanto la mediana dei titolari della sua squadra: 14 su 46 = 30,4%;
#   - chi non era titolare in NESSUNA delle due giornate precedenti: 7 su 98 = 7,1%; fra i più quotati 1 su 10 = 10,0%.
# I giocatori che questa correzione tocca hanno ZERO titolarità nella finestra che guardiamo (fino a 3 giornate): stanno
# quindi nella fascia peggiore, fra il 7% e il 30%. Il tetto è 30, cioè il massimo tasso base che siamo riusciti a misurare,
# e ci arriva solo il profilo più forte. Alzare oltre significherebbe pubblicare una previsione al posto di un dato: la
# pagina stampa la percentuale nuda (render_probabili.py non legge né `note` né `why`), quindi un numero che avrebbe
# bisogno di un "attenzione, è una stima da profilo" semplicemente non va prodotto. Sotto 40 la pagina lo colora di rosso,
# che è la lettura giusta: possibile, non probabile.
CAP_PROFILO = 30.0        # tetto: il tasso base più alto che abbiamo misurato (30,4% dei più quotati rimasti fuori un turno)
SOGLIA_PROFILO = 20.0     # sotto questa stima non tocco niente: dire 16% quando il tasso base generico è 15,9% non aggiunge nulla
SALTO_PROFILO = 12.0      # rialzo massimo in una volta: il profilo conferma un segnale, non lo inventa dal nulla.
                          # Così chi era a 11 arriva al massimo a 23 e solo chi era già a 18-20 tocca il tetto di 30:
                          # l'ordine fra i giocatori resta quello che le formazioni ufficiali hanno davvero prodotto.

def stima_da_profilo(prezzo, prezzi_titolari, stat):
    """Stima 0-100 della titolarità di chi non ha formazioni recenti, tarata sui tassi base qui sopra. `prezzi_titolari`
    sono le quotazioni dei titolari dell'ultima formazione nello stesso ruolo Classic. None se manca il riferimento di mercato."""
    rif = sorted(p for p in prezzi_titolari if p)
    if not prezzo or not rif:
        return None
    mediana = rif[len(rif) // 2] if len(rif) % 2 else (rif[len(rif) // 2 - 1] + rif[len(rif) // 2]) / 2.0
    if not mediana:
        return None
    r = prezzo / float(mediana)
    # Il mercato è il segnale principale: chi è quotato quanto o più dei titolari del suo ruolo è stato preso per giocare.
    # I gradini sono i tassi base misurati: 30 = il gruppo dei più quotati, 16 ≈ il 15,9% di chiunque resti fuori un turno.
    s = 30.0 if r >= 1.25 else 22.0 if r >= 1.00 else 16.0 if r >= 0.70 else 10.0 if r >= 0.45 else 5.0
    # Minuti di questa stagione in Serie A: poche presenze ma quasi sempre per intero = titolare che è arrivato tardi.
    app, mins, prev_app, prev_lin = stat
    if app >= 1 and mins / float(app) >= 70:
        s += 4.0
    elif app >= 1 and mins / float(app) >= 45:
        s += 2.0
    # Stagione scorsa (anche in un altro campionato): chi era titolare fisso non diventa riserva cambiando maglia.
    if prev_app >= 10 and prev_lin / float(prev_app) >= 0.6:
        s += 3.0
    return s

def stat_giocatore(stats, pid):
    """(presenze, minuti, da titolare) nella Serie A in corso e (presenze, da titolare) del campionato più giocato la stagione scorsa."""
    p = (stats or {}).get(str(pid)) or {}
    app = mins = lin = 0
    for r in p.get("cur") or []:
        if (r.get("league") or {}).get("id") == LEAGUE_ID:
            g = r.get("games") or {}
            app += g.get("appearences") or 0; mins += g.get("minutes") or 0; lin += g.get("lineups") or 0
    best = None
    for r in p.get("prev") or []:
        g = r.get("games") or {}
        if best is None or (g.get("appearences") or 0) > (best.get("appearences") or 0):
            best = g
    return app, mins, lin, (best or {}).get("appearences") or 0, (best or {}).get("lineups") or 0

def carica_stats():
    """data/stats/players.json (artefatto di produzione: solo lettura). Assente = correzione da profilo senza segnale minuti."""
    try:
        return (json.load(open(os.path.join(ROOT, "data", "stats", "players.json"), encoding="utf-8")) or {}).get("players") or {}
    except Exception:
        return {}

def load_cache():
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        return {"fixtures": {}}

def lineups_of(fid, cache):
    k = str(fid)
    if k not in cache["fixtures"]:
        lu = af_get("/fixtures/lineups", fixture=fid)
        if not lu:
            return None
        cache["fixtures"][k] = [{"team": t["team"]["id"], "name": t["team"]["name"], "formation": t.get("formation"),
                                 "coach": (t.get("coach") or {}).get("name"),
                                 "xi": [{"id": p["player"]["id"], "name": p["player"]["name"], "pos": p["player"].get("pos"), "grid": p["player"].get("grid")} for p in t.get("startXI", [])],
                                 "bench": [{"id": p["player"]["id"], "name": p["player"]["name"], "pos": p["player"].get("pos")} for p in t.get("substitutes", [])]} for t in lu]
        time.sleep(0.25)
    return cache["fixtures"][k]

def leggi_argomenti(argv):
    """[giornata] [--out CARTELLA] [--no-coppe] [--no-esordienti] → (giornata|None, cartella|None, coppe, esordienti)."""
    md, out_dir, coppe, esordienti = None, None, True, True
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out" and i + 1 < len(argv):
            out_dir = argv[i + 1]; i += 2; continue
        if a == "--no-coppe":
            coppe = False
        elif a == "--no-esordienti":
            esordienti = False
        else:
            md = int(a)
        i += 1
    return md, out_dir, coppe, esordienti

def main():
    md_arg, out_dir, usa_coppe, usa_esordienti = leggi_argomenti(sys.argv[1:])
    allfx = af_get("/fixtures", league=LEAGUE_ID, season=SEASON)
    def rnd(f):
        r = f["league"]["round"]
        return int(r.split("-")[-1]) if r.startswith("Regular Season") else 0
    played = {}
    for f in allfx:
        if f["fixture"]["status"]["short"] in ("FT", "AET", "PEN") and rnd(f):
            played.setdefault(rnd(f), []).append(f)
    if md_arg is not None:
        md = md_arg
    else:
        rated = [m["number"] for m in sb_get("matchdays", {"select": "number,status", "season": "eq.%d" % SEASON, "status": "eq.rated"})]
        md = (max(rated) if rated else (max(played) if played else 0)) + 1
    fixtures = sorted([f for f in allfx if rnd(f) == md], key=lambda f: f["fixture"]["date"])
    if not fixtures:
        raise SystemExit("nessuna partita per la giornata %d" % md)
    # indice di titolarità e listone
    tit = {}
    try:
        t = json.load(open(os.path.join(DATA, "titolari-%02d.json" % md), encoding="utf-8"))
        tit = {s["player_id"]: s for s in t.get("status", [])}
    except Exception:
        pass
    lst = {p["id"]: p for p in json.load(open(os.path.join(DATA, "listone.json"), encoding="utf-8")).get("players", [])}
    cache = load_cache()
    # ultime 3 formazioni ufficiali per squadra (partite finite delle giornate precedenti, dalla più recente)
    recent_fx = [f for r in sorted([r for r in played if r < md], reverse=True)[:5] for f in played[r]]
    hist = {}   # team_id -> [lineup dict più recente prima, ...]
    for f in sorted(recent_fx, key=lambda f: f["fixture"]["date"], reverse=True):
        lu = lineups_of(f["fixture"]["id"], cache)
        for t in (lu or []):
            if len(hist.setdefault(t["team"], [])) < 3:
                t = dict(t); t["fixture"] = f["fixture"]["id"]; t["date"] = f["fixture"]["date"][:10]
                t["opponent"] = f["teams"]["away"]["name"] if f["teams"]["home"]["id"] == t["team"] else f["teams"]["home"]["name"]
                hist[t["team"]].append(t)
    if out_dir:   # prova fuori dal repo: la cache di produzione non si tocca, se ne scrive una copia accanto all'output
        os.makedirs(out_dir, exist_ok=True)
        json.dump(cache, open(os.path.join(out_dir, "lineups.json"), "w", encoding="utf-8"), ensure_ascii=False)
    else:
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    now = datetime.datetime.utcnow()
    first = min(f["fixture"]["date"] for f in fixtures)
    days = (datetime.datetime.strptime(first[:19], "%Y-%m-%dT%H:%M:%S") - now).total_seconds() / 86400
    stage = "giorno-gara" if days < 1 else ("vigilia" if days <= 3 else "settimana")
    # calcio d'inizio di ogni squadra in questa giornata: serve per misurare la distanza dall'eventuale impegno europeo
    kickoff, id_di = {}, {}
    for f in fixtures:
        for side in ("home", "away"):
            t = f["teams"][side]
            kickoff[t["name"]] = f["fixture"]["date"]; id_di[t["name"]] = t["id"]
    impegni = impegni_di_coppa(set(kickoff), kickoff) if usa_coppe else {}
    # la ricerca nel ciclo va per id squadra, non per nome: i nomi di /fixtures e di /fixtures/lineups sono gli stessi
    # ma l'id è l'unica chiave davvero sicura, e uno sbaglio qui applicherebbe il turnover alla squadra sbagliata
    impegni_id = {id_di[n]: v for n, v in impegni.items()}
    stats = carica_stats() if usa_esordienti else {}
    teams = {}
    n_profilo = 0   # quanti giocatori ha toccato la stima da profilo: serve solo al riepilogo a fine run
    canon = make_canon(lst)
    for tid, L in hist.items():
        if not L:
            continue
        name = L[0]["name"]
        for lu in L:   # id del feed -> id del listone (doppioni) e nomi ripuliti, una volta sola
            for p in lu["xi"] + lu["bench"]:
                p["id"] = canon(p["id"], p.get("name"), name); p["name"] = fix_moji(p.get("name"))
        score, seen = {}, {}
        for i, lu in enumerate(L):
            w = W[i] if i < len(W) else 0
            for p in lu["xi"]:
                score[p["id"]] = score.get(p["id"], 0) + 100 * w; seen[p["id"]] = seen.get(p["id"]) or p
            for p in lu["bench"]:
                score[p["id"]] = score.get(p["id"], 0) + 15 * w; seen[p["id"]] = seen.get(p["id"]) or p
        last_xi = {p["id"] for p in L[0]["xi"]}
        def info(pid):
            p = seen.get(pid) or {}; lp = lst.get(pid) or {}
            role = lp.get("role") or ROLE_OF_POS.get(p.get("pos") or "", "C")
            return {"id": pid, "name": lp.get("name") or p.get("name") or ("#%d" % pid), "role": role, "pos": p.get("pos") or POS_OF_ROLE[role]}
        prob, why = {}, {}
        for pid in score:
            s = tit.get(pid) or {}
            if s.get("injury") or (s.get("prob") == 0 and "squalific" in (s.get("reason") or "")):
                prob[pid] = 0; why[pid] = s.get("reason") or s.get("injury"); continue
            p0 = min(95, score[pid])
            if pid in last_xi:
                p0 = max(p0, 70)
            if s.get("prob"):
                p0 = 0.7 * p0 + 0.3 * s["prob"]
            prob[pid] = int(round(max(5, min(95, p0))))
            why[pid] = "titolare nelle ultime %d su %d" % (sum(1 for lu in L if pid in {x["id"] for x in lu["xi"]}), len(L))
        pos_of = lambda pid: (seen[pid].get("pos") or POS_OF_ROLE[info(pid)["role"]])
        xi_ids = [{x["id"] for x in lu["xi"]} for lu in L]
        # L'ordine conta: prima il turnover di coppa, poi la stima da profilo. Al contrario il bonus di rotazione si
        # sommerebbe SOPRA il tetto del profilo (K. De Bruyne finiva a 38 invece che a 30) e il tetto non sarebbe più
        # un tetto: chi non ha nessuna titolarità recente uscirebbe di nuovo con un numero che ha bisogno di una nota.
        # --- limite 1: coppe e turnover (correzione a somma zero fra titolari e alternative) ---
        imp = impegni_id.get(tid)
        if imp:
            # i delta sono già interi e a somma zero, e per costruzione lasciano prob dentro 5..95: sommarli e basta,
            # perché arrotondare o troncare qui rimetterebbe la deriva che delta_turnover si è preoccupato di togliere
            delta = delta_turnover(prob, pos_of, imp["intensita"])
            for pid, d in delta.items():
                prob[pid] += d
            # la coda va SOLO a chi la correzione ha davvero spostato. Scriverla su tutti gli undici (portiere compreso,
            # che dalla correzione e' escluso per scelta) significa pubblicare un motivo falso su un giocatore preciso.
            for pid, d in delta.items():
                if d:
                    why[pid] = (why.get(pid) or "") + " · %s il %s: possibile turnover" % (imp["competizione"], imp["data"][:10])
        # --- limite 2: chi ha poche presenze non è per forza una riserva (quotazione del listone + minuti giocati) ---
        if usa_esordienti:
            prezzi_ruolo = {}     # quotazioni dei titolari dell'ultima formazione, per ruolo Classic: il metro di paragone
            for x in L[0]["xi"]:
                lp = lst.get(x["id"]) or {}
                if lp.get("price"):
                    prezzi_ruolo.setdefault(lp.get("role"), []).append(lp["price"])
            for pid in list(prob):
                if prob[pid] <= 0 or any(pid in s for s in xi_ids):
                    continue          # indisponibile, oppure già partito titolare di recente: i dati suoi ce li ha
                app, mins, lin, prev_app, prev_lin = stat_giocatore(stats, pid)
                if lin > 1:
                    continue          # più di una gara da titolare in stagione: lo storico basta, niente stima da profilo
                lp = lst.get(pid) or {}
                stima = stima_da_profilo(lp.get("price"), prezzi_ruolo.get(lp.get("role")) or [], (app, mins, prev_app, prev_lin))
                if stima is None or stima < SOGLIA_PROFILO:
                    continue          # segnale debole (riserva pagata poco): resta dov'era
                nuovo = int(round(min(CAP_PROFILO, stima, prob[pid] + SALTO_PROFILO)))
                if nuovo > prob[pid]:
                    prob[pid] = nuovo; n_profilo += 1
                # CLAMP esplicito, non affidato al ramo qui sopra: chi non e' mai partito titolare nella finestra puo'
                # arrivare sopra CAP_PROFILO per altre strade (la fusione 70/30 con l'indice di titolarita', o il bonus
                # di rotazione). La nota pubblicata promette questo tetto: va imposto, non sperato.
                if prob[pid] > CAP_PROFILO:
                    prob[pid] = CAP_PROFILO
                    # il motivo del profilo sostituisce quello delle formazioni, ma la coda del turnover (aggiunta
                    # dal blocco qui sopra, dopo un " · ") resta: nel JSON deve restare traccia di tutto quello che ha agito
                    coda = (why.get(pid) or "").split(" · ", 1)
                    why[pid] = ("poche presenze: stima da quotazione e minuti giocati, mai sopra il %d%%" % int(CAP_PROFILO)) + \
                               ((" · " + coda[1]) if len(coda) > 1 else "")
        # slot dall'ultima formazione: chi è disponibile resta, gli altri vengono sostituiti per posizione
        assigned, xi = set(), []
        avail = lambda pid: prob.get(pid, 0) > 0 and pid not in assigned
        def best_for(pos, grid):
            cands = [pid for pid in prob if avail(pid) and (seen[pid].get("pos") or POS_OF_ROLE[info(pid)["role"]]) == pos]
            same_slot = {x["id"] for lu in L[1:] for x in lu["xi"] if x.get("grid") == grid}
            cands.sort(key=lambda pid: (-(prob[pid] + (8 if pid in same_slot else 0)), info(pid)["name"]))
            return cands[0] if cands else None
        for p in L[0]["xi"]:
            pid = p["id"] if avail(p["id"]) else best_for(p["pos"], p.get("grid"))
            if pid is None:
                continue
            assigned.add(pid); d = info(pid); d.update({"grid": p.get("grid"), "prob": prob[pid], "why": why.get(pid), "ballot": None,
                                                        "out_for": (info(p["id"])["name"] if pid != p["id"] else None)})
            xi.append(d)
        for d in xi:   # ballottaggi: alternativa vicina nella stessa posizione
            alt = [pid for pid in prob if avail(pid) and (seen[pid].get("pos") or POS_OF_ROLE[info(pid)["role"]]) == d["pos"] and prob[pid] >= 30 and prob[pid] >= d["prob"] - 30]
            if alt:
                a = max(alt, key=lambda pid: prob[pid]); assigned.add(a)
                tot = d["prob"] + prob[a]
                d["ballot"] = {"id": a, "name": info(a)["name"], "prob": prob[a], "share": int(round(100 * prob[a] / tot))}
                d["share"] = 100 - d["ballot"]["share"]
        bench = sorted([pid for pid in prob if avail(pid)], key=lambda pid: (-prob[pid], info(pid)["name"]))
        bench_rows = []
        for pos in ("G", "D", "M", "F"):
            bench_rows += [info(pid) | {"prob": prob[pid]} for pid in bench if (seen[pid].get("pos") or POS_OF_ROLE[info(pid)["role"]]) == pos][:2 if pos != "G" else 1]
        out = [info(pid) | {"reason": why[pid], "back_at": (tit.get(pid) or {}).get("back_at")} for pid in prob if prob[pid] == 0]
        doubt = [info(pid) | {"prob": prob[pid], "reason": why[pid]} for pid in prob if 0 < prob[pid] < 60 and pid in last_xi and pid not in assigned]
        teams[name] = {"id": tid, "coach": L[0].get("coach"), "module": L[0].get("formation"), "based_on": [{"fixture": lu["fixture"], "date": lu["date"], "opponent": lu["opponent"], "formation": lu.get("formation")} for lu in L],
                       "xi": xi, "bench": bench_rows, "out": sorted(out, key=lambda x: x["name"]), "doubt": doubt, "coppa": imp}
    fx_out = [{"id": f["fixture"]["id"], "date": f["fixture"]["date"], "home": f["teams"]["home"]["name"], "away": f["teams"]["away"]["name"],
               "home_id": f["teams"]["home"]["id"], "away_id": f["teams"]["away"]["id"], "venue": (f["fixture"].get("venue") or {}).get("name"), "status": f["fixture"]["status"]["short"]}
              for f in fixtures]
    missing = [n for f in fx_out for n in (f["home"], f["away"]) if n not in teams]
    # Nota del dataset: il progetto dichiara sempre che cosa è una stima e come è costruita (regola di kb/FANTATB.md §20).
    # Non è un caveat che salva un numero gonfiato — la pagina non la mostra, e i numeri devono reggersi senza —
    # ma la descrizione del metodo per chi riusa il JSON (CC BY 4.0).
    nota = ("Le percentuali sono una stima statistica costruita solo sui nostri dati: formazioni ufficiali delle ultime giornate, "
            "indice di titolarità, quotazioni del listone, minuti giocati. Non sono notizie dagli allenamenti e non riprendono le "
            "probabili di altre testate. Chi non è mai partito titolare nelle giornate che guardiamo non supera il %d%%, perché è "
            "il tasso base che misuriamo sulle nostre formazioni ufficiali: la quotazione può alzarlo dentro quel limite, non oltre." % int(CAP_PROFILO))
    if impegni:
        nota += (" Per %s la stima tiene conto dell'impegno europeo dei giorni precedenti, che di solito porta a qualche rotazione: "
                 "i titolari perdono qualche punto e le alternative lo guadagnano, senza cambiare il totale della squadra." % ", ".join(sorted(impegni)))
    # Onesta' sul perimetro: la correzione vale solo per le coppe che stanno davvero in data/competizioni.json, oggi la sola
    # Champions. Tacerlo farebbe sembrare "nessun impegno" una squadra che gioca l'Europa League il giovedi' prima.
    nota += (" La rotazione europea viene considerata per le coppe di cui seguiamo il calendario: al momento la Champions League. "
             "Chi gioca Europa o Conference League non riceve questa correzione.")
    save_json_out = (lambda nome, obj: json.dump(obj, open(os.path.join(out_dir, nome), "w", encoding="utf-8"), ensure_ascii=False, indent=0)) if out_dir else save_json
    save_json_out("probabili-%02d.json" % md, {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "season": SEASON, "matchday": md, "stage": stage,
                                               "fixtures": fx_out, "teams": teams, "missing": missing, "note": nota, "coppe": impegni})
    print("giornata %d (%s): %d partite, %d squadre con probabile, %d senza storico %s, %d chiamate API" % (md, stage, len(fx_out), len(teams), len(missing), missing, calls()))
    print("  turnover di coppa: %d squadre (%s)" % (len(impegni), ", ".join("%s %s a %.1f gg, peso %.2f" % (k, v["competizione"], v["giorni"], v["intensita"]) for k, v in sorted(impegni.items())) or "nessuna"))
    print("  stima da profilo (poche presenze): %d giocatori alzati, mai sopra il %d%%" % (n_profilo, int(CAP_PROFILO)))

if __name__ == "__main__":
    main()
