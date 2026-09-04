#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - fanta_quotazioni.py: allinea la tabella `players` al listone ufficiale del fantacalcio (kb/FANTATB.md §16).

Fonte: il file Excel "Quotazioni Fantacalcio" scaricato dal proprio account su Fantacalcio.it (foglio con colonne
Id, R, RM, Nome, Squadra, Qt.A, Qt.I, Diff., ..., FVM) oppure un CSV con almeno le colonne R, Nome, Squadra e, se ci sono,
RM (ruoli Mantra separati da ;) e Qt.A / Quotazione. Il file non e' nel repo: si passa come argomento.

  py scripts/fanta_quotazioni.py <file> --check              solo rapporto: abbinati, ambigui, non trovati, differenze di ruolo/squadra
  py scripts/fanta_quotazioni.py <file>                      aggiorna ruolo Classic, ruoli Mantra e squadra; prezzi invariati
  py scripts/fanta_quotazioni.py <file> --prezzi             anche price = Qt.A (quotazione attuale del file)
  py scripts/fanta_quotazioni.py <file> --disattiva          i giocatori attivi assenti dal file diventano active=false (usciti dalla Serie A)
  py scripts/fanta_quotazioni.py <file> --check --locale data/fanta/listone.json     prova l'abbinamento senza Supabase

Abbinamento nomi: cognome (e iniziale) del file contro nome API-Football, nome e cognome delle schede (data/stats/players.json),
con bonus per squadra e per portiere/non portiere. Le righe ambigue o non trovate finiscono nel rapporto: per risolverle a mano
si scrive data/fanta/alias_quotazioni.json come {"nome nel file|squadra": id_giocatore}.
Salva in players.stats.qt {team, qta, qti, fvm, rm, date}: fanta_players.py rispetta la squadra del listone ufficiale per 45 giorni
(il feed rose API-Football resta indietro a fine mercato). Dopo l'aggiornamento riscrive data/fanta/listone.json dalla tabella:
poi `py scripts/render_site.py` e `bash scripts/pubblica.sh`."""
import csv, io, json, os, re, sys, unicodedata, zipfile
from datetime import date
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fanta_common import sb_get, sb_upsert, sb_patch, save_json, DATA, ROOT, SEASON

ALIAS_FILE = os.path.join(DATA, "alias_quotazioni.json")
STATS_PLAYERS = os.path.join(ROOT, "data", "stats", "players.json")
STATS_TEAMS = os.path.join(ROOT, "data", "stats", "teams.json")
TEAM_API = {"Milan": "AC Milan", "Roma": "AS Roma"}      # nome squadra nel listone ufficiale -> nome nella tabella players (API-Football)

SPECIAL = str.maketrans({"ð": "d", "Ð": "D", "đ": "d", "Đ": "D", "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ß": "ss", "æ": "ae", "Æ": "AE", "þ": "th", "Þ": "Th", "œ": "oe"})

def norm(s):
    """Minuscolo, senza accenti (NFKD) e con le lettere che NFKD non scompone: Guðmundsson -> gudmundsson, Łukasz -> lukasz."""
    s = unicodedata.normalize("NFKD", str(s or "").translate(SPECIAL)).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

# ---------- lettura file ----------
def read_xlsx(path):
    """Lettore minimo di .xlsx (primo foglio) senza dipendenze: restituisce le righe come liste di stringhe."""
    z = zipfile.ZipFile(path)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
    sheet = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))[0]
    rows = []
    for row in ET.fromstring(z.read(sheet)).iter("{%s}row" % ns["m"]):
        cells = {}
        for c in row.findall("m:c", ns):
            ref = c.get("r") or ""; col = 0
            for ch in re.match(r"[A-Z]+", ref).group(0):
                col = col * 26 + (ord(ch) - 64)
            v = c.find("m:v", ns); t = c.get("t")
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % ns["m"]))
            else:
                val = v.text if v is not None else ""
            cells[col - 1] = val
        n = max(cells) + 1 if cells else 0
        rows.append([cells.get(i, "") for i in range(n)])
    return rows

def read_csv(path):
    raw = open(path, encoding="utf-8-sig", errors="replace").read()
    try:
        dialect = csv.Sniffer().sniff(raw[:4000], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel; dialect.delimiter = ";"
    return [row for row in csv.reader(io.StringIO(raw), dialect)]

HEAD = {"r": ["r", "ruolo", "ruolo classic", "rc"], "rm": ["rm", "ruolo mantra", "ruoli mantra"], "nome": ["nome", "giocatore", "calciatore"],
        "squadra": ["squadra", "sq", "club"], "qta": ["qt a", "qt.a", "quotazione", "quotazione attuale", "qa", "prezzo"], "qti": ["qt i", "qt.i", "quotazione iniziale", "qi"],
        "fvm": ["fvm", "fantavalore"]}

def parse(rows):
    """Trova l'intestazione (una riga con 'Nome' e 'R'/'Ruolo') e restituisce le voci {r, rm, nome, squadra, qta, qti, fvm}."""
    for i, row in enumerate(rows[:30]):
        cols = {}
        for j, c in enumerate(row):
            n = norm(c).replace(".", " ").strip()
            for k, names in HEAD.items():
                if k not in cols and any(n == norm(x).replace(".", " ").strip() for x in names):
                    cols[k] = j; break
        if "nome" in cols and "r" in cols:
            out = []
            for row in rows[i + 1:]:
                get = lambda k: (str(row[cols[k]]).strip() if k in cols and cols[k] < len(row) else "")
                if not get("nome"):
                    continue
                def num(v):
                    try: return int(round(float(str(v).replace(",", "."))))
                    except ValueError: return None
                out.append({"r": get("r").upper()[:1], "rm": [x.strip() for x in get("rm").split(";") if x.strip()], "nome": get("nome"), "squadra": get("squadra"),
                            "qta": num(get("qta")), "qti": num(get("qti")), "fvm": num(get("fvm"))})
            return out
    raise SystemExit("intestazione non trovata: servono almeno le colonne Nome e R (ruolo)")

