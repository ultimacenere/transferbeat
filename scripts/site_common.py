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
# Menu unico del sito (direzione C, 2026-09-06): sei voci + bottone CTA; Home = logo; Fonti e Chi siamo stanno nel footer.
NAV = [("Notizie", "/board.html"), ("Campionati", "/campionati/"), ("Squadre", "/squadre/"), ("Giocatori", "/giocatori/"),
       ("Fantacalcio", "/fantacalcio/"), ("Articoli", "/articoli/it/")]
CTA = ("Gioca a FantaTB", "/fantatb.html")
# Nomi vecchi di `here` ancora accettati dai generatori: "Live" era la board, "FantaTB" il ramo fantacalcio, "Home" nessuna voce.
HERE_ALIAS = {"Live": "Notizie", "FantaTB": "Fantacalcio", "Home": ""}
# Barra di sezione del ramo fantacalcio (hub, pagine dati, landing).
FANTA_BAR = [("Panoramica", "/fantacalcio/"), ("Probabili formazioni", "/fantacalcio/probabili-formazioni.html"), ("Voti", "/fantacalcio/voti.html"),
             ("Listone", "/fantacalcio/listone.html"), ("Infortunati e squalificati", "/fantacalcio/titolari.html"),
             ("Regolamento", "/fantacalcio/regolamento.html"), ("Guida all'asta", "/fantacalcio/guida-asta.html")]
# Barra di sezione dei campionati: tutte, una voce per competizione, archivio del Mondiale.
CAMP_BAR = [("Tutte", "/campionati/")] + [(c["nome"], "/campionati/" + c["slug"] + ".html") for c in COMPS] + [("Mondiale 2026", "/mondiali.html")]
# Footer a tre colonne: (titolo, [(nome, url)]).
FOOTER = [("Sezioni", list(NAV)),
          ("Fantacalcio", list(FANTA_BAR) + [CTA]),
          ("TransferBeat", [("Chi siamo", "/chi-siamo.html"), ("Fonti", "/fonti.html"), ("Dati aperti", "/fantacalcio/listone.html#dati"),
                            ("Articles (EN)", "/articoli/en/"), ("Artículos (ES)", "/articoli/es/"), ("Archivio Mondiale 2026", "/mondiali.html")])]
# Lista piatta (nome, url) dei link del footer: compatibilita' con chi la importa.
SITELINKS = [link for _, links in FOOTER for link in links]
# Primi due livelli del breadcrumb del ramo fantacalcio (render_site ha la sua copia identica).
FANTA_CRUMB = [("Home", SITE + "/"), ("Fantacalcio", SITE + "/fantacalcio/")]
RIBBON_TEXT = "FantaTB è il fantacalcio gratuito di TransferBeat: leghe private, asta live, voti ogni 30 minuti."
GA = ('<script async src="https://www.googletagmanager.com/gtag/js?id=G-RLST76W6H2"></script>'
      "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-RLST76W6H2');</script>")
