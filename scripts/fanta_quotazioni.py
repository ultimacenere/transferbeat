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
import csv, html, io, json, os, re, sys, unicodedata, zipfile
from datetime import date
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fanta_common import sb_get, sb_upsert, sb_patch, save_json, DATA, ROOT, SEASON

ALIAS_FILE = os.path.join(DATA, "alias_quotazioni.json")
STATS_PLAYERS = os.path.join(ROOT, "data", "stats", "players.json")
STATS_TEAMS = os.path.join(ROOT, "data", "stats", "teams.json")
TEAM_API = {"Milan": "AC Milan", "Roma": "AS Roma"}      # nome squadra nel listone ufficiale -> nome nella tabella players (API-Football)

SPECIAL = str.maketrans({"ð": "d", "Ð": "D", "đ": "d", "Đ": "D", "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ß": "ss", "æ": "ae", "Æ": "AE", "þ": "th", "Þ": "Th", "œ": "oe", "ı": "i", "İ": "I"})

def norm(s):
    """Minuscolo, senza accenti (NFKD) e con le lettere che NFKD non scompone: Guðmundsson -> gudmundsson, Yıldız -> yildiz, N&apos;Diaye -> n diaye."""
    s = unicodedata.normalize("NFKD", html.unescape(str(s or "")).translate(SPECIAL)).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def joined(s):
    return norm(s).replace(" ", "")

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
        name = html.unescape(p["name"] or "")
        m = re.match(r"^([A-Za-zÀ-ɏ])\.\s*(.+)$", name)
        initial, sur = (norm(m.group(1)), m.group(2)) if m else ("", name)
        first, last = extra.get(p["id"], ("", ""))
        if first and not initial:
            initial = norm(first)[:1]
        # token del COGNOME: dopo l'iniziale nel nome API ("F. Dimarco") o dal cognome delle schede ("Lautaro Martínez" -> Martínez);
        # senza né l'uno né l'altro restano tutti i token (Juan Jesus)
        prim = set(norm(sur).split()) - {""}                       # nome mostrato dall'API senza l'iniziale: "Dimarco", "Lautaro Martínez", "Wesley"
        toks = (prim | set(norm(last).split())) - {""}             # + cognome esteso delle schede ("Jiménez Sánchez")
        keys[p["id"]] = {"toks": toks, "prim": prim, "initial": initial, "first": set(norm(first).split()), "team": norm(p.get("team") or ""),
                         "joined": {joined(sur), joined(last), joined(first + " " + last)} - {""}}
    return keys

def score_rows(e, db, keys, alias):
    """Candidati ordinati per punteggio per una riga del file: [(punteggio, giocatore)]. Alias manuale = punteggio massimo."""
    ak = norm(e["nome"]) + "|" + norm(e["squadra"])
    if ak in alias:
        p = next((x for x in db if x["id"] == alias[ak]), None)
        return [(99, p)] if p else []
    toks = norm(e["nome"]).split()
    initial, abbr = "", ""
    if len(toks) > 1 and len(toks[-1]) <= 3 and (len(toks[-1]) == 1 or "." in e["nome"]):   # "Martinez L." / "Pessina Mas." -> cognome + iniziale o abbreviazione del nome
        abbr = toks[-1]; initial = abbr[:1]; toks = toks[:-1]
    core = [t for t in toks if len(t) >= 3] or toks     # "el", "de", "n" non contano da soli
    if not core:
        return []
    jn = "".join(toks)
    team = norm(TEAM_API.get(e["squadra"], e["squadra"]))
    scored = []
    for p in db:
        k = keys[p["id"]]
        hit = sum(1 for t in core if t in k["toks"])
        full = jn in k["joined"]                          # "Ndiaye" == "N'Diaye", "Norton-Cuffy" == "Norton Cuffy"
        if not full and hit < len(core):                  # tutti i pezzi del cognome del file devono esserci
            continue
        if not full and not any(t in k["prim"] for t in core):   # trovato solo nel cognome esteso (Sanchez Ro. contro "Álex Jiménez" Sánchez): non basta
            continue
        s = hit * 3 + (3 if full else 2)
        if initial and k["initial"]:
            s += 1 if initial == k["initial"] else -2
        if len(abbr) > 1 and k["first"]:
            s += 1 if any(f.startswith(abbr) for f in k["first"]) else -1
        if team and k["team"]:
            s += 3 if (team == k["team"] or team in k["team"] or k["team"] in team) else -2
        if (e["r"] == "P") != (p.get("role") == "P"):
            s -= 3
        elif e["r"] and e["r"] == p.get("role"):
            s += 1
        scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    return scored

