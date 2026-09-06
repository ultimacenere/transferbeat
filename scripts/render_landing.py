#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - render_landing.py: la landing /fantatb.html, unica pagina indicizzabile che spiega e promuove FantaTB
(il fantacalcio gratuito di TransferBeat). Direzione visiva C (mockup Landing.dc.html), guscio di site_common.page().
Contratto: render(D, T) -> HTML completo. D = render_site.load_all() (con D["pctx"] se render_site l'ha già costruito),
T = render_site.Teams(D). Tutto il testo è nell'HTML statico; i numeri (giocatori quotati, giornate con voti, migliori fantavoti,
indisponibili) vengono dai JSON al momento del render. Nessuna emoji: icone SVG inline. Il gradiente firma compare una sola volta (hero).
Uso da render_site: import render_landing; save_text(ROOT/fantatb.html, render_landing.render(D, T))."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_common import SITE, SEASON, ORG, esc, fdate_it, page, door

CANON = SITE + "/fantatb.html"
CRUMBS = [("Home", SITE + "/"), ("Fantacalcio", SITE + "/fantacalcio/"), ("Gioca a FantaTB", CANON)]
RUOLI = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}

# Icone SVG inline (28px, stroke 2) nel colore --violet: niente emoji nel markup nuovo.
def _icon(paths, size=28):
    return ('<svg width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true">%s</svg>' % (size, size, paths))