CSS = """*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f6f4fb;--card:#fff;--panel:#f6f4fb;--line:#e5e1ee;--line2:#eeebf4;--txt:#161b21;--txt2:#3d4750;--muted:#5b6670;
--brand:#ff6a00;--brand-ink:#c24d00;--ink:#1b1140;--violet:#4b1d95;--violet-bg:#ece6f7;--blue:#1f6fd6;
--ok:#0b7a45;--ok-bg:#d6f2e1;--warn:#946200;--warn-bg:#fff4dc;--err:#c9302c;--err-bg:#fdecea;
--rP:#9a5b00;--rD:#1f6fd6;--rC:#15804f;--rA:#c8281c;
--grad:linear-gradient(115deg,#ff6a00 0%,#e0298a 48%,#6b2bd9 100%);
--accent:var(--brand);--done:var(--ok);--rumor:var(--warn);--red:var(--err);--conf:#7b46c9;--font:'Segoe UI',system-ui,-apple-system,Roboto,'Helvetica Neue',Arial,sans-serif}
html{-webkit-text-size-adjust:100%}
body{font-family:var(--font);background:var(--bg);color:var(--txt);line-height:1.5;font-size:14px}
a{color:var(--violet);text-decoration:none}a:hover{color:var(--brand-ink)}
img,svg{vertical-align:middle}[hidden]{display:none!important}[id]{scroll-margin-top:56px}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px}main.wrap{padding-top:16px;padding-bottom:48px}
.num,td.num,th.num{font-variant-numeric:tabular-nums;text-align:right}
/* testata 64px */
header.site{background:#fff;border-bottom:1px solid var(--line)}
header.site .top{display:flex;align-items:center;gap:8px;height:64px}
.brand{font-family:Georgia,'Times New Roman',serif;font-size:26px;font-weight:700;letter-spacing:-.3px;color:var(--txt);flex:none}.brand b{color:var(--brand)}.brand:hover{color:var(--txt)}
.tabsw{margin-left:auto;min-width:0}
nav.tabs{display:flex;gap:2px;align-items:center}
nav.tabs a{font-size:14px;font-weight:600;color:var(--txt2);padding:0 12px;height:64px;display:inline-flex;align-items:center;white-space:nowrap;flex:none}
nav.tabs a:hover{color:var(--txt)}nav.tabs a.here{color:var(--txt);font-weight:700;box-shadow:inset 0 -2px 0 var(--brand)}nav.tabs a.fanta{color:var(--txt2)}
header.site a.cta,nav.secbar a.cta,.ribbon .rb-cta{display:inline-flex;align-items:center;flex:none;background:var(--brand);color:var(--ink);font-weight:700;border-radius:8px;white-space:nowrap}
header.site a.cta{font-size:14px;height:40px;padding:0 16px;margin-left:12px}header.site a.cta:hover,nav.secbar a.cta:hover,.ribbon .rb-cta:hover{background:#ff8226;color:var(--ink)}
/* barra di sezione 44px */
nav.secbar{background:#fff;border-top:1px solid var(--line);position:sticky;top:0;z-index:20}
nav.secbar .wrap{display:flex;gap:4px;align-items:center;height:44px;overflow-x:auto;scrollbar-width:none}nav.secbar .wrap::-webkit-scrollbar{display:none}
nav.secbar a{font-size:13px;font-weight:600;color:var(--txt2);padding:0 10px;height:44px;display:inline-flex;align-items:center;white-space:nowrap;flex:none}
nav.secbar a:hover{color:var(--txt)}nav.secbar a.here{color:var(--violet);font-weight:700;box-shadow:inset 0 -2px 0 var(--violet)}
nav.secbar a.cta{margin-left:auto;font-size:13px;height:32px;padding:0 12px}
/* ribbon promo */
.ribbon{background:var(--ink);color:#fff;font-size:13px}.ribbon .wrap{display:flex;align-items:center;gap:12px;min-height:48px}
.ribbon p{margin:0;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ribbon .rb-cta{font-size:13px;height:32px;padding:0 12px}
.ribbon .rb-x{background:none;border:0;color:#fff;cursor:pointer;padding:8px;margin-right:-8px;display:inline-flex;flex:none;font:inherit}.ribbon .rb-x:hover{color:var(--brand)}
/* titoli e testo */
.crumbs{font-size:13px;color:var(--muted);margin:0 0 12px}.crumbs a{color:var(--violet)}.crumbs span{color:var(--muted)}
h1{font-family:Georgia,'Times New Roman',serif;font-size:36px;line-height:1.15;font-weight:700;margin:0 0 8px;letter-spacing:-.4px}
.sub{color:var(--txt2);font-size:16px;margin:0 0 24px;max-width:760px}.sub a{font-weight:600}
h2{font-size:22px;font-weight:700;line-height:1.25;margin:32px 0 12px}h3{font-size:16px;font-weight:600;margin:16px 0 8px}
p{margin-bottom:12px}.lead{font-size:16px;line-height:1.65}.small{font-size:12px;color:var(--muted)}
.status{background:var(--warn-bg);color:var(--warn);font-weight:600;font-size:13px;border-radius:8px;padding:8px 12px;margin:0 0 16px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:24px}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
/* card */
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-bottom:16px}
.card>h2,.card>h3{font-family:var(--font);font-size:18px;font-weight:600;padding:12px 16px;border-bottom:1px solid var(--line);margin:0;background:#fff}
.card .in{padding:12px 16px}.card .in>p:last-child{margin-bottom:0}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin:0 0 24px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.kpi .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:600}
.kpi .v{font-size:28px;font-weight:700;line-height:1.25;margin-top:2px;font-variant-numeric:tabular-nums}.kpi .s{font-size:12px;color:var(--muted)}.kpi a{font-size:13px;font-weight:600}
/* tabelle */
.tscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}.tscroll>table{min-width:100%}
table{width:100%;border-collapse:collapse;font-size:13px}caption{text-align:left;font-size:12px;color:var(--muted);padding:8px 12px}
th{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;padding:10px 12px;text-align:left;background:#fff;border-bottom:1px solid var(--line)}
td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line2);font-variant-numeric:tabular-nums}
tbody tr:hover td{background:var(--panel)}tbody tr.me td{background:var(--panel)}tbody tr.me td:first-child{box-shadow:inset 2px 0 0 var(--brand)}
td.team,th.team,td.l,th.l{text-align:left}td.c,th.c{text-align:center}
tr.z1 td.pos{color:var(--brand-ink);font-weight:700}tr.z2 td.pos{color:var(--blue);font-weight:700}tr.z3 td.pos{color:var(--warn);font-weight:700}tr.zr td.pos{color:var(--err);font-weight:700}
.card .in table td,.card .in table th{padding:8px 8px}
th.sort{cursor:pointer;user-select:none}th.sort:hover{color:var(--txt)}
.crest{width:20px;height:20px;object-fit:contain;margin-right:8px;vertical-align:-5px}.pt{font-weight:700}
/* badge ruolo, pillole, tag */
.rb{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:6px;color:#fff;font-size:12px;font-weight:700;font-style:normal;flex:none;line-height:1}
.rb.P{background:var(--rP)}.rb.D{background:var(--rD)}.rb.C{background:var(--rC)}.rb.A{background:var(--rA)}
.pill{display:inline-block;font-size:12px;font-weight:700;padding:2px 10px;border-radius:6px;background:var(--panel);color:var(--txt2);line-height:1.5;white-space:nowrap}
.pill.ok{background:var(--ok-bg);color:#0b5d36}.pill.warn{background:var(--warn-bg);color:var(--warn)}.pill.err{background:var(--err-bg);color:#8a1f16}.pill.info{background:var(--violet-bg);color:var(--violet)}
.pct{font-weight:700;font-variant-numeric:tabular-nums}.pct.g{color:var(--ok)}.pct.a{color:var(--warn)}.pct.r{color:var(--err)}
.pol{color:var(--warn);font-weight:700}.pol::after{content:"*"}
.lab{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:6px;color:#fff;font-size:12px;font-weight:700;margin-right:8px;vertical-align:middle}
.tag{display:inline-block;font-size:12px;text-transform:uppercase;letter-spacing:.4px;font-weight:700;padding:1px 6px;border-radius:6px;margin-right:6px;vertical-align:middle;line-height:1.5}
.t-done{background:var(--ok-bg);color:var(--ok)}.t-conf{background:var(--violet-bg);color:var(--conf)}.t-obj{background:#e3edfb;color:var(--blue)}.t-rumor{background:var(--warn-bg);color:var(--warn)}
.reli{display:inline-flex;gap:2px;margin-right:6px;vertical-align:middle}.reli i{width:6px;height:6px;border-radius:50%;background:#cfd6dd}.reli i.on{background:var(--brand)}
.badge{vertical-align:middle;margin-right:8px;flex:none}h1 .badge{vertical-align:-9px;margin-right:12px}.chips a .badge{margin-right:6px;vertical-align:-7px}
.form{display:inline-flex;gap:3px;vertical-align:middle}.form i{display:inline-grid;place-items:center;min-width:22px;height:22px;padding:0 4px;border-radius:6px;color:#fff;font-size:12px;font-weight:700;font-style:normal}
.form .w{background:var(--ok)}.form .d{background:#5b6670}.form .l{background:var(--err)}
/* liste e notizie */
.news{list-style:none}.news li{padding:8px 0;border-top:1px solid var(--line2);font-size:14px}.news li:first-child{border-top:0}
.news a.t{font-weight:600;color:var(--txt)}.news a.t:hover{color:var(--brand-ink)}.news .src{font-size:12px;color:var(--muted);margin-top:2px}
.fx{display:grid;grid-template-columns:96px 1fr auto 1fr;align-items:center;gap:8px;padding:8px 0;border-top:1px solid var(--line2);font-size:13px}.fx:first-child{border-top:0}
.fx .d{color:var(--muted);font-size:12px}.fx .h{text-align:right}.fx .r{font-weight:700;background:var(--panel);padding:2px 8px;border-radius:6px;min-width:52px;text-align:center;font-variant-numeric:tabular-nums}.fx .r.vs{color:var(--muted);font-weight:600;font-size:12px}
.fx a{color:var(--txt)}.fx a:hover{color:var(--brand-ink)}
.legend{font-size:12px;color:var(--muted);padding:8px 12px 12px}
.legend2{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:4px 0 8px}.legend2 i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.rosa{columns:3;column-gap:24px;font-size:14px;list-style:none}.rosa li{padding:4px 0;break-inside:avoid}
.plist{list-style:none;columns:2;column-gap:24px;font-size:14px;margin-bottom:8px}.plist li{padding:4px 0;break-inside:avoid}.plist .n{display:inline-block;min-width:28px;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.arts{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}.arts a{display:block;background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;color:var(--txt)}.arts a:hover{border-color:var(--violet);color:var(--txt)}
.arts .k{font-size:12px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;color:var(--violet)}.arts .h{font-size:16px;font-weight:600;line-height:1.25;margin:4px 0}.arts .m{font-size:12px;color:var(--muted)}
/* chip, bottoni, campi */
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 16px}
.chips a,.chips span{display:inline-flex;align-items:center;min-height:32px;background:#fff;border:1px solid var(--line);border-radius:8px;padding:4px 12px;font-size:13px;font-weight:600;color:var(--txt2)}
.chips a:hover{border-color:var(--violet);color:var(--violet)}.chips a.on{background:var(--violet);color:#fff;border-color:var(--violet)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--brand);color:var(--ink);font-weight:700;font-size:14px;min-height:40px;padding:8px 16px;border-radius:8px;border:1px solid transparent;margin:4px 8px 4px 0;cursor:pointer;font-family:inherit}
.btn:hover{background:#ff8226;color:var(--ink)}.btn.sec{background:var(--violet);color:#fff}.btn.sec:hover{background:#3b1676;color:#fff}
.btn.ghost{background:#fff;color:var(--txt);border-color:var(--line)}.btn.ghost:hover{border-color:var(--violet);color:var(--violet)}.btn.small{min-height:32px;font-size:13px;padding:4px 12px}
.tools{margin:0 0 16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.tools input,.tools select{font:inherit;font-size:14px;height:40px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--txt)}
.tools input:focus,.tools select:focus{outline:0;border-color:var(--blue);box-shadow:0 0 0 3px rgba(31,111,214,.25)}
/* card speciali */
.grad{background:var(--grad);color:#fff;border-radius:16px;padding:24px 28px}.grad h2,.grad h3{color:#fff;margin-top:0}.grad h2{font-size:28px;line-height:1.15}.grad p{opacity:.95}
.grad a{color:#fff}.grad .btn{background:#fff;color:var(--violet);margin-top:8px}.grad .btn:hover{background:#f3eefb;color:var(--violet)}
.grad .k{font-size:12px;text-transform:uppercase;letter-spacing:.8px;font-weight:700;opacity:.9;margin-bottom:8px}
.door{display:flex;justify-content:space-between;align-items:center;gap:12px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px;color:var(--txt);margin-bottom:8px}
.door:hover{border-color:var(--violet);color:var(--txt)}.door b{font-weight:600;display:block}.door .s{font-size:12px;color:var(--muted)}.door svg{flex:none;color:var(--muted)}
.door.dark{background:var(--violet);border-color:var(--violet);color:#fff}.door.dark:hover{background:#3b1676;color:#fff}.door.dark .s,.door.dark svg{color:rgba(255,255,255,.85)}
.note{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;font-size:13px;color:var(--muted);margin:16px 0}.note b{color:var(--txt)}
.faq details{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-bottom:8px}.faq summary{font-weight:600;cursor:pointer}.faq details p{margin:8px 0 0;color:var(--txt2);font-size:14px}
.ph{margin:0 0 12px;font-size:13px;color:var(--muted)}.photo{border-radius:12px;float:right;margin:0 0 12px 16px}
.back{margin:0 0 8px;font-size:13px;color:var(--muted)}.back a{font-weight:600}.back a#backLs{display:inline-block;border:1px solid var(--line);border-radius:8px;padding:4px 12px;background:#fff}
.chart{width:100%;max-width:720px;height:auto;display:block;font-family:var(--font);margin:4px 0 12px}.chart .ax{fill:var(--muted);font-size:12px}.chart .lb{fill:var(--txt);font-size:12px;font-weight:600}
.chart .grid{stroke:var(--line);stroke-width:1}.chart .base{stroke:#c3c2b7;stroke-width:1}.chart .ring{stroke:#fff;stroke-width:2}
/* footer */
.foot{border-top:3px solid var(--brand);background:#fff;margin-top:48px;padding:24px 0 20px;font-size:12px;color:var(--muted)}
.foot .cols{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}.foot .ft{font-size:12px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;color:var(--txt2);margin:0 0 8px}
.foot ul{list-style:none}.foot li{padding:3px 0}.foot li a{font-size:13px;color:var(--muted)}.foot li a:hover{color:var(--brand-ink)}
.foot .copy{margin:20px 0 0;padding-top:12px;border-top:1px solid var(--line2)}.foot .copy a{color:var(--muted)}
.sitelinks{display:flex;flex-wrap:wrap;gap:8px 16px;justify-content:center;padding:12px 24px 20px;font-size:12px}.sitelinks a{color:var(--muted)}
/* mobile */
@media(max-width:760px){
.wrap{padding:0 16px}main.wrap{padding-top:12px;padding-bottom:32px}h1{font-size:28px}h2{font-size:18px;margin-top:24px}.sub{font-size:14px;margin-bottom:16px}
header.site .top{flex-wrap:wrap;height:auto;gap:0}.brand{font-size:22px;height:56px;display:inline-flex;align-items:center}
header.site a.cta{margin-left:auto;height:36px;font-size:13px;padding:0 12px}
.tabsw{order:3;flex:0 0 calc(100% + 32px);margin:0 -16px;position:relative}
nav.tabs{overflow-x:auto;scrollbar-width:none;padding:0 8px}nav.tabs::-webkit-scrollbar{display:none}nav.tabs a{height:44px;padding:0 10px}
.tabsw::after{content:"";position:absolute;right:0;top:0;bottom:0;width:32px;background:linear-gradient(90deg,rgba(255,255,255,0),#fff);pointer-events:none}/* sfumatura al bianco della riga scorrevole: trasparenza, non un colore */
nav.secbar .wrap{padding:0 8px}.ribbon .wrap{gap:8px}
.grid2,.grid3,.foot .cols{grid-template-columns:1fr}.kpis{grid-template-columns:1fr 1fr;gap:8px}.kpi .v{font-size:22px}
.rosa{columns:2}.plist{columns:1}.grad{padding:16px;border-radius:12px}.grad h2{font-size:22px}
.fx{grid-template-columns:64px 1fr auto 1fr;font-size:12px}th,td{padding:8px}
}
@media(max-width:400px){.rosa{columns:1}.kpis{grid-template-columns:1fr 1fr}}"""

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

