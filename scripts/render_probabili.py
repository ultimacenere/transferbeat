# -*- coding: utf-8 -*-
"""Pagina delle probabili formazioni (fantacalcio/probabili-formazioni.html e archivio probabili-giornata-N.html) da data/fanta/probabili-NN.json.
Importato da render_site.py (kb/FANTATB.md §20, kb/SEO.md §3.6). Guscio unico di site_common (testata, barra Fantacalcio, footer);
struttura del mockup Probabili.dc.html: sub citabile, chip delle giornate, indice delle partite in griglia, una card per partita con i due
mezzi campi SVG affiancati (uno sotto l'altro su mobile), riga modulo/allenatore/base dati, testo leggibile per squadra; legenda in fondo.
Ancore: id="partita-<slug casa>-<slug ospite>" sulla card e id="squadra-<slug>" su ogni blocco squadra (slug di site_common.slugify sul nome di teams.json)."""
from site_common import esc, page, fdate_it, slugify, badge, SITE, SEASON, FANTA_BAR

ROW_LABEL = {"G": "in porta", "D": "in difesa", "M": "a centrocampo", "F": "in attacco"}
# Colori del campo: erba unica (niente strisce), linee bianche al 60%, percentuali in tinta chiara con bordo scuro per restare leggibili sul verde.
PITCH = "#2f9e5f"
PCT_ON_PITCH = {"g": "#b6f3cf", "a": "#ffe08a", "r": "#ffb3a7"}
FONT_SVG = "'Segoe UI',system-ui,-apple-system,Roboto,'Helvetica Neue',Arial,sans-serif"
# Solo regole proprie della pagina: i token, .pct, .note, .chips, .pill, .card e .faq arrivano dal CSS condiviso.
PITCH_CSS = """
.chips .pf-hint{border:0;background:none;padding:0 0 0 4px;font-weight:400;color:var(--muted)}
.pf-idx{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:0 0 24px}
.pf-idx a{display:flex;flex-direction:column;gap:4px;min-width:0;background:#fff;border:1px solid var(--line);border-radius:12px;padding:8px 10px;color:var(--txt);font-size:13px}
.pf-idx a:hover{border-color:var(--violet);color:var(--txt)}
.pf-idx .t{display:flex;align-items:center;gap:5px;font-weight:600;min-width:0}.pf-idx .t .badge{margin:0}.pf-idx .t .vs{color:var(--muted);font-weight:400}
.pf-idx .t span.n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pf-idx .d{font-size:12px;color:var(--muted)}
.pf-match{margin:0 0 24px}
.pf-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 16px;border-bottom:1px solid var(--line)}
.pf-head h2{font-family:var(--font);font-size:18px;font-weight:600;margin:0;line-height:1.25}.pf-head h2 a{color:var(--txt)}.pf-head h2 a:hover{color:var(--brand-ink)}
.pf-head .d{font-size:13px;color:var(--muted)}
.pf-halves{display:grid;grid-template-columns:1fr 1fr;gap:0}
.pf-half{padding:16px 16px 8px;display:flex;flex-direction:column;gap:8px}.pf-half svg{width:100%;height:auto;display:block;border-radius:8px}
.pf-meta{font-size:12px;color:var(--muted);line-height:1.5}.pf-meta b{color:var(--txt)}
.pf-pills{display:flex;flex-wrap:wrap;gap:4px 6px;align-items:center;font-size:12px;color:var(--muted)}
.pf-txt{padding:8px 16px 16px;color:var(--txt2)}.pf-txt p{margin:0 0 8px}.pf-txt p:last-child{margin-bottom:0}.pf-txt p b{color:var(--txt)}
.pf-list{columns:2;column-gap:24px;font-size:13px;list-style:none;padding:0;margin:0 0 16px}.pf-list li{break-inside:avoid;padding:4px 0}
.pf-top{display:none}
@media(max-width:760px){
.pf-idx{grid-template-columns:repeat(2,minmax(0,1fr))}.pf-halves{grid-template-columns:1fr}.pf-half{padding:12px 12px 4px}.pf-head{padding:12px}.pf-txt{padding:8px 12px 12px}.pf-list{columns:1}
.pf-top{display:inline-flex;position:fixed;right:16px;bottom:16px;z-index:10;margin:0;box-shadow:0 2px 8px rgba(27,17,64,.25)}
}
/* Telefoni stretti: una colonna con nomi e data sulla stessa riga, cosi' la griglia non supera mai il viewport (minmax(0,1fr) evita
   che le due colonne si allarghino al min-content delle card con i nomi in nowrap: 'Frosinone - Cagliari' superava i 375px). */
@media(max-width:479px){
.pf-idx{grid-template-columns:minmax(0,1fr)}
.pf-idx a{flex-direction:row;align-items:center;justify-content:space-between;gap:8px;padding:8px 12px}
.pf-idx .d{flex:none;white-space:nowrap}
}
"""

