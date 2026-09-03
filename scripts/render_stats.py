#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - render_stats.py: grafici SVG, sezione "Statistiche" delle pagine squadra e schede giocatore
(giocatori/<slug>.html + giocatori/index.html) dai JSON di data/stats/ scritti da stats_pull.py (kb/FANTATB.md §14).
Importato da render_site.py: nessuna rete, nessuna chiave, HTML statico (i grafici sono SVG inline, indicizzabili).
Regole grafiche (skill dataviz): palette validata blu #1f6fd6 / arancio #eb6834 / viola #7b46c9, grigio #a7b0ba per la
de-enfasi; barre <= 24px con punta arrotondata e 2px di aria fra barre adiacenti; linee 2px; marcatori >= 8px con anello
bianco; griglia hairline; legenda sempre presente con >= 2 serie; etichette dirette solo sui massimi; accanto a ogni
grafico c'e' sempre la tabella con i numeri."""
import os, math
from datetime import date
from site_common import esc, slugify, norm, load_json, DATA, SITE, SEASON, fdate_it, date_only, page, ORG, FANTA_ALIAS, badge

C1, C2, C3, GRAY = "#1f6fd6", "#eb6834", "#7b46c9", "#a7b0ba"
STATS_DIR = os.path.join(DATA, "stats")
CUR = int(SEASON[:4])                                   # 2026
PREV_LABEL = "%d-%s" % (CUR - 1, str(CUR)[2:])           # "2025-26"
PHOTOS = False        # foto dal CDN di API-Football: da attivare solo dopo aver verificato la licenza d'uso
API_ALIAS = {"AC Milan": "Milan", "AS Roma": "Roma", "Manchester City": "Man City", "Manchester United": "Man United",
             "Atletico Madrid": "Atlético Madrid", "Alaves": "Alavés", "Malaga": "Málaga", "Deportivo La Coruna": "Deportivo",
             "Hellas Verona": "Verona", "Ipswich": "Ipswich Town", "Coventry": "Coventry City", "Hull": "Hull City"}
ROLE_IT = {"Goalkeeper": "portiere", "Defender": "difensore", "Midfielder": "centrocampista", "Attacker": "attaccante"}
ROLE_PL = {"Goalkeeper": "Portieri", "Defender": "Difensori", "Midfielder": "Centrocampisti", "Attacker": "Attaccanti"}
ROLE_ORDER = ["Goalkeeper", "Defender", "Midfielder", "Attacker"]
ROLE_CLASSIC = {"Goalkeeper": "P", "Defender": "D", "Midfielder": "C", "Attacker": "A"}
INTERVALS = ["0-15", "16-30", "31-45", "46-60", "61-75", "76-90"]
TOP_LEAGUES = {"Serie A", "Premier League", "La Liga", "Bundesliga", "Ligue 1", "Eredivisie", "Primeira Liga", "Serie B", "Championship",
               "Liga Profesional Argentina", "Süper Lig", "Jupiler Pro League", "Pro League", "Super League", "Ekstraklasa", "Major League Soccer",
               "Saudi Pro League", "Premiership", "Liga MX", "Primera Division", "Superliga", "Eliteserien", "Allsvenskan", "Czech Liga",
               "HNL", "Super Liga", "Liga I", "Ligue 2", "2. Bundesliga", "Segunda División", "Liga Portugal", "Premier Liga", "Prva HNL",
               "Serie A Betano", "Super League 1", "Ligat ha'Al", "First Division A", "UAE League", "Stars League", "J1 League", "K League 1"}
NAZ = {"Italy": "italiano", "France": "francese", "Argentina": "argentino", "Brazil": "brasiliano", "Spain": "spagnolo", "Portugal": "portoghese",
       "Netherlands": "olandese", "Belgium": "belga", "Germany": "tedesco", "England": "inglese", "Serbia": "serbo", "Croatia": "croato",
       "Nigeria": "nigeriano", "Senegal": "senegalese", "Denmark": "danese", "Sweden": "svedese", "Norway": "norvegese", "Poland": "polacco",
       "Switzerland": "svizzero", "Austria": "austriaco", "USA": "statunitense", "Colombia": "colombiano", "Uruguay": "uruguaiano", "Chile": "cileno",
       "Mexico": "messicano", "Morocco": "marocchino", "Algeria": "algerino", "Ivory Coast": "ivoriano", "Côte d'Ivoire": "ivoriano", "Ghana": "ghanese",
       "Cameroon": "camerunese", "Mali": "maliano", "Turkey": "turco", "Türkiye": "turco", "Greece": "greco", "Albania": "albanese", "Kosovo": "kosovaro",
       "Slovenia": "sloveno", "Slovakia": "slovacco", "Czech Republic": "ceco", "Czechia": "ceco", "Hungary": "ungherese", "Romania": "rumeno",
       "Ukraine": "ucraino", "Russia": "russo", "Scotland": "scozzese", "Wales": "gallese", "Ireland": "irlandese", "Republic of Ireland": "irlandese",
       "Northern Ireland": "nordirlandese", "Iceland": "islandese", "Finland": "finlandese", "Japan": "giapponese", "Korea Republic": "sudcoreano",
       "South Korea": "sudcoreano", "Australia": "australiano", "Canada": "canadese", "Ecuador": "ecuadoriano", "Paraguay": "paraguaiano",
       "Venezuela": "venezuelano", "Peru": "peruviano", "Bolivia": "boliviano", "Bosnia and Herzegovina": "bosniaco", "North Macedonia": "macedone",
       "Montenegro": "montenegrino", "Israel": "israeliano", "Egypt": "egiziano", "Tunisia": "tunisino", "Guinea": "guineano", "Congo DR": "congolese",
       "Congo": "congolese", "Gambia": "gambiano", "Angola": "angolano", "Cape Verde Islands": "capoverdiano", "Cape Verde": "capoverdiano",
       "Burkina Faso": "burkinabé", "Georgia": "georgiano", "Armenia": "armeno", "Iran": "iraniano", "New Zealand": "neozelandese",
       "Luxembourg": "lussemburghese", "Cyprus": "cipriota", "Malta": "maltese", "Lithuania": "lituano", "Latvia": "lettone", "Estonia": "estone",
       "Bulgaria": "bulgaro", "Moldova": "moldavo", "Belarus": "bielorusso", "Kazakhstan": "kazako", "Uzbekistan": "uzbeko", "Jamaica": "giamaicano",
       "Honduras": "honduregno", "Costa Rica": "costaricano", "Panama": "panamense", "Guinea-Bissau": "guineense", "Equatorial Guinea": "equatoguineano",
       "Sierra Leone": "sierraleonese", "Togo": "togolese", "Benin": "beninese", "Zambia": "zambiano", "Zimbabwe": "zimbabwese", "South Africa": "sudafricano",
       "Mozambique": "mozambicano", "Ethiopia": "etiope", "Kenya": "keniano", "Uganda": "ugandese", "Tanzania": "tanzaniano", "Suriname": "surinamese",
       "Dominican Republic": "dominicano", "Cuba": "cubano", "Haiti": "haitiano", "Trinidad and Tobago": "trinidadiano", "Saudi Arabia": "saudita",
       "Qatar": "qatariota", "Iraq": "iracheno", "Syria": "siriano", "Lebanon": "libanese", "Jordan": "giordano", "China PR": "cinese", "China": "cinese",
       "Indonesia": "indonesiano", "Philippines": "filippino", "Thailand": "thailandese", "Vietnam": "vietnamita", "India": "indiano", "Gabon": "gabonese",
       "Central African Republic": "centrafricano", "Chad": "ciadiano", "Niger": "nigerino", "Libya": "libico", "Sudan": "sudanese", "Rwanda": "ruandese",
       "Burundi": "burundese", "Madagascar": "malgascio", "Mauritania": "mauritano", "Liberia": "liberiano", "Comoros": "comoriano", "Faroe Islands": "faroese",
       "Andorra": "andorrano", "San Marino": "sammarinese", "Gibraltar": "gibraltino", "Liechtenstein": "liechtensteinese", "Azerbaijan": "azero",
       "Guadeloupe": "guadalupense", "Martinique": "martinicano", "Curacao": "curaçaoense", "Puerto Rico": "portoricano", "Guatemala": "guatemalteco",
       "El Salvador": "salvadoregno", "Nicaragua": "nicaraguense", "Malawi": "malawiano", "Namibia": "namibiano", "Botswana": "botswano", "Eritrea": "eritreo"}
ART = {"Inter": "dell'Inter", "Juventus": "della Juventus", "Milan": "del Milan", "Napoli": "del Napoli", "Roma": "della Roma", "Lazio": "della Lazio",
       "Atalanta": "dell'Atalanta", "Fiorentina": "della Fiorentina", "Bologna": "del Bologna", "Torino": "del Torino", "Genoa": "del Genoa",
       "Udinese": "dell'Udinese", "Cagliari": "del Cagliari", "Como": "del Como", "Lecce": "del Lecce", "Parma": "del Parma", "Sassuolo": "del Sassuolo",
       "Frosinone": "del Frosinone", "Monza": "del Monza", "Venezia": "del Venezia", "Verona": "del Verona", "Cremonese": "della Cremonese", "Pisa": "del Pisa",
       "Empoli": "dell'Empoli", "Sampdoria": "della Sampdoria", "Spezia": "dello Spezia", "Palermo": "del Palermo", "Bari": "del Bari", "Salernitana": "della Salernitana"}
ART_A = {k: v.replace("dell'", "all'").replace("della ", "alla ").replace("dello ", "allo ").replace("del ", "al ") for k, v in ART.items()}

# ---------- dati ----------
def load_stats():
    return {"teams": load_json(os.path.join(STATS_DIR, "teams.json"), {}) or {},
            "matches": load_json(os.path.join(STATS_DIR, "matches.json"), {}) or {},
            "players": load_json(os.path.join(STATS_DIR, "players.json"), {}) or {}}

def has_stats(S):
    return bool((S.get("teams") or {}).get("teams"))

def map_teams(S, names):
    """{nome di teams.json: id API-Football} per le squadre presenti in data/stats/teams.json."""
    byn = {norm(n): n for n in names}
    out = {}
    for tid, t in ((S.get("teams") or {}).get("teams") or {}).items():
        api = t.get("name") or ""
        cand = API_ALIAS.get(api) or FANTA_ALIAS.get(api) or api
        site = byn.get(norm(cand))
        if not site:
            na = norm(api)
            for k, v in byn.items():
                if k and (na.startswith(k + " ") or k.startswith(na + " ")):
                    site = v; break
        if site:
            out[site] = int(tid)
    return out

def unmapped_teams(S, mapping):
    ids = set(mapping.values())
    return sorted(t["name"] for tid, t in ((S.get("teams") or {}).get("teams") or {}).items() if int(tid) not in ids)

# ---------- numeri e testo ----------
def it(x, dec=0):
    """Numero in formato italiano: 1.234 · 2,5 · — se manca."""
    if x is None:
        return "—"
    if dec == 0:
        return "{:,}".format(int(round(x))).replace(",", ".")
    return ("{:,.%df}" % dec).format(x).replace(",", "X").replace(".", ",").replace("X", ".")

def pct(x):
    return "—" if x is None else it(x) + "%"

def plural(n, uno, tanti):
    return uno if n == 1 else tanti

def age_of(birth):
    try:
        y, m, d = [int(x) for x in (birth or "").split("-")]
        t = date.today()
        return t.year - y - ((t.month, t.day) < (m, d))
    except Exception:
        return None

def data_it(iso):
    return fdate_it((iso or "") + "T12:00:00Z") if iso else ""

def il_data(iso):
    """'il 22 maggio 1999' / 'l'8 settembre 2004' / 'l'11 giugno 2001'."""
    d = data_it(iso)
    return ("l'" + d) if d.split(" ")[0] in ("8", "11") else ("il " + d)

COUNTRY_IT = {"Italy": "Italia", "Spain": "Spagna", "France": "Francia", "Germany": "Germania", "England": "Inghilterra", "Netherlands": "Paesi Bassi",
              "Belgium": "Belgio", "Portugal": "Portogallo", "Brazil": "Brasile", "Switzerland": "Svizzera", "Croatia": "Croazia", "Poland": "Polonia",
              "Denmark": "Danimarca", "Sweden": "Svezia", "Norway": "Norvegia", "Morocco": "Marocco", "Cameroon": "Camerun", "Ivory Coast": "Costa d'Avorio",
              "Turkey": "Turchia", "Türkiye": "Turchia", "Greece": "Grecia", "USA": "Stati Uniti", "Chile": "Cile", "Mexico": "Messico", "Japan": "Giappone",
              "Scotland": "Scozia", "Wales": "Galles", "Ireland": "Irlanda", "Republic of Ireland": "Irlanda", "Slovakia": "Slovacchia", "Czech Republic": "Repubblica Ceca",
              "Czechia": "Repubblica Ceca", "Hungary": "Ungheria", "Ukraine": "Ucraina", "Bosnia and Herzegovina": "Bosnia ed Erzegovina", "North Macedonia": "Macedonia del Nord",
              "Israel": "Israele", "Egypt": "Egitto", "Finland": "Finlandia", "Iceland": "Islanda", "Austria": "Austria", "Serbia": "Serbia", "Slovenia": "Slovenia",
              "Korea Republic": "Corea del Sud", "South Korea": "Corea del Sud", "Congo DR": "Repubblica Democratica del Congo", "Cape Verde Islands": "Capo Verde",
              "Equatorial Guinea": "Guinea Equatoriale", "Dominican Republic": "Repubblica Dominicana", "Saudi Arabia": "Arabia Saudita", "New Zealand": "Nuova Zelanda",
              "Luxembourg": "Lussemburgo", "Cyprus": "Cipro", "Lithuania": "Lituania", "Latvia": "Lettonia", "Bulgaria": "Bulgaria", "Belarus": "Bielorussia",
              "Georgia": "Georgia", "Armenia": "Armenia", "Guinea-Bissau": "Guinea-Bissau", "South Africa": "Sudafrica", "Ethiopia": "Etiopia", "Kenya": "Kenya"}

def con_team(api_name, site_of=None):
    """'con il Milan', 'con l'Inter', 'con la Roma', 'con il Fulham'."""
    site = (site_of(api_name) if site_of else None) or FANTA_ALIAS.get(api_name) or api_name or "?"
    a = ART.get(site)
    if a:
        return "con " + a.replace("dell'", "l'").replace("della ", "la ").replace("dello ", "lo ").replace("del ", "il ")
    return "con " + ("l'" if norm(site)[:1] in "aeiou" else "il ") + site

