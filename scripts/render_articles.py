#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render pagine statiche degli articoli + indici + sitemap.xml + robots.txt."""
import json, os, html
from datetime import datetime, timezone

LANGS = ("it", "en", "es")
STATE_LABEL = {
    "it": {"rumor": "Rumor", "obj": "Obiettivo", "conf": "Trattativa confermata", "done": "Affare concluso"},
    "en": {"rumor": "Rumour", "obj": "Target", "conf": "Deal agreed", "done": "Done deal"},
    "es": {"rumor": "Rumor", "obj": "Objetivo", "conf": "Negociacion confirmada", "done": "Cerrado"},
}
STATE_COLOR = {"rumor": "#d98700", "obj": "#d98700", "conf": "#7b46c9", "done": "#0a9d57"}
UI = {
  "it": {"by": "Redazione TransferBeat", "sources": "Fonti", "updated": "Aggiornato il", "home": "Home",
         "board": "Board live", "campionati": "Campionati", "back": "← Tutti gli articoli", "status": "Stato", "list": "Articoli",
         "disc": "TransferBeat aggrega notizie di mercato citando le fonti originali. Notizia in aggiornamento.",
         "via": "via", "smentita": "SMENTITA"},
  "en": {"by": "TransferBeat Newsroom", "sources": "Sources", "updated": "Updated on", "home": "Home",
         "board": "Live board", "campionati": "Leagues", "back": "← All articles", "status": "Status", "list": "Articles",
         "disc": "TransferBeat aggregates transfer news citing the original sources. Developing story.",
         "via": "via", "smentita": "DENIED"},
  "es": {"by": "Redaccion TransferBeat", "sources": "Fuentes", "updated": "Actualizado el", "home": "Inicio",
         "board": "Board en vivo", "campionati": "Ligas", "back": "← Todos los articulos", "status": "Estado", "list": "Articulos",
         "disc": "TransferBeat agrega noticias de mercado citando las fuentes originales. Noticia en desarrollo.",
         "via": "via", "smentita": "DESMENTIDO"},
}
RECAP_LABEL = {"it": "RECAP DI GIORNATA", "en": "DAILY RECAP", "es": "RESUMEN DEL DIA"}
STORIA_LABEL = {"it": "FOCUS", "en": "FOCUS", "es": "FOCO"}
LUNCH_LABEL = {"it": "LUNCH BREAK", "en": "LUNCH BREAK", "es": "LUNCH BREAK"}
SCOOP_LABEL = {"it": "SCOOP", "en": "SCOOP", "es": "SCOOP"}
NOTTI_LABEL = {"it": "NOTTI MONDIALI", "en": "WORLD CUP NIGHTS", "es": "NOCHES MUNDIALES"}
TIPI = {"recap": {"label": RECAP_LABEL, "col": "#0a9d57", "cover": "cover-recap.svg"},
        "lunch": {"label": LUNCH_LABEL, "col": "#d98700", "cover": "cover-lunch.svg"},
        "storia": {"label": STORIA_LABEL, "col": "#1f6fd6", "cover": "cover-storia.svg"},
        "scoop": {"label": SCOOP_LABEL, "col": "#e0392b", "cover": "cover-scoop.svg"},
        "notti": {"label": NOTTI_LABEL, "col": "#21366e", "cover": "cover-notti.svg"}}
MONTHS = {"it": ["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"],
          "en": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
          "es": ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]}

def esc(s):
    return html.escape(str(s or ""), quote=True)

def fdate(iso, lang):
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return str(d.day) + " " + MONTHS[lang][d.month - 1] + " " + str(d.year)
    except Exception:
        return ""

HL_LABEL = {"it": "Gli highlights", "en": "Highlights", "es": "Lo m\u00e1s destacado"}
HL_NOTE = {"it": 'In Italia i match integrali sono su <a href="https://www.raiplay.it/" target="_blank" rel="noopener nofollow">RaiPlay</a>.',
           "en": 'In Italy, full matches are on <a href="https://www.raiplay.it/" target="_blank" rel="noopener nofollow">RaiPlay</a>.',
           "es": 'En Italia, los partidos completos est\u00e1n en <a href="https://www.raiplay.it/" target="_blank" rel="noopener nofollow">RaiPlay</a>.'}
