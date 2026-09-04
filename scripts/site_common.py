#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - site_common.py: costanti, alias squadre, date italiane, template pagina, sitemap e lastmod.
Condiviso da render_site.py e render_articles.py. Le pagine generate sono SOLO in italiano (kb/SEO.md §3.2).
Nessuna dipendenza esterna: gira anche senza tzdata (Windows) e su Python 3.12 (GitHub Actions)."""
import json, os, re, html, hashlib, unicodedata
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SITE = "https://transferbeat.com"
SEASON = "2026-27"
# Entita' editoriale (kb/SEO.md §3.5). Nome pubblico confermato dal committente il 2026-09-03; il profilo LinkedIn va in sameAs.
AUTHOR = {"name": "Pierluigi Cella", "url": SITE + "/chi-siamo.html", "jobTitle": "Fondatore e responsabile editoriale",
          "sameAs": ["https://www.linkedin.com/in/pierluigi-cella-58076960/"]}
PERSON_LD = {"@type": "Person", "name": AUTHOR["name"], "url": AUTHOR["url"], "jobTitle": AUTHOR["jobTitle"], "sameAs": AUTHOR["sameAs"]}
ORG = {"@type": "Organization", "name": "TransferBeat", "url": SITE + "/",
       "logo": {"@type": "ImageObject", "url": SITE + "/favicon.png"},
       "founder": PERSON_LD}

# Competizioni: codice football-data -> pagina statica, nome italiano, lega della board (teams.json "league").
COMPS = [
    {"code": "SA",  "slug": "serie-a",          "nome": "Serie A",          "league": "Serie A", "paese": "Italia"},
    {"code": "CL",  "slug": "champions-league", "nome": "Champions League", "league": "",        "paese": "Europa"},
    {"code": "PL",  "slug": "premier-league",   "nome": "Premier League",   "league": "Premier", "paese": "Inghilterra"},
    {"code": "PD",  "slug": "liga",             "nome": "Liga",             "league": "La Liga", "paese": "Spagna"},
    {"code": "BL1", "slug": "bundesliga",       "nome": "Bundesliga",       "league": "",        "paese": "Germania"},
    {"code": "FL1", "slug": "ligue-1",          "nome": "Ligue 1",          "league": "",        "paese": "Francia"},
]
COMP_BY_CODE = {c["code"]: c for c in COMPS}
COMP_BY_LEAGUE = {c["league"]: c for c in COMPS if c["league"]}
LEAGUE_LABEL = {"Serie A": "Serie A", "La Liga": "Liga", "Premier": "Premier League"}
LEAGUE_ORDER = ["Serie A", "La Liga", "Premier"]
# Zone di classifica per competizione: [champions, europa, conference, retrocessione dal basso] (come campionati.html).
ZONES = {"SA": [4, 1, 1, 3], "PL": [5, 1, 0, 3], "PD": [5, 1, 1, 3], "BL1": [4, 1, 1, 2], "FL1": [3, 1, 1, 2], "CL": [8, 16, 0, 12]}

# Alias: nome in teams.json -> "short" di football-data (competizioni.json). Gli altri coincidono.
FD_ALIAS = {"Como": "Como 1907", "Barcelona": "Barça", "Atlético Madrid": "Atleti", "Athletic Club": "Athletic",
            "Sevilla": "Sevilla FC", "Celta Vigo": "Celta", "Brighton": "Brighton Hove", "Nottingham Forest": "Nottingham",
            "Leeds": "Leeds United", "Racing Santander": "Santander", "Venezia": "Venezia FC"}
# Alias: squadra nel listone FantaTB (API-Football) -> nome in teams.json.
FANTA_ALIAS = {"AC Milan": "Milan", "AS Roma": "Roma"}

STATE_LABEL = {"done": "Fatto", "conf": "Ufficiale", "obj": "Anteprima", "rumor": "Voce"}
STATE_ORDER = ["done", "conf", "obj", "rumor"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
MESI_B = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
GIORNI_B = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)

def esct(s):
    """Titoli delle testate: alcuni feed portano tag HTML grezzi (<p>…</p>): via i tag, poi escape."""
    return esc(re.sub(r"<[^>]+>", "", html.unescape(str(s if s is not None else ""))).strip())

def slugify(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_text(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

# ---------- date: Europe/Rome anche senza tzdata ----------
def _last_sunday(year, month):
    d = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1) if month < 12 else datetime(year, 12, 31, tzinfo=timezone.utc)
    return d - timedelta(days=(d.weekday() + 1) % 7)

def to_rome(dt):
    """datetime UTC -> ora italiana (CET/CEST). Usa zoneinfo se c'e', altrimenti la regola UE dell'ora legale."""
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("Europe/Rome"))
    except Exception:
        pass
    start = _last_sunday(dt.year, 3).replace(hour=1)
    end = _last_sunday(dt.year, 10).replace(hour=1)
    off = 2 if start <= dt < end else 1
    return dt.astimezone(timezone(timedelta(hours=off)))

