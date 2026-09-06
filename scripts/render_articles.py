#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render pagine statiche degli articoli + indici + sitemap-articoli.xml (l'indice sitemap.xml lo scrive site_common.write_sitemap_index).
SEO (kb/SEO.md §3.5 e §3.7): autore Person con link a chi-siamo, breadcrumb Home > Articoli > Squadra > Articolo, tag squadra e competizione
con link alle pagine statiche, blocco "Correlati" (stessa squadra, poi stesso tipo, ultimi 5). Hub linkate senza ?lang= (hub solo in italiano).
Guscio unico del sito (direzione C, 2026-09-06): testata, barra di sezione con le tre lingue, ribbon (solo IT), breadcrumb e footer vengono da
site_common; il CSS e' quello condiviso piu' le sole regole del corpo articolo. Ogni articolo ha una card "Fantacalcio" con i numeri veri dei
dati fanta al momento del render (voti, probabili, listone, indisponibili) e i link alla pagina squadra e alla scheda del giocatore citato."""
import json, os, re, html, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_common import (AUTHOR, PERSON_LD, ORG, COMP_BY_LEAGUE, DATA as _DATA, slugify, write_urlset, write_sitemap_index, date_only, load_json,
                         seo_title, seo_desc, ld_script, breadcrumb_ld, CSS as SHELL_CSS, GA, shell_header, shell_footer, ribbon, breadcrumb_html,
                         badge as team_badge)
TEAMS = {t["nome"]: t for t in (load_json(os.path.join(_DATA, "teams.json"), {}) or {}).get("squadre", [])}
TEAM_SLUG = {n: slugify(n) for n in TEAMS}
AUTHOR_LD = dict(PERSON_LD)

LANGS = ("it", "en", "es")
# Etichette della barra di sezione (selettore lingua): ogni lingua nel proprio nome.
LANG_LABEL = {"it": "Italiano", "en": "English", "es": "Español"}
STATE_LABEL = {
    "it": {"rumor": "Rumor", "obj": "Obiettivo", "conf": "Trattativa confermata", "done": "Affare concluso"},
    "en": {"rumor": "Rumour", "obj": "Target", "conf": "Deal agreed", "done": "Done deal"},
    "es": {"rumor": "Rumor", "obj": "Objetivo", "conf": "Negociación confirmada", "done": "Cerrado"},
}
# Classe della pillola per stato della trattativa (sfondo chiaro + testo scuro semantico, contrasto AA).
STATE_PILL = {"rumor": "warn", "obj": "warn", "conf": "info", "done": "ok"}
UI = {
  "it": {"by": "Redazione TransferBeat", "sources": "Fonti", "updated": "Aggiornato il", "home": "Home",
         "board": "Notizie", "campionati": "Campionati", "back": "Tutti gli articoli", "status": "Stato", "list": "Articoli",
         "disc": "TransferBeat aggrega notizie di calcio citando le fonti originali. Notizia in aggiornamento.",
         "via": "via", "smentita": "SMENTITA", "squadre": "Squadre", "related": "Articoli correlati", "edby": "a cura di",
         "fanta": "Fantacalcio", "fanta_intro": "I dati originali di TransferBeat per il fantacalcio",
         "fanta_voti": "Voti FantaTB della giornata {n}", "fanta_voti_s": "voti FantaTB della giornata {n} ({f} partite su {t} votate)",
         "fanta_voti_done": "voti FantaTB della giornata {n} ({t} partite)",
         "fanta_prob": "Probabili formazioni della giornata {n}", "fanta_prob_s": "probabili formazioni della giornata {n} ({p} partite, la prima il giorno {d})",
         "fanta_list": "Listone: {n} giocatori quotati", "fanta_list_s": "listone con {n} giocatori quotati",
         "fanta_inj": "Infortunati e squalificati", "fanta_inj_s": "{n} indisponibili",
         "fanta_all": "Tutto il fantacalcio", "fanta_team": "{t}: notizie, statistiche e classifica", "fanta_player": "Scheda di {p}",
         "fanta_note": ""},
  "en": {"by": "TransferBeat Newsroom", "sources": "Sources", "updated": "Updated on", "home": "Home",
         "board": "News", "campionati": "Leagues", "back": "All articles", "status": "Status", "list": "Articles",
         "disc": "TransferBeat aggregates football news citing the original sources. Developing story.",
         "via": "via", "smentita": "DENIED", "squadre": "Clubs", "related": "Related articles", "edby": "edited by",
         "fanta": "Fantasy football", "fanta_intro": "TransferBeat's own Serie A fantasy football data",
         "fanta_voti": "Matchday {n} FantaTB ratings", "fanta_voti_s": "matchday {n} FantaTB ratings ({f} of {t} matches rated)",
         "fanta_voti_done": "matchday {n} FantaTB ratings ({t} matches)",
         "fanta_prob": "Matchday {n} predicted line-ups", "fanta_prob_s": "matchday {n} predicted line-ups ({p} matches, the first on {d})",
         "fanta_list": "Player list: {n} valuations", "fanta_list_s": "a player list with {n} valuations",
         "fanta_inj": "Injured and suspended", "fanta_inj_s": "{n} unavailable players",
         "fanta_all": "All the fantasy football data", "fanta_team": "{t}: news, stats and table", "fanta_player": "{p} profile",
         "fanta_note": "Pages in Italian."},
  "es": {"by": "Redacción TransferBeat", "sources": "Fuentes", "updated": "Actualizado el", "home": "Inicio",
         "board": "Noticias", "campionati": "Ligas", "back": "Todos los artículos", "status": "Estado", "list": "Artículos",
         "disc": "TransferBeat agrega noticias de fútbol citando las fuentes originales. Noticia en desarrollo.",
         "via": "via", "smentita": "DESMENTIDO", "squadre": "Equipos", "related": "Artículos relacionados", "edby": "editado por",
         "fanta": "Fantacalcio", "fanta_intro": "Los datos propios de TransferBeat para el fantacalcio de la Serie A",
         "fanta_voti": "Votos FantaTB de la jornada {n}", "fanta_voti_s": "votos FantaTB de la jornada {n} ({f} partidos de {t} valorados)",
         "fanta_voti_done": "votos FantaTB de la jornada {n} ({t} partidos)",
         "fanta_prob": "Alineaciones probables de la jornada {n}", "fanta_prob_s": "alineaciones probables de la jornada {n} ({p} partidos, el primero el {d})",
         "fanta_list": "Listado: {n} jugadores cotizados", "fanta_list_s": "listado con {n} jugadores cotizados",
         "fanta_inj": "Lesionados y sancionados", "fanta_inj_s": "{n} bajas",
         "fanta_all": "Todo el fantacalcio", "fanta_team": "{t}: noticias, estadísticas y clasificación", "fanta_player": "Ficha de {p}",
         "fanta_note": "Páginas en italiano."},
}
RECAP_LABEL = {"it": "RECAP DI GIORNATA", "en": "DAILY RECAP", "es": "RESUMEN DEL DÍA"}
STORIA_LABEL = {"it": "FOCUS", "en": "FOCUS", "es": "FOCO"}
LUNCH_LABEL = {"it": "LUNCH BREAK", "en": "LUNCH BREAK", "es": "LUNCH BREAK"}
SCOOP_LABEL = {"it": "SCOOP", "en": "SCOOP", "es": "SCOOP"}
NOTTI_LABEL = {"it": "NOTTI MONDIALI", "en": "WORLD CUP NIGHTS", "es": "NOCHES MUNDIALES"}
# pill = classe semantica della pillola (colori dai token del sito, mai testo bianco su colore pieno).
TIPI = {"recap": {"label": RECAP_LABEL, "pill": "ok", "cover": "cover-recap.svg"},
        "lunch": {"label": LUNCH_LABEL, "pill": "warn", "cover": "cover-lunch.svg"},
        "storia": {"label": STORIA_LABEL, "pill": "blue", "cover": "cover-storia.svg"},
        "scoop": {"label": SCOOP_LABEL, "pill": "err", "cover": "cover-scoop.svg"},
        "notti": {"label": NOTTI_LABEL, "pill": "info", "cover": "cover-notti.svg"}}
MONTHS = {"it": ["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"],
          "en": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
          "es": ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]}
# URL fisse del ramo fantacalcio (le pagine esistono nel repo). I voti dell'ultima giornata stanno sull'URL fissa voti.html:
# voti-giornata-N.html esiste solo per le giornate passate (archivio), quindi la card, che cita sempre l'ultima, non deve usarla.
FANTA_URL = {"hub": "/fantacalcio/", "prob": "/fantacalcio/probabili-formazioni.html", "listone": "/fantacalcio/listone.html",
             "tit": "/fantacalcio/titolari.html", "voti": "/fantacalcio/voti.html"}
ICON_PLAY = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round" aria-hidden="true"><polygon points="6 4 20 12 6 20 6 4"/></svg>')

def esc(s):
    return html.escape(str(s or ""), quote=True)

def fdate(iso, lang):
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return str(d.day) + " " + MONTHS[lang][d.month - 1] + " " + str(d.year)
    except Exception:
        return ""

# ---------- dati fanta per la card contestuale (letti una volta per run, numeri veri al momento del render) ----------
_FANTA = {}

def _latest(prefix):
    """Ultimo data/fanta/<prefix>-N.json (N massimo) con contenuto: (N, dati) oppure None."""
    fd = os.path.join(_DATA, "fanta")
    best = None
    if os.path.isdir(fd):
        for fn in os.listdir(fd):
            m = re.match(prefix + r"-(\d+)\.json$", fn)
            if m and (best is None or int(m.group(1)) > best[0]):
                j = load_json(os.path.join(fd, fn))
                if j:
                    best = (int(m.group(1)), j)
    return best

def fanta_ctx():
    """Numeri della card Fantacalcio: giornata dei voti e partite votate, giornata delle probabili e prima partita, quotati, indisponibili,
    URL delle schede giocatore (da data/fanta/schede.json). Cache per processo; tutto facoltativo (chiave assente = dato mancante)."""
    if _FANTA:
        return _FANTA
    c = {}
    v = _latest("voti")
    if v and v[1].get("ratings"):
        c["voti_md"] = v[0]; c["voti_fin"] = int(v[1].get("finished") or 0); c["voti_tot"] = int(v[1].get("total") or 0)
    p = _latest("probabili")
    if p and p[1].get("fixtures"):
        fx = p[1]["fixtures"]
        c["prob_md"] = p[0]; c["prob_n"] = len(fx)
        c["prob_date"] = min((f.get("date") or "" for f in fx if f.get("date")), default="")
    t = _latest("titolari")
    if t and t[1].get("status"):
        c["inj_n"] = sum(1 for s in t[1]["status"] if s.get("injury"))
    L = load_json(os.path.join(_DATA, "fanta", "listone.json"), {}) or {}
    if L.get("players"):
        c["list_n"] = len(L["players"])
    S = load_json(os.path.join(_DATA, "fanta", "schede.json"), {}) or {}
    c["player_urls"] = {pl.get("url") for pl in (S.get("players") or {}).values() if pl.get("url")}
    _FANTA.update(c)
    return _FANTA

def player_url(name):
    """URL della scheda giocatore se esiste (slug del nome come in render_stats.player_urls), altrimenti ''."""
    if not name:
        return ""
    u = "/giocatori/" + slugify(name) + ".html"
    return u if u in fanta_ctx().get("player_urls", set()) else ""

def fanta_card(art, lang, site):
    """Card "Fantacalcio" contestuale: frase con i numeri veri + link a voti, probabili, listone, indisponibili, hub, pagina squadra e scheda."""
    U = UI[lang]; c = fanta_ctx()
    parts, links = [], []
    if c.get("voti_md"):
        n, f, t = c["voti_md"], c["voti_fin"], c["voti_tot"]
        parts.append((U["fanta_voti_done"] if (t and f >= t) else U["fanta_voti_s"]).format(n=n, f=f, t=t))
        links.append((U["fanta_voti"].format(n=n), FANTA_URL["voti"]))
    if c.get("prob_md"):
        parts.append(U["fanta_prob_s"].format(n=c["prob_md"], p=c["prob_n"], d=fdate(c.get("prob_date", ""), lang)))
        links.append((U["fanta_prob"].format(n=c["prob_md"]), FANTA_URL["prob"]))
    if c.get("list_n"):
        parts.append(U["fanta_list_s"].format(n=c["list_n"]))
        links.append((U["fanta_list"].format(n=c["list_n"]), FANTA_URL["listone"]))
    if c.get("inj_n"):
        parts.append(U["fanta_inj_s"].format(n=c["inj_n"]))
        links.append((U["fanta_inj"], FANTA_URL["tit"]))
    links.append((U["fanta_all"], FANTA_URL["hub"]))
    team = art.get("team") or ""; tslug = TEAM_SLUG.get(team)
    if tslug:
        links.append((U["fanta_team"].format(t=team), "/squadre/" + tslug + ".html"))
    pu = player_url(art.get("giocatore"))
    if pu:
        links.append((U["fanta_player"].format(p=art["giocatore"]), pu))
    intro = U["fanta_intro"] + (": " + ", ".join(parts) if parts else "") + "."
    out = ['<aside class="card fanta"><h2>' + esc(U["fanta"]) + '</h2><div class="in"><p>' + esc(intro) + "</p><ul>"]
    out.append("".join('<li><a href="' + esc(site + u) + '">' + esc(n) + "</a></li>" for n, u in links))
    out.append("</ul>" + (('<p class="small">' + esc(U["fanta_note"]) + "</p>") if U["fanta_note"] else "") + "</div></aside>")
    return "".join(out)

HL_LABEL = {"it": "Gli highlights", "en": "Highlights", "es": "Lo más destacado"}
HL_NOTE = {"it": 'In Italia i match integrali sono su <a href="https://www.raiplay.it/" target="_blank" rel="noopener nofollow">RaiPlay</a>.',
           "en": 'In Italy, full matches are on <a href="https://www.raiplay.it/" target="_blank" rel="noopener nofollow">RaiPlay</a>.',
           "es": 'En Italia, los partidos completos están en <a href="https://www.raiplay.it/" target="_blank" rel="noopener nofollow">RaiPlay</a>.'}
def highlights_html(art, lang):
    hls = art.get("highlights") or []
    if not hls:
        return ""
    out = ['<section class="hls"><h2>' + HL_LABEL.get(lang, HL_LABEL["it"]) + '</h2>']
    for h in hls:
        yt = h.get("yt"); src = h.get("src", ""); match = h.get("match", "")
        out.append('<div class="hl">')
        if match:
            out.append('<div class="hlt">' + esc(match) + (' <span class="src">via ' + esc(src) + '</span>' if src else "") + '</div>')
        if yt:
            out.append('<div class="ytwrap"><iframe loading="lazy" src="https://www.youtube-nocookie.com/embed/' + esc(yt) + '" title="' + esc(match) + '" frameborder="0" allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>')
        elif h.get("link"):
            out.append('<a class="hllink" href="' + esc(h["link"]) + '" target="_blank" rel="noopener nofollow">' + ICON_PLAY + ' ' + esc(match) + '</a>')
        out.append('</div>')
    out.append('<p class="hlnote">' + HL_NOTE.get(lang, HL_NOTE["it"]) + '</p></section>')
    return "".join(out)

# Regole specifiche degli articoli, in aggiunta al CSS condiviso di site_common (token, scala 12/13/14/16/18/22, spazi multipli di 4).
ART_CSS = """.art{max-width:760px}
.art .kick{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 12px}
.art .team{display:inline-flex;align-items:center;gap:4px;font-size:13px;font-weight:600;color:var(--txt2)}a.team:hover{color:var(--brand-ink)}
.art .cover{width:100%;border-radius:12px;margin:0 0 12px;display:block}
.art .byline{font-size:13px;color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:16px}.art .byline a{font-weight:600}
.art .lead{font-size:18px;font-weight:600;line-height:1.5;margin-bottom:16px}
.art .body p{font-size:16px;line-height:1.65;margin-bottom:12px}
.pill.blue{background:#e3edfb;color:var(--blue)}
.sources ul,.fanta ul{list-style:none}
.sources li{font-size:14px;padding:8px 0;border-top:1px solid var(--line2);display:flex;gap:8px;flex-wrap:wrap}.sources li:first-child{border-top:0;padding-top:0}
.sources a{font-weight:600}.sources .w{color:var(--muted);font-size:12px}
.fanta ul{display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;margin-top:8px}.fanta li{padding:4px 0;font-size:14px}.fanta li a{font-weight:600}.fanta .small{margin:8px 0 0}
.disc{font-size:12px;color:var(--muted);margin-top:16px;font-style:italic}
.hl{margin-bottom:16px}.hlt{font-size:14px;font-weight:600;margin-bottom:8px}.hlt .src{color:var(--muted);font-weight:400}
.ytwrap{position:relative;padding-top:56.25%;border-radius:12px;overflow:hidden;background:#000}.ytwrap iframe{position:absolute;top:0;left:0;width:100%;height:100%;border:0}
a.hllink{display:inline-flex;align-items:center;gap:4px;font-size:14px;font-weight:600}
.hlnote{font-size:12px;color:var(--muted);margin-top:8px}.hlnote a{font-weight:600}
.lcard{display:block;background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-bottom:8px;color:var(--txt)}
.lcard:hover{border-color:var(--violet);color:var(--txt)}.lcard .h{font-size:18px;font-weight:600;line-height:1.25;margin:4px 0}.lcard .m{font-size:12px;color:var(--muted)}
@media(max-width:760px){.fanta ul{grid-template-columns:1fr}.art .lead{font-size:16px}}"""
CSS = SHELL_CSS + "\n" + ART_CSS

def head(title, desc, canon, alts, lang, og_img="", ld=None):
    """<head> completo: title/description entro i limiti (seo_title/seo_desc), canonical, hreflang (x-default = IT), og, CSS condiviso + regole articolo, JSON-LD."""
    h = ['<!DOCTYPE html><html lang="' + lang + '"><head><meta charset="UTF-8">', GA,
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>' + esc(seo_title(title)) + '</title>',
         '<meta name="description" content="' + esc(seo_desc(desc)) + '">',
         '<link rel="canonical" href="' + esc(canon) + '">']
    for l, u in alts.items():
        h.append('<link rel="alternate" hreflang="' + l + '" href="' + esc(u) + '">')
    if alts.get('it'):
        h.append('<link rel="alternate" hreflang="x-default" href="' + esc(alts['it']) + '">')
    h.append('<meta property="og:type" content="article"><meta property="og:site_name" content="TransferBeat">')
    h.append('<meta property="og:title" content="' + esc(title) + '">')
    h.append('<meta property="og:description" content="' + esc(seo_desc(desc)) + '">')
    h.append('<meta property="og:url" content="' + esc(canon) + '">')
    if og_img:
        h.append('<meta property="og:image" content="' + esc(og_img) + '">')
    h.append('<meta name="twitter:card" content="' + ("summary_large_image" if og_img else "summary") + '">')
    h.append('<style>' + CSS + '</style>')
    for o in (ld or []):
        h.append(ld_script(o))
    h.append('</head><body>')
    return "".join(h)

def topbar(lang, alts, site=""):
    """Testata unica del sito (voce attiva Articoli) + barra di sezione con le tre lingue dell'articolo + ribbon promo solo in italiano."""
    bar = [(LANG_LABEL[l], alts[l]) for l in LANGS if alts.get(l)]
    return shell_header(here="Articoli", bar=bar, bar_here=LANG_LABEL[lang]) + (ribbon() if lang == "it" else "")

def crumbs(art, lang, site, title, canon):
    """[(nome, url)] del breadcrumb: Home › Articoli › Squadra (se ha la pagina) › Articolo. Serve sia al visibile sia al BreadcrumbList."""
    items = [(UI[lang]["home"], site + "/"), (UI[lang]["list"], site + "/articoli/" + lang + "/")]
    tslug = TEAM_SLUG.get(art.get("team") or "")
    if tslug:
        items.append((art["team"], site + "/squadre/" + tslug + ".html"))
    items.append((title, canon))
    return items

def related_html(art, lang, site, arts):
    """Correlati: stessa squadra, poi stesso tipo; ultimi 5 (arts e' gia' ordinato per data)."""
    if not arts:
        return ""
    team = art.get("team") or ""; tipo = art.get("tipo") or ""; me = art.get("slug")
    cand = [a for a in arts if a.get("slug") != me and team and a.get("team") == team] + [a for a in arts if a.get("slug") != me and tipo and a.get("tipo") == tipo]
    pick = []
    for a in cand:
        if a not in pick:
            pick.append(a)
        if len(pick) >= 5:
            break
    if not pick:
        return ""
    items = []
    for a in pick:
        c = a["content"].get(lang) or a["content"]["it"]
        items.append('<li><a href="' + site + '/articoli/' + lang + '/' + a["slug"] + '.html">' + esc(c["title"]) + '</a><span class="w">' + esc(a.get("team") or "") + (' · ' if a.get("team") else '') + fdate(a.get("updated", ""), lang) + '</span></li>')
    return '<section class="card sources related"><h2>' + UI[lang]["related"] + '</h2><div class="in"><ul>' + "".join(items) + '</ul></div></section>'

def crumbs_ld(art, lang, site, title, canon):
    return breadcrumb_ld(crumbs(art, lang, site, title, canon))

def kicker(art, lang):
    """Pillola del tipo di articolo (o dello stato della trattativa): sfondo chiaro, testo scuro semantico."""
    st = art["stato"]; smn = art.get("smentita"); tipo = art.get("tipo", "")
    if tipo in TIPI:
        return TIPI[tipo]["pill"], TIPI[tipo]["label"].get(lang, tipo.upper())
    if smn:
        return "err", UI[lang]["smentita"]
    return STATE_PILL.get(st, ""), STATE_LABEL[lang].get(st, st)

def render_article(art, lang, site, arts=None):
    c = art["content"].get(lang) or art["content"]["it"]
    slug = art["slug"]
    canon = site + "/articoli/" + lang + "/" + slug + ".html"
    alts = {l: site + "/articoli/" + l + "/" + slug + ".html" for l in LANGS}
    tipo = art.get("tipo", "")
    pill, badge_txt = kicker(art, lang)
    og_img = ""
    if tipo in TIPI:
        badge_txt += " · " + fdate(art.get("updated", "") or art.get("created", ""), lang)
        og_img = site + "/img/" + TIPI[tipo]["cover"]
    title = c["title"]; lead = c["lead"]
    desc = lead or title
    team = art.get("team", ""); tslug = TEAM_SLUG.get(team or "")
    # JSON-LD: NewsArticle (con about e citation se ci sono fonti) + BreadcrumbList, nel <head>
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": title,
          "description": desc, "datePublished": art.get("created", ""), "dateModified": art.get("updated", ""),
          "inLanguage": lang, "mainEntityOfPage": {"@type": "WebPage", "@id": canon},
          "articleSection": "Calcio", "author": AUTHOR_LD, "publisher": ORG}
    if og_img:
        ld["image"] = [og_img]
    if art.get("updates"):
        ld["about"] = [{"@type": "Person", "name": art.get("giocatore", "")}] + ([{"@type": "SportsTeam", "name": team}] if team else [])
        ld["citation"] = [{"@type": "CreativeWork", "name": u["fonte"], "url": u["link"]} for u in art["updates"]]
    out = [head(title, desc, canon, alts, lang, og_img, ld=[ld, crumbs_ld(art, lang, site, title, canon)]), topbar(lang, alts, site)]
    out.append('<main class="wrap">' + breadcrumb_html(crumbs(art, lang, site, title, canon)))
    out.append('<article class="art">')
    # riga di testa: pillola del tipo/stato, squadra con stemma e link, competizione
    out.append('<div class="kick"><span class="pill' + ((" " + pill) if pill else "") + '">' + esc(badge_txt) + '</span>')
    if team:
        inner = team_badge(TEAMS.get(team) or {"lab": art.get("lab", ""), "col": art.get("col", "")}, 22) + esc(team)
        out.append(('<a class="team" href="' + site + '/squadre/' + tslug + '.html">' + inner + '</a>') if tslug else '<span class="team">' + inner + '</span>')
    comp = COMP_BY_LEAGUE.get(art.get("league") or "")
    if comp:
        out.append('<a class="team" href="' + site + '/campionati/' + comp["slug"] + '.html">' + esc(comp["nome"]) + '</a>')
    out.append('</div>')
    if tipo in TIPI:
        out.append('<img class="cover" src="/img/' + TIPI[tipo]["cover"] + '" alt="">')
    out.append('<h1>' + esc(title) + '</h1>')
    out.append('<div class="byline">' + UI[lang]["by"] + ' · ' + UI[lang]["edby"] + ' <a href="' + AUTHOR["url"] + '" rel="author">' + esc(AUTHOR["name"]) + '</a> · ' + UI[lang]["updated"] + ' ' + fdate(art.get("updated",""), lang) + '</div>')
    if lead:
        out.append('<p class="lead">' + esc(lead) + '</p>')
    out.append('<div class="body">' + "".join('<p>' + esc(p) + '</p>' for p in c["body"]) + '</div>')
    out.append(highlights_html(art, lang))
    out.append(fanta_card(art, lang, site))
    out.append(related_html(art, lang, site, arts))
    # fonti (solo se presenti)
    if art.get("updates"):
        out.append('<section class="card sources"><h2>' + UI[lang]["sources"] + '</h2><div class="in"><ul>')
        for u in art["updates"]:
            out.append('<li><a href="' + esc(u["link"]) + '" target="_blank" rel="noopener nofollow">' + esc(u["fonte"]) + '</a>'
                       '<span class="w">' + esc(STATE_LABEL[lang].get(u.get("stato","rumor"), "")) + ' · ' + fdate(u.get("ts",""), lang) + '</span></li>')
        out.append('</ul></div></section>')
    out.append('<p class="disc">' + UI[lang]["disc"] + '</p>')
    out.append('</article></main>')
    out.append(shell_footer() + '</body></html>')
    return "".join(out)

# Title (senza suffisso: lo aggiunge seo_title) e description degli indici articoli, kb/SEO.md §0.2.
INDEX_META = {
  "it": ("Articoli: recap, lunch break e focus", "Tutti gli articoli di TransferBeat: il Recap di giornata su campionati e coppe, il Lunch Break di metà giornata e il Focus sulla storia del giorno."),
  "en": ("Articles: recaps, lunch breaks and focus", "All TransferBeat articles: the daily Recap on leagues and cups, the midday Lunch Break and the Focus on the story of the day, in English."),
  "es": ("Artículos: recap, lunch break y focus", "Todos los artículos de TransferBeat: el Recap del día sobre ligas y copas, el Lunch Break de mediodía y el Focus sobre la historia del día."),
}

def render_index(arts, lang, site):
    canon = site + "/articoli/" + lang + "/"
    alts = {l: site + "/articoli/" + l + "/" for l in LANGS}
    meta = INDEX_META[lang]
    cr = [(UI[lang]["home"], site + "/"), (UI[lang]["list"], canon)]
    out = [head(meta[0], meta[1], canon, alts, lang, ld=[breadcrumb_ld(cr)]), topbar(lang, alts, site)]
    out.append('<main class="wrap">' + breadcrumb_html(cr) + '<div class="art"><h1>' + UI[lang]["list"] + '</h1><p class="sub">' + esc(meta[1]) + '</p>')
    for a in arts:
        c = a["content"].get(lang) or a["content"]["it"]
        pill, lbl = kicker(a, lang)
        out.append('<a class="lcard" href="' + site + '/articoli/' + lang + '/' + a["slug"] + '.html">'
                   '<span class="pill' + ((" " + pill) if pill else "") + '">' + esc(lbl) + '</span>'
                   '<div class="h">' + esc(c["title"]) + '</div>'
                   '<div class="m">' + esc(a.get("team","")) + (' · ' if a.get("team") else '') + fdate(a.get("updated",""), lang) + '</div></a>')
    if not arts:
        out.append('<p class="small">—</p>')
    out.append(fanta_card({}, lang, site))
    out.append('</div></main>' + shell_footer() + '</body></html>')
    return "".join(out)

def render_all(arts, site, pages_dir, data_dir):
    os.makedirs(pages_dir, exist_ok=True)
    for lang in LANGS:
        d = os.path.join(pages_dir, lang)
        os.makedirs(d, exist_ok=True)
        for a in arts:
            open(os.path.join(d, a["slug"] + ".html"), "w", encoding="utf-8", newline="\n").write(render_article(a, lang, site, arts))
        open(os.path.join(d, "index.html"), "w", encoding="utf-8", newline="\n").write(render_index(arts, lang, site))
    # index.json per il front-end
    idx = {"aggiornato": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "articoli": []}
    for a in arts:
        entry = {"slug": a["slug"], "tipo": a.get("tipo", ""), "giocatore": a.get("giocatore", ""), "team": a.get("team", ""),
                 "league": a.get("league", ""), "lab": a.get("lab", ""), "col": a.get("col", ""),
                 "stato": a["stato"], "smentita": a.get("smentita", False), "updated": a.get("updated", ""),
                 "t": {l: (a["content"].get(l) or a["content"]["it"])["title"] for l in LANGS}}
        idx["articoli"].append(entry)
    os.makedirs(os.path.join(data_dir, "articles"), exist_ok=True)
    json.dump(idx, open(os.path.join(data_dir, "articles", "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # sitemap degli articoli: lastmod = data reale di aggiornamento di ogni articolo (kb/SEO.md §0.6).
    # L'indice sitemap.xml (con le altre sitemap generate da render_site.py) e robots.txt li scrive write_sitemap_index.
    entries = [(site + "/articoli/" + lang + "/", date_only(arts[0].get("updated", "")) if arts else "") for lang in LANGS]
    for lang in LANGS:
        for a in arts:
            entries.append((site + "/articoli/" + lang + "/" + a["slug"] + ".html", date_only(a.get("updated", ""))))
    root = os.path.dirname(pages_dir)
    write_urlset(os.path.join(root, "sitemap-articoli.xml"), entries)
    write_sitemap_index(root)
    return len(arts)