ICONS = {
    "clock": _icon('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    "rules": _icon('<path d="M4 6h16M4 12h10M4 18h6"/>'),
    "grid": _icon('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/>'),
    "gavel": _icon('<path d="M14 4l6 6M4 20l7-7M9 9l6 6M12 6l6 6"/>'),
    "sheet": _icon('<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h8"/>'),
    "list": _icon('<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1.5"/><circle cx="4.5" cy="12" r="1.5"/><circle cx="4.5" cy="18" r="1.5"/>'),
    "pitch": _icon('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16M3 12h18"/><circle cx="12" cy="12" r="3"/>'),
    "chart": _icon('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
    "chat": _icon('<path d="M21 12a8 8 0 0 1-8 8H8l-5 3 1.5-4.5A8 8 0 1 1 21 12z"/>'),
    "trophy": _icon('<path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8 21h8M10 17h4"/>'),
    "stack": _icon('<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>'),
    "shield": _icon('<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>'),
}

# CSS proprio della landing (prefisso lp-): sopra i token e le classi condivise di site_common.CSS.
LANDING_CSS = """<style>
.lp-hero{background:var(--grad);color:#fff;border-radius:16px;padding:40px 32px;display:grid;grid-template-columns:1.1fr .9fr;gap:32px;align-items:center;margin:4px 0 24px}
.lp-hero .k{font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;opacity:.9;margin:0 0 12px}
.lp-hero h1{color:#fff;font-size:36px;margin:0 0 12px}
.lp-hero .lead{color:#fff;font-size:18px;line-height:1.5;margin:0 0 16px;opacity:.95}
.lp-hero .acts{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:0 0 8px}
.lp-hero .btn{background:#fff;color:var(--ink);margin:0}.lp-hero .btn:hover{background:#f3eefb;color:var(--ink)}
.lp-hero .btn.line{background:transparent;color:#fff;border:2px solid rgba(255,255,255,.8)}.lp-hero .btn.line:hover{background:rgba(255,255,255,.12);color:#fff}
.lp-hero .fine{font-size:13px;opacity:.85;margin:0}
.lp-proof{background:#fff;color:var(--txt);border-radius:16px;padding:16px 18px;box-shadow:0 24px 60px rgba(27,17,64,.35)}
.lp-proof .h{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:0 0 8px;font-size:16px;font-weight:700}
.lp-proof table{font-size:13px}.lp-proof td,.lp-proof th{padding:7px 8px}.lp-proof td.n{font-weight:600}.lp-proof td.fv{font-weight:700}
.lp-proof .f{display:flex;justify-content:space-between;align-items:center;gap:8px;background:var(--panel);border-radius:8px;padding:8px 12px;font-size:13px;margin:10px 0 0}
.lp-proof .f a{font-weight:600}
.lp-why{margin:0 0 8px}.lp-why .card{padding:18px 20px;margin:0}.lp-why .card svg{color:var(--violet);margin-bottom:8px}
.lp-why .card h2{font-size:18px;font-weight:600;padding:0;border:0;margin:0 0 6px}.lp-why .card p{font-size:14px;color:var(--txt2);margin:0}
.lp-steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:0 0 8px}
.lp-step{display:flex;gap:12px;align-items:flex-start}.lp-step .n{width:32px;height:32px;border-radius:50%;background:var(--brand);color:var(--ink);font-weight:700;display:inline-grid;place-items:center;flex:none}
.lp-step h3{margin:4px 0 4px;font-size:16px}.lp-step p{font-size:13px;color:var(--txt2);margin:0}
.lp-feat{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:0 0 8px}
.lp-feat .card{padding:16px 18px;margin:0;display:flex;gap:12px;align-items:flex-start}.lp-feat .card svg{color:var(--violet);flex:none;width:24px;height:24px}
.lp-feat h3{margin:0 0 4px;font-size:16px}.lp-feat p{font-size:13px;color:var(--txt2);margin:0}
.lp-rules{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:0 0 8px}.lp-rules .card{margin:0}
.lp-rules ul{margin:0;padding-left:18px;font-size:14px;color:var(--txt2)}.lp-rules li{margin:0 0 6px}
.lp-doors{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0 0 8px}.lp-doors .door{margin:0}
.lp-final{background:var(--ink);color:#fff;border-radius:16px;padding:24px 28px;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin:32px 0 0}
.lp-final h2{color:#fff;margin:0 0 4px;font-size:22px}.lp-final p{margin:0;opacity:.9;font-size:14px}.lp-final .btn{margin:0}
@media(max-width:760px){.lp-hero{grid-template-columns:1fr;padding:20px 16px;border-radius:12px}.lp-hero h1{font-size:28px}.lp-hero .lead{font-size:16px}
.lp-steps,.lp-feat,.lp-rules,.lp-doors{grid-template-columns:1fr}.lp-final{padding:20px 16px}}
</style>"""

FAQ = [
    ("Quanto costa FantaTB?", "Niente. FantaTB è gratuito, senza abbonamenti, senza funzioni a pagamento e senza limiti al numero di leghe: è un servizio di TransferBeat."),
    ("Serve installare un'app?", "No: funziona dal browser del telefono e del computer, bastano un'email e una password. Dal telefono si può aggiungere alla schermata iniziale."),
    ("Da dove vengono i voti?", "Dal voto statistico FantaTB, calcolato dalle prestazioni reali in campo: rating della partita meno 0,8, arrotondato al mezzo punto fra 4 e 8,5, senza voto sotto i 15 minuti. Bonus e malus hanno pesi pubblici e l'admin di lega può correggere qualsiasi voto. Non sono i voti dei quotidiani."),
    ("Cosa vuol dire voti in diretta e 6 politico?", "Nei giorni di gara i voti si aggiornano ogni 30 minuti e la giornata di lega viene ricalcolata a partite in corso. Chi deve ancora giocare vale un 6 politico provvisorio, senza bonus: il risultato live è una simulazione completa, che diventa definitiva a giornata chiusa."),
    ("Posso usare le regole della mia lega?", "Sì. Crediti, numero di squadre, slot per ruolo, panchina, sostituzioni, soglia e passo dei gol, fattore casa e trasferta, bonus e malus con i pesi, modificatore di difesa a tabella (con o senza portiere, alla propria squadra o all'avversaria), modificatori di centrocampo e attacco: si impostano alla creazione e si cambiano dalla scheda Regole."),
    ("Come funziona l'asta live?", "L'admin fa da banditore: cerca il giocatore, fissa la base e apre l'asta; tutti rilanciano dal proprio telefono (+1, +5, +10 o un importo) e il timer riparte a ogni offerta. Crediti e slot liberi vengono controllati in automatico. Se l'asta l'avete già fatta altrove, le rose si importano da Excel o CSV."),
    ("Quante squadre può avere una lega?", "Il numero di squadre lo decide l'admin alla creazione (8 per impostazione predefinita) e il calendario di lega si genera con un clic a partire da una giornata di Serie A."),
    ("FantaTB è affiliato a Fantacalcio®?", "No. FantaTB è un progetto indipendente di TransferBeat e non è affiliato a Fantacalcio® né ai quotidiani; i voti sono statistici e la formula è pubblica."),
]

def _dec(x):
    """Numero con la virgola italiana (7.5 -> 7,5)."""
    if isinstance(x, (int, float)):
        return ("%g" % x).replace(".", ",")
    return str(x)

def _dec1(x):
    """Fantavoto con un decimale (14 -> 14,0), come nelle pagine voti."""
    return ("%.1f" % x).replace(".", ",") if isinstance(x, (int, float)) else str(x)

def _team_link(T, team):
    n = T.fanta_name(team or "")
    return ('<a href="' + T.url(n) + '">' + esc(team) + "</a>") if n else esc(team)

def _player_link(D, pid, fallback):
    """Nome del giocatore con link alla scheda (giocatori/<slug>.html) se render_site ha costruito D["pctx"]."""
    ctx = D.get("pctx") or {}
    u = (ctx.get("urls") or {}).get(pid)
    name = fallback
    p = (ctx.get("P") or {}).get(str(pid))
    if p:
        try:
            import render_stats
            name = render_stats.full_name(p) or fallback
        except Exception:
            name = fallback
    return ('<a href="' + esc(u) + '">' + esc(name) + "</a>") if u else esc(name)

def _bonus_txt(b):
    lab = {"gol": "gol", "assist": "assist", "rig_parato": "rig. parato", "rig_sbagliato": "rig. sbagliato", "gol_subito": "gol subiti",
           "autogol": "autogol", "amm": "amm.", "esp": "esp."}
    out = []
    for k, v in (b or {}).items():
        if v:
            out.append((str(v) + " " if v != 1 else "") + lab.get(k, k))
    return ", ".join(out)

def top_fantavoti(D, n=4):
    """(giornata, dati giornata, [(rating, giocatore del listone)]) dei migliori fantavoti dell'ultima giornata con voti."""
    if not D.get("voti"):
        return None, None, []
    md = max(D["voti"])
    V = D["voti"][md]
    listone = {p["id"]: p for p in (D.get("listone") or {}).get("players") or []}
    rows = [r for r in V.get("ratings") or [] if r.get("fantavoto") is not None and r["player_id"] in listone]
    rows.sort(key=lambda r: (-r["fantavoto"], -(r.get("voto") or 0), listone[r["player_id"]]["name"]))
    return md, V, [(r, listone[r["player_id"]]) for r in rows[:n]]

def proof_card(D, T):
    """Card bianca del hero: i migliori fantavoti dell'ultima giornata, dati pubblici (mai leghe private o nomi di utenti)."""
    md, V, top = top_fantavoti(D)
    if not top:
        n = len((D.get("listone") or {}).get("players") or [])
        return ('<div class="lp-proof"><div class="h"><span>Listone ' + esc(SEASON) + '</span><span class="pill info">' + str(n) + ' giocatori</span></div>'
                '<p style="margin:0;font-size:14px;color:var(--txt2)">I voti FantaTB arrivano dopo la prima giornata di Serie A: intanto il listone con le quotazioni è già pronto per l\'asta.</p>'
                '<div class="f"><a href="/fantacalcio/listone.html">Apri il listone</a></div></div>')
    live = (V.get("status") or "") != "rated"
    pill = ('<span class="pill warn">giornata ' + str(md) + ' live · ' + str(V.get("finished") or 0) + ' partite su ' + str(V.get("total") or 10) + '</span>') if live \
        else '<span class="pill ok">giornata ' + str(md) + ' completa</span>'
    rows = []
    for i, (r, p) in enumerate(top):
        rows.append('<tr><td class="num">' + str(i + 1) + '</td><td><i class="rb ' + esc(p.get("role")) + '">' + esc(p.get("role")) + '</i></td>'
                    '<td class="n">' + _player_link(D, p["id"], p["name"]) + '<span class="small"> · ' + _team_link(T, p.get("team")) + '</span></td>'
                    '<td class="num">' + _dec(r.get("voto")) + '</td><td class="num fv">' + _dec1(r.get("fantavoto")) + '</td></tr>')
    first = top[0]
    fb = _bonus_txt(first[0].get("bonus"))
    return ('<div class="lp-proof"><div class="h"><span>Giornata ' + str(md) + ' · i migliori fantavoti</span>' + pill + '</div>'
            '<div class="tscroll"><table><thead><tr><th class="num">#</th><th>R</th><th>Giocatore</th><th class="num">Voto</th><th class="num">FV</th></tr></thead><tbody>' +
            "".join(rows) + '</tbody></table></div>'
            '<div class="f"><span><b>' + esc(first[1]["name"]) + '</b>' + ((": " + esc(fb)) if fb else "") + '</span>'
            '<a href="/fantacalcio/voti-giornata-' + str(md) + '.html">Tutti i voti</a></div></div>')

def kpis(D):
    n_players = len((D.get("listone") or {}).get("players") or [])
    n_md = len(D.get("voti") or {})
    md, V, _ = top_fantavoti(D, 1)
    n_rated = sum(1 for r in (V or {}).get("ratings") or [] if r.get("voto") is not None) if V else 0
    tit = D.get("titolari") or {}
    n_out = sum(1 for s in tit.get("status") or [] if s.get("injury") or (s.get("prob") == 0))
    out = ['<div class="kpis">',
           '<div class="kpi"><div class="l">Giocatori quotati</div><div class="v">' + str(n_players) + '</div><a href="/fantacalcio/listone.html">Apri il listone</a></div>',
           '<div class="kpi"><div class="l">Giornate con voti</div><div class="v">' + str(n_md) + '</div><a href="/fantacalcio/voti.html">Voti dell\'ultima giornata</a></div>']
    if V:
        out.append('<div class="kpi"><div class="l">Con voto nella giornata ' + str(md) + '</div><div class="v">' + str(n_rated) + '</div><div class="s">giocatori con almeno 15 minuti</div></div>')
    if tit.get("matchday"):
        out.append('<div class="kpi"><div class="l">Indisponibili giornata ' + str(tit["matchday"]) + '</div><div class="v">' + str(n_out) + '</div><a href="/fantacalcio/titolari.html">Infortunati e squalificati</a></div>')
    out.append("</div>")
    return "".join(out)

def render(D, T):
    """HTML completo di /fantatb.html."""
    n_players = len((D.get("listone") or {}).get("players") or [])
    n_md = len(D.get("voti") or {})
    md, V, _ = top_fantavoti(D, 1)
    upd = (V or {}).get("updated") or (D.get("listone") or {}).get("updated") or ""
    upd_txt = fdate_it(upd) if upd else ""
    # Prima frase citabile: numero + oggetto + data, tutto nell'HTML statico.
    lead = ("FantaTB quota " + str(n_players) + " giocatori di Serie A " + SEASON + " e ha pubblicato i voti di " + str(n_md) +
            (" giornata" if n_md == 1 else " giornate") + (", aggiornati al " + upd_txt if upd_txt else "") +
            ". Crea la lega, invita gli amici con un codice, schiera la formazione: i punteggi si calcolano da soli durante le partite, "
            "con bonus, modificatori e le regole della tua lega.")

    hero = ('<section class="lp-hero"><div><p class="k">FantaTB · il fantacalcio gratuito di TransferBeat</p>'
            '<h1>La tua lega di fantacalcio con i voti in diretta</h1>'
            '<p class="lead">' + esc(lead) + '</p>'
            '<div class="acts"><a class="btn" href="/fanta/#crea">Crea la tua lega</a><a class="btn line" href="/fanta/">Entra con un codice</a></div>'
            '<p class="fine">Nessuna carta di credito, nessuna app da scaricare: basta un\'email.</p></div>' + proof_card(D, T) + '</section>')

    why = ('<div class="grid3 lp-why">'
           '<div class="card">' + ICONS["clock"] + '<h2>Voti e bonus in diretta</h2><p>Nei giorni di gara i voti si aggiornano ogni 30 minuti e la giornata di lega viene ricalcolata a partite in corso. '
           'Chi deve ancora giocare vale un 6 politico provvisorio, così vedi subito come sta andando la sfida; a giornata chiusa il risultato diventa definitivo.</p></div>'
           '<div class="card">' + ICONS["rules"] + '<h2>Le regole della tua lega</h2><p>Modificatore di difesa a tabella (con o senza portiere, alla propria squadra o all\'avversaria), '
           'modificatori di centrocampo e attacco, fattore casa, bonus e malus con i tuoi pesi, soglia gol e panchina. Le imposti una volta e valgono per tutti.</p></div>'
           '<div class="card">' + ICONS["grid"] + '<h2>Probabili e listone integrati</h2><p>Dalla formazione passi alle probabili formazioni di TransferBeat con un clic: percentuale di titolarità, '
           'infortunati e squalificati accanto a ogni nome. Le quotazioni sono quelle del listone pubblico, con voto medio e fantamedia aggiornati.</p></div></div>')

    steps = ('<h2>Come funziona</h2><div class="lp-steps">'
             '<div class="lp-step"><span class="n">1</span><div><h3>Crea la lega</h3><p>Nome, numero di squadre, crediti e regole: ci vogliono due minuti e puoi cambiarle anche dopo, dalla scheda Regole.</p></div></div>'
             '<div class="lp-step"><span class="n">2</span><div><h3>Invita gli amici</h3><p>Condividi il codice invito. Ognuno entra con il proprio account, anche dal telefono, e prende la sua rosa dopo l\'asta live o dall\'importazione da Excel.</p></div></div>'
             '<div class="lp-step"><span class="n">3</span><div><h3>Schiera e guarda</h3><p>Formazione sul mezzo campo entro il fischio d\'inizio, poi i risultati arrivano da soli: partita per partita, con voti, bonus e modificatori, anche a giornata in corso.</p></div></div></div>')

    feats = [
        ("gavel", "Asta live dal telefono", "L'admin fa da banditore, tutti rilanciano in tempo reale (+1, +5, +10 o un importo) e il timer riparte a ogni offerta. Crediti e slot liberi per ruolo controllati in automatico."),
        ("sheet", "Importazione rose da Excel o CSV", "Asta già fatta altrove? Carichi il file con fantasquadra, giocatore e prezzo (anche l'export di altre piattaforme): i nomi vengono abbinati al listone e le squadre restano in attesa finché il loro manager entra col codice."),
        ("list", "Liste obiettivi con tier", "Cinque livelli, da Top a Da evitare, con note per giocatore. La lista attiva colora il listone e si può condividere con un link o copiare da quelle consigliate."),
        ("stack", "Strategie d'asta", "Budget per ruolo, inflazione stimata dei prezzi, tetto di spesa per ogni obiettivo e cruscotto in asta con speso e pianificato. Esportabili in Excel con il listone e la tua rosa."),
        ("pitch", "Formazione sul campo", "Sette moduli, mezzo campo con gli slot per ruolo, panchina ordinata, percentuale di titolarità e infortuni accanto ai nomi, scadenza chiara per ogni giornata."),
        ("chart", "Risultati partita per partita", "Le due formazioni allineate riga per riga con voto, fantavoto, bonus e sostituzioni dalla panchina; totali parziali, modificatori e classifica con punti e fantapunti."),
        ("trophy", "Calendario e classifica di lega", "Il calendario si genera con un clic a partire da una giornata di Serie A; a ogni turno la classifica aggiorna punti, gol fatti e subiti e fantapunti. Le giornate passate si ricalcolano se cambi le regole."),
        ("shield", "Voti statistici a formula pubblica", "Ogni voto nasce dai dati reali della partita con una formula dichiarata; bonus e malus sono visibili giocatore per giocatore e l'admin può correggere qualsiasi voto."),
        ("chat", "Assistenza dentro l'app", "Un pulsante Scrivici apre una chat con la redazione di TransferBeat: domande, segnalazioni e richieste sulle regole trovano risposta senza uscire dalla lega."),
    ]
    inside = ('<h2>Cosa trovi dentro</h2><div class="lp-feat">' + "".join(
        '<div class="card">' + ICONS[k] + '<div><h3>' + esc(t) + '</h3><p>' + esc(d) + '</p></div></div>' for k, t, d in feats) + "</div>")

    rules = ('<h2>Voti, bonus e modificatori</h2><div class="lp-rules">'
             '<div class="card"><h3>Come nasce il voto FantaTB</h3><div class="in"><ul>'
             '<li><b>Voto base</b>: rating statistico della partita meno 0,8, arrotondato al mezzo punto fra 4 e 8,5; senza voto sotto i 15 minuti.</li>'
             '<li><b>Bonus e malus predefiniti</b>: gol +3, assist +1, rigore sbagliato −3, rigore parato +3, gol subito −1 per i portieri, autogol −2, ammonizione −0,5, espulsione −1. Ogni lega può cambiare i pesi.</li>'
             '<li><b>6 politico</b>: nelle giornate in corso chi non ha ancora giocato vale 6 senza bonus, segnalato con un asterisco; a giornata chiusa entra il voto vero o il primo panchinaro dello stesso ruolo.</li>'
             '<li><b>Gol</b>: 1 gol a 66 fantapunti, poi 1 ogni 6 (soglia e passo modificabili); vittoria 3 punti, pareggio 1.</li></ul>'
             '<p class="small">I voti FantaTB sono statistici e non coincidono con quelli dei quotidiani. Formula completa nel <a href="/fantacalcio/regolamento.html">regolamento</a>.</p></div></div>'
             '<div class="card"><h3>I modificatori della lega</h3><div class="in"><ul>'
             '<li><b>Difesa</b>: media del portiere e dei tre migliori difensori (o dei quattro migliori senza portiere), con almeno quattro difensori schierati; tabella a soglie modificabile, dal +0,5 con media 6 al +7,5 con media 7,5. Il bonus va alla propria squadra o, se preferite, come malus all\'avversaria.</li>'
             '<li><b>Centrocampo</b>: differenza fra le medie voto dei centrocampisti delle due squadre, da +1 a +6 a chi ha la media più alta.</li>'
             '<li><b>Attacco</b>: media voto degli attaccanti schierati, da +1 a +6.</li>'
             '<li><b>Fattore casa e trasferta</b>, porta inviolata, sostituzioni dalla panchina (fino a 3) e panchina a 7: tutto nella scheda Regole della lega.</li></ul>'
             '<p class="small">Le voci dei modificatori attivi compaiono sempre nel dettaglio della partita, anche quando valgono 0.</p></div></div></div>')

    doors = ('<h2>I dati aperti che alimentano FantaTB</h2>'
             '<p class="sub" style="margin-bottom:12px">Listone, voti, probabili formazioni e indisponibili sono pubblicati come pagine e come file JSON con licenza CC BY 4.0: gli stessi dati che usa l\'app.</p>'
             '<div class="lp-doors">' +
             door("Probabili formazioni", "Moduli, titolari e percentuali partita per partita", "/fantacalcio/probabili-formazioni.html") +
             door("Voti e fantavoti", "Voto statistico, bonus e malus dopo ogni giornata", "/fantacalcio/voti.html") +
             door("Listone " + SEASON, str(n_players) + " giocatori quotati con ruolo e squadra", "/fantacalcio/listone.html") +
             door("Infortunati e squalificati", "Indice di titolarità e date di rientro stimate", "/fantacalcio/titolari.html") + "</div>")

    faq = ('<h2>Domande frequenti</h2><div class="faq">' + "".join(
        "<details><summary>" + esc(q) + "</summary><p>" + esc(a) + "</p></details>" for q, a in FAQ) + "</div>")

    final = ('<section class="lp-final"><div><h2>La tua lega parte adesso</h2><p>Crea la lega, manda il codice agli amici e fissate l\'asta. Il resto lo fa FantaTB.</p></div>'
             '<a class="btn" href="/fanta/#crea">Crea la tua lega</a></section>'
             '<p class="note">FantaTB è un servizio gratuito di TransferBeat. I voti sono statistici e non coincidono con quelli dei quotidiani. '
             'Non affiliato a Fantacalcio® né ad altre piattaforme. <a href="/fantacalcio/guida-asta.html">Guida all\'asta</a> · <a href="/fantacalcio/regolamento.html">Regolamento</a> · <a href="/chi-siamo.html">Chi siamo</a>.</p>')

    body = hero + kpis(D) + why + steps + inside + rules + doors + faq + final

    ld = [{"@context": "https://schema.org", "@type": "WebApplication", "name": "FantaTB", "url": SITE + "/fanta/",
           "applicationCategory": "GameApplication", "operatingSystem": "Web", "browserRequirements": "Requires JavaScript",
           "inLanguage": "it", "isAccessibleForFree": True,
           "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"}, "publisher": ORG,
           "description": "Fantacalcio gratuito con leghe private, asta live dal telefono, voti statistici in diretta, modificatori e regole su misura.",
           "featureList": [t for _, t, _ in feats],
           "mainEntityOfPage": CANON},
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
              {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ]}]

    title = "FantaTB: fantacalcio gratis con asta live e voti in diretta"
    desc = ("Crea la tua lega di fantacalcio gratis: asta live dal telefono, regole con modificatori, " + str(n_players) +
            " giocatori quotati e voti statistici in diretta ogni giornata.")
    return page(title, desc, CANON, body, crumbs=CRUMBS, ld=ld, here="Fantacalcio", extra_head=LANDING_CSS, promo=False, bar=None)

if __name__ == "__main__":
    # Prova manuale: scrive fantatb.html nella root del sito con i dati veri (nessuna rete).
    import render_site
    from site_common import ROOT, save_text
    D = render_site.load_all(); T = render_site.Teams(D)
    try:
        import render_stats
        D["pctx"] = render_stats.build_ctx(D, D["stats"], T)
    except Exception as e:
        print("render_landing: schede giocatore non disponibili (%s), nomi senza link" % e)
    save_text(os.path.join(ROOT, "fantatb.html"), render(D, T))
    print("render_landing OK")
