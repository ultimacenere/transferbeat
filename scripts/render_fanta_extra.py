#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - render_fanta_extra.py: tre pagine statiche del ramo fantacalcio (kb/SEO.md §0, kb/FANTATB.md §4-7).
- fantacalcio/regolamento.html : come funziona FantaTB, tabella bonus e malus, formula del voto statistico con esempio,
                                 modificatori, 6 politico, panchina e sostituzioni, FAQ (FAQPage).
- fantacalcio/guida-asta.html  : guida originale all'asta (budget per ruolo, ordine delle chiamate, ruolo per ruolo, rilanci,
                                 errori comuni, come usare i dati di TransferBeat) con HowTo e i piu' cari del listone al render.
- fantacalcio/consigli.html    : "Chi schierare nella giornata N" generata dai dati (probabili + fantamedia FantaTB), ItemList.
Contratto: render_all(D, T) -> [(rel_file, url, html), ...]; D = render_site.load_all(), T = render_site.Teams(D).
Nessuna rete: legge solo i dizionari gia' caricati. Tutti i numeri sono presi dai dati al momento del render."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_common import esc, SITE, SEASON, ORG, page, FANTA_BAR, FANTA_CRUMB, fdate_it, date_only, today_iso

try:
    import render_stats as RS   # link alle schede giocatore e riassunti (fantamedia, media voto)
except Exception:               # senza statistiche le pagine escono comunque, con i nomi in chiaro
    RS = None

# ---------- regole di default di FantaTB (kb/FANTATB.md §4 e fanta/supabase/fix-012-sei-politico.sql) ----------
CREDITS, MAX_TEAMS, TIMER, MAX_SUBS, BENCH, GOAL_BASE, GOAL_STEP = 500, 8, 20, 3, 7, 66, 6
SLOTS = [("P", "Portieri", 3), ("D", "Difensori", 8), ("C", "Centrocampisti", 8), ("A", "Attaccanti", 6)]
ROSA = sum(n for _, _, n in SLOTS)
RUOLO = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}
RUOLI_PL = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
# (voce, peso, a chi si applica, nota)
BONUS = [("Gol segnato", 3, "tutti", "su azione o su rigore; un gol di un difensore vale quanto uno di un attaccante"),
         ("Assist", 1, "tutti", "passaggio decisivo registrato nel tabellino"),
         ("Rigore parato", 3, "portieri", "il rigore parato non conta come gol subito"),
         ("Porta inviolata", 0, "portieri", "attivabile dall'admin: scatta con almeno 60 minuti giocati e zero gol subiti"),
         ("Gol subito", -1, "portieri", "per ogni gol incassato mentre era in campo"),
         ("Rigore sbagliato", -3, "tutti", "parato o fuori"),
         ("Autogol", -2, "tutti", "dagli eventi ufficiali della partita"),
         ("Ammonizione", -0.5, "tutti", "una sola per partita: la seconda diventa espulsione"),
         ("Espulsione", -1, "tutti", "rosso diretto o doppia ammonizione (in questo caso resta anche il -0,5 del primo giallo)")]
MOD_DEF = [(6, 0.5), (6.25, 1), (6.5, 2), (6.75, 3), (7, 4.5), (7.25, 6), (7.5, 7.5)]      # media portiere + 3 migliori difensori
MOD_ATT = [(6, 1), (6.25, 2), (6.5, 3), (6.75, 4), (7, 5), (7.25, 6)]                      # media voto degli attaccanti (>= 2)
MOD_MID = [(0.25, 1), (0.5, 2), (0.75, 3), (1, 4), (1.5, 5), (2, 6)]                       # differenza fra le medie dei centrocampi

# ---------- utilita' ----------
def dec(x, plus=False):
    """Numero in formato italiano: 6,5 · +0,5 · -1."""
    if x is None:
        return "—"
    s = ("%g" % x).replace(".", ",")
    return ("+" + s) if (plus and x > 0) else s

def voto_base(rating):
    """Voto FantaTB: rating - 0,8 arrotondato al mezzo punto, fra 4 e 8,5 (kb/FANTATB.md §5)."""
    return max(4.0, min(8.5, round((rating - 0.8) * 2) / 2))

def mod_lookup(avg, tab):
    v = 0
    for soglia, val in tab:
        if avg >= soglia:
            v = val
    return v