def highlights_html(art, lang):
    hls = art.get("highlights") or []
    if not hls:
        return ""
    out = ['<div class="hls"><h2>' + HL_LABEL.get(lang, HL_LABEL["it"]) + '</h2>']
    for h in hls:
        yt = h.get("yt"); src = h.get("src", ""); match = h.get("match", "")
        out.append('<div class="hl">')
        if match:
            out.append('<div class="hlt">' + esc(match) + (' <span class="src">via ' + esc(src) + '</span>' if src else "") + '</div>')
        if yt:
            out.append('<div class="ytwrap"><iframe loading="lazy" src="https://www.youtube-nocookie.com/embed/' + esc(yt) + '" title="' + esc(match) + '" frameborder="0" allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>')
        elif h.get("link"):
            out.append('<a class="hlnote" href="' + esc(h["link"]) + '" target="_blank" rel="noopener nofollow">\u25b6 ' + esc(match) + '</a>')
        out.append('</div>')
    out.append('<p class="hlnote">' + HL_NOTE.get(lang, HL_NOTE["it"]) + '</p></div>')
    return "".join(out)

CSS = """*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#fff;color:#161b21;line-height:1.6}
a{color:inherit;text-decoration:none}
.wrap{max-width:760px;margin:0 auto;padding:0 18px}
.top{border-bottom:1px solid #e2e6ea;padding:14px 0;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.brand{font-family:Georgia,serif;font-size:26px;font-weight:700}.brand b{color:#0a9d57}
.nav a{font-size:13px;color:#67727e;margin-left:14px}
.langsw a{font-size:11px;font-weight:700;padding:3px 7px;border:1px solid #e2e6ea;border-radius:6px;color:#67727e;margin-left:4px}
.langsw a.on{background:#161b21;color:#fff;border-color:#161b21}
.crumbs{font-size:12px;color:#8a94a0;padding:14px 0 0}
article{padding:10px 0 30px}
.badge{display:inline-block;font-size:11px;font-weight:800;letter-spacing:.4px;color:#fff;padding:3px 9px;border-radius:5px;text-transform:uppercase}
.team{display:inline-flex;align-items:center;gap:7px;font-size:13px;color:#67727e;margin-left:8px}
.team .lab{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:5px;color:#fff;font-size:10px;font-weight:800}
h1{font-family:Georgia,serif;font-size:32px;line-height:1.22;margin:14px 0 8px}
.byline{font-size:13px;color:#8a94a0;border-bottom:1px solid #e2e6ea;padding-bottom:14px;margin-bottom:18px}
.lead{font-size:18px;font-weight:600;margin-bottom:16px}
article p{margin-bottom:14px;font-size:16px}
.sources{background:#f7f8fa;border:1px solid #e2e6ea;border-radius:10px;padding:14px 16px;margin-top:22px}
.sources h2{font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:#67727e;margin-bottom:10px}
.sources li{list-style:none;font-size:14px;padding:6px 0;border-top:1px solid #eef1f5;display:flex;gap:8px;flex-wrap:wrap}
.sources li:first-child{border-top:0}
.sources a{color:#1f6fd6;font-weight:600}
.sources .w{color:#8a94a0;font-size:12px}
.disc{font-size:12px;color:#8a94a0;margin-top:18px;font-style:italic}
.foot{border-top:1px solid #e2e6ea;padding:18px 0;font-size:12px;color:#8a94a0;text-align:center}
.lcard{display:block;border:1px solid #e2e6ea;border-radius:10px;padding:14px 16px;margin-bottom:12px}
.lcard:hover{border-color:#0a9d57}
.lcard .h{font-family:Georgia,serif;font-size:19px;margin:6px 0 4px}
.lcard .m{font-size:12px;color:#8a94a0}
.list-h{font-family:Georgia,serif;font-size:28px;margin:18px 0 4px}
.hls{margin:26px 0}.hls h2{font-family:Georgia,serif;font-size:22px;margin-bottom:14px}
.hl{margin-bottom:18px}.hlt{font-size:14px;font-weight:600;margin-bottom:8px}.hlt .src{color:#8a94a0;font-weight:400}
.ytwrap{position:relative;padding-top:56.25%;border-radius:10px;overflow:hidden;background:#000}
.ytwrap iframe{position:absolute;top:0;left:0;width:100%;height:100%;border:0}
.hlnote{font-size:12.5px;color:#8a94a0;margin-top:10px}.hlnote a{color:#1f6fd6;font-weight:600}"""

def head(title, desc, canon, alts, lang, og_img=""):
    h = ['<!DOCTYPE html><html lang="' + lang + '"><head><meta charset="UTF-8">',
         '<script async src="https://www.googletagmanager.com/gtag/js?id=G-RLST76W6H2"></script>',
         "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-RLST76W6H2');</script>",
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>' + esc(title) + ' | TransferBeat</title>',
         '<meta name="description" content="' + esc(desc) + '">',
         '<link rel="canonical" href="' + esc(canon) + '">']
    for l, u in alts.items():
        h.append('<link rel="alternate" hreflang="' + l + '" href="' + esc(u) + '">')
    h.append('<meta property="og:type" content="article"><meta property="og:site_name" content="TransferBeat">')
    h.append('<meta property="og:title" content="' + esc(title) + '">')
    h.append('<meta property="og:description" content="' + esc(desc) + '">')
    h.append('<meta property="og:url" content="' + esc(canon) + '">')
    if og_img:
        h.append('<meta property="og:image" content="' + esc(og_img) + '">')
    h.append('<meta name="twitter:card" content="' + ("summary_large_image" if og_img else "summary") + '">')
    h.append('<style>' + CSS + '</style></head><body>')
    return "".join(h)

