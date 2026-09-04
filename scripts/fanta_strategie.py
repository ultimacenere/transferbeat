#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - fanta_strategie.py: crea (o rigenera) le liste obiettivi e le strategie d'asta CONSIGLIATE da TransferBeat
(featured = true, visibili a tutti nella vista Obiettivi e strategie), a partire da quotazioni ufficiali, media voto, fantamedia,
titolarità e età dei giocatori. kb/FANTATB.md §17.

  py scripts/fanta_strategie.py --owner <email>      crea/rigenera le 4 strategie con le loro liste, intestate a quell'account (staff)
  py scripts/fanta_strategie.py --owner <email> --check   solo anteprima: quanti giocatori per tier e ruolo, senza scrivere

Le 4 strategie (formato asta da 8 con 500 crediti, slot Classic 3/8/8/6):
  1. Equilibrata           budget P 8 / D 24 / C 26 / A 42 - tier per quotazione ufficiale
  2. Sbilanciata sui bonus budget P 5 / D 16 / C 24 / A 55 - due top in attacco, il resto a basso costo
  3. Modificatore difesa   budget P 14 / D 32 / C 22 / A 32 - portiere top e difensori scelti per media voto
  4. Low budget scommesse  budget P 6 / D 18 / C 26 / A 50 - pochi big, molti giovani e titolari sottoquotati