def dal(name):
    """'dal Fulham', 'dall'Everton', 'dalla Roma', 'dall'Inter'."""
    a = ART.get(FANTA_ALIAS.get(name, name))
    if a:
        return a.replace("dell'", "dall'").replace("della ", "dalla ").replace("dello ", "dallo ").replace("del ", "dal ")
    return ("dall'" if norm(name)[:1] in "aeiou" else "dal ") + name

def full_name(p):
    """Nome d'uso: primo nome + cognome come lo scrive il feed ('S. Chukwueze' -> Samuel Chukwueze; 'Emerson' resta Emerson)."""
    nm = (p.get("name") or "").strip(); f = (p.get("first") or "").strip(); l = (p.get("last") or "").strip()
    if nm and ". " in nm:
        sur = nm.split(". ", 1)[1].strip()
    else:
        sur = nm or l
    fw = f.split()[0] if f else ""
    if not sur:
        return (fw + " " + l).strip() or ("Giocatore %s" % p.get("id"))
    if not fw:
        return nm or sur          # senza profilo resta la forma del feed ('A. Akarakiri')
    if norm(fw) == norm(sur) or norm(sur).startswith(norm(fw) + " "):
        return sur
    return fw + " " + sur

def ticks(vmax, n=4):
    if vmax <= 0:
        vmax = 1.0
    raw = vmax / float(n)
    mag = 10 ** math.floor(math.log10(raw))
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if step >= raw:
            break
    top = math.ceil(vmax / step - 1e-9) * step
    k = int(round(top / step))
    return [i * step for i in range(k + 1)], top

# ---------- SVG ----------
def _svg(W, H, body, label=""):
    return ('<svg class="chart" viewBox="0 0 %d %d" width="100%%" role="img" aria-label="%s" xmlns="http://www.w3.org/2000/svg">%s</svg>'
            % (W, H, esc(label), body))

def bar_d(x, y, w, h, r=4):
    """Colonna che cresce dalla base: punta arrotondata in alto, base squadrata."""
    if h <= 0 or w <= 0:
        return ""
    r = min(r, w / 2.0, h)
    return "M%.1f %.1f v%.1f a%.1f %.1f 0 0 1 %.1f %.1f h%.1f a%.1f %.1f 0 0 1 %.1f %.1f v%.1f z" % (
        x, y + h, -(h - r), r, r, r, -r, w - 2 * r, r, r, r, r, h - r)

def hbar_d(x, y, w, h, r=4):
    """Barra orizzontale: punta arrotondata a destra, base squadrata a sinistra."""
    if h <= 0 or w <= 0:
        return ""
    r = min(r, h / 2.0, w)
    return "M%.1f %.1f h%.1f a%.1f %.1f 0 0 1 %.1f %.1f v%.1f a%.1f %.1f 0 0 1 %.1f %.1f h%.1f z" % (
        x, y, w - r, r, r, r, r, h - 2 * r, r, r, -r, r, -(w - r))

def legend(items):
    return '<div class="legend2">' + "".join('<span><i style="background:%s"></i>%s</span>' % (c, esc(n)) for n, c in items) + "</div>"