def parse_iso(s):
    """'2026-09-02T22:52:57' (UTC senza suffisso), con 'Z' o con offset -> datetime aware UTC."""
    if not s:
        return None
    try:
        s = str(s).strip().replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None

def fdate_it(iso, with_time=False, short=False):
    """Data italiana leggibile: '4 settembre 2026' / '4 set' / 'ven 4 set, 20:45'."""
    d = parse_iso(iso)
    if not d:
        return ""
    r = to_rome(d)
    if short:
        s = GIORNI_B[r.weekday()] + " " + str(r.day) + " " + MESI_B[r.month - 1]
        return s + ", " + r.strftime("%H:%M") if with_time else s
    s = str(r.day) + " " + MESI[r.month - 1] + " " + str(r.year)
    return s + " alle " + r.strftime("%H:%M") if with_time else s

def date_only(iso):
    d = parse_iso(iso)
    return d.strftime("%Y-%m-%d") if d else ""

def today_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ---------- template pagina (solo italiano) ----------
NAV = [("Home", "/"), ("Live", "/board.html"), ("Articoli", "/articoli/it/"), ("Campionati", "/campionati.html"),
       ("Squadre", "/squadre/"), ("Giocatori", "/giocatori/"), ("FantaTB", "/fantatb.html"), ("Fonti", "/fonti.html")]
SITELINKS = [("Home", "/"), ("Articoli", "/articoli/it/"), ("Articles (EN)", "/articoli/en/"), ("Artículos (ES)", "/articoli/es/"),
             ("Live board", "/board.html"), ("Campionati", "/campionati.html"), ("Squadre", "/squadre/"), ("Giocatori di Serie A", "/giocatori/"),
             ("Fantacalcio: listone, voti e titolari", "/fantacalcio/"), ("FantaTB", "/fanta/"), ("Fonti", "/fonti.html"),
             ("Chi siamo", "/chi-siamo.html"), ("Archivio Mondiale 2026", "/mondiali.html")]
GA = ('<script async src="https://www.googletagmanager.com/gtag/js?id=G-RLST76W6H2"></script>'
      "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-RLST76W6H2');</script>")