def topbar(lang, alts, site):
    nav = ('<a href="' + site + '/?lang=' + lang + '">' + UI[lang]["home"] + '</a>'
           '<a href="' + site + '/board.html?lang=' + lang + '">' + UI[lang]["board"] + '</a>'
           '<a href="' + site + '/campionati.html?lang=' + lang + '">' + UI[lang]["campionati"] + '</a>')
    langs = "".join('<a class="' + ("on" if l == lang else "") + '" href="' + esc(alts[l]) + '">' + l.upper() + '</a>' for l in LANGS)
    return ('<div class="wrap"><div class="top"><a class="brand" href="' + site + '/?lang=' + lang + '">Transfer<b>Beat</b></a>'
            '<div><span class="nav">' + nav + '</span> <span class="langsw">' + langs + '</span></div></div></div>')

def render_article(art, lang, site):
    c = art["content"].get(lang) or art["content"]["it"]
    slug = art["slug"]
    canon = site + "/articoli/" + lang + "/" + slug + ".html"
    alts = {l: site + "/articoli/" + l + "/" + slug + ".html" for l in LANGS}
    st = art["stato"]; smn = art.get("smentita")
    tipo = art.get("tipo", "")
    badge_col = "#e0392b" if smn else STATE_COLOR.get(st, "#67727e")
    badge_txt = UI[lang]["smentita"] if smn else STATE_LABEL[lang].get(st, st)
    og_img = ""
    if tipo in TIPI:
        badge_col = TIPI[tipo]["col"]
        badge_txt = TIPI[tipo]["label"].get(lang, tipo.upper()) + " · " + fdate(art.get("updated", "") or art.get("created", ""), lang)
        og_img = site + "/img/" + TIPI[tipo]["cover"]
    title = c["title"]; lead = c["lead"]
    desc = lead or title
    out = [head(title, desc, canon, alts, lang, og_img), topbar(lang, alts, site)]
    out.append('<div class="wrap">')
    out.append('<div class="crumbs"><a href="' + site + '/articoli/' + lang + '/">' + UI[lang]["list"] + '</a> / ' + esc(art.get("team","")) + '</div>')
    out.append('<article>')
    team = art.get("team", ""); lab = art.get("lab", ""); col = art.get("col", "#0a9d57")
    out.append('<span class="badge" style="background:' + badge_col + '">' + esc(badge_txt) + '</span>')
    if team:
        out.append('<span class="team"><span class="lab" style="background:' + esc(col) + '">' + esc(lab) + '</span>' + esc(team) + '</span>')
    if tipo in TIPI:
        out.append('<img src="../../img/' + TIPI[tipo]["cover"] + '" alt="" style="width:100%;border-radius:12px;margin:14px 0 2px;display:block">')
    out.append('<h1>' + esc(title) + '</h1>')
    out.append('<div class="byline">' + UI[lang]["by"] + ' · ' + UI[lang]["updated"] + ' ' + fdate(art.get("updated",""), lang) + '</div>')
    if lead:
        out.append('<p class="lead">' + esc(lead) + '</p>')
    for p in c["body"]:
        out.append('<p>' + esc(p) + '</p>')
    out.append(highlights_html(art, lang))
    # fonti (solo se presenti)
    if not art.get("updates"):
        out.append('<p class="disc">' + UI[lang]["disc"] + '</p>')
        out.append('</article></div>')
        out.append('<div class="wrap"><div class="foot">© TransferBeat</div></div>')
        ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": title,
              "description": desc, "datePublished": art.get("created", ""), "dateModified": art.get("updated", ""),
              "inLanguage": lang, "mainEntityOfPage": {"@type": "WebPage", "@id": canon},
              "articleSection": "Calciomercato",
              "author": {"@type": "Organization", "name": "TransferBeat"},
              "publisher": {"@type": "Organization", "name": "TransferBeat"}}
        if og_img:
            ld["image"] = [og_img]
        out.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + '</script>')
        out.append('<script src="/fanta/promo.js" defer></script></body></html>')
        return "".join(out)
    out.append('<div class="sources"><h2>' + UI[lang]["sources"] + '</h2><ul>')
    for u in art["updates"]:
        out.append('<li><a href="' + esc(u["link"]) + '" target="_blank" rel="noopener nofollow">' + esc(u["fonte"]) + '</a>'
                   '<span class="w">' + esc(STATE_LABEL[lang].get(u.get("stato","rumor"), "")) + ' · ' + fdate(u.get("ts",""), lang) + '</span></li>')
    out.append('</ul></div>')
    out.append('<p class="disc">' + UI[lang]["disc"] + '</p>')
    out.append('</article></div>')
    out.append('<div class="wrap"><div class="foot">© TransferBeat · ' + esc(team) + '</div></div>')
    # JSON-LD
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": title,
          "description": desc, "datePublished": art.get("created", ""), "dateModified": art.get("updated", ""),
          "inLanguage": lang, "mainEntityOfPage": {"@type": "WebPage", "@id": canon},
          "articleSection": "Calciomercato", "author": {"@type": "Organization", "name": "TransferBeat"},
          "publisher": {"@type": "Organization", "name": "TransferBeat",
                        "logo": {"@type": "ImageObject", "url": site + "/favicon.png"}},
          "about": [{"@type": "Person", "name": art.get("giocatore", "")},
                    {"@type": "SportsTeam", "name": team}] if team else [{"@type": "Person", "name": art.get("giocatore", "")}],
          "citation": [{"@type": "CreativeWork", "name": u["fonte"], "url": u["link"]} for u in art["updates"]]}
    out.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + '</script>')
    bc = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "TransferBeat", "item": site + "/"},
            {"@type": "ListItem", "position": 2, "name": UI[lang]["list"], "item": site + "/articoli/" + lang + "/"},
            {"@type": "ListItem", "position": 3, "name": title, "item": canon}]}
    out.append('<script type="application/ld+json">' + json.dumps(bc, ensure_ascii=False) + '</script>')
    out.append('<script src="/fanta/promo.js" defer></script></body></html>')
    return "".join(out)