def chart_cols(cats, series, colors, fmt=None, W=480, H=230, label=""):
    """Colonne raggruppate. cats: etichette x; series: [(nome, [valori o None])]. Etichetta diretta solo sul massimo di ogni serie."""
    fmt = fmt or (lambda v: it(v, 1 if v != int(v) else 0))
    L, R, T, B = 40, 12, 18, 30
    vals = [v for _, vs in series for v in vs if v is not None]
    tk, top = ticks(max([max(v, 0) for v in vals] + [0.0001]))
    pw, ph = W - L - R, H - T - B
    def y(v):
        return T + ph - (v / top) * ph
    out = []
    for t in tk:
        yy = y(t)
        out.append('<line class="%s" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % ("base" if t == 0 else "grid", L, W - R, yy, yy))
        out.append('<text class="ax" x="%d" y="%.1f" text-anchor="end" dy="4">%s</text>' % (L - 6, yy, esc(fmt(t))))
    n, k = max(len(cats), 1), max(len(series), 1)
    slot = pw / float(n)
    bw = max(3.0, min(24.0, (slot * 0.72 - 2 * (k - 1)) / k))
    grp = k * bw + 2 * (k - 1)
    maxima = [max([v for v in vs if v is not None] or [None]) for _, vs in series]
    for i, c in enumerate(cats):
        x0 = L + i * slot + (slot - grp) / 2.0
        out.append('<text class="ax" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (L + i * slot + slot / 2.0, H - 10, esc(c)))
        for j, (name, vs) in enumerate(series):
            v = vs[i] if i < len(vs) else None
            if v is None:
                continue
            x = x0 + j * (bw + 2); yy = y(max(v, 0)); h = T + ph - yy
            out.append('<path d="%s" fill="%s"><title>%s · %s: %s</title></path>' % (bar_d(x, yy, bw, h), colors[j], esc(c), esc(name), esc(fmt(v))))
            if v == maxima[j] and v > 0:
                out.append('<text class="lb" x="%.1f" y="%.1f" text-anchor="middle">%s</text>' % (x + bw / 2.0, yy - 5, esc(fmt(v))))
    return _svg(W, H, "".join(out), label)

def chart_hbars(items, color=C1, fmt=None, W=480, labw=120, label=""):
    """Barre orizzontali ordinate, valore alla punta. items: [(etichetta, valore, titolo)]."""
    fmt = fmt or (lambda v: it(v))
    bh, gap, T = 18, 8, 6
    items = sorted(items, key=lambda x: -x[1])
    H = T + len(items) * (bh + gap) + 4
    vmax = max([v for _, v, _ in items] + [0.0001])
    pw = W - labw - 56
    out = ['<line class="base" x1="%d" x2="%d" y1="%d" y2="%d"/>' % (labw, labw, T, H - 4)]
    for i, (lab, v, title) in enumerate(items):
        yy = T + i * (bh + gap); w = pw * v / vmax
        out.append('<text class="ax" x="%d" y="%.1f" text-anchor="end" dy="4">%s</text>' % (labw - 8, yy + bh / 2.0, esc(lab[:22])))
        out.append('<path d="%s" fill="%s"><title>%s</title></path>' % (hbar_d(labw, yy, w, bh), color, esc(title or (lab + ": " + fmt(v)))))
        out.append('<text class="lb" x="%.1f" y="%.1f" dy="4">%s</text>' % (labw + w + 6, yy + bh / 2.0, esc(fmt(v))))
    return _svg(W, H, "".join(out), label)

def chart_hgroup(cats, series, colors, fmt=None, W=480, labw=118, label=""):
    """Barre orizzontali raggruppate (confronto fra due stagioni sulla stessa voce): etichetta a sinistra, valore alla punta."""
    fmt = fmt or (lambda v: it(v, 2))
    k = max(len(series), 1); bh, gap, rowgap, T = 12, 2, 10, 6
    rowh = k * bh + (k - 1) * gap
    H = T + len(cats) * (rowh + rowgap) + 4
    vmax = max([v for _, vs in series for v in vs if v is not None] + [0.0001])
    pw = W - labw - 52
    out = ['<line class="base" x1="%d" x2="%d" y1="%d" y2="%d"/>' % (labw, labw, T, H - 4)]
    for i, c in enumerate(cats):
        y0 = T + i * (rowh + rowgap)
        out.append('<text class="ax" x="%d" y="%.1f" text-anchor="end" dy="4">%s</text>' % (labw - 8, y0 + rowh / 2.0, esc(c)))
        for j, (name, vs) in enumerate(series):
            v = vs[i] if i < len(vs) else None
            yy = y0 + j * (bh + gap)
            if v is None:
                out.append('<text class="ax" x="%d" y="%.1f" dy="4">—</text>' % (labw + 6, yy + bh / 2.0))
                continue
            w = pw * v / vmax
            out.append('<path d="%s" fill="%s"><title>%s · %s: %s</title></path>' % (hbar_d(labw, yy, w, bh), colors[j], esc(c), esc(name), esc(fmt(v))))
            out.append('<text class="lb" x="%.1f" y="%.1f" dy="4">%s</text>' % (labw + w + 6, yy + bh / 2.0, esc(fmt(v))))
    return _svg(W, H, "".join(out), label)

def chart_stack(rows, colors, W=480, labw=84, label=""):
    """Barre orizzontali impilate (parte-tutto) con 2px di aria fra i segmenti. rows: [(etichetta, [(nome, valore)])]."""
    bh, gap, T = 22, 12, 6
    H = T + len(rows) * (bh + gap)
    total = max([sum(v for _, v in segs) for _, segs in rows] + [1])
    pw = W - labw - 12
    out = []
    for i, (lab, segs) in enumerate(rows):
        yy = T + i * (bh + gap); x = labw
        out.append('<text class="ax" x="%d" y="%.1f" text-anchor="end" dy="4">%s</text>' % (labw - 8, yy + bh / 2.0, esc(lab)))
        for j, (name, v) in enumerate(segs):
            if not v:
                continue
            w = pw * v / float(total) - 2
            if w <= 0:
                continue
            out.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" rx="%d" fill="%s"><title>%s · %s: %s</title></rect>'
                       % (x, yy, w, bh, 3, colors[j], esc(lab), esc(name), it(v)))
            if w >= 22:
                out.append('<text x="%.1f" y="%.1f" text-anchor="middle" dy="4" font-size="12.5" font-weight="700" fill="%s">%s</text>'
                           % (x + w / 2.0, yy + bh / 2.0, "#161b21" if colors[j] == GRAY else "#fff", it(v)))
            x += w + 2
    return _svg(W, H, "".join(out), label)

def chart_line(cats, series, colors, fmt=None, W=480, H=230, top=None, label=""):
    """Linee 2px con marcatori ad anello; etichetta del valore solo all'ultimo punto di ogni serie."""
    fmt = fmt or (lambda v: it(v))
    L, R, T, B = 40, 44, 18, 30
    vals = [v for _, vs in series for v in vs if v is not None]
    tk, tp = ticks(max(vals + [0.0001]))
    if top:
        tp = top; tk = [tp * i / 4.0 for i in range(5)]
    pw, ph = W - L - R, H - T - B
    n = max(len(cats), 1)
    def x(i):
        return L + (pw / 2.0 if n == 1 else i * pw / float(n - 1))
    def y(v):
        return T + ph - (v / float(tp)) * ph
    out = []
    for t in tk:
        yy = y(t)
        out.append('<line class="%s" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % ("base" if t == 0 else "grid", L, W - R, yy, yy))
        out.append('<text class="ax" x="%d" y="%.1f" text-anchor="end" dy="4">%s</text>' % (L - 6, yy, esc(fmt(t))))
    for i, c in enumerate(cats):
        out.append('<text class="ax" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x(i), H - 10, esc(c)))
    for j, (name, vs) in enumerate(series):
        pts = [(x(i), y(v)) for i, v in enumerate(vs) if v is not None]
        if len(pts) >= 2:
            out.append('<polyline fill="none" stroke="%s" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="%s"/>'
                       % (colors[j], " ".join("%.1f,%.1f" % p for p in pts)))
        last = None
        for i, v in enumerate(vs):
            if v is None:
                continue
            out.append('<circle class="ring" cx="%.1f" cy="%.1f" r="5" fill="%s"><title>%s · %s: %s</title></circle>' % (x(i), y(v), colors[j], esc(cats[i]), esc(name), esc(fmt(v))))
            last = (i, v)
        if last:
            out.append('<text class="lb" x="%.1f" y="%.1f" dy="4">%s</text>' % (x(last[0]) + 9, y(last[1]), esc(fmt(last[1]))))
    return _svg(W, H, "".join(out), label)

def chart_radar(axes, series, colors, W=420, label=""):
    """Radar normalizzato: axes [(etichetta, massimo)], series [(nome, [valori])]. Anelli hairline al 25/50/75/100%."""
    cx = cy = W / 2.0; R = W / 2.0 - 78
    n = len(axes)
    def pt(i, f):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return (cx + R * f * math.cos(a), cy + R * f * math.sin(a))
    out = []
    for f in (0.25, 0.5, 0.75, 1.0):
        out.append('<polygon class="grid" fill="none" points="%s"/>' % " ".join("%.1f,%.1f" % pt(i, f) for i in range(n)))
    for i, (lab, _) in enumerate(axes):
        px, py = pt(i, 1.0); lx, ly = pt(i, 1.17)
        out.append('<line class="grid" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (cx, cy, px, py))
        anchor = "middle" if abs(lx - cx) < 8 else ("start" if lx > cx else "end")
        out.append('<text class="ax" x="%.1f" y="%.1f" text-anchor="%s" dy="4">%s</text>' % (lx, ly, anchor, esc(lab)))
    for j, (name, vs) in enumerate(series):
        fs = [min(1.0, (v or 0) / float(axes[i][1] or 1)) for i, v in enumerate(vs)]
        pts = [pt(i, f) for i, f in enumerate(fs)]
        out.append('<polygon points="%s" fill="%s" fill-opacity=".12" stroke="%s" stroke-width="2" stroke-linejoin="round"/>'
                   % (" ".join("%.1f,%.1f" % p for p in pts), colors[j], colors[j]))
        for i, (px, py) in enumerate(pts):
            out.append('<circle class="ring" cx="%.1f" cy="%.1f" r="4.5" fill="%s"><title>%s · %s: %s</title></circle>'
                       % (px, py, colors[j], esc(axes[i][0]), esc(name), it(vs[i], 2) if vs[i] is not None else "—"))
    return _svg(W, W, "".join(out), label)

def kpi(label, value, sub=""):
    return '<div class="kpi"><div class="l">%s</div><div class="v">%s</div>%s</div>' % (esc(label), value, ('<div class="s">%s</div>' % esc(sub)) if sub else "")

def form_html(form, n=10):
    m = {"W": ("V", "w"), "D": ("N", "d"), "L": ("P", "l")}
    return '<span class="form">' + "".join('<i class="%s" title="%s">%s</i>' % (m[c][1], {"W": "vittoria", "D": "pareggio", "L": "sconfitta"}[c], m[c][0])
                                            for c in (form or "")[-n:] if c in m) + "</span>"

def card(title, inner, legend_html=""):
    return '<div class="card"><h3>%s</h3><div class="in">%s%s</div></div>' % (title, legend_html, inner)

# ---------- squadre ----------
def team_matches(S, tid):
    fx = [f for f in ((S.get("matches") or {}).get("fixtures") or {}).values() if tid in (f.get("home"), f.get("away")) and f.get("round")]
    fx.sort(key=lambda f: (f["round"], f["date"]))
    rows = []
    for f in fx:
        home = f["home"] == tid
        me = (f.get("stats") or {}).get(str(tid)) or {}
        opp_id = f["away"] if home else f["home"]
        opp = (f.get("stats") or {}).get(str(opp_id)) or {}
        gf, ga = (f["goals"][0], f["goals"][1]) if home else (f["goals"][1], f["goals"][0])
        rows.append({"round": f["round"], "date": f["date"], "home": home, "opp_id": opp_id, "opp": f["away_name"] if home else f["home_name"],
                     "gf": gf, "ga": ga, "res": "W" if (gf or 0) > (ga or 0) else ("L" if (gf or 0) < (ga or 0) else "D"), "me": me, "opp_st": opp})
    return rows

def avg(vals, dec=1):
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), dec) if v else None

def team_stats_html(S, T, nome, tid, upd=""):
    """Sezione 'Statistiche' della pagina squadra: KPI, forma, 5 grafici con tabella, partita per partita."""
    TS = ((S.get("teams") or {}).get("teams") or {}).get(str(tid))
    if not TS:
        return ""
    lg = ((S.get("teams") or {}).get("leagues") or {}).get(str(TS.get("league")), {})
    row = next((r for r in lg.get("standings", []) if r["team_id"] == tid), None)
    ms = team_matches(S, tid)
    fx = TS.get("fixtures") or {}
    played = (fx.get("played") or {}).get("total") or 0
    if not played and not row:
        return ""
    gf, ga = TS.get("goals_for") or {}, TS.get("goals_against") or {}
    poss = avg([m["me"].get("possession") for m in ms]); xg = avg([m["me"].get("xg") for m in ms], 2)
    shots = avg([m["me"].get("shots") for m in ms]); pk = avg([m["me"].get("passes_pct") for m in ms])
    b = ["<h2>Statistiche %s</h2>" % esc(SEASON),
         '<p class="ph">%s · dati API-Football aggiornati <time>%s</time> · xG = expected goals, la qualità delle occasioni create.</p>'
         % (esc(lg.get("name") or ""), esc(fdate_it(upd or (S.get("teams") or {}).get("updated"), True)))]
    k = []
    if row:
        k.append(kpi("Classifica", "%sª" % row["rank"], "%s punti" % it(row["points"])))
    k.append(kpi("Partite", it(played), "%s V · %s N · %s P" % (it((fx.get("wins") or {}).get("total") or 0), it((fx.get("draws") or {}).get("total") or 0), it((fx.get("loses") or {}).get("total") or 0))))
    k.append(kpi("Gol fatti", it((gf.get("total") or {}).get("total") or 0), "media %s a partita" % it((gf.get("avg") or {}).get("total"), 2)))
    k.append(kpi("Gol subiti", it((ga.get("total") or {}).get("total") or 0), "media %s a partita" % it((ga.get("avg") or {}).get("total"), 2)))
    k.append(kpi("Porte inviolate", it((TS.get("clean_sheet") or {}).get("total") or 0), "senza segnare: %s" % it((TS.get("failed_to_score") or {}).get("total") or 0)))
    if poss is not None:
        k.append(kpi("Possesso medio", pct(poss), "passaggi riusciti %s" % pct(pk)))
    if xg is not None:
        k.append(kpi("xG a partita", it(xg, 2), "tiri a partita %s" % it(shots, 1)))
    b.append('<div class="kpis">' + "".join(k) + "</div>")
    if TS.get("form"):
        b.append('<p class="ph">Forma (ultime partite, dalla più vecchia): ' + form_html(TS["form"]) + "</p>")
    # gol per fase di gara
    cats = list(INTERVALS)
    fm, am = gf.get("minute") or {}, ga.get("minute") or {}
    extra_f = sum(v for kk, v in fm.items() if kk not in INTERVALS); extra_a = sum(v for kk, v in am.items() if kk not in INTERVALS)
    sf = [fm.get(c, 0) for c in cats]; sa = [am.get(c, 0) for c in cats]
    if extra_f or extra_a:
        cats.append("90+"); sf.append(extra_f); sa.append(extra_a)
    tot_f = (gf.get("total") or {}).get("total") or 0; tot_a = (ga.get("total") or {}).get("total") or 0
    miss_note = ""
    if sum(sf) != tot_f or sum(sa) != tot_a:   # il provider attribuisce il minuto con ritardo: lo diciamo invece di far quadrare i conti a mano
        miss_note = '<p class="small">Gol senza minuto registrato dal provider: %s fatti, %s subiti (non compaiono nel grafico).</p>' % (it(max(tot_f - sum(sf), 0)), it(max(tot_a - sum(sa), 0)))
    tbl = (miss_note + '<table><thead><tr><th class="l">Minuti</th>' + "".join("<th>%s</th>" % esc(c) for c in cats) + "</tr></thead><tbody>"
           '<tr><td class="l">Fatti</td>' + "".join("<td>%s</td>" % it(v) for v in sf) + '</tr><tr><td class="l">Subiti</td>' + "".join("<td>%s</td>" % it(v) for v in sa) + "</tr></tbody></table>")
    g1 = card("Gol per fase di gara", chart_cols(cats, [("Fatti", sf), ("Subiti", sa)], [C1, C2], label="Gol fatti e subiti per fase di gara") + tbl, legend([("Fatti", C1), ("Subiti", C2)]))
    # casa e trasferta
    rows = []
    for lab, side in (("Casa", "home"), ("Trasferta", "away")):
        rows.append((lab, [("Vittorie", (fx.get("wins") or {}).get(side) or 0), ("Pareggi", (fx.get("draws") or {}).get(side) or 0), ("Sconfitte", (fx.get("loses") or {}).get(side) or 0)]))
    tbl = ('<table><thead><tr><th class="l"></th><th>PG</th><th>V</th><th>N</th><th>P</th><th>GF</th><th>GS</th></tr></thead><tbody>' +
           "".join('<tr><td class="l">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
               lab, it((fx.get("played") or {}).get(side) or 0), it((fx.get("wins") or {}).get(side) or 0), it((fx.get("draws") or {}).get(side) or 0),
               it((fx.get("loses") or {}).get(side) or 0), it((gf.get("total") or {}).get(side) or 0), it((ga.get("total") or {}).get(side) or 0)) for lab, side in (("Casa", "home"), ("Trasferta", "away"))) + "</tbody></table>")
    g2 = card("Casa e trasferta", chart_stack(rows, [C1, GRAY, C2], label="Vittorie, pareggi e sconfitte in casa e in trasferta") + tbl, legend([("Vittorie", C1), ("Pareggi", GRAY), ("Sconfitte", C2)]))
    b.append('<div class="grid2"><div>%s</div><div>%s</div></div>' % (g1, g2))
    # per giornata: gol e xG, possesso, tiri
    if ms:
        cats = ["G%d" % m["round"] for m in ms]
        gols = [m["gf"] for m in ms]; xgs = [m["me"].get("xg") for m in ms]
        tbl = ('<table><thead><tr><th class="l">Giornata</th>' + "".join("<th>%s</th>" % c for c in cats) + "</tr></thead><tbody>"
               '<tr><td class="l">Gol fatti</td>' + "".join("<td>%s</td>" % it(v) for v in gols) + "</tr>" +
               ('<tr><td class="l">xG</td>' + "".join("<td>%s</td>" % it(v, 2) for v in xgs) + "</tr>" if any(x is not None for x in xgs) else "") + "</tbody></table>")
        series = [("Gol fatti", gols)] + ([("xG", xgs)] if any(x is not None for x in xgs) else [])
        g3 = card("Gol e xG per giornata", chart_cols(cats, series, [C1, C2], fmt=lambda v: it(v, 1 if v != int(v) else 0), label="Gol fatti ed expected goals per giornata") + tbl,
                  legend([(n, c) for (n, _), c in zip(series, [C1, C2])]) if len(series) > 1 else "")
        poss_l = [m["me"].get("possession") for m in ms]
        if any(p is not None for p in poss_l):
            tbl = ('<table><thead><tr><th class="l">Giornata</th>' + "".join("<th>%s</th>" % c for c in cats) + "</tr></thead><tbody>"
                   '<tr><td class="l">Possesso</td>' + "".join("<td>%s</td>" % pct(v) for v in poss_l) + "</tr></tbody></table>")
            g4 = card("Possesso palla per giornata", chart_line(cats, [("Possesso", poss_l)], [C1], fmt=lambda v: it(v) + "%", top=100, label="Possesso palla per giornata") + tbl)
        else:
            g4 = ""
        b.append('<div class="grid2"><div>%s</div><div>%s</div></div>' % (g3, g4))
        sh = [m["me"].get("shots") for m in ms]; so = [m["me"].get("shots_on") for m in ms]
        if any(v is not None for v in sh):
            tbl = ('<table><thead><tr><th class="l">Giornata</th>' + "".join("<th>%s</th>" % c for c in cats) + "</tr></thead><tbody>"
                   '<tr><td class="l">Tiri</td>' + "".join("<td>%s</td>" % it(v) for v in sh) + '</tr><tr><td class="l">In porta</td>' + "".join("<td>%s</td>" % it(v) for v in so) + "</tr></tbody></table>")
            g5 = card("Tiri per giornata", chart_cols(cats, [("Tiri", sh), ("In porta", so)], [C1, C2], label="Tiri totali e in porta per giornata") + tbl, legend([("Tiri", C1), ("In porta", C2)]))
        else:
            g5 = ""
        lu = [(l["formation"] or "?", l["played"], "%s: %s partite" % (l["formation"], it(l["played"]))) for l in (TS.get("lineups") or []) if l.get("played")]
        g6 = card("Moduli usati", chart_hbars(lu, C1, label="Moduli schierati e numero di partite") +
                  '<table><thead><tr><th class="l">Modulo</th><th>Partite</th></tr></thead><tbody>' + "".join('<tr><td class="l">%s</td><td>%s</td></tr>' % (esc(f), it(n)) for f, n, _ in sorted(lu, key=lambda x: -x[1])) + "</tbody></table>") if lu else ""
        b.append('<div class="grid2"><div>%s</div><div>%s</div></div>' % (g5, g6))
        # partita per partita
        b.append('<div class="card"><h3>Partita per partita</h3><div style="overflow-x:auto"><table><thead><tr><th>G</th><th class="l">Data</th><th class="l">Avversario</th><th>Risultato</th>'
                 '<th>Possesso</th><th>Tiri (in porta)</th><th>xG</th><th>Corner</th><th>Parate</th><th>Passaggi ok</th></tr></thead><tbody>')
        for m in ms:
            st = m["me"]
            opp = T.api_link(m["opp_id"], m["opp"]) if hasattr(T, "api_link") else esc(m["opp"])
            res = '<span class="form"><i class="%s">%s-%s</i></span>' % ({"W": "w", "D": "d", "L": "l"}[m["res"]], m["gf"], m["ga"])
            b.append('<tr><td>%d</td><td class="l">%s</td><td class="l">%s%s</td><td>%s</td><td>%s</td><td>%s (%s)</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                m["round"], esc(fdate_it(m["date"], False, True)), opp, "" if m["home"] else ' <span class="small">(fuori casa)</span>', res, pct(st.get("possession")),
                it(st.get("shots")), it(st.get("shots_on")), it(st.get("xg"), 2), it(st.get("corners")), it(st.get("saves")), pct(st.get("passes_pct"))))
        b.append("</tbody></table></div></div>")
    return "".join(b)