def gol_da_punti(punti):
    return 0 if punti < GOAL_BASE else 1 + int((punti - GOAL_BASE) // GOAL_STEP)

def rb(role):
    return '<i class="rb %s">%s</i>' % (esc(role), esc(role))

def _apos(day):
    """True se davanti al numero del giorno serve l'apostrofo: 1, 8, 11 (uno, otto, undici)."""
    return str(day).split(" ")[0] in ("1", "8", "11")

def dal(data):
    return ("dall'" if _apos(data) else "dal ") + data

def al(data):
    return ("all'" if _apos(data) else "al ") + data

def il(parola):
    """Articolo determinativo davanti a un nome di ruolo: l'attaccante, il portiere."""
    return ("l'" if parola[:1].lower() in "aeiou" else "il ") + parola

def periodo(d1, d2):
    """'dall'11 al 14 settembre 2026' se stesso mese, altrimenti le due date intere."""
    if not d1:
        return ""
    if d1 == d2 or not d2:
        return "il " + d1
    p1, p2 = d1.split(" ", 1), d2.split(" ", 1)
    if len(p1) == 2 and len(p2) == 2 and p1[1] == p2[1]:
        return dal(p1[0]) + " " + al(p2[0]) + " " + p2[1]
    return dal(d1) + " " + al(d2)

def pulisci_motivo(s):
    """Il feed scrive 'infortunio: infortunio' quando non conosce il tipo."""
    s = s or ""
    return "infortunio (tipo non indicato)" if s.strip().lower() == "infortunio: infortunio" else s

def plink(D, pid, name):
    if RS and D.get("pctx"):
        return RS.plink(D["pctx"], pid, name)
    return esc(name)

def team_link(T, team):
    n = T.fanta_name(team or "")
    return ('<a href="' + T.url(n) + '">' + esc(team) + "</a>") if n else esc(team)

def fm_from_voti(D):
    """Fantamedia e media voto per giocatore calcolate dai voti FantaTB (ripiego quando mancano le statistiche)."""
    acc = {}
    for md, V in (D.get("voti") or {}).items():
        for r in V.get("ratings") or []:
            if r.get("fantavoto") is None or r.get("voto") is None:
                continue
            a = acc.setdefault(r["player_id"], [0.0, 0.0, 0])
            a[0] += r["fantavoto"]; a[1] += r["voto"]; a[2] += 1
    return {pid: {"fmv": round(a[0] / a[2], 2), "mv": round(a[1] / a[2], 2), "n": a[2]} for pid, a in acc.items() if a[2]}

def summaries(D):
    """{player_id: {fmv, mv, n, url}} dalle schede se ci sono, altrimenti dai voti."""
    if RS and D.get("pctx"):
        out = {}
        for pid, s in (D["pctx"].get("summ") or {}).items():
            out[pid] = {"fmv": s.get("fmv"), "mv": s.get("mv"), "n": s.get("n") or 0, "url": s.get("url")}
        if out:
            return out
    return fm_from_voti(D)

def voti_stats(D):
    """Giornate con voti, righe con voto e con fantavoto: numeri veri per la prima frase del regolamento."""
    mds = sorted((D.get("voti") or {}).keys())
    n_voti = sum(1 for V in (D.get("voti") or {}).values() for r in V.get("ratings") or [] if r.get("voto") is not None)
    rated = [md for md in mds if (D["voti"][md].get("status") or "rated") == "rated"]
    return mds, rated, n_voti

def listone_stats(D):
    ps = [p for p in (D.get("listone") or {}).get("players") or [] if p.get("price") is not None]
    by = {r: sorted([p for p in ps if p.get("role") == r], key=lambda p: (-(p.get("price") or 0), p.get("name") or "")) for r, _, _ in SLOTS}
    return ps, by

def table(head, rows, caption="", cls=""):
    """Tabella in .tscroll; head = [(testo, classe)], rows = [[celle html]] con classi gia' nelle celle."""
    h = "".join("<th%s>%s</th>" % ((' class="' + c + '"') if c else "", t) for t, c in head)
    b = "".join("<tr>" + "".join(r) + "</tr>" for r in rows)
    return ('<div class="tscroll"><table%s>%s<thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
            % ((' class="' + cls + '"') if cls else "", ("<caption>" + caption + "</caption>") if caption else "", h, b))

def td(x, cls=""):
    return "<td%s>%s</td>" % ((' class="' + cls + '"') if cls else "", x)

def faq_html(faq):
    return '<div class="faq">' + "".join("<details><summary>" + esc(q) + "</summary><p>" + a + "</p></details>" for q, a in faq) + "</div>"

def faq_ld(faq):
    import re
    strip = lambda s: re.sub(r"<[^>]+>", "", s)
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": strip(a)}} for q, a in faq]}

# CSS proprio delle tre pagine: solo cio' che il foglio condiviso non ha (passi numerati, barre del budget, elenco a due colonne).
EXTRA_CSS = ("<style>"
             ".steps{list-style:none;counter-reset:s;margin:0 0 16px}.steps li{position:relative;padding:0 0 12px 44px;counter-increment:s}"
             ".steps li::before{content:counter(s);position:absolute;left:0;top:0;width:28px;height:28px;border-radius:8px;background:var(--violet);color:#fff;"
             "font-size:13px;font-weight:700;display:grid;place-items:center}.steps b{display:block;font-size:16px;margin-bottom:4px}"
             ".bar{display:flex;align-items:center;gap:8px;min-width:120px}.bar i{display:block;height:8px;border-radius:6px;background:var(--violet)}"
             ".ul2{columns:2;column-gap:24px;margin:0 0 16px 20px}.ul2 li{break-inside:avoid;padding:2px 0}"
             ".card ul,.card ol{margin:0 0 8px 20px}.card li{padding:2px 0}ul.plain{margin:0 0 16px 20px}ul.plain li{padding:2px 0}"
             ".ico{display:inline-flex;align-items:center;gap:8px}.ico svg{flex:none;color:var(--violet)}"
             "@media(max-width:760px){.ul2{columns:1}}</style>")

ICON_CHECK = ('<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>')
ICON_ALERT = ('<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
              '<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>')

# =====================================================================================================================
# 1. REGOLAMENTO
# =====================================================================================================================
def render_regolamento(D, T):
    canon = SITE + "/fantacalcio/regolamento.html"
    mds, rated, n_voti = voti_stats(D)
    oggi = fdate_it(today_iso() + "T12:00:00Z")
    last_md = mds[-1] if mds else 0
    voti_url = ("/fantacalcio/voti-giornata-%d.html" % last_md) if last_md else "/fantacalcio/"
    # esempi numerici calcolati con le stesse formule del motore
    ex_rating, ex_gol, ex_amm = 7.32, 1, 1
    ex_base = voto_base(ex_rating); ex_fv = ex_base + 3 * ex_gol - 0.5 * ex_amm
    gk_rating, gk_sub, gk_rig = 7.10, 2, 1
    gk_base = voto_base(gk_rating); gk_fv = gk_base - 1 * gk_sub + 3 * gk_rig
    mod_p, mod_d = 6.5, [6.5, 6.5, 6.0, 5.5]
    mod_best = sorted(mod_d, reverse=True)[:3]
    mod_avg = (sum(mod_best) / 3 * 3 + mod_p) / 4
    mod_v = mod_lookup(mod_avg, MOD_DEF)
    n_bonus = len(BONUS)

    b = ["<h1>Regolamento FantaTB: regole di lega, bonus e malus, calcolo del voto</h1>",
         '<p class="sub">Il regolamento di FantaTB per la Serie A ' + SEASON + " prevede rose da " + str(ROSA) + " giocatori (3 portieri, 8 difensori, 8 centrocampisti, "
         "6 attaccanti), " + str(CREDITS) + " crediti d'asta per squadra, " + str(n_bonus) + " voci di bonus e malus e il modificatore difesa attivo di default; "
         "questa pagina è aggiornata al " + esc(oggi) + (", con " + "{:,}".format(n_voti).replace(",", ".") + " voti già calcolati in " + str(len(mds)) + " giornate" if n_voti else "") + ".</p>",
         '<div class="kpis">'
         '<div class="kpi"><div class="l">Crediti per squadra</div><div class="v">' + str(CREDITS) + '</div><div class="s">modificabili dall\'admin</div></div>'
         '<div class="kpi"><div class="l">Giocatori in rosa</div><div class="v">' + str(ROSA) + '</div><div class="s">3 P · 8 D · 8 C · 6 A</div></div>'
         '<div class="kpi"><div class="l">Panchina</div><div class="v">' + str(BENCH) + '</div><div class="s">massimo ' + str(MAX_SUBS) + ' sostituzioni</div></div>'
         '<div class="kpi"><div class="l">Timer d\'asta</div><div class="v">' + str(TIMER) + ' s</div><div class="s">riparte a ogni rilancio</div></div>'
         '<div class="kpi"><div class="l">Primo gol</div><div class="v">' + str(GOAL_BASE) + '</div><div class="s">poi uno ogni ' + str(GOAL_STEP) + ' punti</div></div>'
         '</div>']

    # --- come funziona
    b.append("<h2>Come funziona FantaTB</h2>")
    b.append('<div class="grid2">'
             '<div class="card"><h3>1. La lega</h3><div class="in"><p>Chi crea la lega ne è l\'admin: sceglie nome, numero massimo di squadre (' + str(MAX_TEAMS) + ' di default), crediti, '
             'composizione delle rose e tutte le regole di questa pagina, che restano modificabili dalla scheda Regole anche a campionato iniziato. Gli amici entrano con il codice d\'invito, '
             'da telefono o computer, senza installare nulla: bastano un\'email e una password. La lega ha due fasi: <b>asta</b> e <b>campionato</b>.</p></div></div>'
             '<div class="card"><h3>2. L\'asta</h3><div class="in"><p>L\'asta è live: l\'admin fa il banditore, cerca un giocatore nel listone e lo mette all\'asta con una base; '
             'tutti rilanciano di +1, +5, +10 o con un importo libero, il timer di ' + str(TIMER) + ' secondi riparte a ogni offerta e allo scadere il giocatore va all\'ultimo offerente. '
             'Ogni squadra vede crediti residui e posti liberi per ruolo; non si può superare il budget né comprare un ruolo già completo. '
             'Le quotazioni del <a href="/fantacalcio/listone.html">listone</a> sono un riferimento, non un prezzo minimo.</p></div></div>'
             '<div class="card"><h3>3. Le formazioni</h3><div class="in"><p>Per ogni giornata si sceglie un modulo fra i sette disponibili, si schierano 11 titolari e fino a ' + str(BENCH) + ' panchinari '
             'in ordine di priorità. La scadenza coincide con l\'inizio della prima partita della giornata ed è indicata nella scheda Schiera insieme all\'indice di titolarità e alle '
             'croci degli infortunati di ogni giocatore. Chi non invia la formazione gioca con l\'ultima inviata.</p></div></div>'
             '<div class="card"><h3>4. Il calcolo</h3><div class="in"><p>Il punteggio di squadra è la somma dei fantavoti degli undici (con le sostituzioni automatiche dalla panchina) più i modificatori '
             'attivi. I punti diventano gol con la tabella qui sotto e la partita di lega finisce 3-1-0 come nel calcio. Durante le giornate i risultati si aggiornano ogni 30 minuti '
             'con il <a href="#sei-politico">6 politico</a> per chi deve ancora giocare, poi vengono consolidati a giornata finita.</p></div></div></div>')

    # --- bonus e malus
    b.append('<h2 id="bonus">Tabella dei bonus e dei malus</h2>'
             '<p>Pesi di default, tutti modificabili dall\'admin nella scheda Regole. Il fantavoto di un giocatore è il voto più la somma di queste voci.</p>')
    rows = []
    for voce, peso, chi, nota in BONUS:
        cls = "pill ok" if peso > 0 else ("pill err" if peso < 0 else "pill")
        rows.append([td("<b>" + esc(voce) + "</b>"), td('<span class="' + cls + '">' + dec(peso, plus=True) + "</span>", "c"), td(esc(chi)), td(esc(nota), "small")])
    b.append(table([("Voce", ""), ("Peso", "c"), ("A chi si applica", ""), ("Nota", "")], rows))

    # --- voto statistico
    b.append('<h2 id="voto">Il voto statistico FantaTB, spiegato</h2>'
             '<p>FantaTB non usa i voti dei quotidiani: il voto di ogni giocatore nasce dal <b>rating statistico della partita</b> (passaggi, duelli, tiri, parate, errori) '
             'fornito da API-Football. La formula è pubblica e sempre la stessa per tutti:</p>'
             '<div class="card"><div class="in"><p><b>Voto base = rating − 0,8, arrotondato al mezzo punto, compreso fra 4 e 8,5.</b></p>'
             '<ul><li>Sotto i 15 minuti giocati il giocatore è <b>senza voto</b> (s.v.) e viene sostituito dalla panchina.</li>'
             '<li>Con almeno 15 minuti ma senza rating disponibile il voto è <b>6 d\'ufficio</b>.</li>'
             '<li>Il rating premia chi partecipa al gioco: un regista che tocca molti palloni o un portiere molto impegnato prendono spesso 6,5; un attaccante che segna con un rating basso '
             'resta a 6 di base ma incassa il +3 del gol.</li>'
             '<li>Le soglie contano: rating 7,05 dà 6,5, rating 7,04 dà 6. Da 7,55 in su il voto base è 7.</li></ul></div></div>')
    b.append('<h3>Esempio numerico: un centrocampista</h3>'
             "<p>Rating " + dec(ex_rating) + " → " + dec(ex_rating) + " − 0,8 = " + dec(round(ex_rating - 0.8, 2)) + ", arrotondato al mezzo punto fa <b>" + dec(ex_base) + "</b>. "
             "Segna un gol (+3) e prende un\'ammonizione (−0,5): fantavoto <b>" + dec(ex_base) + " + 3 − 0,5 = " + dec(ex_fv) + "</b>.</p>"
             '<h3>Esempio numerico: un portiere</h3>'
             "<p>Rating " + dec(gk_rating) + " → voto base <b>" + dec(gk_base) + "</b>. Subisce " + str(gk_sub) + " gol (−1 ciascuno) e para un rigore (+3): "
             "fantavoto <b>" + dec(gk_base) + " − " + str(gk_sub) + " + 3 = " + dec(gk_fv) + "</b>. Il rigore parato non conta fra i gol subiti.</p>"
             '<p class="small">Verifica sui voti pubblicati: <a href="' + voti_url + '">voti della giornata ' + str(last_md) + '</a>' + (" · giornate calcolate: " + ", ".join(str(m) for m in mds) if mds else "") + ".</p>")

    # --- modificatori
    b.append('<h2 id="modificatori">I modificatori</h2>'
             '<p>Tre modificatori, tutti configurabili. Di default è acceso solo quello di difesa. Le voci dei modificatori attivi compaiono sempre nel dettaglio della partita, anche quando valgono 0.</p>')
    b.append('<h3>Modificatore difesa (attivo di default)</h3>'
             '<p>Si calcola sulla <b>media dei voti</b> (senza bonus e malus) del portiere e dei 3 migliori difensori schierati; serve avere almeno <b>4 difensori</b> con voto in campo, '
             'altrimenti vale 0. L\'admin può escludere il portiere (in quel caso conta la media dei 4 migliori difensori) e scegliere se il bonus va alla propria squadra o diventa un '
             'malus per l\'avversaria. La tabella delle soglie è modificabile; questa è quella di default:</p>')
    b.append(table([("Media voto", ""), ("Modificatore", "c")], [[td("da " + dec(s)), td('<span class="pill ok">' + dec(v, plus=True) + "</span>", "c")] for s, v in MOD_DEF] +
                   [[td("sotto 6"), td('<span class="pill">0</span>', "c")]]))
    b.append("<p><b>Esempio.</b> Portiere " + dec(mod_p) + ", difensori " + ", ".join(dec(x) for x in mod_d) + ": i tre migliori difensori fanno " + ", ".join(dec(x) for x in mod_best) +
             " e la media dei quattro voti è " + dec(round(mod_avg, 3)) + " → modificatore <b>" + dec(mod_v, plus=True) + "</b>. Con un 6,5 al posto del 6 la media salirebbe a 6,5 e il bonus a +2: "
             "un difensore in più da voto alto sposta il risultato più di quanto sembri.</p>")
    b.append('<h3>Modificatore attacco (spento di default)</h3>'
             '<p>Media dei voti degli attaccanti schierati, con almeno 2 in campo, sulla scala fissa: ' +
             ", ".join("da " + dec(s) + " " + dec(v, plus=True) for s, v in MOD_ATT) + ".</p>"
             '<h3>Modificatore centrocampo (spento di default)</h3>'
             '<p>Si confrontano le <b>medie</b> (non le somme, per non premiare i moduli a cinque) dei voti dei centrocampisti delle due squadre, con almeno 3 per parte: '
             'la differenza dà un bonus a chi ha la media più alta: ' + ", ".join("da " + dec(s) + " " + dec(v, plus=True) for s, v in MOD_MID) + ".</p>")

    # --- 6 politico
    b.append('<h2 id="sei-politico">Il 6 politico</h2>'
             '<p>In FantaTB il 6 politico ha due significati, entrambi automatici.</p>'
             '<ul class="plain"><li><b>Durante la giornata (risultati live).</b> Finché la giornata non è consolidata, chi ha in campo un giocatore la cui partita non è ancora stata giocata '
             'riceve per lui un 6 provvisorio senza bonus: entra nel totale e nel modificatore difesa come un 6, così il risultato live è una simulazione completa e non un parziale. '
             'Nella scheda Risultati la riga è evidenziata in ambra con l\'asterisco. A giornata finita il 6 viene sostituito dal voto reale.</li>'
             '<li><b>A giornata finita.</b> Chi ha giocato almeno 15 minuti ma per cui il fornitore non ha un rating riceve un 6 d\'ufficio, a cui si sommano normalmente bonus e malus. '
             'Chi non è sceso in campo non prende nessun 6: viene sostituito dalla panchina.</li></ul>')

    # --- panchina
    b.append('<h2 id="panchina">Panchina e sostituzioni automatiche</h2>'
             '<p>La panchina ha fino a ' + str(BENCH) + ' posti numerati e <b>l\'ordine conta</b>. Quando un titolare resta senza voto (meno di 15 minuti, non convocato, partita rinviata) '
             'il motore scorre la panchina dal primo posto e fa entrare il <b>primo panchinaro dello stesso ruolo che ha un voto</b>, saltando quelli senza voto. '
             'Le sostituzioni sono al massimo ' + str(MAX_SUBS) + ' per giornata (modificabile). Se nessun panchinaro del ruolo ha un voto, il posto vale 0. '
             'Nelle giornate live chi deve ancora giocare non viene sostituito: riceve il 6 politico e si aspetta la sua partita.</p>'
             '<div class="note"><b>Consiglio pratico.</b> Il primo panchinaro di ogni ruolo dovrebbe essere un titolare vero della sua squadra: con 3 sostituzioni automatiche una panchina '
             'che gioca vale un 6 al posto di uno 0. Nella <a href="/fantacalcio/guida-asta.html">guida all\'asta</a> spieghiamo come costruirla.</div>')

    # --- gol e punti
    b.append('<h2 id="gol">Dai fantapunti ai gol</h2><p>Il primo gol scatta a ' + str(GOAL_BASE) + ' punti e poi uno ogni ' + str(GOAL_STEP) + ' (entrambi modificabili). '
             'Vittoria 3 punti, pareggio 1, sconfitta 0; chi riposa somma i fantapunti ma non fa classifica per quel turno.</p>')
    soglie = [GOAL_BASE + GOAL_STEP * i for i in range(6)]
    b.append(table([("Fantapunti", ""), ("Gol", "c")], [[td("da " + str(s) + " a " + str(s + GOAL_STEP - 0.5).replace(".", ",")), td(str(gol_da_punti(s)), "c")] for s in soglie] +
                   [[td("sotto " + str(GOAL_BASE)), td("0", "c")]]))

    # --- regole modificabili
    b.append('<h2>Cosa può cambiare l\'admin</h2><ul class="ul2">'
             '<li>Crediti, numero di squadre, posti per ruolo e dimensione della panchina</li><li>Timer dell\'asta e numero massimo di sostituzioni</li>'
             '<li>Peso di ogni bonus e malus, porta inviolata compresa</li><li>Modificatori accesi o spenti, tabella delle soglie della difesa, portiere incluso o no, bonus proprio o malus all\'avversario</li>'
             '<li>Fattore casa e trasferta (attivo solo con formazione inviata)</li><li>Soglia del primo gol e passo dei successivi</li>'
             '<li>Correzione manuale di un singolo voto</li><li>Ricalcolo delle giornate passate dopo un cambio di regole</li></ul>')

    # --- FAQ
    faq = [("I voti FantaTB sono quelli dei giornali?", "No. Sono voti statistici calcolati da TransferBeat dai dati reali della partita con una formula pubblica (rating meno 0,8, "
            "arrotondato al mezzo punto). Non coincidono con quelli dei quotidiani e FantaTB non è affiliato a Fantacalcio®."),
           ("Quando arrivano i voti?", "Durante le giornate i risultati si aggiornano ogni 30 minuti con le partite finite e il 6 politico per quelle ancora da giocare; "
            "a giornata completa i voti vengono consolidati e i punteggi di lega calcolati in automatico. Sono pubblici anche senza login nella sezione "
            '<a href="/fantacalcio/">Fantacalcio</a> di TransferBeat.'),
           ("Cosa succede se un mio titolare non gioca?", "Entra il primo panchinaro dello stesso ruolo che ha un voto, nell'ordine in cui hai messo la panchina, fino a un massimo di "
            + str(MAX_SUBS) + " sostituzioni. Se nessuno del ruolo ha un voto, quel posto vale 0."),
           ("Il modificatore difesa usa il voto o il fantavoto?", "Il voto, senza bonus e malus: un difensore ammonito con 6,5 conta 6,5 nella media. Servono almeno 4 difensori con voto; "
            "di default la media include il portiere."),
           ("Un gol di un difensore vale quanto uno di un attaccante?", "Sì: +3 per tutti i ruoli, come l'assist vale +1 per tutti. Solo gol subito, rigore parato e porta inviolata "
            "riguardano i portieri."),
           ("Posso cambiare le regole a campionato iniziato?", "Sì, dalla scheda Regole della lega. Le nuove regole valgono dai calcoli successivi; per le giornate passate l'admin può "
            "usare Ricalcola."),
           ("Quanto costa FantaTB e serve un'app?", "È gratuito, senza limiti di leghe e senza funzioni a pagamento. Funziona dal browser del telefono e del computer: "
            '<a href="/fanta/">apri l\'app</a> o leggi la <a href="/fantatb.html">presentazione</a>.'),
           ("Da dove vengono infortuni e probabilità di titolarità?", "Dal feed infortuni di API-Football e dalle ultime tre giornate giocate: l'indice è nella pagina "
            '<a href="/fantacalcio/titolari.html">infortunati e squalificati</a> e accanto a ogni nome nella scheda Schiera.')]
    b.append("<h2>Domande frequenti</h2>" + faq_html(faq))
    b.append('<div class="grad"><div class="k">FantaTB</div><h2>Crea la tua lega con queste regole, o cambiale</h2>'
             '<p>Leghe private, asta live dal telefono, voti ogni 30 minuti, tutto gratis. Le regole di questa pagina sono i default: ogni lega decide le sue.</p>'
             '<a class="btn" href="/fanta/#crea">Crea la tua lega</a> <a class="btn" href="/fantatb.html">Scopri FantaTB</a></div>')
    b.append('<p class="small">Pagine collegate: <a href="/fantacalcio/guida-asta.html">guida all\'asta</a> · <a href="/fantacalcio/consigli.html">chi schierare</a> · '
             '<a href="/fantacalcio/listone.html">listone</a> · <a href="/fantacalcio/probabili-formazioni.html">probabili formazioni</a> · <a href="/fantacalcio/">tutti i dati del fantacalcio</a>.</p>')

    ld = [faq_ld(faq),
          {"@context": "https://schema.org", "@type": "WebPage", "name": "Regolamento FantaTB", "url": canon, "inLanguage": "it", "dateModified": today_iso(),
           "about": {"@type": "WebApplication", "name": "FantaTB", "url": SITE + "/fanta/", "applicationCategory": "GameApplication", "operatingSystem": "Web",
                     "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"}}, "publisher": ORG}]
    return page("Regolamento FantaTB: bonus, malus e voto",
                "Regole di FantaTB, il fantacalcio gratuito di TransferBeat: rose da " + str(ROSA) + ", asta a " + str(CREDITS) + " crediti, bonus e malus, voto statistico, "
                "modificatori, panchina e FAQ.",
                canon, "".join(b), crumbs=FANTA_CRUMB + [("Regolamento", canon)], ld=ld, here="Fantacalcio", extra_head=EXTRA_CSS, bar=FANTA_BAR, bar_here="Regolamento")