# ---------- abbinamento ----------
def player_keys(db):
    """Per ogni giocatore in tabella: token del cognome, iniziale, squadra normalizzata."""
    extra = {}
    try:
        for pid, p in json.load(open(STATS_PLAYERS, encoding="utf-8")).get("players", {}).items():
            extra[int(pid)] = (p.get("first") or "", p.get("last") or "")
    except Exception:
        pass
    keys = {}
    for p in db:
        name = p["name"] or ""
        m = re.match(r"^([A-Za-zÀ-ɏ])\.\s*(.+)$", name)
        initial, sur = (norm(m.group(1)), m.group(2)) if m else ("", name)
        first, last = extra.get(p["id"], ("", ""))
        if first and not initial:
            initial = norm(first)[:1]
        toks = set(norm(sur).split()) | set(norm(last).split())
        toks.discard("")
        keys[p["id"]] = {"toks": toks, "initial": initial, "first": set(norm(first).split()), "team": norm(p.get("team") or "")}
    return keys

def match(e, db, keys, alias):
    """-> (giocatore, candidati, sicuro)."""
    ak = norm(e["nome"]) + "|" + norm(e["squadra"])
    if ak in alias:
        p = next((x for x in db if x["id"] == alias[ak]), None)
        return p, [p] if p else [], bool(p)
    toks = norm(e["nome"]).split()
    initial = ""
    if toks and len(toks[-1]) == 1:          # "Martinez L." -> cognome + iniziale
        initial = toks[-1]; toks = toks[:-1]
    if not toks:
        return None, [], False
    team = norm(TEAM_API.get(e["squadra"], e["squadra"]))
    scored = []
    for p in db:
        k = keys[p["id"]]
        hit = sum(1 for t in toks if t in k["toks"])
        if not hit:
            continue
        s = hit * 3 + (2 if hit == len(toks) and hit == len(k["toks"]) else 0)
        if initial and k["initial"]:
            s += 1 if initial == k["initial"] else -2
        if team and k["team"]:
            s += 2 if (team == k["team"] or team in k["team"] or k["team"] in team) else -1
        if e["r"] == "P" and p.get("role") != "P" or e["r"] != "P" and p.get("role") == "P":
            s -= 2
        scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return None, [], False
    best = scored[0][0]
    cands = [p for s, p in scored if s >= best - 1][:5]
    sure = len(scored) == 1 or scored[0][0] - scored[1][0] >= 2
    return (scored[0][1] if sure else None), cands, sure