# ---------- giocatori: dati derivati ----------
KEYS = [("app", "games", "appearences"), ("lineups", "games", "lineups"), ("min", "games", "minutes"), ("gol", "goals", "total"), ("assist", "goals", "assists"),
        ("conceded", "goals", "conceded"), ("saves", "goals", "saves"), ("shots", "shots", "total"), ("shots_on", "shots", "on"), ("passes", "passes", "total"),
        ("key", "passes", "key"), ("tackles", "tackles", "total"), ("blocks", "tackles", "blocks"), ("inter", "tackles", "interceptions"),
        ("duels", "duels", "total"), ("duels_won", "duels", "won"), ("drib_att", "dribbles", "attempts"), ("drib_ok", "dribbles", "success"),
        ("fouls_drawn", "fouls", "drawn"), ("fouls_comm", "fouls", "committed"), ("yellow", "cards", "yellow"), ("red", "cards", "red"),
        ("pen_scored", "penalty", "scored"), ("pen_missed", "penalty", "missed"), ("pen_saved", "penalty", "saved"), ("sub_in", "substitutes", "in"), ("bench", "substitutes", "bench")]

def agg(blocks):
    a = {k: 0 for k, _, _ in KEYS}; rs = []
    for b in blocks or []:
        for k, g, f in KEYS:
            a[k] += (b.get(g) or {}).get(f) or 0
        g = b.get("games") or {}
        if g.get("rating"):
            rs.append((float(g["rating"]), g.get("appearences") or 1))
    a["rating"] = round(sum(r * n for r, n in rs) / sum(n for _, n in rs), 2) if rs else None
    return a

