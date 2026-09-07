#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - rosters.py: scarica le rose attuali (football-data.org) e le salva
in data/rosters.json (club -> giocatori). Una chiamata per competizione (CODES, con 7
secondi di pausa fra l'una e l'altra); su piano free ne risponde solo una parte, e i club
delle competizioni mute NON spariscono: si ereditano dallo snapshot precedente."""
import json, os, sys, time, unicodedata, calendar
try:
    import requests
except ImportError:
    print("manca requests"); sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
# "CL" tolto: da quando e' iniziata la stagione le squadre della Champions tornano con lo squad
# vuoto, quindi la chiamata bruciava quota e 7 secondi di sleep per zero giocatori.
CODES = ["SA", "PD", "PL", "FL1", "BL1", "DED", "PPL", "ELC"]
ALIAS = {"Atleti": "Atlético Madrid", "Barça": "Barcelona", "Athletic": "Athletic Club",
         "Celta": "Celta Vigo", "Sevilla FC": "Sevilla", "Brighton Hove": "Brighton",
         "Leeds United": "Leeds", "Nottingham": "Nottingham Forest", "Wolverhampton": "Wolves"}

# Soglie del controllo anti-scarico-monco. Sono rapporti sul file precedente e sul massimo
# storico, non valori assoluti, perche' quante competizioni rispondano dipende dal piano.
GIORNI_FRESCHEZZA = float(os.environ.get("ROSTERS_GIORNI", "5"))
RITENTA_ORE = float(os.environ.get("ROSTERS_RITENTA_ORE", "12"))
MIN_CLUB = float(os.environ.get("ROSTERS_MIN_CLUB", "0.8"))
MIN_GIOCATORI = float(os.environ.get("ROSTERS_MIN_GIOCATORI", "0.9"))
MIN_MASSIMI = float(os.environ.get("ROSTERS_MIN_MASSIMI", "0.75"))
# sotto questa quota il calo si accetta ma si SEGNALA: e' il gradino fra "tutto bene" e "rifiuto"
AVVISO_GIOCATORI = float(os.environ.get("ROSTERS_AVVISO_GIOCATORI", "0.97"))

def get_key():
    k = os.environ.get("FOOTBALL_DATA_KEY", "").strip()
    if k:
        return k
    try:
        return open(os.path.join(ROOT, "football_data_key.txt")).read().strip()
    except Exception:
        return ""

def deac(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii").lower().strip()

def board_names():
    try:
        b = json.load(open(os.path.join(DATA, "it", "board.json"), encoding="utf-8"))
        return set(b.get("squadre", {}).keys())
    except Exception:
        return set()

def resolve(team, BN):
    sn = team.get("shortName") or team.get("name") or ""
    if sn in BN:
        return sn
    if sn in ALIAS:
        return ALIAS[sn]
    d = deac(sn)
    for bn in BN:
        if d and (d in deac(bn) or deac(bn) in d):
            return bn
    return sn

def fetch(code, key):
    r = requests.get("https://api.football-data.org/v4/competitions/%s/teams" % code,
                     headers={"X-Auth-Token": key}, timeout=30)
    r.raise_for_status()
    return r.json().get("teams", [])

def _path():
    return os.path.join(DATA, "rosters.json")

def _leggi_prec():
    """Lo snapshot precedente e il suo stato: 'ok' | 'assente' | 'illeggibile'.
    I tre casi vanno distinti: prima qualsiasi eccezione tornava {} e il confronto col
    file precedente si SALTAVA, cioe' il controllo si spegneva proprio quando serviva."""
    p = _path()
    if not os.path.exists(p):
        return {}, "assente"
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print("  ATTENZIONE: rosters.json precedente illeggibile (%s)" % str(e)[:60])
        return {}, "illeggibile"
    return (d, "ok") if isinstance(d, dict) else ({}, "illeggibile")

