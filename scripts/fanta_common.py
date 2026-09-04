#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - funzioni comuni: chiavi, API-Football, Supabase (REST con service key)."""
import json, os, sys, time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "fanta")
SEASON = int(os.environ.get("FANTA_SEASON", "2026"))   # stagione 2026-27
LEAGUE_ID = 135                                         # Serie A su API-Football
API = "https://v3.football.api-sports.io"

def _read(name):
    try:
        return open(os.path.join(ROOT, name), encoding="utf-8").read().strip()
    except Exception:
        return ""

def api_key():
    return os.environ.get("APIFOOTBALL_KEY", "").strip() or _read("apifootball_key.txt")

def supabase_conf():
    """supabase_keys.txt: tre righe -> URL, anon key, service key. Oppure env SUPABASE_URL / SUPABASE_SERVICE_KEY."""
    url = os.environ.get("SUPABASE_URL", "").strip(); key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (url and key):
        lines = [l.strip() for l in _read("supabase_keys.txt").splitlines() if l.strip() and not l.startswith("#")]
        if len(lines) >= 3:
            url, key = lines[0], lines[2]
    return url.rstrip("/"), key

_calls = 0
def af_get(path, **params):
    """GET API-Football con paginazione automatica (campo paging)."""
    global _calls
    key = api_key()
    if not key:
        print("manca la chiave API-Football (apifootball_key.txt o APIFOOTBALL_KEY)"); sys.exit(1)
    out, page = [], 1
    while True:
        p = dict(params)
        if page > 1:
            p["page"] = page
        for attempt in range(4):
            r = requests.get(API + path, headers={"x-apisports-key": key}, params=p, timeout=40)
            _calls += 1
            if r.status_code == 429:
                time.sleep(10 * (attempt + 1)); continue
            r.raise_for_status(); break
        j = r.json()
        if j.get("errors"):
            raise RuntimeError("API-Football: %s" % j["errors"])
        out.extend(j.get("response", []))
        pg = j.get("paging") or {}
        if pg.get("current", 1) >= pg.get("total", 1):
            break
        page += 1
        time.sleep(0.4)   # limite 300 req/min sui piani a pagamento
    return out

def sb_upsert(table, rows, on_conflict=None, chunk=500):
    """Upsert su Supabase via PostgREST con la service key (bypassa RLS)."""
    url, key = supabase_conf()
    if not (url and key):
        print("Supabase non configurato: salto l'upsert su", table); return False
    h = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
         "Prefer": "resolution=merge-duplicates,return=minimal"}
    q = url + "/rest/v1/" + table + (("?on_conflict=" + on_conflict) if on_conflict else "")
    for i in range(0, len(rows), chunk):
        r = requests.post(q, headers=h, data=json.dumps(rows[i:i+chunk], ensure_ascii=False).encode("utf-8"), timeout=60)
        if r.status_code >= 300:
            raise RuntimeError("Supabase %s: %s %s" % (table, r.status_code, r.text[:300]))
    return True

def sb_get(table, params):
    url, key = supabase_conf()
    if not (url and key):
        return []
    h = {"apikey": key, "Authorization": "Bearer " + key}
    r = requests.get(url + "/rest/v1/" + table, headers=h, params=params, timeout=60)
    r.raise_for_status()
    return r.json()

def save_json(name, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=0)

def role_of(position):
    return {"Goalkeeper": "P", "Defender": "D", "Midfielder": "C", "Attacker": "A"}.get(position or "", "C")

def calls():
    return _calls

def sb_rpc(fn, args):
    """Chiama una funzione RPC con la service key."""
    url, key = supabase_conf()
    if not (url and key):
        return None
    h = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}
    r = requests.post(url + "/rest/v1/rpc/" + fn, headers=h, data=json.dumps(args), timeout=120)
    if r.status_code >= 300:
        raise RuntimeError("RPC %s: %s %s" % (fn, r.status_code, r.text[:300]))
    return r.json() if r.text else None