# ---------- guscio unico: testata, barra di sezione, ribbon, breadcrumb, footer (direzione C, 2026-09-06) ----------
ICON_X = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
          '<path d="M6 6l12 12M18 6L6 18"/></svg>')
ICON_CHEVRON = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
                'stroke-linejoin="round" aria-hidden="true"><polyline points="9 6 15 12 9 18"/></svg>')

def _here(here):
    """Nome della voce attiva del menu, accettando i nomi vecchi (Live, FantaTB, Home)."""
    return HERE_ALIAS.get(here or "", here or "")

def _is_fanta(here):
    return _here(here) == "Fantacalcio"

def _links(items, here, cls="", cta=None):
    out = []
    for n, u in items:
        k = ("here" if n == here else "") + ((" " + cls) if cls else "")
        out.append('<a href="%s"%s>%s</a>' % (esc(u), (' class="' + k.strip() + '"') if k.strip() else "", esc(n)))
    if cta:
        out.append('<a class="cta" href="%s">%s</a>' % (esc(cta[1]), esc(cta[0])))
    return "".join(out)

def section_bar(items, here, cta=None):
    """Barra di sezione 44px: <nav class="secbar">; here = nome della voce attiva; cta = (nome, url) facoltativo a destra."""
    return '<nav class="secbar" aria-label="Sezione"><div class="wrap">' + _links(items, here, cta=cta) + "</div></nav>"

