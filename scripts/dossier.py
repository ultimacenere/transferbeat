#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dossier.py - prepara i NUMERI per i sei formati fanta di TransferBeat.

Perche' esiste: la prosa la scrive Cowork, ma i conti no. Ogni volta che chi scrive
deve dividere minuti per 90 o confrontare due stagioni a occhio, nasce un numero
sbagliato in un pezzo pubblicato. Qui i conti sono fatti una volta sola, in modo
deterministico, e finiscono in un .md gia' arrotondato e gia' etichettato in italiano.

Uso:
    py -X utf8 scripts/dossier.py <formato> [--data AAAA-MM-GG] [--dry] [--out CARTELLA]

Formati: giocatore | cartello | migliori | confronto | rigoristi | sorprese

Regola di fondo: se un dato manca, si scrive "non disponibile". Mai uno zero al posto
di un buco, mai una stima. Se manca il presupposto stesso del pezzo (per esempio non
c'e' una giornata chiusa per "migliori") lo script esce senza scrivere e lo dice.
"""

import argparse
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERIE_A = 135          # id API-Football della Serie A
COPPA_ITALIA = 137     # coppa nazionale: i rigori battuti qui contano per il rigorista
# Nei dati di origine le amichevoli ripetono i numeri di altre competizioni (per esempio
# "Friendlies Clubs" riporta gli stessi minuti del Mondiale per club): sommarle
# raddoppierebbe i totali. Restano visibili nell'elenco, ma fuori dalle somme.
LEGHE_AMICHEVOLI = (667, 10)
ND = "non disponibile"
POCHI = "campione troppo piccolo"

# Soglie di default. Sono parametri perche' a inizio stagione i minuti sono pochi:
# una soglia unica renderebbe muto tutto il blocco "per 90" della stagione in corso.
MIN_MIN_PREV = 450     # 5 partite piene: sotto, i "per 90" della stagione scorsa sono rumore
MIN_MIN_CUR = 180      # 2 partite piene: sotto, i "per 90" della stagione in corso sono rumore

RUOLI = {"P": "portiere", "D": "difensore", "C": "centrocampista", "A": "attaccante"}
RUOLI_PL = {"P": "portieri", "D": "difensori", "C": "centrocampisti", "A": "attaccanti"}

# I nomi delle squadre arrivano da due anagrafiche diverse (API-Football per stats e
# listone, football-data per competizioni.json). Normalizzo togliendo le sigle e gli
# anni sociali; l'unico caso che il taglio non risolve e' l'Inter, che sta qui sotto.
_RUMORE = {"fc", "ac", "as", "ss", "ssc", "us", "acf", "cfc", "bc", "sc", "asd",
           "calcio", "1907", "1909", "1913", "1919", "spa", "srl"}
_ALIAS = {"fc internazionale milano": "inter", "internazionale": "inter",
          "inter milan": "inter", "hellas verona fc": "verona", "hellas verona": "verona"}


class DatiMancanti(Exception):
    """Il dossier non si puo' produrre: manca un presupposto, non un dettaglio."""