CSS = """*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#fff;--panel:#f7f8fa;--line:#e2e6ea;--txt:#161b21;--muted:#67727e;--accent:#ff6a00;--blue:#1f6fd6;--red:#e0392b;--done:#0a9d57;--conf:#7b46c9;--rumor:#d98700}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--txt);line-height:1.55}
a{color:inherit;text-decoration:none}
.wrap{max-width:1080px;margin:0 auto;padding:0 18px}
header{border-bottom:1px solid var(--line)}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 0;flex-wrap:wrap}
.brand{font-family:Georgia,serif;font-size:26px;font-weight:700}.brand b{color:var(--accent)}
nav.tabs{display:flex;gap:2px;flex-wrap:wrap}nav.tabs a{font-size:13px;color:var(--muted);padding:8px 10px;border-bottom:2px solid transparent}
nav.tabs a.here,nav.tabs a:hover{color:var(--txt);border-bottom-color:var(--accent)}nav.tabs a.fanta{color:var(--accent);font-weight:700}
.crumbs{font-size:12px;color:var(--muted);padding:14px 0 0}.crumbs a{color:var(--blue)}
h1{font-family:Georgia,serif;font-size:32px;line-height:1.15;margin:12px 0 6px;letter-spacing:-.4px}
.sub{color:var(--muted);font-size:14px;margin-bottom:18px}.sub a{color:var(--blue);font-weight:600}
h2{font-family:Georgia,serif;font-size:22px;margin:28px 0 10px}h3{font-size:16px;margin:16px 0 8px}
p{margin-bottom:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:24px}@media(max-width:760px){.grid2{grid-template-columns:1fr}}
.card{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-bottom:18px;background:#fff}
.card>h2,.card>h3{background:var(--panel);font-size:14px;padding:10px 14px;border-bottom:1px solid var(--line);margin:0;font-family:'Segoe UI',system-ui,sans-serif}
.card .in{padding:12px 14px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:7px 6px;text-align:center}
th{font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);font-weight:700;background:#fcfcfd}
td.team,th.team,td.l,th.l{text-align:left;padding-left:12px}tbody tr{border-top:1px solid var(--line)}tbody tr.me{background:#fff4ec}
tr.z1 td.pos{color:var(--accent);font-weight:800}tr.z2 td.pos{color:var(--blue);font-weight:800}tr.z3 td.pos{color:#c9a227;font-weight:800}tr.zr td.pos{color:var(--red);font-weight:800}
.crest{width:20px;height:20px;object-fit:contain;margin-right:7px;vertical-align:-5px}.pt{font-weight:800}
.lab{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:6px;color:#fff;font-size:10px;font-weight:800;margin-right:8px;vertical-align:middle}
.news{list-style:none}.news li{padding:9px 0;border-top:1px solid var(--line);font-size:14px}.news li:first-child{border-top:0}
.news a.t{font-weight:600}.news a.t:hover{color:var(--accent)}.news .src{font-size:12px;color:var(--muted);margin-top:2px}.news .src a{color:var(--blue)}
.tag{font-size:10px;text-transform:uppercase;letter-spacing:.6px;font-weight:700;padding:1px 7px;border-radius:5px;margin-right:6px;vertical-align:middle}
.t-done{background:rgba(10,157,87,.14);color:var(--done)}.t-conf{background:rgba(123,70,201,.14);color:var(--conf)}.t-obj{background:rgba(31,111,214,.14);color:var(--blue)}.t-rumor{background:rgba(217,135,0,.14);color:var(--rumor)}
.reli{display:inline-flex;gap:2px;margin-right:6px;vertical-align:middle}.reli i{width:6px;height:6px;border-radius:50%;background:#cfd6dd}.reli i.on{background:var(--accent)}
.fx{display:grid;grid-template-columns:96px 1fr auto 1fr;align-items:center;gap:8px;padding:7px 0;border-top:1px solid #eef1f5;font-size:13px}.fx:first-child{border-top:0}
.fx .d{color:var(--muted);font-size:11px}.fx .h{text-align:right}.fx .r{font-weight:800;background:var(--panel);padding:2px 9px;border-radius:5px;min-width:52px;text-align:center}.fx .r.vs{color:var(--muted);font-weight:600;font-size:11px}
.fx a:hover{color:var(--accent)}@media(max-width:560px){.fx{grid-template-columns:64px 1fr auto 1fr;font-size:12px}}
.legend{font-size:11px;color:var(--muted);padding:6px 12px 10px}
.chips a,.chips span{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:5px 12px;font-size:13px;margin:0 6px 8px 0}.chips a:hover{border-color:var(--accent);color:var(--accent)}
.chips a.on{background:var(--txt);color:#fff;border-color:var(--txt)}
.rosa{columns:3;column-gap:24px;font-size:14px;list-style:none}.rosa li{padding:3px 0;break-inside:avoid}@media(max-width:700px){.rosa{columns:2}}
.arts{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}.arts a{display:block;border:1px solid var(--line);border-radius:10px;padding:12px 14px}.arts a:hover{border-color:var(--accent)}
.arts .k{font-size:10.5px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;color:var(--blue)}.arts .h{font-family:Georgia,serif;font-size:16px;line-height:1.25;margin:4px 0}.arts .m{font-size:12px;color:var(--muted)}
.btn{display:inline-block;background:var(--accent);color:#fff;font-weight:700;font-size:13px;padding:9px 16px;border-radius:8px;margin:6px 8px 6px 0}.btn.sec{background:var(--panel);color:var(--txt);border:1px solid var(--line)}
.faq details{border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:10px}.faq summary{font-weight:700;cursor:pointer}.faq details p{margin:8px 0 0;color:var(--muted);font-size:14px}
.pct{font-weight:800}.pct.g{color:var(--done)}.pct.a{color:var(--rumor)}.pct.r{color:var(--red)}
.note{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;font-size:13.5px;color:var(--muted);margin:14px 0}
.note b{color:var(--txt)}.small{font-size:12px;color:var(--muted)}
.foot{border-top:3px solid var(--accent);margin-top:30px;padding:18px 0 6px;color:var(--muted);font-size:12px;text-align:center}
.sitelinks{display:flex;flex-wrap:wrap;gap:8px 16px;justify-content:center;padding:10px 18px 18px;font-size:12px}.sitelinks a{color:var(--muted)}
.tools{margin:8px 0 12px;display:flex;gap:8px;flex-wrap:wrap}.tools input,.tools select{font:inherit;font-size:13px;padding:7px 10px;border:1px solid var(--line);border-radius:8px}
th.sort{cursor:pointer}th.sort:hover{color:var(--txt)}
.badge{vertical-align:middle;margin-right:8px;flex:none}h1 .badge{vertical-align:-9px;margin-right:12px}.chips a .badge{margin-right:6px;vertical-align:-7px}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px;margin:8px 0 18px}
.kpi{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:#fff}.kpi .l{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;font-weight:700}
.kpi .v{font-size:24px;font-weight:600;line-height:1.25;margin-top:2px}.kpi .s{font-size:12px;color:var(--muted)}
.chart{width:100%;max-width:720px;height:auto;display:block;font-family:'Segoe UI',system-ui,sans-serif;margin:4px 0 10px}.chart .ax{fill:var(--muted);font-size:12.5px}.chart .lb{fill:var(--txt);font-size:12.5px;font-weight:600}
.chart .grid{stroke:var(--line);stroke-width:1}.chart .base{stroke:#c3c2b7;stroke-width:1}.chart .ring{stroke:#fff;stroke-width:2}
.legend2{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:2px 0 6px}.legend2 i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.form{display:inline-flex;gap:3px;vertical-align:middle}.form i{display:inline-grid;place-items:center;min-width:22px;height:22px;padding:0 4px;border-radius:5px;color:#fff;font-size:11px;font-weight:800;font-style:normal}
.form .w{background:var(--done)}.form .d{background:#9aa5b1}.form .l{background:var(--red)}
.ph{margin:0 0 10px;font-size:13px;color:var(--muted)}.lead{font-size:16px;line-height:1.65}
.plist{list-style:none;columns:2;column-gap:24px;font-size:14px;margin-bottom:8px}.plist li{padding:3px 0;break-inside:avoid}.plist .n{display:inline-block;min-width:28px;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
@media(max-width:600px){.plist{columns:1}}
.card .in table td,.card .in table th{padding:6px 5px;font-variant-numeric:tabular-nums}.photo{border-radius:12px;float:right;margin:0 0 10px 16px}
.back{margin:12px 0 -2px;font-size:13px;color:var(--muted)}.back a{color:var(--blue);font-weight:600}.back a#backLs{display:inline-block;border:1px solid var(--line);border-radius:8px;padding:5px 11px;background:var(--panel)}"""