Idempotente: cancella e ricrea liste e strategie con lo stesso nome dello stesso proprietario. Scrive con la service key (la lancia l'utente)."""
import json, os, sys
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fanta_common import sb_get, sb_upsert, supabase_conf, ROOT

ROLES = ["P", "D", "C", "A"]
SLOTS = {"P": 3, "D": 8, "C": 8, "A": 6}
STRATS = [
    {"name": "Equilibrata (8 squadre, 500 crediti)", "budget": {"P": 8, "D": 24, "C": 26, "A": 42}, "mode": "quot",
     "targets": {"P": {"1": 1}, "D": {"1": 1, "2": 2, "3": 3}, "C": {"1": 1, "2": 2, "3": 3}, "A": {"1": 1, "2": 1, "3": 2}},
     "description": "Un top per reparto, poi seconde e terze scelte solide. La base sicura per chi non vuole scommettere."},
    {"name": "Sbilanciata sui bonus (8 squadre, 500 crediti)", "budget": {"P": 5, "D": 16, "C": 24, "A": 55}, "mode": "bonus",
     "targets": {"P": {"2": 1}, "D": {"2": 2, "3": 3}, "C": {"1": 1, "2": 1, "3": 3}, "A": {"1": 2, "2": 1, "3": 1}},
     "description": "Due attaccanti di primissima fascia e un centrocampista da gol: i bonus fanno la differenza, la difesa si riempie a poco."},
    {"name": "Modificatore difesa (8 squadre, 500 crediti)", "budget": {"P": 14, "D": 32, "C": 22, "A": 32}, "mode": "difesa",
     "targets": {"P": {"1": 1}, "D": {"1": 2, "2": 2, "3": 2}, "C": {"2": 2, "3": 3}, "A": {"1": 1, "2": 1, "3": 1}},
     "description": "Per le leghe con il modificatore difesa: portiere top e tre difensori da media voto alta, il resto equilibrato."},
    {"name": "Low budget e scommesse (8 squadre, 500 crediti)", "budget": {"P": 6, "D": 18, "C": 26, "A": 50}, "mode": "scommesse",
     "targets": {"P": {"3": 1}, "D": {"2": 1, "3": 3, "4": 3}, "C": {"2": 1, "3": 3, "4": 3}, "A": {"1": 1, "3": 2, "4": 3}},
     "description": "Un solo big, poi titolari sottoquotati e giovani in rampa di lancio: rischio alto, rendimento potenzialmente altissimo."},
]
TIER_SIZES = {"P": [3, 5, 6, 8], "D": [5, 10, 14, 16], "C": [5, 10, 14, 16], "A": [4, 8, 10, 12]}   # quanti giocatori per T1..T4 per ruolo

def owner_id(email):
    url, key = supabase_conf()
    r = requests.get(url + "/auth/v1/admin/users", headers={"apikey": key, "Authorization": "Bearer " + key}, params={"page": 1, "per_page": 500}, timeout=60)
    r.raise_for_status()
    for u in r.json().get("users", []):
        if (u.get("email") or "").lower() == email.lower():
            return u["id"], (u.get("user_metadata") or {}).get("username") or email.split("@")[0]
    raise SystemExit("account non trovato: " + email)

def load_players():
    db = [p for p in sb_get("players", {"select": "id,name,team,role,price,active,stats", "limit": "5000"}) if p["active"]]
    schede = {}
    try:
        schede = {int(k): v for k, v in json.load(open(os.path.join(ROOT, "data", "fanta", "schede.json"), encoding="utf-8"))["players"].items()}
    except Exception:
        pass
    ages = {}
    try:
        from datetime import date
        for k, v in json.load(open(os.path.join(ROOT, "data", "stats", "players.json"), encoding="utf-8"))["players"].items():
            b = (v.get("birth") or {}).get("date")
            if b:
                y, m, d = [int(x) for x in b.split("-")]; t = date.today(); ages[int(k)] = t.year - y - ((t.month, t.day) < (m, d))
    except Exception:
        pass
    for p in db:
        s = schede.get(p["id"], {})
        p["mv"] = s.get("mv"); p["fmv"] = s.get("fmv"); p["tit"] = s.get("tit"); p["age"] = ages.get(p["id"])
        qt = (p.get("stats") or {}).get("qt") or {}
        p["fvm"] = qt.get("fvm") or 0
    return db

def score(p, mode):
    """Punteggio per ordinare i giocatori dentro un ruolo, secondo la strategia."""
    q = p["price"]; mv = p.get("mv") or 0; fmv = p.get("fmv") or 0; tit = p.get("tit") or 0; age = p.get("age") or 27
    if mode == "quot":
        return q * 10 + fmv
    if mode == "bonus":
        return q * 10 + (fmv - mv) * 30 + (p["fvm"] or 0) / 20   # premia chi porta bonus (fantamedia sopra la media voto)
    if mode == "difesa":
        if p["role"] in ("P", "D"):
            return (mv or 5.8) * 40 + tit * 0.3 + q * 2
        return q * 10 + fmv
    if mode == "scommesse":
        young = 1.0 if age <= 23 else 0.0
        return (tit * 0.8) + (fmv * 15) + young * 40 - q * 2.5    # titolari sottoquotati e giovani
    return q

def build_list(db, mode):
    """{player_id: tier} per la strategia: T1..T4 per posizione nel ranking del ruolo; T5 = cari con media voto bassa."""
    items = {}
    for r in ROLES:
        rp = [p for p in db if p["role"] == r]
        cut = TIER_SIZES[r]
        if mode == "scommesse":   # i big (T1, T2) restano quelli veri per quotazione; T3 e T4 sono le scommesse (titolari sottoquotati, giovani)
            top = sorted(rp, key=lambda p: -score(p, "quot"))[:cut[0] + cut[1]]
            rest = sorted([p for p in rp if p not in top], key=lambda p: -score(p, "scommesse"))
            ps = top + rest
        else:
            ps = sorted(rp, key=lambda p: -score(p, mode))
        pos = 0
        for t, n in enumerate(cut, start=1):
            for p in ps[pos:pos + n]:
                items[p["id"]] = t
            pos += n
        for p in ps:
            if p["id"] not in items and p["price"] >= 15 and p.get("mv") is not None and p["mv"] < 5.8:
                items[p["id"]] = 5
    return items

def main():
    args = sys.argv[1:]
    if "--owner" not in args:
        raise SystemExit(__doc__)
    email = args[args.index("--owner") + 1]; check = "--check" in args
    db = load_players()
    print("giocatori attivi:", len(db))
    uid, uname = (None, "TransferBeat") if check else owner_id(email)
    url, key = supabase_conf()
    H = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json", "Prefer": "return=representation"}
    byid = {p["id"]: p for p in db}
    for st in STRATS:
        items = build_list(db, st["mode"])
        cnt = {}
        for pid, t in items.items():
            k = byid[pid]["role"] + str(t); cnt[k] = cnt.get(k, 0) + 1
        print("\n== %s" % st["name"])
        print("   tier per ruolo:", {r: [cnt.get(r + str(t), 0) for t in range(1, 6)] for r in ROLES})
        top = sorted([pid for pid, t in items.items() if t == 1], key=lambda pid: -byid[pid]["price"])[:8]
        print("   T1:", ", ".join(byid[pid]["name"] + " (" + byid[pid]["role"] + " " + str(byid[pid]["price"]) + ")" for pid in top))
        if check:
            continue
        lname = "Lista " + st["name"]
        # lista: cancello la precedente con lo stesso nome e la ricreo
        old = requests.get(url + "/rest/v1/lists", headers=H, params={"select": "id", "owner_id": "eq." + uid, "name": "eq." + lname}, timeout=30).json()
        for o in old:
            requests.delete(url + "/rest/v1/lists", headers=H, params={"id": "eq." + o["id"]}, timeout=30)
        r = requests.post(url + "/rest/v1/lists", headers=H, json={"owner_id": uid, "name": lname, "description": st["description"], "author": "TransferBeat", "is_public": True, "featured": True}, timeout=30)
        r.raise_for_status(); lid = r.json()[0]["id"]
        rows = [{"list_id": lid, "player_id": pid, "tier": t} for pid, t in items.items()]
        sb_upsert("list_items", rows, on_conflict="list_id,player_id")
        olds = requests.get(url + "/rest/v1/strategies", headers=H, params={"select": "id", "owner_id": "eq." + uid, "name": "eq." + st["name"]}, timeout=30).json()
        for o in olds:
            requests.delete(url + "/rest/v1/strategies", headers=H, params={"id": "eq." + o["id"]}, timeout=30)
        r = requests.post(url + "/rest/v1/strategies", headers=H, json={"owner_id": uid, "name": st["name"], "description": st["description"], "author": "TransferBeat", "teams": 8, "credits": 500,
                                                                          "slots": SLOTS, "budget": st["budget"], "targets": st["targets"], "list_id": lid, "is_public": True, "featured": True}, timeout=30)
        r.raise_for_status()
        print("   lista %s (%d giocatori) e strategia create, condivise e consigliate" % (lid[:8], len(rows)))
    print("\nfatto" if not check else "\nsolo anteprima: nessuna scrittura")

if __name__ == "__main__":
    main()
