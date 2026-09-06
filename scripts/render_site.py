#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - render_site.py: le pagine statiche per il posizionamento (kb/SEO.md §3, punti 1-3-4-6).
Genera, in italiano, tutte sul guscio unico di site_common (testata, barra di sezione, breadcrumb, footer):
- iniezione statica nelle hub index.html, board.html, campionati.html (fra i marcatori <!--static:NOME--> ... <!--/static:NOME-->)
  e guscio nelle cinque pagine a mano (index, board, campionati, fonti, mondiali) fra i marcatori <!--shell:NOME-->;
- squadre/<slug>.html per ogni squadra di data/teams.json + squadre/index.html;
- campionati/<slug>.html per le 6 competizioni di data/competizioni.json + campionati/index.html;
- fantacalcio/index.html (hub), listone.html, voti.html (ultima giornata) + voti-giornata-N.html (archivio; per l'ultima giornata una copia
  con canonical su voti.html, fuori sitemap, perche' la URL e' gia' linkata), titolari.html
  (infortunati e squalificati), probabili (render_probabili), schede giocatore (render_stats), landing e pagine extra se i moduli esistono;
- llms.txt, robots.txt, sitemap-pagine/squadre/campionati/fanta/giocatori.xml e l'indice sitemap.xml (lastmod veri: data/lastmod.json).
Uso: python scripts/render_site.py            (in update.yml DOPO build.py e competizioni.py, PRIMA del commit)
     python scripts/render_site.py --check    (solo controlli, non scrive)
Legge SOLO i JSON gia' presenti: nessuna rete, nessuna chiave. Non tocca data/<lang>/*.json."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_common import (esct, ROOT, DATA, SITE, SEASON, AUTHOR, ORG, COMPS, COMP_BY_CODE, COMP_BY_LEAGUE, LEAGUE_LABEL, LEAGUE_ORDER, punti,
                         ZONES, FD_ALIAS, FANTA_ALIAS, STATE_LABEL, STATE_ORDER, esc, slugify, norm, load_json, save_text, read_text,
                         fdate_it, date_only, today_iso, dots, page, ld_script, breadcrumb_ld, LastMod, write_urlset, write_sitemap_index, badge,
                         FANTA_BAR, CAMP_BAR, FANTA_CRUMB, CTA, apply_shell, door, ICON_CHEVRON, to_rome, MESI, parse_iso)
import render_stats as RS   # statistiche squadra con grafici e schede giocatore (data/stats/*.json)
import render_probabili as RP   # probabili formazioni con i due mezzi campi (data/fanta/probabili-NN.json)
# Moduli nuovi con contratto fisso: se mancano si va avanti senza (nessuna eccezione).
try:
    import render_landing as RL     # render(D, T) -> HTML di /fantatb.html
except ImportError:
    RL = None
    print("render_site: modulo render_landing assente, fantatb.html resta com'e'")
try:
    import render_fanta_extra as RX  # render_all(D, T) -> [(rel_file, url, html)] per regolamento, guida all'asta, consigli
except ImportError:
    RX = None
    print("render_site: modulo render_fanta_extra assente, niente regolamento/guida")

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
         "voti": {}, "titolari": None, "titolari_all": {}, "probabili": {}, "stats": RS.load_stats(), "pctx": None}
    fd = os.path.join(DATA, "fanta")
    if os.path.isdir(fd):
        for fn in sorted(os.listdir(fd)):
            m = re.match(r"voti-(\d+)\.json$", fn)
            if m:
                v = load_json(os.path.join(fd, fn))
                if v and v.get("ratings"):
                    D["voti"][int(m.group(1))] = v
            m = re.match(r"probabili-(\d+)\.json$", fn)
            if m:
                pr = load_json(os.path.join(fd, fn))
                if pr and pr.get("fixtures") and pr.get("teams"):
                    D["probabili"][int(m.group(1))] = pr
            m = re.match(r"titolari-(\d+)\.json$", fn)
            if m:
                t = load_json(os.path.join(fd, fn))
                if t and t.get("status"):
                    D["titolari_all"][int(m.group(1))] = t   # tutte le giornate: servono per "dal" e "chi rientra"
                    if D["titolari"] is None or (t.get("matchday") or 0) > (D["titolari"].get("matchday") or 0):
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

# ---------- pezzi riutilizzabili ----------
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

def fdate_long(iso, with_time=True):
    """'giovedì 11 settembre alle 20:45' (ora italiana) per le strisce di stato."""
    d = parse_iso(iso)
    if not d:
        return ""
    r = to_rome(d)
    s = GIORNI[r.weekday()] + " " + str(r.day) + " " + MESI[r.month - 1]
    return s + " alle " + r.strftime("%H:%M") if with_time else s

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
    h = ['<div class="card">' + ("<h3>" + caption + "</h3>" if caption else "") + '<div class="tscroll"><table><thead><tr>'
         '<th class="num">#</th><th class="team">Squadra</th><th class="num">PG</th><th class="num">V</th><th class="num">N</th><th class="num">P</th>'
         '<th class="num">GF</th><th class="num">GS</th><th class="num">DR</th><th class="num">Pt</th>' +
         ("<th>Forma</th>" if has_form else "") + "</tr></thead><tbody>"]
    for r in rows:
        nm = T.name_of(r["team"])
        cls = (zone_class(r.get("pos") or 0, n, c["code"]) + (" me" if me and nm == me else "")).strip()
        dr = r.get("dr") or 0
        h.append('<tr class="' + cls + '"><td class="pos num">' + str(r.get("pos")) + '</td><td class="team">' + T.link(r["team"]) + '</td><td class="num">' +
                 str(r.get("pg", 0)) + '</td><td class="num">' + str(r.get("v", 0)) + '</td><td class="num">' + str(r.get("n", 0)) + '</td><td class="num">' + str(r.get("p", 0)) + '</td><td class="num">' +
                 str(r.get("gf", 0)) + '</td><td class="num">' + str(r.get("gs", 0)) + '</td><td class="num">' + ("+" if dr > 0 else "") + str(dr) + '</td><td class="pt num">' + str(r.get("pt", 0)) + "</td>" +
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

# ---------- Serie A: partite di una giornata (football-data) e indice squadra -> partita ----------
def md_matches(D, md):
    """Partite di Serie A della giornata md da data/competizioni.json (ordinate per data)."""
    for c in D["comp"].get("competizioni", []):
        if c.get("code") == "SA":
            ms = (c.get("giornate") or {}).get(str(md)) or []
            return sorted(ms, key=lambda m: m.get("utc") or "")
    return []

def md_start(D, md):
    ms = md_matches(D, md)
    return ms[0].get("utc") if ms else None

def team_match_index(T, ms):
    """{nome squadra di teams.json: partita} per una lista di partite football-data."""
    out = {}
    for m in ms:
        for side in ("home", "away"):
            n = T.name_of(m[side])
            if n:
                out[n] = m
    return out

# ---------- pagine squadra ----------
GRUPPI = {"done": "Fatti", "conf": "Ufficiali", "obj": "Anteprime", "rumor": "Voci e analisi"}

def team_desc(nome, t, T, has_st=False):
    pos = ""
    if nome in T.row_of:
        c, r, n, g = T.row_of[nome]
        pos = ", " + str(r.get("pos")) + "ª in " + COMP_BY_CODE[c["code"]]["nome"] + " con " + punti(r.get("pt", 0))
    st = "statistiche con grafici, " if has_st else ""
    return nome + pos + ": calciomercato e notizie con fonte e concretezza, " + st + "classifica, partite, rosa e articoli."

def team_title(nome):
    """'Inter: calciomercato, notizie e classifica' se sta nei 60 caratteri, altrimenti la forma corta (stesso schema per tutte)."""
    t = nome + ": calciomercato, notizie e classifica"
    return t if len(t) <= 60 else nome + ": notizie e classifica"

def team_fanta_card(D, T, nome):
    """Card 'Fantacalcio <squadra>' per le squadre di Serie A nel listone: probabile formazione (ancora #squadra-<slug>),
    infortunati e squalificati, listone, voti, i cinque più quotati e gli indisponibili con link alle schede."""
    ps = [p for p in D["listone"].get("players") or [] if T.fanta_name(p.get("team") or "") == nome]
    if not ps:
        return ""
    pctx = D.get("pctx"); slug = T.slug[nome]
    md_p = max(D["probabili"]) if D.get("probabili") else None
    tit = D.get("titolari") or {}
    st = {s["player_id"]: s for s in tit.get("status") or []}
    top = sorted(ps, key=lambda p: (-(p.get("price") or 0), p.get("name") or ""))[:5]
    inj = sorted([(p, st[p["id"]]) for p in ps if (st.get(p["id"]) or {}).get("injury")], key=lambda x: x[0]["name"])
    links = []
    if md_p:
        links.append('<a href="/fantacalcio/probabili-formazioni.html#squadra-' + slug + '">Probabile formazione giornata ' + str(md_p) + "</a>")
    links.append('<a href="/fantacalcio/titolari.html">Infortunati e squalificati</a>')
    links.append('<a href="/fantacalcio/listone.html">Listone e quotazioni</a>')
    if D.get("voti"):
        links.append('<a href="/fantacalcio/voti.html">Voti dell\'ultima giornata</a>')
    art = RS.ART.get(nome, "di " + nome)
    b = ['<h2 id="fantacalcio">Fantacalcio ' + esc(nome) + '</h2><div class="card"><div class="in">',
         "<p>" + str(len(ps)) + " giocatori " + esc(art) + " sono nel listone FantaTB con quotazione, indice di titolarità e voto statistico dopo ogni giornata: "
         "ogni nome apre la scheda del giocatore.</p>",
         '<div class="chips">' + "".join(links) + "</div>",
         "<h3>I cinque più quotati</h3><ul class=\"plist\">" + "".join(
             "<li>" + rb(p.get("role")) + " " + RS.plink(pctx, p["id"], p["name"]) + ' <span class="small">' + str(p.get("price") or 0) + " crediti</span></li>" for p in top) + "</ul>"]
    if tit.get("matchday"):
        if inj:
            b.append("<h3>Indisponibili per la giornata " + str(tit["matchday"]) + " (" + str(len(inj)) + ')</h3><ul class="plist">' + "".join(
                "<li>" + rb(p.get("role")) + " " + RS.plink(pctx, p["id"], p["name"]) + ' <span class="small">' + esc(s.get("injury")) +
                ((" · rientro " + esc(fdate_it(s["back_at"] + "T12:00:00Z"))) if s.get("back_at") else "") + "</span></li>" for p, s in inj) + "</ul>")
        else:
            b.append('<p class="small">Nessun indisponibile segnalato per la giornata ' + str(tit["matchday"]) + ".</p>")
    b.append("</div></div>")
    return "".join(b)

def render_team(D, T, t):
    nome = t["nome"]; canon = SITE + T.url(nome); lg = t.get("league", "")
    comp_meta = COMP_BY_LEAGUE.get(lg)
    bd = D["board_sq"].get(nome) or {}
    upd = D["board"].get("aggiornato") or ""
    b = ["<h1>" + badge(t, 44) + esc(nome) + "</h1>"]
    b.append('<div class="sub">' + esc(LEAGUE_LABEL.get(lg, lg)) + " · calciomercato, notizie, classifica, calendario e rosa · aggiornato <time>" + esc(fdate_it(upd, True)) + "</time> · "
             '<a href="/board.html?team=' + quote(nome) + '">apri nelle notizie</a>' +
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
    b.append(team_fanta_card(D, T, nome))
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
    return page(team_title(nome), team_desc(nome, t, T, has_st), canon, "".join(b), crumbs=crumbs, ld=[ld], here="Squadre")

def render_squadre_index(D, T):
    canon = SITE + "/squadre/"
    b = ["<h1>Squadre: calciomercato, notizie, classifiche e rose</h1>",
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
    return page("Squadre di Serie A, Premier League e Liga",
                "Le " + str(len(T.list)) + " squadre seguite da TransferBeat, una pagina ciascuna: calciomercato e notizie del giorno con fonti e concretezza, classifica, prossime partite, rosa e articoli.",
                canon, "".join(b), crumbs=[("Home", SITE + "/"), ("Squadre", canon)], ld=[ld], here="Squadre")

# ---------- pagine competizione ----------
def comp_title(meta, c):
    if c.get("classifica"):
        return "Classifica " + meta["nome"] + " " + SEASON + " e risultati"
    return meta["nome"] + " " + SEASON + ": calendario e risultati"

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
        b.append('<h2>Marcatori</h2><div class="card"><div class="tscroll"><table><thead><tr><th class="num">#</th><th class="l">Giocatore</th><th class="l">Squadra</th><th class="num">Gol</th><th class="num">Rig.</th><th class="num">Assist</th></tr></thead><tbody>')
        for i, s in enumerate(c["marcatori"]):
            b.append('<tr><td class="num">' + str(i + 1) + '</td><td class="l">' + esc(s.get("name")) + '</td><td class="l">' + T.link(s.get("team") or {}) + '</td><td class="pt num">' +
                     str(s.get("goals", 0)) + '</td><td class="num">' + str(s.get("pen", 0)) + '</td><td class="num">' + str(s.get("assists", 0)) + "</td></tr>")
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
        lead_txt = "classifica con " + (T.name_of(lead["team"]) or lead["team"].get("short") or "") + " in testa a " + punti(lead.get("pt", 0)) + ", "
    desc = meta["nome"] + " " + SEASON + ": " + lead_txt + "risultati e calendario giornata per giornata, marcatori. Ogni due ore."
    ld = [{"@context": "https://schema.org", "@type": "SportsOrganization", "name": meta["nome"], "sport": "Calcio", "url": canon}]
    if events:
        ld.append({"@context": "https://schema.org", "@type": "ItemList", "name": meta["nome"] + " " + SEASON + ": partite",
                   "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": e} for i, e in enumerate(events[:24])]})
    crumbs = [("Home", SITE + "/"), ("Campionati", SITE + "/campionati/"), (meta["nome"], canon)]
    return page(comp_title(meta, c), desc, canon, "".join(b), crumbs=crumbs, ld=ld, here="Campionati", bar=CAMP_BAR, bar_here=meta["nome"])

def render_comp_index(D, T):
    canon = SITE + "/campionati/"
    b = ["<h1>Campionati e coppe " + SEASON + ": classifiche, risultati e marcatori</h1>",
         '<div class="sub">Sei competizioni con classifica, calendario giornata per giornata, risultati e marcatori, aggiornati ogni due ore. Versione interattiva in <a href="/campionati.html">Campionati live</a>.</div>']
    for c in D["comp"].get("competizioni", []):
        meta = COMP_BY_CODE.get(c["code"]); lead = comp_leader(c)
        if not meta:
            continue
        b.append('<div class="card"><h3><a href="/campionati/' + meta["slug"] + '.html">' + esc(meta["nome"]) + '</a></h3><div class="in">Giornata ' + str(c.get("giornata") or "") + " · " +
                 (("in testa " + T.link(lead["team"]) + " con " + str(lead.get("pt", 0)) + " punti") if lead else "fase a campionato non ancora iniziata") +
                 ' · <a href="/campionati/' + meta["slug"] + '.html">classifica, risultati e marcatori →</a></div></div>')
    b.append(door("Archivio Mondiale 2026", "Risultati, tabellone e marcatori del Mondiale", "/mondiali.html"))
    return page("Campionati e coppe " + SEASON + ": classifiche",
                "Serie A, Champions League, Premier League, Liga, Bundesliga e Ligue 1: classifica, risultati, calendario e marcatori, aggiornati ogni due ore.",
                canon, "".join(b), crumbs=[("Home", SITE + "/"), ("Campionati", canon)], here="Campionati", bar=CAMP_BAR, bar_here="Tutte")

# ---------- fantacalcio: pagine dati (kb/SEO.md §3.4, formule in kb/FANTATB.md §5-7) ----------
RUOLI = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}
RUOLI_PL = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
ROLE_ANCHOR = {"P": "portieri", "D": "difensori", "C": "centrocampisti", "A": "attaccanti"}
ROLE_ORDER = {"P": 0, "D": 1, "C": 2, "A": 3}