def _senza_accenti(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm_team(nome):
    """Chiave di confronto fra le due anagrafiche di squadra."""
    if not nome:
        return ""
    grezzo = _senza_accenti(str(nome)).lower().strip()
    if grezzo in _ALIAS:
        return _ALIAS[grezzo]
    pulito = "".join(c if c.isalnum() or c.isspace() else " " for c in grezzo)
    tok = [t for t in pulito.split() if t not in _RUMORE]
    return " ".join(tok) if tok else grezzo.replace(" ", "")


def carica(rel):
    """Legge un JSON del repo. Se non c'e', e' un errore rumoroso: non si tira avanti."""
    percorso = os.path.join(ROOT, rel)
    if not os.path.exists(percorso):
        raise DatiMancanti("manca il file %s" % rel)
    with open(percorso, "r", encoding="utf-8") as f:
        return json.load(f)


def esiste(rel):
    return os.path.exists(os.path.join(ROOT, rel))


# ---------------------------------------------------------------- numeri e formato

def arr(v, dec=2):
    """Arrotonda tenendo il None come None: un buco non diventa uno zero."""
    if v is None:
        return None
    try:
        x = round(float(v), dec)
    except (TypeError, ValueError):
        return None
    return int(x) if dec == 0 else x


def fmt(v, dec=2, unita=""):
    """Il numero come deve comparire nel .md: gia' arrotondato, con l'unita'."""
    if v is None:
        return ND
    if v is POCHI or v == POCHI:
        return POCHI
    if isinstance(v, str):
        return v
    x = arr(v, dec)
    if x is None:
        return ND
    testo = ("%d" % x) if dec == 0 else (("%." + str(dec) + "f") % x)
    return testo + (" " + unita if unita else "")


def fmt_media_partite(st, chiave, dec=2, unita=""):
    """
    Una media a partita con accanto il campione VERO di quella metrica.
    Le partite con un blocco stats non sono il denominatore: se in qualcuna il campo era
    a null, la media e' calcolata su meno partite. Chi scrive il pezzo copia il numero E
    il denominatore, quindi il denominatore deve essere quello della metrica, non quello
    della riga accanto.
    """
    st = st or {}
    valore = st.get(chiave)
    if valore is None:
        return ND
    n = st.get("n_" + chiave) or 0
    tot = st.get("partite_con_statistiche") or 0
    if n < tot:
        return "%s (su %d partite delle %d con statistiche)" % (fmt(valore, dec, unita), n, tot)
    return "%s (su %d partite)" % (fmt(valore, dec, unita), n)


def somma(valori):
    """Somma ignorando i None, ma se sono TUTTI None restituisce None (dato assente)."""
    presenti = [v for v in valori if v is not None]
    if not presenti:
        return None
    return sum(presenti)


def per90(valore, minuti, soglia):
    """Valore ogni 90 minuti. Sotto la soglia di minuti non e' un numero, e' rumore."""
    if minuti is None or valore is None:
        return None
    if minuti < soglia:
        return POCHI
    if minuti == 0:
        return None
    return valore * 90.0 / minuti


def variazione(prima, dopo):
    """(differenza assoluta, differenza percentuale). La percentuale non esiste se si parte da 0."""
    if prima is None or dopo is None or prima is POCHI or dopo is POCHI:
        return None, None
    if isinstance(prima, str) or isinstance(dopo, str):
        return None, None
    diff = dopo - prima
    if prima == 0:
        return diff, None
    return diff, diff / abs(prima) * 100.0


def fmt_var(diff, pct, dec=2):
    if diff is None:
        return ND
    segno = "+" if diff >= 0 else ""
    testo = segno + (("%." + str(dec) + "f") % round(diff, dec))
    if pct is None:
        return testo + " (variazione percentuale non calcolabile: si parte da zero)"
    sp = "+" if pct >= 0 else ""
    return "%s (%s%.1f%%)" % (testo, sp, pct)


def percentile(valore, popolazione):
    """
    Percentuale di pari ruolo con un valore MINORE O UGUALE al suo (rank inclusivo).
    Dichiarato nel .md perche' esistono altri modi di calcolarlo e danno numeri diversi.
    """
    if valore is None or isinstance(valore, str):
        return None
    pop = [v for v in popolazione if v is not None and not isinstance(v, str)]
    if len(pop) < 5:
        return None
    sotto = sum(1 for v in pop if v <= valore)
    return sotto * 100.0 / len(pop)


# ---------------------------------------------------------------- caricamento dati

class Dati(object):
    """Tutti i file del repo che servono, letti una volta sola."""

    def __init__(self):
        self.listone = carica("data/fanta/listone.json")
        self.schede = carica("data/fanta/schede.json")
        self.stats_players = carica("data/stats/players.json")
        self.stats_teams = carica("data/stats/teams.json")
        self.matches = carica("data/stats/matches.json")
        self.competizioni = carica("data/competizioni.json")

        self.giocatori = {p["id"]: p for p in self.listone["players"]}
        self.per_prezzo = sorted(self.listone["players"], key=lambda p: (-p["price"], p["name"]))
        self.sch = self.schede["players"]
        self.stp = self.stats_players["players"]
        self.squadre = self.stats_teams["teams"]

        # nome squadra -> blocco statistiche (il listone usa i nomi API-Football)
        self.squadra_per_nome = {}
        self.squadra_per_id = {}
        for v in self.squadre.values():
            self.squadra_per_nome[norm_team(v.get("name"))] = v
            self.squadra_per_id[v.get("id")] = v

        self.rigori_squadra_affidabili, self.rigori_squadra_nota = self._rigori_lega_affidabili()

        self.classifica = self._classifica_serie_a()
        self.giornate_voti = self._giornate_voti()
        self.probabili, self.giornata_prossima = self._probabili_piu_recenti()
        self.titolari = self._titolari(self.giornata_prossima)

    # -- affidabilita' di un campo di squadra -----------------------------------

    @staticmethod
    def _lega_di(squadra):
        lg = squadra.get("league")
        return lg.get("id") if isinstance(lg, dict) else lg

    def _rigori_lega_affidabili(self, lega=SERIE_A):
        """
        Il campo penalty di teams.json e' un dato solo se qualcuno nella lega ha un rigore.
        Tutte le squadre di un campionato a 0 su 0 dopo decine di partite giocate non e' un
        fatto della stagione: e' il sintomo di un campo che la fonte non ha popolato. Uno
        zero cosi', pubblicato, sarebbe un'affermazione falsa su tutte le squadre insieme.
        Quindi lo riconosco qui una volta sola e chi stampa scrive "non disponibile".
        """
        squadre = [v for v in self.squadre.values() if self._lega_di(v) == lega]
        if not squadre:
            return True, None
        partite = sum(((v.get("fixtures") or {}).get("played") or {}).get("total") or 0
                      for v in squadre)
        battuti = sum((v.get("penalty") or {}).get("total") or 0 for v in squadre)
        if battuti or not partite:
            return True, None
        # Se anche le altre leghe del file sono tutte a zero il buco e' del campo in
        # generale; se invece altrove i rigori ci sono, l'anomalia e' di questa lega.
        altrove = sum((v.get("penalty") or {}).get("total") or 0
                      for v in self.squadre.values() if self._lega_di(v) != lega)
        confronto = ("mentre nello stesso file le altre leghe ne registrano %d" % altrove) \
            if altrove else "e nello stesso file nessuna squadra di nessuna lega ne ha uno"
        return False, {
            # La breve va accanto a ogni squadra: ripetuta venti volte deve restare corta,
            # ma da sola deve gia' impedire di copiare lo zero.
            "breve": "in data/stats/teams.json tutte le %d squadre della lega sono a 0 su 0: "
                     "campo non popolato, non uno zero vero" % len(squadre),
            "lunga": "In data/stats/teams.json tutte le %d squadre della lega risultano 0 "
                     "rigori su 0 dopo %d partite giocate, %s. Uno zero uniforme di lega e' un "
                     "campo che la fonte non ha popolato, non un fatto della stagione"
                     % (len(squadre), partite, confronto)}

    def testo_rigori_squadra(self, sq):
        """I rigori di squadra come devono comparire: un numero solo se sono un dato."""
        if not self.rigori_squadra_affidabili:
            return "%s (%s; non usarlo nel pezzo)" % (ND, self.rigori_squadra_nota["breve"])
        pen = (sq.get("penalty") or {}) if sq else {}
        return "%s segnati su %s battuti" % (fmt(pen.get("scored"), 0), fmt(pen.get("total"), 0))

    # -- classifica ------------------------------------------------------------

    def _classifica_serie_a(self):
        blocchi = [c for c in self.competizioni.get("competizioni", []) if c.get("code") == "SA"]
        if not blocchi:
            return {}
        tabelle = blocchi[0].get("classifica") or []
        righe = []
        for t in tabelle:
            righe.extend(t.get("table") or [])
        fuori = {}
        for r in righe:
            chiave = norm_team((r.get("team") or {}).get("name"))
            if chiave:
                fuori[chiave] = r
        return fuori

    def riga_classifica(self, nome_squadra):
        """None se il nome non si aggancia: chi stampa deve scrivere 'non disponibile'."""
        return self.classifica.get(norm_team(nome_squadra))

    # -- giornate --------------------------------------------------------------

    def _giornate_voti(self):
        """{numero giornata: contenuto voti-NN.json} per tutti i file presenti."""
        fuori = {}
        cartella = os.path.join(ROOT, "data", "fanta")
        if not os.path.isdir(cartella):
            return fuori
        for nome in sorted(os.listdir(cartella)):
            if nome.startswith("voti-") and nome.endswith(".json"):
                try:
                    n = int(nome[5:-5])
                except ValueError:
                    continue
                fuori[n] = carica("data/fanta/voti-%s.json" % nome[5:-5])
        return fuori

    def giornate_chiuse(self):
        """Giornate con tutte le partite rilevate: le uniche su cui si puo' scrivere."""
        fuori = []
        for n, d in sorted(self.giornate_voti.items()):
            tot, fin = d.get("total"), d.get("finished")
            if d.get("status") != "live" and tot and fin == tot:
                fuori.append(n)
        return fuori

    def _probabili_piu_recenti(self):
        cartella = os.path.join(ROOT, "data", "fanta")
        numeri = []
        if os.path.isdir(cartella):
            for nome in os.listdir(cartella):
                if nome.startswith("probabili-") and nome.endswith(".json"):
                    try:
                        numeri.append(int(nome[10:-5]))
                    except ValueError:
                        pass
        if not numeri:
            return None, None
        n = max(numeri)
        return carica("data/fanta/probabili-%02d.json" % n), n

    def _titolari(self, giornata):
        if giornata is None or not esiste("data/fanta/titolari-%02d.json" % giornata):
            return None
        d = carica("data/fanta/titolari-%02d.json" % giornata)
        return {r["player_id"]: r for r in d.get("status", [])}

    # -- statistiche di squadra dalle singole partite ---------------------------

    def stat_partite_squadra(self, team_id):
        """
        Medie a partita ricavate dalle partite con statistiche in data/stats/matches.json.
        Sono le uniche che contengono l'xG, e l'xG e' della SQUADRA, mai del giocatore.

        Il campione va contato PER METRICA, non per partita: una partita puo' avere il
        blocco stats con dentro un campo a null (succede con l'xG delle giornate appena
        chiuse). La media scarta quei null, quindi il denominatore vero e' piu' piccolo
        del numero di partite, e stampare il numero di partite accanto alla media
        pubblicherebbe un denominatore falso. Per ogni metrica esce anche "n_<metrica>".
        """
        n = 0
        acc = {"xg": [], "xg_contro": [], "possesso": [], "tiri": [], "tiri_in_porta": [],
               "corner": [], "passaggi_pct": [], "parate": []}
        for f in (self.matches.get("fixtures") or {}).values():
            if f.get("home") != team_id and f.get("away") != team_id:
                continue
            st = f.get("stats") or {}
            mio = st.get(str(team_id))
            altro_id = f["away"] if f.get("home") == team_id else f["home"]
            suo = st.get(str(altro_id))
            if not mio:
                continue
            n += 1
            acc["xg"].append(mio.get("xg"))
            acc["xg_contro"].append((suo or {}).get("xg"))
            acc["possesso"].append(mio.get("possession"))
            acc["tiri"].append(mio.get("shots"))
            acc["tiri_in_porta"].append(mio.get("shots_on"))
            acc["corner"].append(mio.get("corners"))
            acc["passaggi_pct"].append(mio.get("passes_pct"))
            acc["parate"].append(mio.get("saves"))
        fuori = {"partite_con_statistiche": n}
        for k, v in acc.items():
            buoni = [x for x in v if x is not None]
            fuori[k] = (sum(buoni) / len(buoni)) if buoni else None
            fuori["n_" + k] = len(buoni)
        return fuori

    # -- prossimo impegno ------------------------------------------------------

    def prossimo_impegno(self, team_id):
        """Prima partita della giornata in arrivo che riguarda questa squadra."""
        if not self.probabili:
            return None
        for f in self.probabili.get("fixtures", []):
            if f.get("home_id") == team_id or f.get("away_id") == team_id:
                in_casa = f.get("home_id") == team_id
                avv_id = f.get("away_id") if in_casa else f.get("home_id")
                return {"giornata": self.probabili.get("matchday"), "data": f.get("date"),
                        "in_casa": in_casa, "casa": f.get("home"), "trasferta": f.get("away"),
                        "avversario": f.get("away") if in_casa else f.get("home"),
                        "avversario_id": avv_id, "stadio": f.get("venue"), "fixture": f.get("id")}
        return None


# ---------------------------------------------------------------- stats giocatore

def blocchi_lega(blocchi, lega):
    return [b for b in (blocchi or []) if (b.get("league") or {}).get("id") == lega]


def _somme(blocchi):
    """Solo i totali di un insieme di blocchi. Le medie (rating, percentuali) stanno fuori."""

    def g(sez, campo):
        return somma([(b.get(sez) or {}).get(campo) for b in blocchi])

    return {
        "presenze": g("games", "appearences"),
        "da_titolare": g("games", "lineups"),
        "minuti": g("games", "minutes"),
        "gol": g("goals", "total"),
        "assist": g("goals", "assists"),
        "gol_subiti": g("goals", "conceded"),
        "parate": g("goals", "saves"),
        "tiri": g("shots", "total"),
        "tiri_in_porta": g("shots", "on"),
        "passaggi": g("passes", "total"),
        "passaggi_chiave": g("passes", "key"),
        "contrasti": g("tackles", "total"),
        "intercetti": g("tackles", "interceptions"),
        "duelli": g("duels", "total"),
        "duelli_vinti": g("duels", "won"),
        "dribbling_tentati": g("dribbles", "attempts"),
        "dribbling_riusciti": g("dribbles", "success"),
        "falli_subiti": g("fouls", "drawn"),
        "falli_fatti": g("fouls", "committed"),
        "gialli": g("cards", "yellow"),
        "doppi_gialli": g("cards", "yellowred"),
        "rossi": g("cards", "red"),
        "rig_segnati": g("penalty", "scored"),
        "rig_sbagliati": g("penalty", "missed"),
        "rig_conquistati": g("penalty", "won"),
        "rig_causati": g("penalty", "commited"),
        "rig_parati": g("penalty", "saved"),
    }


def aggrega(blocchi):
    """
    Somma i blocchi per competizione di una stagione.
    Il rating e' una media pesata sulle presenze: sommarlo non avrebbe senso.

    Oltre ai totali di stagione prepara "p90_base": gli STESSI totali calcolati sui soli
    blocchi che hanno i minuti. Serve perche' somma() ignora i None nei minuti ma non nei
    gol: un blocco con minuti a null (Supercoppe e Intercontinentale nei dati di origine)
    non entra nel denominatore, quindi i suoi gol non possono restare al numeratore, o la
    media per 90 esce gonfiata. Fra le due strade possibili - escludere quei gol oppure
    rinunciare del tutto alla media - scelgo di escluderli: la media resta calcolabile
    sulla parte di stagione che sappiamo misurare, e "p90_esclusi" dice cosa e' rimasto
    fuori, cosi' chi scrive il pezzo vede la differenza invece di subirla.
    """
    if not blocchi:
        return None

    presenze_rating = [(b["games"].get("rating"), b["games"].get("appearences"))
                       for b in blocchi
                       if (b.get("games") or {}).get("rating") is not None
                       and (b.get("games") or {}).get("appearences")]
    if presenze_rating:
        peso = sum(a for _, a in presenze_rating)
        rating = sum(float(r) * a for r, a in presenze_rating) / peso if peso else None
    else:
        rating = None

    con_minuti = [b for b in blocchi if (b.get("games") or {}).get("minutes") is not None]

    fuori = _somme(blocchi)
    fuori["competizioni"] = [{"lega": (b.get("league") or {}).get("name"),
                              "squadra": (b.get("team") or {}).get("name"),
                              "minuti": (b.get("games") or {}).get("minutes"),
                              "presenze": (b.get("games") or {}).get("appearences")}
                             for b in blocchi]
    fuori["rating"] = rating
    fuori["precisione_passaggi"] = _media_pesata(blocchi, "passes", "accuracy")
    fuori["p90_base"] = _somme(con_minuti)
    fuori["p90_esclusi"] = [{"lega": (b.get("league") or {}).get("name"),
                             "squadra": (b.get("team") or {}).get("name"),
                             "presenze": (b.get("games") or {}).get("appearences"),
                             "gol": (b.get("goals") or {}).get("total"),
                             "assist": (b.get("goals") or {}).get("assists")}
                            for b in blocchi
                            if (b.get("games") or {}).get("minutes") is None]
    return fuori


def per90_agg(agg, chiave, soglia):
    """Il per-90 di una metrica preso dalla base coerente (stessi blocchi sopra e sotto)."""
    base = (agg or {}).get("p90_base") or {}
    return per90(base.get(chiave), base.get("minuti"), soglia)


def per90_somma_agg(agg, chiavi, soglia):
    """Come per90_agg ma su piu' metriche sommate (gol+assist, gialli+rossi)."""
    base = (agg or {}).get("p90_base") or {}
    return per90(somma([base.get(k) for k in chiavi]), base.get("minuti"), soglia)


def nota_p90_esclusi(agg):
    """
    Riga da stampare quando la base dei per-90 e' piu' stretta dei totali di stagione.
    None quando non c'e' niente da dichiarare: cosi' il percorso normale (una sola riga
    di Serie A, con i minuti) resta identico a prima.
    """
    esclusi = (agg or {}).get("p90_esclusi") or []
    if not esclusi:
        return None
    interessanti = [e for e in esclusi
                    if (e.get("gol") or e.get("assist") or e.get("presenze"))]
    if not interessanti:
        return None
    gol = sum(e.get("gol") or 0 for e in interessanti)
    ass = sum(e.get("assist") or 0 for e in interessanti)
    return ("Nei dati di origine queste competizioni non hanno i minuti, quindi NON entrano "
            "nei per-90 (ne' al numeratore ne' al denominatore): %s. Restano nei totali di "
            "stagione qui sopra, e valgono %d gol e %d assist: e' questa la differenza fra i "
            "totali e i numeri per 90 minuti."
            % ("; ".join("%s (%s presenze, %s gol, %s assist)"
                         % (e.get("lega") or ND, fmt(e.get("presenze"), 0),
                            fmt(e.get("gol"), 0), fmt(e.get("assist"), 0))
                         for e in interessanti), gol, ass))


def _media_pesata(blocchi, sez, campo):
    """Percentuali (precisione passaggi) pesate sui minuti: la somma sarebbe sbagliata."""
    coppie = [((b.get(sez) or {}).get(campo), (b.get("games") or {}).get("minutes"))
              for b in blocchi]
    coppie = [(v, m) for v, m in coppie if v is not None and m]
    if not coppie:
        return None
    peso = sum(m for _, m in coppie)
    return sum(float(v) * m for v, m in coppie) / peso if peso else None


# ---------------------------------------------------------------- costruzione .md

class Md(object):
    """Accumulatore di righe markdown. Niente logica: solo forma."""

    def __init__(self):
        self.righe = []

    def t(self, testo=""):
        self.righe.append(testo)
        return self

    def h(self, livello, testo):
        self.righe.append("")
        self.righe.append("#" * livello + " " + testo)
        self.righe.append("")
        return self

    def voce(self, etichetta, valore):
        self.righe.append("- **%s**: %s" % (etichetta, valore))
        return self

    def tabella(self, intestazioni, righe):
        # Senza riga vuota sopra, la tabella non viene renderizzata come tabella.
        if self.righe and self.righe[-1].strip():
            self.righe.append("")
        self.righe.append("| " + " | ".join(intestazioni) + " |")
        self.righe.append("|" + "|".join(["---"] * len(intestazioni)) + "|")
        for r in righe:
            self.righe.append("| " + " | ".join(str(c) for c in r) + " |")
        self.righe.append("")
        return self

    def testo(self):
        out = "\n".join(self.righe).rstrip() + "\n"
        while "\n\n\n" in out:
            out = out.replace("\n\n\n", "\n\n")
        return out


def intestazione(md, titolo, data, dati, nota):
    md.t("# " + titolo)
    md.t("")
    md.t("_Dossier di soli numeri per chi scrive il pezzo. Ogni valore qui dentro e' gia' "
         "calcolato e gia' arrotondato: non rifare i conti, copia questi. Se leggi "
         "\"%s\" il dato non c'e' nei nostri file e non va sostituito con una stima._" % ND)
    md.t("")
    md.voce("Data del dossier", data)
    md.voce("A cosa serve", nota)
    md.t("")
    md.h(2, "Da dove vengono i numeri")
    md.tabella(["File", "Aggiornato al"], [
        ["data/fanta/listone.json", dati.listone.get("updated") or ND],
        ["data/fanta/schede.json", dati.schede.get("updated") or ND],
        ["data/stats/players.json", dati.stats_players.get("updated") or ND],
        ["data/stats/teams.json", dati.stats_teams.get("updated") or ND],
        ["data/stats/matches.json", dati.matches.get("updated") or ND],
        ["data/competizioni.json", dati.competizioni.get("aggiornato") or ND],
    ])


def blocco_soglie(md, min_prev, min_cur):
    md.h(2, "Soglie usate (dichiarale nel pezzo se citi un numero per 90)")
    md.voce("Minuti minimi per i \"per 90\" della stagione 2025-26",
            "%d minuti (5 partite piene)" % min_prev)
    md.voce("Minuti minimi per i \"per 90\" della stagione 2026-27",
            "%d minuti (2 partite piene: il campionato e' appena cominciato)" % min_cur)
    md.voce("Sotto la soglia", "il dossier scrive \"%s\" e quel numero NON va usato" % POCHI)
    md.voce("Base di confronto", "Serie A contro Serie A. Le altre competizioni sono "
                                 "elencate a parte e non entrano nei confronti")


# ---------------------------------------------------------------- profilo giocatore

def profilo(dati, pid, min_prev, min_cur):
    """Tutto quello che sappiamo su un giocatore, gia' aggregato. Nessun buco riempito."""
    lst = dati.giocatori.get(pid)
    sch = dati.sch.get(str(pid)) or {}
    st = dati.stp.get(str(pid))

    p = {"id": pid, "nome": (lst or {}).get("name") or (st or {}).get("name") or ND,
         "squadra": (lst or {}).get("team") or (st or {}).get("team_name"),
         "ruolo": (lst or {}).get("role"), "prezzo": (lst or {}).get("price"),
         "fvm": (lst or {}).get("fvm"),
         "eta": sch.get("age"), "nazionalita": sch.get("nat"),
         "foto": sch.get("photo"), "scheda_url": sch.get("url"),
         "fanta": {"mv": sch.get("mv"), "fmv": sch.get("fmv"), "tit": sch.get("tit"),
                   "pres": sch.get("pres"), "gol": sch.get("gol"), "assist": sch.get("assist"),
                   "ultimi": sch.get("last") or [], "prev_sintesi": sch.get("prev")},
         "infortunio": sch.get("inj"), "rientro": sch.get("back"),
         "ha_statistiche": bool(st)}

    if not st:
        p["prev"] = None
        p["cur"] = None
        p["prev_fonte"] = "nessun dato: il giocatore non e' in data/stats/players.json"
        p["cur_fonte"] = "nessun dato: il giocatore non e' in data/stats/players.json"
        p["altre_competizioni"] = []
        return p

    cur_sa = blocchi_lega(st.get("cur"), SERIE_A)
    prev_sa = blocchi_lega(st.get("prev"), SERIE_A)

    p["cur"] = aggrega(cur_sa) if cur_sa else None
    p["cur_fonte"] = "Serie A 2026-27" if cur_sa else \
        "non ha ancora dati di Serie A 2026-27 in data/stats/players.json"

    if prev_sa:
        p["prev"] = aggrega(prev_sa)
        p["prev_fonte"] = "Serie A 2025-26"
    elif st.get("prev"):
        # Ripiego dichiarato: chi arriva da un altro campionato non ha una riga di Serie A.
        # Meglio dare il totale 2025-26 SCRITTO A CHIARE LETTERE che lasciare il vuoto.
        veri = [b for b in st["prev"]
                if (b.get("league") or {}).get("id") not in LEGHE_AMICHEVOLI]
        p["prev"] = aggrega(veri) if veri else None
        p["prev_fonte"] = ("NON ha giocato in Serie A nel 2025-26: qui sotto c'e' il totale "
                           "di TUTTE le sue competizioni ufficiali 2025-26 (amichevoli escluse "
                           "perche' nei dati di origine ripetono i numeri di altri tornei). "
                           "NON e' confrontabile uno a uno con la Serie A: dillo nel pezzo")
    else:
        p["prev"] = None
        p["prev_fonte"] = "nessun dato sulla stagione 2025-26"

    p["altre_competizioni"] = [
        {"lega": (b.get("league") or {}).get("name"), "squadra": (b.get("team") or {}).get("name"),
         "presenze": (b.get("games") or {}).get("appearences"),
         "minuti": (b.get("games") or {}).get("minutes"),
         "gol": (b.get("goals") or {}).get("total"),
         "assist": (b.get("goals") or {}).get("assists")}
        for b in (st.get("prev") or []) if (b.get("league") or {}).get("id") != SERIE_A]

    p["min_prev"] = min_prev
    p["min_cur"] = min_cur
    return p


# metrica -> (etichetta, decimali). L'ordine e' quello con cui esce nel .md.
METRICHE = [
    ("presenze", "Presenze", 0), ("da_titolare", "Da titolare", 0), ("minuti", "Minuti giocati", 0),
    ("gol", "Gol", 0), ("assist", "Assist", 0),
    ("tiri", "Tiri totali", 0), ("tiri_in_porta", "Tiri in porta", 0),
    ("passaggi", "Passaggi", 0), ("passaggi_chiave", "Passaggi chiave", 0),
    ("contrasti", "Contrasti", 0), ("intercetti", "Intercetti", 0),
    ("duelli", "Duelli", 0), ("duelli_vinti", "Duelli vinti", 0),
    ("dribbling_tentati", "Dribbling tentati", 0), ("dribbling_riusciti", "Dribbling riusciti", 0),
    ("falli_fatti", "Falli fatti", 0), ("falli_subiti", "Falli subiti", 0),
    ("gialli", "Ammonizioni", 0), ("doppi_gialli", "Doppie ammonizioni", 0), ("rossi", "Espulsioni", 0),
    ("rig_segnati", "Rigori segnati", 0), ("rig_sbagliati", "Rigori sbagliati", 0),
    ("rig_conquistati", "Rigori conquistati", 0), ("rig_causati", "Rigori causati", 0),
    ("gol_subiti", "Gol subiti (portiere)", 0), ("parate", "Parate (portiere)", 0),
    ("rig_parati", "Rigori parati (portiere)", 0),
]

# Voci che restano nella tabella anche quando il dato manca: chi scrive deve VEDERE
# che il rigore non e' un buco lasciato aperto ma un dato che non abbiamo.
METRICHE_SEMPRE = ("presenze", "da_titolare", "minuti", "gol", "assist",
                   "rig_segnati", "rig_sbagliati", "rig_conquistati", "rig_causati")

# Voci che hanno senso solo per un portiere: su un attaccante sono rumore.
METRICHE_PORTIERE = ("gol_subiti", "parate", "rig_parati")


def metriche_visibili(ruolo):
    if ruolo == "P":
        return list(METRICHE)
    return [m for m in METRICHE if m[0] not in METRICHE_PORTIERE]


# Metriche che ha senso portare a 90 minuti (i minuti stessi no, le presenze no).
METRICHE_P90 = ["gol", "assist", "tiri", "tiri_in_porta", "passaggi", "passaggi_chiave",
                "contrasti", "intercetti", "duelli", "duelli_vinti", "dribbling_tentati",
                "dribbling_riusciti", "falli_fatti", "falli_subiti", "gialli",
                "gol_subiti", "parate"]


def tabella_stagione(md, agg, fonte, titolo, ruolo=None):
    md.h(3, titolo)
    md.t("_Fonte dei numeri: %s._" % fonte)
    md.t("")
    if not agg:
        md.t("**%s**: nessun numero da mostrare." % ND)
        return
    righe = []
    for chiave, etichetta, dec in metriche_visibili(ruolo):
        v = agg.get(chiave)
        if v is None and chiave not in METRICHE_SEMPRE:
            continue
        righe.append([etichetta, fmt(v, dec)])
    # percentuali e medie, che non sono somme
    if agg.get("precisione_passaggi") is not None:
        righe.append(["Precisione passaggi", fmt(agg["precisione_passaggi"], 1, "%")])
    if agg.get("duelli") and agg.get("duelli_vinti") is not None and agg["duelli"]:
        righe.append(["Duelli vinti sul totale",
                      "%s su %s (%s)" % (fmt(agg["duelli_vinti"], 0), fmt(agg["duelli"], 0),
                                         fmt(agg["duelli_vinti"] * 100.0 / agg["duelli"], 1, "%"))])
    if agg.get("dribbling_tentati"):
        righe.append(["Dribbling riusciti su tentati",
                      "%s su %s (%s)" % (fmt(agg.get("dribbling_riusciti"), 0),
                                         fmt(agg["dribbling_tentati"], 0),
                                         fmt((agg.get("dribbling_riusciti") or 0) * 100.0
                                             / agg["dribbling_tentati"], 1, "%"))])
    if agg.get("rating") is not None:
        righe.append(["Voto medio API-Football (media pesata sulle presenze)",
                      fmt(agg["rating"], 2)])
    if not righe:
        md.t("**%s**: nessun numero da mostrare." % ND)
        return
    md.tabella(["Voce", "Valore"], righe)
    if agg.get("competizioni"):
        md.t("Competizioni comprese in questi totali: " +
             "; ".join("%s con %s (%s presenze, %s minuti)" %
                       (c["lega"], c["squadra"], fmt(c["presenze"], 0), fmt(c["minuti"], 0))
                       for c in agg["competizioni"]) + ".")
        md.t("")


def tabella_p90(md, prev, cur, min_prev, min_cur, ruolo=None):
    md.h(3, "Gli stessi numeri ogni 90 minuti, e la variazione")
    md.t("_E' l'unico confronto onesto fra due stagioni con minutaggi diversi. "
         "La variazione va dalla stagione 2025-26 alla 2026-27._")
    md.t("")
    if not prev and not cur:
        md.t("**%s**: mancano i dati di entrambe le stagioni." % ND)
        return
    righe = []
    riservate = () if ruolo == "P" else METRICHE_PORTIERE
    for chiave in METRICHE_P90:
        if chiave in riservate:
            continue
        etichetta = dict((k, e) for k, e, _ in METRICHE).get(chiave, chiave)
        a = per90_agg(prev, chiave, min_prev)
        b = per90_agg(cur, chiave, min_cur)
        if a is None and b is None:
            continue
        d, pct = variazione(a, b)
        righe.append([etichetta + " ogni 90'", fmt(a, 2), fmt(b, 2), fmt_var(d, pct)])
    if righe:
        md.tabella(["Metrica", "2025-26 per 90'", "2026-27 per 90'", "Variazione"], righe)
    else:
        md.t("**%s**: nessuna metrica supera le soglie di minuti." % POCHI)
        md.t("")
    for etichetta, chiave, dec in [("Voto medio", "rating", 2),
                                   ("Precisione passaggi", "precisione_passaggi", 1)]:
        a = (prev or {}).get(chiave)
        b = (cur or {}).get(chiave)
        d, pct = variazione(a, b)
        md.t("- **%s**: 2025-26 %s, 2026-27 %s, variazione %s"
             % (etichetta, fmt(a, dec), fmt(b, dec), fmt_var(d, pct, dec)))
    md.t("")
    md.t("_Minuti effettivi su cui sono calcolati: 2025-26 %s, 2026-27 %s._"
         % (fmt(((prev or {}).get("p90_base") or {}).get("minuti"), 0),
            fmt(((cur or {}).get("p90_base") or {}).get("minuti"), 0)))
    md.t("")
    for stagione, agg in (("2025-26", prev), ("2026-27", cur)):
        nota = nota_p90_esclusi(agg)
        if nota:
            md.t("**Attenzione, stagione %s.** %s" % (stagione, nota))
            md.t("")


# ---------------------------------------------------------------- blocchi comuni

def blocco_fantatb(md, p):
    md.h(3, "I nostri numeri FantaTB")
    f = p["fanta"]
    md.voce("Media voto (MV)", fmt(f["mv"], 2))
    md.voce("Fantamedia (FMV)", fmt(f["fmv"], 2))
    md.voce("Titolarita' stimata da FantaTB", fmt(f["tit"], 0, "%") if f["tit"] is not None else ND)
    md.voce("Presenze con voto", fmt(f["pres"], 0))
    md.voce("Gol", fmt(f["gol"], 0))
    md.voce("Assist", fmt(f["assist"], 0))
    if f["ultimi"]:
        md.voce("Ultimi fantavoti", ", ".join("%da giornata %s" % (g, fmt(v, 1))
                                              for g, v in f["ultimi"]))
    else:
        md.voce("Ultimi fantavoti", ND)
    pv = f.get("prev_sintesi")
    if pv:
        md.voce("Sintesi 2025-26 dalla scheda",
                "%s: %s presenze (%s da titolare), %s gol, %s assist, voto medio %s"
                % (pv.get("lega") or ND, fmt(pv.get("pres"), 0), fmt(pv.get("tit"), 0),
                   fmt(pv.get("gol"), 0), fmt(pv.get("assist"), 0), fmt(pv.get("rating"), 2)))
    else:
        md.voce("Sintesi 2025-26 dalla scheda", ND)
    md.t("")


def blocco_squadra(md, dati, nome_squadra, titolo="La sua squadra"):
    md.h(3, titolo)
    sq = dati.squadra_per_nome.get(norm_team(nome_squadra))
    if not sq:
        md.t("**%s**: la squadra \"%s\" non e' in data/stats/teams.json." % (ND, nome_squadra))
        return None
    riga = dati.riga_classifica(nome_squadra)
    if riga:
        md.voce("Posizione in Serie A", "%d^ con %d punti in %d giornate (%dV %dN %dP)"
                % (riga["pos"], riga["pt"], riga["pg"], riga["v"], riga["n"], riga["p"]))
        md.voce("Gol fatti e subiti in campionato", "%d fatti, %d subiti (differenza %+d)"
                % (riga["gf"], riga["gs"], riga["dr"]))
    else:
        md.voce("Posizione in Serie A",
                "%s: il nome \"%s\" non si aggancia alla classifica di competizioni.json"
                % (ND, nome_squadra))
    md.voce("Andamento ultime partite (form)", sq.get("form") or ND)
    gf = (sq.get("goals_for") or {}).get("avg", {}).get("total")
    ga = (sq.get("goals_against") or {}).get("avg", {}).get("total")
    md.voce("Media gol fatti a partita", fmt(gf, 2))
    md.voce("Media gol subiti a partita", fmt(ga, 2))
    md.voce("Porta inviolata", "%s partite su %s"
            % (fmt((sq.get("clean_sheet") or {}).get("total"), 0),
               fmt((sq.get("fixtures") or {}).get("played", {}).get("total"), 0)))
    md.voce("Rigori di squadra", dati.testo_rigori_squadra(sq))
    st = dati.stat_partite_squadra(sq["id"])
    md.voce("xG della squadra a partita",
            "%s; e' l'xG DELLA SQUADRA, non del giocatore"
            % fmt_media_partite(st, "xg", 2))
    md.voce("xG concessi agli avversari a partita", fmt_media_partite(st, "xg_contro", 2))
    md.voce("Possesso medio", fmt_media_partite(st, "possesso", 1, "%"))
    md.voce("Tiri a partita", "%s, di cui in porta %s"
            % (fmt_media_partite(st, "tiri", 1), fmt_media_partite(st, "tiri_in_porta", 1)))
    md.voce("Partite di questa squadra con un blocco statistiche",
            "%d (il numero fra parentesi accanto a ogni media dice su quante di queste "
            "quel dato c'era davvero)" % st["partite_con_statistiche"])
    md.t("")
    return sq


def blocco_impegno(md, dati, sq, titolo="Il prossimo impegno"):
    md.h(3, titolo)
    if not sq:
        md.t("**%s**: senza la squadra non posso cercare la partita." % ND)
        return None
    imp = dati.prossimo_impegno(sq["id"])
    if not imp:
        md.t("**%s**: nessuna partita di questa squadra nella giornata in arrivo "
             "(file probabili-NN.json)." % ND)
        return None
    md.voce("Giornata", fmt(imp["giornata"], 0))
    md.voce("Partita", "%s - %s" % (imp["casa"], imp["trasferta"]))
    md.voce("Dove gioca", "in casa" if imp["in_casa"] else "in trasferta")
    md.voce("Data e ora (UTC, come nei nostri dati)", imp["data"] or ND)
    md.voce("Stadio", imp["stadio"] or ND)
    avv = dati.squadra_per_id.get(imp["avversario_id"])
    if not avv:
        md.voce("Come sta l'avversario", "%s: %s non e' in data/stats/teams.json"
                % (ND, imp["avversario"]))
        return imp
    riga = dati.riga_classifica(avv["name"])
    md.voce("Avversario", avv["name"])
    md.voce("Posizione dell'avversario",
            ("%d^ con %d punti" % (riga["pos"], riga["pt"])) if riga else ND)
    md.voce("Forma dell'avversario", avv.get("form") or ND)
    md.voce("Gol dell'avversario", "%s fatti a partita, %s subiti a partita"
            % (fmt((avv.get("goals_for") or {}).get("avg", {}).get("total"), 2),
               fmt((avv.get("goals_against") or {}).get("avg", {}).get("total"), 2)))
    md.voce("Porta inviolata dell'avversario",
            "%s partite su %s" % (fmt((avv.get("clean_sheet") or {}).get("total"), 0),
                                fmt((avv.get("fixtures") or {}).get("played", {}).get("total"), 0)))
    sta = dati.stat_partite_squadra(avv["id"])
    md.voce("xG concessi dall'avversario a partita", fmt_media_partite(sta, "xg_contro", 2))
    md.t("")
    return imp


def blocco_disponibilita(md, dati, p):
    md.h(3, "Disponibilita': infortuni, squalifiche, probabile formazione")
    md.voce("Infortunio o indisponibilita' segnalata", p.get("infortunio") or "nessuna nei nostri dati")
    md.voce("Rientro previsto", p.get("rientro") or ND)
    tit = (dati.titolari or {}).get(p["id"])
    if tit:
        md.voce("Probabilita' di essere titolare nella giornata %s"
                % fmt(dati.giornata_prossima, 0), "%s%% - %s"
                % (fmt(tit.get("prob"), 0), tit.get("reason") or ND))
        if tit.get("injury"):
            md.voce("Nota infortunio dal file titolari", "%s (rientro: %s)"
                    % (tit["injury"], tit.get("back_at") or ND))
    else:
        md.voce("Probabilita' di essere titolare",
                "%s: non compare nel file titolari-%s.json"
                % (ND, ("%02d" % dati.giornata_prossima) if dati.giornata_prossima else "NN"))
    riga = _riga_probabili(dati, p)
    md.voce("Nelle probabili formazioni", riga)
    md.t("")


def _riga_probabili(dati, p):
    if not dati.probabili:
        return ND
    sq = (dati.probabili.get("teams") or {}).get(p.get("squadra"))
    if not sq:
        for nome, blocco in (dati.probabili.get("teams") or {}).items():
            if norm_team(nome) == norm_team(p.get("squadra")):
                sq = blocco
                break
    if not sq:
        return ND
    for g in sq.get("xi") or []:
        if g.get("id") == p["id"]:
            base = "titolare nella probabile (%s%%, %s)" % (fmt(g.get("prob"), 0), g.get("why") or ND)
            if g.get("ballot"):
                base += "; ballottaggio con %s (%s%%)" % (g["ballot"].get("name"),
                                                          fmt(g["ballot"].get("prob"), 0))
            return base
    for g in sq.get("bench") or []:
        if g.get("id") == p["id"]:
            return "in panchina nella probabile (%s%%)" % fmt(g.get("prob"), 0)
    for g in sq.get("out") or []:
        if g.get("id") == p["id"]:
            return "indicato indisponibile nella probabile"
    return "non compare nella probabile formazione della sua squadra"


def blocco_pari_ruolo(md, dati, p, min_cur):
    """Dove si colloca fra i pari ruolo del listone. Il metodo e' scritto nel .md."""
    md.h(3, "Dove si colloca fra i pari ruolo")
    ruolo = p.get("ruolo")
    if not ruolo:
        md.t("**%s**: ruolo sconosciuto." % ND)
        return
    pop = []
    for g in dati.listone["players"]:
        if g["role"] != ruolo:
            continue
        sch = dati.sch.get(str(g["id"])) or {}
        st = dati.stp.get(str(g["id"]))
        cur = aggrega(blocchi_lega((st or {}).get("cur"), SERIE_A)) if st else None
        pop.append({"id": g["id"], "prezzo": g["price"], "fmv": sch.get("fmv"),
                    "mv": sch.get("mv"), "tit": sch.get("tit"),
                    "minuti": (cur or {}).get("minuti"),
                    "ga90": per90_somma_agg(cur, ("gol", "assist"), min_cur)})
    mio = [x for x in pop if x["id"] == p["id"]]
    mio = mio[0] if mio else None
    if not mio:
        md.t("**%s**: il giocatore non e' nel listone." % ND)
        return
    righe = []
    for chiave, etichetta, dec in [("fmv", "Fantamedia FantaTB", 2),
                                   ("prezzo", "Quotazione", 0),
                                   ("tit", "Titolarita' %", 0),
                                   ("ga90", "Gol + assist ogni 90' in Serie A 2026-27", 2)]:
        valori = [x[chiave] for x in pop]
        pc = percentile(mio[chiave], valori)
        validi = len([v for v in valori if v is not None and not isinstance(v, str)])
        righe.append([etichetta, fmt(mio[chiave], dec),
                      (fmt(pc, 0, "%") if pc is not None else ND),
                      "%d %s" % (validi, RUOLI_PL.get(ruolo, "giocatori"))])
    md.tabella(["Metrica", "Il suo valore", "Percentile fra i pari ruolo",
                "Su quanti giocatori"], righe)
    md.t("_Percentile = quota di pari ruolo del listone con un valore minore o uguale al suo "
         "(rank inclusivo). Chi non ha il dato non entra nel conteggio._")
    md.t("")


# ---------------------------------------------------------------- stato rotazione

STATO_FILE = "_stato-rotazione.json"


def leggi_stato(cartella):
    percorso = os.path.join(cartella, STATO_FILE)
    if not os.path.exists(percorso):
        return {"giocatore": {"usati": [], "giro": 1, "assegnazioni": {}},
                "confronto": {"usate": [], "giro": 1, "assegnazioni": {}}}
    with open(percorso, "r", encoding="utf-8") as f:
        s = json.load(f)
    s.setdefault("giocatore", {"usati": [], "giro": 1, "assegnazioni": {}})
    s.setdefault("confronto", {"usate": [], "giro": 1, "assegnazioni": {}})
    return s


def scrivi_stato(cartella, stato):
    if not os.path.isdir(cartella):
        os.makedirs(cartella)
    percorso = os.path.join(cartella, STATO_FILE)
    with open(percorso, "w", encoding="utf-8", newline="\n") as f:
        json.dump(stato, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


# ---------------------------------------------------------------- 1. GIOCATORE

def scegli_giocatore(dati, stato, data, soglia_prezzo):
    """
    Rotazione dal piu' costoso a scendere. Idempotente: se la data ha gia' un
    assegnato lo riusa, cosi' due giri di fila nello stesso giorno danno lo stesso file.
    """
    s = stato["giocatore"]
    if data in s.get("assegnazioni", {}):
        pid = s["assegnazioni"][data]
        if pid in dati.giocatori:
            return pid, s.get("giro", 1), [], True

    candidati = [g for g in dati.per_prezzo if g["price"] >= soglia_prezzo]
    if not candidati:
        raise DatiMancanti("nessun giocatore del listone costa almeno %d crediti "
                           "(soglia --soglia-prezzo)" % soglia_prezzo)

    saltati = []
    usati = set(s.get("usati", []))
    giro = s.get("giro", 1)

    for tentativo in (1, 2):
        for g in candidati:
            if g["id"] in usati:
                continue
            if str(g["id"]) not in dati.stp:
                # Non lo salto in silenzio: finisce nel .md come giocatore escluso e perche'.
                saltati.append(g)
                usati.add(g["id"])
                continue
            return g["id"], giro, saltati, False
        # Lista finita: si ricomincia dall'alto, con i numeri aggiornati.
        if tentativo == 1:
            usati = set()
            giro += 1
    raise DatiMancanti("nessun giocatore da %d crediti in su ha statistiche in "
                       "data/stats/players.json" % soglia_prezzo)


def dossier_giocatore(dati, data, opz, stato):
    pid, giro, saltati, riusato = scegli_giocatore(dati, stato, data, opz.soglia_prezzo)
    p = profilo(dati, pid, opz.min_minuti_prev, opz.min_minuti_cur)

    candidati = [g for g in dati.per_prezzo if g["price"] >= opz.soglia_prezzo]
    posizione = next((i + 1 for i, g in enumerate(candidati) if g["id"] == pid), None)
    usati_dopo = set(stato["giocatore"].get("usati", [])) | {g["id"] for g in saltati} | {pid}
    if giro != stato["giocatore"].get("giro", 1):
        usati_dopo = {g["id"] for g in saltati} | {pid}
    rimasti = len([g for g in candidati if g["id"] not in usati_dopo])

    md = Md()
    intestazione(md, "GIOCATORE DEL GIORNO - %s (%s)" % (p["nome"], p["squadra"] or ND),
                 data, dati,
                 "pezzo quotidiano di 2.500-4.000 caratteri su un singolo giocatore: "
                 "com'e' andato l'anno scorso, come sta andando adesso, cosa cambia")
    blocco_soglie(md, opz.min_minuti_prev, opz.min_minuti_cur)

    md.h(2, "1. Chi e' e perche' tocca a lui")
    md.voce("Nome", p["nome"])
    md.voce("Squadra", p["squadra"] or ND)
    md.voce("Ruolo al fanta", "%s (%s)" % (p["ruolo"] or ND, RUOLI.get(p["ruolo"], ND)))
    md.voce("Eta'", fmt(p["eta"], 0, "anni"))
    md.voce("Nazionalita'", p["nazionalita"] or ND)
    md.voce("Quotazione nel listone", fmt(p["prezzo"], 0, "crediti"))
    md.voce("FVM (fantavalore di mercato)",
            fmt(p["fvm"], 0) if p.get("fvm") is not None else
            "%s: il listone di oggi non contiene il FVM" % ND)
    md.voce("Scheda sul sito", p["scheda_url"] or ND)
    md.t("")
    md.voce("Punto della rotazione",
            "e' il %s giocatore della lista ordinata per quotazione, fra quelli da %d crediti "
            "in su; giro numero %d; dopo di lui restano %d giocatori prima di ricominciare"
            % (("%d^" % posizione) if posizione else ND, opz.soglia_prezzo, giro, rimasti))
    md.voce("Soglia di quotazione", "%d crediti: piu' in basso non si scende, "
                                    "quando la lista finisce si riparte dall'alto con i numeri "
                                    "aggiornati" % opz.soglia_prezzo)
    if riusato:
        md.voce("Nota", "per questa data la rotazione aveva gia' assegnato questo giocatore: "
                        "il dossier e' lo stesso di prima")
    if saltati:
        md.voce("Saltati prima di lui (nessun dato in data/stats/players.json)",
                ", ".join("%s (%s, %d crediti)" % (g["name"], g["team"], g["price"])
                          for g in saltati))
    md.t("")

    md.h(2, "2. Le due stagioni, numeri grezzi")
    tabella_stagione(md, p["prev"], p["prev_fonte"], "Stagione 2025-26", p["ruolo"])
    tabella_stagione(md, p["cur"], p["cur_fonte"], "Stagione 2026-27 (in corso)", p["ruolo"])
    if p["altre_competizioni"]:
        md.h(3, "Le altre competizioni del 2025-26 (fuori dal confronto)")
        md.tabella(["Competizione", "Squadra", "Presenze", "Minuti", "Gol", "Assist"],
                   [[c["lega"] or ND, c["squadra"] or ND, fmt(c["presenze"], 0),
                     fmt(c["minuti"], 0), fmt(c["gol"], 0), fmt(c["assist"], 0)]
                    for c in p["altre_competizioni"]])
        md.t("_Queste righe NON entrano in nessun confronto: sono qui solo come contesto. "
             "Attenzione: nei dati di origine le voci \"Friendlies\" e \"Friendlies Clubs\" "
             "ripetono i minuti di altri tornei, quindi non vanno sommate._")
        md.t("")

    md.h(2, "3. Il confronto vero: ogni 90 minuti")
    tabella_p90(md, p["prev"], p["cur"], opz.min_minuti_prev, opz.min_minuti_cur, p["ruolo"])

    md.h(2, "4. I nostri numeri di fantacalcio")
    blocco_fantatb(md, p)

    md.h(2, "5. Il contesto")
    sq = blocco_squadra(md, dati, p["squadra"])
    blocco_impegno(md, dati, sq)
    blocco_disponibilita(md, dati, p)
    blocco_pari_ruolo(md, dati, p, opz.min_minuti_cur)

    md.h(2, "6. COSA NON ABBIAMO")
    mancanti = cose_che_mancano_giocatore(dati, p)
    for m in mancanti:
        md.t("- " + m)
    md.t("")
    md.t("_Non promettere nel pezzo nessuna delle cose elencate qui sopra._")

    payload = {"formato": "giocatore", "data": data, "giocatore": p,
               "rotazione": {"posizione": posizione, "giro": giro, "rimasti": rimasti,
                             "soglia_prezzo": opz.soglia_prezzo,
                             "saltati": [g["id"] for g in saltati]},
               "soglie": {"min_minuti_prev": opz.min_minuti_prev,
                          "min_minuti_cur": opz.min_minuti_cur},
               "cosa_non_abbiamo": mancanti}

    stato["giocatore"]["giro"] = giro
    stato["giocatore"]["usati"] = sorted(usati_dopo)
    stato["giocatore"].setdefault("assegnazioni", {})[data] = pid
    return md.testo(), payload


def cose_che_mancano_giocatore(dati, p):
    fuori = ["**xG e xA del singolo giocatore: non esistono nei nostri dati.** L'xG lo abbiamo "
             "solo per SQUADRA e per partita (data/stats/matches.json). Non scrivere mai "
             "\"xG di %s\"." % p["nome"],
             "Tocchi, palloni giocati, heat map, posizione media in campo: non li abbiamo.",
             "Precedenti storici e statistiche contro il prossimo avversario: "
             "data/stats/matches.json contiene solo la stagione in corso.",
             "Valore di mercato in euro, stipendio, scadenza di contratto: non li abbiamo."]
    if not dati.rigori_squadra_affidabili:
        fuori.append("**I rigori della sua SQUADRA: non ce li abbiamo.** %s. Non scrivere che "
                     "la squadra non ha ancora battuto rigori: il dato manca, non e' zero."
                     % dati.rigori_squadra_nota["lunga"])
    if not p["ha_statistiche"]:
        fuori.append("Questo giocatore NON e' in data/stats/players.json: mancano tutte le "
                     "statistiche tecniche, restano solo listone e scheda FantaTB.")
    if not p["cur"]:
        fuori.append("Non ha ancora dati di Serie A 2026-27: il confronto fra le due stagioni "
                     "non si puo' fare.")
    if not p["prev"]:
        fuori.append("Non abbiamo dati sulla stagione 2025-26: niente confronto.")
    if p.get("fvm") is None:
        fuori.append("FVM: il listone di oggi non lo contiene.")
    if p["fanta"]["mv"] is None:
        fuori.append("Media voto e fantamedia FantaTB: non ancora calcolate per questo "
                     "giocatore (probabilmente non ha ancora preso un voto).")
    return fuori


# ---------------------------------------------------------------- sintesi rapida

LEGHE_RIGORI = (SERIE_A, COPPA_ITALIA)


def sintesi(dati, pid, min_prev, min_cur):
    """I pochi numeri che servono nelle tabelle di confronto. Nessuno inventato."""
    g = dati.giocatori.get(pid) or {}
    sch = dati.sch.get(str(pid)) or {}
    st = dati.stp.get(str(pid))
    cur = aggrega(blocchi_lega((st or {}).get("cur"), SERIE_A)) if st else None
    prev = aggrega(blocchi_lega((st or {}).get("prev"), SERIE_A)) if st else None
    ga_cur = per90_somma_agg(cur, ("gol", "assist"), min_cur) if cur else None
    ga_prev = per90_somma_agg(prev, ("gol", "assist"), min_prev) if prev else None
    cart_prev = per90_somma_agg(prev, ("gialli", "rossi"), min_prev) if prev else None
    cart_cur = per90_somma_agg(cur, ("gialli", "rossi"), min_cur) if cur else None
    tit = (dati.titolari or {}).get(pid) or {}
    return {"id": pid, "nome": g.get("name") or (st or {}).get("name") or ND,
            "squadra": g.get("team") or (st or {}).get("team_name"),
            "ruolo": g.get("role"), "prezzo": g.get("price"),
            "mv": sch.get("mv"), "fmv": sch.get("fmv"), "tit": sch.get("tit"),
            "pres": sch.get("pres"), "gol": sch.get("gol"), "assist": sch.get("assist"),
            "inj": sch.get("inj"), "back": sch.get("back"),
            "prob_titolare": tit.get("prob"), "prob_perche": tit.get("reason"),
            "minuti_cur": (cur or {}).get("minuti"), "minuti_prev": (prev or {}).get("minuti"),
            "ga90_cur": ga_cur, "ga90_prev": ga_prev,
            "cart90_cur": cart_cur, "cart90_prev": cart_prev,
            "cur": cur, "prev": prev}


def rigori(dati, pid):
    """Rigori battuti in Serie A e Coppa Italia, con la squadra dell'epoca."""
    st = dati.stp.get(str(pid))
    if not st:
        return []
    fuori = []
    for etichetta, blocchi in (("2026-27", st.get("cur")), ("2025-26", st.get("prev"))):
        for b in blocchi or []:
            if (b.get("league") or {}).get("id") not in LEGHE_RIGORI:
                continue
            pen = b.get("penalty") or {}
            if not any([pen.get("scored"), pen.get("missed"), pen.get("won")]):
                continue
            fuori.append({"stagione": etichetta, "lega": (b.get("league") or {}).get("name"),
                          "squadra": (b.get("team") or {}).get("name"),
                          "segnati": pen.get("scored") or 0, "sbagliati": pen.get("missed") or 0,
                          "conquistati": pen.get("won") or 0})
    return fuori


# ---------------------------------------------------------------- 2. CARTELLO

def dossier_cartello(dati, data, opz):
    if not dati.probabili:
        raise DatiMancanti("non c'e' nessun file data/fanta/probabili-NN.json: "
                           "senza la giornata in arrivo non si sceglie la partita di cartello")
    fixtures = dati.probabili.get("fixtures") or []
    if not fixtures:
        raise DatiMancanti("il file probabili-%02d.json non contiene partite"
                           % dati.giornata_prossima)

    valutate, scartate = [], []
    for f in fixtures:
        rc = dati.riga_classifica(f.get("home"))
        ra = dati.riga_classifica(f.get("away"))
        if not rc or not ra:
            scartate.append((f, "posizione in classifica non disponibile per almeno una squadra"))
            continue
        valutate.append({"f": f, "somma": rc["pos"] + ra["pos"], "casa": rc, "ospite": ra})
    if not valutate:
        raise DatiMancanti("nessuna partita della giornata %s ha entrambe le squadre in "
                           "classifica: impossibile applicare il criterio di scelta"
                           % dati.giornata_prossima)
    valutate.sort(key=lambda x: (x["somma"], x["f"].get("date") or "", x["f"].get("home") or ""))
    scelta = valutate[0]
    f = scelta["f"]

    md = Md()
    intestazione(md, "PARTITA DI CARTELLO - %s - %s (giornata %s)"
                 % (f["home"], f["away"], fmt(dati.giornata_prossima, 0)), data, dati,
                 "analisi della partita clou del turno IN OTTICA FANTACALCIO, sui numeri")
    blocco_soglie(md, opz.min_minuti_prev, opz.min_minuti_cur)

    md.h(2, "1. Perche' questa partita")
    md.voce("Criterio", "fra le partite della giornata in arrivo scelgo quella con la SOMMA "
                        "PIU' BASSA delle posizioni in classifica delle due squadre. A parita', "
                        "vince la partita che si gioca prima")
    md.voce("Partita scelta", "%s (%d^) - %s (%d^), somma %d"
            % (f["home"], scelta["casa"]["pos"], f["away"], scelta["ospite"]["pos"],
               scelta["somma"]))
    md.voce("Data e ora (UTC)", f.get("date") or ND)
    md.voce("Stadio", f.get("venue") or ND)
    md.t("")
    md.t("Tutte le partite della giornata, con il punteggio del criterio:")
    md.t("")
    md.tabella(["Partita", "Posizioni", "Somma", "Data (UTC)"],
               [["%s - %s" % (v["f"]["home"], v["f"]["away"]),
                 "%d^ e %d^" % (v["casa"]["pos"], v["ospite"]["pos"]),
                 v["somma"], v["f"].get("date") or ND] for v in valutate])
    if scartate:
        md.t("Partite escluse dal criterio: " +
             "; ".join("%s - %s (%s)" % (x[0].get("home"), x[0].get("away"), x[1])
                       for x in scartate) + ".")
        md.t("")

    md.h(2, "2. Le due squadre")
    _tabella_due_squadre(md, dati, f["home"], f["away"])

    md.h(2, "3. Le probabili formazioni")
    for nome in (f["home"], f["away"]):
        _blocco_probabile(md, dati, nome)

    md.h(2, "4. Chi conta al fantacalcio")
    for nome in (f["home"], f["away"]):
        _tabella_fanta_squadra(md, dati, nome, opz)

    md.h(2, "5. Rigoristi delle due squadre")
    for nome in (f["home"], f["away"]):
        _rigoristi_squadra(md, dati, nome)

    md.h(2, "6. Portieri e difesa")
    _portieri(md, dati, f["home"], f["away"], opz)

    md.h(2, "7. Indisponibili")
    for nome in (f["home"], f["away"]):
        _indisponibili(md, dati, nome)

    md.h(2, "8. Precedenti fra le due squadre")
    _precedenti(md, dati, f["home"], f["away"])

    md.h(2, "9. COSA NON ABBIAMO")
    for r in ["**xG dei singoli giocatori: non esistono.** L'xG e' solo di squadra e per partita.",
              "Quote dei bookmaker, pronostici, probabilita' di vittoria: non le abbiamo.",
              "Precedenti storici fra le due squadre: non li abbiamo.",
              "Formazioni ufficiali: escono un'ora prima del calcio d'inizio, qui ci sono solo "
              "le probabili costruite sulle ultime tre partite.",
              "Squalifiche da giudice sportivo: nei dati compaiono solo gli infortuni e le "
              "indisponibilita' gia' segnalate."]:
        md.t("- " + r)
    md.t("")

    payload = {"formato": "cartello", "data": data, "giornata": dati.giornata_prossima,
               "criterio": "somma minima delle posizioni in classifica",
               "partita": {"casa": f["home"], "ospite": f["away"], "data": f.get("date"),
                           "stadio": f.get("venue"), "fixture": f.get("id"),
                           "posizioni": [scelta["casa"]["pos"], scelta["ospite"]["pos"]]},
               "tutte_le_partite": [{"casa": v["f"]["home"], "ospite": v["f"]["away"],
                                     "somma": v["somma"]} for v in valutate],
               "soglie": {"min_minuti_prev": opz.min_minuti_prev,
                          "min_minuti_cur": opz.min_minuti_cur}}
    return md.testo(), payload


def _tabella_due_squadre(md, dati, casa, ospite):
    righe = []
    voci = [("Posizione in classifica", lambda r, s, x: ("%d^" % r["pos"]) if r else ND),
            ("Punti", lambda r, s, x: fmt(r["pt"], 0) if r else ND),
            ("Forma (ultime partite)", lambda r, s, x: s.get("form") or ND),
            ("Gol fatti a partita", lambda r, s, x: fmt((s.get("goals_for") or {}).get("avg", {}).get("total"), 2)),
            ("Gol subiti a partita", lambda r, s, x: fmt((s.get("goals_against") or {}).get("avg", {}).get("total"), 2)),
            ("Partite giocate", lambda r, s, x: fmt((s.get("fixtures") or {}).get("played", {}).get("total"), 0)),
            ("Partite con porta inviolata", lambda r, s, x: fmt((s.get("clean_sheet") or {}).get("total"), 0)),
            ("xG della squadra a partita", lambda r, s, x: fmt_media_partite(x, "xg", 2)),
            ("xG concessi a partita", lambda r, s, x: fmt_media_partite(x, "xg_contro", 2)),
            ("Possesso medio", lambda r, s, x: fmt_media_partite(x, "possesso", 1, "%")),
            ("Tiri a partita", lambda r, s, x: fmt_media_partite(x, "tiri", 1)),
            ("Tiri in porta a partita", lambda r, s, x: fmt_media_partite(x, "tiri_in_porta", 1)),
            ("Precisione passaggi", lambda r, s, x: fmt_media_partite(x, "passaggi_pct", 1, "%")),
            # Non e' "statistiche complete": e' il numero di partite che HANNO un blocco
            # stats. Quante di quelle avessero davvero ogni singola metrica lo dice la
            # parentesi accanto a ciascuna media qui sopra.
            ("Partite con un blocco statistiche",
             lambda r, s, x: fmt(x["partite_con_statistiche"], 0))]
    dati_squadre = []
    for nome in (casa, ospite):
        s = dati.squadra_per_nome.get(norm_team(nome))
        dati_squadre.append((dati.riga_classifica(nome), s,
                             dati.stat_partite_squadra(s["id"]) if s else
                             {"partite_con_statistiche": 0}))
    for etichetta, f in voci:
        righe.append([etichetta] + [f(r, s or {}, x) for r, s, x in dati_squadre])
    md.tabella(["Voce", casa, ospite], righe)
    md.t("_Dove una media porta \"su N partite delle M con statistiche\", il denominatore da "
         "citare nel pezzo e' N: quel campo era vuoto nelle altre partite. Copia la frase "
         "intera, non il solo numero._")
    md.t("")


def _blocco_probabile(md, dati, nome):
    sq = _probabile_squadra(dati, nome)
    md.h(3, "Probabile formazione: %s" % nome)
    if not sq:
        md.t("**%s**: la squadra non compare nel file probabili-%s.json."
             % (ND, "%02d" % dati.giornata_prossima if dati.giornata_prossima else "NN"))
        return
    md.voce("Allenatore", sq.get("coach") or ND)
    md.voce("Modulo probabile", sq.get("module") or ND)
    md.voce("Basata su", "; ".join("%s contro %s (%s)" % (b.get("date"), b.get("opponent"),
                                                          b.get("formation"))
                                   for b in sq.get("based_on") or []) or ND)
    md.tabella(["Ruolo", "Giocatore", "Probabilita'", "Perche'", "Ballottaggio"],
               [[g.get("role") or ND, g.get("name") or ND, fmt(g.get("prob"), 0, "%"),
                 g.get("why") or ND,
                 ("%s (%s%%)" % (g["ballot"].get("name"), fmt(g["ballot"].get("prob"), 0))
                  if g.get("ballot") else "nessuno")] for g in sq.get("xi") or []])
    panca = sq.get("bench") or []
    if panca:
        md.t("Panchina probabile: " + ", ".join("%s (%s%%)" % (g.get("name"), fmt(g.get("prob"), 0))
                                                for g in panca) + ".")
        md.t("")


def _probabile_squadra(dati, nome):
    if not dati.probabili:
        return None
    teams = dati.probabili.get("teams") or {}
    if nome in teams:
        return teams[nome]
    for k, v in teams.items():
        if norm_team(k) == norm_team(nome):
            return v
    return None


def _giocatori_squadra(dati, nome):
    return sorted([g for g in dati.listone["players"] if norm_team(g["team"]) == norm_team(nome)],
                  key=lambda g: (-g["price"], g["name"]))


def _tabella_fanta_squadra(md, dati, nome, opz):
    md.h(3, "%s: chi fa bonus e chi rischia malus" % nome)
    rosa = _giocatori_squadra(dati, nome)
    if not rosa:
        md.t("**%s**: nessun giocatore del listone risulta in questa squadra." % ND)
        return
    righe = []
    for g in rosa[:16]:
        s = sintesi(dati, g["id"], opz.min_minuti_prev, opz.min_minuti_cur)
        righe.append([s["nome"], s["ruolo"] or ND, fmt(s["prezzo"], 0),
                      fmt(s["tit"], 0, "%") if s["tit"] is not None else ND,
                      fmt(s["fmv"], 2), fmt(s["ga90_cur"], 2), fmt(s["ga90_prev"], 2),
                      fmt(s["cart90_prev"], 2)])
    md.tabella(["Giocatore", "Ruolo", "Quot.", "Titolarita'", "Fantamedia",
                "Gol+assist /90 Serie A 2026-27", "Gol+assist /90 Serie A 2025-26",
                "Cartellini /90 Serie A 2025-26"], righe)
    md.t("_I primi 16 per quotazione. \"%s\" significa che sotto quella soglia di minuti il "
         "numero non e' affidabile: non usarlo._" % POCHI)
    md.t("")


def _rigoristi_squadra(md, dati, nome):
    md.h(3, "Rigoristi: %s" % nome)
    trovati = []
    for g in _giocatori_squadra(dati, nome):
        r = rigori(dati, g["id"])
        tot_s = sum(x["segnati"] for x in r)
        tot_m = sum(x["sbagliati"] for x in r)
        tot_w = sum(x["conquistati"] for x in r)
        if tot_s or tot_m:
            trovati.append((g, tot_s, tot_m, tot_w, r))
    if not trovati:
        md.t("**Nessun rigorista chiaro nei dati** per il %s: nessun giocatore del listone "
             "risulta aver battuto un rigore in Serie A o Coppa Italia fra 2025-26 e 2026-27. "
             "Non attribuire i rigori a nessuno." % nome)
        md.t("")
        return
    trovati.sort(key=lambda x: (-x[1], -x[2], x[0]["name"]))
    md.tabella(["Giocatore", "Rigori segnati", "Rigori sbagliati", "Rigori conquistati", "Dove"],
               [[g["name"], s, m, w,
                 "; ".join("%s %s con %s" % (x["lega"], x["stagione"], x["squadra"]) for x in r)]
                for g, s, m, w, r in trovati])


def _portieri(md, dati, casa, ospite, opz):
    righe = []
    for nome in (casa, ospite):
        sq = dati.squadra_per_nome.get(norm_team(nome))
        cs = (sq.get("clean_sheet") or {}).get("total") if sq else None
        pg = (sq.get("fixtures") or {}).get("played", {}).get("total") if sq else None
        for g in _giocatori_squadra(dati, nome):
            if g["role"] != "P":
                continue
            s = sintesi(dati, g["id"], opz.min_minuti_prev, opz.min_minuti_cur)
            cur = s["cur"]
            # Nell'origine il portiere di riserva ha appearences 0, minutes null e
            # goals.conceded 0: quello zero non e' "non ha subito gol", e' "non ha
            # giocato". Senza i minuti accanto era indistinguibile da chi ha davvero
            # tenuto la porta inviolata, quindi i minuti diventano una colonna e chi non
            # ne ha non porta numeri, porta la frase.
            minuti = (cur or {}).get("minuti")
            if not cur:
                min_txt = ND
                subiti = parate = "nessun dato di Serie A 2026-27"
            elif not minuti:
                min_txt = "0"
                subiti = parate = "NON HA GIOCATO"
            else:
                min_txt = "%s (%s presenze)" % (fmt(minuti, 0), fmt(cur.get("presenze"), 0))
                subiti = fmt(cur.get("gol_subiti"), 0)
                parate = fmt(cur.get("parate"), 0)
            righe.append([nome, s["nome"], fmt(s["prezzo"], 0), fmt(s["fmv"], 2),
                          fmt(s["tit"], 0, "%") if s["tit"] is not None else ND,
                          min_txt, subiti, parate,
                          "%s su %s" % (fmt(cs, 0), fmt(pg, 0))])
    if righe:
        md.tabella(["Squadra", "Portiere", "Quot.", "Fantamedia", "Titolarita'",
                    "Minuti 2026-27", "Gol subiti 2026-27", "Parate 2026-27",
                    "Porta inviolata (squadra)"], righe)
        md.t("_\"NON HA GIOCATO\" non e' uno zero: quel portiere ha 0 minuti in Serie A "
             "2026-27, quindi non ha subito gol perche' non e' mai stato in campo. Non "
             "confonderlo con chi ha giocato e ha tenuto la porta inviolata: guarda sempre "
             "la colonna dei minuti prima di scrivere un numero di questa tabella._")
        md.t("")
    else:
        md.t("**%s**: nessun portiere delle due squadre nel listone." % ND)
        md.t("")


def _indisponibili(md, dati, nome):
    md.h(3, "Indisponibili: %s" % nome)
    sq = _probabile_squadra(dati, nome)
    fuori = (sq.get("out") or []) if sq else []
    dubbi = (sq.get("doubt") or []) if sq else []
    infortunati = [(g, (dati.sch.get(str(g["id"])) or {}))
                   for g in _giocatori_squadra(dati, nome)
                   if (dati.sch.get(str(g["id"])) or {}).get("inj")]
    if not fuori and not dubbi and not infortunati:
        md.t("Nessun indisponibile e nessun dubbio segnalato nei nostri dati per il %s. "
             "Attenzione: **non abbiamo le squalifiche del giudice sportivo**, quindi "
             "l'assenza di segnalazioni non e' una garanzia." % nome)
        md.t("")
        return
    if fuori:
        md.voce("Fuori nella probabile", ", ".join(g.get("name") or ND for g in fuori))
    if dubbi:
        md.voce("In dubbio nella probabile", ", ".join(g.get("name") or ND for g in dubbi))
    if infortunati:
        md.tabella(["Giocatore", "Quotazione", "Segnalazione", "Rientro previsto"],
                   [[g["name"], fmt(g["price"], 0), s.get("inj") or ND, s.get("back") or ND]
                    for g, s in infortunati])
    md.t("")


def _precedenti(md, dati, casa, ospite):
    """
    Storico dei confronti diretti: cerco davvero nei nostri dati invece di dare per
    scontato che non ci siano. data/stats/matches.json copre solo la stagione in corso.
    """
    a = dati.squadra_per_nome.get(norm_team(casa))
    b = dati.squadra_per_nome.get(norm_team(ospite))
    if not a or not b:
        md.t("**%s**: almeno una delle due squadre non e' in data/stats/teams.json." % ND)
        md.t("")
        return
    trovati = []
    for fid, f in sorted((dati.matches.get("fixtures") or {}).items()):
        coppia = {f.get("home"), f.get("away")}
        if coppia == {a["id"], b["id"]}:
            st = f.get("stats") or {}
            trovati.append([f.get("date") or ND,
                            "%s - %s" % (f.get("home_name"), f.get("away_name")),
                            "%s-%s" % tuple(f.get("goals") or [ND, ND]),
                            "xG %s - %s" % (fmt((st.get(str(f.get("home"))) or {}).get("xg"), 2),
                                            fmt((st.get(str(f.get("away"))) or {}).get("xg"), 2))])
    if trovati:
        md.t("Nei nostri dati (solo stagione 2026-27) risultano questi confronti diretti:")
        md.t("")
        md.tabella(["Data (UTC)", "Partita", "Risultato", "xG"], trovati)
        md.t("_Non abbiamo nulla oltre la stagione in corso: non citare precedenti storici._")
    else:
        md.t("**%s.** data/stats/matches.json copre solo la stagione 2026-27 e in questi dati "
             "le due squadre non si sono ancora incontrate. Non abbiamo alcuno storico dei "
             "confronti diretti: non citarne nel pezzo." % ND)
    md.t("")


# ---------------------------------------------------------------- 3. MIGLIORI

def segno(v, dec=2):
    """Uno scarto va letto col segno davanti: +1.50 si capisce, 1.5 no."""
    if v is None:
        return ND
    return ("+" if v >= 0 else "") + (("%." + str(dec) + "f") % round(v, dec))


BONUS_ETICHETTE = {"gol": "gol", "assist": "assist", "amm": "ammonizione",
                   "esp": "espulsione", "gol_subito": "gol subito", "autogol": "autogol"}


def nome_di(dati, pid):
    g = dati.giocatori.get(pid)
    if g:
        return g["name"], g["team"], g["role"], g["price"]
    st = dati.stp.get(str(pid))
    if st:
        return st.get("name") or ND, st.get("team_name") or ND, ND, None
    return "id %s (nome %s)" % (pid, ND), ND, ND, None


def descrivi_bonus(bonus):
    if not bonus:
        return "nessuno"
    return ", ".join("%s x%d" % (BONUS_ETICHETTE.get(k, k), v) for k, v in sorted(bonus.items()))


def dossier_migliori(dati, data, opz):
    chiuse = dati.giornate_chiuse()
    if not chiuse:
        aperte = ["giornata %d: %s, %s partite su %s rilevate"
                  % (n, d.get("status") or ND, fmt(d.get("finished"), 0), fmt(d.get("total"), 0))
                  for n, d in sorted(dati.giornate_voti.items())]
        raise DatiMancanti("nessuna giornata chiusa nei file data/fanta/voti-NN.json, quindi "
                           "non c'e' niente da raccontare. Stato attuale: "
                           + ("; ".join(aperte) if aperte else "nessun file dei voti"))
    g = max(chiuse)
    voti = dati.giornate_voti[g]
    successive = [n for n in dati.giornate_voti if n > g]

    righe = [r for r in voti.get("ratings", []) if r.get("fantavoto") is not None]
    if not righe:
        raise DatiMancanti("la giornata %d risulta chiusa ma nessun giocatore ha un fantavoto "
                           "in data/fanta/voti-%02d.json" % (g, g))

    # Media stagionale su TUTTE le giornate chiuse, questa compresa: dichiarata nel .md.
    storico = {}
    for n in chiuse:
        for r in dati.giornate_voti[n].get("ratings", []):
            if r.get("fantavoto") is not None:
                storico.setdefault(r["player_id"], []).append((n, r["fantavoto"]))

    def scarto(pid, fv):
        serie = storico.get(pid, [])
        if len(serie) < 2:
            return None, len(serie)
        media = sum(v for _, v in serie) / len(serie)
        return fv - media, len(serie)

    arricchite = []
    for r in righe:
        nome, squadra, ruolo, prezzo = nome_di(dati, r["player_id"])
        d, pres = scarto(r["player_id"], r["fantavoto"])
        arricchite.append({"id": r["player_id"], "nome": nome, "squadra": squadra,
                           "ruolo": ruolo, "prezzo": prezzo, "minuti": r.get("minutes"),
                           "voto": r.get("voto"), "fantavoto": r.get("fantavoto"),
                           "bonus": r.get("bonus") or {}, "scarto": d, "presenze": pres})

    per_fv = sorted(arricchite, key=lambda x: (-x["fantavoto"], -(x["voto"] or 0), x["nome"]))
    migliori = per_fv[:12]
    peggiori = list(reversed(per_fv))[:12]
    con_scarto = [x for x in arricchite if x["scarto"] is not None]
    su = sorted(con_scarto, key=lambda x: (-x["scarto"], x["nome"]))[:10]
    giu = sorted(con_scarto, key=lambda x: (x["scarto"], x["nome"]))[:10]

    visti = set(r["player_id"] for r in voti.get("ratings", []))
    giocato = set(r["player_id"] for r in voti.get("ratings", []) if (r.get("minutes") or 0) > 0)
    assenti = [g2 for g2 in dati.per_prezzo if g2["id"] not in giocato][:15]

    md = Md()
    intestazione(md, "MIGLIORI E PEGGIORI - giornata %d" % g, data, dati,
                 "pezzo del lunedi' sui NOSTRI fantavoti FantaTB della giornata appena chiusa")

    md.h(2, "1. Di quale giornata parliamo")
    md.voce("Giornata", "%d" % g)
    md.voce("Stato", "%s, %s partite su %s rilevate"
            % (voti.get("status") or ND, fmt(voti.get("finished"), 0), fmt(voti.get("total"), 0)))
    md.voce("Voti aggiornati al", voti.get("updated") or ND)
    md.voce("Giocatori con un fantavoto", "%d su %d rilevati" % (len(righe), len(visti)))
    if successive:
        st = dati.giornate_voti[max(successive)]
        md.voce("Attenzione", "esiste gia' il file della giornata %d ma NON e' chiusa "
                              "(%s, %s partite su %s): non usarne i numeri"
                % (max(successive), st.get("status") or ND, fmt(st.get("finished"), 0),
                   fmt(st.get("total"), 0)))
    md.t("")

    md.h(2, "2. I migliori fantavoti")
    md.tabella(["Giocatore", "Squadra", "Ruolo", "Quot.", "Minuti", "Voto", "Fantavoto", "Bonus e malus"],
               [[x["nome"], x["squadra"], x["ruolo"], fmt(x["prezzo"], 0), fmt(x["minuti"], 0),
                 fmt(x["voto"], 1), fmt(x["fantavoto"], 1), descrivi_bonus(x["bonus"])]
                for x in migliori])

    md.h(2, "3. I peggiori fantavoti")
    md.tabella(["Giocatore", "Squadra", "Ruolo", "Quot.", "Minuti", "Voto", "Fantavoto", "Bonus e malus"],
               [[x["nome"], x["squadra"], x["ruolo"], fmt(x["prezzo"], 0), fmt(x["minuti"], 0),
                 fmt(x["voto"], 1), fmt(x["fantavoto"], 1), descrivi_bonus(x["bonus"])]
                for x in peggiori])

    md.h(2, "4. Bonus e malus della giornata")
    conteggi = {}
    for x in arricchite:
        for k, v in x["bonus"].items():
            conteggi[k] = conteggi.get(k, 0) + v
    if conteggi:
        md.tabella(["Voce", "Quante volte"],
                   [[BONUS_ETICHETTE.get(k, k), v] for k, v in sorted(conteggi.items(),
                                                                      key=lambda kv: -kv[1])])
    else:
        md.t("**%s**: nessun bonus o malus registrato in questa giornata." % ND)
        md.t("")
    for chiave, titolo in (("gol", "Chi ha segnato"), ("assist", "Chi ha servito un assist"),
                           ("esp", "Chi e' stato espulso"), ("autogol", "Autogol")):
        elenco = [x for x in arricchite if x["bonus"].get(chiave)]
        if elenco:
            md.voce(titolo, ", ".join("%s (%s) x%d" % (x["nome"], x["squadra"], x["bonus"][chiave])
                                      for x in sorted(elenco, key=lambda y: y["nome"])))
        else:
            md.voce(titolo, "nessuno in questa giornata")
    md.t("")

    md.h(2, "5. Chi ha fatto meglio della propria media stagionale")
    md.t("_Media stagionale = media dei fantavoti di questo giocatore su TUTTE le giornate "
         "chiuse, questa compresa (giornate %s). Con meno di 2 presenze lo scarto non si "
         "calcola: la riga non compare._" % ", ".join(str(n) for n in chiuse))
    md.t("")
    md.tabella(["Giocatore", "Squadra", "Fantavoto", "Media stagionale", "Scarto", "Presenze"],
               [[x["nome"], x["squadra"], fmt(x["fantavoto"], 1),
                 fmt(x["fantavoto"] - x["scarto"], 2), segno(x["scarto"], 2),
                 "%d%s" % (x["presenze"], " - %s" % POCHI if x["presenze"] < 3 else "")]
                for x in su])

    md.h(2, "6. Chi ha fatto peggio della propria media stagionale")
    md.tabella(["Giocatore", "Squadra", "Fantavoto", "Media stagionale", "Scarto", "Presenze"],
               [[x["nome"], x["squadra"], fmt(x["fantavoto"], 1),
                 fmt(x["fantavoto"] - x["scarto"], 2), segno(x["scarto"], 2),
                 "%d%s" % (x["presenze"], " - %s" % POCHI if x["presenze"] < 3 else "")]
                for x in giu])

    md.h(2, "7. I piu' quotati che non sono scesi in campo")
    md.tabella(["Giocatore", "Squadra", "Ruolo", "Quotazione", "Perche' non compare"],
               [[g2["name"], g2["team"], g2["role"], fmt(g2["price"], 0),
                 ("rilevato con 0 minuti" if g2["id"] in visti
                  else "non compare fra i rilevati della giornata")] for g2 in assenti])
    md.t("_Il file dei voti non distingue infortunio, squalifica e scelta tecnica: "
         "il motivo va cercato altrove e, se non lo trovi, non va scritto._")
    md.t("")

    md.h(2, "8. COSA NON ABBIAMO")
    for r in ["I rigori segnati non sono distinti dai gol su azione: nel file dei voti c'e' "
              "solo la voce \"gol\". Non scrivere \"gol su rigore\" a partire da qui.",
              "Rigori sbagliati e rigori parati non compaiono fra i bonus della giornata.",
              "Il motivo per cui un giocatore non ha giocato (infortunio, squalifica, panchina) "
              "non e' nel file dei voti.",
              "xG dei singoli giocatori: non esistono nei nostri dati.",
              "Il voto di un giornale sportivo: i nostri sono voti FantaTB calcolati da noi, "
              "e vanno chiamati cosi'."]:
        md.t("- " + r)
    md.t("")

    payload = {"formato": "migliori", "data": data, "giornata": g,
               "stato_giornata": voti.get("status"), "giornate_chiuse": chiuse,
               "migliori": migliori, "peggiori": peggiori, "sopra_media": su,
               "sotto_media": giu, "conteggio_bonus": conteggi,
               "quotati_senza_minuti": [{"id": x["id"], "nome": x["name"], "squadra": x["team"],
                                         "prezzo": x["price"]} for x in assenti]}
    return md.testo(), payload


# ---------------------------------------------------------------- 4. CONFRONTO

def dossier_confronto(dati, data, opz, stato):
    s = stato["confronto"]
    ammessi, esclusi_pochi_minuti = [], 0
    for g in dati.per_prezzo:
        st = dati.stp.get(str(g["id"]))
        if not st:
            continue
        cur = aggrega(blocchi_lega(st.get("cur"), SERIE_A))
        minuti = (cur or {}).get("minuti") or 0
        if minuti < opz.min_minuti_cur:
            esclusi_pochi_minuti += 1
            continue
        ammessi.append(g)

    coppie = []
    for i, a in enumerate(ammessi):
        for b in ammessi[i + 1:]:
            if a["role"] != b["role"]:
                continue
            if abs(a["price"] - b["price"]) > opz.tolleranza_prezzo:
                continue
            coppie.append((a, b))
    if not coppie:
        raise DatiMancanti(
            "nessuna coppia utilizzabile: servono due giocatori dello stesso ruolo con "
            "quotazioni entro %d crediti di differenza ed entrambi sopra i %d minuti di "
            "Serie A 2026-27 (esclusi per pochi minuti: %d giocatori)"
            % (opz.tolleranza_prezzo, opz.min_minuti_cur, esclusi_pochi_minuti))

    coppie.sort(key=lambda c: (-(c[0]["price"] + c[1]["price"]), c[0]["name"], c[1]["name"]))
    usate = set(s.get("usate", []))
    giro = s.get("giro", 1)
    riusata = False

    chiave_data = s.get("assegnazioni", {}).get(data)
    scelta = None
    if chiave_data:
        for a, b in coppie:
            if _chiave(a["id"], b["id"]) == chiave_data:
                scelta, riusata = (a, b), True
                break
    if scelta is None:
        for a, b in coppie:
            if _chiave(a["id"], b["id"]) not in usate:
                scelta = (a, b)
                break
        if scelta is None:
            usate, giro, scelta = set(), giro + 1, coppie[0]

    a, b = scelta
    sa = sintesi(dati, a["id"], opz.min_minuti_prev, opz.min_minuti_cur)
    sb = sintesi(dati, b["id"], opz.min_minuti_prev, opz.min_minuti_cur)

    md = Md()
    intestazione(md, "X O Y? - %s contro %s" % (sa["nome"], sb["nome"]), data, dati,
                 "pezzo del mercoledi': due giocatori stesso ruolo e prezzo simile, "
                 "confronto secco su chi schierare")
    blocco_soglie(md, opz.min_minuti_prev, opz.min_minuti_cur)

    md.h(2, "1. Perche' questi due")
    md.voce("Criterio", "stesso ruolo, quotazioni entro %d crediti di differenza, entrambi con "
                        "almeno %d minuti giocati in Serie A 2026-27 (niente confronti fra chi "
                        "non gioca). Fra tutte le coppie ammesse prendo quella con la somma "
                        "delle quotazioni piu' alta, saltando le coppie gia' uscite"
            % (opz.tolleranza_prezzo, opz.min_minuti_cur))
    md.voce("Ruolo", "%s (%s)" % (a["role"], RUOLI.get(a["role"], ND)))
    md.voce("Quotazioni", "%s %d crediti, %s %d crediti (differenza %d)"
            % (sa["nome"], a["price"], sb["nome"], b["price"], abs(a["price"] - b["price"])))
    md.voce("Coppie ammesse dal criterio", "%d (giro %d)" % (len(coppie), giro))
    if riusata:
        md.voce("Nota", "per questa data la coppia era gia' stata assegnata: stesso dossier")
    md.t("")

    md.h(2, "2. I due a confronto")
    _tabella_confronto(md, sa, sb, opz)

    md.h(2, "3. Titolarita' e disponibilita'")
    md.tabella(["Voce", sa["nome"], sb["nome"]],
               [["Titolarita' FantaTB", fmt(sa["tit"], 0, "%") if sa["tit"] is not None else ND,
                 fmt(sb["tit"], 0, "%") if sb["tit"] is not None else ND],
                ["Probabilita' di partire titolare",
                 fmt(sa["prob_titolare"], 0, "%") if sa["prob_titolare"] is not None else ND,
                 fmt(sb["prob_titolare"], 0, "%") if sb["prob_titolare"] is not None else ND],
                ["Perche'", sa["prob_perche"] or ND, sb["prob_perche"] or ND],
                ["Infortunio segnalato", sa["inj"] or "nessuno", sb["inj"] or "nessuno"],
                ["Rientro previsto", sa["back"] or ND, sb["back"] or ND],
                ["Nella probabile formazione",
                 _riga_probabili(dati, {"id": sa["id"], "squadra": sa["squadra"]}),
                 _riga_probabili(dati, {"id": sb["id"], "squadra": sb["squadra"]})]])

    md.h(2, "4. Il prossimo impegno di ciascuno")
    for s2 in (sa, sb):
        sq = dati.squadra_per_nome.get(norm_team(s2["squadra"]))
        blocco_impegno(md, dati, sq, "Prossimo impegno di %s (%s)" % (s2["nome"], s2["squadra"]))

    md.h(2, "5. COSA NON ABBIAMO")
    for r in ["xG e xA dei due giocatori: non esistono nei nostri dati.",
              "Il calendario oltre la prossima giornata: non e' in questo dossier, "
              "quindi niente \"ha un calendario facile nelle prossime cinque\".",
              "Le scelte dell'allenatore: le probabilita' di titolarita' sono calcolate sulle "
              "ultime tre partite, non sono dichiarazioni.",
              "Quotazioni di altri listoni o fantavalori di mercato: usiamo solo il nostro listone."]:
        md.t("- " + r)
    md.t("")

    s["giro"] = giro
    s["usate"] = sorted(usate | {_chiave(a["id"], b["id"])})
    s.setdefault("assegnazioni", {})[data] = _chiave(a["id"], b["id"])

    payload = {"formato": "confronto", "data": data, "criterio":
               {"tolleranza_prezzo": opz.tolleranza_prezzo, "min_minuti_cur": opz.min_minuti_cur,
                "coppie_ammesse": len(coppie), "giro": giro},
               "a": sa, "b": sb}
    return md.testo(), payload


def _chiave(a, b):
    return "%d-%d" % (min(a, b), max(a, b))


def _tabella_confronto(md, sa, sb, opz):
    righe = [["Squadra", sa["squadra"] or ND, sb["squadra"] or ND],
             ["Quotazione", fmt(sa["prezzo"], 0), fmt(sb["prezzo"], 0)],
             ["Media voto FantaTB", fmt(sa["mv"], 2), fmt(sb["mv"], 2)],
             ["Fantamedia FantaTB", fmt(sa["fmv"], 2), fmt(sb["fmv"], 2)],
             ["Presenze con voto", fmt(sa["pres"], 0), fmt(sb["pres"], 0)],
             ["Gol (FantaTB)", fmt(sa["gol"], 0), fmt(sb["gol"], 0)],
             ["Assist (FantaTB)", fmt(sa["assist"], 0), fmt(sb["assist"], 0)],
             ["Minuti Serie A 2026-27", fmt(sa["minuti_cur"], 0), fmt(sb["minuti_cur"], 0)],
             ["Minuti Serie A 2025-26", fmt(sa["minuti_prev"], 0), fmt(sb["minuti_prev"], 0)]]
    for chiave, etichetta, dec in metriche_visibili(sa["ruolo"]):
        if chiave not in METRICHE_P90:
            continue
        for stagione, campo_min, soglia in (("2026-27", "cur", opz.min_minuti_cur),
                                            ("2025-26", "prev", opz.min_minuti_prev)):
            va = per90_agg(sa[campo_min], chiave, soglia)
            vb = per90_agg(sb[campo_min], chiave, soglia)
            if va is None and vb is None:
                continue
            righe.append(["%s ogni 90' (%s)" % (etichetta, stagione), fmt(va, 2), fmt(vb, 2)])
    for etichetta, campo in (("Voto medio 2026-27", "cur"), ("Voto medio 2025-26", "prev")):
        righe.append([etichetta, fmt((sa[campo] or {}).get("rating"), 2),
                      fmt((sb[campo] or {}).get("rating"), 2)])
    md.tabella(["Voce", sa["nome"], sb["nome"]], righe)
    for s2 in (sa, sb):
        for stagione, campo in (("2025-26", "prev"), ("2026-27", "cur")):
            nota = nota_p90_esclusi(s2[campo])
            if nota:
                md.t("**Attenzione, %s stagione %s.** %s" % (s2["nome"], stagione, nota))
                md.t("")


# ---------------------------------------------------------------- 5. RIGORISTI

def dossier_rigoristi(dati, data, opz):
    squadre = sorted({g["team"] for g in dati.listone["players"]})
    md = Md()
    intestazione(md, "I RIGORISTI - squadra per squadra", data, dati,
                 "pezzo quindicinale: chi batte i rigori in ogni squadra, con i numeri")

    md.h(2, "1. Come sono contati")
    md.voce("Competizioni", "Serie A e Coppa Italia, stagioni 2025-26 e 2026-27. "
                            "Amichevoli, coppe europee e nazionali NON sono contate")
    md.voce("A chi sono attribuiti", "al giocatore, non alla squadra. Se un rigore e' stato "
                                     "battuto con un altro club, la colonna \"dove\" lo dice")
    md.voce("Chi entra nell'elenco", "solo i giocatori presenti nel nostro listone: "
                                     "chi non e' nel listone non serve al fantacalcio")
    md.voce("Limite", "questi numeri dicono chi HA battuto rigori, non chi li battera'. "
                      "La gerarchia puo' essere cambiata: non spacciare il passato per "
                      "una designazione")
    md.t("")

    per_squadra, senza = [], []
    for nome in squadre:
        battitori, conquistatori = [], []
        for g in _giocatori_squadra(dati, nome):
            r = rigori(dati, g["id"])
            if not r:
                continue
            seg = sum(x["segnati"] for x in r)
            sba = sum(x["sbagliati"] for x in r)
            con = sum(x["conquistati"] for x in r)
            voce = {"id": g["id"], "nome": g["name"], "ruolo": g["role"], "prezzo": g["price"],
                    "segnati": seg, "sbagliati": sba, "conquistati": con, "dettaglio": r}
            if seg or sba:
                battitori.append(voce)
            if con:
                conquistatori.append(voce)
        battitori.sort(key=lambda x: (-x["segnati"], -x["sbagliati"], x["nome"]))
        conquistatori.sort(key=lambda x: (-x["conquistati"], x["nome"]))
        sq = dati.squadra_per_nome.get(norm_team(nome))
        pen_sq = (sq.get("penalty") or {}) if sq else {}
        per_squadra.append({"squadra": nome, "battitori": battitori,
                            "conquistatori": conquistatori,
                            "rigori_squadra_2026_27": {"segnati": pen_sq.get("scored"),
                                                       "battuti": pen_sq.get("total"),
                                                       "affidabile": dati.rigori_squadra_affidabili}})
        if not battitori:
            senza.append(nome)

    md.h(2, "2. Squadra per squadra")
    for blocco in per_squadra:
        md.h(3, blocco["squadra"])
        p = blocco["rigori_squadra_2026_27"]
        if p.get("affidabile"):
            md.voce("Rigori della squadra in questa stagione",
                    "%s segnati su %s battuti" % (fmt(p["segnati"], 0), fmt(p["battuti"], 0)))
        else:
            md.voce("Rigori della squadra in questa stagione",
                    "%s (vedi il punto 4: il campo non e' popolato per nessuna squadra)" % ND)
        if blocco["battitori"]:
            md.tabella(["Giocatore", "Ruolo", "Quot.", "Segnati", "Sbagliati", "Dove"],
                       [[x["nome"], x["ruolo"], fmt(x["prezzo"], 0), x["segnati"], x["sbagliati"],
                         "; ".join("%s %s con %s" % (d["lega"], d["stagione"], d["squadra"])
                                   for d in x["dettaglio"] if d["segnati"] or d["sbagliati"])]
                        for x in blocco["battitori"]])
        else:
            md.t("**Nessun rigorista chiaro nei dati.** Nessun giocatore del listone di questa "
                 "squadra risulta aver battuto un rigore in Serie A o Coppa Italia fra 2025-26 "
                 "e 2026-27. Nel pezzo va scritto cosi': non indicare un nome per intuito.")
            md.t("")
            if p.get("affidabile") and p["battuti"]:
                md.t("_Attenzione: la squadra ha comunque battuto %s rigori in questa stagione. "
                     "Chi li ha calciati non risulta dai dati per giocatore: potrebbe essere un "
                     "giocatore fuori dal listone o un dato non ancora aggiornato._"
                     % fmt(p["battuti"], 0))
                md.t("")
        if blocco["conquistatori"]:
            md.voce("Chi si procura piu' rigori",
                    ", ".join("%s (%d)" % (x["nome"], x["conquistati"])
                              for x in blocco["conquistatori"][:5]))
        else:
            md.voce("Chi si procura piu' rigori", "nessun rigore conquistato nei dati")
        md.t("")

    md.h(2, "3. Le squadre senza un rigorista nei dati")
    md.t(", ".join(senza) + "." if senza else "Nessuna: tutte hanno almeno un giocatore "
                                              "che ha battuto un rigore.")
    md.t("")

    md.h(2, "4. COSA NON ABBIAMO")
    mancano = []
    if not dati.rigori_squadra_affidabili:
        mancano.append("**Il totale dei rigori di ogni SQUADRA: non ce l'abbiamo, ed e' per "
                       "questo che sopra c'e' scritto \"%s\" e non uno zero.** %s. Nel pezzo "
                       "non scrivere ne' \"la squadra ha battuto N rigori\" ne' \"non ne ha "
                       "ancora battuto nessuno\": il dato manca, non e' zero. Gli unici rigori "
                       "affidabili di questo dossier sono quelli per GIOCATORE delle tabelle "
                       "qui sopra, che vengono da data/stats/players.json."
                       % (ND, dati.rigori_squadra_nota["lunga"]))
    for r in mancano + [
              "La designazione ufficiale del rigorista: nessuna squadra la pubblica e noi non "
              "l'abbiamo. Abbiamo solo chi li ha battuti.",
              "La gerarchia fra primo e secondo rigorista: non e' nei dati.",
              "I rigori battuti in coppe europee, amichevoli e nazionali: esclusi per scelta.",
              "I rigori parati dai portieri sono nel dato per giocatore ma non sono elencati qui: "
              "questo pezzo parla di chi li batte.",
              "Il momento della stagione in cui il rigore e' stato battuto: i dati sono totali."]:
        md.t("- " + r)
    md.t("")

    payload = {"formato": "rigoristi", "data": data,
               "competizioni": ["Serie A", "Coppa Italia"], "stagioni": ["2025-26", "2026-27"],
               "squadre": per_squadra, "squadre_senza_rigorista": senza}
    return md.testo(), payload


# ---------------------------------------------------------------- 6. SORPRESE

FASCE = [(21, 999, "21 crediti e oltre"), (16, 20, "da 16 a 20 crediti"),
         (11, 15, "da 11 a 15 crediti"), (6, 10, "da 6 a 10 crediti"),
         (1, 5, "da 1 a 5 crediti")]


def _fascia(prezzo):
    for lo, hi, etichetta in FASCE:
        if lo <= prezzo <= hi:
            return etichetta
    return "fuori fascia"


def _mediana(valori):
    v = sorted(x for x in valori if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def dossier_sorprese(dati, data, opz):
    ammessi, scartati = [], {"poche_presenze": 0, "pochi_minuti": 0, "senza_fantamedia": 0}
    for g in dati.listone["players"]:
        sch = dati.sch.get(str(g["id"])) or {}
        st = dati.stp.get(str(g["id"]))
        cur = aggrega(blocchi_lega((st or {}).get("cur"), SERIE_A)) if st else None
        minuti = (cur or {}).get("minuti") or 0
        if sch.get("fmv") is None or not g.get("price"):
            scartati["senza_fantamedia"] += 1
            continue
        if (sch.get("pres") or 0) < opz.min_presenze:
            scartati["poche_presenze"] += 1
            continue
        if minuti < opz.min_minuti_sorprese:
            scartati["pochi_minuti"] += 1
            continue
        ammessi.append({"id": g["id"], "nome": g["name"], "squadra": g["team"],
                        "ruolo": g["role"], "prezzo": g["price"], "fmv": sch["fmv"],
                        "mv": sch.get("mv"), "pres": sch.get("pres"), "tit": sch.get("tit"),
                        "gol": sch.get("gol"), "assist": sch.get("assist"), "minuti": minuti,
                        "fascia": _fascia(g["price"]),
                        "fmv_per_credito": sch["fmv"] / float(g["price"]),
                        "crediti_per_punto": g["price"] / float(sch["fmv"]) if sch["fmv"] else None})
    if not ammessi:
        raise DatiMancanti("nessun giocatore supera i requisiti minimi (almeno %d presenze con "
                           "voto e almeno %d minuti di Serie A 2026-27): scartati %s"
                           % (opz.min_presenze, opz.min_minuti_sorprese, scartati))

    # Mediana della fantamedia per ruolo e fascia di prezzo: serve a dire quanto uno rende
    # rispetto ai suoi simili senza inventare una curva.
    mediane = {}
    for x in ammessi:
        mediane.setdefault((x["ruolo"], x["fascia"]), []).append(x["fmv"])
    mediane = {k: _mediana(v) for k, v in mediane.items()}
    for x in ammessi:
        m = mediane.get((x["ruolo"], x["fascia"]))
        n = len([1 for y in ammessi if y["ruolo"] == x["ruolo"] and y["fascia"] == x["fascia"]])
        x["mediana_fascia"] = m
        x["scarto_mediana"] = (x["fmv"] - m) if m is not None else None
        x["quanti_in_fascia"] = n

    su = sorted(ammessi, key=lambda x: (-x["fmv_per_credito"], -x["fmv"], x["nome"]))[:20]
    giu = sorted(ammessi, key=lambda x: (x["fmv_per_credito"], x["fmv"], x["nome"]))[:20]

    md = Md()
    intestazione(md, "LE SORPRESE - chi rende piu' e chi meno di quanto costa", data, dati,
                 "pezzo del sabato: fantamedia rapportata alla quotazione")

    md.h(2, "1. Come sono scelti (dichiaralo nel pezzo)")
    md.voce("Presenze minime con voto", "%d" % opz.min_presenze)
    md.voce("Minuti minimi in Serie A 2026-27", "%d" % opz.min_minuti_sorprese)
    md.voce("Perche' queste soglie", "senza un minimo di partite vincerebbe sempre un giocatore "
                                     "da 1 credito con una presenza fortunata: quel numero non "
                                     "dice niente")
    md.voce("Giocatori ammessi", "%d su %d del listone" % (len(ammessi),
                                                           len(dati.listone["players"])))
    md.voce("Esclusi", "%d senza fantamedia o senza quotazione, %d con troppe poche presenze, "
                       "%d con troppi pochi minuti"
            % (scartati["senza_fantamedia"], scartati["poche_presenze"], scartati["pochi_minuti"]))
    md.voce("Indice usato", "fantamedia divisa per la quotazione (punti di fantamedia per "
                            "credito speso). Piu' alto e' meglio")
    md.voce("Secondo indice", "scarto fra la sua fantamedia e la MEDIANA dei pari ruolo della "
                              "stessa fascia di prezzo: dice se rende piu' o meno di chi costa "
                              "come lui. E' il confronto da preferire nel pezzo")
    md.voce("Fasce di prezzo", "; ".join(e for _, _, e in FASCE))
    md.voce("Mediana usabile", "solo se nella fascia ci sono almeno %d giocatori ammessi"
            % opz.min_fascia)
    md.t("")

    md.h(2, "2. Chi rende di piu' per credito speso")
    md.t("_Attenzione, e' l'indice piu' fragile: dividere per la quotazione premia quasi sempre "
         "chi costa 1 o 2 crediti, perche' il denominatore e' piccolo. Serve per dire \"costa "
         "niente e porta voto\", non per dire \"e' il migliore\". Il confronto corretto fra "
         "giocatori di prezzo diverso e' quello del punto 4._")
    _tabella_sorprese(md, su)

    md.h(2, "3. Chi rende di meno per credito speso")
    md.t("_Stesso limite al contrario: in fondo a questa classifica finiscono per forza i piu' "
         "cari. Un giocatore da 30 crediti non puo' vincerla nemmeno giocando benissimo._")
    _tabella_sorprese(md, giu)

    md.h(2, "4. Rispetto a chi costa come lui (il confronto piu' onesto)")
    md.t("_Scarto fra la sua fantamedia e la MEDIANA dei pari ruolo della stessa fascia di "
         "prezzo. Qui un giocatore da 30 crediti e uno da 2 competono ciascuno con i propri "
         "simili. Mostro solo le fasce con almeno %d giocatori ammessi: sotto, la mediana e' "
         "un numero che non regge._" % opz.min_fascia)
    solidi = [x for x in ammessi if x["scarto_mediana"] is not None
              and x["quanti_in_fascia"] >= opz.min_fascia]
    if solidi:
        meglio = sorted(solidi, key=lambda x: (-x["scarto_mediana"], x["nome"]))[:15]
        peggio = sorted(solidi, key=lambda x: (x["scarto_mediana"], x["nome"]))[:15]
        md.h(3, "Rendono piu' dei pari fascia")
        _tabella_sorprese(md, meglio)
        md.h(3, "Rendono meno dei pari fascia")
        _tabella_sorprese(md, peggio)
    else:
        md.t("**%s**: nessuna fascia di prezzo ha almeno %d giocatori ammessi, quindi nessuna "
             "mediana e' abbastanza solida per fare questo confronto." % (ND, opz.min_fascia))
        md.t("")
        meglio, peggio = [], []

    md.h(2, "5. Ruolo per ruolo")
    for ruolo in ("P", "D", "C", "A"):
        gruppo = [x for x in ammessi if x["ruolo"] == ruolo]
        md.h(3, "%s (%d ammessi)" % (RUOLI_PL.get(ruolo, ruolo).capitalize(), len(gruppo)))
        if not gruppo:
            md.t("**%s**: nessun %s supera le soglie." % (ND, RUOLI.get(ruolo, ruolo)))
            md.t("")
            continue
        gruppo.sort(key=lambda x: (-x["fmv_per_credito"], x["nome"]))
        _tabella_sorprese(md, gruppo[:6] + ([] if len(gruppo) <= 12 else gruppo[-6:]))

    md.h(2, "6. Le mediane di riferimento")
    md.tabella(["Ruolo", "Fascia di prezzo", "Mediana della fantamedia", "Quanti giocatori"],
               [[RUOLI.get(k[0], k[0]), k[1], fmt(v, 2),
                 len([1 for x in ammessi if x["ruolo"] == k[0] and x["fascia"] == k[1]])]
                for k, v in sorted(mediane.items()) if v is not None])

    md.h(2, "7. COSA NON ABBIAMO")
    for r in ["Il prezzo pagato all'asta dai fantallenatori: usiamo la quotazione del listone "
              "ufficiale, che e' un'altra cosa.",
              "La fantamedia attesa o proiettata: non facciamo previsioni, qui c'e' solo "
              "quello che e' successo.",
              "La difficolta' del calendario gia' affrontato: due fantamedie uguali possono "
              "nascere da avversari diversissimi e noi non lo pesiamo.",
              "xG dei giocatori: non esistono nei nostri dati.",
              "Con poche giornate giocate questi numeri si muovono molto: dillo nel pezzo."]:
        md.t("- " + r)
    md.t("")

    payload = {"formato": "sorprese", "data": data,
               "soglie": {"min_presenze": opz.min_presenze,
                          "min_minuti": opz.min_minuti_sorprese},
               "ammessi": len(ammessi), "scartati": scartati,
               "rendono_di_piu": su, "rendono_di_meno": giu,
               "sopra_la_mediana_di_fascia": meglio, "sotto_la_mediana_di_fascia": peggio,
               "mediane": {"%s|%s" % k: v for k, v in mediane.items()}}
    return md.testo(), payload


def _tabella_sorprese(md, elenco):
    md.tabella(["Giocatore", "Squadra", "Ruolo", "Quot.", "Fantamedia", "Fantamedia per credito",
                "Crediti per punto", "Mediana della sua fascia", "Scarto dalla mediana",
                "Presenze", "Minuti"],
               [[x["nome"], x["squadra"], x["ruolo"], fmt(x["prezzo"], 0), fmt(x["fmv"], 2),
                 fmt(x["fmv_per_credito"], 3), fmt(x["crediti_per_punto"], 2),
                 fmt(x["mediana_fascia"], 2), segno(x["scarto_mediana"], 2),
                 fmt(x["pres"], 0), fmt(x["minuti"], 0)] for x in elenco])


# ---------------------------------------------------------------- riga di comando

FORMATI = {"giocatore": "GIOCATORE DEL GIORNO", "cartello": "PARTITA DI CARTELLO",
           "migliori": "MIGLIORI E PEGGIORI", "confronto": "X O Y?",
           "rigoristi": "I RIGORISTI", "sorprese": "LE SORPRESE"}


def opzioni(argv):
    ap = argparse.ArgumentParser(
        description="Prepara i numeri (json + md) per i sei formati fanta di TransferBeat.")
    ap.add_argument("formato", choices=sorted(FORMATI))
    ap.add_argument("--data", default=None, help="data del dossier, AAAA-MM-GG (default: oggi UTC)")
    ap.add_argument("--dry", action="store_true", help="stampa il .md a video e non scrive nulla")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "dossier"),
                    help="cartella di destinazione (default: data/dossier)")
    ap.add_argument("--soglia-prezzo", type=int, default=8, dest="soglia_prezzo",
                    help="giocatore del giorno: quotazione minima per entrare in rotazione")
    ap.add_argument("--min-minuti-prev", type=int, default=MIN_MIN_PREV, dest="min_minuti_prev",
                    help="minuti minimi per i per-90 della stagione 2025-26")
    ap.add_argument("--min-minuti-cur", type=int, default=MIN_MIN_CUR, dest="min_minuti_cur",
                    help="minuti minimi per i per-90 della stagione 2026-27")
    ap.add_argument("--tolleranza-prezzo", type=int, default=3, dest="tolleranza_prezzo",
                    help="X o Y: differenza massima di quotazione fra i due")
    ap.add_argument("--min-presenze", type=int, default=2, dest="min_presenze",
                    help="sorprese: presenze minime con voto")
    ap.add_argument("--min-minuti-sorprese", type=int, default=120, dest="min_minuti_sorprese",
                    help="sorprese: minuti minimi in Serie A 2026-27")
    ap.add_argument("--min-fascia", type=int, default=4, dest="min_fascia",
                    help="sorprese: quanti giocatori servono in una fascia perche' la sua "
                         "mediana sia usabile")
    return ap.parse_args(argv)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    opz = opzioni(argv)
    data = opz.data or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        sys.stderr.write("Data non valida: %s (serve AAAA-MM-GG)\n" % data)
        return 2

    try:
        dati = Dati()
        stato = leggi_stato(opz.out)
        if opz.formato == "giocatore":
            testo, payload = dossier_giocatore(dati, data, opz, stato)
        elif opz.formato == "cartello":
            testo, payload = dossier_cartello(dati, data, opz)
        elif opz.formato == "migliori":
            testo, payload = dossier_migliori(dati, data, opz)
        elif opz.formato == "confronto":
            testo, payload = dossier_confronto(dati, data, opz, stato)
        elif opz.formato == "rigoristi":
            testo, payload = dossier_rigoristi(dati, data, opz)
        else:
            testo, payload = dossier_sorprese(dati, data, opz)
    except DatiMancanti as e:
        # Fallire rumorosamente: nessun file scritto, motivo esplicito, codice di uscita 3.
        sys.stderr.write("IMPOSSIBILE PRODURRE IL DOSSIER \"%s\" del %s.\nMotivo: %s\n"
                         "Non ho scritto nessun file.\n" % (opz.formato, data, e))
        return 3

    if opz.dry:
        sys.stdout.write(testo)
        return 0

    if not os.path.isdir(opz.out):
        os.makedirs(opz.out)
    base = os.path.join(opz.out, "%s-%s" % (opz.formato, data))
    with open(base + ".json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True, default=str)
        f.write("\n")
    with open(base + ".md", "w", encoding="utf-8", newline="\n") as f:
        f.write(testo)
    if opz.formato in ("giocatore", "confronto"):
        scrivi_stato(opz.out, stato)
    sys.stdout.write("Scritti:\n  %s.json\n  %s.md\n" % (base, base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