def dots(n):
    try:
        n = int(n or 0)
    except Exception:
        n = 0
    return '<span class="reli">' + "".join('<i class="%s"></i>' % ("on" if i <= n else "") for i in (1, 2, 3)) + "</span>"

def badge(t, size=26, cls="badge"):
    """Stemma con i colori sociali: quadrato diviso in diagonale fra col (sopra) e col2 (sotto) con la sigla; t = voce di teams.json.
    Il testo bianco ha un bordo scuro (paint-order) cosi' resta leggibile anche sui colori chiari (bianco, giallo)."""
    t = t or {}
    col = t.get("col") or "#67727e"; col2 = t.get("col2") or col; lab = t.get("lab") or ""
    return ('<svg class="%s" width="%d" height="%d" viewBox="0 0 26 26" aria-hidden="true"><rect width="26" height="26" rx="6" fill="%s"/>'
            '<path d="M26 0V26H0Z" fill="%s"/><rect x=".5" y=".5" width="25" height="25" rx="6" fill="none" stroke="rgba(0,0,0,.16)"/>'
            '<text x="13" y="17" text-anchor="middle" font-size="10" font-weight="800" fill="#fff" stroke="rgba(0,0,0,.6)" stroke-width="2.2" '
            'paint-order="stroke" font-family="\'Segoe UI\',system-ui,sans-serif">%s</text></svg>') % (cls, size, size, esc(col), esc(col2), esc(lab))