def shell_header(here="", bar=None, bar_here="", cta=True):
    """<header class="site">: testata 64px (logo, sei voci NAV, bottone CTA) + barra di sezione facoltativa."""
    h = _here(here)
    nav = "".join('<a href="%s"%s>%s</a>' % (esc(u), ' class="here"' if n == h else "", esc(n)) for n, u in NAV)
    out = ['<header class="site"><div class="wrap top"><a class="brand" href="/">Transfer<b>Beat</b></a>',
           '<div class="tabsw"><nav class="tabs" aria-label="Sezioni principali">' + nav + "</nav></div>"]
    if cta:
        out.append('<a class="cta" href="%s">%s</a>' % (esc(CTA[1]), esc(CTA[0])))
    out.append("</div>")
    if bar:
        out.append(section_bar(bar, bar_here))
    out.append("</header>")
    return "".join(out)

def ribbon():
    """Striscia promo 48px sotto la testata: una frase, il link alla landing e la X; lo script la nasconde per 7 giorni (localStorage tb_ribbon).
    Senza JS resta visibile. Sostituisce fanta/promo.js."""
    return ('<div class="ribbon" id="tbRibbon"><div class="wrap"><p>' + esc(RIBBON_TEXT) + '</p>'
            '<a class="rb-cta" href="' + esc(CTA[1]) + '">Crea la tua lega</a>'
            '<button type="button" class="rb-x" aria-label="Chiudi il messaggio">' + ICON_X + "</button></div></div>"
            "<script>(function(){try{var r=document.getElementById('tbRibbon'),t=Number(localStorage.getItem('tb_ribbon')||0);"
            "if(t&&6048e5>Date.now()-t){r.hidden=true;return}r.querySelector('.rb-x').addEventListener('click',function(){"
            "try{localStorage.setItem('tb_ribbon',String(Date.now()))}catch(e){}r.hidden=true})}catch(e){}})();</script>")