# =====================================================================================================================
# 2. GUIDA ALL'ASTA
# =====================================================================================================================
# Ripartizioni del budget (percentuali ragionate su 500 crediti): (nome, {ruolo: %}, quando conviene)
RIPARTIZIONI = [("Muro e un bomber", {"P": 7, "D": 27, "C": 16, "A": 50},
                 "Regole FantaTB di default (modificatore difesa acceso, voto statistico): portiere e difensori da voto alto valgono più dei centrocampisti da bonus."),
                ("Classic senza modificatori", {"P": 7, "D": 18, "C": 35, "A": 40},
                 "Lega senza modificatore difesa o con voti redazionali: il centrocampo torna a pesare, i difensori si comprano quasi tutti a basso costo.")]

def render_guida(D, T):
    canon = SITE + "/fantacalcio/guida-asta.html"
    ps, by = listone_stats(D)
    L = D.get("listone") or {}
    upd = fdate_it(L.get("updated") or today_iso())
    n = len(ps); tot = sum(p["price"] for p in ps); top = max((p["price"] for p in ps), default=0)
    medio = round(CREDITS / ROSA)
    counts = {r: len(by[r]) for r, _, _ in SLOTS}
    posti8 = {r: k * MAX_TEAMS for r, _, k in SLOTS}
    posti10 = {r: k * 10 for r, _, k in SLOTS}
    # titolari per ruolo: gli undici delle probabili formazioni dell'ultima giornata (a inizio stagione l'indice di titolarita'
    # da' 90 solo a chi ha giocato tutte le ultime tre gare e sottostimerebbe i titolari); ripiego: indice >= 65
    prob = D.get("probabili") or {}
    tit70 = {r: 0 for r, _, _ in SLOTS}
    if prob:
        P = prob[max(prob)]; tit_src = "gli undici delle probabili formazioni della giornata " + str(P.get("matchday"))
        for t in (P.get("teams") or {}).values():
            for x in t.get("xi") or []:
                if x.get("role") in tit70:
                    tit70[x["role"]] += 1
        has_tit = True
    else:
        tit = D.get("titolari") or {}
        byid = {p["id"]: p for p in ps}
        for s in tit.get("status") or []:
            p = byid.get(s.get("player_id"))
            if p and (s.get("prob") or 0) >= 65 and p.get("role") in tit70:
                tit70[p["role"]] += 1
        has_tit = bool(tit.get("status")); tit_src = "i giocatori con indice di titolarità almeno 65% per la giornata " + str(tit.get("matchday"))
    summ = summaries(D)

    b = ["<h1>Guida all'asta del fantacalcio " + SEASON + ": budget per ruolo, ordine delle chiamate e tetti di spesa</h1>",
         '<p class="sub">Con ' + str(CREDITS) + " crediti e " + str(ROSA) + " giocatori da comprare, un posto in rosa costa in media " + str(medio) + " crediti; il listone TransferBeat del " + esc(upd) +
         " quota " + str(n) + " giocatori di Serie A (" + ", ".join(str(counts[r]) + " " + RUOLI_PL[r].lower() for r, _, _ in SLOTS) + ") per un totale di " + "{:,}".format(tot).replace(",", ".") +
         " crediti, con la quotazione più alta a " + str(top) + ". Questa guida è scritta per un'asta a 8-10 squadre con le <a href=\"/fantacalcio/regolamento.html\">regole FantaTB</a>, "
         "ma i principi valgono per qualsiasi Classic.</p>",
         '<div class="kpis">'
         '<div class="kpi"><div class="l">Giocatori quotati</div><div class="v">' + str(n) + '</div><div class="s">listone del ' + esc(upd) + '</div></div>'
         '<div class="kpi"><div class="l">Posti da riempire</div><div class="v">' + str(ROSA * MAX_TEAMS) + '</div><div class="s">con 8 squadre · ' + str(ROSA * 10) + ' con 10</div></div>'
         '<div class="kpi"><div class="l">Crediti in gioco</div><div class="v">' + "{:,}".format(CREDITS * MAX_TEAMS).replace(",", ".") + '</div><div class="s">8 squadre da ' + str(CREDITS) + '</div></div>'
         '<div class="kpi"><div class="l">Costo medio di un posto</div><div class="v">' + str(medio) + '</div><div class="s">crediti a giocatore</div></div>'
         '</div>']

    # --- scarsita' per ruolo (numeri veri)
    b.append("<h2>Quanti giocatori ci sono davvero per ogni ruolo</h2>"
             "<p>Prima di parlare di crediti conviene guardare l'offerta: in un'asta a 8 squadre si comprano " + str(ROSA * MAX_TEAMS) + " giocatori su " + str(n) +
             " quotati, ma la scarsità è diversa ruolo per ruolo. I difensori e i centrocampisti titolari avanzano e finiscono a 1-3 crediti negli ultimi giri; gli attaccanti titolari no.</p>")
    rows = []
    for r, nome, k in SLOTS:
        rows.append([td(rb(r) + " " + esc(nome)), td(str(counts[r]), "num"), td(str(posti8[r]), "num"), td(str(posti10[r]), "num"),
                     td((str(tit70[r]) if has_tit else "—"), "num"),
                     td(('<span class="pill %s">%s</span>' % (("err" if tit70[r] < posti8[r] else "ok"), ("scarsi" if tit70[r] < posti8[r] else "abbondanti"))) if has_tit else "—", "c")])
    b.append(table([("Ruolo", ""), ("Quotati", "num"), ("Posti con 8 squadre", "num"), ("Posti con 10", "num"), ("Titolari", "num"), ("Titolari vs posti (8 squadre)", "c")], rows,
                   caption=("Titolari = " + tit_src + ".") if has_tit else "Titolari: disponibili con le probabili formazioni della giornata."))

    # --- budget per ruolo
    b.append('<h2 id="budget">Il budget per ruolo su ' + str(CREDITS) + " crediti</h2>"
             "<p>Due ripartizioni ragionate. La prima segue le regole di default di FantaTB, dove il voto è statistico e il modificatore difesa premia un blocco portiere più difensori da voto alto; "
             "la seconda è la classica ripartizione di un fantacalcio senza modificatori. Sono punti di partenza: scrivi la tua prima dell'asta e adattala durante, non dopo.</p>")
    for nome, pct, quando in RIPARTIZIONI:
        rows = []
        for r, ruolo, k in SLOTS:
            cred = round(CREDITS * pct[r] / 100)
            rows.append([td(rb(r) + " " + esc(ruolo) + ' <span class="small">(' + str(k) + " posti)</span>"), td(str(pct[r]) + "%", "num"), td(str(cred), "num"),
                         td(str(round(cred / k)), "num"), td('<span class="bar"><i style="width:' + str(pct[r] * 2) + 'px"></i></span>')])
        b.append('<div class="card"><h3>' + esc(nome) + "</h3><div class=\"in\"><p>" + esc(quando) + "</p>" +
                 table([("Ruolo", ""), ("Quota", "num"), ("Crediti", "num"), ("Media a posto", "num"), ("", "")], rows) + "</div></div>")
    b.append('<div class="note"><b>Con 10 squadre</b> le percentuali restano le stesse ma i posti da riempire salgono a ' + str(ROSA * 10) + ': gli attaccanti titolari finiscono prima, '
             'quindi i tre-quattro attaccanti economici vanno presi subito dopo il blocco e non negli ultimi giri. Chi entra in una lega con crediti diversi da ' + str(CREDITS) + ' può usare le percentuali così come sono.</div>')

    # --- prima dell'asta
    b.append('<h2 id="prima">Prima dell\'asta: tetti, liste e checkpoint</h2><ol class="steps">'
             '<li><b>Scrivi un tetto per ogni giocatore che vuoi</b>Uno solo, su carta, prima di sederti. Il tetto è un limite di disciplina, non una previsione: in un\'asta a 8 i primi 10-15 nomi chiamati '
             'salgono del 20-40% sopra il loro valore atteso, perché tutti hanno ancora ' + str(CREDITS) + ' crediti. Un solo giocatore sopra il 30% del budget; la somma dei tre acquisti più cari non oltre il 55-60%.</li>'
             '<li><b>Prepara la lista a tre alternative</b>Per ognuno dei 12-13 posti che contano (il portiere, 5-6 difensori, 4 centrocampisti, 2 attaccanti) tre nomi con fantamedia simile e il loro tetto: '
             'quando il primo sfonda, passi al secondo senza rimpianti. Le <a href="/giocatori/">schede giocatore</a> danno fantamedia, media voto e titolarità.</li>'
             '<li><b>Tieni a parte 15 nomi da 1 credito</b>Titolari veri (titolarità 90%) di squadre medio-piccole, quasi tutti difensori e centrocampisti: servono per chiudere la rosa negli ultimi giri senza ragionare sotto pressione.</li>'
             '<li><b>Fissa i checkpoint del budget</b>A un terzo dell\'asta almeno il 60% dei crediti se non hai ancora l\'attaccante top, almeno il 35% se lo hai; a due terzi blocco portiere più difensori completo '
             'e non più del 15-20% residuo; sempre 1 credito per posto vuoto più 15-25 crediti per gli ultimi giri.</li>'
             '<li><b>Controlla i dati della settimana</b>Il giorno dell\'asta rileggi <a href="/fantacalcio/titolari.html">infortunati e squalificati</a> e le '
             '<a href="/fantacalcio/probabili-formazioni.html">probabili formazioni</a>: un titolare fermo due mesi cambia il tetto, un 45% di titolarità dopo due giornate su un titolare certo è uno sconto, non un allarme.</li></ol>')

    # --- ordine delle chiamate
    b.append('<h2 id="ordine">L\'ordine dei ruoli e delle chiamate</h2>'
             '<div class="grid3">'
             '<div class="card"><h3>Primi giri</h3><div class="in"><p>Tutti hanno tutti i crediti: è il momento in cui i nomi si gonfiano. Chiama tu i giocatori famosi che <b>non</b> vuoi, così gli altri bruciano crediti; '
             'non rilanciare su niente fuori lista. L\'unica eccezione è l\'attaccante top: se esce subito, rilancia fino al tetto e non oltre.</p></div></div>'
             '<div class="card"><h3>Secondo terzo</h3><div class="in"><p>Tre o quattro squadre hanno già speso 200 crediti sui top e ragionano al ribasso: è qui che si comprano il portiere, i difensori del blocco '
             'e i centrocampisti da voto alto, che il listone sottovaluta. Subito dopo il blocco, gli attaccanti economici ma titolari: sono pochi e spariscono.</p></div></div>'
             '<div class="card"><h3>Ultimi giri</h3><div class="in"><p>Arrivaci con i posti vuoti in difesa e a centrocampo, mai in attacco o in porta: lì l\'offerta di titolari a 1-3 crediti è ampia. '
             'Chi arriva in fondo con 60-80 crediti e cinque posti li spreca pagando 20 un attaccante da 6 di fantamedia.</p></div></div></div>')

    # --- ruolo per ruolo
    def top5(r, k=5):
        rows = []
        for p in by[r][:k]:
            s = summ.get(p["id"]) or {}
            rows.append([td(plink(D, p["id"], p["name"])), td(team_link(T, p.get("team"))), td(str(p["price"]), "num"),
                         td(dec(s.get("fmv")), "num"), td(dec(s.get("mv")), "num")])
        return table([("Giocatore", ""), ("Squadra", ""), ("Quotazione", "num"), ("Fantamedia", "num"), ("Media voto", "num")], rows,
                     caption="I " + str(min(k, len(by[r]))) + " " + RUOLI_PL[r].lower() + " più quotati del listone; fantamedia e media voto FantaTB " + SEASON + " (— = ancora senza voti).")

    b.append('<h2 id="portieri">' + rb("P") + ' Portieri: uno solo, con la sua riserva</h2>'
             '<p>Con il voto statistico i portieri hanno tutti un rating simile: quello che li distingue è il <b>−1 a gol subito</b>. Un portiere di una difesa che incassa 0,8 gol a partita vale '
             'mezzo punto a giornata più di uno da 1,3, cioè circa 20 punti a stagione: si paga la squadra, non il nome. Lo schema che funziona è <b>un titolare di una difesa solida, la sua riserva della stessa squadra a 1 credito</b> '
             '(se il titolare si ferma, il vice eredita la stessa difesa ed entra da solo con le sostituzioni automatiche) e un terzo portiere titolare di una piccola a 2-5 crediti per le emergenze. '
             'Evita il secondo portiere titolare di un\'altra squadra a 15-20 crediti: quei crediti sono un difensore da 6,5. Con il modificatore difesa il voto del portiere entra nella media del blocco: '
             'un 6,5 al posto di un 6 vale mezzo scalino di modificatore.</p>' + top5("P"))

    b.append('<h2 id="difensori">' + rb("D") + ' Difensori: il blocco vale più di un secondo bomber</h2>'
             '<p>Con il modificatore attivo il difensore vale prima di tutto per il <b>voto base</b>: la media del ruolo dà un 6, solo un difensore su dieci sale stabilmente a 6,5. '
             'Quattro elementi da 6,5 fanno una media che vale +2 a giornata, con punte a +3 e +4,5; quattro da 6 valgono +0,5 o +1. Un punto di modificatore in più per 38 giornate sono 38 punti, '
             'quanto 12-13 gol di un attaccante, e il listone prezza i difensori come in un Classic senza modificatore: per questo <b>5-6 difensori da voto alto di squadre che subiscono poco</b> '
             'possono essere pagati fino al 40-50% sopra il valore atteso. Gli altri 2-3 devono comunque giocare: con 3 buoni e 5 riempitivi, appena due non giocano scendi sotto i 4 difensori con voto e il modificatore salta.</p>'
             '<p>I difensori con bonus (terzini e quinti con gol e assist) sono un caso a parte: un esterno da 7 gol e 15 assist è un attaccante travestito e si compra al posto del secondo attaccante, non in aggiunta. '
             'Diffida invece di chi è quotato per un gol ogni tanto ma ha rating basso o prende 10 gialli l\'anno (−5 punti a stagione), e delle difese da 1,3 gol subiti a partita anche se il singolo ha buoni numeri. '
             'Schiera sempre 4 o 5 difensori: 4-4-2, 4-3-3, 5-3-2.</p>' + top5("D"))

    b.append('<h2 id="centrocampisti">' + rb("C") + ' Centrocampisti: rating alto a prezzo basso</h2>'
             '<p>Con il modificatore centrocampo spento un centrocampista vale solo voto più bonus: un regista da rating alto senza gol rende quanto o più di un\'ala da 6 di base con qualche gol, e costa un quinto. '
             'È il ruolo con l\'offerta più larga (' + str(counts["C"]) + ' quotati per ' + str(posti8["C"]) + ' posti con 8 squadre) e quello dove i crediti rendono meno: <b>mai un centrocampista sopra il 12% del budget</b>, '
             'al massimo uno "da bonus" e cinque titolari da voto a 10-20 crediti, più tre riempitivi a 1-6. La fascia dei centrocampisti da 10-30 crediti si sgonfia sempre nel secondo terzo dell\'asta: aspettala. '
             'Le ammonizioni costano −0,5: chi prende 8-9 gialli perde 0,12 a partita, poco rispetto a un rating da 6,5 fisso.</p>' + top5("C"))

    b.append('<h2 id="attaccanti">' + rb("A") + ' Attaccanti: un top, un secondo livello, quattro titolari veri</h2>'
             '<p>Il gol vale +3 e gli attaccanti da 15 gol valgono 1,3 punti a giornata in più di uno da 6 di base: qui si paga la produttività verificata (gol ogni 90 minuti, tiri, titolarità), non le prime due giornate. '
             'Il ruolo è piatto dopo i primi dieci: dal secondo livello in giù le fantamedie si assomigliano, quindi <b>un solo top</b> (fino al 30% del budget), un secondo attaccante da 8-12% e '
             '<b>quattro titolari a 2-4%</b> presi subito dopo il blocco difensivo. Riempire l\'attacco con sei "titolari" da 15-25 crediti significa spendere 100 crediti per fantamedie da 6,5 che una panchina a 3-5 crediti replica. '
             'Un rating sopra 7,05 è un bonus gratuito: base 6,5 invece di 6 per 38 giornate, come 5-6 gol in più.</p>' + top5("A"))

    # --- rilanci
    b.append('<h2 id="rilanci">Quando rilanciare, quando lasciare</h2><ul class="plain">'
             '<li><b>Rilancia negli ultimi secondi</b>, mai subito: ogni rilancio anticipato riavvia il timer di ' + str(TIMER) + ' secondi e regala tempo per ragionare agli altri.</li>'
             '<li><b>Su un obiettivo sotto tetto usa salti di +5 o +10</b>: spezzano le aste a piccoli passi che portano il prezzo esattamente al tetto di tutti e segnalano determinazione.</li>'
             '<li><b>Su un giocatore che non vuoi non toccare il timer</b>, anche se il prezzo sembra basso: ogni credito fuori piano è un credito in meno per il blocco.</li>'
             '<li><b>Lascia appena il prezzo supera il tetto</b>: per ogni posto esistono tre alternative con fantamedia simile. L\'unica eccezione dove sforare del 10-15% è il quinto difensore del blocco, '
             'perché senza 4 difensori con voto il modificatore salta.</li>'
             '<li><b>Tetti come minimi di disciplina</b>: se a un terzo dell\'asta sei sotto i checkpoint, smetti di rilanciare su tutto ciò che non è nella lista dei tre obiettivi per posto.</li></ul>')

    # --- panchina
    b.append('<h2 id="panchina">La panchina che gioca</h2><p>Con ' + str(BENCH) + ' panchinari e ' + str(MAX_SUBS) + ' sostituzioni automatiche, la panchina non è un deposito di riempitivi ma sette titolari a basso costo '
             'che entrano da soli quando un tuo titolare non ha voto: ogni panchinaro che gioca vale un 6 al posto di uno 0. Composizione tipo: 3 difensori, 2-3 centrocampisti, 1-2 attaccanti, tutti con titolarità 90%, '
             'pagati 1-6 crediti, con il più affidabile al primo posto del suo ruolo. Il motore FantaTB salta i panchinari senza voto e prende il primo del ruolo che ne ha uno, ma con al massimo ' + str(MAX_SUBS) +
             ' cambi l\'ordine resta importante. Regola completa nel <a href="/fantacalcio/regolamento.html#panchina">regolamento</a>.</p>')

    # --- errori comuni
    errori = ["Pagare due giornate come una stagione: le fantamedie di settembre sono segnali di titolarità e forma, non di rendimento atteso.",
              "Comprare i centrocampisti top a 80-90 crediti quando il modificatore centrocampo è spento: è il ruolo dove i crediti rendono meno.",
              "Scegliere il portiere per blasone e non per i gol subiti dalla sua squadra: il rating è quasi uguale per tutti, decide il malus.",
              "Difensori di difese che subiscono molto o con troppi cartellini, anche con un buon rating individuale.",
              "Sotto-investire in difesa con 3 buoni e 5 riempitivi: appena due non giocano il modificatore salta.",
              "Prendere per buone le statistiche estere e di Serie B: valgono 3-6 crediti da panchina, non 15-20 da titolare.",
              "Ignorare la percentuale di titolarità e gli infortuni senza chiedersi il perché, o all'opposto scambiare per allarme un dato di due giornate su un titolare certo.",
              "Bruciare 300 crediti nel primo giro e chiudere con venti riempitivi; oppure arrivare in fondo con 80 crediti e cinque posti.",
              "Sopravvalutare i cartellini: 10 gialli sono −5 punti a stagione, un rating da 6,5 fisso ne vale 19.",
              "Un secondo portiere titolare di un'altra squadra a 15-20 crediti al posto della riserva della stessa squadra a 1."]
    b.append('<h2 id="errori">Gli errori più comuni</h2><ul class="plain">' + "".join('<li class="ico">' + ICON_ALERT + "<span>" + esc(e) + "</span></li>" for e in errori) + "</ul>")

    # --- dati TransferBeat
    b.append('<h2 id="dati">Come usare i dati di TransferBeat durante l\'asta</h2><div class="grid2">'
             '<div class="card"><h3>Listone</h3><div class="in"><p>' + str(n) + ' giocatori con ruolo Classic, squadra e quotazione, ordinabili e filtrabili dal telefono: usalo come riferimento per il valore atteso, non come prezzo. '
             'Ogni nome apre la scheda con fantamedia, media voto e statistiche della stagione scorsa.</p><a class="btn" href="/fantacalcio/listone.html">Apri il listone</a></div></div>'
             '<div class="card"><h3>Probabili formazioni</h3><div class="in"><p>Moduli e undici con la percentuale di ogni giocatore, ballottaggi e sostituti: prima dell\'asta rivelano chi è titolare davvero e chi vive di prime pagine.</p>'
             '<a class="btn" href="/fantacalcio/probabili-formazioni.html">Le probabili della giornata</a></div></div>'
             '<div class="card"><h3>Infortunati e squalificati</h3><div class="in"><p>Indice di titolarità per ogni giocatore, infortuni con rientro stimato e squalifiche: un titolare fermo due mesi va pagato da panchina.</p>'
             '<a class="btn" href="/fantacalcio/titolari.html">Chi gioca e chi no</a></div></div>'
             '<div class="card"><h3>Voti e chi schierare</h3><div class="in"><p>Voto, bonus e fantavoto di ogni giornata con la formula pubblica, e la pagina dei consigli per la giornata in arrivo, generata dai dati.</p>'
             '<a class="btn" href="/fantacalcio/consigli.html">Chi schierare</a> <a class="btn sec" href="/fantacalcio/">Tutti i dati</a></div></div></div>')
    b.append('<div class="note"><b>Nota sulle regole.</b> I pesi dati qui alla difesa valgono con il modificatore difesa acceso e il voto statistico di FantaTB. In una lega con voti redazionali e senza modificatori usa la seconda ripartizione: '
             'i difensori tornano a costare poco e il centrocampo con i gol torna a contare. Le regole di default sono nel <a href="/fantacalcio/regolamento.html">regolamento</a>; '
             'puoi creare la tua lega su <a href="/fantatb.html">FantaTB</a> e cambiarle.</div>')

    steps = [("Scrivi i tetti", "Un tetto per ogni giocatore che vuoi, uno solo sopra il 30% del budget, somma dei tre più cari entro il 55-60%.", canon + "#prima"),
             ("Dividi il budget per ruolo", "Con le regole FantaTB circa 7% portieri, 27% difensori, 16% centrocampisti, 50% attaccanti; senza modificatori 7/18/35/40.", canon + "#budget"),
             ("Nei primi giri chiama chi non vuoi", "Fai spendere gli altri sui nomi gonfiati, non rilanciare fuori lista; rilancia solo sull'attaccante top se esce subito.", canon + "#ordine"),
             ("Compra il portiere e il blocco nel secondo terzo", "Un portiere di una difesa solida con la sua riserva a 1, poi 5-6 difensori da voto alto pagati anche sopra il valore atteso.", canon + "#difensori"),
             ("Centrocampo di rating", "Cinque titolari da voto alto a 10-20 crediti, mai uno sopra il 12% del budget, tre riempitivi a 1-6.", canon + "#centrocampisti"),
             ("Attaccanti economici subito dopo il blocco", "Un top, un secondo livello e quattro titolari veri a 2-4% del budget presi prima che finiscano.", canon + "#attaccanti"),
             ("Rilancia negli ultimi secondi e a salti", "Salti di +5/+10 sotto tetto, timer intoccato su chi non vuoi, si lascia appena il tetto è superato.", canon + "#rilanci"),
             ("Chiudi con la panchina che gioca", "Ultimi giri con i posti vuoti in difesa e a centrocampo: titolari a 1-3 crediti, il più affidabile primo in panchina.", canon + "#panchina")]
    ld = [{"@context": "https://schema.org", "@type": "HowTo", "name": "Come preparare e condurre l'asta del fantacalcio", "inLanguage": "it",
           "description": "Budget per ruolo su " + str(CREDITS) + " crediti, ordine delle chiamate, tetti di spesa e panchina per un'asta a 8-10 squadre.",
           "totalTime": "PT3H", "estimatedCost": {"@type": "MonetaryAmount", "currency": "EUR", "value": "0"},
           "tool": [{"@type": "HowToTool", "name": "Listone TransferBeat"}, {"@type": "HowToTool", "name": "Probabili formazioni TransferBeat"}, {"@type": "HowToTool", "name": "Infortunati e squalificati TransferBeat"}],
           "step": [{"@type": "HowToStep", "position": i + 1, "name": nm, "text": tx, "url": u} for i, (nm, tx, u) in enumerate(steps)],
           "author": ORG, "publisher": ORG, "dateModified": today_iso()}]
    return page("Guida all'asta fantacalcio: budget e tetti",
                "Guida all'asta del fantacalcio " + SEASON + " su " + str(CREDITS) + " crediti: budget per ruolo, ordine delle chiamate, tetti, rilanci, "
                "errori comuni e i dati di TransferBeat.",
                canon, "".join(b), crumbs=FANTA_CRUMB + [("Guida all'asta", canon)], ld=ld, here="Fantacalcio", extra_head=EXTRA_CSS, bar=FANTA_BAR, bar_here="Guida all'asta")