def rb(role):
    """Badge ruolo quadrato 22px (classe .rb del guscio): <i class="rb A">A</i>."""
    r = role if role in RUOLI else ""
    return '<i class="rb' + ((" " + r) if r else "") + '">' + (r or "?") + "</i>"

def d1(v):
    """Numero con una cifra decimale e virgola (fantavoto): 14,0."""
    return ("%.1f" % v).replace(".", ",") if isinstance(v, (int, float)) else "—"

def d2(v):
    """Numero con due cifre decimali e virgola (medie): 6,50."""
    return ("%.2f" % v).replace(".", ",") if isinstance(v, (int, float)) else "—"

def dec(x):
    return ("%g" % x).replace(".", ",") if isinstance(x, (int, float)) else str(x)

def pct_html(v):
    """Percentuale di titolarità nei tre colori semantici (verde da 70, ambra da 40, rosso sotto)."""
    if v is None:
        return "—"
    v = int(v)
    return '<span class="pct ' + ("g" if v >= 70 else ("a" if v >= 40 else "r")) + '">' + str(v) + "%</span>"

def fv_cls(v):
    return "hi" if (v is not None and v >= 8) else ("lo" if (v is not None and v <= 5.5) else "")

# Icone SVG monocrome 14px per bonus e malus (colore ereditato dal chip).
_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>'
ICO = {"gol": '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="12" r="8"/></svg>',
       "assist": _SVG % '<path d="M4 12h14M13 6l6 6-6 6"/>',
       "rig_sbagliato": _SVG % '<circle cx="12" cy="12" r="8"/><path d="M9 9l6 6M15 9l-6 6"/>',
       "rig_parato": _SVG % '<circle cx="12" cy="12" r="8"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/>',
       "gol_subito": _SVG % '<path d="M6 6l12 12M18 6L6 18"/>',
       "autogol": _SVG % '<circle cx="12" cy="12" r="8"/><path d="M8 12h8"/>',
       "amm": '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="7" y="3" width="10" height="18" rx="2"/></svg>',
       "esp": '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="7" y="3" width="10" height="18" rx="2"/></svg>'}
BONUS_IT = {"gol": ("gol", "gol"), "assist": ("assist", "assist"), "rig_sbagliato": ("rigore sbagliato", "rigori sbagliati"), "rig_parato": ("rigore parato", "rigori parati"),
            "gol_subito": ("gol subito", "gol subiti"), "autogol": ("autogol", "autogol"), "amm": ("ammonizione", "ammonizioni"), "esp": ("espulsione", "espulsioni")}
BONUS_CLS = {"rig_sbagliato": "neg", "gol_subito": "neg", "autogol": "neg", "esp": "neg", "amm": "warn"}
BONUS_ORDER = ["gol", "assist", "rig_parato", "rig_sbagliato", "gol_subito", "autogol", "amm", "esp"]

def bonus_items(bonus):
    out = []
    for k in BONUS_ORDER + [x for x in (bonus or {}) if x not in BONUS_ORDER]:
        v = (bonus or {}).get(k)
        if not v:
            continue
        s, p = BONUS_IT.get(k, (k, k))
        out.append((k, v, (p if v > 1 else s) + (" ×" + str(v) if v > 1 else "")))
    return out

def bonus_txt(bonus):
    return " · ".join(lab for _, _, lab in bonus_items(bonus))

def bonus_html(bonus):
    """Chip compatti con icona SVG e testo: <span class="bn [neg|warn]">icona gol ×2</span>."""
    return "".join('<span class="bn' + ((" " + BONUS_CLS[k]) if k in BONUS_CLS else "") + '">' + ICO.get(k, "") + esc(lab) + "</span>" for k, v, lab in bonus_items(bonus))

VOTO_NOTE = ('<div class="note"><b>Come nasce il voto FantaTB.</b> Voto base = rating statistico della partita (API-Football) meno 0,8, arrotondato al mezzo punto, fra 4 e 8,5; '
             'senza rating ma con almeno 15 minuti vale 6; sotto i 15 minuti è senza voto (s.v.). Il fantavoto somma bonus e malus con i pesi di default: gol +3, assist +1, '
             'rigore sbagliato −3, rigore parato +3, gol subito (portiere) −1, autogol −2, ammonizione −0,5, espulsione −1. Sono voti statistici, calcolati da noi con formula '
             'pubblica: non coincidono con quelli dei quotidiani. Non affiliato a Fantacalcio®.</div>')

# CSS proprio delle pagine fantacalcio (in extra_head): chip bonus, righe dei voti, riga H1 con badge, contatori colorati, scheda rapida.
FANTA_CSS = """<style>
.h1row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 8px}.h1row h1{margin:0}
.bn{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:600;padding:1px 8px;border-radius:6px;background:var(--panel);color:var(--txt2);margin:1px 4px 1px 0;white-space:nowrap;line-height:1.5}
.bn.neg{color:var(--err)}.bn.warn{color:var(--warn)}
.tools .chips{margin:0}.tools .chips a{min-height:40px}.tools .hint{margin-left:auto;font-size:13px;color:var(--muted)}
table.srt td.name{font-weight:600}table.srt td .rb{vertical-align:middle}
.fv{font-weight:700}.fv.hi{color:var(--ok)}.fv.lo{color:var(--err)}
.vrows{padding:0}.vr{display:flex;align-items:center;gap:10px;padding:8px 16px;border-top:1px solid var(--line2);font-size:14px}.vr .n{flex:1;min-width:0}.vr .n span{color:var(--muted)}.vr .fv{min-width:40px;text-align:right}
.card .cf{padding:12px 16px;border-top:1px solid var(--line);font-size:13px}.card>h2 .pill{float:right;margin-top:2px}
.kpi.err{border-left:4px solid var(--err)}.kpi.warn{border-left:4px solid var(--warn)}.kpi.info{border-left:4px solid var(--violet)}.kpi.ok{border-left:4px solid var(--ok)}
.rows2{display:flex;flex-direction:column;gap:6px;margin:8px 0}.rows2 div{display:flex;justify-content:space-between;gap:8px}.rows2 span.m{color:var(--muted)}.rows2 .e{color:var(--err);font-weight:600}
.grad .lines{margin:8px 0 0;padding:0;list-style:none}.grad .lines li{padding:2px 0}
.doors3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:24px 0}.doors3 .door{margin:0;padding:16px 18px;align-items:flex-start}.doors3 .door b{font-size:18px}
@media(max-width:760px){.doors3{grid-template-columns:1fr}.tools .hint{display:none}}
</style>"""

PCARD_CSS = """<style>
.pcard{position:fixed;z-index:70;width:380px;max-width:calc(100vw - 16px);background:#fff;border:1px solid var(--line);border-radius:16px;box-shadow:0 16px 48px rgba(27,17,64,.18);font-size:13px;overflow:hidden}
.pcard .hd{display:flex;align-items:center;gap:12px;padding:12px 14px;background:var(--panel);border-left:6px solid var(--violet)}
.pcard .av{width:48px;height:48px;border-radius:50%;display:inline-grid;place-items:center;font-weight:700;font-size:16px;flex:none}
.pcard .hd b{font-size:16px}.pcard .hd .m{font-size:12px;color:var(--muted)}.pcard .hd .rb{vertical-align:middle;margin-left:4px}
.pcard .x{margin-left:auto;background:none;border:0;cursor:pointer;color:var(--muted);padding:4px;display:inline-flex;flex:none}
.pcard .g{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px 12px;padding:12px 14px}.pcard .g .l{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600}
.pcard .g b{font-size:16px;font-variant-numeric:tabular-nums}.pcard .g b.sm{font-size:13px}
.pcard .r{padding:0 14px 10px;color:var(--muted);font-size:12px}.pcard .lv{display:inline-block;background:var(--panel);color:var(--txt2);font-weight:700;padding:1px 8px;border-radius:6px;margin-left:4px;font-variant-numeric:tabular-nums}
.pcard .lv.hi{background:var(--ok-bg);color:#0b5d36}.pcard .lv.lo{background:var(--err-bg);color:#8a1f16}
.pcard .tx{padding:0 14px 12px;color:var(--txt2)}.pcard .tx.inj{color:var(--err);font-weight:600}
.pcard .ft{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-top:1px solid var(--line);font-size:13px}.pcard .ft a{font-weight:700}
</style>"""

