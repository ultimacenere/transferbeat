#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - stats_pull.py: statistiche di squadra e schede giocatore da API-Football -> data/stats/*.json
(kb/FANTATB.md §14). Le pagine le genera render_site.py (modulo render_stats.py), che legge solo questi JSON.

  py scripts/stats_pull.py               squadre + giocatori
  py scripts/stats_pull.py --squadre     classifiche (standings), statistiche di squadra (teams/statistics) e statistiche
                                         per partita (fixtures/statistics, solo le partite finite non ancora in cache)
                                         per le leghe di LEAGUES -> data/stats/teams.json, data/stats/matches.json
  py scripts/stats_pull.py --giocatori   rose di Serie A, profili, statistiche della stagione corrente (Serie A) e della
                                         precedente (tutte le competizioni, in cache per sempre), trasferimenti
                                         -> data/stats/players.json
  py scripts/stats_pull.py --carriera    BACKFILL ESPLICITO (mai automatico, mai nei workflow): carriera per stagione
                                         (presenze, minuti, gol, assist, cartellini per stagione e competizione) dei
                                         giocatori gia' in players.json -> data/stats/careers.json.
                                         Opzioni: --max N tetto di chiamate (default 400, si ferma li'); --dry dice
                                         quante chiamate servirebbero senza farne nessuna; --quanti N solo i primi N
                                         giocatori dell'ordine di rilevanza; --da/--fino ANNO intervallo di stagioni
                                         (default 2010 -> SEASON-2: SEASON-1 e SEASON sono gia' in players.json);
                                         --squadra <id|nome> e --solo <id,id> per lavorare su un sottoinsieme.
                                         E' RIPRENDIBILE: rilanciandolo riparte da dove era arrivato.
                                         Il riepilogo finale conta le RIGHE di carriera salvate, non solo le
                                         stagioni toccate: zero righe con chiamate spese = allarme e uscita 1.
                                         In cache finisce solo cio' che e' stato letto e capito; argomenti
                                         sconosciuti o valori storti fermano lo script invece di essere ignorati.

Chiamate: squadre ~65 + ~10 per giornata nuova per lega; giocatori ~50 a regime (rose 20, stagione corrente ~27,
trasferimenti 20) più, una tantum, 1 chiamata per giocatore per la stagione precedente e 1 per i profili mancanti.
Chiave: apifootball_key.txt nella radice del repo o variabile APIFOOTBALL_KEY (come gli altri script fanta_*)."""
import os, re, sys, time
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fanta_common import af_get, api_key, calls, SEASON, LEAGUE_ID, API
from site_common import load_json, DATA          # DATA = data/ (quella di fanta_common e' data/fanta)

STATS = os.path.join(DATA, "stats")
LEAGUES = {135: "SA", 39: "PL", 140: "PD"}     # le leghe di teams.json (Serie A, Premier League, Liga)
PLAYER_LEAGUE = LEAGUE_ID                        # schede giocatore: solo Serie A (repo e quota sotto controllo)
FINISHED = ("FT", "AET", "PEN")
PAUSE = 0.25                                     # piano Pro: 300 richieste/minuto
_extra = 0
_DRY = False                                     # --dry: vedi il blocco in af_one qui sotto

class RispostaInattesa(RuntimeError):
    """La risposta dell'API c'e' ma non ha la forma attesa (o non contiene proprio niente da leggere).
    E' volutamente una RuntimeError: cosi' finisce nello stesso conteggio degli errori API e fa scattare
    il fermo dopo CAREER_MAX_FAIL. Una forma inattesa che non solleva nulla e' il modo tipico in cui un
    dato sbagliato entra in una cache DEFINITIVA e non ne esce mai piu'."""

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def af_one(path, **params):
    """GET che restituisce la response grezza (per gli endpoint che rispondono con un oggetto, non con una lista)."""
    global _extra
    if _DRY:
        # --dry promette "nessuna chiamata": la promessa e' fatta rispettare qui, non dalla disciplina di
        # chi scrive il codice a valle. Un --dry che chiama davvero spenderebbe quota senza che nessuno lo veda.
        raise RuntimeError("--dry attivo: nessuna chiamata deve partire (tentata %s %r)" % (path, params))
    for attempt in range(4):
        r = requests.get(API + path, headers={"x-apisports-key": api_key()}, params=params, timeout=40)
        _extra += 1
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1)); continue
        r.raise_for_status(); break
    j = r.json()
    if j.get("errors"):
        raise RuntimeError("API-Football: %s" % j["errors"])
    time.sleep(PAUSE)
    return j.get("response")

def n_calls():
    return calls() + _extra

def load(name, default):
    return load_json(os.path.join(STATS, name), default) or default

