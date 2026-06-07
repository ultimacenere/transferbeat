#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TransferBeat - mondiali.py
Sezione Mondiali (FIFA World Cup 2026). Fonte: openfootball/worldcup.json (pubblico dominio,
nessuna chiave). Produce data/mondiali.json: gironi + classifiche calcolate, calendario/risultati,
marcatori, bracket knockout, e una barra news dedicata (Google News RSS solo-Mondiale, 3 lingue).
Struttura pronta per agganciare cartellini/rose/live (GOAT) in futuro.
"""
import json, os, sys, re
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import requests
    import build  # riuso fetch/enrich/clean_title per le news
except Exception as e:
    print("Dipendenze mancanti:", e); sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SRC = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"

# nazionale: nome_en -> (iso2, nome_it, nome_es). ENG/SCT trattate a parte per la bandiera.
NAZ = {
 "Algeria":("DZ","Algeria","Argelia"), "Argentina":("AR","Argentina","Argentina"),
 "Australia":("AU","Australia","Australia"), "Austria":("AT","Austria","Austria"),
 "Belgium":("BE","Belgio","Bélgica"), "Bosnia & Herzegovina":("BA","Bosnia ed Erzegovina","Bosnia y Herzegovina"),
 "Brazil":("BR","Brasile","Brasil"), "Canada":("CA","Canada","Canadá"),
 "Cape Verde":("CV","Capo Verde","Cabo Verde"), "Colombia":("CO","Colombia","Colombia"),
 "Croatia":("HR","Croazia","Croacia"), "Curaçao":("CW","Curaçao","Curazao"),
 "Czech Republic":("CZ","Rep. Ceca","Rep. Checa"), "DR Congo":("CD","RD Congo","RD Congo"),
 "Ecuador":("EC","Ecuador","Ecuador"), "Egypt":("EG","Egitto","Egipto"),
 "England":("_ENG","Inghilterra","Inglaterra"), "France":("FR","Francia","Francia"),
 "Germany":("DE","Germania","Alemania"), "Ghana":("GH","Ghana","Ghana"),
 "Haiti":("HT","Haiti","Haití"), "Iran":("IR","Iran","Irán"), "Iraq":("IQ","Iraq","Irak"),
 "Ivory Coast":("CI","Costa d'Avorio","Costa de Marfil"), "Japan":("JP","Giappone","Japón"),
 "Jordan":("JO","Giordania","Jordania"), "Mexico":("MX","Messico","México"),
 "Morocco":("MA","Marocco","Marruecos"), "Netherlands":("NL","Paesi Bassi","Países Bajos"),
 "New Zealand":("NZ","Nuova Zelanda","Nueva Zelanda"), "Norway":("NO","Norvegia","Noruega"),
 "Panama":("PA","Panama","Panamá"), "Paraguay":("PY","Paraguay","Paraguay"),
 "Portugal":("PT","Portogallo","Portugal"), "Qatar":("QA","Qatar","Catar"),
 "Saudi Arabia":("SA","Arabia Saudita","Arabia Saudí"), "Scotland":("_SCT","Scozia","Escocia"),
 "Senegal":("SN","Senegal","Senegal"), "South Africa":("ZA","Sudafrica","Sudáfrica"),
 "South Korea":("KR","Corea del Sud","Corea del Sur"), "Spain":("ES","Spagna","España"),
 "Sweden":("SE","Svezia","Suecia"), "Switzerland":("CH","Svizzera","Suiza"),
 "Tunisia":("TN","Tunisia","Túnez"), "Turkey":("TR","Turchia","Turquía"),
 "USA":("US","Stati Uniti","Estados Unidos"), "Uruguay":("UY","Uruguay","Uruguay"),
 "Uzbekistan":("UZ","Uzbekistan","Uzbekistán"),
}

def flag(iso2):
    if iso2 == "_ENG": return "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"
    if iso2 == "_SCT": return "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F"
    if not iso2 or len(iso2) != 2: return "\U0001F3F3"  # bandiera bianca
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())

def team(name):
    """Risolve un nome squadra (o un placeholder knockout) in {en,it,es,flag,ph}."""
    if name in NAZ:
        iso, it, es = NAZ[name]
        return {"en": name, "it": it, "es": es, "flag": flag(iso), "ph": False}
    # placeholder tipo 2A, 1C, W101, 3C/3D/3E... -> mostralo com'e'
    return {"en": name, "it": name, "es": name, "flag": "", "ph": True}

def to_utc(date, time):
    """ '2026-06-11' + '13:00 UTC-6' -> ISO UTC. """
    try:
        m = re.match(r"(\d{1,2}):(\d{2})\s*UTC([+-]\d{1,2})?", time or "")
        hh, mm = int(m.group(1)), int(m.group(2))
        off = int(m.group(3)) if m and m.group(3) else 0
        y, mo, d = map(int, date.split("-"))
        local = datetime(y, mo, d, hh, mm, tzinfo=timezone(timedelta(hours=off)))
        return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return date + "T00:00:00Z"

def conv_match(m):
    out = {"round": m.get("round", ""), "group": m.get("group", ""),
           "date": m.get("date", ""), "utc": to_utc(m.get("date", ""), m.get("time", "")),
           "ground": m.get("ground", ""), "team1": team(m.get("team1", "")), "team2": team(m.get("team2", ""))}
    sc = m.get("score")
    if sc and sc.get("ft"):
        out["score"] = {"ft": sc["ft"], "ht": sc.get("ht"), "et": sc.get("et"), "p": sc.get("p")}
        out["played"] = True
    else:
        out["played"] = False
    g1 = m.get("goals1") or []; g2 = m.get("goals2") or []
    if g1 or g2:
        def gg(lst): return [{"name": x.get("name", ""), "minute": x.get("minute"),
                              "pen": bool(x.get("penalty")), "og": bool(x.get("owngoal"))} for x in lst]
        out["goals1"] = gg(g1); out["goals2"] = gg(g2)
    return out

def standings(group_matches):
    tbl = {}
    def row(t):
        return tbl.setdefault(t["en"], {"team": t, "pg": 0, "v": 0, "n": 0, "p": 0, "gf": 0, "gs": 0, "pt": 0})
    for m in group_matches:
        row(m["team1"]); row(m["team2"])
        if not m["played"]:
            continue
        a, b = m["score"]["ft"]
        r1, r2 = row(m["team1"]), row(m["team2"])
        r1["pg"] += 1; r2["pg"] += 1; r1["gf"] += a; r1["gs"] += b; r2["gf"] += b; r2["gs"] += a
        if a > b: r1["v"] += 1; r2["p"] += 1; r1["pt"] += 3
        elif a < b: r2["v"] += 1; r1["p"] += 1; r2["pt"] += 3
        else: r1["n"] += 1; r2["n"] += 1; r1["pt"] += 1; r2["pt"] += 1
    rows = list(tbl.values())
    for r in rows: r["dr"] = r["gf"] - r["gs"]
    rows.sort(key=lambda r: (-r["pt"], -r["dr"], -r["gf"], r["team"]["en"]))
    return rows

NEWS_Q = {"it": "Mondiali 2026 calcio", "en": "World Cup 2026 football", "es": "Mundial 2026 fútbol"}

def fetch_news(lang, loc, n=8):
    out = []
    seen = set()
    for r in build.fetch(NEWS_Q[lang], n + 4, loc):
        kx = re.sub(r"[^a-z0-9 ]", "", r["titolo"].lower())[:60]
        if kx in seen:
            continue
        seen.add(kx)
        e = build.enrich(r["gn_link"], r["src_href"])
        out.append({"titolo": r["titolo"], "fonte": r["fonte"], "link": e["url"],
                    "img": e["img"], "dominio": e["dominio"], "quando": build.time_ago(r["pub"], lang)})
        if len(out) >= n:
            break
    return out

def main():
    print("Scarico openfootball 2026...")
    d = requests.get(SRC, timeout=25).json()
    matches = [conv_match(m) for m in d.get("matches", [])]
    # gironi
    groups = []
    gnames = sorted({m["group"] for m in matches if m["group"]})
    for g in gnames:
        gm = [m for m in matches if m["group"] == g]
        gm.sort(key=lambda x: x["utc"])
        groups.append({"name": g.replace("Group ", ""), "partite": gm, "classifica": standings(gm)})
    # knockout (per round, in ordine)
    ko_order = ["Round of 32", "Round of 16", "Quarter-final", "Semi-final", "Match for third place", "Final"]
    knockout = []
    for r in ko_order:
        rm = [m for m in matches if m["round"] == r]
        rm.sort(key=lambda x: x["utc"])
        if rm:
            knockout.append({"round": r, "partite": rm})
    # news per lingua
    print("News dedicate...")
    news = {}
    for lang in ("it", "en", "es"):
        try:
            news[lang] = fetch_news(lang, build.LANGS[lang])
        except Exception as e:
            print("  news", lang, "errore:", str(e)[:80]); news[lang] = []
    out = {"aggiornato": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "nome": d.get("name", "World Cup 2026"), "groups": groups, "knockout": knockout, "news": news}
    os.makedirs(DATA, exist_ok=True)
    json.dump(out, open(os.path.join(DATA, "mondiali.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    np = sum(len(g["partite"]) for g in groups) + sum(len(k["partite"]) for k in knockout)
    print("OK: " + str(len(groups)) + " gironi, " + str(np) + " partite, news IT/EN/ES " +
          str([len(news[l]) for l in ("it", "en", "es")]))

if __name__ == "__main__":
    main()