# ---------- main ----------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    path = args[0]; check = "--check" in flags; prezzi = "--prezzi" in flags; disattiva = "--disattiva" in flags
    locale = args[1] if "--locale" in flags and len(args) > 1 else None
    rows = read_xlsx(path) if path.lower().endswith((".xlsx", ".xlsm")) else read_csv(path)
    entries = parse(rows)
    cnt = {}
    for e in entries:
        cnt[e["r"] or "?"] = cnt.get(e["r"] or "?", 0) + 1
    print("file: %d giocatori, per ruolo %s" % (len(entries), dict(sorted(cnt.items()))))
    if locale:
        db = [dict(p, team_id=None, role_mantra=[], active=True, stats={}) for p in json.load(open(locale, encoding="utf-8"))["players"]]
    else:
        db = sb_get("players", {"select": "id,name,team,team_id,role,role_mantra,price,active,stats", "limit": "5000"})
        if not db:
            raise SystemExit("tabella players vuota o Supabase non configurato (supabase_keys.txt / SUPABASE_URL + SUPABASE_SERVICE_KEY)")
    alias = {}
    try:
        alias = {k: int(v) for k, v in json.load(open(ALIAS_FILE, encoding="utf-8")).items()}
    except Exception:
        pass
    team_ids = {}
    try:
        for t in json.load(open(STATS_TEAMS, encoding="utf-8")).get("teams", {}).values():
            team_ids[t["name"]] = t["id"]
    except Exception:
        pass
    keys = player_keys(db)
    today = date.today().isoformat()
    matched, ambiguous, missing, updates = {}, [], [], []
    for e in entries:
        p, cands, sure = match(e, db, keys, alias)
        if p:
            if p["id"] in matched:
                ambiguous.append((e, cands)); continue
            matched[p["id"]] = e
        elif cands:
            ambiguous.append((e, cands))
        else:
            missing.append(e)
    diff_role, diff_team = [], []
    for pid, e in matched.items():
        p = next(x for x in db if x["id"] == pid)
        team_api = TEAM_API.get(e["squadra"], e["squadra"])
        row = {"id": pid}
        if e["r"] in ("P", "D", "C", "A") and e["r"] != p.get("role"):
            row["role"] = e["r"]; diff_role.append((p, e))
        if e["rm"] and e["rm"] != (p.get("role_mantra") or []):
            row["role_mantra"] = e["rm"]
        if team_api and norm(team_api) != norm(p.get("team") or ""):
            row["team"] = team_api; diff_team.append((p, e))
            if team_api in team_ids:
                row["team_id"] = team_ids[team_api]
        if prezzi and e["qta"] is not None and e["qta"] != p.get("price"):
            row["price"] = e["qta"]
        st = dict(p.get("stats") or {}); st["qt"] = {"team": team_api, "qta": e["qta"], "qti": e["qti"], "fvm": e["fvm"], "rm": e["rm"], "date": today}
        row["stats"] = st
        if not p.get("active"):
            row["active"] = True
        updates.append(row)
    absent = [p for p in db if p.get("active") and p["id"] not in matched]
    # ---- rapporto ----
    print("\n== abbinati %d su %d · ambigui %d · non trovati %d · in tabella ma assenti dal file %d" % (len(matched), len(entries), len(ambiguous), len(missing), len(absent)))
    print("\n-- RUOLO CLASSIC che cambia: %d" % len(diff_role))
    for p, e in sorted(diff_role, key=lambda x: -(x[0].get("price") or 0))[:80]:
        print("   %s -> %s  %-24s %-14s q.%s" % (p["role"], e["r"], p["name"], p.get("team") or "", p.get("price")))
    print("\n-- SQUADRA che cambia: %d" % len(diff_team))
    for p, e in diff_team:
        print("   %-24s %-16s -> %s" % (p["name"], p.get("team") or "", e["squadra"]))
    if prezzi:
        ch = [(next(x for x in db if x["id"] == pid), e) for pid, e in matched.items() if e["qta"] is not None and e["qta"] != next(x for x in db if x["id"] == pid).get("price")]
        print("\n-- QUOTAZIONI che cambiano: %d (le prime 40 per valore)" % len(ch))
        for p, e in sorted(ch, key=lambda x: -(x[1]["qta"] or 0))[:40]:
            print("   %-24s %-14s %3s -> %3s" % (p["name"], e["squadra"], p.get("price"), e["qta"]))
    print("\n-- AMBIGUI (scegli e scrivi l'id in %s come {\"%s\": id}): %d" % (os.path.relpath(ALIAS_FILE, ROOT), "nome|squadra", len(ambiguous)))
    for e, cands in ambiguous:
        print("   %s|%s -> " % (norm(e["nome"]), norm(e["squadra"])) + " / ".join("%s %s (%s, id %s)" % (c["role"], c["name"], c.get("team"), c["id"]) for c in cands))
    print("\n-- NON TROVATI nel listone FantaTB (nuovi arrivi non ancora nel feed rose, o nomi diversi): %d" % len(missing))
    for e in missing:
        print("   %s %-22s %s" % (e["r"], e["nome"], e["squadra"]))
    print("\n-- ATTIVI in tabella ma ASSENTI dal file (usciti dalla Serie A? con --disattiva diventano inattivi): %d" % len(absent))
    for p in absent:
        print("   %s %-24s %s" % (p["role"], p["name"], p.get("team") or ""))
    if check or locale:
        print("\nsolo verifica: nessuna scrittura"); return
    # ---- scrittura ----
    if updates and sb_upsert("players", updates, on_conflict="id"):
        print("\nupsert players: %d righe (ruolo/mantra/squadra%s)" % (len(updates), "/prezzo" if prezzi else ""))
    if disattiva and absent:
        sb_patch("players", {"id": "in.(%s)" % ",".join(str(p["id"]) for p in absent)}, {"active": False})
        print("disattivati:", len(absent))
    db = sb_get("players", {"select": "id,name,team,role,price,active", "limit": "5000"})
    act = sorted([p for p in db if p["active"]], key=lambda r: ("PDCA".index(r["role"]), -r["price"], r["name"]))
    save_json("listone.json", {"updated": date.today().isoformat() + "T00:00:00Z", "season": SEASON, "source": "quotazioni ufficiali " + today,
                               "players": [{k: r[k] for k in ("id", "name", "team", "role", "price")} for r in act]})
    print("listone.json riscritto: %d attivi. Ora: py scripts/render_site.py e bash scripts/pubblica.sh" % len(act))

if __name__ == "__main__":
    main()