def breadcrumb_html(crumbs):
    """<nav class="crumbs"> con separatore ›; l'ultima voce non e' un link. crumbs: [(nome, url)]."""
    if not crumbs:
        return ""
    return '<nav class="crumbs" aria-label="Percorso">' + " › ".join(
        ('<a href="%s">%s</a>' % (esc(u), esc(n))) if i < len(crumbs) - 1 else "<span>" + esc(n) + "</span>"
        for i, (n, u) in enumerate(crumbs)) + "</nav>"

def door(title, sub, url, dark=False):
    """Card-porta: titolo, riga grigia e freccia a destra (SVG inline). dark=True = sfondo viola con testo bianco."""
    return ('<a class="door%s" href="%s"><span><b>%s</b>%s</span>%s</a>'
            % (" dark" if dark else "", esc(url), esc(title), ('<span class="s">' + esc(sub) + "</span>") if sub else "", ICON_CHEVRON))

def shell_footer():
    """<footer class="foot">: bordo superiore 3px --brand, tre colonne da FOOTER e riga finale."""
    cols = "".join('<div><p class="ft">' + esc(t) + "</p><ul>" + "".join('<li><a href="%s">%s</a></li>' % (esc(u), esc(n)) for n, u in links) + "</ul></div>"
                   for t, links in FOOTER)
    return ('<footer class="foot"><div class="wrap"><div class="cols">' + cols + '</div><p class="copy">© TransferBeat · le notizie citano sempre '
            "la testata originale · non affiliato a Fantacalcio®</p></div></footer>")