# =====================================================================================================================
# 3. CHI SCHIERARE (consigli generati dai dati)
# =====================================================================================================================
SOGLIA_TIT = 70     # titolarita' minima per entrare fra i consigliati
N_MAX, N_MIN = 8, 5

def _opponents(P):
    """{squadra: (avversario, 'in casa'|'in trasferta', data iso)} dalle partite della giornata."""
    out = {}
    for f in P.get("fixtures") or []:
        out[f["home"]] = (f["away"], "in casa", f.get("date") or "")
        out[f["away"]] = (f["home"], "in trasferta", f.get("date") or "")
    return out

def render_consigli(D, T):
    canon = SITE + "/fantacalcio/consigli.html"
    prob = D.get("probabili") or {}
    oggi = fdate_it(today_iso() + "T12:00:00Z")
    if not prob:
        return _consigli_vuoti(D, T, canon, oggi)
    md = max(prob); P = prob[md]
    upd = P.get("updated") or ""
    opp = _opponents(P)
    dates = sorted(f["date"] for f in P.get("fixtures") or [] if f.get("date"))
    d1, d2 = (fdate_it(dates[0]), fdate_it(dates[-1])) if dates else ("", "")
    summ = summaries(D)
    byid = {p["id"]: p for p in (D.get("listone") or {}).get("players") or []}
    # candidati: titolari delle probabili con prob >= soglia
    cand = {r: [] for r, _, _ in SLOTS}
    doubt = []
    for team, t in (P.get("teams") or {}).items():
        for x in t.get("xi") or []:
            r = x.get("role")
            if r not in cand:
                continue
            s = summ.get(x["id"]) or {}
            row = {"id": x["id"], "name": x["name"], "role": r, "team": team, "prob": x.get("prob") or 0, "fmv": s.get("fmv"), "mv": s.get("mv"), "n": s.get("n") or 0,
                   "ballot": x.get("ballot"), "why": x.get("why") or ""}
            if row["prob"] >= SOGLIA_TIT:
                cand[r].append(row)
            elif row["prob"] < 60:
                doubt.append(row)
    def key(x):
        return (0 if x["fmv"] is not None else 1, -(x["fmv"] or 0), -x["prob"], x["name"])
    picks = {}
    for r in cand:
        lst = sorted(cand[r], key=key)
        con_fm = [x for x in lst if x["fmv"] is not None]
        picks[r] = (con_fm[:N_MAX] if len(con_fm) >= N_MIN else lst[:N_MAX])
    n_picks = sum(len(v) for v in picks.values())
    # da evitare: indisponibili dell'indice di titolarita' (prob 0) e "out" delle probabili
    tit = D.get("titolari") or {}
    inj, squal = [], []
    for s in tit.get("status") or []:
        p = byid.get(s.get("player_id"))
        if not p or (s.get("prob") or 0) > 0:
            continue
        reason = s.get("reason") or ""
        if s.get("injury"):
            inj.append((p, s))
        elif "squalific" in reason.lower():
            squal.append((p, s))
    seen = {p["id"] for p, _ in inj} | {p["id"] for p, _ in squal}
    for team, t in (P.get("teams") or {}).items():
        for o in t.get("out") or []:
            if o["id"] in seen:
                continue
            seen.add(o["id"])
            p = byid.get(o["id"]) or {"id": o["id"], "name": o["name"], "role": o.get("role"), "team": team}
            s = {"reason": o.get("reason") or "indisponibile", "injury": o.get("reason") if "infortun" in (o.get("reason") or "") else None, "back_at": o.get("back_at")}
            (squal if "squalific" in (o.get("reason") or "").lower() else inj).append((p, s))
    inj.sort(key=lambda x: (x[0].get("team") or "", x[0].get("name") or ""))
    squal.sort(key=lambda x: (x[0].get("team") or "", x[0].get("name") or ""))
    doubt.sort(key=lambda x: (x["prob"], x["name"]))
    n_out = len(inj) + len(squal)
    quando = (" in programma " + esc(periodo(d1, d2))) if d1 else ""

    b = ["<h1>Chi schierare nella giornata " + str(md) + " di Serie A " + SEASON + ": i consigli di TransferBeat per il fantacalcio</h1>",
         '<p class="sub">Per la giornata ' + str(md) + " di Serie A " + SEASON + quando + ", TransferBeat segnala " + str(n_picks) + " giocatori con titolarità almeno " + str(SOGLIA_TIT) +
         "% nelle probabili formazioni, ordinati per fantamedia FantaTB, e " + str(n_out) + " indisponibili da evitare; aggiornato il " + esc(fdate_it(upd, True) if upd else oggi) + ".</p>",
         '<div class="kpis">'
         '<div class="kpi"><div class="l">Giornata</div><div class="v">' + str(md) + '</div><div class="s">' + esc(periodo(d1, d2)) + '</div></div>'
         '<div class="kpi"><div class="l">Consigliati</div><div class="v">' + str(n_picks) + '</div><div class="s">titolarità ≥ ' + str(SOGLIA_TIT) + '%</div></div>'
         '<div class="kpi"><div class="l">Da evitare</div><div class="v">' + str(n_out) + '</div><div class="s">' + str(len(inj)) + ' infortunati · ' + str(len(squal)) + ' squalificati</div></div>'
         '<div class="kpi"><div class="l">In dubbio</div><div class="v">' + str(len(doubt)) + '</div><div class="s">titolarità sotto il 60%</div></div>'
         '</div>',
         '<div class="note"><b>I criteri.</b> Entrano solo i giocatori che nelle <a href="/fantacalcio/probabili-formazioni.html">probabili formazioni</a> della giornata ' + str(md) +
         ' hanno almeno il ' + str(SOGLIA_TIT) + '% di probabilità di partire titolare; l\'ordine è per fantamedia FantaTB della stagione (voto statistico più bonus e malus, '
         '<a href="/fantacalcio/regolamento.html#voto">formula</a>), poi per titolarità. Chi non ha ancora voti sta in fondo. Sono consigli generati dai dati, non da una redazione: '
         'incrociali con le notizie dell\'ultima ora e con il calendario del tuo avversario di lega.</div>']
    head = [("Giocatore", ""), ("Squadra", ""), ("Avversario", ""), ("Titolare", "num"), ("Fantamedia", "num"), ("Media voto", "num"), ("Voti", "num")]
    for r, nome, _ in SLOTS:
        lst = picks[r]
        b.append('<h2 id="' + r.lower() + '">' + rb(r) + " " + esc(nome) + ": " + str(len(lst)) + " nomi da schierare</h2>")
        if not lst:
            b.append("<p>Nessun " + esc(RUOLO[r].lower()) + " supera la soglia di titolarità in questa stima: riprova alla vigilia, quando le probabili vengono ricalcolate.</p>")
            continue
        rows = []
        for x in lst:
            o = opp.get(x["team"])
            avv = (team_link(T, o[0]) + ' <span class="small">' + esc(o[1]) + "</span>") if o else "—"
            pc = "g" if x["prob"] >= 70 else ("a" if x["prob"] >= 40 else "r")
            rows.append([td("<b>" + plink(D, x["id"], x["name"]) + "</b>"), td(team_link(T, x["team"])), td(avv),
                         td('<span class="pct ' + pc + '">' + str(x["prob"]) + "%</span>", "num"), td("<b>" + dec(x["fmv"]) + "</b>", "num"), td(dec(x["mv"]), "num"), td(str(x["n"]), "num")])
        b.append(table(head, rows))
        best = lst[0]
        o = opp.get(best["team"])
        b.append("<p>" + esc(best["name"]) + " (" + esc(best["team"]) + ") è " + esc(il(RUOLO[r].lower())) + " con la fantamedia più alta fra i titolari probabili" +
                 ((": " + dec(best["fmv"]) + " in " + str(best["n"]) + (" voto" if best["n"] == 1 else " voti")) if best["fmv"] is not None else "") +
                 ((", " + esc(o[1]) + " contro " + esc(o[0])) if o else "") + ". " +
                 ("Titolarità " + str(best["prob"]) + "%: " + esc(best["why"]) + "." if best["why"] else "") + "</p>")

    # da evitare
    b.append('<h2 id="evitare">Da evitare: infortunati, squalificati e in dubbio</h2>')
    if squal:
        b.append("<h3>Squalificati (" + str(len(squal)) + ')</h3><ul class="plain">' + "".join(
            "<li>" + rb(p.get("role") or "") + " <b>" + plink(D, p["id"], p["name"]) + "</b> (" + team_link(T, p.get("team")) + ") · " + esc(s.get("reason")) + "</li>" for p, s in squal) + "</ul>")
    if inj:
        b.append("<h3>Infortunati e indisponibili (" + str(len(inj)) + ')</h3><ul class="ul2">' + "".join(
            "<li>" + rb(p.get("role") or "") + " <b>" + plink(D, p["id"], p["name"]) + "</b> (" + team_link(T, p.get("team")) + ") · " + esc(pulisci_motivo(s.get("injury") or s.get("reason"))) +
            ((" · rientro stimato " + esc(fdate_it(s["back_at"] + "T12:00:00Z"))) if s.get("back_at") else "") + "</li>" for p, s in inj) + "</ul>")
    if doubt:
        b.append("<h3>In dubbio: titolari probabili sotto il 60% (" + str(len(doubt)) + ")</h3><p>Sono nell'undici delle probabili ma con un ballottaggio aperto o poche presenze recenti: "
                 "schierali solo con un panchinaro affidabile dello stesso ruolo dietro.</p>" +
                 table([("Giocatore", ""), ("Squadra", ""), ("Titolare", "num"), ("Ballottaggio con", ""), ("Fantamedia", "num")],
                       [[td(rb(x["role"]) + " " + plink(D, x["id"], x["name"])), td(team_link(T, x["team"])),
                         td('<span class="pct ' + ("a" if x["prob"] >= 40 else "r") + '">' + str(x["prob"]) + "%</span>", "num"),
                         td(esc(x["ballot"]["name"]) + " (" + str(x["ballot"].get("prob") or "") + "%)" if x.get("ballot") else "—"), td(dec(x["fmv"]), "num")] for x in doubt[:16]]))
    if not (squal or inj or doubt):
        b.append("<p>Nessun indisponibile segnalato al momento: il feed infortuni si popola a ridosso della giornata, ricontrolla alla vigilia.</p>")
    b.append('<p class="small">Fonti: <a href="/fantacalcio/probabili-formazioni.html">probabili formazioni giornata ' + str(md) + '</a> · <a href="/fantacalcio/titolari.html">infortunati e squalificati</a> · '
             '<a href="/fantacalcio/">voti e listone</a>. Dati grezzi: <a href="/data/fanta/probabili-%02d.json">probabili-%02d.json</a>. ' % (md, md) +
             'Le probabili vengono ricalcolate più volte a settimana fino al giorno di gara: questa pagina si aggiorna con loro.</p>')
    b.append('<div class="grad"><div class="k">FantaTB</div><h2>Schiera la formazione con la percentuale accanto a ogni nome</h2>'
             '<p>Nell\'app di FantaTB l\'indice di titolarità e le croci degli infortunati sono accanto a ogni giocatore della tua rosa, e i risultati arrivano ogni 30 minuti.</p>'
             '<a class="btn" href="/fanta/">Apri FantaTB</a> <a class="btn" href="/fantacalcio/guida-asta.html">Guida all\'asta</a></div>')

    items = []
    pos = 0
    for r, _, _ in SLOTS:
        for x in picks[r]:
            pos += 1
            it = {"@type": "ListItem", "position": pos, "name": x["name"] + " (" + x["team"] + ", " + RUOLO[r] + ")"}
            u = (summ.get(x["id"]) or {}).get("url")
            if u:
                it["url"] = SITE + u
            items.append(it)
    ld = [{"@context": "https://schema.org", "@type": "ItemList", "name": "Chi schierare nella giornata " + str(md) + " di Serie A " + SEASON, "url": canon,
           "description": str(n_picks) + " giocatori con titolarità almeno " + str(SOGLIA_TIT) + "% nelle probabili formazioni, ordinati per fantamedia FantaTB.",
           "numberOfItems": len(items), "itemListOrder": "https://schema.org/ItemListOrderDescending", "itemListElement": items}]
    return page("Chi schierare nella giornata " + str(md) + " di Serie A",
                "Giornata " + str(md) + " di Serie A " + SEASON + ": " + str(n_picks) + " titolari probabili per fantamedia FantaTB con l'avversario, "
                + str(n_out) + " indisponibili da evitare e i ballottaggi in dubbio.",
                canon, "".join(b), crumbs=FANTA_CRUMB + [("Chi schierare", canon)], ld=ld, here="Fantacalcio", extra_head=EXTRA_CSS, bar=FANTA_BAR, bar_here="")