def match_all(entries, db, keys, alias):
    """Due passate: ogni riga prende il miglior candidato; se due righe reclamano lo stesso giocatore vince il punteggio più alto.
    -> matched {id: riga}, ambiguous [(riga, candidati)], missing [riga]."""
    best = {}
    for i, e in enumerate(entries):
        sc = score_rows(e, db, keys, alias)
        if not sc or sc[0][0] < 3:            # cognome uguale ma squadra E iniziale diverse = non trovato, non ambiguo
            best[i] = (None, [], False); continue
        top = sc[0][0]
        cands = [p for s, p in sc if s >= top - 1][:5]
        sure = len(sc) == 1 or sc[0][0] - sc[1][0] >= 2
        best[i] = ((sc[0][1] if sure else None), cands, sure, top)
    claims = {}
    for i, b in best.items():
        if b[0]:
            claims.setdefault(b[0]["id"], []).append((b[3], i))
    matched, ambiguous, missing = {}, [], []
    for i, e in enumerate(entries):
        p, cands, sure = best[i][0], best[i][1], best[i][2]
        if p and max(claims[p["id"]])[1] == i:
            matched[p["id"]] = e
        elif cands:
            ambiguous.append((e, cands))
        else:
            missing.append(e)
    return matched, ambiguous, missing