def page(title, desc, canon, body, crumbs=None, ld=None, here="", og_type="website", extra_head="", promo=True, bar=None, bar_here=""):
    """Pagina completa in italiano. title senza suffisso: seo_title() aggiunge ' | TransferBeat' se il totale resta entro 60 caratteri
    e taglia a fine parola se serve; la description e' limitata a 155 caratteri da seo_desc() (kb/SEO.md §0.2).
    here = voce attiva del menu (anche i nomi vecchi Live/FantaTB); bar/bar_here = barra di sezione; promo = ribbon sotto la testata,
    mai sul ramo Fantacalcio."""
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
         "<style>" + CSS + "</style>", extra_head]
    if crumbs:
        h.append(ld_script(breadcrumb_ld(crumbs)))
    for o in (ld or []):
        h.append(ld_script(o))
    h.append("</head><body>")
    h.append(shell_header(here, bar, bar_here))
    if promo and not _is_fanta(here):
        h.append(ribbon())
    h.append('<main class="wrap">' + breadcrumb_html(crumbs) + body + "</main>")
    h.append(shell_footer())
    h.append("</body></html>")
    return "".join(h)

_SHELL_RX = {k: re.compile("<!--shell:" + k + "-->.*?<!--/shell:" + k + "-->", re.S) for k in ("css", "header", "footer")}

def apply_shell(path, here="", bar=None, bar_here="", promo=True):
    """Pagine scritte a mano: sostituisce i blocchi fra i marcatori <!--shell:css-->, <!--shell:header--> e <!--shell:footer-->
    con CSS, testata (+ ribbon se promo e fuori dal ramo Fantacalcio) e footer. Marcatore mancante = avviso, nessuna eccezione.
    Salva solo se cambia qualcosa; ritorna True se ha scritto."""
    try:
        src = read_text(path)
    except Exception as e:
        print("apply_shell: non leggo", path, e)
        return False
    blocks = {"css": "<style>" + CSS + "</style>",
              "header": shell_header(here, bar, bar_here) + (ribbon() if promo and not _is_fanta(here) else ""),
              "footer": shell_footer()}
    out = src
    for k, rx in _SHELL_RX.items():
        new = "<!--shell:" + k + "-->" + blocks[k] + "<!--/shell:" + k + "-->"
        out, n = rx.subn(lambda m: new, out, count=1)
        if not n:
            print("apply_shell: manca il marcatore shell:" + k + " in", os.path.relpath(path, ROOT))
    if out != src:
        save_text(path, out)
        return True
    return False

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
