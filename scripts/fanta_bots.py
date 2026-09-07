#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - schiera le formazioni delle squadre BOT della lega reale "Fantamarcio 26/27" (kb/FANTATB.md §19).
Senza questo script i bot non mandano la formazione e fanno 0 ogni settimana: la lega dell'utente sarebbe falsata.

Uso: py fanta_bots.py [--giornata N] [--lega <uuid>] [--dry]
  --giornata N   giornata da schierare (default: la prima con la deadline ancora aperta)
  --lega <uuid>  lega su cui lavorare (default: Fantamarcio 26/27)
  --dry          stampa cosa farebbe, senza scrivere niente su Supabase

Come sceglie la formazione: per ogni bot prova tutti i moduli e tiene quello che massimizza la somma dei
punteggi degli 11 titolari, dove il punteggio di un giocatore è il fantavoto REALE se la sua gara è già stata
votata, altrimenti `prob_titolare/100 × fantamedia stimata`; al totale somma il modificatore difesa atteso,
perché con `mod_difesa` acceso il quarto difensore può valere più di un attaccante mediocre.

Il modificatore difesa tiene SEPARATE le due cose che la probabilità e il voto dicono (prima erano moltiplicate
fra loro, e il risultato era che il modificatore atteso usciva 0 quasi sempre - vedi `modif`):
· SE il giocatore gioca -> probabilità: decide se il blocco difensivo arriva ai 4 difensori con voto che il
  modificatore pretende, tenendo conto che chi non gioca viene sostituito dalla panchina (compute_matchday);
· QUANTO rende se gioca -> voto: entra nella media, che la tabella confronta con soglie (6,0 la più bassa)
  definite sui voti veri di chi è sceso in campo, non su voti scontati per la probabilità.

Lo script dichiara sempre su quanti giocatori sta indovinando: da dove viene la probabilità (probabili
formazioni, `player_status`, oppure il 50% di ripiego) e da dove viene la fantamedia (stagione scorsa, stagione
in corso, stima per quotazione, default piatto).

Tre regole che lo rendono sicuro da rilanciare quante volte si vuole:
1. non tocca MAI una formazione già salvata (INSERT semplice, niente upsert: se la riga c'è, Postgres
   risponde 409 e noi la lasciamo stare) - vale anche per la squadra dell'utente, che non è un bot;
2. non scrive mai dopo la deadline `matchdays.starts_at` (come fa il server in `save_lineup`);
3. schiera solo da ANTICIPO_ORE prima della deadline in poi: più indietro le probabili e gli infortuni
   sono vecchi, e siccome la prima formazione salvata è definitiva conviene aspettare i dati buoni.