def p90(a, k):
    return round(a[k] * 90.0 / a["min"], 2) if a and a.get("min") else None

def main_block(blocks):
    """Il campionato della stagione: il blocco con più minuti fra le leghe nazionali (fuori nazionale e coppe se c'è un campionato noto)."""
    cl = [b for b in (blocks or []) if (b.get("league") or {}).get("country") not in ("World",)]
    tops = [b for b in cl if (b.get("league") or {}).get("name") in TOP_LEAGUES]
    pool = tops or cl or (blocks or [])
    return max(pool, key=lambda b: ((b.get("games") or {}).get("minutes") or 0)) if pool else None

RADAR_AXES = [("Gol+assist", lambda a: (a["gol"] + a["assist"])), ("Tiri", lambda a: a["shots"]), ("Pass. chiave", lambda a: a["key"]),
              ("Dribbling", lambda a: a["drib_ok"]), ("Duelli vinti", lambda a: a["duels_won"]), ("Recuperi", lambda a: a["tackles"] + a["inter"])]
CMP_ROWS = [("Presenze", "app", 0, False), ("Da titolare", "lineups", 0, False), ("Minuti", "min", 0, False), ("Gol", "gol", 0, True), ("Assist", "assist", 0, True),
            ("Tiri", "shots", 0, True), ("Tiri in porta", "shots_on", 0, True), ("Passaggi", "passes", 0, True), ("Passaggi chiave", "key", 0, True),
            ("Dribbling riusciti", "drib_ok", 0, True), ("Dribbling tentati", "drib_att", 0, True), ("Duelli vinti", "duels_won", 0, True), ("Duelli totali", "duels", 0, True),
            ("Contrasti", "tackles", 0, True), ("Intercetti", "inter", 0, True), ("Falli subiti", "fouls_drawn", 0, True), ("Falli commessi", "fouls_comm", 0, True),
            ("Ammonizioni", "yellow", 0, False), ("Espulsioni", "red", 0, False)]
CMP_GK = [("Presenze", "app", 0, False), ("Da titolare", "lineups", 0, False), ("Minuti", "min", 0, False), ("Parate", "saves", 0, True), ("Gol subiti", "conceded", 0, True),
          ("Rigori parati", "pen_saved", 0, False), ("Passaggi", "passes", 0, True), ("Ammonizioni", "yellow", 0, False), ("Espulsioni", "red", 0, False)]

def per90(a, fn):
    return round(fn(a) * 90.0 / a["min"], 2) if a and a.get("min") else None

def role_reference(players):
    """Per ogni ruolo: valori di riferimento per 90' (90° percentile dei pari ruolo con almeno 900' nel campionato della stagione scorsa)
    e media di ruolo, sugli assi del radar."""
    ref = {}
    for pos in ROLE_ORDER:
        rows = []
        for p in players.values():
            if p.get("position") != pos:
                continue
            mb = main_block(p.get("prev"))
            a = agg([mb]) if mb else None
            if a and a["min"] >= 900:
                rows.append([per90(a, fn) for _, fn in RADAR_AXES])
        if not rows:
            continue
        axes_max, mean = [], []
        for i in range(len(RADAR_AXES)):
            col = sorted(v for r in rows for v in [r[i]] if v is not None)
            if not col:
                axes_max.append(1.0); mean.append(0.0); continue
            axes_max.append(max(col[min(len(col) - 1, int(len(col) * 0.9))], 0.05))
            mean.append(round(sum(col) / len(col), 2))
        ref[pos] = {"max": axes_max, "mean": mean, "n": len(rows)}
    return ref