# ---------- limiti SEO di title e description (kb/SEO.md §0.2) ----------
TITLE_MAX = 60      # caratteri del <title> completo, suffisso compreso
DESC_MAX = 155      # caratteri della meta description
BRAND_SUFFIX = " | TransferBeat"
# Parole che non devono restare "appese" alla fine di un taglio (it/en/es).
_TRAIL = {"e", "a", "o", "di", "da", "in", "con", "su", "per", "tra", "fra", "il", "lo", "la", "i", "gli", "le", "un", "una", "uno", "del", "della",
          "dello", "dei", "degli", "delle", "al", "alla", "allo", "ai", "agli", "alle", "dal", "dalla", "nel", "nella", "sul", "sulla", "che", "ed", "od",
          "and", "or", "the", "of", "to", "at", "on", "for", "with", "by", "from", "an", "as", "y", "el", "los", "las", "de", "del", "en", "por", "para", "al", "u"}

def punti(n):
    """'1 punto' / '6 punti'."""
    try:
        n = int(n or 0)
    except Exception:
        n = 0
    return str(n) + (" punto" if n == 1 else " punti")

def cut_words(text, limit):
    """Taglia a fine parola entro `limit` caratteri, senza lasciare punteggiatura o preposizioni appese. Nessun puntino di sospensione."""
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit + 1]
    cut = cut[:cut.rfind(" ")] if " " in cut else cut[:limit]
    while True:
        prev = cut
        cut = cut.rstrip(" ,;:.-–—(\"'«»")
        parts = cut.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].lower().strip("'’") in _TRAIL:
            cut = parts[0]
        if cut == prev:
            break
    return cut.strip()

def seo_title(title, limit=TITLE_MAX):
    """<title> entro `limit` caratteri: con il suffisso della testata se ci sta, altrimenti senza (Google mostra comunque il nome del sito);
    se anche da solo supera il limite, taglio a fine parola."""
    t = re.sub(r"\s+", " ", (title or "")).strip()
    if "TransferBeat" in t:
        return t if len(t) <= limit else cut_words(t, limit)
    if len(t) + len(BRAND_SUFFIX) <= limit:
        return t + BRAND_SUFFIX
    return t if len(t) <= limit else cut_words(t, limit)

def seo_desc(desc, limit=DESC_MAX):
    """Meta description entro `limit` caratteri, tagliata a fine parola."""
    d = re.sub(r"\s+", " ", (desc or "")).strip()
    if len(d) <= limit:
        return d
    head = d[:limit + 1]
    ends = [x.start() for x in re.finditer(r"(?<![A-ZÀ-Ý])[.!?](?= )", head)]   # niente iniziali tipo "A. Raimondo"
    m = ends[-1] if ends else -1
    if m >= limit * 0.6:            # c'e' una frase intera che ci sta: chiudo li'
        return head[:m + 1]
    m = max(head.rfind("; "), head.rfind(": "))
    if m >= limit * 0.7:
        return head[:m] + "."
    return cut_words(d, limit - 1) + "…"

def breadcrumb_ld(items):
    """items: [(nome, url assoluta)] -> JSON-LD BreadcrumbList."""
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)]}