# Ricerca, chip ruolo (.rf a[data-r]), select squadra (#t) e ordinamento (th.sort) su tutte le table.srt della pagina. Senza JS la pagina resta completa.
FILTER_JS = ("<script>(function(){var ts=[].slice.call(document.querySelectorAll('table.srt'));if(!ts.length)return;"
             "var q=document.getElementById('q'),sel=document.getElementById('t'),chips=[].slice.call(document.querySelectorAll('.rf a')),cnt=document.getElementById('cnt'),ro='';"
             "function filt(){var s=(q&&q.value||'').toLowerCase(),tm=sel&&sel.value||'',n=0;ts.forEach(function(t){var k=0;[].slice.call(t.tBodies[0].rows).forEach(function(tr){"
             "var ok=(!s||tr.textContent.toLowerCase().indexOf(s)>=0)&&(!ro||tr.getAttribute('data-r')===ro)&&(!tm||tr.getAttribute('data-t')===tm);tr.hidden=!ok;if(ok){k++;n++;}});"
             "var sec=t.closest('[data-sec]');if(sec)sec.hidden=(k===0);});if(cnt)cnt.textContent=n;}"
             "if(q)q.addEventListener('input',filt);if(sel)sel.addEventListener('change',filt);"
             "chips.forEach(function(a){a.addEventListener('click',function(e){e.preventDefault();ro=a.getAttribute('data-r')||'';chips.forEach(function(x){x.classList.toggle('on',x===a);});filt();"
             "var h=a.getAttribute('href');if(h&&h.charAt(0)==='#'&&h.length>1){var el=document.getElementById(h.slice(1));if(el&&ro)el.scrollIntoView();}});});"
             "ts.forEach(function(t){[].slice.call(t.querySelectorAll('th.sort')).forEach(function(th){th.addEventListener('click',function(){var i=th.cellIndex,tb=t.tBodies[0],rows=[].slice.call(tb.rows),"
             "num=th.getAttribute('data-n')==='1',asc=th.getAttribute('data-asc')!=='1';rows.sort(function(a,b){var x=a.cells[i].getAttribute('data-v')||a.cells[i].textContent.trim(),"
             "y=b.cells[i].getAttribute('data-v')||b.cells[i].textContent.trim();if(num){x=parseFloat(x);y=parseFloat(y);if(isNaN(x))x=-999;if(isNaN(y))y=-999;return asc?x-y:y-x;}"
             "return asc?x.localeCompare(y):y.localeCompare(x);});rows.forEach(function(x){tb.appendChild(x);});[].slice.call(t.querySelectorAll('th.sort')).forEach(function(h){h.removeAttribute('data-asc');});"
             "th.setAttribute('data-asc',asc?'1':'0');});});});})();</script>")

# Scheda rapida del listone (porting di fanta/app.js pcardHtml/pcardShow/pcardHide): al primo passaggio del mouse scarica /data/fanta/schede.json una sola volta.
PCARD_JS = ("<script>(function(){var S=null,ld=false,el=null,tm=null,cur=null,touch=window.matchMedia('(hover: none)').matches,SEAS=" + json.dumps(SEASON) + ";"
            "function esc(s){return String(s==null?'':s).replace(/[&<>\"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c];});}"
            "function num(v,d){return v==null?'—':(d==null?String(v):Number(v).toFixed(d).replace('.',','));}"
            "function pct(v){return v==null?'—':'<span class=\"pct '+(v>=70?'g':v>=40?'a':'r')+'\">'+v+'%</span>';}"
            "function dark(h){var m=/^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(h||'');if(!m)return true;var r=parseInt(m[1],16),g=parseInt(m[2],16),b=parseInt(m[3],16);return (r*299+g*587+b*114)/1000<150;}"
            "function load(cb){if(S){cb();return;}if(ld)return;ld=true;fetch('/data/fanta/schede.json').then(function(r){return r.json();}).then(function(j){S=j;cb();}).catch(function(){ld=false;});}"
            "function html(tr){var d=tr.dataset,s=(S.players||{})[d.pid]||{},col=((S.teams||{})[d.t]||['#4b1d95'])[0],ini=(d.name||'').split(' ').map(function(w){return w.charAt(0);}).join('').replace(/[^A-Za-zÀ-ž]/g,'').slice(0,2).toUpperCase();"
            "var last=(s.last||[]).map(function(x){var v=x[1];return '<span class=\"lv'+(v>=8?' hi':v<=5.5?' lo':'')+'\" title=\"Giornata '+x[0]+'\">'+num(v,1)+'</span>';}).join('');"
            "var prev=s.prev?'<div><span class=\"l\">'+esc(s.prev.lega||'Stagione scorsa')+'</span><b class=\"sm\">'+num(s.prev.pres)+' pres · '+num(s.prev.gol)+' gol · '+num(s.prev.assist)+' assist</b></div>':'';"
            "var tx=s.inj?'<div class=\"tx inj\">'+esc(s.inj)+(s.back?' · rientro previsto '+esc(s.back):'')+'</div>':(s.prev&&s.prev.rating?'<div class=\"tx\">Stagione scorsa in '+esc(s.prev.lega||'')+': '+num(s.prev.tit)+' volte titolare su '+num(s.prev.pres)+', rating medio '+num(s.prev.rating,2)+'.</div>':'');"
            "return '<div class=\"hd\" style=\"border-left-color:'+esc(col)+'\"><span class=\"av\" style=\"background:'+esc(col)+';color:'+(dark(col)?'#fff':'#1b1140')+'\">'+esc(ini)+'</span><div><b>'+esc(d.name)+'</b><i class=\"rb '+esc(d.r)+'\">'+esc(d.r)+'</i><div class=\"m\">'+esc(d.team)+(s.age?' · '+s.age+' anni':'')+(s.nat?' · '+esc(s.nat):'')+'</div></div>"
            "<button type=\"button\" class=\"x\" aria-label=\"Chiudi\"><svg width=\"16\" height=\"16\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\"><path d=\"M6 6l12 12M18 6L6 18\"/></svg></button></div>"
            "<div class=\"g\"><div><span class=\"l\">Quot.</span><b>'+esc(d.price)+'</b></div>'+(d.fvm?'<div><span class=\"l\">FVM</span><b>'+esc(d.fvm)+'</b></div>':'')+'<div><span class=\"l\">Titolare</span><b>'+pct(s.tit)+'</b></div>"
            "<div><span class=\"l\">MV · FMV</span><b>'+num(s.mv,2)+' · '+num(s.fmv,2)+'</b></div><div><span class=\"l\">Pres · Gol · Assist</span><b>'+num(s.pres)+' · '+num(s.gol)+' · '+num(s.assist)+'</b></div>'+prev+'</div>'+"
            "(last?'<div class=\"r\">Ultimi fantavoti '+last+'</div>':'')+tx+'<div class=\"ft\">'+(s.url?'<a href=\"'+esc(s.url)+'\">Scheda completa →</a>':'<span>Scheda non disponibile</span>')+'<span class=\"small\">Serie A '+esc(SEAS)+' · dati FantaTB</span></div>';}"
            "function box(){if(!el){el=document.createElement('div');el.className='pcard';el.hidden=true;document.body.appendChild(el);el.addEventListener('mouseenter',function(){clearTimeout(tm);});el.addEventListener('mouseleave',function(){hide(180);});"
            "el.addEventListener('click',function(e){if(e.target.closest('.x'))hide(0);});}return el;}"
            "function show(tr,anchor){load(function(){var b=box();cur=tr.dataset.pid;b.innerHTML=html(tr);b.hidden=false;var r=anchor.getBoundingClientRect(),w=Math.min(380,window.innerWidth-16),h=b.offsetHeight||260;"
            "var left=Math.min(Math.max(8,r.left),window.innerWidth-w-8),top=r.bottom+6;if(top+h>window.innerHeight-8)top=Math.max(8,r.top-h-6);b.style.width=w+'px';b.style.left=left+'px';b.style.top=top+'px';});}"
            "function hide(d){clearTimeout(tm);tm=setTimeout(function(){if(el)el.hidden=true;cur=null;},d||0);}"
            "document.addEventListener('mouseover',function(e){if(touch)return;var tr=e.target.closest('tr[data-pid]');if(!tr)return;clearTimeout(tm);if(tr.dataset.pid===cur)return;tm=setTimeout(function(){show(tr,tr.querySelector('td.name')||tr);},260);});"
            "document.addEventListener('mouseout',function(e){if(touch)return;var tr=e.target.closest('tr[data-pid]');if(tr&&!(e.relatedTarget&&(e.relatedTarget.closest('.pcard')||e.relatedTarget.closest('tr[data-pid]')===tr)))hide(220);});"
            "document.addEventListener('click',function(e){var tr=e.target.closest('tr[data-pid]'),a=e.target.closest('td.name a');if(touch&&a&&tr&&!e.target.closest('.pcard')){e.preventDefault();if(cur===tr.dataset.pid)hide(0);else show(tr,a);return;}if(!e.target.closest('.pcard')&&!tr)hide(0);});"
            "document.addEventListener('keydown',function(e){if(e.key==='Escape')hide(0);});})();</script>")

def role_chips(active="", anchors=None):
    """Chip Tutti/P/D/C/A (.chips.rf): senza JS puntano alle ancore, con JS filtrano le tabelle."""
    anchors = anchors or {}
    items = [("", "Tutti", "#tabella")] + [(r, r, "#" + ROLE_ANCHOR[r]) for r in "PDCA"]
    return '<div class="chips rf" role="group" aria-label="Ruolo">' + "".join(
        '<a href="%s" data-r="%s"%s title="%s">%s</a>' % (esc(anchors.get(r, h)), r, ' class="on"' if r == active else "", esc(RUOLI_PL.get(r, "Tutti i ruoli")), lab)
        for r, lab, h in items) + "</div>"

def team_select(T, teams):
    """<select id="t"> con le squadre del listone (valore = nome API-Football, etichetta = nome del sito)."""
    opts = sorted(((T.fanta_name(t) or t), t) for t in set(teams))
    return '<select id="t" aria-label="Squadra"><option value="">Tutte le squadre</option>' + "".join('<option value="%s">%s</option>' % (esc(v), esc(lab)) for lab, v in opts) + "</select>"

SEARCH_ICON = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
               '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/></svg>')

def dataset_ld(name, desc, url, json_url, updated, keywords):
    return {"@context": "https://schema.org", "@type": "Dataset", "name": name, "description": desc, "url": url, "inLanguage": "it",
            "keywords": keywords, "creator": ORG, "publisher": ORG, "dateModified": date_only(updated), "license": "https://creativecommons.org/licenses/by/4.0/",
            "isAccessibleForFree": True, "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": json_url}]}

def fanta_team_link(T, team):
    n = T.fanta_name(team or "")
    return ('<a href="' + T.url(n) + '">' + esc(n) + "</a>") if n else esc(team)

def fanta_team_name(T, team):
    return T.fanta_name(team or "") or (team or "")

def fanta_page(title, desc, canon, body, crumbs, ld, bar_here, extra_head=""):
    """page() del ramo fantacalcio: voce Fantacalcio attiva, barra di sezione, CSS delle pagine dati, nessun ribbon."""
    return page(title, desc, canon, body, crumbs=crumbs, ld=ld, here="Fantacalcio", bar=FANTA_BAR, bar_here=bar_here, extra_head=FANTA_CSS + extra_head)

