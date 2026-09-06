# -*- coding: utf-8 -*-
"""Pagina delle probabili formazioni (fantacalcio/probabili-formazioni.html e archivio probabili-giornata-N.html) da data/fanta/probabili-NN.json.
Importato da render_site.py (kb/FANTATB.md §20). Due mezzi campi per partita in SVG inline, percentuali, ballottaggi, indisponibili,
testo leggibile generato dai dati per ogni partita e per la giornata."""
import re
from site_common import esc, page, fdate_it, SITE, SEASON

ROW_LABEL = {"G": "in porta", "D": "in difesa", "M": "a centrocampo", "F": "in attacco"}
PITCH_CSS = """
.pf-match{border:1px solid var(--line);border-radius:12px;margin:18px 0;background:#fff;overflow:hidden}
.pf-head{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 14px;background:var(--panel);border-bottom:1px solid var(--line);font-size:14px}
.pf-head b{font-size:16px}.pf-head .d{color:var(--muted);font-size:12px}
.pf-halves{display:grid;grid-template-columns:1fr 1fr;gap:0}@media(max-width:700px){.pf-halves{grid-template-columns:1fr}}
.pf-half{padding:10px 12px 4px}.pf-half svg{width:100%;height:auto;display:block;border-radius:8px}
.pf-meta{font-size:12px;color:var(--muted);padding:6px 2px 8px;line-height:1.5}.pf-meta b{color:var(--txt)}
.pf-txt{padding:4px 14px 12px;font-size:14px}.pf-txt p{margin-bottom:8px}
.pct.g{color:var(--done)}.pct.a{color:#b8860b}.pct.r{color:var(--red)}
.pf-list{columns:2;column-gap:24px;font-size:13px;list-style:none;padding:0 14px 10px}.pf-list li{break-inside:avoid;padding:2px 0}@media(max-width:600px){.pf-list{columns:1}}
.note{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px;font-size:13px;margin:12px 0}
"""

def pct_cls(v):
    return "g" if v >= 70 else ("a" if v >= 40 else "r")