def player_urls(players):
    """{id: /giocatori/slug.html}; omonimi -> suffisso con l'id (stabile)."""
    slugs = {}
    for pid, p in players.items():
        s = slugify(full_name(p)) or ("giocatore-" + str(pid))
        slugs.setdefault(s, []).append(int(pid))
    out = {}
    for s, ids in slugs.items():
        for i in ids:
            out[i] = "/giocatori/" + (s if len(ids) == 1 else s + "-" + str(i)) + ".html"
    return out

def build_ctx(D, S, T):
    """Dati derivati condivisi da tutte le schede: URL, voti FantaTB per giocatore, titolarità, quotazioni, riferimenti di ruolo."""
    P = (S.get("players") or {}).get("players") or {}
    voti = {}
    for md, V in (D.get("voti") or {}).items():
        for r in V.get("ratings") or []:
            voti.setdefault(r["player_id"], {})[md] = r
    tit = {s["player_id"]: s for s in ((D.get("titolari") or {}).get("status") or [])}
    listone = {p["id"]: p for p in (D.get("listone") or {}).get("players") or []}
    return {"P": P, "urls": player_urls(P), "voti": voti, "tit": tit, "listone": listone, "ref": role_reference(P),
            "updated": (S.get("players") or {}).get("updated") or ""}

def plink(ctx, pid, text, cls=""):
    u = (ctx or {}).get("urls", {}).get(pid)
    return ('<a href="%s"%s>%s</a>' % (u, (' class="%s"' % cls) if cls else "", esc(text))) if u else esc(text)

def find_by_name(ctx, name, team_api_id=None):
    """Giocatore per nome completo (rose football-data: 'Mike Maignan'), opzionalmente nella squadra data."""
    n = norm(name)
    if not n:
        return None
    best = None
    for pid, p in ctx["P"].items():
        if team_api_id and p.get("team") != team_api_id:
            continue
        if norm(full_name(p)) == n or norm((p.get("first") or "") + " " + (p.get("last") or "")) == n:
            return p
        last = norm(p.get("last") or "")
        if last and n.endswith(" " + last) and (norm(p.get("first") or "").split(" ")[0] == n.split(" ")[0]):
            best = best or p
    return best

# ---------- giocatori: pagina ----------
def transfer_type_it(t):
    t = (t or "").strip()
    if not t or t in ("N/A",):
        return ""
    low = t.lower()
    if low == "loan":
        return "prestito"
    if "free" in low:
        return "a parametro zero"
    if "return" in low or "back from loan" in low:
        return "rientro dal prestito"
    if low == "swap":
        return "scambio"
    if t.startswith("€") or t.startswith("$") or t.startswith("£"):
        return "a titolo definitivo, " + t.replace("€ ", "").replace("M", " milioni di euro").replace("K", " mila euro")
    return t

def describe(p, team_site, a_cur, a_prev, mb, role_it, ctx, n_md):
    """Descrizione in italiano costruita SOLO dai dati strutturati (niente testo libero da modelli)."""
    full = full_name(p); s = []
    naz = NAZ.get(p.get("nationality") or "")
    team_txt = ART.get(team_site or "", "del " + (team_site or p.get("team_name") or ""))
    s.append("%s è un %s%s %s%s." % (full, role_it, (" " + naz) if naz else "", team_txt, (", maglia numero %s" % p["number"]) if p.get("number") else ""))
    if not naz and p.get("nationality"):
        s[-1] = s[-1][:-1] + " (nazionalità: %s)." % p["nationality"]
    b = p.get("birth") or {}
    age = age_of(b.get("date"))
    if b.get("date"):
        s.append("Nato %s%s %s, ha %s anni%s." % (("a " + b["place"]) if b.get("place") else "", (" (%s)" % COUNTRY_IT.get(b["country"], b["country"])) if b.get("country") and b.get("place") else "",
                                                    il_data(b["date"]), age if age is not None else "—",
                                                    (", è alto %s cm e pesa %s kg" % (it(p["height"]), it(p["weight"]))) if p.get("height") and p.get("weight") else
                                                    ((", è alto %s cm" % it(p["height"])) if p.get("height") else "")))
    trs = p.get("transfers") or []
    arrivo = next((t for t in reversed(trs) if t["to"].get("id") == p.get("team")), None)
    if arrivo and arrivo["from"].get("name"):
        tipo = transfer_type_it(arrivo.get("type"))
        s.append("È arrivato %s %s %s%s." % (ART_A.get(team_site or "", "al " + (team_site or "")), dal(arrivo["from"]["name"]),
                                            il_data(arrivo["date"]), (" (" + tipo + ")") if tipo else ""))
    clubs = []
    for t in trs:
        for side in ("from", "to"):
            n = t[side].get("name")
            if n and n not in clubs:
                clubs.append(n)
    if len(clubs) >= 3:
        s.append("In carriera ha vestito almeno %d maglie: %s." % (len(clubs), ", ".join(clubs)))
    if mb and a_prev and a_prev["app"]:
        lg = (mb.get("league") or {}); tm = (mb.get("team") or {})
        if p.get("position") == "Goalkeeper":
            s.append("Nella stagione %s, in %s %s, ha giocato %d %s (%s minuti) subendo %d gol, con %s parate%s." % (
                PREV_LABEL, lg.get("name") or "campionato", con_team(tm.get("name") or "?"), a_prev["app"], plural(a_prev["app"], "partita", "partite"), it(a_prev["min"]),
                a_prev["conceded"], it(a_prev["saves"]), (" e un rating medio di %s" % it(a_prev["rating"], 2)) if a_prev.get("rating") else ""))
        else:
            s.append("Nella stagione %s, in %s %s, ha giocato %d %s (%d da titolare, %s minuti) con %d gol e %d assist%s." % (
                PREV_LABEL, lg.get("name") or "campionato", con_team(tm.get("name") or "?"), a_prev["app"], plural(a_prev["app"], "partita", "partite"), a_prev["lineups"], it(a_prev["min"]),
                a_prev["gol"], a_prev["assist"], (", rating medio %s" % it(a_prev["rating"], 2)) if a_prev.get("rating") else ""))
    if a_cur and a_cur["app"]:
        vs = ctx["voti"].get(p["id"]) or {}
        vv = [r["voto"] for r in vs.values() if r.get("voto") is not None]
        resa = ("%d %s e %s %s" % (a_cur["conceded"], plural(a_cur["conceded"], "gol subito", "gol subiti"), it(a_cur["saves"]), plural(a_cur["saves"], "parata", "parate"))) if p.get("position") == "Goalkeeper" else ("%d gol e %d assist" % (a_cur["gol"], a_cur["assist"]))
        s.append("In questa Serie A, dopo %d %s, ha %d %s per %s minuti, %s%s." % (
            n_md, plural(n_md, "giornata", "giornate"), a_cur["app"], plural(a_cur["app"], "presenza", "presenze"), it(a_cur["min"]), resa,
            ("; il suo voto medio FantaTB è %s" % it(sum(vv) / len(vv), 2)) if vv else ""))
    elif n_md:
        s.append("In questa Serie A non è ancora sceso in campo.")
    li = ctx["listone"].get(p["id"]); st = ctx["tit"].get(p["id"])
    if li:
        s.append("Nel listone FantaTB è quotato %s %s%s." % (it(li.get("price")), plural(li.get("price") or 0, "credito", "crediti"), (" e il suo indice di titolarità per la prossima giornata è %s%%" % st["prob"]) if st and st.get("prob") is not None else ""))
    return " ".join(s)

def cmp_table(rows, a_prev, a_cur, lab_prev, lab_cur):
    h = ['<div style="overflow-x:auto"><table class="cmp"><thead><tr><th class="l">Voce</th><th>%s</th><th>per 90\'</th><th>%s</th><th>per 90\'</th></tr></thead><tbody>' % (esc(lab_prev), esc(lab_cur))]
    for lab, k, dec, show90 in rows:
        vp = a_prev[k] if a_prev else None; vc = a_cur[k] if a_cur else None
        h.append('<tr><td class="l">%s</td><td>%s</td><td class="small">%s</td><td>%s</td><td class="small">%s</td></tr>' % (
            esc(lab), it(vp, dec), it(p90(a_prev, k), 2) if show90 and a_prev and a_prev.get("min") else "", it(vc, dec), it(p90(a_cur, k), 2) if show90 and a_cur and a_cur.get("min") else ""))
    h.append('<tr><td class="l">Rating medio</td><td>%s</td><td></td><td>%s</td><td></td></tr>' % (it(a_prev.get("rating") if a_prev else None, 2), it(a_cur.get("rating") if a_cur else None, 2)))
    h.append("</tbody></table></div>")
    return "".join(h)