# ---------- listone ----------
def render_listone(D, T):
    L = D["listone"]; ps = sorted(L.get("players") or [], key=lambda p: (-(p.get("price") or 0), p.get("name") or ""))
    canon = SITE + "/fantacalcio/listone.html"; upd = L.get("updated") or ""; pctx = D.get("pctx")
    n = len(ps)
    top5 = ps[:5]
    top = ", ".join(RS.plink(pctx, p["id"], p["name"]) + " " + str(p["price"]) for p in top5)
    top_txt = ", ".join(p["name"] + " " + str(p["price"]) for p in top5)
    by_role = {r: [p for p in ps if p.get("role") == r] for r in "PDCA"}
    has_fvm = any(p.get("fvm") is not None for p in ps)   # listone.json oggi non ha il fantavalore: la colonna FVM esce solo se almeno un giocatore ce l'ha
    def num_td(v, txt=None, cls="num"):
        return '<td class="' + cls + '" data-v="' + (str(v) if v is not None else "-1") + '">' + (txt if txt is not None else (dec(v) if v is not None else "—")) + "</td>"
    b = ["<h1>Listone fantacalcio " + SEASON + ": quotazioni di " + str(n) + " giocatori</h1>",
         '<div class="sub">' + str(n) + " giocatori di Serie A quotati da FantaTB, aggiornati il <time>" + esc(fdate_it(upd)) + "</time>. I più cari: " + top +
         ". Passa il mouse su un nome (o toccalo) per la scheda rapida; il clic apre la scheda completa.</div>",
         '<div class="tools"><label class="small" for="q" hidden>Cerca</label><input id="q" type="search" placeholder="Cerca giocatore o squadra" aria-label="Cerca giocatore o squadra">' +
         role_chips() + team_select(T, [p.get("team") for p in ps]) + '<span class="hint">Ordina cliccando le intestazioni · <span id="cnt">' + str(n) + "</span> giocatori</span></div>",
         '<div id="tabella"></div>']
    for r in "PDCA":
        lst = by_role[r]
        if not lst:
            continue
        b.append('<section data-sec="' + r + '"><h2 id="' + ROLE_ANCHOR[r] + '">' + RUOLI_PL[r] + " (" + str(len(lst)) + ')</h2><div class="card"><div class="tscroll"><table class="srt"><thead><tr>'
                 '<th class="sort" title="Ruolo">R</th><th class="sort">Giocatore</th><th class="sort">Squadra</th><th class="sort num" data-n="1" title="Quotazione FantaTB in crediti">Quot.</th>' +
                 ('<th class="sort num" data-n="1" title="Fantavalore di mercato">FVM</th>' if has_fvm else "") + '<th class="sort num" data-n="1" title="Media voto FantaTB">MV</th><th class="sort num" data-n="1" title="Fantamedia: media dei fantavoti">FMV</th>'
                 '<th class="sort num" data-n="1" title="Indice di titolarità per la prossima giornata">Titolare</th><th class="sort num" data-n="1" title="Presenze in Serie A">Pres.</th>'
                 '<th class="sort num" data-n="1">Gol</th><th class="sort num" data-n="1">Assist</th></tr></thead><tbody>')
        for p in lst:
            s = RS.summary_of(pctx, p["id"]) or {}
            tit = s.get("tit"); fvm = p.get("fvm")
            b.append('<tr data-pid="' + str(p["id"]) + '" data-r="' + esc(r) + '" data-t="' + esc(p.get("team")) + '" data-name="' + esc(p.get("name")) + '" data-price="' + str(p.get("price") or 0) +
                     '" data-fvm="' + (str(fvm) if fvm is not None else "") + '"><td data-v="' + str(ROLE_ORDER.get(r, 9)) + '">' + rb(r) + '</td><td class="name">' + RS.plink(pctx, p["id"], p.get("name")) +
                     '</td><td data-v="' + esc(fanta_team_name(T, p.get("team"))) + '">' + fanta_team_link(T, p.get("team")) + '</td><td class="pt num" data-v="' + str(p.get("price") or 0) + '">' + str(p.get("price") or 0) + "</td>" +
                     (num_td(fvm) if has_fvm else "") + num_td(s.get("mv"), d2(s.get("mv")) if s.get("mv") is not None else "—") + num_td(s.get("fmv"), d2(s.get("fmv")) if s.get("fmv") is not None else "—") +
                     num_td(tit, pct_html(tit) if tit is not None else "—") + num_td(s.get("pres"), str(s.get("pres")) if s.get("pres") is not None else "—") +
                     num_td(s.get("gol"), str(s.get("gol")) if s.get("gol") is not None else "—") + num_td(s.get("assist"), str(s.get("assist")) if s.get("assist") is not None else "—") + "</tr>")
        b.append("</tbody></table></div></div></section>")
    b.append('<h2>Come si legge il listone</h2><div class="note"><b>Quot.</b> = quotazione FantaTB in crediti (limite da 1 a 60). ' +
             ('<b>FVM</b> = fantavalore di mercato del listone ufficiale, quando disponibile. ' if has_fvm else "") +
             '<b>MV</b> = media dei voti FantaTB della stagione in corso; <b>FMV</b> = fantamedia, cioè la media dei fantavoti con bonus e malus. <b>Titolare</b> = indice di titolarità per la prossima giornata '
             '(verde da 70%, ambra da 40%). Presenze, gol e assist in Serie A ' + SEASON + ' (statistiche API-Football). Il trattino vuol dire ancora senza dato.</div>')
    b.append('<div class="faq"><details><summary>Come calcoliamo le quotazioni</summary><p>Base per ruolo (P 1, D 1, C 1, A 2) + presenze della scorsa stagione su 38 × (P 8, D 10, C 12, A 14) '
             '+ gol × (D 3, C 2, A 1,2) + assist × (D 1, C 1, A 0,8) + (rating medio − 6,5) × 10 se sopra 6,5 con almeno 10 presenze; i portieri con meno di un gol subito '
             'a partita guadagnano 0,3 a presenza. Limite da 1 a 60 crediti. Fonte statistiche: API-Football. Il listone si rifà dopo il mercato di gennaio.</p></details></div>')
    b.append('<h2 id="dati">Dati aperti</h2><div class="card"><div class="in"><p>Il listone è pubblicato anche come file JSON con licenza <a href="https://creativecommons.org/licenses/by/4.0/deed.it" rel="license noopener" target="_blank">CC BY 4.0</a>: '
             'puoi riutilizzarlo citando TransferBeat con un link. Ogni voce ha id, nome, squadra, ruolo Classic e quotazione; aggiornato il ' + esc(fdate_it(upd, True)) + '.</p>'
             '<a class="btn ghost" href="/data/fanta/listone.json">Scarica listone.json</a> <a class="btn sec" href="/fanta/#listone">Apri nell\'app FantaTB</a> '
             '<a class="btn ghost" href="/fantacalcio/">Tutti i dati del fantacalcio</a></div></div>')
    b.append(FILTER_JS + PCARD_JS)
    ld = dataset_ld("Listone fantacalcio Serie A " + SEASON + " (quotazioni FantaTB)",
                    "Quotazioni FantaTB di " + str(n) + " giocatori di Serie A con ruolo Classic e squadra, calcolate con formula pubblica da presenze, gol, assist e rating.",
                    canon, SITE + "/data/fanta/listone.json", upd, ["fantacalcio", "listone", "quotazioni", "Serie A " + SEASON])
    return fanta_page("Listone fantacalcio " + SEASON + ": quotazioni FantaTB",
                      "Listone fantacalcio " + SEASON + ": quotazioni FantaTB di " + str(n) + " giocatori di Serie A con ruolo, squadra, titolarità e medie. I più cari: " + top_txt + ".",
                      canon, "".join(b), FANTA_CRUMB + [("Listone", canon)], [ld], "Listone", extra_head=PCARD_CSS)

# ---------- voti ----------
VOTI_FAQ = [("I voti FantaTB sono quelli dei quotidiani?", "No. Sono voti statistici calcolati da TransferBeat dai dati reali della partita (API-Football) con una formula pubblica: rating meno 0,8, arrotondato al mezzo punto fra 4 e 8,5. Non coincidono con quelli della Gazzetta o di Fantacalcio.it."),
            ("Quando escono i voti?", "Durante la giornata di Serie A la pagina si aggiorna ogni 30 minuti con le partite finite; chi deve ancora giocare compare con il 6 politico. A giornata chiusa i voti sono definitivi e passano in archivio con la loro URL."),
            ("Cos'è il 6 politico?", "Un 6 provvisorio assegnato ai probabili titolari delle squadre che devono ancora giocare, per simulare il risultato delle leghe FantaTB. Sparisce appena la partita è votata e non è mai un voto reale."),
            ("Posso riutilizzare i voti?", "Sì: ogni giornata è pubblicata anche in JSON con licenza CC BY 4.0. Basta citare TransferBeat con un link.")]