def _consigli_vuoti(D, T, canon, oggi):
    """Senza probabili formazioni: la pagina spiega quando arrivano i consigli e come sono costruiti (mai una pagina vuota)."""
    tit = D.get("titolari") or {}
    md = (tit.get("matchday") or 0)
    n_tit = len(tit.get("status") or [])
    b = ["<h1>Chi schierare nel fantacalcio: i consigli di TransferBeat giornata per giornata</h1>",
         '<p class="sub">I consigli per la prossima giornata di Serie A ' + SEASON + " arrivano insieme alle probabili formazioni di TransferBeat, che vengono pubblicate nella settimana "
         "della giornata e ricalcolate fino al giorno di gara; al " + esc(oggi) + " le probabili non sono ancora disponibili" + ((", mentre l'indice di titolarità copre già " + str(n_tit) + " giocatori per la giornata " + str(md)) if n_tit else "") + ".</p>",
         '<h2>Come nascono i consigli</h2><p>Questa pagina è generata dai dati, non da una redazione. Per ogni ruolo elenca fino a ' + str(N_MAX) + ' giocatori che nelle probabili formazioni hanno almeno il ' +
         str(SOGLIA_TIT) + '% di probabilità di partire titolare, ordinati per fantamedia FantaTB della stagione (voto statistico più bonus e malus), con l\'avversario di giornata e il link alla scheda; '
         'poi la sezione da evitare con infortunati, squalificati e ballottaggi aperti. Le probabili si basano sulle ultime tre formazioni ufficiali di ogni squadra e sull\'indice di titolarità, '
         'e vengono ricalcolate più volte a settimana.</p>'
         '<h2>Cosa consultare intanto</h2><div class="grid2">'
         '<div class="card"><h3>Infortunati e squalificati</h3><div class="in"><p>Indice di titolarità di ogni giocatore, infortuni con rientro stimato e squalifiche per la prossima giornata.</p><a class="btn" href="/fantacalcio/titolari.html">Chi gioca e chi no</a></div></div>'
         '<div class="card"><h3>Voti e fantamedie</h3><div class="in"><p>Voto, bonus e fantavoto di ogni giornata giocata, con la formula pubblica del voto statistico.</p><a class="btn" href="/fantacalcio/">Voti e listone</a></div></div>'
         '<div class="card"><h3>Schede giocatore</h3><div class="in"><p>Fantamedia, media voto, titolarità e statistiche della stagione scorsa per ogni giocatore di Serie A.</p><a class="btn" href="/giocatori/">Tutti i giocatori</a></div></div>'
         '<div class="card"><h3>Regolamento e guida all\'asta</h3><div class="in"><p>Come si calcola il voto FantaTB, i modificatori, la panchina; e la guida per l\'asta.</p><a class="btn" href="/fantacalcio/regolamento.html">Regolamento</a> <a class="btn sec" href="/fantacalcio/guida-asta.html">Guida all\'asta</a></div></div></div>'
         '<h2>Come leggere i consigli quando arrivano</h2><ul class="plain"><li>La percentuale di titolarità è la probabilità che il giocatore parta dall\'inizio: verde da 70 in su, ambra fra 40 e 69, rossa sotto 40.</li>'
         '<li>La fantamedia è la media dei fantavoti FantaTB della stagione; con poche giornate giocate pesa meno della titolarità.</li>'
         '<li>Un giocatore consigliato con un avversario forte resta consigliato: il voto statistico premia chi partecipa al gioco, non solo chi segna.</li>'
         '<li>Metti sempre dietro a un titolare in dubbio un panchinaro affidabile dello stesso ruolo: le sostituzioni automatiche fanno il resto.</li></ul>']
    ld = [{"@context": "https://schema.org", "@type": "WebPage", "name": "Chi schierare nel fantacalcio", "url": canon, "inLanguage": "it", "dateModified": today_iso(), "publisher": ORG}]
    return page("Chi schierare nel fantacalcio: consigli dai dati",
                "I consigli di TransferBeat per la prossima giornata di Serie A " + SEASON + ": titolari probabili ordinati per fantamedia FantaTB, infortunati e squalificati da evitare. "
                "Arrivano con le probabili formazioni.",
                canon, "".join(b), crumbs=FANTA_CRUMB + [("Chi schierare", canon)], ld=ld, here="Fantacalcio", extra_head=EXTRA_CSS, bar=FANTA_BAR, bar_here="")

# =====================================================================================================================
def render_all(D, T):
    """Contratto con render_site: lista di (rel_file, url, html) per le tre pagine."""
    return [("fantacalcio/regolamento.html", "/fantacalcio/regolamento.html", render_regolamento(D, T)),
            ("fantacalcio/guida-asta.html", "/fantacalcio/guida-asta.html", render_guida(D, T)),
            ("fantacalcio/consigli.html", "/fantacalcio/consigli.html", render_consigli(D, T))]