def render_index(arts, lang, site):
    canon = site + "/articoli/" + lang + "/"
    alts = {l: site + "/articoli/" + l + "/" for l in LANGS}
    out = [head(UI[lang]["list"], UI[lang]["list"] + " - TransferBeat", canon, alts, lang), topbar(lang, alts, site)]
    out.append('<div class="wrap"><h1 class="list-h">' + UI[lang]["list"] + '</h1>')
    for a in arts:
        c = a["content"].get(lang) or a["content"]["it"]
        st = a["stato"]; smn = a.get("smentita")
        col = "#e0392b" if smn else STATE_COLOR.get(st, "#67727e")
        lbl = UI[lang]["smentita"] if smn else STATE_LABEL[lang].get(st, st)
        if a.get("tipo") in TIPI:
            t = TIPI[a["tipo"]]
            col = t["col"]; lbl = t["label"].get(lang, a["tipo"].upper())
        out.append('<a class="lcard" href="' + site + '/articoli/' + lang + '/' + a["slug"] + '.html">'
                   '<span class="badge" style="background:' + col + ';font-size:10px">' + esc(lbl) + '</span>'
                   '<div class="h">' + esc(c["title"]) + '</div>'
                   '<div class="m">' + esc(a.get("team","")) + ' · ' + fdate(a.get("updated",""), lang) + '</div></a>')
    if not arts:
        out.append('<p style="color:#8a94a0">—</p>')
    out.append('</div><div class="wrap"><div class="foot">© TransferBeat</div></div><script src="/fanta/promo.js" defer></script></body></html>')
    return "".join(out)

def render_all(arts, site, pages_dir, data_dir):
    os.makedirs(pages_dir, exist_ok=True)
    for lang in LANGS:
        d = os.path.join(pages_dir, lang)
        os.makedirs(d, exist_ok=True)
        for a in arts:
            open(os.path.join(d, a["slug"] + ".html"), "w", encoding="utf-8").write(render_article(a, lang, site))
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(render_index(arts, lang, site))
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
    # sitemap
    urls = [site + "/", site + "/board.html", site + "/campionati.html", site + "/mondiali.html", site + "/fonti.html", site + "/fanta/", site + "/fantatb.html"]
    for lang in LANGS:
        urls.append(site + "/articoli/" + lang + "/")
        for a in arts:
            urls.append(site + "/articoli/" + lang + "/" + a["slug"] + ".html")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for u in urls:
        sm.append("<url><loc>" + esc(u) + "</loc><lastmod>" + today + "</lastmod></url>")
    sm.append("</urlset>")
    open(os.path.join(os.path.dirname(pages_dir), "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sm))
    open(os.path.join(os.path.dirname(pages_dir), "robots.txt"), "w", encoding="utf-8").write(
        "User-agent: *\nAllow: /\nSitemap: " + site + "/sitemap.xml\n")
    return len(arts)