def half_svg(team, col, col2, mirror, plink, pctx):
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
         '<rect width="%d" height="%d" fill="#2f8f5b"/>' % (W, H)]
    for i in range(6):   # strisce d'erba
        g.append('<rect x="%d" y="0" width="60" height="%d" fill="#33985f" opacity="%s"/>' % (i * 60, H, "0.55" if i % 2 else "0"))
    def X(v):
        return W - v if mirror else v
    # linee: bordo, area, dischetto, metà campo con semicerchio
    g.append('<rect x="2" y="4" width="356" height="232" fill="none" stroke="#fff" stroke-width="2"/>')
    ax = 2 if not mirror else W - 2 - 66
    g.append('<rect x="%d" y="%d" width="66" height="132" fill="none" stroke="#fff" stroke-width="2"/>' % (ax, (H - 132) // 2))
    gx = 2 if not mirror else W - 2 - 24
    g.append('<rect x="%d" y="%d" width="24" height="60" fill="none" stroke="#fff" stroke-width="2"/>' % (gx, (H - 60) // 2))
    g.append('<circle cx="%d" cy="%d" r="2.5" fill="#fff"/>' % (X(46), H // 2))
    mx = W - 2 if not mirror else 2
    g.append('<line x1="%d" y1="4" x2="%d" y2="%d" stroke="#fff" stroke-width="2"/>' % (mx, mx, H - 4))
    g.append('<path d="M %d %d A 44 44 0 0 %d %d %d" fill="none" stroke="#fff" stroke-width="2"/>' % (mx, H // 2 - 44, 0 if not mirror else 1, mx, H // 2 + 44))
    xs = [30 + (r - 1) * (275 / max(R - 1, 1)) for r in range(1, R + 1)]
    for r in sorted(rows):
        lst = sorted(rows[r], key=lambda t: t[0])
        n = len(lst)
        for i, (c, x) in enumerate(lst):
            cx = X(xs[r - 1]); cy = 26 + (i + 0.5) * (188 / n)
            b = x.get("ballot")
            name = x["name"] if len(x["name"]) <= 14 else x["name"].split()[-1]
            g.append('<g><circle cx="%.1f" cy="%.1f" r="12" fill="%s" stroke="%s" stroke-width="2.5"%s/>' % (cx, cy, col, col2, ' stroke-dasharray="3 2"' if b else ""))
            if x.get("role"):
                g.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="9" font-weight="700" fill="#fff" font-family="Segoe UI,system-ui,sans-serif">%s</text>' % (cx, cy + 3.3, esc(x["role"])))
            g.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="10.5" font-weight="700" fill="#fff" stroke="#123" stroke-width="2.5" paint-order="stroke" font-family="Segoe UI,system-ui,sans-serif">%s</text>' % (cx, cy + 25, esc(name)))
            if b:
                share = x.get("share") or 50
                g.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="9" font-weight="700" fill="#ffe08a" stroke="#123" stroke-width="2" paint-order="stroke" font-family="Segoe UI,system-ui,sans-serif">%d%% · %s %d%%</text>' % (cx, cy + 36, share, esc(b["name"] if len(b["name"]) <= 12 else b["name"].split()[-1]), b["share"]))
            else:
                g.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="9.5" font-weight="700" fill="%s" stroke="#123" stroke-width="2" paint-order="stroke" font-family="Segoe UI,system-ui,sans-serif">%d%%</text>' % (cx, cy + 36, "#9ff2b8" if x["prob"] >= 70 else ("#ffe08a" if x["prob"] >= 40 else "#ffb3a7"), x["prob"]))
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
    intro = ("%s%s dovrebbe confermare il %s delle ultime %d uscite" % (fanta_team_link(T, team["name"]), coach, esc(team.get("module") or "modulo abituale"), len(based))
             if same else "%s%s riparte dal %s dell'ultima gara (contro %s)" % (fanta_team_link(T, team["name"]), coach, esc(team.get("module") or "modulo abituale"), esc(based[0]["opponent"]) if based else "?"))
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

def render(D, T, P, latest, helpers):
    """P = probabili-NN.json; latest=True -> URL fissa /fantacalcio/probabili-formazioni.html, altrimenti archivio per giornata."""
    md = P["matchday"]; upd = P.get("updated") or ""; fx = P["fixtures"]; teams = P["teams"]
    for n, t in teams.items():
        t.setdefault("name", n)
    plink, pctx, fanta_team_link, dataset_ld, crumb = helpers["plink"], helpers["pctx"], helpers["fanta_team_link"], helpers["dataset_ld"], helpers["crumb"]
    rel = "fantacalcio/probabili-formazioni.html" if latest else "fantacalcio/probabili-giornata-%d.html" % md
    canon = SITE + "/" + rel; fn = "probabili-%02d.json" % md
    dates = sorted(f["date"] for f in fx)
    d1, d2 = fdate_it(dates[0]), fdate_it(dates[-1])
    n_out = sum(len(t.get("out") or []) for t in teams.values()); n_bal = sum(1 for t in teams.values() for x in t["xi"] if x.get("ballot"))
    n_forced = sum(1 for t in teams.values() for x in t["xi"] if x.get("out_for"))
    stage = {"settimana": "prima stima della settimana", "vigilia": "vigilia della giornata", "giorno-gara": "giorno di gara"}.get(P.get("stage"), "")
    def colors(name):
        site = T.fanta_name(name); t = T.by_name.get(site) if site else None
        return ((t.get("col") or "#67727e"), (t.get("col2") or "#ffffff")) if t else ("#67727e", "#ffffff")
    b = ["<h1>Probabili formazioni giornata %d Serie A %s: moduli, titolari e percentuali</h1>" % (md, SEASON),
         '<div class="sub">%d partite da %s a %s · %d indisponibili, %d ballottaggi, %d sostituzioni forzate · %s · aggiornato <time>%s</time></div>' % (len(fx), esc(d1), esc(d2), n_out, n_bal, n_forced, esc(stage), esc(fdate_it(upd, True))),
         '<p>Le probabili formazioni della giornata %d di Serie A %s partita per partita, costruite da TransferBeat con i propri dati: per ogni squadra il modulo e l\'undici '
         'dell\'ultima formazione ufficiale, la percentuale di ogni giocatore di partire titolare calcolata sulle ultime tre gare e sull\'indice di titolarità FantaTB, '
         'infortunati e squalificati con la data di rientro, e i sostituti più probabili nella stessa posizione. Il campo mostra i titolari nei loro ruoli; sotto ogni partita il dettaglio in testo con panchina e ballottaggi.</p>' % (md, SEASON),
         '<div class="note"><b>Come leggere.</b> La percentuale è la probabilità che il giocatore parta titolare: verde da 70 in su, ambra fra 40 e 69, rossa sotto 40. '
         'Cerchio tratteggiato = ballottaggio, con la quota dei due contendenti. "Al posto di" segnala chi prende il posto di un indisponibile o di uno squalificato. '
         'Sono probabili statistiche di TransferBeat, non formazioni ufficiali: vengono ricalcolate più volte a settimana fino al giorno di gara.</div>']
    for f in fx:
        h, a = teams.get(f["home"]), teams.get(f["away"])
        hc, ac = colors(f["home"]), colors(f["away"])
        anchor = re.sub(r"[^a-z0-9]+", "-", (f["home"] + "-" + f["away"]).lower()).strip("-")
        b.append('<div class="pf-match" id="%s"><div class="pf-head"><b>%s - %s</b><span class="d">%s%s</span></div>' % (
            anchor, fanta_team_link(T, f["home"]), fanta_team_link(T, f["away"]), esc(fdate_it(f["date"], True)), (" · " + esc(f["venue"])) if f.get("venue") else ""))
        b.append('<div class="pf-halves">')
        for team, col, mirror in ((h, hc, False), (a, ac, True)):
            if not team:
                b.append('<div class="pf-half"><p class="small">Probabile non disponibile: nessuna formazione ufficiale recente.</p></div>'); continue
            b.append('<div class="pf-half">' + half_svg(team, col[0], col[1], mirror, plink, pctx) +
                     '<div class="pf-meta"><b>%s</b> · %s%s · basato su: %s</div></div>' % (esc(team["name"]), esc(team.get("module") or "?"), (" · all. " + esc(team["coach"])) if team.get("coach") else "",
                                                                                          ", ".join(esc(x["opponent"]) + " (" + esc(x.get("formation") or "?") + ")" for x in team.get("based_on") or [])))
        b.append("</div>")
        b.append('<div class="pf-txt">' + "".join("<p>" + team_text(t, T, plink, pctx, fanta_team_link) + "</p>" for t in (h, a) if t) + "</div></div>")
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
    others = helpers.get("others") or []
    links = ['<a href="/fantacalcio/titolari.html">indice di titolarità</a>', '<a href="/fantacalcio/">tutti i dati del fantacalcio</a>', '<a href="/data/fanta/%s">%s</a>' % (fn, fn)]
    if others:
        links.insert(0, "altre giornate: " + " · ".join(('<a href="/fantacalcio/probabili-giornata-%d.html">giornata %d</a>' % (k, k)) if k != md else "<b>giornata %d</b>" % k for k in others))
    b.append('<p class="small">' + " · ".join(links) + "</p>")
    ld = [dataset_ld("Probabili formazioni TransferBeat, Serie A %s giornata %d" % (SEASON, md),
                     "Modulo, undici titolari con probabilità, ballottaggi, indisponibili e squalificati per le %d partite della giornata %d di Serie A." % (len(fx), md),
                     canon, SITE + "/data/fanta/" + fn, upd, ["probabili formazioni", "fantacalcio", "Serie A giornata %d" % md, "titolari"]),
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]
    return page("Probabili formazioni giornata %d Serie A %s" % (md, SEASON),
                "Probabili formazioni della giornata %d di Serie A %s partita per partita: moduli, undici titolari con la percentuale di ogni giocatore, ballottaggi, infortunati e squalificati." % (md, SEASON),
                canon, "".join(b), crumbs=crumb + [("Probabili formazioni giornata %d" % md, canon)], ld=ld, here="FantaTB", extra_head="<style>" + PITCH_CSS + "</style>")