def _eta_ore(ts):
    """Ore trascorse da un timestamp '%Y-%m-%dT%H:%M:%SZ', o None se assente/illeggibile."""
    try:
        return (time.time() - calendar.timegm(time.strptime(ts or "", "%Y-%m-%dT%H:%M:%SZ"))) / 3600.0
    except Exception:
        return None

def _scrivi(out):
    """Scrittura ATOMICA. Il json.dump su open(path,"w") troncava il file in place: un run
    interrotto a meta' lasciava un rosters.json illeggibile che al giro dopo spegneva sia il
    controllo di freschezza sia il confronto col precedente. Il temporaneo sta nella stessa
    cartella perche' os.replace e' atomico solo sullo stesso volume."""
    p = _path(); tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise

def _totali(rose):
    return len(rose), sum(len(v or []) for v in rose.values())

def main():
    key = get_key()
    if not key:
        print("nessuna chiave football-data (FOOTBALL_DATA_KEY o football_data_key.txt) - salto")
        return
    prev, stato_prec = _leggi_prec()
    if not os.environ.get("FORCE_ROSTERS"):
        eta = _eta_ore(prev.get("updated"))
        if eta is not None and eta < GIORNI_FRESCHEZZA * 24:
            print("rose ancora fresche (<%.0f giorni) - salto refresh" % GIORNI_FRESCHEZZA); return
        # se il giro precedente e' stato rifiutato, "updated" resta vecchia apposta: senza questa
        # pausa lo script ritenterebbe 8 chiamate a ogni run del workflow (ogni 2 ore) bruciando quota
        eta_b = _eta_ore((prev.get("blocco") or {}).get("quando"))
        if eta_b is not None and eta_b < RITENTA_ORE:
            print("ultimo giro rifiutato %.1f ore fa - ritento fra %.0f ore" % (eta_b, RITENTA_ORE - eta_b))
            return
    BN = board_names()
    rose = {}; ids = {}; unresolved = []; ok = []; ko = []; senza_dati = []; collisioni = []
    vuoti = set()      # club tornati dall'API con lo squad vuoto: guasto dell'API, non club senza rosa
    fonti = {}         # club -> competizione che l'ha portato (serve al giro dopo per sapere cosa ereditare)
    per_comp = {}
    for i, code in enumerate(CODES):
        if i:
            time.sleep(7)
        try:
            teams = fetch(code, key)
        except Exception as e:
            print("  errore", code, str(e)[:80]); ko.append(code); continue
        con_giocatori = 0
        for t in teams:
            club = resolve(t, BN)
            if club not in BN:
                unresolved.append(t.get("shortName"))
            # nomi e id vanno riempiti insieme: "ids" e' parallelo a "rose" (stesso indice,
            # stesso giocatore) perche' i consumatori pretendono che "rose" resti lista di stringhe
            sq = []; sq_id = []
            for p in t.get("squad", []) or []:
                if not p.get("name"):
                    continue
                sq.append(p["name"]); sq_id.append(p.get("id"))
            if not sq:
                # squad vuoto = l'API ha risposto ma non ha dato la rosa (e' successo per mesi con
                # la Champions: 36 club, 0 giocatori). Il club resta "da ereditare", non "sparito".
                vuoti.add(club); fonti.setdefault(club, code)
                continue
            # due squadre diverse possono cadere sullo stesso nome di board (resolve() matcha per
            # sottostringa): vince l'ultima come prima, ma la collisione va lasciata nei dati
            # perche' e' sempre una mappatura sbagliata, non un doppione vero
            if club in rose:
                collisioni.append("%s -> %s" % (t.get("shortName") or t.get("name") or "", club))
            rose[club] = sq; ids[club] = sq_id; fonti[club] = code; con_giocatori += 1
        per_comp[code] = con_giocatori
        # l'esito HTTP non basta: una competizione che risponde 200 con tutte le rose vuote non ha
        # portato NIENTE, e contarla fra le riuscite fa sparire i suoi club dal file
        (ok if con_giocatori else senza_dati).append(code)
        print("  %s: %d club con giocatori su %d tornati" % (code, con_giocatori, len(teams)))

    # --- fusione con lo snapshot precedente: non si sostituisce, si FONDE ---
    prev_rose = prev.get("rose") or {}
    prev_ids = prev.get("ids") or {}
    prev_fonti = prev.get("fonti") or {}
    prev_ered = prev.get("ereditati") or {}
    ora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    portano_dati = set(ok)
    ereditati = {}
    for club, sq in prev_rose.items():
        if club in rose or not sq:
            continue
        fonte = prev_fonti.get(club)
        # un club si lascia cadere SOLO se la sua competizione ha portato dati in questo giro e lui
        # non c'e' piu': allora e' un cambio vero (promozione/retrocessione). In ogni altro caso
        # (competizione caduta, muta, o sconosciuta perche' il file vecchio non aveva "fonti", o
        # club tornato con la rosa vuota) si eredita la rosa vecchia: una rosa di qualche giorno fa
        # vale infinitamente piu' di una rosa assente, perche' l'assenza avvelena in silenzio
        # build.roster_club() e brain.is_coach() senza che nessuno se ne accorga.
        if club not in vuoti and fonte in portano_dati:
            continue
        rose[club] = sq
        if prev_ids.get(club):
            ids[club] = prev_ids[club]
        if fonte:
            fonti.setdefault(club, fonte)
        # la data e' quella del dato, non di oggi: se era gia' ereditato si porta avanti l'originale
        ereditati[club] = prev_ered.get(club) or prev.get("updated") or ora

    if not rose:
        print("nessuna rosa scaricata e niente da ereditare - non sovrascrivo"); return

    n_club, n_gio = _totali(rose)
    p_club, p_gio = _totali(prev_rose)
    mx = prev.get("massimi") or {}
    # riferimento stabile: il massimo mai visto, non solo l'ultimo file. Col solo ultimo file cali
    # ripetuti sotto soglia erodono il dataset senza mai farla scattare (storico: 165, 119, 105, 81, 66, 36)
    max_club = max(int(mx.get("club") or 0), p_club)
    max_gio = max(int(mx.get("giocatori") or 0), p_gio)
    motivi = []
    if p_club and n_club < p_club * MIN_CLUB:
        motivi.append("%d club contro %d del file precedente" % (n_club, p_club))
    if p_gio and n_gio < p_gio * MIN_GIOCATORI:
        motivi.append("%d giocatori contro %d del file precedente" % (n_gio, p_gio))
    if max_club and n_club < max_club * MIN_MASSIMI:
        motivi.append("%d club contro il massimo storico di %d" % (n_club, max_club))
    if max_gio and n_gio < max_gio * MIN_MASSIMI:
        motivi.append("%d giocatori contro il massimo storico di %d" % (n_gio, max_gio))

    if motivi and not os.environ.get("ROSTERS_FORCE_WRITE"):
        print("scarico monco: " + "; ".join(motivi) + " - NON aggiorno le rose")
        print("  competizioni ok:", ok, "- senza dati:", senza_dati, "- fallite:", ko)
        print("  (per forzare comunque la scrittura: ROSTERS_FORCE_WRITE=1)")
        # il rifiuto va lasciato NEL file, non solo nel log: freshness.py lo legge e colora di rosso
        # il workflow. "updated" resta quella vecchia apposta, cosi' le rose continuano a invecchiare
        # in modo visibile invece di sembrare aggiornate; "rose" non viene toccata.
        if stato_prec == "ok":
            prev["ultimo_tentativo"] = ora
            prev["blocco"] = {"quando": ora, "motivo": "; ".join(motivi),
                              "club": n_club, "giocatori": n_gio,
                              "competizioni": {"ok": ok, "senza_dati": senza_dati, "ko": ko}}
            _scrivi(prev)
        return

    # NIENTE DATI NUOVI = RIFIUTO, non successo. Da quando le rose dei club falliti si ereditano dallo
    # snapshot precedente, `rose` non e' mai vuota: la guardia `if not rose` non scatta piu' e un giro in cui
    # football-data non ha risposto per NESSUNA competizione arriverebbe qui, riscrivendo "updated" con la data
    # di oggi su dati vecchi al 100% - e cancellando anche l'eventuale "blocco" di un rifiuto precedente.
    # Il workflow resterebbe verde e il sito pubblicherebbe una data falsa: e' il guasto silenzioso che questo
    # script deve impedire, non produrre. Un giro a zero dati lascia il file com'e' e si fa vedere.
    if not ok and not os.environ.get("ROSTERS_FORCE_WRITE"):
        print("nessuna competizione ha portato giocatori (ok vuoto) - NON aggiorno le rose ne' la data")
        print("  senza dati:", senza_dati or "(nessuna)", "- fallite:", ko or "(nessuna)")
        if stato_prec == "ok":
            prev["ultimo_tentativo"] = ora
            # un blocco gia' presente NON si cancella: il guasto precedente non e' stato risolto da questo giro
            b = dict(prev.get("blocco") or {})
            b.update({"quando": b.get("quando") or ora, "ultimo": ora,
                      "motivo": "nessuna competizione ha portato giocatori" + (("; " + b["motivo"]) if b.get("motivo") else ""),
                      "club": n_club, "giocatori": n_gio,
                      "competizioni": {"ok": ok, "senza_dati": senza_dati, "ko": ko}})
            prev["blocco"] = b
            _scrivi(prev)
        return

    avvisi = []
    # gradino intermedio: un calo accettato ma anomalo deve comunque lasciare traccia, altrimenti l'erosione
    # lenta (ogni giro un po' sotto la soglia di rifiuto) arriva al cricchetto senza che nessuno se ne accorga.
    if p_gio and n_gio < p_gio * AVVISO_GIOCATORI:
        avvisi.append("giocatori scesi da %d a %d (-%.0f%%) senza superare la soglia di rifiuto"
                      % (p_gio, n_gio, 100.0 * (p_gio - n_gio) / p_gio))
    if p_club and n_club < p_club:
        avvisi.append("club scesi da %d a %d" % (p_club, n_club))
    if stato_prec == "illeggibile":
        avvisi.append("il rosters.json precedente era illeggibile: niente da ereditare e nessun confronto possibile")
    if motivi:
        avvisi.append("scrittura forzata (ROSTERS_FORCE_WRITE) nonostante: " + "; ".join(motivi))
    nuovo_massimo = n_club > max_club or n_gio > max_gio
    out = {"updated": ora, "ultimo_tentativo": ora,
           "competizioni": {"ok": ok, "senza_dati": senza_dati, "ko": ko,
                            "parziale": bool(ko or senza_dati), "club_con_giocatori": per_comp},
           "totali": {"club": n_club, "giocatori": n_gio},
           "massimi": {"club": max(max_club, n_club), "giocatori": max(max_gio, n_gio),
                       "il": ora if nuovo_massimo else (mx.get("il") or ora)},
           "avvisi": avvisi, "collisioni": collisioni,
           "ereditati": ereditati, "fonti": fonti, "rose": rose, "ids": ids}
    _scrivi(out)
    print("rose:", n_club, "club,", n_gio, "giocatori (di cui", len(ereditati), "club ereditati dal giro precedente)")
    print("  competizioni ok:", len(ok), ok, "- senza dati:", senza_dati or "(nessuna)", "- fallite:", ko or "(nessuna)")
    if senza_dati:
        print("  ATTENZIONE: hanno risposto senza portare un solo giocatore:", senza_dati)
    if ereditati:
        piu_vecchia = min(ereditati.values())
        print("  club ereditati:", len(ereditati), "- il dato piu' vecchio e' del", piu_vecchia)
    for a in avvisi:
        print("  AVVISO:", a)
    if collisioni:
        print("COLLISIONI (una squadra ha sovrascritto l'altra):", collisioni)
    if unresolved:
        print("NON risolti:", unresolved)

if __name__ == "__main__":
    main()