def render_voti(D, T, md, V, latest=False, mirror=False):
    """Voti della giornata md: sull'URL fissa voti.html se è l'ultima disponibile, altrimenti in archivio voti-giornata-N.html.
    mirror=True: copia dell'ultima giornata sulla sua URL d'archivio (voti-giornata-N.html), che esiste già ed è linkata da articoli e schede:
    stesso contenuto e stesso guscio, ma canonical su voti.html, title e description propri e un avviso in testa; resta fuori dalla sitemap."""
    arch = "/fantacalcio/voti-giornata-%d.html" % md
    canon = SITE + ("/fantacalcio/voti.html" if (latest or mirror) else arch); upd = V.get("updated") or ""
    fn = "voti-%02d.json" % md; pctx = D.get("pctx")
    byid = {p["id"]: p for p in D["listone"].get("players") or []}
    rows = [(byid[r["player_id"]], r) for r in V.get("ratings") or [] if r.get("player_id") in byid]
    rated = [x for x in rows if x[1].get("voto") is not None]
    sv = [x for x in rows if x[1].get("voto") is None]
    rated.sort(key=lambda x: (-(x[1].get("fantavoto") or 0), -(x[1].get("voto") or 0), x[0]["name"]))
    sv.sort(key=lambda x: x[0]["name"])
    media = round(sum(x[1]["voto"] for x in rated) / len(rated), 2) if rated else None
    live = V.get("status") == "live"
    fin, tot = V.get("finished") or 0, V.get("total") or 0
    ms = md_matches(D, md); tmi = team_match_index(T, ms)
    now = datetime.now(timezone.utc)
    pending = [m for m in ms if m.get("status") not in FINISHED]
    nxt = next((m for m in pending if (parse_iso(m.get("utc")) or now) >= now), None) or (pending[0] if pending else None)
    # 6 politico: probabili titolari (indice >= 50) delle squadre che devono ancora giocare, solo a giornata in corso
    pol = []
    if live and pending:
        tit = D["titolari_all"].get(md) or D.get("titolari") or {}
        prob = {s["player_id"]: s.get("prob") or 0 for s in tit.get("status") or []}
        done_ids = {r["player_id"] for _, r in rows}
        for p in byid.values():
            site = T.fanta_name(p.get("team") or "")
            m = tmi.get(site) if site else None
            if m and m.get("status") not in FINISHED and p["id"] not in done_ids and prob.get(p["id"], 0) >= 50:
                pol.append((p, m))
        pol.sort(key=lambda x: (x[1].get("utc") or "", ROLE_ORDER.get(x[0].get("role"), 9), x[0]["name"]))
    top3 = ", ".join(p["name"] + " " + d1(r.get("fantavoto")) for p, r in rated[:3])
    best = rated[0] if rated else None
    stato = ("giornata in corso: " + str(fin) + " partite su " + str(tot) + " votate") if live else (str(tot) + " partite su " + str(tot) + " votate, giornata chiusa")
    first = (str(fin) + " partite su " + str(tot) + " votate, ") if live else (str(tot) + " partite votate, ")
    sub = (first + str(len(rated)) + " giocatori con voto, media " + (d2(media) if media is not None else "—") + (", il migliore " + best[0]["name"] + " " + d1(best[1].get("fantavoto")) if best else "") +
           ". Voto statistico FantaTB della giornata " + str(md) + " di Serie A " + SEASON + ", aggiornato il " + fdate_it(upd, True) + (" e ogni 30 minuti fino a fine giornata." if live else "."))
    mds = sorted(D["voti"]); last_md = mds[-1] if mds else md
    chips = '<div class="chips" aria-label="Giornate">' + "".join(
        '<a href="%s"%s>Giornata %d</a>' % (("/fantacalcio/voti.html" if k == last_md else "/fantacalcio/voti-giornata-%d.html" % k), ' class="on"' if k == md else "", k) for k in mds) + "</div>"
    b = ['<div class="h1row"><h1>Voti fantacalcio giornata ' + str(md) + " Serie A " + SEASON + "</h1>" + ('<span class="pill warn">giornata in corso</span>' if live else "") + "</div>",
         '<div class="sub">' + esc(sub) + "</div>",
         ('<div class="status">Copia d\'archivio della giornata ' + str(md) + ', l\'ultima con i voti: la versione aggiornata è su <a href="/fantacalcio/voti.html">Voti dell\'ultima giornata</a>.</div>') if mirror else "",
         chips,
         '<div class="tools"><input id="q" type="search" placeholder="Cerca giocatore o squadra" aria-label="Cerca giocatore o squadra">' + role_chips(anchors={r: "#tabella" for r in "PDCA"}) +
         team_select(T, [p.get("team") for p, _ in rows] + [p.get("team") for p, _ in pol]) + '<span class="hint"><span id="cnt">' + str(len(rows) + len(pol)) + "</span> righe · ordina dalle intestazioni</span></div>",
         '<div class="kpis"><div class="kpi"><div class="l">Partite votate</div><div class="v">' + str(fin) + ' <span class="s">su ' + str(tot) + '</span></div><div class="s">' + esc(stato) + "</div></div>"
         '<div class="kpi"><div class="l">Giocatori con voto</div><div class="v">' + str(len(rated)) + '</div><div class="s">' + str(len(sv)) + " senza voto (s.v.)</div></div>"
         '<div class="kpi"><div class="l">Media voto</div><div class="v">' + (d2(media) if media is not None else "—") + '</div><div class="s">voto base, senza bonus</div></div>'
         '<div class="kpi"><div class="l">' + ("Prossimo aggiornamento" if live else "Stato") + '</div><div class="v">' +
         ((esc(fdate_it(nxt.get("utc"), True, True)) if nxt else "ogni 30 min") if live else "Giornata chiusa") + '</div><div class="s">' +
         (("prossima partita: " + esc((nxt["home"].get("short") or "") + "-" + (nxt["away"].get("short") or "")) + " · voti ogni 30 minuti nei giorni di gara") if (live and nxt) else ("voti ogni 30 minuti nei giorni di gara" if live else "voti definitivi")) + "</div></div></div>",
         '<div class="card" id="tabella"><div class="tscroll"><table class="srt"><thead><tr><th class="sort" title="Ruolo">R</th><th class="sort">Giocatore</th><th class="sort">Squadra</th>'
         '<th class="sort num" data-n="1" title="Minuti giocati">Min</th><th class="sort num" data-n="1">Voto</th><th>Bonus e malus</th><th class="sort num" data-n="1">Fantavoto</th></tr></thead><tbody>']
    for p, r in rated + sv:
        v = r.get("voto"); fv = r.get("fantavoto"); rl = p.get("role")
        b.append('<tr data-pid="' + str(p["id"]) + '" data-r="' + esc(rl) + '" data-t="' + esc(p.get("team")) + '"><td data-v="' + str(ROLE_ORDER.get(rl, 9)) + '">' + rb(rl) + '</td><td class="name">' + RS.plink(pctx, p["id"], p["name"]) +
                 '</td><td data-v="' + esc(fanta_team_name(T, p.get("team"))) + '">' + fanta_team_link(T, p.get("team")) + '</td><td class="num" data-v="' + str(r.get("minutes") or 0) + '">' + str(r.get("minutes") or 0) +
                 '</td><td class="num' + (" fv lo" if (v is not None and v < 5) else "") + '" data-v="' + (str(v) if v is not None else "-1") + '">' + (d1(v) if v is not None else "s.v.") +
                 '</td><td>' + (bonus_html(r.get("bonus")) or '<span class="small">—</span>') + '</td><td class="num fv ' + fv_cls(fv) + '" data-v="' + (str(fv) if fv is not None else "-1") + '">' + (d1(fv) if fv is not None else "—") + "</td></tr>")
    for p, m in pol:
        rl = p.get("role"); when = fdate_it(m.get("utc"), True, True)
        b.append('<tr data-pid="' + str(p["id"]) + '" data-r="' + esc(rl) + '" data-t="' + esc(p.get("team")) + '"><td data-v="' + str(ROLE_ORDER.get(rl, 9)) + '">' + rb(rl) + '</td><td class="name">' + RS.plink(pctx, p["id"], p["name"]) +
                 '</td><td data-v="' + esc(fanta_team_name(T, p.get("team"))) + '">' + fanta_team_link(T, p.get("team")) + '</td><td class="num" data-v="0">—</td><td class="num" data-v="6"><span class="pol">6</span></td>'
                 '<td><span class="small">gioca ' + esc(when) + ', ' + esc((m["home"].get("short") or "") + "-" + (m["away"].get("short") or "")) + '</span></td><td class="num" data-v="6"><span class="pol">6,0</span></td></tr>')
    b.append('</tbody></table></div><div class="cf small"><b class="pol">6</b> = <b>6 politico</b>: chi deve ancora giocare conta come un 6 per simulare il risultato delle leghe; sparisce a partita votata' +
             (" (qui i probabili titolari delle squadre ancora da giocare, indice di titolarità almeno 50%)" if pol else "") + '. <b>s.v.</b> = senza voto, sotto i 15 minuti. Fantavoto in verde da 8, in rosso fino a 5,5.</div></div>')
    b.append(VOTO_NOTE)
    nav = []
    if D.get("probabili"):
        nmd = max(D["probabili"])
        nav.append('<a class="btn ghost" href="/fantacalcio/probabili-formazioni.html">Probabili formazioni giornata ' + str(nmd) + "</a>")
    nav.append('<a class="btn ghost" href="/fantacalcio/titolari.html">Infortunati e squalificati</a>')
    nav.append('<a class="btn sec" href="/fanta/#voti">Apri nell\'app FantaTB</a>')
    b.append("<p>" + " ".join(nav) + "</p>")
    if latest:
        b.append('<h2>Domande frequenti sui voti</h2><div class="faq">' + "".join("<details><summary>" + esc(q) + "</summary><p>" + esc(a) + "</p></details>" for q, a in VOTI_FAQ) + "</div>")
    b.append('<p class="small">Archivio: ' + " · ".join(("<b>giornata " + str(k) + "</b>") if k == md else ('<a href="' + ("/fantacalcio/voti.html" if k == last_md else "/fantacalcio/voti-giornata-" + str(k) + ".html") + '">giornata ' + str(k) + "</a>") for k in mds) +
             ' · dati grezzi: <a href="/data/fanta/' + fn + '">' + fn + '</a> (CC BY 4.0) · <a href="/fantacalcio/">tutti i dati del fantacalcio</a></p>')
    b.append(FILTER_JS)
    ld = [dataset_ld("Voti fantacalcio FantaTB, Serie A " + SEASON + " giornata " + str(md),
                     "Voto statistico, minuti, bonus e malus e fantavoto di " + str(len(rows)) + " giocatori di Serie A per la giornata " + str(md) + ", calcolati da FantaTB con formula pubblica.",
                     canon, SITE + "/data/fanta/" + fn, upd, ["fantacalcio", "voti", "fantavoto", "Serie A giornata " + str(md)])]
    if latest:
        ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in VOTI_FAQ]})
    crumbs = FANTA_CRUMB + ([("Voti giornata " + str(md), canon)] if latest else [("Voti", SITE + "/fantacalcio/voti.html"), ("Giornata " + str(md), SITE + arch)])
    desc = ("Voti FantaTB della giornata " + str(md) + " di Serie A " + SEASON + ": " + str(len(rated)) + " giocatori con voto statistico, bonus, malus e fantavoto" +
            (", giornata in corso" if live else "") + ". I migliori: " + top3 + ".")
    title = "Voti fantacalcio giornata " + str(md) + " Serie A " + SEASON
    if mirror:   # title e description diversi da voti.html (stesso contenuto, canonical su voti.html)
        title = "Archivio voti fantacalcio giornata " + str(md) + " Serie A " + SEASON
        desc = ("Archivio dei voti FantaTB della giornata " + str(md) + " di Serie A " + SEASON + ", l'ultima votata: " + str(len(rated)) + " giocatori con voto, bonus e fantavoto. "
                "Versione aggiornata su /fantacalcio/voti.html.")
    return fanta_page(title, desc, canon, "".join(b), crumbs, ld, "Voti")

# ---------- infortunati e squalificati (URL /fantacalcio/titolari.html invariata) ----------
STATO = {"inf": ("Fuori", "err"), "dubbio": ("In dubbio", "warn"), "squal": ("Squalificato", "info"), "rientra": ("Rientra", "ok")}

def unavailable(D, T, S, md):
    """Righe degli indisponibili della giornata md: (giocatore, stato, kind, motivo, dal, rientro, salta). kind in inf/dubbio/squal/rientra."""
    byid = {p["id"]: p for p in D["listone"].get("players") or []}
    allt = D["titolari_all"]; start = md_start(D, md)
    start_d = date_only(start) if start else ""
    # prima giornata delle giornate future (per contare quante ne salta)
    future = []
    for c in D["comp"].get("competizioni", []):
        if c.get("code") == "SA":
            for k, ms in (c.get("giornate") or {}).items():
                if int(k) >= md and ms:
                    future.append((int(k), date_only(min(m.get("utc") or "" for m in ms))))
    future.sort()
    def injured_in(t, pid):
        s = next((x for x in (t.get("status") or []) if x.get("player_id") == pid), None)
        return bool(s and (s.get("injury") or ("squalific" in (s.get("reason") or "").lower())))
    out = []
    cur = {s["player_id"]: s for s in S.get("status") or []}
    for pid, s in cur.items():
        p = byid.get(pid)
        inj = s.get("injury") or ""
        if not p or not (inj or "squalific" in (s.get("reason") or "").lower()):
            continue
        squal = "squalific" in (inj or s.get("reason") or "").lower()
        back = s.get("back_at") or ""
        if squal:
            kind = "squal"
        elif back and start_d and back <= start_d:
            kind = "dubbio"
        else:
            kind = "inf"
        k = md
        while (k - 1) in allt and injured_in(allt[k - 1], pid):
            k -= 1
        dal = "giornata " + str(k)
        if back:
            salta = sum(1 for kk, d0 in future if d0 and d0 < back)
            if future and back > future[-1][1]:
                salta = str(salta) + "+"   # rientro oltre l'ultima giornata in calendario: il conteggio è per difetto
            rientro = fdate_it(back + "T12:00:00Z")
        elif squal:
            salta = 1 if "espuls" in (s.get("reason") or "").lower() else None
            rientro = "giornata " + str(md + 1) if salta == 1 else "—"
        else:
            salta = None; rientro = "—"
        motivo = (s.get("reason") or inj or "").strip().replace("infortunio: infortunio", "infortunio")
        out.append((p, kind, motivo[:1].upper() + motivo[1:], dal, rientro, salta))
    prev = allt.get(md - 1)
    if prev:
        for s in prev.get("status") or []:
            pid = s.get("player_id"); p = byid.get(pid)
            if p and injured_in(prev, pid) and pid in cur and not injured_in(S, pid):
                mot = (s.get("injury") or s.get("reason") or "").replace("infortunio: infortunio", "infortunio")
                out.append((p, "rientra", mot[:1].upper() + mot[1:] + " · di nuovo disponibile", "giornata " + str(md - 1), "giornata " + str(md), 0))
    kord = {"inf": 0, "dubbio": 1, "squal": 2, "rientra": 3}
    out.sort(key=lambda x: (fanta_team_name(T, x[0].get("team")), kord.get(x[1], 9), x[0]["name"]))
    return out

