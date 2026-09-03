#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - render_site.py: le pagine statiche per il posizionamento (kb/SEO.md §3, punti 1-3-4-6).
Genera, in italiano:
- iniezione statica nelle hub index.html, board.html, campionati.html (fra i marcatori <!--static:NOME--> ... <!--/static:NOME-->);
- squadre/<slug>.html per ogni squadra di data/teams.json + squadre/index.html;
- campionati/<slug>.html per le 6 competizioni di data/competizioni.json + campionati/index.html;
- fantacalcio/listone.html, voti-giornata-N.html, titolari.html, index.html (con FAQ) da data/fanta/*.json;
- llms.txt, robots.txt, sitemap-pagine/squadre/campionati/fanta.xml e l'indice sitemap.xml (lastmod veri: data/lastmod.json).
Uso: python scripts/render_site.py            (in update.yml DOPO build.py e competizioni.py, PRIMA del commit)
     python scripts/render_site.py --check    (solo controlli, non scrive)
Legge SOLO i JSON gia' presenti: nessuna rete, nessuna chiave. Non tocca data/<lang>/*.json."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_common import (esct, ROOT, DATA, SITE, SEASON, AUTHOR, ORG, COMPS, COMP_BY_CODE, COMP_BY_LEAGUE, LEAGUE_LABEL, LEAGUE_ORDER,
                         ZONES, FD_ALIAS, FANTA_ALIAS, STATE_LABEL, STATE_ORDER, esc, slugify, norm, load_json, save_text, read_text,
                         fdate_it, date_only, today_iso, dots, page, ld_script, breadcrumb_ld, LastMod, write_urlset, write_sitemap_index, badge)
import render_stats as RS   # statistiche squadra con grafici e schede giocatore (data/stats/*.json)

FINISHED = ("FINISHED", "AWARDED")

# ---------- dati ----------
def load_all():
    D = {"teams": load_json(os.path.join(DATA, "teams.json"), {"squadre": []}),
         "home": load_json(os.path.join(DATA, "it", "home.json"), {}) or {},
         "board": load_json(os.path.join(DATA, "it", "board.json"), {"squadre": {}}) or {"squadre": {}},
         "comp": load_json(os.path.join(DATA, "competizioni.json"), {"competizioni": []}) or {"competizioni": []},
         "rosters": load_json(os.path.join(DATA, "rosters.json"), {"rose": {}}) or {"rose": {}},
         "articles": load_json(os.path.join(DATA, "articles", "index.json"), {"articoli": []}) or {"articoli": []},
         "listone": load_json(os.path.join(DATA, "fanta", "listone.json"), {"players": []}) or {"players": []},
         "voti": {}, "titolari": None, "stats": RS.load_stats(), "pctx": None}
    fd = os.path.join(DATA, "fanta")
    if os.path.isdir(fd):
        for fn in sorted(os.listdir(fd)):
            m = re.match(r"voti-(\d+)\.json$", fn)
            if m:
                v = load_json(os.path.join(fd, fn))
                if v and v.get("ratings"):
                    D["voti"][int(m.group(1))] = v
            m = re.match(r"titolari-(\d+)\.json$", fn)
            if m:
                t = load_json(os.path.join(fd, fn))
                if t and t.get("status") and (D["titolari"] is None or (t.get("matchday") or 0) > (D["titolari"].get("matchday") or 0)):
                    D["titolari"] = t
    D["board_sq"] = D["board"].get("squadre") or {}
    D["arts"] = [a for a in D["articles"].get("articoli", []) if a.get("slug")]
    return D

class Teams:
    """Indice delle squadre di teams.json con i collegamenti a football-data (classifica, partite), rose e listone."""
    def __init__(self, D):
        self.list = D["teams"].get("squadre", [])
        self.by_name = {t["nome"]: t for t in self.list}
        self.slug = {t["nome"]: slugify(t["nome"]) for t in self.list}
        self.fd2name = {FD_ALIAS.get(t["nome"], t["nome"]): t["nome"] for t in self.list}
        self._fdnorm = {norm(k): v for k, v in self.fd2name.items()}
        self.rose = D["rosters"].get("rose", {})
        self.row_of, self.row_cl, self.matches_of, self.fdteam = {}, {}, {}, {}
        for c in D["comp"].get("competizioni", []):
            domestic = bool(COMP_BY_CODE.get(c["code"], {}).get("league"))
            for tbl in c.get("classifica", []):
                for r in tbl.get("table", []):
                    n = self.name_of(r["team"])
                    if not n:
                        continue
                    self.fdteam.setdefault(n, r["team"])
                    if domestic:
                        self.row_of.setdefault(n, (c, r, len(tbl["table"]), tbl.get("group", "")))
                    else:
                        self.row_cl.setdefault(n, (c, r, len(tbl["table"]), tbl.get("group", "")))
            for md, ms in (c.get("giornate") or {}).items():
                for m in ms:
                    for side in ("home", "away"):
                        n = self.name_of(m[side])
                        if n:
                            self.fdteam.setdefault(n, m[side])
                            self.matches_of.setdefault(n, []).append((c, m))
        for n in self.matches_of:
            self.matches_of[n].sort(key=lambda x: x[1].get("utc", ""))
        # squadre API-Football (data/stats/teams.json) -> nome di teams.json, e viceversa
        self.api = RS.map_teams(D.get("stats") or {}, [t["nome"] for t in self.list])
        self.api_name = {v: k for k, v in self.api.items()}

    def api_link(self, api_id, fallback=""):
        """Nome con link alla pagina squadra a partire dall'id API-Football (avversari nelle tabelle partita per partita)."""
        n = self.api_name.get(api_id)
        return ('<a href="' + self.url(n) + '">' + esc(n) + "</a>") if n else esc(fallback)

    def name_of(self, fdteam):
        s = (fdteam or {}).get("short") or ""
        if s in self.fd2name:
            return self.fd2name[s]
        return self._fdnorm.get(norm(s))

    def fanta_name(self, team):
        return FANTA_ALIAS.get(team, team) if FANTA_ALIAS.get(team, team) in self.by_name else None

    def url(self, nome):
        return "/squadre/" + self.slug[nome] + ".html"

    def link(self, fdteam):
        """Nome di una squadra football-data, con stemma e link alla pagina squadra se esiste."""
        n = self.name_of(fdteam)
        crest = ('<img class="crest" src="' + esc(fdteam.get("crest")) + '" alt="" loading="lazy">') if fdteam.get("crest") else ""
        if n:
            return '<a href="' + self.url(n) + '">' + crest + esc(n) + "</a>"
        return crest + esc(fdteam.get("short") or fdteam.get("name"))

    def link_name(self, nome, cls=""):
        t = self.by_name.get(nome)
        if not t:
            return esc(nome)
        return '<a href="' + self.url(nome) + '"' + (' class="' + cls + '"' if cls else "") + '>' + badge(t) + esc(nome) + "</a>"

from datetime import datetime, timezone
from urllib.parse import quote
from site_common import parse_iso

# ---------- pezzi riutilizzabili ----------
def ext(link):
    return 'href="' + esc(link or "#") + '" target="_blank" rel="noopener"'

def hours_since(iso):
    d = parse_iso(iso)
    return ((datetime.now(timezone.utc) - d).total_seconds() / 3600.0) if d else 1e9

def news_li(st, it, show_tag=True):
    tag = ('<span class="tag t-' + st + '">' + STATE_LABEL.get(st, st) + "</span>") if show_tag else ""
    when = (' <span class="ago">· ' + esc(it.get("quando")) + "</span>") if it.get("quando") else ""
    return ("<li>" + tag + dots(it.get("affidabilita")) + '<a class="t" ' + ext(it.get("link")) + ">" + esct(it.get("titolo")) + "</a>"
            '<div class="src">Fonte: <a ' + ext(it.get("link")) + ">" + esc(it.get("fonte") or "—") + "</a>" +
            (" · " + esc(it.get("dominio")) if it.get("dominio") else "") + when + "</div></li>")

def team_news(bd, limit=None):
    """Notizie di una squadra della board in ordine di concretezza (fatti, ufficiali, anteprime, voci): [(stato, voce)]."""
    out, seen = [], set()
    cols = bd.get("colonne") or {}
    for st in STATE_ORDER:
        for it in cols.get(st) or []:
            k = it.get("link") or it.get("titolo")
            if k in seen:
                continue
            seen.add(k)
            out.append((st, it))
    return out[:limit] if limit else out

def zone_class(pos, n, code):
    z = ZONES.get(code) or [0, 0, 0, 0]
    if pos <= z[0]:
        return "z1"
    if pos <= z[0] + z[1]:
        return "z2"
    if pos <= z[0] + z[1] + z[2]:
        return "z3"
    if pos > n - z[3]:
        return "zr"
    return ""

LEGEND = "Arancione: zona Champions · Blu: Europa League · Oro: Conference · Rosso: retrocessione"

def table_html(T, c, tbl, me=None, caption=""):
    rows = tbl.get("table") or []
    n = len(rows)
    has_form = any(r.get("form") for r in rows)
    h = ['<div class="card">' + ("<h3>" + caption + "</h3>" if caption else "") + '<div style="overflow-x:auto"><table><thead><tr>'
         '<th>#</th><th class="team">Squadra</th><th>PG</th><th>V</th><th>N</th><th>P</th><th>GF</th><th>GS</th><th>DR</th><th>Pt</th>' +
         ("<th>Forma</th>" if has_form else "") + "</tr></thead><tbody>"]
    for r in rows:
        nm = T.name_of(r["team"])
        cls = (zone_class(r.get("pos") or 0, n, c["code"]) + (" me" if me and nm == me else "")).strip()
        dr = r.get("dr") or 0
        h.append('<tr class="' + cls + '"><td class="pos">' + str(r.get("pos")) + '</td><td class="team">' + T.link(r["team"]) + "</td><td>" +
                 str(r.get("pg", 0)) + "</td><td>" + str(r.get("v", 0)) + "</td><td>" + str(r.get("n", 0)) + "</td><td>" + str(r.get("p", 0)) + "</td><td>" +
                 str(r.get("gf", 0)) + "</td><td>" + str(r.get("gs", 0)) + "</td><td>" + ("+" if dr > 0 else "") + str(dr) + '</td><td class="pt">' + str(r.get("pt", 0)) + "</td>" +
                 ("<td>" + esc(" ".join(x for x in (r.get("form") or "").split(",")[-5:])) + "</td>" if has_form else "") + "</tr>")
    h.append('</tbody></table></div><div class="legend">' + LEGEND + "</div></div>")
    return "".join(h)

STATUS_IT = {"IN_PLAY": "in corso", "PAUSED": "intervallo", "POSTPONED": "rinviata", "SUSPENDED": "sospesa", "CANCELLED": "annullata", "AWARDED": "a tavolino"}

def match_row(T, m, comp_name=""):
    st = STATUS_IT.get(m.get("status"), "")
    if m.get("ft"):
        r = '<span class="r">' + str(m["ft"][0]) + "-" + str(m["ft"][1]) + (" " + st if st else "") + "</span>"
    else:
        r = '<span class="r vs">' + (st or fdate_it(m.get("utc"), True, True).split(", ")[-1]) + "</span>"
    d = fdate_it(m.get("utc"), False, True) + (" · " + comp_name if comp_name else "")
    return '<div class="fx"><span class="d">' + esc(d) + '</span><span class="h">' + T.link(m["home"]) + "</span>" + r + "<span>" + T.link(m["away"]) + "</span></div>"

def match_ld(m, comp_name):
    home = m["home"].get("short") or m["home"].get("name") or ""
    away = m["away"].get("short") or m["away"].get("name") or ""
    ev = {"@type": "SportsEvent", "name": home + " - " + away, "sport": "Calcio", "startDate": m.get("utc"),
          "homeTeam": {"@type": "SportsTeam", "name": home}, "awayTeam": {"@type": "SportsTeam", "name": away},
          "organizer": {"@type": "SportsOrganization", "name": comp_name}, "location": {"@type": "Place", "name": "Campo di " + home}}
    if m.get("ft"):
        ev["description"] = comp_name + ": " + home + " " + str(m["ft"][0]) + "-" + str(m["ft"][1]) + " " + away + " (risultato finale)"
    elif m.get("status") == "POSTPONED":
        ev["eventStatus"] = "https://schema.org/EventPostponed"
    elif m.get("status") == "CANCELLED":
        ev["eventStatus"] = "https://schema.org/EventCancelled"
    else:
        ev["eventStatus"] = "https://schema.org/EventScheduled"
    return ev

TIPO_LABEL = {"recap": "Recap di giornata", "lunch": "Lunch break", "storia": "Focus", "scoop": "Scoop", "notti": "Notti mondiali"}

def art_card(a):
    k = a.get("team") or TIPO_LABEL.get(a.get("tipo") or "", "Articolo")
    return ('<a href="/articoli/it/' + esc(a["slug"]) + '.html"><div class="k">' + esc(k) + '</div><div class="h">' + esc((a.get("t") or {}).get("it") or a.get("giocatore") or "") +
            '</div><div class="m">' + esc(fdate_it(a.get("updated"))) + "</div></a>")

# ---------- pagine squadra ----------
GRUPPI = {"done": "Fatti", "conf": "Ufficiali", "obj": "Anteprime", "rumor": "Voci e analisi"}

def team_desc(nome, t, T, has_st=False):
    pos = ""
    if nome in T.row_of:
        c, r, n, g = T.row_of[nome]
        pos = ", " + str(r.get("pos")) + "ª in " + COMP_BY_CODE[c["code"]]["nome"] + " con " + str(r.get("pt", 0)) + " punti"
    st = "statistiche della stagione con grafici (gol per fase di gara, casa e trasferta, xG, possesso, moduli), " if has_st else ""
    return nome + pos + ": le notizie di oggi con fonte e grado di concretezza, " + st + "classifica, ultime e prossime partite, rosa completa con le schede dei giocatori e articoli. Aggiornato ogni due ore da TransferBeat."

def render_team(D, T, t):
    nome = t["nome"]; canon = SITE + T.url(nome); lg = t.get("league", "")
    comp_meta = COMP_BY_LEAGUE.get(lg)
    bd = D["board_sq"].get(nome) or {}
    upd = D["board"].get("aggiornato") or ""
    b = ["<h1>" + badge(t, 44) + esc(nome) + "</h1>"]
    b.append('<div class="sub">' + esc(LEAGUE_LABEL.get(lg, lg)) + " · notizie, classifica, calendario e rosa · aggiornato <time>" + esc(fdate_it(upd, True)) + "</time> · "
             '<a href="/board.html?team=' + quote(nome) + '">apri nella board live</a>' +
             (' · <a href="/campionati/' + comp_meta["slug"] + '.html">classifica ' + esc(comp_meta["nome"]) + "</a>" if comp_meta else "") + "</div>")
    news = team_news(bd)
    b.append("<h2>Le notizie di oggi su " + esc(nome) + "</h2>")
    if news:
        b.append('<p class="small">Ordinate per concretezza: prima i fatti, poi gli atti ufficiali, le anteprime e infine le voci. Ogni voce cita la testata e la sua affidabilità (pallini).</p>')
        for st in STATE_ORDER:
            grp = [it for s, it in news if s == st]
            if grp:
                b.append("<h3>" + GRUPPI[st] + " (" + str(len(grp)) + ')</h3><ul class="news">' + "".join(news_li(st, it, False) for it in grp) + "</ul>")
    else:
        b.append('<p class="small">Nessuna notizia classificata nelle ultime ore.</p>')
    b.append('<div class="grid2"><div>')
    if nome in T.row_of:
        c, r, n, g = T.row_of[nome]
        meta = COMP_BY_CODE[c["code"]]
        b.append("<h2>Classifica " + esc(meta["nome"]) + " " + SEASON + "</h2>")
        tbl = next((x for x in c.get("classifica", []) if any(T.name_of(rr["team"]) == nome for rr in x.get("table", []))), None)
        if tbl:
            b.append(table_html(T, c, tbl, me=nome))
        b.append('<p class="small"><a href="/campionati/' + meta["slug"] + '.html">Classifica completa, risultati e marcatori →</a></p>')
    b.append("</div><div>")
    ms = T.matches_of.get(nome) or []
    played = [(c, m) for c, m in ms if m.get("status") in FINISHED]
    coming = [(c, m) for c, m in ms if m.get("status") not in FINISHED]
    if coming:
        b.append('<h2>Prossime partite</h2><div class="card"><div class="in">' + "".join(match_row(T, m, COMP_BY_CODE.get(c["code"], {}).get("nome", c["code"])) for c, m in coming[:6]) + "</div></div>")
    if played:
        b.append('<h2>Ultime partite</h2><div class="card"><div class="in">' + "".join(match_row(T, m, COMP_BY_CODE.get(c["code"], {}).get("nome", c["code"])) for c, m in played[-6:][::-1]) + "</div></div>")
    b.append("</div></div>")
    tid = T.api.get(nome)
    if tid:
        b.append(RS.team_stats_html(D["stats"], T, nome, tid))
    rosa = T.rose.get(nome) or []
    rosa_api, names_api = RS.rosa_html(D["stats"], T, tid, D["pctx"]) if (tid and D.get("pctx")) else ("", [])
    if rosa_api:
        b.append("<h2>La rosa " + SEASON + " (" + str(len(names_api)) + " giocatori)</h2>" + rosa_api)
        b.append('<p class="small">Rose da API-Football, aggiornate il ' + esc(fdate_it(D["pctx"]["updated"])) + '. Ogni nome apre la scheda del giocatore con statistiche, carriera e voti · <a href="/giocatori/">tutti i giocatori di Serie A</a>.</p>')
        rosa = names_api
    elif rosa:
        b.append("<h2>La rosa " + SEASON + " (" + str(len(rosa)) + ' giocatori)</h2><ul class="rosa">' + "".join("<li>" + esc(p) + "</li>" for p in rosa) + "</ul>")
        b.append('<p class="small">Rosa da football-data.org, aggiornata il ' + esc(fdate_it(D["rosters"].get("updated"))) + ".</p>")
    arts = [a for a in D["arts"] if a.get("team") == nome][:8]
    if arts:
        b.append("<h2>Articoli su " + esc(nome) + '</h2><div class="arts">' + "".join(art_card(a) for a in arts) + "</div>")
    if lg == "Serie A" and D["listone"].get("players"):
        b.append('<p class="small">Fantacalcio: <a href="/fantacalcio/listone.html">quotazioni FantaTB</a> e <a href="/fantacalcio/titolari.html">probabili titolari</a> dei giocatori del ' + esc(nome) + ".</p>")
    ld = {"@context": "https://schema.org", "@type": "SportsTeam", "name": nome, "sport": "Calcio", "url": canon,
          "memberOf": {"@type": "SportsOrganization", "name": LEAGUE_LABEL.get(lg, lg)}}
    if t.get("paese"):
        ld["location"] = {"@type": "Country", "name": t["paese"]}
    if (T.fdteam.get(nome) or {}).get("crest"):
        ld["logo"] = T.fdteam[nome]["crest"]
    if rosa:
        ld["athlete"] = [{"@type": "Person", "name": p} for p in rosa]
    crumbs = [("Home", SITE + "/"), ("Squadre", SITE + "/squadre/"), (nome, canon)]
    has_st = bool(tid and ((D["stats"].get("teams") or {}).get("teams") or {}).get(str(tid)))
    return page(nome + (": notizie, statistiche, classifica, calendario e rosa" if has_st else ": notizie, classifica, calendario e rosa"),
                team_desc(nome, t, T, has_st), canon, "".join(b), crumbs=crumbs, ld=[ld], here="Squadre")

def render_squadre_index(D, T):
    canon = SITE + "/squadre/"
    b = ["<h1>Squadre: notizie, classifiche, calendario e rose</h1>",
         '<div class="sub">Una pagina per ognuna delle ' + str(len(T.list)) + " squadre seguite da TransferBeat in Serie A, Premier League e Liga: notizie del giorno classificate per concretezza, posizione in classifica, partite e rosa.</div>"]
    for lg in LEAGUE_ORDER:
        ts = [t for t in T.list if t.get("league") == lg]
        if not ts:
            continue
        meta = COMP_BY_LEAGUE.get(lg)
        b.append("<h2>" + esc(LEAGUE_LABEL.get(lg, lg)) + (' <a class="small" href="/campionati/' + meta["slug"] + '.html">classifica →</a>' if meta else "") + '</h2><div class="chips">')
        def key(t):
            r = T.row_of.get(t["nome"])
            return (r[1].get("pos") if r else 99, t["nome"])
        for t in sorted(ts, key=key):
            r = T.row_of.get(t["nome"])
            extra = (" · " + str(r[1].get("pos")) + "ª, " + str(r[1].get("pt", 0)) + " pt") if r else ""
            b.append('<a href="' + T.url(t["nome"]) + '">' + badge(t) + esc(t["nome"]) + esc(extra) + "</a>")
        b.append("</div>")
    ld = {"@context": "https://schema.org", "@type": "ItemList", "name": "Squadre seguite da TransferBeat",
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": t["nome"], "url": SITE + T.url(t["nome"])} for i, t in enumerate(T.list)]}
    return page("Squadre di Serie A, Premier League e Liga: notizie, classifiche e rose",
                "Le " + str(len(T.list)) + " squadre seguite da TransferBeat, una pagina ciascuna: notizie del giorno con fonti e concretezza, classifica, prossime partite, rosa e articoli.",
                canon, "".join(b), crumbs=[("Home", SITE + "/"), ("Squadre", canon)], ld=[ld], here="Squadre")

# ---------- pagine competizione ----------
def comp_title(meta, c):
    if c.get("classifica"):
        return "Classifica " + meta["nome"] + " " + SEASON + ", risultati, calendario e marcatori"
    return meta["nome"] + " " + SEASON + ": calendario, risultati e classifica"

def comp_leader(c):
    for tbl in c.get("classifica", []):
        rows = tbl.get("table") or []
        if rows:
            return rows[0]
    return None

def render_comp(D, T, c):
    meta = COMP_BY_CODE[c["code"]]; canon = SITE + "/campionati/" + meta["slug"] + ".html"
    upd = D["comp"].get("aggiornato") or ""
    lead = comp_leader(c)
    g = c.get("giornata")
    b = ["<h1>" + esc(comp_title(meta, c)) + "</h1>"]
    b.append('<div class="sub">' + esc(meta["paese"]) + " · giornata " + str(g or "") + " · " + str(c.get("partite_giocate", 0)) + " partite giocate su " + str(c.get("partite_totali", 0)) +
             " · aggiornato <time>" + esc(fdate_it(upd, True)) + "</time> · dati football-data.org</div>")
    events = []
    if c.get("classifica"):
        b.append("<h2>Classifica</h2>")
        for tbl in c["classifica"]:
            grp = tbl.get("group") or ""
            b.append(table_html(T, c, tbl, caption=(esc(grp) if re.search(r"GROUP|Group|Girone", grp) else "")))
    else:
        b.append('<p class="note">La classifica compare quando inizia la fase a campionato: fino ad allora qui trovi il calendario completo delle prime giornate.</p>')
    keys = sorted(int(k) for k in (c.get("giornate") or {}).keys())
    if keys:
        b.append("<h2>Risultati e calendario</h2>")
        for k in keys:
            ms = c["giornate"][str(k)] or []
            done = sum(1 for m in ms if m.get("status") in FINISHED)
            lab = "Giornata " + str(k) + (": risultati" if ms and done == len(ms) else (": in corso" if done else ": calendario"))
            b.append('<div class="card"><h3>' + lab + '</h3><div class="in">' + ("".join(match_row(T, m) for m in ms) or '<span class="small">Nessuna partita.</span>') + "</div></div>")
            if g is not None and abs(k - g) <= 1:
                events += [match_ld(m, meta["nome"]) for m in ms]
    for st, ms in (c.get("stages") or {}).items():
        b.append('<div class="card"><h3>' + esc(st.replace("_", " ").capitalize()) + '</h3><div class="in">' + "".join(match_row(T, m) for m in ms) + "</div></div>")
    if c.get("marcatori"):
        b.append('<h2>Marcatori</h2><div class="card"><div style="overflow-x:auto"><table><thead><tr><th>#</th><th class="l">Giocatore</th><th class="l">Squadra</th><th>Gol</th><th>Rig.</th><th>Assist</th></tr></thead><tbody>')
        for i, s in enumerate(c["marcatori"]):
            b.append("<tr><td>" + str(i + 1) + '</td><td class="l">' + esc(s.get("name")) + '</td><td class="l">' + T.link(s.get("team") or {}) + '</td><td class="pt">' +
                     str(s.get("goals", 0)) + "</td><td>" + str(s.get("pen", 0)) + "</td><td>" + str(s.get("assists", 0)) + "</td></tr>")
        b.append("</tbody></table></div></div>")
    names = {T.name_of(r["team"]) for tbl in c.get("classifica", []) for r in tbl.get("table", [])}
    names |= {T.name_of(m[s]) for ms in (c.get("giornate") or {}).values() for m in ms for s in ("home", "away")}
    names = sorted(n for n in names if n)
    if names:
        b.append('<h2>Le squadre</h2><div class="chips">' + "".join('<a href="' + T.url(n) + '">' + esc(n) + "</a>" for n in names) + "</div>")
    b.append('<p class="small">Altre competizioni: ' + " · ".join('<a href="/campionati/' + m["slug"] + '.html">' + esc(m["nome"]) + "</a>" for m in COMPS if m["code"] != c["code"]) +
             ' · <a href="/campionati.html">versione interattiva</a></p>')
    lead_txt = ""
    if lead:
        lead_txt = "classifica aggiornata con " + (T.name_of(lead["team"]) or lead["team"].get("short") or "") + " in testa a " + str(lead.get("pt", 0)) + " punti, "
    desc = meta["nome"] + " " + SEASON + ": " + (lead_txt or "calendario completo, ") + "risultati dell'ultima giornata, calendario della prossima e classifica marcatori. Dati ufficiali, aggiornati ogni due ore."
    ld = [{"@context": "https://schema.org", "@type": "SportsOrganization", "name": meta["nome"], "sport": "Calcio", "url": canon}]
    if events:
        ld.append({"@context": "https://schema.org", "@type": "ItemList", "name": meta["nome"] + " " + SEASON + ": partite",
                   "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": e} for i, e in enumerate(events[:24])]})
    crumbs = [("Home", SITE + "/"), ("Campionati", SITE + "/campionati/"), (meta["nome"], canon)]
    return page(comp_title(meta, c), desc, canon, "".join(b), crumbs=crumbs, ld=ld, here="Campionati")

def render_comp_index(D, T):
    canon = SITE + "/campionati/"
    b = ["<h1>Campionati e coppe " + SEASON + ": classifiche, risultati e marcatori</h1>",
         '<div class="sub">Sei competizioni con classifica, calendario giornata per giornata, risultati e marcatori, aggiornati ogni due ore. Versione interattiva in <a href="/campionati.html">Campionati</a>.</div>']
    for c in D["comp"].get("competizioni", []):
        meta = COMP_BY_CODE.get(c["code"]); lead = comp_leader(c)
        if not meta:
            continue
        b.append('<div class="card"><h3><a href="/campionati/' + meta["slug"] + '.html">' + esc(meta["nome"]) + '</a></h3><div class="in">Giornata ' + str(c.get("giornata") or "") + " · " +
                 (("in testa " + T.link(lead["team"]) + " con " + str(lead.get("pt", 0)) + " punti") if lead else "fase a campionato non ancora iniziata") +
                 ' · <a href="/campionati/' + meta["slug"] + '.html">classifica, risultati e marcatori →</a></div></div>')
    return page("Campionati e coppe " + SEASON + ": classifiche, risultati e marcatori",
                "Serie A, Champions League, Premier League, Liga, Bundesliga e Ligue 1: classifica, risultati, calendario e marcatori di ogni competizione, in pagine aggiornate ogni due ore.",
                canon, "".join(b), crumbs=[("Home", SITE + "/"), ("Campionati", canon)], here="Campionati")

# ---------- fantacalcio: pagine dati (kb/SEO.md §3.4, formule in kb/FANTATB.md §5-7) ----------
RUOLI = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}
FANTA_CRUMB = [("Home", SITE + "/"), ("Fantacalcio", SITE + "/fantacalcio/")]
ROLE_SELECT = '<select id="r"><option value="">Tutti i ruoli</option><option value="P">Portieri</option><option value="D">Difensori</option><option value="C">Centrocampisti</option><option value="A">Attaccanti</option></select>'
VOTO_NOTE = ('<div class="note"><b>Come nasce il voto FantaTB.</b> Voto base = rating statistico della partita (API-Football) meno 0,8, arrotondato al mezzo punto, fra 4 e 8,5; '
             'senza rating ma con almeno 15 minuti vale 6; sotto i 15 minuti è senza voto (s.v.). Il fantavoto somma bonus e malus con i pesi di default: gol +3, assist +1, '
             'rigore sbagliato −3, rigore parato +3, gol subito (portiere) −1, autogol −2, ammonizione −0,5, espulsione −1. Sono voti statistici, calcolati da noi con formula '
             'pubblica: non coincidono con quelli dei quotidiani. Non affiliato a Fantacalcio®.</div>')
SORT_JS = ("<script>(function(){var t=document.querySelector('table.srt');if(!t)return;var q=document.getElementById('q'),r=document.getElementById('r');"
           "function filt(){var s=(q&&q.value||'').toLowerCase(),ro=r&&r.value||'';t.querySelectorAll('tbody tr').forEach(function(tr){var ok=(!s||tr.textContent.toLowerCase().indexOf(s)>=0)&&(!ro||tr.getAttribute('data-r')===ro);tr.style.display=ok?'':'none';});}"
           "if(q)q.oninput=filt;if(r)r.onchange=filt;t.querySelectorAll('th.sort').forEach(function(th,i){th.onclick=function(){var tb=t.tBodies[0],rows=[].slice.call(tb.rows),num=th.getAttribute('data-n')==='1',asc=th.getAttribute('data-asc')!=='1';"
           "rows.sort(function(a,b){var x=a.cells[i].getAttribute('data-v')||a.cells[i].textContent,y=b.cells[i].getAttribute('data-v')||b.cells[i].textContent;if(num){x=parseFloat(x);y=parseFloat(y);if(isNaN(x))x=-999;if(isNaN(y))y=-999;return asc?x-y:y-x;}return asc?x.localeCompare(y):y.localeCompare(x);});"
           "rows.forEach(function(x){tb.appendChild(x);});th.setAttribute('data-asc',asc?'1':'0');};});})();</script>")

def dataset_ld(name, desc, url, json_url, updated, keywords):
    return {"@context": "https://schema.org", "@type": "Dataset", "name": name, "description": desc, "url": url, "inLanguage": "it",
            "keywords": keywords, "creator": ORG, "publisher": ORG, "dateModified": date_only(updated), "license": "https://creativecommons.org/licenses/by/4.0/",
            "isAccessibleForFree": True, "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": json_url}]}

def fanta_team_link(T, team):
    n = T.fanta_name(team or "")
    return ('<a href="' + T.url(n) + '">' + esc(team) + "</a>") if n else esc(team)

def dec(x):
    return ("%g" % x).replace(".", ",") if isinstance(x, (int, float)) else str(x)

def render_listone(D, T):
    L = D["listone"]; ps = sorted(L.get("players") or [], key=lambda p: (-(p.get("price") or 0), p.get("name") or ""))
    canon = SITE + "/fantacalcio/listone.html"; upd = L.get("updated") or ""
    n = len(ps)
    top = ", ".join(esc(p["name"]) + " (" + str(p["price"]) + ")" for p in ps[:5])
    b = ["<h1>Listone fantacalcio " + SEASON + ": le quotazioni FantaTB di " + str(n) + " giocatori di Serie A</h1>",
         '<div class="sub">Aggiornato <time>' + esc(fdate_it(upd, True)) + "</time> · Serie A " + SEASON + " · ruoli Classic · i più cari: " + top + "</div>",
         '<div class="note"><b>Come calcoliamo le quotazioni.</b> Base per ruolo (P 1, D 1, C 1, A 2) + presenze della scorsa stagione su 38 × (P 8, D 10, C 12, A 14) '
         '+ gol × (D 3, C 2, A 1,2) + assist × (D 1, C 1, A 0,8) + (rating medio − 6,5) × 10 se sopra 6,5 con almeno 10 presenze; i portieri con meno di un gol subito '
         'a partita guadagnano 0,3 a presenza. Limite da 1 a 60 crediti. Fonte statistiche: API-Football. Il listone si rifà dopo il mercato di gennaio.</div>',
         '<div class="tools"><input id="q" placeholder="Cerca giocatore o squadra">' + ROLE_SELECT + '<span class="small">Clic sull\'intestazione per ordinare</span></div>',
         '<div class="card"><div style="overflow-x:auto"><table class="srt"><thead><tr><th class="sort" data-n="1">#</th><th class="sort l">Ruolo</th><th class="sort l">Giocatore</th>'
         '<th class="sort l">Squadra</th><th class="sort" data-n="1">Quotazione</th></tr></thead><tbody>']
    for i, p in enumerate(ps):
        b.append('<tr data-r="' + esc(p.get("role")) + '"><td>' + str(i + 1) + '</td><td class="l">' + esc(RUOLI.get(p.get("role"), p.get("role"))) + '</td><td class="l">' + RS.plink(D.get("pctx"), p["id"], p.get("name")) +
                 '</td><td class="l">' + fanta_team_link(T, p.get("team")) + '</td><td class="pt" data-v="' + str(p.get("price") or 0) + '">' + str(p.get("price") or 0) + "</td></tr>")
    b.append("</tbody></table></div></div>" + SORT_JS)
    b.append('<p class="small">Il listone è usato nelle aste di <a href="/fanta/">FantaTB</a>, il fantacalcio gratuito di TransferBeat · dati grezzi: <a href="/data/fanta/listone.json">listone.json</a> · <a href="/fantacalcio/">tutti i dati del fantacalcio</a></p>')
    ld = dataset_ld("Listone fantacalcio Serie A " + SEASON + " (quotazioni FantaTB)",
                    "Quotazioni FantaTB di " + str(n) + " giocatori di Serie A con ruolo Classic e squadra, calcolate con formula pubblica da presenze, gol, assist e rating.",
                    canon, SITE + "/data/fanta/listone.json", upd, ["fantacalcio", "listone", "quotazioni", "Serie A " + SEASON])
    return page("Listone fantacalcio " + SEASON + ": quotazioni FantaTB di " + str(n) + " giocatori",
                "Il listone del fantacalcio " + SEASON + " con le quotazioni FantaTB di " + str(n) + " giocatori di Serie A: ruolo, squadra e prezzo in crediti, formula pubblica, tabella ordinabile e dati scaricabili.",
                canon, "".join(b), crumbs=FANTA_CRUMB + [("Listone", canon)], ld=[ld], here="FantaTB")

BONUS_IT = {"gol": ("⚽", "gol"), "assist": ("👟", "assist"), "rig_sbagliato": ("❌", "rigore sbagliato"), "rig_parato": ("🧤", "rigore parato"),
            "gol_subito": ("🥅", "gol subito"), "autogol": ("🙈", "autogol"), "amm": ("🟨", "ammonizione"), "esp": ("🟥", "espulsione")}

def bonus_txt(bonus):
    out = []
    for k, v in (bonus or {}).items():
        if not v:
            continue
        e, lab = BONUS_IT.get(k, ("", k))
        out.append(e + (" ×" + str(v) if v > 1 else "") + " " + lab)
    return " · ".join(out)

def render_voti(D, T, md, V):
    canon = SITE + "/fantacalcio/voti-giornata-" + str(md) + ".html"; upd = V.get("updated") or ""
    fn = "voti-%02d.json" % md
    byid = {p["id"]: p for p in D["listone"].get("players") or []}
    rows = [(byid[r["player_id"]], r) for r in V.get("ratings") or [] if r.get("player_id") in byid]
    rated = [x for x in rows if x[1].get("voto") is not None]
    sv = [x for x in rows if x[1].get("voto") is None]
    rated.sort(key=lambda x: (-(x[1].get("fantavoto") or 0), -(x[1].get("voto") or 0), x[0]["name"]))
    sv.sort(key=lambda x: x[0]["name"])
    media = round(sum(x[1]["voto"] for x in rated) / len(rated), 2) if rated else 0
    top = ", ".join(esc(p["name"]) + " " + dec(r.get("fantavoto")) for p, r in rated[:5])
    stato = "giornata completa" if V.get("status") == "rated" else str(V.get("finished", 0)) + " partite su " + str(V.get("total", 0))
    b = ["<h1>Voti fantacalcio giornata " + str(md) + " Serie A " + SEASON + ": voto, bonus e fantavoto FantaTB</h1>",
         '<div class="sub">' + stato + " · " + str(len(rated)) + " giocatori con voto, " + str(len(sv)) + " senza voto · media voto " + dec(media) +
         " · aggiornato <time>" + esc(fdate_it(upd, True)) + "</time> · i migliori: " + top + "</div>", VOTO_NOTE,
         '<div class="tools"><input id="q" placeholder="Cerca giocatore o squadra">' + ROLE_SELECT + '<span class="small">Clic sull\'intestazione per ordinare</span></div>',
         '<div class="card"><div style="overflow-x:auto"><table class="srt"><thead><tr><th class="sort l">Giocatore</th><th class="sort l">Squadra</th><th class="sort">Ruolo</th>'
         '<th class="sort" data-n="1">Min</th><th class="sort" data-n="1">Voto</th><th class="l">Bonus e malus</th><th class="sort" data-n="1">Fantavoto</th></tr></thead><tbody>']
    for p, r in rated + sv:
        v = r.get("voto"); fv = r.get("fantavoto")
        b.append('<tr data-r="' + esc(p.get("role")) + '"><td class="l">' + RS.plink(D.get("pctx"), p["id"], p["name"]) + '</td><td class="l">' + fanta_team_link(T, p.get("team")) + "</td><td>" + esc(p.get("role")) +
                 '</td><td data-v="' + str(r.get("minutes") or 0) + '">' + str(r.get("minutes") or 0) + '</td><td data-v="' + (str(v) if v is not None else "-1") + '">' +
                 (dec(v) if v is not None else "s.v.") + '</td><td class="l">' + esc(bonus_txt(r.get("bonus"))) + '</td><td class="pt" data-v="' + (str(fv) if fv is not None else "-1") + '">' +
                 (dec(fv) if fv is not None else "—") + "</td></tr>")
    b.append("</tbody></table></div></div>" + SORT_JS)
    others = sorted(D["voti"].keys())
    b.append('<p class="small">Altre giornate: ' + " · ".join(("<b>giornata " + str(k) + "</b>") if k == md else ('<a href="/fantacalcio/voti-giornata-' + str(k) + '.html">giornata ' + str(k) + "</a>") for k in others) +
             ' · dati grezzi: <a href="/data/fanta/' + fn + '">' + fn + '</a> · <a href="/fantacalcio/">tutti i dati del fantacalcio</a></p>')
    ld = dataset_ld("Voti fantacalcio FantaTB, Serie A " + SEASON + " giornata " + str(md),
                    "Voto statistico, minuti, bonus e malus e fantavoto di " + str(len(rows)) + " giocatori di Serie A per la giornata " + str(md) + ", calcolati da FantaTB con formula pubblica.",
                    canon, SITE + "/data/fanta/" + fn, upd, ["fantacalcio", "voti", "fantavoto", "Serie A giornata " + str(md)])
    return page("Voti fantacalcio giornata " + str(md) + " Serie A " + SEASON + ": voto, bonus e fantavoto",
                "I voti FantaTB della giornata " + str(md) + " di Serie A " + SEASON + ": " + str(len(rated)) + " giocatori con voto statistico, minuti, bonus e malus e fantavoto. I migliori: " + re.sub(r"<[^>]+>", "", top) + ".",
                canon, "".join(b), crumbs=FANTA_CRUMB + [("Voti giornata " + str(md), canon)], ld=[ld], here="FantaTB")

def render_titolari(D, T):
    S = D["titolari"]; md = S.get("matchday") or 0; canon = SITE + "/fantacalcio/titolari.html"; upd = S.get("updated") or ""
    fn = "titolari-%02d.json" % md
    byid = {p["id"]: p for p in D["listone"].get("players") or []}
    rows = [(byid[s["player_id"]], s) for s in S.get("status") or [] if s.get("player_id") in byid]
    inf = [(p, s) for p, s in rows if s.get("injury")]
    squal = [(p, s) for p, s in rows if "squalific" in (s.get("reason") or "").lower() and not s.get("injury")]
    teams = {}
    for p, s in rows:
        teams.setdefault(p.get("team") or "?", []).append((p, s))
    def pct(v):
        v = int(v or 0)
        return '<span class="pct ' + ("g" if v >= 70 else ("a" if v >= 40 else "r")) + '">' + str(v) + "%</span>"
    b = ["<h1>Probabili titolari, infortunati e squalificati: giornata " + str(md) + " Serie A " + SEASON + "</h1>",
         '<div class="sub">Indice di titolarità FantaTB per ' + str(len(rows)) + " giocatori · " + str(len(inf)) + " infortunati, " + str(len(squal)) + " squalificati · aggiornato <time>" + esc(fdate_it(upd, True)) + "</time></div>",
         '<div class="note"><b>Come nasce l\'indice.</b> Dalle ultime tre giornate: 90% se titolare (almeno 60 minuti) in tutte; altrimenti 15 + 25 per ogni partita da titolare + 5 per ogni '
         'subentro (fra 5 e 95); mai in campo 10%; mai convocato 20%; espulso nell\'ultima giornata 0% (squalifica). Infortuni e squalifiche da API-Football, con data di rientro stimata '
         'quando c\'è. È un indice statistico, non una formazione ufficiale: le probabili dei giornali restano un\'altra cosa.</div>']
    if inf:
        b.append("<h2>Infortunati (" + str(len(inf)) + ')</h2><ul class="news">' + "".join(
            "<li><b>" + RS.plink(D.get("pctx"), p["id"], p["name"]) + "</b> (" + fanta_team_link(T, p.get("team")) + ", " + esc(p.get("role")) + ") · " + esc(s.get("injury")) +
            (" · rientro stimato " + esc(fdate_it(s["back_at"] + "T12:00:00Z")) if s.get("back_at") else "") + "</li>" for p, s in inf) + "</ul>")
    if squal:
        b.append("<h2>Squalificati (" + str(len(squal)) + ')</h2><ul class="news">' + "".join(
            "<li><b>" + RS.plink(D.get("pctx"), p["id"], p["name"]) + "</b> (" + fanta_team_link(T, p.get("team")) + ") · " + esc(s.get("reason")) + "</li>" for p, s in squal) + "</ul>")
    b.append('<h2>Squadra per squadra</h2><div class="grid2">')
    order = {"P": 0, "D": 1, "C": 2, "A": 3}
    for team in sorted(teams):
        lst = sorted(teams[team], key=lambda x: (-(x[1].get("prob") or 0), order.get(x[0].get("role"), 9), x[0]["name"]))
        b.append('<div class="card"><h3>' + fanta_team_link(T, team) + '</h3><div class="in"><table><thead><tr><th class="l">Giocatore</th><th>R</th><th>Titolare</th><th class="l">Perché</th></tr></thead><tbody>')
        for p, s in lst:
            b.append('<tr><td class="l">' + RS.plink(D.get("pctx"), p["id"], p["name"]) + "</td><td>" + esc(p.get("role")) + "</td><td>" + pct(s.get("prob")) + '</td><td class="l small">' + esc(s.get("reason")) + "</td></tr>")
        b.append("</tbody></table></div></div>")
    b.append("</div>")
    b.append('<p class="small">Dati grezzi: <a href="/data/fanta/' + fn + '">' + fn + '</a> · usati nella schermata di schieramento di <a href="/fanta/">FantaTB</a> · <a href="/fantacalcio/">tutti i dati del fantacalcio</a></p>')
    ld = dataset_ld("Indice di titolarità FantaTB, Serie A " + SEASON + " giornata " + str(md),
                    "Probabilità di titolarità, infortuni con rientro stimato e squalifiche per " + str(len(rows)) + " giocatori di Serie A in vista della giornata " + str(md) + ".",
                    canon, SITE + "/data/fanta/" + fn, upd, ["fantacalcio", "probabili formazioni", "titolari", "infortunati", "squalificati"])
    return page("Probabili titolari, infortunati e squalificati giornata " + str(md) + " Serie A",
                "Chi gioca e chi no nella giornata " + str(md) + " di Serie A " + SEASON + ": indice di titolarità FantaTB per " + str(len(rows)) + " giocatori, " + str(len(inf)) +
                " infortunati con rientro stimato e " + str(len(squal)) + " squalificati, squadra per squadra.",
                canon, "".join(b), crumbs=FANTA_CRUMB + [("Titolari", canon)], ld=[ld], here="FantaTB")

FAQ = [("Come si calcola il voto FantaTB?", "Dal rating statistico della partita meno 0,8, arrotondato al mezzo punto fra 4 e 8,5; senza voto sotto i 15 minuti. Il fantavoto aggiunge bonus e malus con pesi pubblici: gol +3, assist +1, rigore sbagliato −3, rigore parato +3, gol subito −1 per i portieri, autogol −2, ammonizione −0,5, espulsione −1. L'admin di lega può correggere qualsiasi voto."),
       ("I voti sono quelli della Gazzetta o di Fantacalcio.it?", "No. Sono voti statistici calcolati da FantaTB dai dati reali della partita, con formula pubblica. Non coincidono con quelli dei quotidiani e FantaTB non è affiliato a Fantacalcio®."),
       ("Quanto costa FantaTB?", "Niente. È gratuito, senza funzioni a pagamento e senza limiti di leghe: è un servizio di TransferBeat."),
       ("Serve installare un'app?", "No: funziona dal browser del telefono e del computer. Bastano un'email e una password."),
       ("Come si calcolano le quotazioni del listone?", "Da presenze, gol, assist e rating della stagione precedente, con una base per ruolo e un limite fra 1 e 60 crediti. La formula completa è nella pagina del listone; il listone si rifà dopo il mercato di gennaio."),
       ("Cos'è l'indice di titolarità?", "Una probabilità da 0 a 100 che un giocatore parta titolare nella prossima giornata, calcolata dalle ultime tre partite, più infortuni e squalifiche con data di rientro stimata. È un indice statistico, non una formazione ufficiale."),
       ("Posso riutilizzare questi dati?", "Sì: listone, voti e titolarità sono pubblicati anche come file JSON con licenza CC BY 4.0. Basta citare TransferBeat con un link.")]

def render_fanta_index(D, T):
    canon = SITE + "/fantacalcio/"
    n = len(D["listone"].get("players") or []); mds = sorted(D["voti"].keys()); tit = D["titolari"]
    voti_btns = " ".join('<a class="btn sec" href="/fantacalcio/voti-giornata-' + str(k) + '.html">Giornata ' + str(k) + "</a>" for k in mds) or '<span class="small">Disponibili dopo la prima giornata.</span>'
    tit_html = (("Indice di titolarità, infortunati e squalificati per la giornata " + str(tit.get("matchday")) + '.<br><a class="btn" href="/fantacalcio/titolari.html">Chi gioca e chi no</a>')
                if tit else '<span class="small">In arrivo prima della prossima giornata.</span>')
    b = ["<h1>Fantacalcio " + SEASON + ": listone, voti e probabili titolari, gratis e con formula pubblica</h1>",
         '<div class="sub">I dati originali di FantaTB, il fantacalcio gratuito di TransferBeat: quotazioni di ' + str(n) + " giocatori, voti statistici dopo ogni giornata di Serie A, indice di titolarità con infortunati e squalificati. Anche in JSON, licenza CC BY 4.0.</div>",
         '<div class="grid2"><div class="card"><h3>Listone</h3><div class="in">Quotazioni FantaTB di ' + str(n) + ' giocatori di Serie A, ruolo Classic, tabella ordinabile.<br><a class="btn" href="/fantacalcio/listone.html">Apri il listone</a></div></div>',
         '<div class="card"><h3>Voti</h3><div class="in">Voto, minuti, bonus e malus e fantavoto di ogni giocatore, giornata per giornata.<br>' + voti_btns + "</div></div>",
         '<div class="card"><h3>Probabili titolari</h3><div class="in">' + tit_html + "</div></div>",
         '<div class="card"><h3>Gioca con FantaTB</h3><div class="in">Leghe private, asta live dal telefono, regole su misura, classifica ogni giornata. Gratis.<br><a class="btn" href="/fanta/#crea">Crea la tua lega</a> <a class="btn sec" href="/fantatb.html">Scopri FantaTB</a></div></div></div>',
         '<h2>Domande frequenti</h2><div class="faq">' + "".join("<details><summary>" + esc(q) + "</summary><p>" + esc(a) + "</p></details>" for q, a in FAQ) + "</div>"]
    ld = [{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ]},
          {"@context": "https://schema.org", "@type": "WebApplication", "name": "FantaTB", "url": SITE + "/fanta/", "applicationCategory": "GameApplication", "operatingSystem": "Web",
           "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"}, "publisher": ORG,
           "description": "Fantacalcio gratuito con leghe private, asta live, voti statistici e regole su misura."}]
    return page("Fantacalcio " + SEASON + ": listone, voti e probabili titolari gratis",
                "Listone con le quotazioni di " + str(n) + " giocatori, voti statistici di ogni giornata di Serie A e probabili titolari con infortunati e squalificati: i dati aperti di FantaTB, il fantacalcio gratuito di TransferBeat.",
                canon, "".join(b), crumbs=FANTA_CRUMB, ld=ld, here="FantaTB")

# ---------- iniezione statica nelle hub (fra <!--static:NOME--> e <!--/static:NOME-->) ----------
def inject(path, blocks):
    src = read_text(path); out = src
    for name, html_ in blocks.items():
        pat = re.compile(r"(<!--static:" + re.escape(name) + r"-->)(.*?)(<!--/static:" + re.escape(name) + r"-->)", re.S)
        if not pat.search(out):
            raise SystemExit("render_site: marcatore static:" + name + " assente in " + os.path.relpath(path, ROOT))
        out = pat.sub(lambda m: m.group(1) + html_ + m.group(3), out, count=1)
    if out != src:
        save_text(path, out)

def home_card(o, emoji="📰"):
    img = ('<div class="ph2"><img src="' + esc(o.get("img")) + '" loading="lazy" alt=""></div>') if o.get("img") else '<div class="ph2"><span>' + emoji + "</span></div>"
    when = (' · <span class="ago">' + esc(o.get("quando")) + "</span>") if o.get("quando") else ""
    return ('<div class="art"><a class="ph2link" ' + ext(o.get("link")) + ">" + img + '</a><div class="cat">' + esc(o.get("categoria")) + "</div><h3><a " + ext(o.get("link")) + ">" +
            esct(o.get("titolo")) + '</a></h3><div class="credit">Fonte: <a ' + ext(o.get("link")) + ">" + esc(o.get("fonte") or "—") + "</a>" + when + "</div></div>")

COVER = {"recap": ("img/cover-recap.svg", "#0a9d57"), "lunch": ("img/cover-lunch.svg", "#d98700"), "storia": ("img/cover-storia.svg", "#1f6fd6"),
         "scoop": ("img/cover-scoop.svg", "#e0392b"), "notti": ("img/cover-notti.svg", "#21366e")}

def art_home_card(a):
    url = "/articoli/it/" + esc(a["slug"]) + ".html"
    return ('<div class="art"><a class="ph2link" href="' + url + '"><div class="ph2" style="background:' + esc(a.get("col") or "#ff6a00") + ';display:grid;place-items:center">'
            '<span style="color:#fff;font-weight:800;font-size:22px;opacity:1">' + esc(a.get("lab") or "TB") + '</span></div></a><div class="cat">' +
            esc(a.get("team") or TIPO_LABEL.get(a.get("tipo") or "", "Articolo")) + '</div><h3><a href="' + url + '">' + esc((a.get("t") or {}).get("it")) +
            '</a></h3><div class="credit">' + esc(fdate_it(a.get("updated"))) + "</div></div>")

def render_home(D, T, lm):
    H = D["home"]; upd = H.get("aggiornato") or ""; arts = D["arts"]
    lead = ""
    fresh = [a for a in arts if a.get("tipo") in COVER and hours_since(a.get("updated")) <= 48]
    if fresh:   # come il JS: l'ultimo articolo recente apre la pagina, altrimenti la notizia di apertura
        a = fresh[0]; cov, col = COVER[a["tipo"]]; url = "/articoli/it/" + esc(a["slug"]) + ".html"; lab = TIPO_LABEL[a["tipo"]]
        lead = ('<a class="ph" href="' + url + '" style="display:grid"><img src="' + cov + '" alt=""><span class="badge" style="background:' + col + '">' + lab.upper() + '</span></a>'
                '<div class="kicker">' + lab + " · " + esc(fdate_it(a.get("updated"))) + '</div><h2 class="hh"><a href="' + url + '">' + esc((a.get("t") or {}).get("it")) +
                '</a></h2><div class="by">Redazione TransferBeat</div>')
    elif H.get("apertura"):
        a = H["apertura"]
        lead = ('<a class="ph" ' + ext(a.get("link")) + ' style="display:grid">' + ('<img src="' + esc(a.get("img")) + '" alt="">' if a.get("img") else '<div class="ico">⚽</div>') +
                '<span class="badge">IN PRIMO PIANO</span></a><div class="kicker">' + esc(a.get("categoria")) + '</div><h2 class="hh"><a ' + ext(a.get("link")) + ">" + esct(a.get("titolo")) +
                '</a></h2><div class="by">Fonte: <a ' + ext(a.get("link")) + ' style="color:var(--accent2);font-weight:600">' + esc(a.get("fonte")) + "</a>" +
                (" (" + esc(a.get("dominio")) + ")" if a.get("dominio") else "") + "</div>")
    ticker = "".join("<span>🟢 " + esct(t) + "</span>" for t in H.get("ticker") or [])
    sub3 = "".join(home_card(s) for s in (H.get("secondari") or []) if s)
    world = "".join(home_card(m, "🌍") for m in H.get("mondo") or [])
    top = [t for t in [H.get("apertura")] + list(H.get("secondari") or []) if t]
    topnews = "".join('<a class="r" ' + ext(t.get("link")) + '><span class="st s-obj">' + str(i + 1) + '</span><span class="tt">' + esct(t.get("titolo")) + "</span></a>" for i, t in enumerate(top))
    mini = []
    for nome, v in D["board_sq"].items():
        for st in ("done", "conf"):
            for c in (v.get("colonne") or {}).get(st) or []:
                mini.append('<a class="r" ' + ext(c.get("link")) + '><span class="st s-' + st + '">' + {"done": "Fatto", "conf": "Uffic."}[st] + '</span><span class="tt">' + esct(c.get("titolo")) + "</span></a>")
    miniboard = "".join(mini[:6]) or '<div style="color:var(--muted);font-size:12px;padding:6px 0">—</div>'
    artrow = "".join(art_home_card(a) for a in arts[:8])
    squadre = []
    for lg in LEAGUE_ORDER:
        ts = [t for t in T.list if t.get("league") == lg]; meta = COMP_BY_LEAGUE.get(lg)
        squadre.append('<div class="sqlg"><b>' + esc(LEAGUE_LABEL.get(lg, lg)) + "</b>" + (' <a class="cl" href="/campionati/' + meta["slug"] + '.html">classifica</a> · ' if meta else " · ") +
                       " · ".join('<a href="' + T.url(t["nome"]) + '">' + esc(t["nome"]) + "</a>" for t in ts) + "</div>")
    squadre.append('<div class="sqlg"><b>Coppe e altri campionati</b> · ' + " · ".join('<a href="/campionati/' + m["slug"] + '.html">' + esc(m["nome"]) + "</a>" for m in COMPS if not m["league"]) +
                   ' · <a class="cl" href="/squadre/">tutte le squadre →</a> · <a class="cl" href="/fantacalcio/">fantacalcio: listone, voti e titolari</a></div>')
    masthead = esc(H.get("giorno")) + "<br>Edizione delle <b><time>" + esc((upd or "")[11:16]) + "</time></b> · Il giornale del calcio"
    blocks = {"ticker": ticker, "lead": lead, "sub3": sub3, "miniBoard": miniboard, "topNews": topnews, "articoliRow": artrow, "worldRow": world, "squadre": "".join(squadre), "masthead": masthead}
    inject(os.path.join(ROOT, "index.html"), blocks)
    return lm.touch("/", "".join(blocks.values()))

def render_board(D, T, lm):
    upd = D["board"].get("aggiornato") or ""
    out = []
    for lg in LEAGUE_ORDER:
        ts = [t for t in T.list if t.get("league") == lg and t["nome"] in D["board_sq"]]
        if not ts:
            continue
        meta = COMP_BY_LEAGUE.get(lg)
        out.append('<div class="sbl" data-league="' + esc(lg) + '"><h2>' + esc(LEAGUE_LABEL.get(lg, lg)) + ': le notizie squadra per squadra</h2><p class="small">Ogni squadra ha anche una pagina con classifica, partite e rosa' +
                   (', e c\'è la <a href="/campionati/' + meta["slug"] + '.html">classifica ' + esc(meta["nome"]) + "</a>" if meta else "") + ".</p></div>")
        for t in ts:
            nome = t["nome"]; bd = D["board_sq"][nome]
            news = team_news(bd, 8 if lg == "Serie A" else 5)
            tot = sum(len(v or []) for v in (bd.get("colonne") or {}).values())
            out.append('<section class="sb" data-league="' + esc(lg) + '" data-team="' + esc(nome) + '"><h3>' + T.link_name(nome) + ' <a class="sbsel" href="/board.html?team=' + quote(nome) + '">solo ' + esc(nome) + " →</a></h3>")
            if news:
                out.append('<ul class="news">' + "".join(news_li(st, it) for st, it in news) + "</ul>")
                if tot > len(news):
                    out.append('<p class="small"><a href="' + T.url(nome) + '">Tutte le ' + str(tot) + " notizie, la classifica e la rosa →</a></p>")
            else:
                out.append('<p class="small">Nessuna notizia nelle ultime ore · <a href="' + T.url(nome) + '">pagina ' + esc(nome) + "</a></p>")
            out.append("</section>")
    html_ = "".join(out)
    inject(os.path.join(ROOT, "board.html"), {"board": html_, "upd": esc(fdate_it(upd, True))})
    return lm.touch("/board.html", html_)

def render_campionati_hub(D, T, lm):
    upd = D["comp"].get("aggiornato") or ""
    comps = [c for c in D["comp"].get("competizioni", []) if c["code"] in COMP_BY_CODE]
    comps_html = "".join('<a class="cb' + (" on" if c["code"] == "SA" else "") + '" href="/campionati/' + COMP_BY_CODE[c["code"]]["slug"] + '.html">' +
                         (('<img src="' + esc(c.get("emblem")) + '" alt="">') if c.get("emblem") else "") + esc(COMP_BY_CODE[c["code"]]["nome"]) + "</a>" for c in comps)
    out = []
    for c in comps:
        meta = COMP_BY_CODE[c["code"]]; g = str(c.get("giornata") or "")
        out.append('<section class="cs" id="c-' + c["code"] + '"><h2><a href="/campionati/' + meta["slug"] + '.html">' + esc(meta["nome"]) + "</a> · giornata " + g + "</h2>")
        if c.get("classifica"):
            for tbl in c["classifica"]:
                out.append(table_html(T, c, tbl))
        else:
            out.append('<p class="legend">Classifica non ancora disponibile: la competizione non è iniziata.</p>')
        ms = (c.get("giornate") or {}).get(g) or []
        if ms:
            out.append('<div class="card"><h2>Giornata ' + g + '</h2><div class="fixtures">' + "".join(match_row(T, m) for m in ms) + "</div></div>")
        if c.get("marcatori"):
            out.append('<div class="card"><h2>Marcatori</h2><table><thead><tr><th>#</th><th class="team">Giocatore</th><th class="team">Squadra</th><th>Gol</th></tr></thead><tbody>' +
                       "".join("<tr><td>" + str(i + 1) + '</td><td class="team">' + esc(s.get("name")) + '</td><td class="team">' + T.link(s.get("team") or {}) + '</td><td class="pt">' + str(s.get("goals", 0)) + "</td></tr>"
                               for i, s in enumerate(c["marcatori"][:5])) + "</tbody></table></div>")
        out.append('<p class="legend"><a href="/campionati/' + meta["slug"] + '.html">' + esc(meta["nome"]) + ": tutte le giornate, i marcatori e le squadre →</a></p></section>")
    html_ = "".join(out)
    inject(os.path.join(ROOT, "campionati.html"), {"view": html_, "comps": comps_html, "upd": "Aggiornato " + esc(fdate_it(upd, True))})
    return lm.touch("/campionati.html", html_)

# ---------- llms.txt ----------
def render_llms(D, T):
    n = len(D["listone"].get("players") or []); mds = sorted(D["voti"].keys()); tit = D["titolari"]
    L = ["# TransferBeat", "",
         "> Giornale di calcio in italiano (articoli anche in inglese e spagnolo): notizie di Serie A, Premier League e Liga squadra per squadra, classificate per grado di concretezza (voce, anteprima, ufficiale, fatto) e con la fonte sempre citata; classifiche, risultati, calendario e marcatori di sei competizioni; FantaTB, fantacalcio gratuito con dati aperti (listone, voti statistici, titolarità).",
         "", "Chi siamo: " + SITE + "/chi-siamo.html · Fonti e affidabilità: " + SITE + "/fonti.html · Aggiornamento automatico ogni due ore; articoli scritti con l'aiuto dell'intelligenza artificiale e supervisione editoriale.",
         "", "## Sezioni", "- [Home](" + SITE + "/): apertura, notizie principali, ultim'ora, articoli",
         "- [Board live](" + SITE + "/board.html): notizie squadra per squadra, ordinate per concretezza",
         "- [Articoli](" + SITE + "/articoli/it/): recap di giornata, lunch break e focus (EN: " + SITE + "/articoli/en/, ES: " + SITE + "/articoli/es/)",
         "- [Campionati](" + SITE + "/campionati/): classifiche, risultati, calendario e marcatori", "- [Squadre](" + SITE + "/squadre/): una pagina per squadra",
         "- [FantaTB](" + SITE + "/fantatb.html): il fantacalcio gratuito; app in " + SITE + "/fanta/", "", "## Competizioni"]
    for c in D["comp"].get("competizioni", []):
        meta = COMP_BY_CODE.get(c["code"]); lead = comp_leader(c)
        if meta:
            L.append("- [" + meta["nome"] + " " + SEASON + "](" + SITE + "/campionati/" + meta["slug"] + ".html): giornata " + str(c.get("giornata") or "") +
                     ((", in testa " + (T.name_of(lead["team"]) or lead["team"].get("short") or "") + " con " + str(lead.get("pt", 0)) + " punti") if lead else ""))
    L += ["", "## Dati originali di FantaTB (citabili, licenza CC BY 4.0, anche in JSON)",
          "- [Listone " + SEASON + "](" + SITE + "/fantacalcio/listone.html): quotazioni di " + str(n) + " giocatori di Serie A (JSON: " + SITE + "/data/fanta/listone.json)"]
    for k in mds:
        L.append("- [Voti giornata " + str(k) + "](" + SITE + "/fantacalcio/voti-giornata-" + str(k) + ".html): voto statistico, bonus, fantavoto (JSON: " + SITE + "/data/fanta/voti-%02d.json)" % k)
    if tit:
        L.append("- [Probabili titolari giornata " + str(tit.get("matchday")) + "](" + SITE + "/fantacalcio/titolari.html): indice di titolarità, infortunati, squalificati")
    L += ["- [Domande frequenti sul fantacalcio FantaTB](" + SITE + "/fantacalcio/)", "", "## Squadre"]
    for lg in LEAGUE_ORDER:
        L.append("- " + LEAGUE_LABEL.get(lg, lg) + ": " + ", ".join("[" + t["nome"] + "](" + SITE + T.url(t["nome"]) + ")" for t in T.list if t.get("league") == lg))
    L += ["", "## Condizioni d'uso",
          "- Le notizie sono aggregate da fonti pubbliche e rimandano sempre alla testata originale: citare la fonte originale insieme a TransferBeat.",
          "- Classifiche e risultati: dati football-data.org. Voti e quotazioni FantaTB: elaborazione originale di TransferBeat su dati API-Football, riutilizzabili citando TransferBeat con un link.",
          "- Schede giocatore: " + SITE + "/giocatori/ (una pagina per ogni giocatore di Serie A: statistiche stagione scorsa e in corso, per 90 minuti, carriera, voti FantaTB). Statistiche di squadra con grafici nelle pagine squadra. Dati API-Football, elaborazione TransferBeat.",
          "- Sitemap: " + SITE + "/sitemap.xml", ""]
    save_text(os.path.join(ROOT, "llms.txt"), "\n".join(L))

def main():
    D = load_all(); T = Teams(D); lm = LastMod()
    if not T.list:
        raise SystemExit("render_site: teams.json vuoto")
    if ((D["stats"].get("players") or {}).get("players")):
        D["pctx"] = RS.build_ctx(D, D["stats"], T)      # URL delle schede, voti per giocatore, riferimenti di ruolo
    missing = RS.unmapped_teams(D["stats"], T.api)
    if missing:
        print("render_site: squadre API-Football senza pagina squadra:", ", ".join(missing))
    pages = {"pagine": [], "squadre": [], "campionati": [], "fanta": [], "giocatori": []}
    def out(rel_file, url, html_, group):
        save_text(os.path.join(ROOT, rel_file), html_)
        pages[group].append((SITE + url, lm.touch(url, html_)))
    if D["home"]:
        pages["pagine"].append((SITE + "/", render_home(D, T, lm)))
    if D["board_sq"]:
        pages["pagine"].append((SITE + "/board.html", render_board(D, T, lm)))
    if D["comp"].get("competizioni"):
        pages["pagine"].append((SITE + "/campionati.html", render_campionati_hub(D, T, lm)))
    out("chi-siamo.html", "/chi-siamo.html", render_chi_siamo(), "pagine")
    for url, fn in (("/fonti.html", "fonti.html"), ("/fantatb.html", "fantatb.html"), ("/mondiali.html", "mondiali.html"), ("/fanta/", "fanta/index.html")):
        p = os.path.join(ROOT, fn)
        if os.path.exists(p):
            pages["pagine"].append((SITE + url, lm.touch(url, read_text(p))))
    for t in T.list:
        out(T.url(t["nome"]).lstrip("/"), T.url(t["nome"]), render_team(D, T, t), "squadre")
    out("squadre/index.html", "/squadre/", render_squadre_index(D, T), "squadre")
    for c in D["comp"].get("competizioni", []):
        if c["code"] in COMP_BY_CODE:
            out("campionati/" + COMP_BY_CODE[c["code"]]["slug"] + ".html", "/campionati/" + COMP_BY_CODE[c["code"]]["slug"] + ".html", render_comp(D, T, c), "campionati")
    if D["comp"].get("competizioni"):
        out("campionati/index.html", "/campionati/", render_comp_index(D, T), "campionati")
    if D["listone"].get("players"):
        out("fantacalcio/listone.html", "/fantacalcio/listone.html", render_listone(D, T), "fanta")
        for md, V in sorted(D["voti"].items()):
            out("fantacalcio/voti-giornata-%d.html" % md, "/fantacalcio/voti-giornata-%d.html" % md, render_voti(D, T, md, V), "fanta")
        if D["titolari"]:
            out("fantacalcio/titolari.html", "/fantacalcio/titolari.html", render_titolari(D, T), "fanta")
        out("fantacalcio/index.html", "/fantacalcio/", render_fanta_index(D, T), "fanta")
    if D.get("pctx"):
        written = set()
        for pid, p in D["pctx"]["P"].items():
            u = D["pctx"]["urls"][int(pid)]
            out(u.lstrip("/"), u, RS.render_player(D, D["stats"], T, p, D["pctx"]), "giocatori")
            written.add(os.path.basename(u))
        out("giocatori/index.html", "/giocatori/", RS.render_players_index(D, D["stats"], T, D["pctx"]), "giocatori")
        gdir = os.path.join(ROOT, "giocatori")
        stale = [f for f in os.listdir(gdir) if f.endswith(".html") and f != "index.html" and f not in written]
        for f in stale:   # schede di giocatori rinominati o usciti dal feed: via, altrimenti restano pagine orfane
            os.remove(os.path.join(gdir, f))
        print("render_site: %d schede giocatore%s" % (len(D["pctx"]["P"]), (", %d pagine vecchie rimosse" % len(stale)) if stale else ""))
    render_llms(D, T)
    for group, entries in pages.items():
        if entries:
            write_urlset(os.path.join(ROOT, "sitemap-" + group + ".xml"), entries)
    if not os.path.exists(os.path.join(ROOT, "sitemap-articoli.xml")) and D["arts"]:   # normalmente la scrive render_articles.py
        write_urlset(os.path.join(ROOT, "sitemap-articoli.xml"), [(SITE + "/articoli/" + l + "/" + a["slug"] + ".html", date_only(a.get("updated"))) for l in ("it", "en", "es") for a in D["arts"]])
    names = write_sitemap_index(ROOT)
    lm.save()
    print("render_site OK: " + ", ".join("%s %d" % (g, len(e)) for g, e in pages.items()) + " · sitemap: " + ", ".join(names))

# ---------- chi siamo (entita': kb/SEO.md §3.5). Nome confermato il 2026-09-03, LinkedIn in sameAs; email di contatto ancora da aggiungere. ----------
def render_chi_siamo():
    canon = SITE + "/chi-siamo.html"
    a = AUTHOR
    b = ["<h1>Chi siamo: TransferBeat, il giornale del calcio fatto di fonti e dati</h1>",
         '<div class="sub">Online da giugno 2026 · notizie, classifiche, articoli e fantacalcio · <a href="/fonti.html">come scegliamo le fonti</a></div>',
         "<h2>Cos’è TransferBeat</h2>",
         "<p>TransferBeat è un sito di calcio in italiano, con articoli anche in inglese e spagnolo. Segue squadra per squadra la Serie A, la Premier League e la Liga e pubblica "
         "classifiche, risultati, calendario e marcatori di sei competizioni. Ogni notizia porta con sé due informazioni che altrove mancano: <b>quanto è concreta</b> "
         "(voce, anteprima, ufficiale o fatto) e <b>quanto è affidabile la fonte</b> che l’ha data. Il link rimanda sempre alla testata originale.</p>",
         "<p>Dal settembre 2026 TransferBeat pubblica anche <a href=\"/fantatb.html\">FantaTB</a>, un fantacalcio gratuito con leghe private, asta live e voti statistici, e mette a disposizione di "
         "tutti i suoi dati originali: <a href=\"/fantacalcio/listone.html\">listone</a>, <a href=\"/fantacalcio/\">voti e probabili titolari</a>, con formula dichiarata e licenza aperta.</p>",
         "<h2>Chi lo fa</h2>",
         "<p><b>" + esc(a["name"]) + "</b>, " + esc(a["jobTitle"]).lower() + ". Ha ideato TransferBeat nel 2026 e ne cura la linea editoriale, la scelta delle fonti e i criteri di classificazione delle notizie. Profilo: <a href=\"" + esc(a["sameAs"][0]) + "\" rel=\"me noopener\" target=\"_blank\">LinkedIn</a>.</p>",
         "<h2>Come produciamo le notizie</h2>",
         "<p><b>Raccolta automatica, fonti dichiarate.</b> Un sistema legge ogni due ore le testate di calcio (Google News per ogni squadra, i feed RSS delle testate e i canali "
         "degli esperti di mercato) e classifica ogni titolo con regole pubbliche in quattro gradi di concretezza. A ogni testata è assegnato a mano un livello di affidabilità, "
         "spiegato nella pagina <a href=\"/fonti.html\">Fonti</a>. Non riscriviamo le notizie altrui: le ordiniamo, le pesiamo e le linkiamo.</p>",
         "<p><b>Articoli con l’aiuto dell’intelligenza artificiale, sotto supervisione editoriale.</b> I recap di giornata, i lunch break e i focus sono scritti a partire dalle notizie "
         "classificate e dai dati ufficiali di classifiche e risultati (football-data.org), con strumenti di intelligenza artificiale e con la revisione della redazione. "
         "La regola è semplice: i risultati vengono solo dai dati, le voci sono chiamate voci, meglio corto che inventato. Ogni articolo cita le sue fonti.</p>",
         "<p><b>Dati originali, formule pubbliche.</b> Le quotazioni, i voti e l’indice di titolarità di FantaTB sono calcolati da noi con formule dichiarate sulle statistiche reali "
         "delle partite (API-Football). Non sono i voti dei quotidiani e non lo pretendono di essere.</p>",
         "<h2>Cosa non facciamo</h2>",
         "<p>Non copiamo articoli, non pubblichiamo voci senza fonte, non vendiamo funzioni a pagamento, non usiamo dati personali oltre l’email necessaria per giocare a FantaTB. "
         "Se trovi un errore, una fonte classificata male o una notizia da correggere, segnalacelo: la classificazione migliora anche così.</p>",
         '<p class="small">TransferBeat non è affiliato a Fantacalcio®, alle leghe o ai club citati. I marchi appartengono ai rispettivi proprietari.</p>']
    person = {"@type": "Person", "name": a["name"], "url": canon, "jobTitle": a["jobTitle"], "sameAs": a.get("sameAs", []), "worksFor": ORG}
    ld = [{"@context": "https://schema.org", "@type": "AboutPage", "name": "Chi siamo", "url": canon, "about": ORG, "inLanguage": "it"},
          dict({"@context": "https://schema.org"}, **ORG), dict({"@context": "https://schema.org"}, **person)]
    return page("Chi siamo: come nasce TransferBeat, il giornale del calcio", "Chi fa TransferBeat e come lavora: notizie raccolte automaticamente da fonti dichiarate e ordinate per concretezza, articoli con l’aiuto dell’intelligenza artificiale e supervisione editoriale, dati originali di FantaTB con formule pubbliche.",
                canon, "".join(b), crumbs=[("Home", SITE + "/"), ("Chi siamo", canon)], ld=ld)

if __name__ == "__main__":
    main()