def blocks_table(blocks, gk=False):
    if not blocks:
        return '<p class="small">Nessuna statistica disponibile.</p>'
    h = ['<div style="overflow-x:auto"><table><thead><tr><th class="l">Competizione</th><th class="l">Squadra</th><th>Pres.</th><th>Tit.</th><th>Min</th>' +
         ("<th>Gol subiti</th><th>Parate</th>" if gk else "<th>Gol</th><th>Assist</th>") + "<th>Gialli</th><th>Rossi</th><th>Rating</th></tr></thead><tbody>"]
    for b in sorted(blocks, key=lambda b: -((b.get("games") or {}).get("minutes") or 0)):
        g = b.get("games") or {}; go = b.get("goals") or {}; c = b.get("cards") or {}
        h.append('<tr><td class="l">%s</td><td class="l">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            esc((b.get("league") or {}).get("name")), esc((b.get("team") or {}).get("name")), it(g.get("appearences") or 0), it(g.get("lineups") or 0), it(g.get("minutes") or 0),
            it(go.get("conceded") or 0) if gk else it(go.get("total") or 0), it(go.get("saves") or 0) if gk else it(go.get("assists") or 0),
            it(c.get("yellow") or 0), it((c.get("red") or 0) + (c.get("yellowred") or 0)), it(g.get("rating"), 2)))
    h.append("</tbody></table></div>")
    return "".join(h)

def render_player(D, S, T, p, ctx):
    pid = p["id"]; url = ctx["urls"][pid]; canon = SITE + url
    full = full_name(p)
    gk = p.get("position") == "Goalkeeper"
    role_it = ROLE_IT.get(p.get("position") or "", "giocatore")
    team_site = T.fanta_name(p.get("team_name") or "")
    tteam = T.by_name.get(team_site) if team_site else None
    cur_blocks = [b for b in (p.get("cur") or []) if (b.get("league") or {}).get("id") == 135]
    a_cur = agg(cur_blocks) if cur_blocks else None
    mb = main_block(p.get("prev"))
    a_prev = agg([mb]) if mb else None
    n_md = max([k for k in (D.get("voti") or {}).keys()] + [0])
    desc = describe(p, team_site, a_cur, a_prev, mb, role_it, ctx, n_md)
    li = ctx["listone"].get(pid); st = ctx["tit"].get(pid)
    vs = ctx["voti"].get(pid) or {}
    b = []
    team_html = (badge(tteam, 26) + '<a href="%s">%s</a>' % (T.url(team_site), esc(team_site))) if tteam else esc(p.get("team_name") or "")
    b.append("<h1>%s</h1>" % esc(full))
    age = age_of((p.get("birth") or {}).get("date"))
    sub = [team_html, esc(role_it)]
    if p.get("number"):
        sub.append("maglia %s" % p["number"])
    if age is not None:
        sub.append("%d anni" % age)
    if p.get("nationality"):
        sub.append(esc(p["nationality"]))
    if p.get("height"):
        sub.append("%s cm" % it(p["height"]))
    if p.get("weight"):
        sub.append("%s kg" % it(p["weight"]))
    if not p.get("active"):
        sub.append('<span class="tag t-rumor">non più in Serie A</span>')
    b.append('<div class="sub">' + " · ".join(sub) + " · scheda aggiornata <time>%s</time></div>" % esc(fdate_it(ctx["updated"], True)))
    if PHOTOS and p.get("photo"):
        b.append('<img class="photo" src="%s" alt="%s" width="120" height="120" loading="lazy">' % (esc(p["photo"]), esc(full)))
    b.append('<p class="lead">%s</p>' % esc(desc))
    # KPI stagione in corso
    k = []
    if a_cur:
        k.append(kpi("Presenze %s" % SEASON, it(a_cur["app"]), "%s da titolare" % it(a_cur["lineups"])))
        k.append(kpi("Minuti", it(a_cur["min"]), "%s su %s giornate" % (it(a_cur["app"]), it(n_md)) if n_md else ""))
        if gk:
            k.append(kpi("Gol subiti", it(a_cur["conceded"]), "%s parate" % it(a_cur["saves"])))
        else:
            k.append(kpi("Gol", it(a_cur["gol"]), "%s assist" % it(a_cur["assist"])))
        if a_cur.get("rating"):
            k.append(kpi("Rating medio", it(a_cur["rating"], 2), "statistico API-Football"))
    vv = [r["voto"] for r in vs.values() if r.get("voto") is not None]
    if vv:
        fvv = [r["fantavoto"] for r in vs.values() if r.get("fantavoto") is not None]
        k.append(kpi("Voto medio FantaTB", it(sum(vv) / len(vv), 2), "fantamedia %s" % it(sum(fvv) / len(fvv), 2) if fvv else ""))
    if li:
        k.append(kpi("Quotazione FantaTB", it(li.get("price")), "ruolo %s" % li.get("role")))
    if st and st.get("prob") is not None:
        k.append(kpi("Titolarità", pct(st["prob"]), st.get("injury") or "prossima giornata"))
    if k:
        b.append('<div class="kpis">' + "".join(k) + "</div>")
    # confronto stagioni
    lab_prev = "%s%s" % (PREV_LABEL, (" · " + ((mb.get("league") or {}).get("name") or "")) if mb else "")
    lab_cur = "%s · Serie A" % SEASON
    b.append("<h2>%s e %s a confronto</h2>" % (esc(PREV_LABEL), esc(SEASON)))
    b.append('<p class="ph">A sinistra il campionato della scorsa stagione, a destra la Serie A in corso; le colonne "per 90\'" normalizzano sui minuti giocati e sono il confronto onesto quando le partite sono poche.</p>')
    cmp_rows = CMP_GK if gk else CMP_ROWS
    charts = []
    if (a_cur and a_cur["min"] >= 90) or (a_prev and a_prev["min"] >= 90):
        if gk:
            metrics = [("Parate", "saves"), ("Gol subiti", "conceded"), ("Passaggi", "passes")]
        else:
            metrics = [("Tiri", "shots"), ("Passaggi chiave", "key"), ("Dribbling riusciti", "drib_ok"), ("Duelli vinti", "duels_won"), ("Contrasti", "tackles"), ("Intercetti", "inter"), ("Falli subiti", "fouls_drawn")]
        cats = [m for m, _ in metrics]
        sp = [p90(a_prev, k2) if a_prev and a_prev["min"] >= 90 else None for _, k2 in metrics]
        sc = [p90(a_cur, k2) if a_cur and a_cur["min"] >= 90 else None for _, k2 in metrics]
        series = [(PREV_LABEL, sp), (SEASON, sc)]
        charts.append(card("Ogni 90 minuti: %s contro %s" % (PREV_LABEL, SEASON), chart_hgroup(cats, series, [GRAY, C1], label="Statistiche per 90 minuti, stagione scorsa e stagione in corso"),
                           legend([(PREV_LABEL, GRAY), (SEASON, C1)])))
    ref = ctx["ref"].get(p.get("position") or "")
    if ref and not gk:
        series = [("Media ruolo %s" % PREV_LABEL, ref["mean"])]; colors = [GRAY]
        if a_prev and a_prev["min"] >= 450:
            series.append(("%s %s" % (full, PREV_LABEL), [per90(a_prev, fn) for _, fn in RADAR_AXES])); colors.append(C2)
        if a_cur and a_cur["min"] >= 180:
            series.append(("%s %s" % (full, SEASON), [per90(a_cur, fn) for _, fn in RADAR_AXES])); colors.append(C1)
        if len(series) > 1:
            axes = [(lab, ref["max"][i]) for i, (lab, _) in enumerate(RADAR_AXES)]
            charts.append(card("Profilo per 90 minuti rispetto ai pari ruolo", chart_radar(axes, series, colors, label="Radar delle statistiche per 90 minuti rispetto alla media del ruolo") +
                               '<p class="small">Scala di ogni asse: 90° percentile dei %s di Serie A con almeno 900 minuti nel campionato %s (%d giocatori).</p>' % (
                                   esc(ROLE_PL.get(p.get("position"), "giocatori").lower()), esc(PREV_LABEL), ref["n"]), legend(list(zip([n for n, _ in series], colors)))))
    if charts:
        b.append('<div class="grid2">' + "".join("<div>%s</div>" % c for c in charts) + "</div>")
    b.append(cmp_table(cmp_rows, a_prev, a_cur, lab_prev, lab_cur))
    if p.get("prev"):
        b.append("<h2>Tutte le competizioni %s</h2>" % esc(PREV_LABEL) + blocks_table(p["prev"], gk))
    # voti FantaTB
    if vs:
        mds = sorted(vs)
        cats = ["G%d" % m for m in mds]
        voti_l = [vs[m].get("voto") for m in mds]; fv_l = [vs[m].get("fantavoto") for m in mds]
        b.append("<h2>Voti FantaTB %s</h2>" % esc(SEASON))
        tbl = ['<table><thead><tr><th>Giornata</th><th>Min</th><th>Voto</th><th class="l">Bonus e malus</th><th>Fantavoto</th></tr></thead><tbody>']
        from render_site import bonus_txt, dec as decf
        for m in mds:
            r = vs[m]
            tbl.append('<tr><td><a href="/fantacalcio/voti-giornata-%d.html">%d</a></td><td>%s</td><td>%s</td><td class="l">%s</td><td class="pt">%s</td></tr>' % (
                m, m, it(r.get("minutes") or 0), decf(r["voto"]) if r.get("voto") is not None else "s.v.", esc(bonus_txt(r.get("bonus"))), decf(r["fantavoto"]) if r.get("fantavoto") is not None else "—"))
        tbl.append("</tbody></table>")
        b.append(card("Voto e fantavoto per giornata", chart_cols(cats, [("Voto", voti_l), ("Fantavoto", fv_l)], [C1, C2], fmt=lambda v: it(v, 1 if v != int(v) else 0), W=720, H=260, label="Voto e fantavoto FantaTB per giornata") + "".join(tbl),
                      legend([("Voto", C1), ("Fantavoto", C2)])))
    # carriera
    trs = p.get("transfers") or []
    if trs:
        b.append("<h2>Carriera: i trasferimenti</h2><div class=\"card\"><div style=\"overflow-x:auto\"><table><thead><tr><th class=\"l\">Data</th><th class=\"l\">Da</th><th class=\"l\">A</th><th class=\"l\">Formula</th></tr></thead><tbody>")
        for t in reversed(trs):
            b.append('<tr><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td></tr>' % (esc(data_it(t["date"])), esc(t["from"].get("name") or "—"), esc(t["to"].get("name") or "—"), esc(transfer_type_it(t.get("type")) or "—")))
        b.append('</tbody></table></div></div><p class="small">Il feed trasferimenti di API-Football parte dagli anni recenti e non copre le giovanili: la carriera può essere incompleta.</p>')
    # articoli e collegamenti
    arts = [a for a in D.get("arts") or [] if norm(a.get("giocatore") or "") == norm(full) or (norm(p.get("last") or "") and norm(p.get("last") or "") in norm(((a.get("t") or {}).get("it") or "")))][:6]
    if arts:
        from render_site import art_card
        b.append("<h2>Articoli su %s</h2><div class=\"arts\">%s</div>" % (esc(full), "".join(art_card(a) for a in arts)))
    mates = sorted([q for q in ctx["P"].values() if q.get("team") == p.get("team") and q.get("active") and q["id"] != pid], key=lambda q: (ROLE_ORDER.index(q.get("position")) if q.get("position") in ROLE_ORDER else 9, full_name(q)))
    if mates:
        b.append("<h2>Compagni di squadra</h2><div class=\"chips\">" + "".join(plink(ctx, q["id"], full_name(q)) for q in mates) + "</div>")
    links = ['<a href="/giocatori/">Tutti i giocatori di Serie A</a>', '<a href="/fantacalcio/listone.html">listone FantaTB</a>', '<a href="/fantacalcio/titolari.html">probabili titolari</a>']
    if team_site:
        links.insert(0, '<a href="%s">pagina %s</a>' % (T.url(team_site), esc(team_site)))
    b.append('<p class="small">%s</p>' % " · ".join(links))
    b.append('<div class="note"><b>Come leggere i numeri.</b> Statistiche di gioco da API-Football (tabellini ufficiali elaborati dal provider); rating = punteggio statistico 0-10 del provider, da cui nasce il voto FantaTB (rating − 0,8, arrotondato al mezzo punto). Le voci "per 90\'" dividono per i minuti giocati. Nessun dato è inventato: le frasi della scheda sono costruite dai numeri qui sopra.</div>')
    # JSON-LD
    bd = p.get("birth") or {}
    ld = {"@context": "https://schema.org", "@type": "Person", "name": full, "url": canon, "jobTitle": "Calciatore, " + role_it, "description": desc[:500]}
    if p.get("first"):
        ld["givenName"] = p["first"]
    if p.get("last"):
        ld["familyName"] = p["last"]
    if bd.get("date"):
        ld["birthDate"] = bd["date"]
    if bd.get("place"):
        ld["birthPlace"] = {"@type": "Place", "name": bd["place"] + ((", " + bd["country"]) if bd.get("country") else "")}
    if p.get("nationality"):
        ld["nationality"] = {"@type": "Country", "name": p["nationality"]}
    if p.get("height"):
        ld["height"] = {"@type": "QuantitativeValue", "value": p["height"], "unitCode": "CMT"}
    if p.get("weight"):
        ld["weight"] = {"@type": "QuantitativeValue", "value": p["weight"], "unitCode": "KGM"}
    if team_site:
        ld["memberOf"] = {"@type": "SportsTeam", "name": team_site, "url": SITE + T.url(team_site)}
    elif p.get("team_name"):
        ld["memberOf"] = {"@type": "SportsTeam", "name": p["team_name"]}
    crumbs = [("Home", SITE + "/"), ("Giocatori", SITE + "/giocatori/"), (full, canon)]
    title = "%s: statistiche, carriera e voti FantaTB" % full
    meta = "%s, %s %s%s: scheda con statistiche %s e %s a confronto, per 90 minuti e rispetto ai pari ruolo, carriera, voti e fantavoto FantaTB giornata per giornata." % (
        full, role_it, ART.get(team_site or "", "del " + (team_site or p.get("team_name") or "")), (", %d anni" % age) if age is not None else "", PREV_LABEL, SEASON)
    return page(title, meta, canon, "".join(b), crumbs=crumbs, ld=[ld], here="Giocatori")