def render_titolari(D, T):
    S = D["titolari"]; md = S.get("matchday") or 0; canon = SITE + "/fantacalcio/titolari.html"; upd = S.get("updated") or ""
    fn = "titolari-%02d.json" % md; pctx = D.get("pctx")
    byid = {p["id"]: p for p in D["listone"].get("players") or []}
    rows = [(byid[s["player_id"]], s) for s in S.get("status") or [] if s.get("player_id") in byid]
    una = unavailable(D, T, S, md)
    cnt = {k: sum(1 for x in una if x[1] == k) for k in STATO}
    n_out = cnt["inf"] + cnt["dubbio"] + cnt["squal"]
    start = md_start(D, md)
    teams = {}
    for p, s in rows:
        teams.setdefault(p.get("team") or "?", []).append((p, s))
    h1 = "Infortunati e squalificati Serie A: chi salta la giornata " + str(md)
    sub = (str(cnt["inf"]) + " giocatori fuori, " + str(cnt["dubbio"]) + " in dubbio e " + str(cnt["squal"]) + " squalificati per la giornata " + str(md) + " di Serie A " + SEASON +
           (" (da " + fdate_long(start) + ")" if start else "") + ", aggiornati il " + fdate_it(upd, True) + " con i dati di TransferBeat. Rientro previsto e giornate saltate per ogni nome, poi l'indice di titolarità di tutte le squadre.")
    state_chips = '<div class="chips rf" role="group" aria-label="Stato"><a href="#tabella" data-r="" class="on">Tutti</a>' + "".join(
        '<a href="#tabella" data-r="%s">%s</a>' % (k, {"inf": "Infortunati", "dubbio": "In dubbio", "squal": "Squalificati", "rientra": "Rientrano"}[k]) for k in ("inf", "dubbio", "squal", "rientra")) + "</div>"
    b = ["<h1>" + esc(h1) + "</h1>", '<div class="sub">' + esc(sub) + "</div>",
         '<div class="kpis"><div class="kpi err"><div class="l">Fuori</div><div class="v">' + str(cnt["inf"]) + '</div><div class="s">infortunati senza rientro entro la giornata</div></div>'
         '<div class="kpi warn"><div class="l">In dubbio</div><div class="v">' + str(cnt["dubbio"]) + '</div><div class="s">rientro stimato prima della giornata</div></div>'
         '<div class="kpi info"><div class="l">Squalificati</div><div class="v">' + str(cnt["squal"]) + '</div><div class="s">giudice sportivo o espulsione</div></div>'
         '<div class="kpi ok"><div class="l">Rientrano</div><div class="v">' + str(cnt["rientra"]) + '</div><div class="s">indisponibili alla giornata ' + str(md - 1) + ", ora ok</div></div></div>",
         '<div class="tools"><input id="q" type="search" placeholder="Cerca giocatore o squadra" aria-label="Cerca giocatore o squadra">' + state_chips + team_select(T, [x[0].get("team") for x in una]) +
         '<span class="hint">Ordinati per squadra, poi per stato · <span id="cnt">' + str(len(una)) + "</span> nomi</span></div>",
         '<h2 id="tabella">Indisponibili per la giornata ' + str(md) + " (" + str(n_out) + ")</h2>",
         '<div class="card"><div class="tscroll"><table class="srt"><thead><tr><th class="sort" title="Ruolo">R</th><th class="sort">Giocatore</th><th class="sort">Squadra</th><th>Motivo</th>'
         '<th class="sort">Dal</th><th class="sort">Rientro previsto</th><th class="sort num" data-n="1" title="Giornate di Serie A saltate dalla prossima">Salta</th><th class="sort">Stato</th></tr></thead><tbody>']
    if not una:
        b.append('<tr><td colspan="8"><span class="small">Nessun indisponibile segnalato per la giornata ' + str(md) + ".</span></td></tr>")
    for p, kind, motivo, dal, rientro, salta in una:
        lab, cls = STATO[kind]; rl = p.get("role")
        b.append('<tr data-r="' + kind + '" data-t="' + esc(p.get("team")) + '"><td data-v="' + str(ROLE_ORDER.get(rl, 9)) + '">' + rb(rl) + '</td><td class="name">' + RS.plink(pctx, p["id"], p["name"]) +
                 '</td><td data-v="' + esc(fanta_team_name(T, p.get("team"))) + '">' + fanta_team_link(T, p.get("team")) + "</td><td>" + esc(motivo) + "</td><td>" + esc(dal) + "</td><td>" + esc(rientro) +
                 '</td><td class="num" data-v="' + (str(salta).rstrip("+") if salta is not None else "-1") + '">' + (str(salta) if salta is not None else "—") + '</td><td data-v="' + lab + '"><span class="pill ' + cls + '">' + lab + "</span></td></tr>")
    b.append("</tbody></table></div></div>")
    back = [x for x in una if x[1] == "rientra"]
    dub = [x for x in una if x[1] == "dubbio"]
    b.append('<div class="grid2"><div class="card"><h3>Chi rientra per la giornata ' + str(md) + "</h3><div class=\"in\">" +
             (("<p>" + ", ".join(RS.plink(pctx, p["id"], p["name"]) + " (" + fanta_team_link(T, p.get("team")) + ")" for p, *_ in back) + ". Se ne hai uno in panchina, valuta di rimetterlo titolare.</p>") if back else
              "<p>Nessun rientro rispetto alla giornata " + str(md - 1) + " nei nostri dati.</p>") +
             (("<p>In dubbio, con rientro stimato a ridosso della giornata: " + ", ".join(RS.plink(pctx, p["id"], p["name"]) + " (" + fanta_team_link(T, p.get("team")) + ")" for p, *_ in dub) + ".</p>") if dub else "") + "</div></div>"
             '<div class="card"><h3>Come leggere la pagina</h3><div class="in"><p>"Salta" conta le giornate di Serie A perse dalla giornata ' + str(md) + ' in poi, quando c\'è una data di rientro (il segno + vuol dire oltre l\'ultima giornata già in calendario). '
             'La data di rientro è una stima nostra dai dati API-Football; per le squalifiche fa fede il giudice sportivo (dopo un\'espulsione contiamo almeno una giornata). '
             '"Dal" è la prima giornata in cui il giocatore risulta indisponibile nei nostri dati. "In dubbio" = rientro stimato prima della prima partita della giornata. Aggiornata dopo ogni turno e il venerdì.</p></div></div></div>')
    b.append('<h2 id="titolarita">Indice di titolarità squadra per squadra</h2>'
             '<div class="note"><b>Come nasce l\'indice.</b> Dalle ultime tre giornate: 90% se titolare (almeno 60 minuti) in tutte; altrimenti 15 + 25 per ogni partita da titolare + 5 per ogni '
             'subentro (fra 5 e 95); mai in campo 10%; mai convocato 20%; espulso nell\'ultima giornata 0% (squalifica). Infortuni e squalifiche da API-Football, con data di rientro stimata '
             'quando c\'è. È un indice statistico, non una formazione ufficiale: le <a href="/fantacalcio/probabili-formazioni.html">probabili formazioni</a> lo usano per costruire gli undici.</div>')
    b.append('<div class="chips">' + "".join('<a href="#sq-' + slugify(fanta_team_name(T, t)) + '">' + esc(fanta_team_name(T, t)) + "</a>" for t in sorted(teams, key=lambda t: fanta_team_name(T, t))) + "</div>")
    b.append('<div class="grid2">')
    for team in sorted(teams, key=lambda t: fanta_team_name(T, t)):
        lst = sorted(teams[team], key=lambda x: (-(x[1].get("prob") or 0), ROLE_ORDER.get(x[0].get("role"), 9), x[0]["name"]))
        b.append('<div class="card" id="sq-' + slugify(fanta_team_name(T, team)) + '"><h3>' + fanta_team_link(T, team) + '</h3><div class="in"><table><thead><tr><th>R</th><th>Giocatore</th><th class="num">Titolare</th><th>Perché</th></tr></thead><tbody>')
        for p, s in lst:
            b.append("<tr><td>" + rb(p.get("role")) + '</td><td class="name">' + RS.plink(pctx, p["id"], p["name"]) + '</td><td class="num">' + pct_html(s.get("prob")) + '</td><td class="small">' + esc(s.get("reason")) + "</td></tr>")
        b.append("</tbody></table></div></div>")
    b.append("</div>")
    b.append('<p class="small">Dati grezzi: <a href="/data/fanta/' + fn + '">' + fn + '</a> (CC BY 4.0) · usati nella schermata di schieramento di <a href="/fanta/">FantaTB</a> · <a href="/fantacalcio/">tutti i dati del fantacalcio</a></p>')
    b.append(FILTER_JS)
    ld = dataset_ld("Infortunati, squalificati e indice di titolarità FantaTB, Serie A " + SEASON + " giornata " + str(md),
                    "Infortunati con rientro stimato, squalificati e probabilità di titolarità per " + str(len(rows)) + " giocatori di Serie A in vista della giornata " + str(md) + ".",
                    canon, SITE + "/data/fanta/" + fn, upd, ["fantacalcio", "infortunati", "squalificati", "titolari", "probabili formazioni"])
    desc = ("Infortunati e squalificati di Serie A per la giornata " + str(md) + ": " + str(cnt["inf"]) + " fuori, " + str(cnt["dubbio"]) + " in dubbio, " + str(cnt["squal"]) +
            " squalificati con rientro previsto e giornate saltate, più l'indice di titolarità FantaTB di " + str(len(rows)) + " giocatori.")
    return fanta_page(h1, desc, canon, "".join(b), FANTA_CRUMB + [("Infortunati e squalificati", canon)], [ld], "Infortunati e squalificati")

# ---------- hub /fantacalcio/ ----------
FAQ = [("Come si calcola il voto FantaTB?", "Dal rating statistico della partita meno 0,8, arrotondato al mezzo punto fra 4 e 8,5; senza voto sotto i 15 minuti. Il fantavoto aggiunge bonus e malus con pesi pubblici: gol +3, assist +1, rigore sbagliato −3, rigore parato +3, gol subito −1 per i portieri, autogol −2, ammonizione −0,5, espulsione −1. L'admin di lega può correggere qualsiasi voto."),
       ("I voti sono quelli della Gazzetta o di Fantacalcio.it?", "No. Sono voti statistici calcolati da FantaTB dai dati reali della partita, con formula pubblica. Non coincidono con quelli dei quotidiani e FantaTB non è affiliato a Fantacalcio®."),
       ("Quando escono le probabili formazioni?", "Il giovedì sera, il venerdì pomeriggio e il sabato mattina, e a ogni aggiornamento dei voti: la pagina delle probabili mostra sempre la giornata più vicina con l'orario di ogni partita."),
       ("Quanto costa FantaTB?", "Niente. È gratuito, senza funzioni a pagamento e senza limiti di leghe: è un servizio di TransferBeat."),
       ("Serve installare un'app?", "No: funziona dal browser del telefono e del computer. Bastano un'email e una password."),
       ("Come si calcolano le quotazioni del listone?", "Da presenze, gol, assist e rating della stagione precedente, con una base per ruolo e un limite fra 1 e 60 crediti. La formula completa è nella pagina del listone; il listone si rifà dopo il mercato di gennaio."),
       ("Cos'è l'indice di titolarità?", "Una probabilità da 0 a 100 che un giocatore parta titolare nella prossima giornata, calcolata dalle ultime tre partite, più infortuni e squalifiche con data di rientro stimata. È un indice statistico, non una formazione ufficiale."),
       ("Come nascono le probabili formazioni?", "Dalle ultime tre formazioni ufficiali di ogni squadra (modulo e posizioni in campo) e dall'indice di titolarità: ogni titolare ha una percentuale, gli indisponibili vengono sostituiti dal giocatore più probabile nella stessa posizione e i ballottaggi mostrano i due contendenti. Sono probabili di TransferBeat costruite sui nostri dati, aggiornate più volte a settimana."),
       ("Posso riutilizzare questi dati?", "Sì: listone, voti e titolarità sono pubblicati anche come file JSON con licenza CC BY 4.0. Basta citare TransferBeat con un link.")]