def pct_cls(v):
    return "g" if v >= 70 else ("a" if v >= 40 else "r")

def team_slug(T, name):
    """Slug della squadra come nelle pagine squadra: nome canonico di teams.json (via T.fanta_name) o, se manca, il nome del feed."""
    n = T.fanta_name(name or "")
    return T.slug[n] if n else slugify(name)

def team_badge(T, name, size=18):
    n = T.fanta_name(name or "")
    return badge(T.by_name.get(n) if n else None, size)

def short_name(T, name):
    """Nome di teams.json (Milan, Roma) al posto di quello del feed (AC Milan, AS Roma) nelle card dell'indice."""
    return T.fanta_name(name or "") or name

def half_svg(team, col, col2, mirror, plink=None, pctx=None):
    """Mezzo campo orizzontale: porta a sinistra (mirror=False) o a destra (mirror=True). Griglia API 'riga:colonna'."""
    W, H = 360, 240
    rows = {}
    for x in team["xi"]:
        try:
            r, c = [int(v) for v in (x.get("grid") or "1:1").split(":")]
        except ValueError:
            r, c = 1, 1
        rows.setdefault(r, []).append((c, x))
    R = max(rows) if rows else 1
    g = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Probabile formazione %s">' % (W, H, esc(team["name"])),
         '<rect width="%d" height="%d" fill="%s"/>' % (W, H, PITCH)]
    def X(v):
        return W - v if mirror else v
    L = 'fill="none" stroke="#fff" stroke-opacity=".6" stroke-width="2"'
    # linee: bordo, area, porta, dischetto, metà campo con semicerchio
    g.append('<rect x="2" y="4" width="356" height="232" %s/>' % L)
    ax = 2 if not mirror else W - 2 - 66
    g.append('<rect x="%d" y="%d" width="66" height="132" %s/>' % (ax, (H - 132) // 2, L))
    gx = 2 if not mirror else W - 2 - 24
    g.append('<rect x="%d" y="%d" width="24" height="60" %s/>' % (gx, (H - 60) // 2, L))
    g.append('<circle cx="%d" cy="%d" r="2.5" fill="#fff" fill-opacity=".6"/>' % (X(46), H // 2))
    mx = W - 2 if not mirror else 2
    g.append('<line x1="%d" y1="4" x2="%d" y2="%d" stroke="#fff" stroke-opacity=".6" stroke-width="2"/>' % (mx, mx, H - 4))
    g.append('<path d="M %d %d A 44 44 0 0 %d %d %d" %s/>' % (mx, H // 2 - 44, 0 if not mirror else 1, mx, H // 2 + 44, L))
    xs = [30 + (r - 1) * (275 / max(R - 1, 1)) for r in range(1, R + 1)]
    for r in sorted(rows):
        lst = sorted(rows[r], key=lambda t: t[0])
        n = len(lst)
        for i, (c, x) in enumerate(lst):
            cx = X(xs[r - 1]); cy = 26 + (i + 0.5) * (188 / n)
            b = x.get("ballot")
            name = x["name"] if len(x["name"]) <= 14 else x["name"].split()[-1]
            g.append('<g><circle cx="%.1f" cy="%.1f" r="12" fill="%s" stroke="%s" stroke-width="2.5"%s/>' % (cx, cy, esc(col), esc(col2), ' stroke-dasharray="3 2"' if b else ""))
            if x.get("role"):
                g.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="9" font-weight="700" fill="#fff" stroke="rgba(0,0,0,.45)" stroke-width="1.5" paint-order="stroke" font-family="%s">%s</text>' % (cx, cy + 3.3, FONT_SVG, esc(x["role"])))
            g.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="10.5" font-weight="700" fill="#fff" stroke="#123" stroke-width="2.5" paint-order="stroke" font-family="%s">%s</text>' % (cx, cy + 25, FONT_SVG, esc(name)))
            if b:
                share = x.get("share") or 50
                g.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="9" font-weight="700" fill="%s" stroke="#123" stroke-width="2" paint-order="stroke" font-family="%s">%d%% · %s %d%%</text>' % (
                    cx, cy + 36, PCT_ON_PITCH["a"], FONT_SVG, share, esc(b["name"] if len(b["name"]) <= 12 else b["name"].split()[-1]), b["share"]))
            else:
                g.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="9.5" font-weight="700" fill="%s" stroke="#123" stroke-width="2" paint-order="stroke" font-family="%s">%d%%</text>' % (
                    cx, cy + 36, PCT_ON_PITCH[pct_cls(x["prob"])], FONT_SVG, x["prob"]))
            g.append("</g>")
    g.append("</svg>")
    return "".join(g)

def group_by_row(team):
    rows = {}
    for x in team["xi"]:
        try:
            r = int((x.get("grid") or "1:1").split(":")[0])
        except ValueError:
            r = 1
        rows.setdefault(r, []).append(x)
    return [rows[r] for r in sorted(rows)]

def names(lst, plink, pctx, with_pct=True):
    out = []
    for x in lst:
        s = plink(pctx, x["id"], x["name"])
        if with_pct:
            s += ' <span class="pct %s">%d%%</span>' % (pct_cls(x["prob"]), x["prob"])
        out.append(s)
    return ", ".join(out[:-1]) + (" e " if len(out) > 1 else "") + out[-1] if out else ""

def team_text(team, T, plink, pctx, fanta_team_link):
    """Paragrafo leggibile: modulo, reparti con percentuali, ballottaggi, sostituzioni forzate, indisponibili, dubbi."""
    rows = group_by_row(team)
    coach = (" di " + esc(team["coach"])) if team.get("coach") else ""
    based = [b for b in team.get("based_on") or []]
    same = all(b.get("formation") == team.get("module") for b in based) and len(based) >= 2
    who = "<b>" + fanta_team_link(T, team["name"]) + coach + "</b>"
    intro = ("%s dovrebbe confermare il %s delle ultime %d uscite" % (who, esc(team.get("module") or "modulo abituale"), len(based))
             if same else "%s riparte dal %s dell'ultima gara (contro %s)" % (who, esc(team.get("module") or "modulo abituale"), esc(based[0]["opponent"]) if based else "?"))
    parts = []
    for lst in rows:
        pos = lst[0].get("pos") or "M"
        parts.append(ROW_LABEL.get(pos, "") + " " + names(lst, plink, pctx))
    s = intro + ": " + "; ".join(parts) + ". "
    ballots = [x for x in team["xi"] if x.get("ballot")]
    if ballots:
        s += "Ballottagg" + ("io" if len(ballots) == 1 else "i") + ": " + "; ".join("%s-%s (%d%%-%d%%)" % (esc(x["name"]), esc(x["ballot"]["name"]), x.get("share") or 50, x["ballot"]["share"]) for x in ballots) + ". "
    forced = [x for x in team["xi"] if x.get("out_for")]
    if forced:
        s += "Al posto di " + ", ".join("%s entra %s" % (esc(x["out_for"]), esc(x["name"])) for x in forced) + ". "
    if team.get("out"):
        s += "Indisponibili: " + ", ".join(esc(o["name"]) + " (" + esc((o.get("reason") or "").split(" · ")[0]) + (", rientro " + esc(fdate_it(o["back_at"] + "T12:00:00Z")) if o.get("back_at") else "") + ")" for o in team["out"]) + ". "
    if team.get("doubt"):
        s += "In dubbio: " + ", ".join("%s (%d%%)" % (esc(o["name"]), o["prob"]) for o in team["doubt"]) + ". "
    if team.get("bench"):
        s += "Dalla panchina: " + ", ".join(esc(b["name"]) for b in team["bench"]) + "."
    return s

def team_pills(team):
    """Riga di pillole sotto il campo: ballottaggi (ambra) e indisponibili (rosso); vuota se non c'è nulla da segnalare."""
    out = ['<span class="pill warn">%s / %s</span>' % (esc(x["name"]), esc(x["ballot"]["name"])) for x in team["xi"] if x.get("ballot")]
    out += ['<span class="pill err">%s</span>' % esc(o["name"]) for o in team.get("out") or []]
    return ('<div class="pf-pills">' + "".join(out) + "</div>") if out else ""

def span_it(d_from, d_to):
    """'dall'11 al 14 settembre 2026' oppure 'dal 30 settembre al 2 ottobre 2026' (apostrofo davanti a 1, 8 e 11)."""
    a, b = fdate_it(d_from).split(" "), fdate_it(d_to).split(" ")   # ['11', 'settembre', '2026']
    def art(day, base):
        return base + ("l'" if day in ("1", "8", "11") else " ") + day
    if a[1:] == b[1:]:
        return "%s %s %s %s" % (art(a[0], "dal"), art(b[0], "al"), b[1], b[2])
    return "%s %s %s %s %s" % (art(a[0], "dal"), a[1], art(b[0], "al"), b[1], b[2])

def render(D, T, P, latest, helpers):
    """P = probabili-NN.json; latest=True -> URL fissa /fantacalcio/probabili-formazioni.html, altrimenti archivio per giornata."""
    md = P["matchday"]; upd = P.get("updated") or ""; fx = P["fixtures"]; teams = P["teams"]
    for n, t in teams.items():
        t.setdefault("name", n)
    plink, pctx, fanta_team_link, dataset_ld, crumb = helpers["plink"], helpers["pctx"], helpers["fanta_team_link"], helpers["dataset_ld"], helpers["crumb"]
    rel = "fantacalcio/probabili-formazioni.html" if latest else "fantacalcio/probabili-giornata-%d.html" % md
    canon = SITE + "/" + rel; fn = "probabili-%02d.json" % md
    dates = sorted(f["date"] for f in fx)
    n_out = sum(len(t.get("out") or []) for t in teams.values()); n_bal = sum(1 for t in teams.values() for x in t["xi"] if x.get("ballot"))
    n_forced = sum(1 for t in teams.values() for x in t["xi"] if x.get("out_for"))
    stage = {"settimana": "Prima stima della settimana", "vigilia": "Vigilia della giornata", "giorno-gara": "Giorno di gara"}.get(P.get("stage"), "Stima")
    others = helpers.get("others") or []
    def colors(name):
        site = T.fanta_name(name); t = T.by_name.get(site) if site else None
        return ((t.get("col") or "#67727e"), (t.get("col2") or "#ffffff")) if t else ("#67727e", "#ffffff")
    def url_of(k):
        return "/fantacalcio/probabili-formazioni.html" if (others and k == others[-1]) else "/fantacalcio/probabili-giornata-%d.html" % k
    b = ["<h1>Probabili formazioni giornata %d Serie A %s: moduli, titolari e percentuali</h1>" % (md, SEASON),
         # prima frase citabile: numero + oggetto + data (span_it produce solo cifre, mesi e apostrofo: niente escape, così l'apostrofo resta vero)
         '<p class="sub">%d partite %s, %d indisponibili, %d ballottaggi e %d sostituzioni forzate. %s, aggiornata il <time datetime="%s">%s</time>.</p>' % (
             len(fx), span_it(dates[0], dates[-1]), n_out, n_bal, n_forced, esc(stage), esc(upd), esc(fdate_it(upd, True)))]
    # chip delle giornate: l'ultima ha la URL fissa, le altre l'archivio; la giornata corrente è la chip attiva
    if others:
        chips = "".join(('<a class="on" href="%s" aria-current="page">Giornata %d</a>' % (url_of(k), k)) if k == md else ('<a href="%s">Giornata %d</a>' % (url_of(k), k)) for k in others)
        if md == others[-1]:
            chips += '<span class="pf-hint">La giornata %d arriva dopo il turno.</span>' % (md + 1)
        b.append('<nav class="chips" aria-label="Giornate">' + chips + "</nav>")
    # indice delle partite in griglia (5 colonne, 2 sotto 760px, 1 sotto 480px), ogni card porta all'ancora della partita
    idx = []
    for f in fx:
        anchor = "partita-%s-%s" % (team_slug(T, f["home"]), team_slug(T, f["away"]))
        idx.append('<a href="#%s"><span class="t">%s<span class="n">%s</span><span class="vs">-</span><span class="n">%s</span>%s</span><span class="d">%s</span></a>' % (
            anchor, team_badge(T, f["home"]), esc(short_name(T, f["home"])), esc(short_name(T, f["away"])), team_badge(T, f["away"]), esc(fdate_it(f["date"], True, True))))
    b.append('<div class="pf-idx" id="partite">' + "".join(idx) + "</div>")
    b.append('<p>Le probabili formazioni della giornata %d di Serie A %s partita per partita, costruite da TransferBeat con i propri dati: per ogni squadra il modulo e l\'undici '
             'dell\'ultima formazione ufficiale, la percentuale di ogni giocatore di partire titolare calcolata sulle ultime tre gare e sull\'indice di titolarità FantaTB, '
             'infortunati e squalificati con la data di rientro, e i sostituti più probabili nella stessa posizione. Il campo mostra i titolari nei loro ruoli; sotto ogni partita il dettaglio in testo con panchina e ballottaggi.</p>' % (md, SEASON))
    for f in fx:
        h, a = teams.get(f["home"]), teams.get(f["away"])
        hc, ac = colors(f["home"]), colors(f["away"])
        anchor = "partita-%s-%s" % (team_slug(T, f["home"]), team_slug(T, f["away"]))
        b.append('<section class="card pf-match" id="%s"><div class="pf-head"><h2>%s - %s</h2><span class="d"><time datetime="%s">%s</time>%s</span></div>' % (
            anchor, fanta_team_link(T, f["home"]), fanta_team_link(T, f["away"]), esc(f["date"]), esc(fdate_it(f["date"], True)), (" · " + esc(f["venue"])) if f.get("venue") else ""))
        b.append('<div class="pf-halves">')
        for name, team, col, mirror in ((f["home"], h, hc, False), (f["away"], a, ac, True)):
            sid = "squadra-" + team_slug(T, name)
            if not team:
                b.append('<div class="pf-half" id="%s"><p class="small">%s: probabile non disponibile, nessuna formazione ufficiale recente.</p></div>' % (sid, esc(name))); continue
            b.append('<div class="pf-half" id="%s">' % sid + half_svg(team, col[0], col[1], mirror) +
                     '<div class="pf-meta"><b>%s</b> · %s%s · basato su %s</div>' % (esc(team["name"]), esc(team.get("module") or "modulo non noto"), (" · all. " + esc(team["coach"])) if team.get("coach") else "",
                                                                                     ", ".join(esc(x["opponent"]) + " (" + esc(x.get("formation") or "?") + ")" for x in team.get("based_on") or []) or "nessuna gara recente") +
                     team_pills(team) + "</div>")
        b.append("</div>")
        b.append('<div class="pf-txt">' + "".join("<p>" + team_text(t, T, plink, pctx, fanta_team_link) + "</p>" for t in (h, a) if t) + "</div></section>")
    # riepilogo indisponibili della giornata
    outs = [(n, o) for n, t in sorted(teams.items()) for o in (t.get("out") or [])]
    if outs:
        b.append("<h2>Indisponibili e squalificati della giornata %d</h2><ul class=\"pf-list\">" % md + "".join(
            "<li><b>%s</b> (%s) · %s%s</li>" % (plink(pctx, o["id"], o["name"]), fanta_team_link(T, n), esc((o.get("reason") or "").split(" · ")[0]), (" · rientro " + esc(fdate_it(o["back_at"] + "T12:00:00Z"))) if o.get("back_at") else "") for n, o in outs) + "</ul>")
    bal = [(n, x) for n, t in sorted(teams.items()) for x in t["xi"] if x.get("ballot")]
    if bal:
        b.append("<h2>I ballottaggi da seguire</h2><ul class=\"pf-list\">" + "".join(
            "<li><b>%s</b>: %s %d%% contro %s %d%%</li>" % (fanta_team_link(T, n), plink(pctx, x["id"], x["name"]), x.get("share") or 50, plink(pctx, x["ballot"]["id"], x["ballot"]["name"]), x["ballot"]["share"]) for n, x in bal) + "</ul>")
    faq = [("Come sono calcolate le probabili formazioni?", "Dalle ultime tre formazioni ufficiali di ogni squadra (modulo e posizioni) e dall'indice di titolarità FantaTB: chi è partito titolare di recente ha una percentuale alta, gli infortunati e gli squalificati sono a zero e vengono sostituiti dal giocatore più probabile nella stessa posizione. Non usiamo le probabili di altri siti."),
           ("Quando vengono aggiornate?", "Più volte a settimana: prima stima dopo l'ultima giornata, poi giovedì, venerdì e la mattina del giorno di gara, quando si aggiornano infortuni e squalifiche."),
           ("Cosa significa la percentuale?", "La probabilità stimata che il giocatore parta titolare. Nei ballottaggi la quota è ripartita fra i due contendenti."),
           ("Posso riutilizzare i dati?", "Sì, il file JSON della giornata è pubblicato con licenza CC BY 4.0: basta citare TransferBeat con un link.")]
    b.append('<h2>Domande frequenti</h2><div class="faq">' + "".join("<details><summary>%s</summary><p>%s</p></details>" % (esc(q), esc(a)) for q, a in faq) + "</div>")
    # legenda in fondo, come nel mockup
    b.append('<div class="note"><b>Come leggere.</b> La percentuale è la probabilità che il giocatore parta titolare: verde da 70 in su, ambra fra 40 e 69, rossa sotto 40. '
             'Cerchio tratteggiato = ballottaggio, con la quota dei due contendenti. "Al posto di" segnala chi prende il posto di un indisponibile o di uno squalificato. '
             'Sono probabili statistiche di TransferBeat, non formazioni ufficiali: vengono ricalcolate più volte a settimana fino al giorno di gara.</div>')
    # link contestuali della stessa giornata: indisponibili, voti della giornata precedente (se esiste), listone, dati aperti e archivio
    links = ['<a href="/fantacalcio/titolari.html">infortunati e squalificati</a>']
    if (md - 1) in (D.get("voti") or {}):
        links.append('<a href="/fantacalcio/voti-giornata-%d.html">voti della giornata %d</a>' % (md - 1, md - 1))
    links += ['<a href="/fantacalcio/listone.html">listone</a>', '<a href="/fantacalcio/">tutti i dati del fantacalcio</a>', '<a href="/data/fanta/%s">%s</a>' % (fn, fn)]
    if others:
        links.append("altre giornate: " + " · ".join(('<a href="%s">giornata %d</a>' % (url_of(k), k)) if k != md else "<b>giornata %d</b>" % k for k in others))
    b.append('<p class="small">' + " · ".join(links) + "</p>")
    # ritorno all'indice delle partite, visibile solo su mobile (senza JS)
    b.append('<a class="btn small sec pf-top" href="#partite">Indice partite</a>')
    ld = [dataset_ld("Probabili formazioni TransferBeat, Serie A %s giornata %d" % (SEASON, md),
                     "Modulo, undici titolari con probabilità, ballottaggi, indisponibili e squalificati per le %d partite della giornata %d di Serie A." % (len(fx), md),
                     canon, SITE + "/data/fanta/" + fn, upd, ["probabili formazioni", "fantacalcio", "Serie A giornata %d" % md, "titolari"]),
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]
    return page("Probabili formazioni giornata %d Serie A %s" % (md, SEASON),
                "Probabili formazioni della giornata %d di Serie A %s partita per partita: moduli, undici titolari con la percentuale di ogni giocatore, ballottaggi, infortunati e squalificati." % (md, SEASON),
                canon, "".join(b), crumbs=crumb + [("Probabili formazioni giornata %d" % md, canon)], ld=ld, here="Fantacalcio",
                bar=FANTA_BAR, bar_here="Probabili formazioni", extra_head="<style>" + PITCH_CSS + "</style>")