"""
import sys, os, math, bisect, datetime, statistics
from fanta_common import *

# lega di default: Fantamarcio 26/27 (kb/FANTATB.md §19). L'ottava squadra, Real Picchiese, è dell'utente:
# non ha una mail @fantatb.test e quindi non viene mai considerata dallo script.
LEGA_DEFAULT = "f849d0cb-bb12-4923-9874-ca3f38493a2c"
BOT_EMAIL = "@fantatb.test"
MODULES = ["3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1"]   # gli stessi della tendina dell'app (fanta/app.js)
ANTICIPO_ORE = 36   # finestra di lavoro prima della deadline: con i cron attuali (§8) dentro ci finiscono sempre almeno 2 run
PESI_DEFAULT = {"gol": 3, "assist": 1, "rig_sbagliato": -3, "rig_parato": 3, "gol_subito": -1,
                "autogol": -2, "amm": -0.5, "esp": -1}
# tabella difesa di default = quella di Fantacalcio.it introdotta dal fix-011 (§19), usata solo se la lega non ne ha una sua
MOD_DIF_TAB = [(6.0, 0.5), (6.25, 1.0), (6.5, 2.0), (6.75, 3.0), (7.0, 4.5), (7.25, 6.0), (7.5, 7.5)]
# coppe e nazionali: nella stima della fantamedia contano solo i campionati (una Coppa Italia da 1 presenza falserebbe la media)
CUPS = ("Cup", "Coppa", "Friendl", "Super", "Qualif", "Copa", "Coupe", "Nations", "World", "Europa",
        "Champions", "Conference", "U21", "U19", "U20", "League Cup", "Playoff")
PRES_PIENA = 5    # presenze sotto le quali il campione è corto: la stima viene tirata verso il prior per quotazione
K_QUOTA = 15      # vicini per quotazione su cui prendere la mediana quando di un giocatore non sappiamo niente
# quando NESSUNO dei giocatori in rosa ha una probabilità vera, schierare è tirare a indovinare: se alla deadline
# manca più di così aspetto il run dopo (le schedule di fanta.yml ne garantiscono almeno uno al giorno), altrimenti
# schiero lo stesso e lo dico, perché una formazione mediocre vale sempre più di uno zero a tavolino.
ULTIMA_CHIAMATA_ORE = 26

URL, KEY = supabase_conf()
_sb = 0

def sb(path, params=None, data=None, method=None, prefer=None):
    """Chiamata REST a Supabase con la service key (come fanta_demo.py), contando le chiamate per il resoconto."""
    global _sb
    h = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json",
         "Prefer": prefer or "return=representation"}
    m = method or ("POST" if data is not None else "GET")
    r = requests.request(m, URL + path, headers=h, params=params,
                         data=json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None, timeout=60)
    _sb += 1
    if r.status_code >= 300:
        raise RuntimeError("%s %s -> %s %s" % (m, path, r.status_code, r.text[:200]))
    return r.json() if r.text else None

def in_list(ids):
    """filtro PostgREST `in.(1,2,3)`: interroga solo i giocatori delle rose, così le risposte restano sotto il limite di righe"""
    return "in.(%s)" % ",".join(str(i) for i in ids)

def utc(d):
    """stampa una data sempre in UTC: PostgREST può restituire il timestamptz con un fuso diverso"""
    return d.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")

def when(s):
    """timestamptz di Supabase -> datetime con fuso (se il fuso manca lo considero UTC)"""
    if not s:
        return None
    d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)

# ---------------------------------------------------------------- punteggi attesi

def prob_probabili(md):
    """Probabilità di scendere in campo dalle probabili formazioni (data/fanta/probabili-NN.json, §20): è il numero
    più informato che abbiamo, perché fonde titolarità, infortuni e ultime formazioni ufficiali. Gli indisponibili
    (`out`) valgono 0, così non finiscono mai in campo."""
    path = os.path.join(DATA, "probabili-%02d.json" % md)
    if not os.path.exists(path):
        return {}
    d = json.load(open(path, encoding="utf-8"))
    pr = {}
    for t in (d.get("teams") or {}).values():
        for e in t.get("xi") or []:
            pr[e["id"]] = e.get("prob") or 0
            b = e.get("ballot")
            if b:
                pr.setdefault(b["id"], b.get("prob") or 0)
        for k in ("bench", "doubt"):
            for e in t.get(k) or []:
                pr.setdefault(e["id"], e.get("prob") or 0)
        for e in t.get("out") or []:
            pr[e["id"]] = 0   # infortunati e squalificati: sovrascrivono qualsiasi altra voce
    return pr

def quotazioni():
    """Quotazioni d'asta dal listone (data/fanta/listone.json): l'unico segnale che esiste per TUTTI i giocatori,
    anche per chi non ha una riga in data/stats/players.json (neopromossi, nuovi acquisti, giovani)."""
    path = os.path.join(DATA, "listone.json")
    if not os.path.exists(path):
        return {}
    return {p["id"]: p.get("price") or 0 for p in (json.load(open(path, encoding="utf-8")).get("players") or [])}

def stima_blocco(b, pesi, portiere):
    """(fantamedia, voto base, presenze) da un blocco stagionale di API-Football, None se il blocco non dice niente.
    Voto base dal rating medio (rating − 0,8 arrotondato al mezzo punto, 4..8,5 come in fanta_voti.py),
    più i bonus/malus della stagione divisi per le presenze."""
    g = b.get("games") or {}; go = b.get("goals") or {}; ca = b.get("cards") or {}; pe = b.get("penalty") or {}
    pres = g.get("appearences") or 0
    try:
        rating = float(g.get("rating")) if g.get("rating") else None
    except (TypeError, ValueError):
        rating = None
    if not pres or not rating:
        return None
    base = max(4.0, min(8.5, math.floor((rating - 0.8) * 2 + 0.5) / 2.0))
    n = lambda x: x or 0
    bon = (n(go.get("total")) * pesi["gol"] + n(go.get("assists")) * pesi["assist"]
           + n(ca.get("yellow")) * pesi["amm"] + (n(ca.get("red")) + n(ca.get("yellowred"))) * pesi["esp"]
           + n(pe.get("missed")) * pesi["rig_sbagliato"])
    if portiere:
        bon += n(go.get("conceded")) * pesi["gol_subito"] + n(pe.get("saved")) * pesi["rig_parato"]
    return round(base + bon / pres, 2), base, pres

def prior_quota(fm, vb, role):
    """Stima di ripiego per chi non ha statistiche: mediana di fantamedia e voto base dei giocatori dello STESSO
    RUOLO con quotazione vicina. Non è un numero inventato - è calibrato sui giocatori che una stima ce l'hanno
    davvero - e soprattutto non è piatto: un difensore da 1 credito e uno da 25 non possono valere entrambi 6,0,
    perché con un voto finto uguale per tutti la scelta del modulo la decide il caso."""
    q = quotazioni()
    tab = {r: sorted([(q[p], fm[p], vb[p]) for p in fm if role.get(p) == r and p in q]) for r in "PDCA"}
    def prior(pid):
        v = tab.get(role.get(pid)) or []
        x = q.get(pid)
        if x is None or not v:
            return None, None
        i = bisect.bisect_left(v, (x,))
        vic = v[max(0, i - K_QUOTA // 2):i + K_QUOTA // 2 + 1] or v
        return round(statistics.median(a[1] for a in vic), 2), round(statistics.median(a[2] for a in vic), 2)
    return prior

def fantamedie(role, pesi):
    """Fantamedia e voto base stimati per più giocatori possibile, con l'etichetta di DOVE viene la stima
    (`fonte`), perché chi lancia lo script deve sapere su quanti giocatori sta indovinando.
    Fonte dei dati: data/stats/players.json, che il cron statistiche (§14) tiene aggiornato e committa nel repo,
    così non servono chiamate ad API-Football. In ordine di affidabilità:
      1. `scorsa`  - campionato della stagione scorsa con almeno PRES_PIENA presenze (la stima usata per l'asta);
      2. `corrente`- campionato in corso, per chi la stagione scorsa non l'ha giocata qui (neopromossi, arrivi);
      3. `corta`   - stagione scorsa con poche presenze, prima scartata del tutto;
    2 e 3 hanno un campione corto: la stima viene mescolata col prior per quotazione in proporzione alle presenze,
    così 2 gol in 3 partite non diventano una fantamedia da 8. Il ripiego per quotazione (`prior`) lo applica
    `punteggi`, che sa quali giocatori servono davvero."""
    path = os.path.join(ROOT, "data", "stats", "players.json")
    if not os.path.exists(path):
        print("data/stats/players.json assente: uso le fantamedie di default")
        return {}, {}, {}, lambda pid: (None, None)
    camp = lambda bl: [b for b in (bl or []) if not any(c in (((b.get("league") or {}).get("name")) or "") for c in CUPS)]
    piu_partite = lambda bl: max(bl, key=lambda x: (x.get("games") or {}).get("appearences") or 0)
    prev, cur = {}, {}
    for k, p in (json.load(open(path, encoding="utf-8")).get("players") or {}).items():
        pid = int(k)
        gk = role.get(pid) == "P"
        for src, dove in ((camp(p.get("prev")), prev), (camp(p.get("cur")), cur)):
            if src:
                s = stima_blocco(piu_partite(src), pesi, gk)
                if s:
                    dove[pid] = s
    fm, vb, fonte = {}, {}, {}
    for pid, (f, v, pres) in prev.items():
        if pres >= PRES_PIENA:
            fm[pid], vb[pid], fonte[pid] = f, v, "scorsa"
    prior = prior_quota(fm, vb, role)   # calibrato SOLO sulle stime solide, prima di aggiungere quelle corte
    for src, tag in ((cur, "corrente"), (prev, "corta")):
        for pid, (f, v, pres) in src.items():
            if pid in fm or pres < 2:   # con una sola presenza il rating è un episodio, non una stima
                continue
            pf, pv = prior(pid)
            w = min(1.0, pres / float(PRES_PIENA))
            fm[pid] = round(w * f + (1 - w) * (pf if pf is not None else f), 2)
            vb[pid] = round(w * v + (1 - w) * (pv if pv is not None else v), 2)
            fonte[pid] = tag
    return fm, vb, fonte, prior

def punteggi(md, ids, role, pesi):
    """Ritorna score(pid) -> (punteggio, origine), voto(pid) -> (voto atteso SE gioca, probabilità che lo slot
    prenda un voto) per il modificatore difesa, e `cop` con la copertura vera dei dati.
    Il punteggio è il fantavoto REALE se la gara è già stata votata, altrimenti prob × fantamedia stimata."""
    rated = {r["player_id"]: r for r in sb("/rest/v1/player_ratings",
             {"select": "player_id,voto,fantavoto", "season": "eq.%d" % SEASON, "matchday": "eq.%d" % md, "player_id": in_list(ids)})}
    pr = prob_probabili(md)
    if not pr:
        # rumoroso di proposito: senza le probabili la scelta del modulo perde il dato migliore che abbiamo
        print("ATTENZIONE: data/fanta/probabili-%02d.json non c'è (fanta_probabili.py non ha scritto questa "
              "giornata): scendo su player_status" % md)
    stat, stat_md = {}, None
    mancanti = [i for i in ids if i not in pr]   # le probabili coprono titolari e alternative, non tutte le rose: il resto da player_status
    if mancanti:
        for k in range(md, max(0, md - 3), -1):   # giornata appena aperta: fanta_titolari.py potrebbe non averla ancora scritta
            stat = {s["player_id"]: s["prob"] for s in sb("/rest/v1/player_status",
                    {"select": "player_id,prob", "season": "eq.%d" % SEASON, "matchday": "eq.%d" % k, "player_id": in_list(mancanti)})}
            if stat:
                stat_md = k
                break
    fm, vb, fonte, prior = fantamedie(role, pesi)
    for pid in ids:   # ripiego per quotazione: applicato solo a chi serve, cioè ai giocatori delle rose
        if pid in fm:
            continue
        pf, pv = prior(pid)
        if pf is not None:
            fm[pid], vb[pid], fonte[pid] = pf, pv, "quota"
    cop = {"n": len(ids), "probabili": sum(1 for i in ids if i in pr), "status": sum(1 for i in ids if i not in pr and i in stat),
           "ignoti": sum(1 for i in ids if i not in pr and i not in stat), "status_md": stat_md,
           "fm": {t: sum(1 for i in ids if fonte.get(i) == t) for t in ("scorsa", "corrente", "corta", "quota")}}
    cop["fm"]["piatto"] = len(ids) - sum(cop["fm"].values())

    def prob(pid):
        p = pr.get(pid)
        if p is None:
            p = stat.get(pid, 50)   # sconosciuto: 50%, né titolare né riserva certa
        return p / 100.0

    def score(pid):
        r = rated.get(pid)
        if r and r["voto"] is not None:
            return float(r["fantavoto"]), "voto"
        if pid in rated:
            return 0.0, "sv"   # ha una riga ma senza voto: s.v. (meno di 15 minuti)
        return prob(pid) * fm.get(pid, 5.5 if role.get(pid) == "P" else 6.0), "atteso"

    def voto(pid):
        """(voto se scende in campo, probabilità che scenda in campo) per il modificatore difesa.
        Le due cose restano SEPARATE: il voto NON va scontato per la probabilità, perché la tabella del
        modificatore ha soglie (6,0 la più bassa) definite sui voti veri di chi ha giocato. Moltiplicandole
        fra loro un difensore da 6,5 al 90% diventava un 5,85 e la media finiva sotto la prima soglia sempre.
        Se la gara è già votata la probabilità vale 1 (ha giocato) o 0 (s.v. o non convocato)."""
        r = rated.get(pid)
        if r and r["voto"] is not None:
            return float(r["voto"]), 1.0
        if pid in rated:
            return 0.0, 0.0   # ha una riga ma senza voto: s.v., per il modificatore è come se non ci fosse
        return vb.get(pid, 6.0), prob(pid)

    return score, voto, cop

# ---------------------------------------------------------------- scelta della formazione

def panchina(by, st, bmax):
    """Panchina D-C-A-D-C-A-P: il portiere di riserva va tenuto anche a panchina corta, perché compute_matchday
    sostituisce per ruolo e senza un secondo portiere quello slot varrebbe 0. L'ORDINE conta: le sostituzioni
    partono dal primo della lista, quindi è la stessa lista che serve per stimare il modificatore difesa."""
    rest = {r: [p for p in by[r] if p not in st] for r in "PDCA"}
    panca = []
    for k in range(3):
        for r in "DCA":
            if len(rest[r]) > k:
                panca.append(rest[r][k])
    panca = panca[:max(0, bmax - 1)] + rest["P"][:1]   # l'ultimo posto è del portiere di riserva
    return panca[:bmax]

def poisson_binom(ps):
    """Distribuzione del numero di successi fra eventi indipendenti con probabilità diverse.
    Serve per una domanda che una media non sa rispondere: qual è la probabilità che ALMENO 4 difensori
    prendano un voto? Gli elementi sono al massimo 5, quindi il conto esatto costa niente."""
    d = [1.0]
    for p in ps:
        d = [(d[k] if k < len(d) else 0.0) * (1 - p) + (d[k - 1] if k else 0.0) * p for k in range(len(d) + 1)]
    return d

def best_lineup(rosa, role, score, voto, bmax, moddif):
    """Modulo che massimizza la somma dei punteggi degli 11 + il modificatore difesa atteso."""
    by = {r: sorted([p for p in rosa if role.get(p) == r], key=lambda p: -score(p)[0]) for r in "PDCA"}
    tabella = lambda avg: max([v for m, v in moddif["tab"] if avg >= m], default=0.0) if moddif else 0.0

    def modif(st):
        """Modificatore difesa atteso = P(il blocco difensivo prende voto) × valore della tabella sulla media
        dei voti attesi. Le due metà rispondono a due domande diverse e vanno calcolate diversamente:

        · SE prendono voto - il modificatore esiste solo con almeno 4 difensori con voto (più il portiere, se la
          lega lo include). Chi non gioca però viene sostituito dalla panchina, stesso ruolo e in ordine, fino a
          `max_subs` (compute_matchday, fix-011): la probabilità è quindi quella di X titolari che giocano più
          le sostituzioni che la panchina riesce a coprire, non il semplice prodotto delle probabilità.
        · QUANTO valgono - la media va fatta sui voti di chi è sceso in campo. Scontare il voto per la
          probabilità (com'era prima) abbassava la media di mezzo punto abbondante e la spingeva sotto 6,0, la
          soglia più bassa della tabella: risultato, modificatore 0 quasi sempre e scelta del modulo che di
          fatto ignorava la difesa. Per lo slot uso il voto atteso fra titolare e prima riserva, pesato sulla
          probabilità che tocchi all'uno o all'altro.

        Tre approssimazioni dichiarate, tutte dalla parte prudente: i 3 migliori li scelgo sui voti attesi invece
        che sui voti veri di chi ha giocato; `max_subs` è condiviso con centrocampo e attacco; e `prob` è la
        probabilità di essere TITOLARE, mentre per il modificatore basta prendere un voto (chi subentra a lungo
        il voto ce l'ha), quindi il modificatore atteso è una stima per difetto."""
        if not moddif:
            return 0.0
        dif = [p for p in st if role.get(p) == "D"]
        if len(dif) < 4:
            return 0.0   # con 3 difensori il modificatore non scatta mai, qualunque voto prendano
        pan = panchina(by, st, bmax)
        ris = lambda r: [voto(p) for p in pan if role.get(p) == r]   # riserve di ruolo, nell'ordine in cui entrano

        def slot(pid, riserve):
            """(voto atteso dello slot SE dà un voto, probabilità che lo dia): gioca il titolare, oppure entra
            la prima riserva del suo ruolo, oppure lo slot resta senza voto e per il modificatore non conta."""
            v, p = voto(pid)
            vr, pr_ = riserve[0] if riserve else (0.0, 0.0)
            q = p + (1 - p) * pr_
            return ((v * p + vr * (1 - p) * pr_) / q if q > 0 else 0.0), q

        rd = ris("D")
        sd = sorted([slot(p, rd) for p in dif], key=lambda x: -x[0])
        # P(≥4 difensori con voto): X titolari che giocano + le sostituzioni che la panchina copre davvero
        px = poisson_binom([voto(p)[1] for p in dif])
        py = poisson_binom([p for _, p in rd])
        p4 = sum(px[x] * py[y] for x in range(len(px)) for y in range(len(py))
                 if x + min(len(dif) - x, y, moddif["subs"]) >= 4)
        if not moddif["gk"]:
            return p4 * tabella(sum(v for v, _ in sd[:4]) / 4.0)
        g = [p for p in st if role.get(p) == "P"]
        if not g:
            return 0.0
        vg, qg = slot(g[0], ris("P"))
        return p4 * qg * tabella((sum(v for v, _ in sd[:3]) + vg) / 4.0)

    best = None
    for m in MODULES:
        d, c, a = map(int, m.split("-"))
        if len(by["P"]) < 1 or len(by["D"]) < d or len(by["C"]) < c or len(by["A"]) < a:
            continue   # rosa incompleta per questo modulo (giocatori svincolati o rosa non finita)
        st = by["P"][:1] + by["D"][:d] + by["C"][:c] + by["A"][:a]
        mdv = modif(st)
        tot = sum(score(p)[0] for p in st) + mdv
        if best is None or tot > best[0] + 1e-9:
            best = (tot, m, st, mdv)
    if best is None:
        return None
    tot, m, st, mdv = best
    return m, st, panchina(by, st, bmax), tot, mdv

def valida(mod, st, panca, rosa, role, bmax):
    """Gli stessi controlli che fa il server in save_lineup: scriviamo con la service key, quindi nessuno li fa per noi."""
    d, c, a = map(int, mod.split("-"))
    want = {"P": 1, "D": d, "C": c, "A": a}
    if len(st) != 11:
        return "titolari %d invece di 11" % len(st)
    for r in "PDCA":
        n = sum(1 for p in st if role.get(p) == r)
        if n != want[r]:
            return "modulo %s: %d %s invece di %d" % (mod, n, r, want[r])
    if len(set(st + panca)) != len(st + panca):
        return "giocatore ripetuto tra titolari e panchina"
    fuori = [p for p in st + panca if p not in rosa]
    if fuori:
        return "giocatori fuori rosa: %s" % fuori
    if len(panca) > bmax:
        return "panchina di %d > %d" % (len(panca), bmax)
    return None

def salva(row):
    """INSERT semplice, non upsert: se la formazione esiste già Postgres risponde 409 e non la sovrascriviamo."""
    global _sb
    h = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json", "Prefer": "return=minimal"}
    r = requests.post(URL + "/rest/v1/lineups", headers=h, data=json.dumps(row).encode("utf-8"), timeout=60)
    _sb += 1
    if r.status_code == 409:
        return "formazione già presente (scritta nel frattempo)"
    if r.status_code >= 300:
        return "errore %s %s" % (r.status_code, r.text[:150])
    return None

# ---------------------------------------------------------------- giornata e deadline

def scegli_giornata(mds, ora):
    """La prima giornata con la deadline ancora aperta. Le date arrivano da fanta_voti.py (sync_matchdays).
    È un criterio DIVERSO da quello di fanta_probabili.py e fanta_titolari.py, che lavorano su `max(rated)+1`,
    e la differenza non è un errore: qui si scrive una formazione, e una formazione ha senso solo per una
    giornata la cui deadline non è ancora passata. Ma i due criteri divergono appena inizia la prima partita
    della giornata N (i bot passano a N+1, probabili e titolari restano su N finché N non diventa `rated`), e
    in quella finestra il file probabili-NN.json della giornata scelta qui può non esistere: `giornata_dati` lo
    dice a voce alta invece di lasciare che lo script tiri a indovinare in silenzio."""
    futuri = [m for m in mds if when(m.get("starts_at")) and when(m["starts_at"]) > ora]
    return min(futuri, key=lambda m: m["number"]) if futuri else None

def giornata_dati(mds):
    """La giornata su cui lavorano fanta_probabili.py e fanta_titolari.py: ultima votata + 1."""
    rated = [x["number"] for x in mds if x.get("status") == "rated"]
    return (max(rated) + 1) if rated else 1

def main():
    args = sys.argv[1:]
    dry = "--dry" in args
    lega, md_forz = LEGA_DEFAULT, None
    for i, a in enumerate(args):
        if a == "--giornata" and i + 1 < len(args):
            md_forz = int(args[i + 1])
        elif a.startswith("--giornata="):
            md_forz = int(a.split("=", 1)[1])
        elif a == "--lega" and i + 1 < len(args):
            lega = args[i + 1]
        elif a.startswith("--lega="):
            lega = a.split("=", 1)[1]
    if not (URL and KEY):
        print("Supabase non configurato (supabase_keys.txt o SUPABASE_URL/SUPABASE_SERVICE_KEY): non faccio niente")
        sys.exit(1)

    l = sb("/rest/v1/leagues", {"select": "id,name,season,settings", "id": "eq." + lega})
    if not l:
        print("lega non trovata:", lega); sys.exit(1)
    l = l[0]; lid = l["id"]; s = l.get("settings") or {}; season = l.get("season") or SEASON
    bmax = s.get("bench_size", 7)
    pesi = dict(PESI_DEFAULT); pesi.update({k: v for k, v in (s.get("bonus") or {}).items() if k in PESI_DEFAULT})
    moddif = None
    if s.get("mod_difesa"):
        tab = [(float(x["min"]), float(x["v"])) for x in (s.get("mod_difesa_tab") or [])] or MOD_DIF_TAB
        moddif = {"gk": s.get("mod_difesa_portiere", True) is not False, "tab": tab,
                  "subs": int(s.get("max_subs", 3) or 3)}   # quante sostituzioni può fare compute_matchday

    ora = datetime.datetime.now(datetime.timezone.utc)
    mds = sb("/rest/v1/matchdays", {"select": "number,starts_at,status", "season": "eq.%d" % season, "order": "number"})
    if md_forz is None:
        m = scegli_giornata(mds, ora)
        if not m:
            print("nessuna giornata con la deadline ancora aperta (date in matchdays fino alla %s): niente da fare"
                  % (max([x["number"] for x in mds]) if mds else "?"))
            return
        md = m["number"]
    else:
        md = md_forz
        m = next((x for x in mds if x["number"] == md), {})
    md_dati = giornata_dati(mds)
    if md_dati != md:
        # è il caso descritto in scegli_giornata: da qui in poi probabili-NN.json della giornata md può mancare
        print("ATTENZIONE: schiero la giornata %d (prima deadline aperta) ma probabili e titolari lavorano sulla "
              "%d (ultima votata + 1): i dati della %d possono non esserci ancora" % (md, md_dati, md))
    dl = when((m or {}).get("starts_at"))
    ore = None
    if dl is None:
        print("giornata %d senza data in matchdays: schiero lo stesso (nessuna deadline da rispettare)" % md)
    else:
        ore = (dl - ora).total_seconds() / 3600.0
        if ore <= 0:
            print("giornata %d: deadline passata (%s UTC, %.1f ore fa): non schiero nessuno" % (md, utc(dl), -ore))
            return
        # con --giornata l'ordine è esplicito, quindi la finestra di attesa non si applica
        if md_forz is None and ore > ANTICIPO_ORE:
            print("giornata %d: deadline il %s UTC, mancano %.1f ore (>%d): aspetto probabili e infortuni aggiornati"
                  % (md, utc(dl), ore, ANTICIPO_ORE))
            return
        print("lega %s - giornata %d, deadline %s UTC (fra %.1f ore)%s"
              % (l["name"], md, utc(dl), ore, "  [DRY]" if dry else ""))

    membri = sb("/rest/v1/league_members", {"select": "user_id,team_name,role", "league_id": "eq." + lid})
    bot_ids = {u["id"] for u in sb("/auth/v1/admin/users", {"per_page": "200"})["users"]
               if (u.get("email") or "").lower().endswith(BOT_EMAIL)}
    # doppia rete: solo account bot E mai l'admin della lega (la squadra dell'utente non va toccata per nessun motivo)
    bots = [m for m in membri if m["user_id"] in bot_ids and m.get("role") != "admin"]
    if not bots:
        print("nessuna squadra bot in questa lega: non tocco niente"); return
    gia = {x["user_id"] for x in sb("/rest/v1/lineups", {"select": "user_id", "league_id": "eq." + lid, "matchday": "eq.%d" % md})}
    todo = [m for m in bots if m["user_id"] not in gia]
    print("squadre bot: %d, con formazione già inviata: %d, da schierare: %d"
          % (len(bots), len(bots) - len(todo), len(todo)))
    if not todo:
        print("niente da fare | chiamate Supabase %d, API-Football 0" % _sb); return
    if not sb("/rest/v1/league_fixtures", {"select": "round", "league_id": "eq." + lid, "matchday": "eq.%d" % md, "limit": "1"}):
        print("attenzione: la lega non ha un turno per la giornata %d (§19: i turni dal 5° vanno inseriti a mano); schiero lo stesso" % md)

    rosters = sb("/rest/v1/rosters", {"select": "player_id,user_id", "league_id": "eq." + lid})
    ids = sorted({r["player_id"] for r in rosters})
    pl = sb("/rest/v1/players", {"select": "id,name,role", "id": in_list(ids)})
    role = {p["id"]: p["role"] for p in pl}; name = {p["id"]: p["name"] for p in pl}
    score, voto, cop = punteggi(md, ids, role, pesi)

    # dichiarare la copertura non è cosmetica: su questi numeri si capisce se lo script sta stimando o indovinando
    print("probabilità (%d giocatori in rosa): %d dalle probabili, %d da player_status%s, %d sconosciuti al 50%%"
          % (cop["n"], cop["probabili"], cop["status"],
             (" della giornata %d" % cop["status_md"]) if cop["status_md"] else "", cop["ignoti"]))
    f = cop["fm"]
    print("fantamedia: %d stagione scorsa, %d stagione in corso, %d campione corto, %d stimati per quotazione, "
          "%d default piatto" % (f["scorsa"], f["corrente"], f["corta"], f["quota"], f["piatto"]))
    if cop["ignoti"] == cop["n"] and md_forz is None and ore is not None and ore > ULTIMA_CHIAMATA_ORE:
        print("nessuna probabilità vera per la giornata %d: schierare adesso vorrebbe dire scegliere il modulo a "
              "caso. Mancano %.1f ore alla deadline e prima c'è almeno un altro run: riprovo al prossimo giro "
              "(per forzare: --giornata %d)." % (md, ore, md))
        return
    if cop["ignoti"] == cop["n"]:
        print("ATTENZIONE: nessuna probabilità vera, tutti al 50%: il modulo lo sceglie la sola fantamedia. "
              "Schiero lo stesso perché una formazione mediocre vale più di uno zero a tavolino.")

    fatte, saltate = 0, 0
    for m in sorted(todo, key=lambda x: x["team_name"]):
        rosa = [r["player_id"] for r in rosters if r["user_id"] == m["user_id"]]
        best = best_lineup(rosa, role, score, voto, bmax, moddif)
        if best is None:
            print("  %-24s rosa incompleta (%d giocatori): salto" % (m["team_name"], len(rosa))); saltate += 1; continue
        mod, st, panca, tot, mdv = best
        err = valida(mod, st, panca, set(rosa), role, bmax)
        if err:
            print("  %-24s formazione non valida (%s): salto" % (m["team_name"], err)); saltate += 1; continue
        print("  %-24s %s  atteso %6.2f (mod. difesa %.2f) | %s" % (m["team_name"], mod, tot, mdv,
              ", ".join(name.get(p, str(p)) + ("*" if score(p)[1] == "atteso" else "") for p in st)))
        print("  %-24s panchina: %s" % ("", ", ".join(name.get(p, str(p)) for p in panca)))
        if dry:
            continue
        err = salva({"league_id": lid, "user_id": m["user_id"], "matchday": md, "module": mod, "starters": st, "bench": panca})
        if err:
            print("  %-24s NON salvata: %s" % (m["team_name"], err)); saltate += 1
        else:
            fatte += 1
    print("giornata %d: %s%d formazioni, %d saltate, %d già presenti | chiamate Supabase %d, API-Football 0"
          % (md, "(dry) " if dry else "", len(todo) - saltate if dry else fatte, saltate, len(bots) - len(todo), _sb))

if __name__ == "__main__":
    main()