def render_fanta_index(D, T):
    canon = SITE + "/fantacalcio/"; pctx = D.get("pctx")
    byid = {p["id"]: p for p in D["listone"].get("players") or []}
    n = len(D["listone"].get("players") or [])
    mds = sorted(D["voti"]); md_v = mds[-1] if mds else None; V = D["voti"].get(md_v) or {}
    live = V.get("status") == "live"
    rated = sorted([(byid[r["player_id"]], r) for r in V.get("ratings") or [] if r.get("player_id") in byid and r.get("voto") is not None],
                   key=lambda x: (-(x[1].get("fantavoto") or 0), -(x[1].get("voto") or 0), x[0]["name"]))
    P = D["probabili"].get(max(D["probabili"])) if D.get("probabili") else None
    md_p = P.get("matchday") if P else None
    tit = D.get("titolari") or {}; md_t = tit.get("matchday")
    st = {s["player_id"]: s for s in tit.get("status") or []}
    inj = sorted([(byid[pid], s) for pid, s in st.items() if pid in byid and s.get("injury")], key=lambda x: (x[1].get("back_at") or "9999", x[0]["name"]))
    n_inj = len(inj)
    n_bal = sum(1 for t in (P or {}).get("teams", {}).values() for x in t.get("xi") or [] if x.get("ballot")) if P else 0
    fx = sorted((P or {}).get("fixtures") or [], key=lambda f: f.get("date") or "")
    first = fx[0] if fx else None
    upd = max([x for x in (D["listone"].get("updated"), V.get("updated"), (P or {}).get("updated"), tit.get("updated")) if x] or [""])
    md_ref = md_p or md_t or md_v
    # frase citabile: numero + oggetto + data
    parts = [str(n) + " giocatori quotati"]
    if P:
        parts.append(str(n_bal) + " ballottaggi")
    if tit:
        parts.append(str(n_inj) + " indisponibili")
    sub = (", ".join(parts[:-1]) + " e " + parts[-1] if len(parts) > 1 else parts[0]) + (" per la giornata " + str(md_ref) if md_ref else "") + " di Serie A " + SEASON + ", aggiornati il " + fdate_it(upd, True) + \
          ". Probabili formazioni con le percentuali, voto statistico dopo ogni partita, listone e infortunati: i dati originali di TransferBeat, anche in JSON."
    # striscia di stato
    strip = []
    if P and first:
        strip.append("<b>Giornata " + str(md_p) + "</b> da " + esc(fdate_long(first.get("date"))))
    if V:
        strip.append("<b>Giornata " + str(md_v) + "</b> " + (("in corso: " + str(V.get("finished") or 0) + " partite su " + str(V.get("total") or 0) + " votate") if live else "chiusa, voti definitivi"))
    strip.append("ultimo aggiornamento " + esc(fdate_it(upd, True)))
    # KPI
    best = rated[0] if rated else None
    kpis = ['<div class="kpi"><div class="l">Giocatori quotati</div><div class="v">' + str(n) + '</div><a href="/fantacalcio/listone.html">Apri il listone</a></div>']
    if P:
        kpis.append('<div class="kpi"><div class="l">Ballottaggi</div><div class="v">' + str(n_bal) + '</div><a href="/fantacalcio/probabili-formazioni.html">Le probabili della giornata ' + str(md_p) + "</a></div>")
    if tit:
        kpis.append('<div class="kpi"><div class="l">Indisponibili</div><div class="v">' + str(n_inj) + '</div><a href="/fantacalcio/titolari.html">Infortunati e squalificati</a></div>')
    if best:
        kpis.append('<div class="kpi"><div class="l">Miglior fantavoto G' + str(md_v) + '</div><div class="v">' + d1(best[1].get("fantavoto")) + '</div><a href="/fantacalcio/voti.html">' +
                    esc(best[0]["name"]) + " · " + esc(fanta_team_name(T, best[0].get("team"))) + "</a></div>")
    b = ["<h1>Fantacalcio Serie A " + SEASON + ": probabili, voti, listone e infortunati</h1>", '<div class="sub">' + esc(sub) + "</div>",
         '<div class="status">' + " · ".join(strip) + "</div>", '<div class="kpis">' + "".join(kpis) + "</div>", '<div class="grid2">']
    # card probabili (gradiente firma, unica della pagina)
    if P and first:
        lines = []
        def pos_of(name):
            r = T.row_of.get(T.fanta_name(name) or "")
            return r[1].get("pos") if r else 99
        clou = min(fx, key=lambda f: pos_of(f.get("home")) + pos_of(f.get("away")))
        lines.append("Partita clou: <b>" + esc(fanta_team_name(T, clou.get("home"))) + "-" + esc(fanta_team_name(T, clou.get("away"))) + "</b>, " + esc(fdate_long(clou.get("date"))) + ".")
        bal = next(((tn, x) for tn in (clou.get("home"), clou.get("away")) for x in (P["teams"].get(tn) or {}).get("xi") or [] if x.get("ballot")), None) or \
              next(((tn, x) for tn, t in P["teams"].items() for x in t.get("xi") or [] if x.get("ballot")), None)
        if bal:
            tn, x = bal
            lines.append("Ballottaggio: " + esc(x["name"]) + "-" + esc(x["ballot"]["name"]) + " " + str(x.get("share") or 50) + "-" + str(x["ballot"].get("share") or 50) + " (" + esc(fanta_team_name(T, tn)) + ").")
        rientri = [x for x in unavailable(D, T, tit, md_t) if x[1] == "rientra"] if (tit and md_t) else []
        if rientri:
            lines.append("Rientra: " + esc(rientri[0][0]["name"]) + " (" + esc(fanta_team_name(T, rientri[0][0].get("team"))) + ").")
        else:
            outs = sum(len(t.get("out") or []) for t in P["teams"].values())
            lines.append(str(outs) + " indisponibili già sostituiti negli undici.")
        b.append('<div class="grad"><div class="k">Probabili formazioni · giornata ' + str(md_p) + "</div><h2>" + str(len(fx)) + " partite, due mezzi campi, la percentuale di ogni giocatore</h2>"
                 '<p>Costruite dalle ultime formazioni ufficiali e dall\'indice di titolarità. ' + esc(fanta_team_name(T, first.get("home"))) + "-" + esc(fanta_team_name(T, first.get("away"))) + " apre " + esc(fdate_long(first.get("date"))) + ".</p>"
                 '<ul class="lines">' + "".join("<li>" + l + "</li>" for l in lines) + "</ul>"
                 '<a class="btn" href="/fantacalcio/probabili-formazioni.html">Apri le probabili</a> <a href="/fantacalcio/probabili-formazioni.html">' + str(n_bal) + " ballottaggi da seguire →</a></div>")
    else:
        b.append('<div class="grad"><div class="k">Probabili formazioni</div><h2>In arrivo prima della prossima giornata</h2><p>Moduli, undici titolari con la percentuale di ogni giocatore, ballottaggi e indisponibili, partita per partita.</p>'
                 '<a class="btn" href="/fantacalcio/probabili-formazioni.html">La pagina delle probabili</a></div>')
    # card voti
    if V:
        b.append('<div class="card"><h2>Voti giornata ' + str(md_v) + ('<span class="pill warn">in corso</span>' if live else "") + '</h2><div class="vrows">' + "".join(
            '<div class="vr">' + rb(p.get("role")) + '<span class="n"><b>' + RS.plink(pctx, p["id"], p["name"]) + "</b> <span>" + esc(fanta_team_name(T, p.get("team"))) + '</span></span><span class="fv ' + fv_cls(r.get("fantavoto")) + '">' + d1(r.get("fantavoto")) + "</span></div>"
            for p, r in rated[:5]) + '</div><div class="cf"><a href="/fantacalcio/voti.html">Tutti i voti della giornata ' + str(md_v) + " →</a>" +
            ((' · <a href="/fantacalcio/voti-giornata-' + str(mds[-2]) + '.html">giornata ' + str(mds[-2]) + "</a>") if len(mds) > 1 else "") + "</div></div>")
    else:
        b.append('<div class="card"><h2>Voti</h2><div class="in"><p>Voto statistico, minuti, bonus e malus e fantavoto di ogni giocatore, disponibili dopo la prima giornata di Serie A.</p></div></div>')
    b.append("</div>")
    # tre porte
    inj_sub = (str(n_inj) + " indisponibili per la giornata " + str(md_t)) if tit else "Indice di titolarità e rientri"
    if tit and inj:
        inj_sub += ": " + ", ".join(p["name"] for p, _ in inj[:3])
    b.append('<div class="doors3">' + door("Infortunati e squalificati", inj_sub, "/fantacalcio/titolari.html") +
             door("Listone", str(n) + " giocatori quotati, aggiornato il " + fdate_it(D["listone"].get("updated")), "/fantacalcio/listone.html") +
             door("Gioca a FantaTB", "Leghe private, asta live dal telefono, voti ogni 30 minuti. Gratis.", "/fantatb.html", dark=True) + "</div>")
    b.append('<h2>Domande frequenti</h2><div class="faq">' + "".join("<details><summary>" + esc(q) + "</summary><p>" + esc(a) + "</p></details>" for q, a in FAQ) + "</div>")
    b.append('<p class="small">Anche in JSON con licenza CC BY 4.0: <a href="/fantacalcio/listone.html#dati">dati aperti</a> · schede di ' +
             (str(len(D["pctx"]["P"])) + ' giocatori in <a href="/giocatori/">Giocatori</a>' if D.get("pctx") else '<a href="/giocatori/">tutti i giocatori</a>') + "</p>")
    ld = [{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ]}]
    desc = ("Fantacalcio Serie A " + SEASON + ": probabili formazioni con le percentuali, voti statistici di ogni giornata, listone di " + str(n) + " giocatori, infortunati e squalificati. Dati aperti di FantaTB, gratis.")
    return fanta_page("Fantacalcio Serie A " + SEASON + ": probabili, voti e listone", desc, canon, "".join(b), FANTA_CRUMB, ld, "Panoramica")

# ---------- iniezione statica nelle hub (fra <!--static:NOME--> e <!--/static:NOME-->) ----------
def inject(path, blocks, optional=()):
    """Sostituisce il contenuto fra i marcatori. I marcatori in `optional` possono mancare (avviso, niente errore): servono per i blocchi nuovi
    finché la pagina a mano non li ha."""
    src = read_text(path); out = src
    for name, html_ in blocks.items():
        pat = re.compile(r"(<!--static:" + re.escape(name) + r"-->)(.*?)(<!--/static:" + re.escape(name) + r"-->)", re.S)
        if not pat.search(out):
            if name in optional:
                print("render_site: marcatore static:" + name + " assente in " + os.path.relpath(path, ROOT) + " (blocco saltato)")
                continue
            raise SystemExit("render_site: marcatore static:" + name + " assente in " + os.path.relpath(path, ROOT))
        out = pat.sub(lambda m: m.group(1) + html_ + m.group(3), out, count=1)
    if out != src:
        save_text(path, out)

# Icone SVG (stroke 2) al posto delle emoji nei riquadri senza immagine della home.
ICON_NEWS = ('<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M4 5h13v14H4zM17 8h3v9a2 2 0 0 1-2 2M7 9h7M7 13h7M7 16h4"/></svg>')
ICON_WORLD = ('<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
              '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>')
ICON_BALL = ('<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<circle cx="12" cy="12" r="9"/><path d="M12 7l4 3-1.5 4.5h-5L8 10zM12 3v4M8 10l-4-1M16 10l4-1M9.5 14.5L7 18M14.5 14.5L17 18"/></svg>')

def home_card(o, icon=ICON_NEWS):
    img = ('<div class="ph2"><img src="' + esc(o.get("img")) + '" loading="lazy" alt=""></div>') if o.get("img") else '<div class="ph2"><span>' + icon + "</span></div>"
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

def home_fanta_block(D, T):
    """Blocco Fantacalcio della home (marcatore static:fanta): giornata, probabili, voti, listone, infortunati e CTA, tutto nell'HTML."""
    n = len(D["listone"].get("players") or [])
    if not n:
        return ""
    mds = sorted(D["voti"]); V = D["voti"].get(mds[-1]) if mds else {}
    P = D["probabili"].get(max(D["probabili"])) if D.get("probabili") else None
    tit = D.get("titolari") or {}
    fx = sorted((P or {}).get("fixtures") or [], key=lambda f: f.get("date") or "")
    n_inj = sum(1 for s in tit.get("status") or [] if s.get("injury"))
    parts = []
    if P and fx:
        parts.append("probabili formazioni della giornata " + str(P.get("matchday")) + " (da " + fdate_long(fx[0].get("date"), False) + ")")
    if V:
        parts.append("voti della giornata " + str(mds[-1]) + ((" in corso, " + str(V.get("finished") or 0) + " partite su " + str(V.get("total") or 0) + " votate") if V.get("status") == "live" else " definitivi"))
    parts.append("listone di " + str(n) + " giocatori")
    if tit:
        parts.append(str(n_inj) + " indisponibili per la giornata " + str(tit.get("matchday")))
    doors = []
    if P:
        doors.append(door("Probabili formazioni", "Giornata " + str(P.get("matchday")) + ", percentuali e ballottaggi", "/fantacalcio/probabili-formazioni.html"))
    if V:
        doors.append(door("Voti giornata " + str(mds[-1]), "Voto statistico, bonus e fantavoto", "/fantacalcio/voti.html"))
    doors.append(door("Listone", str(n) + " giocatori quotati", "/fantacalcio/listone.html"))
    if tit:
        doors.append(door("Infortunati e squalificati", str(n_inj) + " indisponibili, rientri previsti", "/fantacalcio/titolari.html"))
    return ('<h2><a href="/fantacalcio/">Fantacalcio Serie A ' + SEASON + "</a></h2><p>" + esc("; ".join(parts).capitalize()) + ". I dati originali di TransferBeat, gratis e anche in JSON.</p>"
            '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin:12px 0">' + "".join(doors) + "</div>"
            '<p><a class="btn" href="' + esc(CTA[1]) + '">' + esc(CTA[0]) + '</a> <a class="btn ghost" href="/fantacalcio/">Tutti i dati del fantacalcio</a></p>')

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
        lead = ('<a class="ph" ' + ext(a.get("link")) + ' style="display:grid">' + ('<img src="' + esc(a.get("img")) + '" alt="">' if a.get("img") else '<div class="ico">' + ICON_BALL + '</div>') +
                '<span class="badge">IN PRIMO PIANO</span></a><div class="kicker">' + esc(a.get("categoria")) + '</div><h2 class="hh"><a ' + ext(a.get("link")) + ">" + esct(a.get("titolo")) +
                '</a></h2><div class="by">Fonte: <a ' + ext(a.get("link")) + ' style="color:var(--accent2);font-weight:600">' + esc(a.get("fonte")) + "</a>" +
                (" (" + esc(a.get("dominio")) + ")" if a.get("dominio") else "") + "</div>")
    ticker = "".join("<span>" + esct(t) + "</span>" for t in H.get("ticker") or [])
    sub3 = "".join(home_card(s) for s in (H.get("secondari") or []) if s)
    world = "".join(home_card(m, ICON_WORLD) for m in H.get("mondo") or [])
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
                   ' · <a class="cl" href="/squadre/">tutte le squadre →</a> · <a class="cl" href="/giocatori/">schede giocatore</a> · <a class="cl" href="/fantacalcio/">fantacalcio: probabili, voti, listone e infortunati</a></div>')
    masthead = esc(H.get("giorno")) + "<br>Edizione delle <b><time>" + esc((upd or "")[11:16]) + "</time></b> · Il giornale del calcio"
    blocks = {"ticker": ticker, "lead": lead, "sub3": sub3, "miniBoard": miniboard, "topNews": topnews, "articoliRow": artrow, "worldRow": world, "squadre": "".join(squadre), "masthead": masthead,
              "fanta": home_fanta_block(D, T)}
    inject(os.path.join(ROOT, "index.html"), blocks, optional=("fanta",))
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
            out.append('<div class="card"><h2>Marcatori</h2><table><thead><tr><th class="num">#</th><th class="team">Giocatore</th><th class="team">Squadra</th><th class="num">Gol</th></tr></thead><tbody>' +
                       "".join('<tr><td class="num">' + str(i + 1) + '</td><td class="team">' + esc(s.get("name")) + '</td><td class="team">' + T.link(s.get("team") or {}) + '</td><td class="pt num">' + str(s.get("goals", 0)) + "</td></tr>"
                               for i, s in enumerate(c["marcatori"][:5])) + "</tbody></table></div>")
        out.append('<p class="legend"><a href="/campionati/' + meta["slug"] + '.html">' + esc(meta["nome"]) + ": tutte le giornate, i marcatori e le squadre →</a></p></section>")
    html_ = "".join(out)
    inject(os.path.join(ROOT, "campionati.html"), {"view": html_, "comps": comps_html, "upd": "Aggiornato " + esc(fdate_it(upd, True))})
    return lm.touch("/campionati.html", html_)