def _save(name, obj):
    import json
    os.makedirs(STATS, exist_ok=True)
    with open(os.path.join(STATS, name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=0)
        f.write("\n")

def num(v):
    """'58%' -> 58, '1.93' -> 1.93, None -> None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace("%", "")
    try:
        f = float(s)
        return int(f) if f == int(f) and "." not in s else round(f, 2)
    except ValueError:
        return None

# ---------- squadre ----------
def minute_totals(d):
    return {k: ((v or {}).get("total") or 0) for k, v in (d or {}).items()}

def trim_team_stats(ts):
    g = ts.get("goals") or {}; gf = g.get("for") or {}; ga = g.get("against") or {}
    pen = ts.get("penalty") or {}; cards = ts.get("cards") or {}
    return {"form": ts.get("form") or "", "fixtures": ts.get("fixtures") or {},
            "goals_for": {"total": gf.get("total") or {}, "avg": {k: num(v) for k, v in (gf.get("average") or {}).items()}, "minute": minute_totals(gf.get("minute"))},
            "goals_against": {"total": ga.get("total") or {}, "avg": {k: num(v) for k, v in (ga.get("average") or {}).items()}, "minute": minute_totals(ga.get("minute"))},
            "biggest": ts.get("biggest") or {}, "clean_sheet": ts.get("clean_sheet") or {}, "failed_to_score": ts.get("failed_to_score") or {},
            "penalty": {"scored": (pen.get("scored") or {}).get("total") or 0, "missed": (pen.get("missed") or {}).get("total") or 0, "total": pen.get("total") or 0},
            "lineups": [{"formation": l.get("formation"), "played": l.get("played") or 0} for l in (ts.get("lineups") or [])],
            "cards": {"yellow": minute_totals(cards.get("yellow")), "red": minute_totals(cards.get("red"))}}

def trim_standing(r):
    def side(s):
        s = s or {}; g = s.get("goals") or {}
        return {"played": s.get("played") or 0, "win": s.get("win") or 0, "draw": s.get("draw") or 0, "lose": s.get("lose") or 0,
                "gf": g.get("for") or 0, "ga": g.get("against") or 0}
    a = side(r.get("all"))
    return {"rank": r.get("rank"), "team_id": r["team"]["id"], "name": r["team"]["name"], "points": r.get("points") or 0, "gd": r.get("goalsDiff") or 0,
            "form": r.get("form") or "", "description": r.get("description") or "", "all": a, "home": side(r.get("home")), "away": side(r.get("away"))}

def pull_teams():
    out = {"updated": now_iso(), "season": SEASON, "leagues": {}, "teams": {}}
    for lid, code in LEAGUES.items():
        st = af_one("/standings", league=lid, season=SEASON) or []
        rows = [trim_standing(r) for grp in ((st[0]["league"].get("standings") or []) if st else []) for r in grp]
        out["leagues"][str(lid)] = {"code": code, "name": (st[0]["league"]["name"] if st else code), "standings": rows}
        for r in rows:
            ts = af_one("/teams/statistics", league=lid, season=SEASON, team=r["team_id"])
            if ts:
                out["teams"][str(r["team_id"])] = dict({"id": r["team_id"], "name": r["name"], "league": lid}, **trim_team_stats(ts))
        print("  %s: %d squadre in classifica" % (code, len(rows)))
    _save("teams.json", out)
    return out

STAT_KEYS = {"Shots on Goal": "shots_on", "Shots off Goal": "shots_off", "Total Shots": "shots", "Blocked Shots": "blocked",
             "Shots insidebox": "inside", "Shots outsidebox": "outside", "Fouls": "fouls", "Corner Kicks": "corners", "Offsides": "offsides",
             "Ball Possession": "possession", "Yellow Cards": "yellow", "Red Cards": "red", "Goalkeeper Saves": "saves",
             "Total passes": "passes", "Passes accurate": "passes_ok", "Passes %": "passes_pct", "expected_goals": "xg", "goals_prevented": "gp"}

def round_no(r):
    m = re.search(r"(\d+)\s*$", r or "")
    return int(m.group(1)) if m and (r or "").startswith("Regular Season") else None

def pull_matches():
    cache = load("matches.json", {"fixtures": {}})
    fx_all = cache.setdefault("fixtures", {})
    new = 0
    for lid, code in LEAGUES.items():
        for f in af_get("/fixtures", league=lid, season=SEASON):
            fid = str(f["fixture"]["id"]); st = f["fixture"]["status"]["short"]
            if st not in FINISHED or fid in fx_all:
                continue
            stats = {}
            for side in af_get("/fixtures/statistics", fixture=int(fid)):
                stats[str(side["team"]["id"])] = {STAT_KEYS[s["type"]]: num(s.get("value")) for s in side.get("statistics", []) if s.get("type") in STAT_KEYS}
            fx_all[fid] = {"league": lid, "round": round_no(f["league"]["round"]), "date": f["fixture"]["date"],
                           "home": f["teams"]["home"]["id"], "away": f["teams"]["away"]["id"],
                           "home_name": f["teams"]["home"]["name"], "away_name": f["teams"]["away"]["name"],
                           "goals": [f["goals"]["home"], f["goals"]["away"]], "stats": stats}
            new += 1
            time.sleep(PAUSE)
        print("  %s: partite in cache %d" % (code, sum(1 for x in fx_all.values() if x["league"] == lid)))
    cache["updated"] = now_iso(); cache["season"] = SEASON
    _save("matches.json", cache)
    print("  nuove partite scaricate:", new)
    return cache

# ---------- giocatori ----------
def trim_block(s):
    t = s.get("team") or {}; l = s.get("league") or {}
    out = {"team": {"id": t.get("id"), "name": t.get("name")},
           "league": {"id": l.get("id"), "name": l.get("name"), "country": l.get("country"), "season": l.get("season")}}
    for k in ("games", "substitutes", "shots", "goals", "passes", "tackles", "duels", "dribbles", "fouls", "cards", "penalty"):
        out[k] = s.get(k) or {}
    g = out["games"]
    if g.get("rating") is not None:
        g["rating"] = num(g["rating"])
    p = out["passes"]
    if p.get("accuracy") is not None:
        p["accuracy"] = num(p["accuracy"])
    return out

def profile_of(pl):
    b = pl.get("birth") or {}
    return {"id": pl["id"], "name": pl.get("name"), "first": pl.get("firstname"), "last": pl.get("lastname"),
            "birth": {"date": b.get("date"), "place": b.get("place"), "country": b.get("country")},
            "nationality": pl.get("nationality"), "height": num(pl.get("height")), "weight": num(pl.get("weight")),
            "injured": bool(pl.get("injured")), "photo": pl.get("photo")}

def trim_transfers(items):
    """[(data, tipo, da, a)] senza doppioni (il feed ripete lo stesso movimento con 'Milan' e 'AC Milan')."""
    out, seen = [], set()
    for tr in items or []:
        tm = tr.get("teams") or {}; i = tm.get("in") or {}; o = tm.get("out") or {}
        k = (tr.get("date"), i.get("id"), o.get("id"))
        if k in seen or not tr.get("date"):
            continue
        seen.add(k)
        out.append({"date": tr.get("date"), "type": tr.get("type"), "from": {"id": o.get("id"), "name": o.get("name")}, "to": {"id": i.get("id"), "name": i.get("name")}})
    out.sort(key=lambda x: x["date"])
    return out

def pull_players():
    P = load("players.json", {"players": {}})
    players = P.setdefault("players", {})
    prev_season = SEASON - 1
    # 1) rose attuali
    teams = af_get("/teams", league=PLAYER_LEAGUE, season=SEASON)
    roster = {}
    for t in teams:
        tid, tname = t["team"]["id"], t["team"]["name"]
        sq = af_get("/players/squads", team=tid)
        for pl in (sq[0]["players"] if sq else []):
            roster.setdefault(pl["id"], {"team": tid, "team_name": tname, "number": pl.get("number"), "position": pl.get("position"), "photo": pl.get("photo"), "sq_name": pl.get("name")})
        time.sleep(PAUSE)
    print("  rose: %d giocatori in %d squadre" % (len(roster), len(teams)))
    # 2) statistiche stagione corrente (Serie A) di chi ha giocato + profilo
    cur = {}
    for it in af_get("/players", league=PLAYER_LEAGUE, season=SEASON):
        pid = it["player"]["id"]
        p = players.setdefault(str(pid), {})
        p.update(profile_of(it["player"]))
        cur.setdefault(pid, []).extend(trim_block(s) for s in it.get("statistics", []))
    ids = set(roster) | set(cur)
    for pid in ids:
        p = players.setdefault(str(pid), {"id": pid})
        r = roster.get(pid)
        if r:
            p.update({"team": r["team"], "team_name": r["team_name"], "number": r["number"], "position": r["position"], "active": True})
            if not p.get("photo"):
                p["photo"] = r["photo"]
            if not p.get("name"):
                p["name"] = r["sq_name"]
        else:
            p["active"] = False           # ha giocato in Serie A quest'anno ma non e' piu' in una rosa
            if pid in cur and cur[pid]:
                b = cur[pid][-1]
                p.setdefault("team", b["team"]["id"]); p.setdefault("team_name", b["team"]["name"]); p.setdefault("position", b["games"].get("position"))
        p["cur"] = cur.get(pid, [])
        p["cur_season"] = SEASON
    print("  stagione corrente: %d giocatori con statistiche" % len(cur))
    _save("players.json", dict(P, updated=now_iso(), season=SEASON, league=PLAYER_LEAGUE))
    # 3) profili mancanti (in rosa ma senza presenze): 1 chiamata ciascuno, poi in cache
    miss = [pid for pid in ids if not players[str(pid)].get("birth")]
    for i, pid in enumerate(miss):
        res = af_one("/players", id=pid, season=SEASON) or af_one("/players/profiles", player=pid) or []
        if res:
            players[str(pid)].update(profile_of(res[0]["player"]))
            if res[0].get("statistics") and not players[str(pid)].get("cur"):
                players[str(pid)]["cur"] = [trim_block(s) for s in res[0]["statistics"] if (s.get("league") or {}).get("id") == PLAYER_LEAGUE]
        if (i + 1) % 50 == 0:
            _save("players.json", dict(P, updated=now_iso(), season=SEASON, league=PLAYER_LEAGUE))
    print("  profili scaricati:", len(miss))
    # 4) stagione precedente, tutte le competizioni: in cache per sempre (non cambia piu')
    todo = [pid for pid in ids if players[str(pid)].get("prev_season") != prev_season]
    for i, pid in enumerate(todo):
        res = af_one("/players", id=pid, season=prev_season) or []
        players[str(pid)]["prev"] = [trim_block(s) for s in (res[0].get("statistics", []) if res else [])]
        players[str(pid)]["prev_season"] = prev_season
        if (i + 1) % 50 == 0:
            _save("players.json", dict(P, updated=now_iso(), season=SEASON, league=PLAYER_LEAGUE))
            print("    stagione precedente: %d/%d" % (i + 1, len(todo)))
    print("  stagione precedente scaricata per %d giocatori" % len(todo))
    # 5) trasferimenti: per squadra (20 chiamate, coprono i movimenti che toccano la Serie A), poi per giocatore solo a chi manca
    seed = {}
    for t in teams:
        for it in af_get("/transfers", team=t["team"]["id"]):
            seed.setdefault(it["player"]["id"], []).extend(it.get("transfers") or [])
        time.sleep(PAUSE)
    solo = 0
    for pid in ids:
        p = players[str(pid)]
        if pid in seed:
            p["transfers"] = trim_transfers(seed[pid])
        elif "transfers" not in p:
            res = af_one("/transfers", player=pid) or []
            p["transfers"] = trim_transfers(res[0].get("transfers") if res else [])
            solo += 1
    print("  trasferimenti: da squadre %d giocatori, chiamate singole %d" % (len(seed), solo))
    # 6) chi non e' piu' ne' in rosa ne' nei tabellini resta in cache ma inattivo (serve alle pagine dei voti passati)
    for k, p in players.items():
        if int(k) not in ids:
            p["active"] = False
    P.update({"updated": now_iso(), "season": SEASON, "league": PLAYER_LEAGUE})
    _save("players.json", P)
    return P

# ---------- carriera per stagione (backfill ESPLICITO: mai dal cron, solo a mano) ----------
# Perche' un file separato e non un campo dentro players.json: players.json (3 MB) viene riscritto e
# committato a ogni giro del cron voti/titolarita'; qualche MB di carriera nel diff di ogni giornata
# gonfierebbe il repo per dati che non cambiano mai piu'.
# Perche' la cache e' definitiva: una stagione CHIUSA non cambia (stessa logica di prev_season qui sopra).
# Proprio perche' e' definitiva, ci finisce dentro SOLO cio' che abbiamo davvero letto e capito:
#  - una stagione entra in "done" se ha prodotto righe, oppure se l'API ha risposto con la scheda del
#    giocatore dichiarando che per quella stagione non ha statistiche: allora finisce anche in "vuote",
#    che e' la prova scritta del "so che non ha dati" (senza, non la richiederemmo mai piu' a vuoto);
#  - una risposta che non abbiamo capito, o che non conteneva niente da leggere, NON entra in "done":
#    resta da rifare e viene contata fra le "sospette", perche' "non ho capito" non e' "non c'e' nulla".
CAREER_FILE = "careers.json"
CAREER_MIN_SEASON = 2010      # sotto il 2010 la copertura API-Football e' rada: chiamate quasi sempre vuote
CAREER_MAX_CALLS = 400        # tetto prudente: il piano da' 7.500 richieste/giorno e voti+titolarita'+statistiche ne usano ~150
CAREER_SAVE_EVERY = 20        # salvataggio intermedio: un'interruzione non deve far ripetere le chiamate gia' pagate
CAREER_GUESS_SEASONS = 6      # stima per --dry quando non si conosce ne' l'elenco stagioni ne' la data di nascita
CAREER_MAX_FAIL = 3           # errori API consecutivi: quasi sempre quota finita o piano scaduto -> meglio fermarsi

def career_row(s, season=None):
    """Una riga di carriera (una stagione per competizione) da un blocco statistiche di API-Football.
    Legge SOLO chiavi che trim_block conserva intatte, quindi funziona anche sui blocchi gia' ridotti
    di players.json ('prev' e 'cur'): render_stats puo' chiamarla per completare la tabella senza chiamate."""
    t = s.get("team") or {}; l = s.get("league") or {}; g = s.get("games") or {}
    go = s.get("goals") or {}; c = s.get("cards") or {}
    return {"season": l.get("season") if l.get("season") is not None else season,
            "team": {"id": t.get("id"), "name": t.get("name")},
            "league": {"id": l.get("id"), "name": l.get("name"), "country": l.get("country")},
            "position": g.get("position"),
            "apps": g.get("appearences") or 0, "lineups": g.get("lineups") or 0, "minutes": g.get("minutes") or 0,
            "rating": num(g.get("rating")),
            "goals": go.get("total") or 0, "assists": go.get("assists") or 0,
            "conceded": go.get("conceded"), "saves": go.get("saves"),
            "yellow": c.get("yellow") or 0, "yellowred": c.get("yellowred") or 0, "red": c.get("red") or 0}

def _anno_valido(v):
    """Un anno plausibile e nient'altro: True/False non sono anni (bool e' un int), '2013' si', 20130 no."""
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        return None
    t = str(v).strip()
    if not t.isdigit():
        return None
    y = int(t)
    return y if 1900 <= y <= SEASON + 1 else None

def anni_stagioni(noti, pid):
    """L'elenco di /players/seasons DEVE essere una lista piatta di anni. Un oggetto, una lista di dizionari
    o una lista vuota NON sono 'questo giocatore non ha stagioni': sono risposte che non abbiamo capito.
    Prima qui usciva [] senza sollevare niente e il giocatore veniva marcato completo PER SEMPRE."""
    if not isinstance(noti, (list, tuple)):
        raise RispostaInattesa("/players/seasons player=%s: attesa una lista di anni, arrivato %s"
                               % (pid, type(noti).__name__))
    anni = []
    for s in noti:
        y = _anno_valido(s)
        if y is None:
            raise RispostaInattesa("/players/seasons player=%s: elemento che non e' un anno (%r)" % (pid, s))
        anni.append(y)
    if not anni:
        raise RispostaInattesa("/players/seasons player=%s: elenco stagioni vuoto (un giocatore in players.json "
                               "ne ha almeno una): risposta non attendibile, non marco nulla" % pid)
    return sorted(set(anni))

def blocchi_stagione(res, pid, s):
    """Blocchi statistiche di /players?id&season, con la distinzione che qui vale tutto:
       - lista con la scheda del giocatore e 'statistics' vuota -> ([], vuota=True): SO che non ha dati,
         la stagione e' chiusa e puo' entrare in cache come definitiva;
       - response assente/vuota o forma inattesa -> solleva: NON ho letto niente, non posso dichiarare
         chiusa la stagione. E' il caso del piano che non copre le stagioni storiche: un backfill da
         migliaia di chiamate 'riusciva' con zero righe e la cache restava avvelenata."""
    if not isinstance(res, list) or not res:
        raise RispostaInattesa("/players id=%s season=%s: nessuna scheda nella risposta (%s). Il piano copre "
                               "le stagioni storiche?" % (pid, s, type(res).__name__))
    it = res[0]
    if not isinstance(it, dict) or "statistics" not in it:
        raise RispostaInattesa("/players id=%s season=%s: scheda senza campo 'statistics' (%r)"
                               % (pid, s, sorted(it)[:6] if isinstance(it, dict) else type(it).__name__))
    st = it.get("statistics")
    if st is None:
        st = []
    if not isinstance(st, list) or any(not isinstance(b, dict) for b in st):
        raise RispostaInattesa("/players id=%s season=%s: 'statistics' non e' una lista di blocchi (%s)"
                               % (pid, s, type(st).__name__))
    # I blocchi devono essere DELLA STAGIONE CHIESTA. Un piano che non copre gli anni storici risponde 200
    # restituendo l'ultima stagione che possiede: chiedi il 2019 e ti arriva il 2024. Senza questo controllo
    # quelle righe entrano in una cache DEFINITIVA con l'anno sbagliato, si duplicano a ogni stagione chiesta,
    # e il backfill riporta successo mentre paga chiamate all'infinito per lo stesso dato.
    anni = {b.get("league", {}).get("season") for b in st if isinstance(b.get("league"), dict)}
    anni = {a for a in anni if a is not None}
    if anni and int(s) not in {int(a) for a in anni if str(a).isdigit()}:
        raise RispostaInattesa("/players id=%s season=%s: la risposta contiene le stagioni %s, non quella chiesta. "
                               "Il piano non copre gli anni storici: le righe NON entrano in cache."
                               % (pid, s, sorted(anni)))
    # tengo solo i blocchi dell'anno chiesto: se ne arrivano di misti, gli altri non sono cio' che ho domandato
    st = [b for b in st if not isinstance(b.get("league"), dict)
          or b["league"].get("season") is None or str(b["league"].get("season")) == str(s)]
    return st, not st

def seasons_note(rec):
    """Elenco stagioni di cui ci FIDIAMO in cache: una lista non vuota di anni plausibili. Un 'seasons'
    vuoto o storto vale come 'non lo sappiamo ancora' e va riletto, anche se c'e' 'seasons_at': cosi' una
    cache gia' avvelenata da un lancio precedente si ripara da sola invece di restare sbagliata per sempre."""
    anni = rec.get("seasons")
    if not isinstance(anni, list) or not anni:
        return None
    out = []
    for s in anni:
        y = _anno_valido(s)
        if y is None:
            return None
        out.append(y)
    return sorted(set(out))

def done_fidati(rec):
    """Stagioni davvero acquisite: quelle che hanno prodotto righe piu' quelle dichiarate senza dati
    ('vuote'). Una stagione in 'done' senza righe e senza prova di essere vuota non e' mai stata letta
    davvero: si rifa'. Vale anche per i record scritti dalla versione precedente di questo script."""
    con_righe = {r.get("season") for r in (rec.get("rows") or []) if isinstance(r, dict)}
    vuote = {_anno_valido(s) for s in (rec.get("vuote") or [])}
    buone = con_righe | vuote
    return {y for y in (_anno_valido(s) for s in (rec.get("done") or [])) if y is not None and y in buone}

def _prezzi():
    """Quotazioni del listone: servono SOLO a ordinare i giocatori per rilevanza, non finiscono nei dati."""
    lst = load_json(os.path.join(DATA, "fanta", "listone.json"), {}) or {}
    return {int(r["id"]): (r.get("price") or 0) for r in (lst.get("players") or []) if r.get("id")}

def _minuti(p):
    return sum(((b.get("games") or {}).get("minutes") or 0) for b in ((p.get("cur") or []) + (p.get("prev") or [])))

def _match_squadra(p, q):
    if not q:
        return True
    q = q.strip().lower()
    return q == str(p.get("team") or "") or q in str(p.get("team_name") or "").lower()

def career_order(players, prezzi, squadra=None, solo=None):
    """ORDINE DI RILEVANZA dichiarato (i piu' utili prima, cosi' un lancio corto serve gia' a qualcosa):
    1) chi e' oggi in una rosa di Serie A (la sua scheda e' quella che viene visitata),
    2) quotazione del listone decrescente (chi va all'asta e' chi viene cercato),
    3) minuti giocati fra stagione corrente e precedente (chi gioca davvero),
    4) id crescente, per un ordine stabile e ripetibile fra un lancio e l'altro."""
    ids = [int(k) for k, p in players.items()
           if (not solo or int(k) in solo) and _match_squadra(p, squadra)]
    ids.sort(key=lambda pid: (0 if players[str(pid)].get("active") else 1,
                              -prezzi.get(pid, 0), -_minuti(players[str(pid)]), pid))
    return ids

def _stima_stagioni(p, da, fino):
    """Quante stagioni potrebbe avere un giocatore di cui non conosciamo ancora l'elenco: dall'eta'."""
    anno = ((p.get("birth") or {}).get("date") or "")[:4]
    if anno.isdigit():
        return max(0, fino - max(da, int(anno) + 17) + 1)   # esordio realistico intorno ai 17-18 anni
    return CAREER_GUESS_SEASONS

def _salva_carriere(C, da, fino):
    C.update({"updated": now_iso(), "source": "API-Football /players?id&season (elenco stagioni da /players/seasons)",
              "range": {"da": da, "fino": fino},
              "nota": "stagioni chiuse fino al %d; %d e %d stanno in data/stats/players.json (campi prev e cur)" % (fino, SEASON - 1, SEASON)})
    _save(CAREER_FILE, C)

def career_todo(players, recs, ordine, da, fino):
    """Chi ha ancora qualcosa da scaricare, con COSA manca. E' anche la logica di RIPRESA: quello che e'
    gia' in 'done' non viene mai richiesto due volte. miss None = non conosciamo ancora l'elenco stagioni."""
    todo = []
    for pid in ordine:
        rec = recs.get(str(pid)) or {}
        # l'elenco stagioni si allunga di una all'anno: se e' stato letto in una stagione precedente a
        # quella che ci serve come tetto, va riletto (con lanci annuali non succede mai)
        noti = seasons_note(rec) if (rec.get("seasons_at") or 0) >= fino + 1 else None
        if noti is None:
            todo.append((pid, None))
        else:
            done = done_fidati(rec)
            miss = [s for s in noti if da <= s <= fino and s not in done]
            if miss:
                todo.append((pid, miss))
    return todo

def pull_careers(cap=CAREER_MAX_CALLS, dry=False, quanti=None, da=CAREER_MIN_SEASON, fino=None, squadra=None, solo=None):
    global _DRY
    _DRY = bool(dry)          # --dry non e' una promessa del codice a valle: af_one si rifiuta di partire
    esito = {"dry": bool(dry), "righe": 0, "stagioni": 0, "chiamate": 0, "sospette": 0, "fermato": None}
    P = load("players.json", {"players": {}})
    players = P.get("players") or {}
    if not players:
        print("  data/stats/players.json e' vuoto: lancia prima 'py -X utf8 scripts/stats_pull.py --giocatori'")
        esito["fermato"] = "senza-players"
        return esito
    fino = (SEASON - 2) if fino is None else fino     # SEASON-1 e' gia' in players.json ('prev'), non si ripaga
    C = load(CAREER_FILE, {"players": {}})
    recs = C.setdefault("players", {})
    ordine = career_order(players, _prezzi(), squadra, solo)
    if not ordine:
        # un filtro che non pesca nessuno non e' "lavoro gia' finito": e' un comando sbagliato, e va detto,
        # altrimenti "0 da lavorare" si legge come "tutto a posto"
        print("  FILTRO A VUOTO: nessun giocatore di players.json corrisponde (--squadra %r, --solo %s)"
              % (squadra, ",".join(str(x) for x in sorted(solo)) if solo else "-"))
        esito["fermato"] = "filtro-vuoto"
        return esito
    todo = career_todo(players, recs, ordine, da, fino)
    completi = len(ordine) - len(todo)
    if quanti:
        todo = todo[:quanti]
    certe = sum(1 if m is None else len(m) for _, m in todo)
    stimate = sum(_stima_stagioni(players[str(pid)], da, fino) for pid, m in todo if m is None)
    print("  stagioni %d-%d | giocatori: %d nell'ordine, %d gia' completi, %d da lavorare"
          % (da, fino, len(ordine), completi, len(todo)))
    print("  chiamate: %d certe (elenchi stagioni + stagioni gia' note mancanti) + ~%d stimate dall'eta' = ~%d"
          % (certe, stimate, certe + stimate))
    if dry:
        tot = certe + stimate
        print("  tetto attuale --max %d -> servirebbero ~%d lanci" % (cap, (tot + cap - 1) // cap if cap else 0))
        for pid, m in todo[:10]:
            p = players[str(pid)]
            print("    %-24s %-14s %s" % ((p.get("name") or "?")[:24], (p.get("team_name") or "-")[:14],
                                          "stagioni da scoprire" if m is None else "mancano %d stagioni" % len(m)))
        print("  --dry: nessuna chiamata fatta")
        esito["stimate"] = tot
        return esito
    start = n_calls()
    fermato = None; tocc = 0; nuove = 0; righe = 0; vuote = 0; sospette = 0; fail = 0
    try:
        for pid, miss in todo:
            p = players[str(pid)]
            # il record entra in cache SOLO se abbiamo davvero letto qualcosa: un record vuoto scritto
            # "per sbaglio" e' esattamente il seme dell'avvelenamento che stiamo togliendo
            rec = recs.get(str(pid)) or {"id": pid, "seasons": [], "done": [], "vuote": [], "rows": []}
            rec["name"] = p.get("name") or rec.get("name")
            scritto = False; in_corso = None
            try:
                if miss is None:
                    if n_calls() - start >= cap:
                        fermato = "tetto"; break
                    in_corso = "elenco stagioni"
                    # se la forma non e' quella attesa, anni_stagioni SOLLEVA: prima usciva [] in silenzio
                    # e la riga dopo marcava comunque il giocatore come completo per sempre
                    noti = anni_stagioni(af_one("/players/seasons", player=pid), pid)
                    rec["seasons"] = noti
                    rec["seasons_at"] = SEASON        # letto in questa stagione: copre tutto fino a SEASON-1
                    recs[str(pid)] = rec              # da qui il record vale: un Ctrl-C non butta la chiamata
                    scritto = True; in_corso = None
                    miss = [s for s in noti if da <= s <= fino and s not in done_fidati(rec)]
                for s in miss:
                    if n_calls() - start >= cap:
                        fermato = "tetto"; break
                    in_corso = s
                    blocchi, vuota = blocchi_stagione(af_one("/players", id=pid, season=s), pid, s)
                    nuove_righe = [career_row(b, s) for b in blocchi]
                    rec["rows"] = [r for r in (rec.get("rows") or []) if r.get("season") != s] + nuove_righe
                    # la stagione entra in 'done' solo ora che l'abbiamo letta davvero: se e' senza dati
                    # lo mettiamo per iscritto in 'vuote', che e' la prova del "so che non ha dati"
                    note = {y for y in (_anno_valido(x) for x in (rec.get("vuote") or [])) if y is not None}
                    if vuota:
                        note.add(s); vuote += 1
                    else:
                        note.discard(s); righe += len(nuove_righe)
                    rec["vuote"] = sorted(note)
                    rec["done"] = sorted(done_fidati(rec) | {s})
                    rec["sospette"] = [x for x in (rec.get("sospette") or []) if _anno_valido(x) != s]
                    recs[str(pid)] = rec
                    nuove += 1; scritto = True; in_corso = None
                fail = 0
            except (RuntimeError, requests.RequestException) as e:
                fail += 1; sospette += 1
                if isinstance(in_corso, int):
                    # traccia scritta della chiamata pagata e non capita: la stagione NON e' in 'done',
                    # resta da rifare, ma al prossimo lancio si sa che qui era gia' andata storta
                    rec["sospette"] = sorted(set(rec.get("sospette") or []) | {in_corso})
                    recs[str(pid)] = rec; scritto = True
                print("    %s su %s (%s) [%s]: %s"
                      % ("RISPOSTA INATTESA" if isinstance(e, RispostaInattesa) else "errore",
                         pid, p.get("name"), in_corso if in_corso is not None else "-", str(e)[:160]))
                if fail >= CAREER_MAX_FAIL:
                    fermato = "errori"     # niente break qui: sotto c'e' il salvataggio di cio' che era gia' letto
            if scritto:
                rec["rows"] = sorted((rec.get("rows") or []), key=lambda r: (r.get("season") or 0, -(r.get("minutes") or 0)))
                rec["updated"] = now_iso()
                tocc += 1
            if fermato:
                break
            if scritto and tocc % CAREER_SAVE_EVERY == 0:
                _salva_carriere(C, da, fino)
                print("    %d/%d giocatori, %d chiamate usate, %d righe salvate" % (tocc, len(todo), n_calls() - start, righe))
    except KeyboardInterrupt:
        fermato = "interrotto"
    finally:
        _salva_carriere(C, da, fino)     # anche su errore o Ctrl-C: le chiamate pagate non si buttano
    chiamate = n_calls() - start
    esito.update({"righe": righe, "stagioni": nuove, "chiamate": chiamate, "sospette": sospette,
                  "vuote": vuote, "giocatori": tocc, "fermato": fermato})
    # il contatore dice le RIGHE, non solo le stagioni toccate: e' l'unico numero che distingue un
    # backfill riuscito da uno che ha speso migliaia di chiamate senza portare a casa niente
    print("  giocatori toccati %d/%d, stagioni nuove in cache %d, RIGHE di carriera salvate %d, chiamate usate %d (tetto %d)"
          % (tocc, len(todo), nuove, righe, chiamate, cap))
    if vuote:
        print("  di cui %d stagioni che l'API dichiara senza statistiche (lette e chiuse: non sono un errore)" % vuote)
    if sospette:
        print("  ATTENZIONE: %d risposte vuote o di forma inattesa NON messe in cache: quelle stagioni restano da rifare" % sospette)
    if chiamate and not righe:
        print("  ALLARME: %d chiamate spese e ZERO righe di carriera salvate: la cache NON si e' popolata." % chiamate)
        print("           %s NON rilanciare alla cieca: si spenderebbe altra quota per niente."
              % ("l'API dichiara SENZA STATISTICHE tutte le stagioni chieste: quasi sempre e' il piano che non "
                 "copre gli anni storici." if vuote and vuote == nuove else
                 "controlla quota, piano e risposte qui sopra."))
    if fermato == "tetto":
        print("  TETTO RAGGIUNTO: rilancia lo stesso comando quando vuoi, riparte esattamente da qui")
    elif fermato == "errori":
        print("  FERMATO dopo %d risposte consecutive sbagliate o non capite (quota finita, piano scaduto o "
              "endpoint cambiato): niente di dubbio e' finito in cache" % CAREER_MAX_FAIL)
    elif fermato == "interrotto":
        print("  interrotto a mano: il lavoro fatto e' salvato")
    return esito

# Argomenti: nessun argparse (come gli altri script del progetto), ma nessun argomento accettato in
# silenzio. Un refuso non deve MAI trasformarsi in "ho capito un'altra cosa": '--quant 5' ignorato
# significa lanciare il backfill su TUTTI i giocatori, cioe' migliaia di chiamate al posto di cinque.
CON_VALORE = ("--max", "--quanti", "--da", "--fino", "--squadra", "--solo")
FLAG_CARRIERA = ("--carriera", "--dry") + CON_VALORE
FLAG_NORMALI = ("--squadre", "--giocatori")

def _stop(msg):
    print("stats_pull: " + msg, file=sys.stderr)
    sys.exit(2)

def _controlla_args(args, ammessi):
    """Ogni argomento e' un flag noto o il valore di un flag noto. Tutto il resto ferma lo script."""
    i = 0
    while i < len(args):
        a = args[i]
        if a not in ammessi:
            _stop("argomento non riconosciuto: %r (ammessi: %s)" % (a, " ".join(sorted(ammessi))))
        if args.count(a) > 1:
            _stop("%s ripetuto: quale dei due valeva?" % a)
        i += 2 if a in CON_VALORE else 1

def _opt(args, name, default=None):
    """--nome valore. Un valore mancante ferma: prima '--max --dry' faceva finta di niente e usava il default."""
    if name not in args:
        return default
    i = args.index(name)
    if i + 1 >= len(args) or args[i + 1].startswith("--"):
        _stop("%s vuole un valore subito dopo" % name)
    return args[i + 1]

def _int_opt(args, name, default=None, minimo=1, massimo=None):
    """Intero con intervallo dichiarato. Prima un valore non numerico (o negativo, o zero) cadeva sul
    default senza dire niente: '--quanti 0' voleva dire 'nessun giocatore' e lanciava invece TUTTO."""
    v = _opt(args, name)
    if v is None:
        return default
    t = str(v).strip()
    if not (t.isdigit() or (t.startswith("-") and t[1:].isdigit())):
        _stop("%s: %r non e' un numero intero" % (name, v))
    n = int(t)
    if n < minimo or (massimo is not None and n > massimo):
        _stop("%s: %d fuori intervallo (%d..%s)" % (name, n, minimo, massimo if massimo is not None else "-"))
    return n

def _ids_opt(args, name):
    """--solo 123,456. Un id storto ferma: se lo scartassimo, 'solo' resterebbe vuoto e il backfill
    lavorerebbe sull'intero listone invece che sui due giocatori chiesti."""
    raw = _opt(args, name)
    if raw is None:
        return None
    ids = set()
    for x in raw.replace(";", ",").split(","):
        x = x.strip()
        if not x:
            continue
        if not x.isdigit():
            _stop("%s: %r non e' un id numerico" % (name, x))
        ids.add(int(x))
    if not ids:
        _stop("%s: nessun id" % name)
    return ids

def main():
    args = sys.argv[1:]
    t0 = time.time()
    if "--carriera" in args:
        # backfill ESPLICITO: nessun workflow lo lancia: costa quota e va deciso da chi guarda il contatore
        _controlla_args(args, FLAG_CARRIERA)
        da = _int_opt(args, "--da", CAREER_MIN_SEASON, minimo=1900, massimo=SEASON - 1)
        # mai oltre SEASON-1: la stagione in corso NON e' chiusa e finirebbe in una cache definitiva
        # (e SEASON-1 sta gia' in players.json come 'prev', non si ripaga richiederla)
        fino = _int_opt(args, "--fino", None, minimo=1900, massimo=SEASON - 1)
        if fino is not None and da > fino:
            _stop("--da %d e' dopo --fino %d: l'intervallo e' vuoto" % (da, fino))
        print("carriera per stagione (backfill)")
        esito = pull_careers(cap=_int_opt(args, "--max", CAREER_MAX_CALLS), dry="--dry" in args,
                             quanti=_int_opt(args, "--quanti"), da=da, fino=fino,
                             squadra=_opt(args, "--squadra"), solo=_ids_opt(args, "--solo"))
        print("stats_pull --carriera: %d chiamate API, %.0fs" % (n_calls(), time.time() - t0))
        # uscita non-zero quando il backfill non ha portato a casa niente o si e' fermato in allarme:
        # un lancio che spende quota e non popola la cache non deve poter passare per riuscito
        if esito.get("fermato") in ("errori", "senza-players", "filtro-vuoto") or \
           (esito.get("chiamate") and not esito.get("righe")):
            sys.exit(1)
        return
    _controlla_args(args, FLAG_NORMALI)
    do_teams = "--squadre" in args or not args
    do_players = "--giocatori" in args or not args
    if do_teams:
        print("squadre e classifiche"); pull_teams()
        print("partite"); pull_matches()
    if do_players:
        print("giocatori"); pull_players()
    print("stats_pull OK: %d chiamate API, %.0fs" % (n_calls(), time.time() - t0))

if __name__ == "__main__":
    main()