def rosa_html(S, T, tid, ctx):
    """Rosa della squadra dalle rose API-Football, per ruolo, con link alle schede. Ritorna (html, nomi)."""
    ps = [p for p in ctx["P"].values() if p.get("active") and p.get("team") == tid]
    if not ps:
        return "", []
    h, names = [], []
    for pos in ROLE_ORDER:
        grp = sorted([p for p in ps if p.get("position") == pos], key=lambda p: ((p.get("number") or 99), full_name(p)))
        if not grp:
            continue
        h.append("<h3>%s (%d)</h3><ul class=\"plist\">" % (ROLE_PL[pos], len(grp)))
        for p in grp:
            age = age_of((p.get("birth") or {}).get("date"))
            h.append('<li><span class="n">%s</span>%s%s</li>' % (p.get("number") or "", plink(ctx, p["id"], full_name(p)), (' <span class="small">%s anni%s</span>' % (age, (", " + p["nationality"]) if p.get("nationality") else "")) if age else ""))
            names.append(full_name(p))
        h.append("</ul>")
    return "".join(h), names

def render_players_index(D, S, T, ctx):
    canon = SITE + "/giocatori/"
    P = ctx["P"]
    act = [p for p in P.values() if p.get("active")]
    teams = {}
    for p in act:
        teams.setdefault(p.get("team_name") or "?", []).append(p)
    top = sorted([p for p in act if p["id"] in ctx["listone"]], key=lambda p: -(ctx["listone"][p["id"]].get("price") or 0))[:20]
    b = ["<h1>Giocatori di Serie A %s: schede, statistiche e voti FantaTB</h1>" % esc(SEASON),
         '<div class="sub">%d giocatori delle %d squadre di Serie A, una scheda ciascuno: descrizione dai dati, statistiche %s e %s a confronto, profilo per 90 minuti rispetto ai pari ruolo, carriera, voti e fantavoto giornata per giornata. Aggiornato <time>%s</time>.</div>'
         % (len(act), len(teams), esc(PREV_LABEL), esc(SEASON), esc(fdate_it(ctx["updated"], True)))]
    if top:
        b.append("<h2>I più quotati nel listone FantaTB</h2><div class=\"chips\">" + "".join(plink(ctx, p["id"], "%s · %s" % (full_name(p), ctx["listone"][p["id"]].get("price"))) for p in top) + "</div>")
    b.append("<h2>Squadra per squadra</h2>")
    def site_of(api_name):
        return T.fanta_name(api_name)
    for tn in sorted(teams, key=lambda x: site_of(x) or x):
        site = site_of(tn); tt = T.by_name.get(site) if site else None
        head = (badge(tt, 26) + '<a href="%s">%s</a>' % (T.url(site), esc(site))) if tt else esc(tn)
        b.append('<div class="card"><h3>%s <span class="small">(%d giocatori)</span></h3><div class="in">' % (head, len(teams[tn])))
        for pos in ROLE_ORDER:
            grp = sorted([p for p in teams[tn] if p.get("position") == pos], key=lambda p: full_name(p))
            if grp:
                b.append('<p class="small" style="margin:6px 0 2px"><b>%s</b></p><div class="chips">%s</div>' % (ROLE_PL[pos], "".join(plink(ctx, p["id"], full_name(p)) for p in grp)))
        b.append("</div></div>")
    b.append('<p class="small">Dati: API-Football (statistiche e rose), FantaTB (voti, quotazioni, titolarità). Le schede si aggiornano dopo ogni giornata. <a href="/fantacalcio/">Dati aperti del fantacalcio</a> · <a href="/squadre/">pagine squadra</a>.</p>')
    ld = {"@context": "https://schema.org", "@type": "ItemList", "name": "Giocatori di Serie A " + SEASON,
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": full_name(p), "url": SITE + ctx["urls"][p["id"]]} for i, p in enumerate(top)]}
    return page("Giocatori di Serie A %s: schede con statistiche, carriera e voti" % SEASON,
                "Tutti i giocatori di Serie A %s con una scheda ciascuno: statistiche della stagione scorsa e di quella in corso a confronto, profilo per 90 minuti, carriera, voti e fantavoto FantaTB." % SEASON,
                canon, "".join(b), crumbs=[("Home", SITE + "/"), ("Giocatori", canon)], ld=[ld], here="Giocatori")