# ---------- llms.txt ----------
def render_llms(D, T):
    n = len(D["listone"].get("players") or []); mds = sorted(D["voti"].keys()); tit = D["titolari"]
    P = D["probabili"].get(max(D["probabili"])) if D.get("probabili") else None
    L = ["# TransferBeat", "",
         "> Giornale di calcio in italiano (articoli anche in inglese e spagnolo): calciomercato e notizie di Serie A, Premier League e Liga squadra per squadra, classificate per grado di concretezza (voce, anteprima, ufficiale, fatto) e con la fonte sempre citata; classifiche, risultati, calendario e marcatori di sei competizioni; schede di tutti i giocatori di Serie A; FantaTB, fantacalcio gratuito con dati aperti (probabili formazioni, voti statistici, listone, infortunati e squalificati).",
         "", "Chi siamo: " + SITE + "/chi-siamo.html · Fonti e affidabilità: " + SITE + "/fonti.html · Aggiornamento automatico ogni due ore; articoli scritti con l'aiuto dell'intelligenza artificiale e supervisione editoriale.",
         "", "## Sezioni", "- [Home](" + SITE + "/): apertura, notizie principali, ultim'ora, articoli, blocco fantacalcio",
         "- [Notizie](" + SITE + "/board.html): calciomercato e notizie squadra per squadra, ordinate per concretezza",
         "- [Campionati](" + SITE + "/campionati/): classifiche, risultati, calendario e marcatori (archivio Mondiale 2026: " + SITE + "/mondiali.html)",
         "- [Squadre](" + SITE + "/squadre/): una pagina per squadra con notizie, classifica, partite, rosa e blocco fantacalcio",
         "- [Giocatori](" + SITE + "/giocatori/): " + ((str(len(D["pctx"]["P"])) + " schede giocatore") if D.get("pctx") else "schede giocatore") + " di Serie A (statistiche, carriera, voti FantaTB)",
         "- [Fantacalcio](" + SITE + "/fantacalcio/): hub dei dati originali di FantaTB",
         "- [Articoli](" + SITE + "/articoli/it/): recap di giornata, lunch break e focus (EN: " + SITE + "/articoli/en/, ES: " + SITE + "/articoli/es/)",
         "- [Gioca a FantaTB](" + SITE + "/fantatb.html): cos'è e come si crea una lega nel fantacalcio gratuito di TransferBeat", "", "## Competizioni"]
    for c in D["comp"].get("competizioni", []):
        meta = COMP_BY_CODE.get(c["code"]); lead = comp_leader(c)
        if meta:
            L.append("- [" + meta["nome"] + " " + SEASON + "](" + SITE + "/campionati/" + meta["slug"] + ".html): giornata " + str(c.get("giornata") or "") +
                     ((", in testa " + (T.name_of(lead["team"]) or lead["team"].get("short") or "") + " con " + str(lead.get("pt", 0)) + " punti") if lead else ""))
    L += ["", "## Fantacalcio: dati originali di FantaTB (citabili, licenza CC BY 4.0, anche in JSON)"]
    if P:
        L.append("- [Probabili formazioni giornata " + str(P.get("matchday")) + "](" + SITE + "/fantacalcio/probabili-formazioni.html): moduli, undici con percentuale, ballottaggi, indisponibili" +
                 (" (archivio: " + ", ".join(SITE + "/fantacalcio/probabili-giornata-%d.html" % k for k in sorted(D["probabili"])[:-1]) + ")" if len(D["probabili"]) > 1 else ""))
    if mds:
        L.append("- [Voti giornata " + str(mds[-1]) + "](" + SITE + "/fantacalcio/voti.html): voto statistico, bonus, fantavoto (JSON: " + SITE + "/data/fanta/voti-%02d.json)" % mds[-1])
        for k in mds[:-1]:
            L.append("- [Voti giornata " + str(k) + "](" + SITE + "/fantacalcio/voti-giornata-" + str(k) + ".html): archivio (JSON: " + SITE + "/data/fanta/voti-%02d.json)" % k)
    L.append("- [Listone " + SEASON + "](" + SITE + "/fantacalcio/listone.html): quotazioni di " + str(n) + " giocatori di Serie A (JSON: " + SITE + "/data/fanta/listone.json)")
    if tit:
        L.append("- [Infortunati e squalificati giornata " + str(tit.get("matchday")) + "](" + SITE + "/fantacalcio/titolari.html): indisponibili con rientro previsto e indice di titolarità")
    if RX:
        L.append("- [Regolamento FantaTB](" + SITE + "/fantacalcio/regolamento.html): regole, bonus e malus, formula del voto")
        L.append("- [Guida all'asta](" + SITE + "/fantacalcio/guida-asta.html): come preparare e condurre l'asta")
    L += ["- [Domande frequenti sul fantacalcio FantaTB](" + SITE + "/fantacalcio/)", "", "## Squadre"]
    for lg in LEAGUE_ORDER:
        L.append("- " + LEAGUE_LABEL.get(lg, lg) + ": " + ", ".join("[" + t["nome"] + "](" + SITE + T.url(t["nome"]) + ")" for t in T.list if t.get("league") == lg))
    L += ["", "## Condizioni d'uso",
          "- Le notizie sono aggregate da fonti pubbliche e rimandano sempre alla testata originale: citare la fonte originale insieme a TransferBeat.",
          "- Classifiche e risultati: dati football-data.org. Voti, quotazioni, titolarità e probabili FantaTB: elaborazione originale di TransferBeat su dati API-Football, riutilizzabili citando TransferBeat con un link.",
          "- Schede giocatore: " + SITE + "/giocatori/ (una pagina per ogni giocatore di Serie A: statistiche stagione scorsa e in corso, per 90 minuti, carriera, voti FantaTB). Statistiche di squadra con grafici nelle pagine squadra. Dati API-Football, elaborazione TransferBeat.",
          "- Sitemap: " + SITE + "/sitemap.xml", ""]
    save_text(os.path.join(ROOT, "llms.txt"), "\n".join(L))

# Pagine scritte a mano: guscio unico fra i marcatori <!--shell:css-->, <!--shell:header-->, <!--shell:footer--> (apply_shell avvisa se mancano).
SHELL_PAGES = [("index.html", dict(here="", promo=True)), ("board.html", dict(here="Notizie")), ("campionati.html", dict(here="Campionati", bar=CAMP_BAR, bar_here="")),
               ("fonti.html", dict(here="")), ("mondiali.html", dict(here="Campionati", bar=CAMP_BAR, bar_here="Mondiale 2026"))]

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
    # guscio unico nelle pagine a mano, PRIMA delle iniezioni statiche (i marcatori shell e static convivono)
    for fn, kw in SHELL_PAGES:
        p = os.path.join(ROOT, fn)
        if os.path.exists(p):
            apply_shell(p, **kw)
    if D["home"]:
        pages["pagine"].append((SITE + "/", render_home(D, T, lm)))
    if D["board_sq"]:
        pages["pagine"].append((SITE + "/board.html", render_board(D, T, lm)))
    if D["comp"].get("competizioni"):
        pages["pagine"].append((SITE + "/campionati.html", render_campionati_hub(D, T, lm)))
    out("chi-siamo.html", "/chi-siamo.html", render_chi_siamo(), "pagine")
    if RL:
        out("fantatb.html", "/fantatb.html", RL.render(D, T), "pagine")   # landing generata dal modulo
    touch = [("/fonti.html", "fonti.html"), ("/mondiali.html", "mondiali.html"), ("/fanta/", "fanta/index.html")] + ([] if RL else [("/fantatb.html", "fantatb.html")])
    for url, fn in touch:
        p = os.path.join(ROOT, fn)
        if os.path.exists(p):
            src = read_text(p)
            if "noindex" in src[:4000]:   # l'app in fanta/ passa a noindex: fuori dalla sitemap
                continue
            pages["pagine"].append((SITE + url, lm.touch(url, src)))
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
        mds = sorted(D["voti"])
        for md in mds:   # l'ultima giornata sull'URL fissa voti.html, le precedenti in archivio
            latest = (md == mds[-1])
            rel = "fantacalcio/voti.html" if latest else "fantacalcio/voti-giornata-%d.html" % md
            out(rel, "/" + rel, render_voti(D, T, md, D["voti"][md], latest), "fanta")
            if latest:   # la URL d'archivio dell'ultima giornata esiste già (linkata da articoli e schede): la riscriviamo col guscio nuovo,
                # canonical su voti.html e fuori dalla sitemap, invece di lasciare sul disco la versione vecchia
                save_text(os.path.join(ROOT, "fantacalcio", "voti-giornata-%d.html" % md), render_voti(D, T, md, D["voti"][md], mirror=True))
        if D["titolari"]:
            out("fantacalcio/titolari.html", "/fantacalcio/titolari.html", render_titolari(D, T), "fanta")
        if D["probabili"]:   # l'ultima giornata sull'URL fissa, le precedenti in archivio (nessun doppione: la corrente non ha pagina d'archivio)
            mds = sorted(D["probabili"]); helpers = {"plink": RS.plink, "pctx": D.get("pctx"), "fanta_team_link": fanta_team_link, "dataset_ld": dataset_ld, "crumb": FANTA_CRUMB, "others": mds}
            for md in mds:
                latest = (md == mds[-1])
                rel = "fantacalcio/probabili-formazioni.html" if latest else "fantacalcio/probabili-giornata-%d.html" % md
                out(rel, "/" + rel, RP.render(D, T, D["probabili"][md], latest, helpers), "fanta")
        out("fantacalcio/index.html", "/fantacalcio/", render_fanta_index(D, T), "fanta")
        if RX:
            for rel, url, html_ in RX.render_all(D, T):   # regolamento, guida all'asta, consigli
                out(rel, url, html_, "fanta")
    if D.get("pctx"):
        written = set()
        for pid, p in D["pctx"]["P"].items():
            u = D["pctx"]["urls"][int(pid)]
            out(u.lstrip("/"), u, RS.render_player(D, D["stats"], T, p, D["pctx"]), "giocatori")
            written.add(os.path.basename(u))
        out("giocatori/index.html", "/giocatori/", RS.render_players_index(D, D["stats"], T, D["pctx"]), "giocatori")
        RS.write_schede(D["pctx"], os.path.join(DATA, "fanta", "schede.json"), T)   # per l'app FantaTB e la scheda rapida del listone: listone, maglie con i colori sociali
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
         "tutti i suoi dati originali: <a href=\"/fantacalcio/probabili-formazioni.html\">probabili formazioni</a>, <a href=\"/fantacalcio/listone.html\">listone</a>, <a href=\"/fantacalcio/voti.html\">voti</a> e "
         "<a href=\"/fantacalcio/titolari.html\">infortunati e squalificati</a>, con formula dichiarata e licenza aperta.</p>",
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
    return page("Chi siamo: come nasce TransferBeat, il giornale del calcio", "Chi fa TransferBeat e come lavora: notizie da fonti dichiarate ordinate per concretezza, articoli supervisionati, dati FantaTB con formule pubbliche.",
                canon, "".join(b), crumbs=[("Home", SITE + "/"), ("Chi siamo", canon)], ld=ld, here="")

if __name__ == "__main__":
    main()