def ld_script(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + "</script>"

def page(title, desc, canon, body, crumbs=None, ld=None, here="", og_type="website", extra_head="", promo=True):
    """Pagina completa in italiano. title senza suffisso: seo_title() aggiunge ' | TransferBeat' se il totale resta entro 60 caratteri
    e taglia a fine parola se serve; la description e' limitata a 155 caratteri da seo_desc() (kb/SEO.md §0.2)."""
    full = seo_title(title)
    desc = seo_desc(desc)
    h = ['<!DOCTYPE html><html lang="it"><head><meta charset="UTF-8">', GA,
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         "<title>" + esc(full) + "</title>",
         '<meta name="description" content="' + esc(desc) + '">',
         '<link rel="canonical" href="' + esc(canon) + '">',
         '<meta property="og:type" content="' + og_type + '"><meta property="og:site_name" content="TransferBeat">',
         '<meta property="og:title" content="' + esc(title) + '"><meta property="og:description" content="' + esc(desc) + '">',
         '<meta property="og:url" content="' + esc(canon) + '"><meta property="og:locale" content="it_IT"><meta name="twitter:card" content="summary">',
         extra_head, "<style>" + CSS + "</style>"]
    if crumbs:
        h.append(ld_script(breadcrumb_ld(crumbs)))
    for o in (ld or []):
        h.append(ld_script(o))
    h.append("</head><body>")
    nav = "".join('<a href="%s" class="%s">%s</a>' % (u, ("here " if n == here else "") + ("fanta" if n == "FantaTB" else ""), n) for n, u in NAV)
    h.append('<header><div class="wrap top"><a class="brand" href="/">Transfer<b>Beat</b></a><nav class="tabs" aria-label="Sezioni principali">' + nav + "</nav></div></header>")
    h.append('<div class="wrap">')
    if crumbs:
        h.append('<nav class="crumbs" aria-label="Percorso">' + " › ".join(
            ('<a href="%s">%s</a>' % (esc(u), esc(n))) if i < len(crumbs) - 1 else "<span>" + esc(n) + "</span>" for i, (n, u) in enumerate(crumbs)) + "</nav>")
    h.append(body)
    h.append("</div>")
    h.append('<div class="foot"><div class="wrap">© TransferBeat · <a href="/chi-siamo.html">chi siamo</a> · <a href="/fonti.html">fonti</a> · le notizie citano sempre la testata originale</div></div>')
    h.append('<nav class="sitelinks" aria-label="Sezioni">' + "".join('<a href="%s">%s</a>' % (u, n) for n, u in SITELINKS) + "</nav>")
    if promo:
        h.append('<script src="/fanta/promo.js" defer></script>')
    h.append("</body></html>")
    return "".join(h)

# ---------- sitemap e lastmod veri ----------
# Parti volatili escluse dall'hash: "2 ore fa", orari di aggiornamento. Cosi' il lastmod cambia solo se cambia il contenuto.
VOLATILE = re.compile(r'<span class="ago">.*?</span>|<time\b[^>]*>.*?</time>', re.S)

class LastMod:
    """data/lastmod.json: per ogni URL l'hash del contenuto e la data dell'ultima modifica reale."""
    def __init__(self, path=None):
        self.path = path or os.path.join(DATA, "lastmod.json")
        self.db = load_json(self.path, {}) or {}
        self.today = today_iso()

    def touch(self, url, content):
        h = hashlib.sha1(VOLATILE.sub("", content).encode("utf-8")).hexdigest()[:16]
        e = self.db.get(url)
        if not e or e.get("h") != h:
            self.db[url] = {"h": h, "d": self.today}
        return self.db[url]["d"]

    def get(self, url, default=None):
        return (self.db.get(url) or {}).get("d") or default or self.today

    def save(self):
        save_text(self.path, json.dumps(self.db, ensure_ascii=False, indent=0, sort_keys=True) + "\n")

def write_urlset(path, entries):
    """entries: [(url assoluta, lastmod 'AAAA-MM-GG' o '')]."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lm in entries:
        lines.append("<url><loc>" + esc(loc) + "</loc>" + ("<lastmod>" + lm + "</lastmod>" if lm else "") + "</url>")
    lines.append("</urlset>")
    save_text(path, "\n".join(lines) + "\n")

def write_sitemap_index(root=ROOT):
    """sitemap.xml = indice di tutti i sitemap-<tipo>.xml presenti; lastmod = il piu' recente dentro ciascuno."""
    names = sorted(f for f in os.listdir(root) if re.match(r"sitemap-[a-z]+\.xml$", f))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for f in names:
        found = re.findall(r"<lastmod>(\d{4}-\d{2}-\d{2})", read_text(os.path.join(root, f)))
        lm = max(found) if found else ""
        lines.append("<sitemap><loc>" + SITE + "/" + f + "</loc>" + ("<lastmod>" + lm + "</lastmod>" if lm else "") + "</sitemap>")
    lines.append("</sitemapindex>")
    save_text(os.path.join(root, "sitemap.xml"), "\n".join(lines) + "\n")
    save_text(os.path.join(root, "robots.txt"), "User-agent: *\nAllow: /\nSitemap: " + SITE + "/sitemap.xml\n")
    return names