# ---------- main ----------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    path = args[0]; check = "--check" in flags; prezzi = "--prezzi" in flags; disattiva = "--disattiva" in flags
    attuale = "--attuale" in flags; cerca = "--cerca" in flags
    qt_of = lambda e: (e["qta"] if attuale else (e["qti"] if e["qti"] is not None else e["qta"]))
    fanta_price = lambda pid, q: max(1, q + (1 if pid % 2 == 0 else -1))   # quotazione FantaTB = ufficiale ±1 (pari +1, dispari -1), mai sotto 1
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
    matched, ambiguous, missing = match_all(entries, db, keys, alias)
    updates, diff_role, diff_team = [], [], []
    for pid, e in matched.items():
        p = next(x for x in db if x["id"] == pid)
        team_api = TEAM_API.get(e["squadra"], e["squadra"])
        # PostgREST vuole le STESSE chiavi in tutte le righe dell'upsert: riga completa, con i valori attuali dove non cambia nulla
        row = {"id": pid, "season": SEASON, "name": html.unescape(p.get("name") or ""), "role": p.get("role"), "role_mantra": p.get("role_mantra") or [],
               "team": p.get("team"), "team_id": p.get("team_id"), "price": p.get("price"), "active": True, "stats": dict(p.get("stats") or {})}
        if e["r"] in ("P", "D", "C", "A") and e["r"] != p.get("role"):
            row["role"] = e["r"]; diff_role.append((p, e))
        if e["rm"]:
            row["role_mantra"] = e["rm"]
        if team_api and norm(team_api) != norm(p.get("team") or ""):
            row["team"] = team_api; diff_team.append((p, e))
            if team_api in team_ids:
                row["team_id"] = team_ids[team_api]
        q = qt_of(e)
        if prezzi and q is not None:
            row["price"] = fanta_price(pid, q)
        row["stats"]["qt"] = {"team": team_api, "qta": e["qta"], "qti": e["qti"], "fvm": e["fvm"], "rm": e["rm"], "date": today}
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
        ch = [(next(x for x in db if x["id"] == pid), e) for pid, e in matched.items() if qt_of(e) is not None and fanta_price(pid, qt_of(e)) != next(x for x in db if x["id"] == pid).get("price")]
        print("\n-- QUOTAZIONI che cambiano: %d (%s ufficiale ±1; le prime 40 per valore)" % (len(ch), "Qt.A" if attuale else "Qt.I"))
        for p, e in sorted(ch, key=lambda x: -(qt_of(x[1]) or 0))[:40]:
            print("   %-24s %-14s %3s -> %3s (uff. %s)" % (p["name"], e["squadra"], p.get("price"), fanta_price(p["id"], qt_of(e)), qt_of(e)))
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
        print("\nsolo verifica: nessuna scrittura" + (" (con --cerca, in scrittura, i non trovati vengono cercati su API-Football: 1 chiamata ciascuno)" if missing else "")); return
    # ---- scrittura ----
    to_search = missing + [e for e, _ in ambiguous]
    if cerca and to_search:   # nuovi arrivi non ancora nel feed rose: cerco l'id API-Football per cognome, filtrando per squadra
        from fanta_common import af_get, LEAGUE_ID
        known_ids = {p["id"] for p in db}
        found = 0
        for e in to_search:
            toks = norm(e["nome"]).split()
            abbr = toks[-1] if len(toks) > 1 and len(toks[-1]) <= 3 and (len(toks[-1]) == 1 or "." in e["nome"]) else ""
            surt = [t for t in (toks[:-1] if abbr else toks) if len(t) >= 3] or toks
            if not surt:
                continue
            team_api = TEAM_API.get(e["squadra"], e["squadra"])
            ak = norm(e["nome"]) + "|" + norm(e["squadra"])
            try:   # /players?search= trova solo chi ha già statistiche: i nuovi arrivi si trovano con /players/profiles
                res = af_get("/players/profiles", player=alias[ak]) if ak in alias and alias[ak] not in known_ids else af_get("/players/profiles", search=surt[0])
            except Exception as ex:
                print("   ricerca API fallita per %s: %s" % (e["nome"], ex)); continue
            if ak in alias and alias[ak] not in known_ids:
                res = [it for it in res if it["player"]["id"] == alias[ak]]      # alias verso un id nuovo: inserimento diretto
            def ok(it):
                pl = it["player"]; full = norm((pl.get("firstname") or "") + " " + (pl.get("lastname") or "") + " " + (pl.get("name") or ""))
                if not all(t in full.split() for t in surt):
                    return False
                if abbr:
                    fn = norm(pl.get("firstname") or "")
                    return fn.startswith(abbr) or (pl.get("name") or "").lower().startswith(abbr[:1] + ".")
                return True
            hits = res if (ak in alias and alias[ak] not in known_ids) else [it for it in res if ok(it)]   # con l'alias il nome puo' essere diverso (Toni = Antonio)
            if len(hits) != 1:
                print("   %-22s %-12s: %d candidati su API-Football%s" % (e["nome"], e["squadra"], len(hits),
                      (" -> " + " / ".join("%s %s (id %s, %s)" % (it["player"].get("firstname"), it["player"].get("lastname"), it["player"]["id"], it["player"].get("nationality")) for it in hits[:5]) + ": scegli e metti l'id in alias") if hits else "")); continue
            pl = hits[0]["player"]; q = qt_of(e)
            if pl["id"] in known_ids:
                print("   %-22s %-12s: su API-Football è id %s, già in tabella con altro nome: aggiungi l'alias" % (e["nome"], e["squadra"], pl["id"])); continue
            updates.append({"id": pl["id"], "season": SEASON, "name": html.unescape(pl.get("name") or e["nome"]), "team": team_api, "team_id": team_ids.get(team_api),
                            "role": e["r"] if e["r"] in ("P", "D", "C", "A") else "C", "role_mantra": e["rm"], "active": True,
                            "price": fanta_price(pl["id"], q) if q is not None else 1,
                            "stats": {"qt": {"team": team_api, "qta": e["qta"], "qti": e["qti"], "fvm": e["fvm"], "rm": e["rm"], "date": today}}})
            found += 1
            print("   + %-22s %-12s -> id %s (%s)" % (e["nome"], e["squadra"], pl["id"], pl.get("name")))
        print("nuovi giocatori trovati su API-Football e inseriti: %d su %d (chiamate: %d)" % (found, len(to_search), len(to_search)))
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
