#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mercato.py - accende e spegne la macchina del calciomercato di TransferBeat.

PERCHE' ESISTE: kb/RIPARTENZA.md §7 descrive la riaccensione come una sequenza di sei
modifiche reversibili da rifare a gennaio e a giugno. Scritta a mano in una KB, fra quattro
mesi va riletta tutta e basta sbagliare un campo. Lo stato piu' pericoloso non e' "tutto
spento": e' quello MISTO (parole chiave e feed di mercato accesi, scout spento), perche' la
board raccoglie notizie di mercato senza che nessuno estragga i movimenti da->a e nessuno se
ne accorge: ogni percorso del codice degrada con un default e il workflow resta verde
(kb/RIPARTENZA.md §5, "guasto silenzioso"). Qui la procedura diventa un comando solo.

  py -X utf8 scripts/mercato.py --stato
  py -X utf8 scripts/mercato.py --accendi [--dry] [--con-mondo]
  py -X utf8 scripts/mercato.py --spegni  [--dry] [--con-mondo]

Codici di uscita: 0 = coerente / fatto e NIENTE resta da fare; 2 = la macchina non e' in uno
stato buono o non lo si e' potuto verificare (stato misto, stato SCONOSCIUTO, feed rifiutato,
verifica dei feed saltata, passo 1 ancora da fare a mano in update.yml); 1 = errore.
Il 2 e' voluto largo: qui un "0" significa "puoi andare a dormire", e non va detto a meta'.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

# La console italiana e' cp1252 e muore sugli accenti (kb/RIPARTENZA.md §3): lo script si
# difende da solo anche se qualcuno lo lancia senza -X utf8.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RADICE_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ACCESO, SPENTO, MISTO, IGNOTO, NA = "ACCESO", "SPENTO", "MISTO", "IGNOTO", "N/A"

# ---------------------------------------------------------------- §7 passo 2: parole chiave
# La query di Google News e' kw[lang] + squadra["search"] (build.py, build_squadra).
KW = {
    ACCESO: {"it": "calciomercato", "en": "football transfer", "es": "fichajes"},
    SPENTO: {"it": "notizie calcio", "en": "football news", "es": "noticias fútbol"},
}

# ---------------------------------------------------------------- §7 passo 3: feed diretti
# I due feed di mercato tolti il 2026-09-02 da data/sources.json, entrambi vivi allora.
# CONFRONTATO CON LA VERITA' (git show pre-riconversione:data/sources.json): prima della
# riconversione i feed erano cinque; oggi in data/sources.json ne mancano tre rispetto ad
# allora, cioe' Gazzetta calciomercato + questi due. BBC Sport e Football Italia non sono mai
# stati tolti. URL, tier e lang qui sotto sono identici a quelli del tag.
# UNICA DIFFERENZA VOLUTA, il campo "nome": al tag si chiamavano "The Guardian" e "Marca",
# ma il file di oggi ha gia' tre voci "The Guardian - ..." e una "Marca" (primera-division).
# Rimettere i nomi nudi darebbe due voci diverse con la stessa etichetta e la pagina fonti
# le mostrerebbe come se fossero lo stesso feed: qui sono qualificati con la sezione.
# Gazzetta calciomercato NON e' in questa lista (§7: morto dal 2023-11-14) ed e' in FEED_VIETATI.
FEED_MERCATO = [
    {"nome": "The Guardian - Transfer window",
     "url": "https://www.theguardian.com/football/transfer-window/rss", "tier": 3, "lang": "en"},
    {"nome": "Marca - Mercado fichajes",
     "url": "https://e00-marca.uecdn.es/rss/futbol/mercado-fichajes.xml", "tier": 3, "lang": "es"},
]

# Feed che la §7 vieta esplicitamente di rimettere. Lo script non li aggiunge mai e se li
# trova nel file lo segnala: sono voci che non portano nulla e non lo segnala nessun altro.
FEED_VIETATI = {
    "https://www.gazzetta.it/rss/calciomercato.xml":
        "morto dal 2023-11-14; tutti i feed Gazzetta sono fermi (calcio.xml a marzo 2026, serie-a.xml al 2023)",
    "https://www.gazzetta.it/rss/calcio.xml":
        "fermo da marzo 2026 (§7)",
    "https://www.gazzetta.it/rss/serie-a.xml":
        "fermo dal 2023 (§7)",
}

# ------------------------------------------------------- §7 passo 5 (FACOLTATIVO): mondo_home
# La §7 elenca solo le query; le etichette per lingua sono quelle usate dal front-end
# (build_home legge m["label"][lang]) e vanno per forza scritte qui.
MONDO = {
    ACCESO: [
        {"search": "Brazil football",
         "label": {"it": "Brasile", "en": "Brazil", "es": "Brasil"}},
        {"search": "Saudi Pro League",
         "label": {"it": "Arabia Saudita", "en": "Saudi Arabia", "es": "Arabia Saudí"}},
        {"search": "MLS Messi",
         "label": {"it": "MLS", "en": "MLS", "es": "MLS"}},
        {"search": "national team World Cup",
         "label": {"it": "Nazionali", "en": "National teams", "es": "Selecciones"}},
    ],
    SPENTO: [
        {"search": "Champions League",
         "label": {"it": "Champions League", "en": "Champions League", "es": "Champions League"}},
        {"search": "Europa League",
         "label": {"it": "Europa League", "en": "Europa League", "es": "Europa League"}},
        {"search": "Conference League",
         "label": {"it": "Conference League", "en": "Conference League", "es": "Conference League"}},
        {"search": "Bundesliga",
         "label": {"it": "Bundesliga", "en": "Bundesliga", "es": "Bundesliga"}},
    ],
}

STEP_WORKFLOW = "Genera i dati"   # nome dello step di update.yml che lancia build.py


class Rifiuto(Exception):
    """Il file non ha il formato che questo script sa modificare in modo reversibile.
    Meglio fermarsi e dirlo che riscrivere un file dati con un formato diverso."""


# ============================================================================ utilita' file
def leggi(path):
    """newline='' per NON tradurre i fine riga: i file del repo sono CRLF (autocrlf) e
    riscriverli in LF farebbe un diff di 400 righe e romperebbe la reversibilita'."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def scrivi(path, testo):
    tmp = path + ".tb_tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(testo)
    os.replace(tmp, path)


def eol_di(testo):
    return "\r\n" if "\r\n" in testo else "\n"


def sha(testo):
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:12]


def rel(radice, path):
    try:
        return os.path.relpath(path, radice).replace("\\", "/")
    except Exception:
        return path


def righe(testo):
    """Spezza tenendo i fine riga attaccati: cosi' ogni riga non toccata torna sul disco
    byte per byte come l'abbiamo letta."""
    return testo.splitlines(keepends=True)


def _blocco(rs, chiave, apre, chiude):
    """Indici (inizio_contenuto, riga_chiusura) del blocco JSON "chiave": apre ... chiude.
    Lavoriamo sul TESTO e non su un json.dump globale perche' un dump riscriverebbe
    l'intero file (allineamenti compresi) e renderebbe illeggibile il diff."""
    ini = None
    for i, r in enumerate(rs):
        if '"%s"' % chiave in r and apre in r:
            ini = i
            break
    if ini is None:
        raise Rifiuto('chiave "%s" non trovata' % chiave)
    for j in range(ini + 1, len(rs)):
        if rs[j].strip().startswith(chiude):
            return ini, j
    raise Rifiuto('blocco "%s" senza chiusura "%s"' % (chiave, chiude))


# ------------------------------------------------------- passo 2: kw di data/teams.json
def kw_leggi(testo):
    """Ritorna {lang: valore} leggendo il JSON (la verita') e non il testo."""
    dati = json.loads(testo)
    kw = dati.get("kw") or {}
    return {l: kw.get(l) for l in ("it", "en", "es")}


def kw_scrivi(testo, voluto):
    """Sostituisce SOLO il valore delle tre righe di "kw", lasciando indentazione,
    virgole e fine riga come stanno. Ritorna (nuovo_testo, [descrizioni])."""
    rs = righe(testo)
    ini, fine = _blocco(rs, "kw", "{", "}")
    fatti = []
    for i in range(ini + 1, fine):
        riga = rs[i]
        m = re.match(r'^(\s*"(it|en|es)"\s*:\s*)(".*?")(\s*,?\s*)$', riga.rstrip("\r\n"))
        if not m:
            continue
        lang = m.group(2)
        vecchio = json.loads(m.group(3))
        nuovo = voluto[lang]
        if vecchio == nuovo:
            continue
        coda = riga[len(riga.rstrip("\r\n")):]
        rs[i] = m.group(1) + json.dumps(nuovo, ensure_ascii=False) + m.group(4) + coda
        fatti.append('kw.%s: "%s" -> "%s"' % (lang, vecchio, nuovo))
    return "".join(rs), fatti


# --------------------------------------------- passo 3: feeds di data/sources.json
def feeds_leggi(testo):
    dati = json.loads(testo)
    return dati.get("feeds") or []


def _feeds_righe(rs):
    """Le voci di sources.json sono una per riga: le rileggo come JSON una a una.
    Se il formato cambia (voce su piu' righe) mi fermo invece di indovinare."""
    ini, fine = _blocco(rs, "feeds", "[", "]")
    voci = []
    for i in range(ini + 1, fine):
        testo_riga = rs[i].rstrip("\r\n")
        if not testo_riga.strip():
            continue
        core = testo_riga.rstrip()
        core = core[:-1] if core.endswith(",") else core
        try:
            voce = json.loads(core)
        except Exception:
            raise Rifiuto("data/sources.json: la voce alla riga %d non sta su una riga sola,"
                          " il formato non e' quello previsto: intervieni a mano" % (i + 1))
        voci.append((core, voce))
    return ini, fine, voci


def _riga_feed(feed, colonna, indent):
    """Ricostruisce una riga nello stile del file: nome allineato alla colonna di "url"."""
    testa = '{ "nome": %s,' % json.dumps(feed["nome"], ensure_ascii=False)
    if colonna and len(testa) < colonna:
        testa = testa.ljust(colonna)
    else:
        testa += " "
    return indent + testa + '"url": %s, "tier": %d, "lang": %s }' % (
        json.dumps(feed["url"], ensure_ascii=False), int(feed["tier"]),
        json.dumps(feed["lang"], ensure_ascii=False))


def feeds_scrivi(testo, da_aggiungere, da_togliere):
    """Aggiunge/toglie voci mantenendo intatte le righe non toccate e sistemando le virgole
    (l'ultima voce dell'array non ne ha). Ritorna (nuovo_testo, [descrizioni])."""
    rs = righe(testo)
    ini, fine, voci = _feeds_righe(rs)
    eol = eol_di(testo)
    indent = re.match(r"\s*", rs[ini + 1]).group(0) if fine > ini + 1 else "    "
    colonna = 0
    for core, _ in voci:
        p = core.find('"url"')
        if p > 0:
            colonna = max(colonna, p - len(indent) if core.startswith(indent) else p)
    presenti = {v.get("url") for _, v in voci}
    fatti = []
    tenuti = []
    urls_togliere = {f["url"] for f in da_togliere}
    for core, voce in voci:
        if voce.get("url") in urls_togliere:
            fatti.append('- tolgo  "%s" (%s)' % (voce.get("nome"), voce.get("url")))
            continue
        tenuti.append(core if core.startswith(indent) else indent + core.strip())
    for f in da_aggiungere:
        if f["url"] in presenti:
            continue
        tenuti.append(_riga_feed(f, colonna, indent))
        fatti.append('+ aggiungo "%s" (%s, tier %d, %s)' % (f["nome"], f["url"], f["tier"], f["lang"]))
    if not fatti:
        return testo, []
    if not tenuti:
        raise Rifiuto("data/sources.json resterebbe senza feed: mi fermo")
    corpo = []
    for k, core in enumerate(tenuti):
        corpo.append(core + ("," if k < len(tenuti) - 1 else "") + eol)
    nuovo = "".join(rs[:ini + 1] + corpo + rs[fine:])
    return nuovo, fatti


# ------------------------------------- passo 5 (facoltativo): mondo_home di data/teams.json
def mondo_leggi(testo):
    return (json.loads(testo).get("mondo_home") or [])


def mondo_scrivi(testo, voluto):
    """Riscrive SOLO il blocco mondo_home nello stile di json.dump(indent=2) del file."""
    rs = righe(testo)
    ini, fine = _blocco(rs, "mondo_home", "[", "]")
    eol = eol_di(testo)
    interno = json.dumps(voluto, ensure_ascii=False, indent=2).split("\n")[1:-1]
    corpo = [("  " + r).rstrip() + eol for r in interno]
    nuovo = "".join(rs[:ini + 1] + corpo + rs[fine:])
    return nuovo, ["mondo_home: %s" % ", ".join(v["search"] for v in voluto)]


# ------------------------------------------------- passo 1: SCOUT_OFF in update.yml (SOLA LETTURA)
def scout_default_di_build(path_build):
    """Il default vero lo dice il codice, non la KB: os.environ.get("SCOUT_OFF", "1")."""
    try:
        src = leggi(path_build)
    except Exception:
        return None, None
    m = re.search(r'environ\.get\(\s*"SCOUT_OFF"\s*,\s*"([01])"\s*\)', src)
    if not m:
        return None, None
    riga = src[:m.start()].count("\n") + 1
    return m.group(1), riga


def _indent_di(riga):
    return len(riga) - len(riga.lstrip(" "))


def scout_blocco_yml(testo):
    """Trova A MANO, sul testo, i confini dello step che lancia build.py e l'INDENTAZIONE VERA
    del suo blocco env:.
    PERCHE' a mano e non con PyYAML: le istruzioni che stampiamo all'utente devono ricalcare il
    file com'e' scritto, e un parser YAML restituisce la struttura ma butta via colonne, ordine
    e commenti. Un'indentazione decisa a costante (era 9/11, il file usa 8/10) produce un
    workflow INVALIDO, e un workflow invalido non avvisa nessuno: ha gia' fermato il sito per
    36 ore (kb/RIPARTENZA.md §5). Ritorna None se lo step non si trova."""
    rs = testo.splitlines()
    ini = col_trattino = None
    for i, r in enumerate(rs):
        m = re.match(r'^(\s*)-\s+name:\s*(.+?)\s*$', r)
        if m and m.group(2).strip().strip('"').strip("'") == STEP_WORKFLOW:
            ini, col_trattino = i, len(m.group(1))
            break
    if ini is None:
        # Ripiego sul contenuto: lo step giusto e' quello che lancia build.py, comunque si chiami.
        for i, r in enumerate(rs):
            if "build.py" in r and not r.lstrip().startswith("#"):
                for j in range(i, -1, -1):
                    m = re.match(r'^(\s*)-\s+\S', rs[j])
                    if m:
                        ini, col_trattino = j, len(m.group(1))
                        break
                break
    if ini is None:
        return None
    col_chiave = col_trattino + 2          # colonna di "name:", "env:", "run:" dentro lo step
    fine = len(rs)
    for j in range(ini + 1, len(rs)):
        if not rs[j].strip():
            continue
        if _indent_di(rs[j]) < col_chiave:  # dedent: e' iniziato un altro step o un'altra chiave
            fine = j
            break
    b = {"riga_step": ini, "fine_step": fine, "col_chiave": col_chiave,
         "col_figlio": col_chiave + 2, "riga_env": None, "fine_env": None,
         "riga_scout": None, "riga_run": None, "n_figli_env": 0,
         "nome": rs[ini].split("name:", 1)[1].strip().strip('"').strip("'")}
    for j in range(ini + 1, fine):
        r = rs[j]
        if _indent_di(r) != col_chiave or not r.strip():
            continue
        if re.match(r'^\s*env\s*:\s*(#.*)?$', r):
            b["riga_env"] = j
        elif re.match(r'^\s*run\s*:', r) and b["riga_run"] is None:
            b["riga_run"] = j
    if b["riga_env"] is not None:
        j = b["riga_env"] + 1
        primo = True
        while j < fine and (not rs[j].strip() or _indent_di(rs[j]) > col_chiave):
            if rs[j].strip():
                if primo:
                    b["col_figlio"] = _indent_di(rs[j])   # l'indentazione VERA dei figli di env
                    primo = False
                b["n_figli_env"] += 1
                if re.match(r'^\s*SCOUT_OFF\s*:', rs[j]):
                    b["riga_scout"] = j
            j += 1
        b["fine_env"] = j
    return b


def _scout_da_doc(doc):
    """Cerca SCOUT_OFF nello step giusto di un workflow gia' interpretato da PyYAML.
    Ritorna (nome_step, presente, valore) oppure (None, False, None) se lo step non c'e'.
    Un YAML valido ma di forma inattesa (una stringa, una lista) non deve far esplodere lo
    script ne' fargli dire qualcosa: cade nel ramo "step non trovato", cioe' IGNOTO."""
    if not isinstance(doc, dict):
        return None, False, None
    # GitHub Actions UNISCE tre livelli di env - workflow, job e step - e lo step vince sugli altri.
    # Guardare solo quello dello step significa rispondere "SPENTO" con sicurezza mentre lo scout gira
    # davvero, perche' SCOUT_OFF era stato messo a livello di job o in cima al file. E' esattamente il
    # tipo di risposta affermativa-e-sbagliata che questo script deve evitare.
    def _env(x):
        e = x.get("env") if isinstance(x, dict) else None
        return e if isinstance(e, dict) else {}
    env_wf = _env(doc)
    for _, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        env_job = _env(job)
        for st in (job.get("steps") or []):
            if not isinstance(st, dict):
                continue
            nome = (st.get("name") or "").strip()
            run = str(st.get("run") or "")
            if nome == STEP_WORKFLOW or "build.py" in run:
                dove = nome or run.strip()
                for env, livello in ((_env(st), "step"), (env_job, "job"), (env_wf, "workflow")):
                    if "SCOUT_OFF" in env:
                        etichetta = dove if livello == "step" else (dove + " (ereditato dal livello " + livello + ")")
                        return etichetta, True, str(env["SCOUT_OFF"]).strip().strip('"')
                return dove, False, None
    return None, False, None


def scout_leggi(path_yml, path_build):
    """update.yml NON e' un file di questo script: qui si LEGGE soltanto e si dice
    all'utente cosa cambiare. Un workflow riscritto male e' gia' costato 36 ore di sito
    fermo (kb/RIPARTENZA.md §5), e il file appartiene alla sessione principale.

    REGOLA DI QUESTA FUNZIONE: non risponde MAI in modo affermativo a una domanda a cui non
    ha potuto rispondere. Se manca lo strumento per leggere lo YAML (PyYAML NON e' in
    requirements.txt: su una macchina pulita manca davvero) o il file non e' interpretabile,
    lo stato del passo 1 e' IGNOTO e viene detto a chiare lettere. Il vecchio ripiego cercava
    SCOUT_OFF con una regex su TUTTO il file, senza sapere in quale step si trovasse: bastava
    che la riga fosse in un altro step - dove build.py non gira - per far dire allo script
    "ACCESO / coerente / uscita 0" con lo scout spento. Una bugia che tace e' il guasto che
    questo progetto paga da sempre."""
    info = {"file": path_yml, "step": None, "valore": None, "presente": False,
            "errore": None, "ignoto": False, "indizio": None, "blocco": None, "testo": None}
    info["default"], info["default_riga"] = scout_default_di_build(path_build)
    try:
        testo = leggi(path_yml)
    except Exception as e:
        info["ignoto"] = True
        info["errore"] = "%s non leggibile (%s): stato del passo 1 SCONOSCIUTO" % (path_yml, e)
        return info
    info["testo"] = testo
    info["blocco"] = scout_blocco_yml(testo)
    if info["blocco"]:
        info["step"] = info["blocco"]["nome"]

    try:
        import yaml
    except ImportError:
        info["ignoto"] = True
        info["errore"] = ("PyYAML non installato (e non e' in requirements.txt): non posso "
                          "stabilire in quale step si trovi SCOUT_OFF, quindi lo stato del "
                          "passo 1 e' SCONOSCIUTO. Rimedio: py -m pip install pyyaml")
        # Un indizio si puo' dare, ma va marchiato come tale: NON e' una risposta.
        m = re.search(r'^\s*SCOUT_OFF\s*:\s*(\S+)\s*$', testo, re.M)
        if m:
            info["indizio"] = ('c\'e\' una riga SCOUT_OFF: %s (riga %d del file) ma non so a '
                               'quale step appartenga: se non e\' "%s" non tocca build.py e '
                               'lo scout resta spento'
                               % (m.group(1), testo[:m.start()].count("\n") + 1, STEP_WORKFLOW))
        else:
            info["indizio"] = "nel file non compare nessuna riga SCOUT_OFF"
        return info

    try:
        doc = yaml.safe_load(testo) or {}
    except Exception as e:
        info["ignoto"] = True
        info["errore"] = ("update.yml NON e' YAML valido (%s): il workflow non parte affatto e "
                          "lo stato del passo 1 e' SCONOSCIUTO" % e)
        return info

    nome, presente, valore = _scout_da_doc(doc)
    if nome is None:
        info["ignoto"] = True
        info["errore"] = ('nessuno step "%s" (ne uno che lanci build.py) nel workflow: '
                          'stato del passo 1 SCONOSCIUTO' % STEP_WORKFLOW)
        return info
    info["step"], info["presente"], info["valore"] = nome, presente, valore
    if not presente and info["default"] is None:
        # Senza la riga nel workflow lo stato lo decide il default di build.py: se non sono
        # riuscito a leggerlo, di nuovo, non lo so - e non lo invento.
        info["ignoto"] = True
        info["errore"] = ("SCOUT_OFF assente dallo step e default non leggibile in "
                          "scripts/build.py: stato del passo 1 SCONOSCIUTO")
    return info


def scout_stato(info):
    """La regola e' quella VERA di build.py (riga `if os.environ.get("SCOUT_OFF","1") == "1"`):
    spento SOLO se il valore e' esattamente "1". Un "2" o un "false" lascerebbero lo scout
    ACCESO, e dire "SPENTO" perche' non e' "0" sarebbe un'altra risposta comoda e falsa."""
    if info.get("ignoto"):
        return IGNOTO
    if info["presente"]:
        return SPENTO if info["valore"] == "1" else ACCESO
    return SPENTO if info.get("default") == "1" else ACCESO   # assente = default di build.py


def scout_simula(testo, blocco, verso):
    """Costruisce IN MEMORIA il testo che update.yml avrebbe dopo la modifica del passo 1,
    usando l'indentazione vera letta dal file. Non scrive niente: serve a stampare istruzioni
    esatte e - soprattutto - a poterle PROVARE con yaml.safe_load prima che l'utente incolli.
    Ritorna (nuovo_testo, [descrizioni]) oppure (None, [motivo]) se non sa dove intervenire."""
    rs = righe(testo)
    eol = eol_di(testo)
    figlio = " " * blocco["col_figlio"]
    fatti = []
    if verso == ACCESO:
        if blocco["riga_scout"] is not None:
            i = blocco["riga_scout"]
            ind = " " * _indent_di(rs[i])
            rs[i] = ind + 'SCOUT_OFF: "0"' + eol
            fatti.append('cambio il valore della riga SCOUT_OFF gia' + "' presente")
        elif blocco["riga_env"] is not None:
            rs.insert(blocco["fine_env"], figlio + 'SCOUT_OFF: "0"' + eol)
            fatti.append('aggiungo una riga in fondo al blocco env: dello step')
        else:
            dove = blocco["riga_run"] if blocco["riga_run"] is not None else blocco["riga_step"] + 1
            rs[dove:dove] = [" " * blocco["col_chiave"] + "env:" + eol,
                             " " * (blocco["col_chiave"] + 2) + 'SCOUT_OFF: "0"' + eol]
            fatti.append("lo step non ha un blocco env:, ne aggiungo uno con dentro SCOUT_OFF")
    else:
        if blocco["riga_scout"] is None:
            # Niente da togliere: allora si SCRIVE lo spegnimento esplicito. Contare sul
            # default di build.py va bene solo quando lo si e' potuto leggere; qui siamo
            # arrivati perche' lo stato non era gia' SPENTO, quindi non ci si affida.
            if blocco["riga_env"] is not None:
                rs.insert(blocco["fine_env"], figlio + 'SCOUT_OFF: "1"' + eol)
            else:
                dove = blocco["riga_run"] if blocco["riga_run"] is not None else blocco["riga_step"] + 1
                rs[dove:dove] = [" " * blocco["col_chiave"] + "env:" + eol,
                                 " " * (blocco["col_chiave"] + 2) + 'SCOUT_OFF: "1"' + eol]
            fatti.append('nello step non c\'e\' nessuna riga SCOUT_OFF: ne aggiungo una a "1", '
                         'cioe\' lo spegnimento scritto nero su bianco')
            return "".join(rs), fatti
        if blocco["n_figli_env"] <= 1:
            # Togliendo l'unica riga resterebbe "env:" senza figli (env: null): non lo lascio
            # a meta', porto il valore a "1" che e' comunque lo spegnimento esplicito.
            i = blocco["riga_scout"]
            rs[i] = " " * _indent_di(rs[i]) + 'SCOUT_OFF: "1"' + eol
            fatti.append('e\' l\'unica riga del blocco env:, quindi la porto a "1" invece di '
                         'toglierla (un env: vuoto e\' un blocco a meta\')')
        else:
            del rs[blocco["riga_scout"]]
            fatti.append("tolgo la riga SCOUT_OFF: torna a valere il default di build.py")
    return "".join(rs), fatti


def scout_valida(testo_nuovo, verso, default):
    """La prova del nove sulle istruzioni appena stampate: il file che ne uscirebbe e' YAML
    valido E la variabile finisce NELLO step che lancia build.py? Non basta che il file si
    apra: SCOUT_OFF in un altro step e' esattamente il modo di non accorgersi di niente.
    Ritorna (True/False/None, messaggio). None = non ho potuto provarlo, e lo dico."""
    try:
        import yaml
    except ImportError:
        return None, ("PyYAML non installato: NON ho potuto provare il risultato. "
                      "Installalo (py -m pip install pyyaml) e rilancia, oppure valida a mano "
                      "prima del push: e' obbligatorio (kb/RIPARTENZA.md §5).")
    try:
        doc = yaml.safe_load(testo_nuovo) or {}
    except Exception as e:
        return False, "il file che ne uscirebbe NON e' YAML valido: %s" % e
    nome, presente, valore = _scout_da_doc(doc)
    if nome is None:
        return False, 'dopo la modifica non trovo piu\' lo step "%s"' % STEP_WORKFLOW
    atteso_acceso = (verso == ACCESO)
    # Stessa regola di build.py: spento solo con "1". Se la riga non c'e', decide il default.
    ora_acceso = (valore != "1") if presente else ((default or "1") != "1")
    if atteso_acceso != ora_acceso:
        return False, ('il file sarebbe YAML valido ma lo scout resterebbe %s '
                       '(SCOUT_OFF=%s nello step "%s")'
                       % (ACCESO if ora_acceso else SPENTO,
                          ('"%s"' % valore) if presente else "assente", nome))
    return True, ('YAML valido e lo scout risulta %s nello step "%s" (riletto con PyYAML, '
                  'non a occhio)' % (verso, nome))


# ------------------------------------------------------------- regola d'oro sui feed
def verifica_feed(url, timeout=20):
    """REGOLA D'ORO della §7: build.py scarta gli item senza data valida
    (age_days(None) = 9999, oltre il filtro dei 30 giorni). Un feed con pubDate non
    standard non porta NULLA e non lo segnala nessuno: qui si controlla PRIMA di scriverlo
    nel file. Nessuna quota consumata: e' un RSS pubblico, non un'API a contatore."""
    try:
        import feedparser
    except ImportError:
        return None, "feedparser non installato (pip install -r requirements.txt)"
    try:
        d = feedparser.parse(url)
    except Exception as e:
        return False, "errore di rete: %s" % e
    stato_http = getattr(d, "status", None)
    voci = list(getattr(d, "entries", []) or [])
    if stato_http and int(stato_http) >= 400:
        return False, "HTTP %s" % stato_http
    if not voci:
        return False, "0 item (feed morto o irraggiungibile)"
    con_data = [v for v in voci if getattr(v, "published_parsed", None)]
    if not con_data:
        return False, ("%d item ma NESSUNO con published_parsed: build.py li scarterebbe TUTTI"
                       " (e' il caso di Sky Sport, date in italiano)" % len(voci))
    ultimo = max(datetime(*v.published_parsed[:6], tzinfo=timezone.utc) for v in con_data)
    giorni = (datetime.now(timezone.utc) - ultimo).days
    if giorni > 30:
        return False, ("ultimo item %d giorni fa: oltre il filtro dei 30 giorni di build.py,"
                       " il feed non porterebbe nulla" % giorni)
    return True, "%d item, %d con data valida, il piu' recente %d giorni fa" % (
        len(voci), len(con_data), giorni)


# ============================================================================ lettura stato
def _kw_stato(valori):
    etichette = {}
    for lang in ("it", "en", "es"):
        v = valori.get(lang)
        if v == KW[ACCESO][lang]:
            etichette[lang] = ACCESO
        elif v == KW[SPENTO][lang]:
            etichette[lang] = SPENTO
        else:
            etichette[lang] = IGNOTO
    unici = set(etichette.values())
    if unici == {ACCESO}:
        return ACCESO, etichette
    if unici == {SPENTO}:
        return SPENTO, etichette
    if IGNOTO in unici and len(unici) == 1:
        return IGNOTO, etichette
    return MISTO, etichette


def rileva(radice):
    """Legge lo stato dei sei passi della §7. Sola lettura, sempre sicura."""
    s = {"radice": radice,
         "teams": os.path.join(radice, "data", "teams.json"),
         "sources": os.path.join(radice, "data", "sources.json"),
         "yml": os.path.join(radice, ".github", "workflows", "update.yml"),
         "build": os.path.join(radice, "scripts", "build.py")}
    s["t_teams"] = leggi(s["teams"])
    s["t_sources"] = leggi(s["sources"])

    s["scout"] = scout_leggi(s["yml"], s["build"])
    s["p1"] = scout_stato(s["scout"])

    s["kw"] = kw_leggi(s["t_teams"])
    s["p2"], s["kw_per_lang"] = _kw_stato(s["kw"])

    feeds = feeds_leggi(s["t_sources"])
    urls = {f.get("url") for f in feeds}
    s["feed_presenti"] = [f for f in FEED_MERCATO if f["url"] in urls]
    s["feed_assenti"] = [f for f in FEED_MERCATO if f["url"] not in urls]
    s["feed_vietati_presenti"] = [f for f in feeds if f.get("url") in FEED_VIETATI]
    s["p3"] = ACCESO if not s["feed_assenti"] else (SPENTO if not s["feed_presenti"] else MISTO)
    s["n_feed"] = len(feeds)

    mondo = [m.get("search") for m in mondo_leggi(s["t_teams"])]
    if mondo == [m["search"] for m in MONDO[ACCESO]]:
        s["p5"] = ACCESO
    elif mondo == [m["search"] for m in MONDO[SPENTO]]:
        s["p5"] = SPENTO
    else:
        s["p5"] = IGNOTO
    s["mondo"] = mondo

    principali = [s["p1"], s["p2"], s["p3"]]
    # Se anche un solo passo non e' verificabile, il complessivo NON e' "acceso" ne' "spento":
    # e' sconosciuto. Rispondere lo stesso sarebbe una risposta comoda e non controllata, ed e'
    # il difetto che questo file esiste per evitare.
    if IGNOTO in principali:
        s["complessivo"] = IGNOTO
    elif all(x == ACCESO for x in principali):
        s["complessivo"] = ACCESO
    elif all(x == SPENTO for x in principali):
        s["complessivo"] = SPENTO
    else:
        s["complessivo"] = MISTO
    return s


# ============================================================================ stampa
def linea(c="="):
    print(c * 78)


def intestazione(s):
    linea()
    print(" TransferBeat - MACCHINA DEL CALCIOMERCATO (kb/RIPARTENZA.md §7)")
    print(" Radice: %s" % s["radice"])
    print(" Ora:    %s UTC" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
    linea()


def stampa_stato(s):
    intestazione(s)
    print("")
    print(" STATO COMPLESSIVO: %s" % s["complessivo"])
    print("")
    print("  passo 1  scout dei movimenti da->a   %-7s  %s" % (s["p1"], rel(s["radice"], s["yml"])))
    sc = s["scout"]
    if sc.get("errore"):
        print("           ! %s" % sc["errore"])
    if sc.get("ignoto"):
        # Non si stampa nessuna affermazione sullo stato: non lo sappiamo.
        print("           NON VERIFICABILE: non dico ne' acceso ne' spento. Trattalo come")
        print("           un allarme, non come un dettaglio (uscita 2, non 0).")
        if sc.get("indizio"):
            print("           indizio, NON una risposta: %s" % sc["indizio"])
    elif sc["presente"]:
        print("           SCOUT_OFF: \"%s\" nello step \"%s\"" % (sc["valore"], sc["step"]))
    else:
        print("           SCOUT_OFF assente dallo step \"%s\": vale il default di build.py" % (sc["step"] or "?"))
    if sc.get("default"):
        print("           default nel codice: SCOUT_OFF=\"%s\" (scripts/build.py riga %s)"
              % (sc["default"], sc["default_riga"]))

    print("")
    print("  passo 2  parole chiave kw            %-7s  %s" % (s["p2"], rel(s["radice"], s["teams"])))
    for lang in ("it", "en", "es"):
        print("           kw.%s = \"%s\"  [%s]  (mercato: \"%s\")"
              % (lang, s["kw"].get(lang), s["kw_per_lang"][lang], KW[ACCESO][lang]))

    print("")
    print("  passo 3  feed diretti di mercato     %-7s  %s  (%d feed in totale)"
          % (s["p3"], rel(s["radice"], s["sources"]), s["n_feed"]))
    for f in FEED_MERCATO:
        c = "presente" if f in s["feed_presenti"] else "ASSENTE "
        print("           %s  %s" % (c, f["nome"]))
    for f in s["feed_vietati_presenti"]:
        print("           !! VIETATO in elenco: %s -> %s" % (f.get("nome"), FEED_VIETATI[f["url"]]))

    print("")
    print("  passo 4  tassonomia                  %-7s  rules/keywords.*.json" % NA)
    print("           NON va toccata (§7 passo 4): i vocabolari sono gia' l'unione dei termini")
    print("           di mercato e di campionato. Questo script non li apre nemmeno.")

    print("")
    print("  passo 5  \"Dal mondo\" (facoltativo)   %-7s  %s" % (s["p5"], rel(s["radice"], s["teams"])))
    print("           mondo_home: %s" % (", ".join(s["mondo"]) or "(vuoto)"))
    print("")
    linea("-")
    if s["complessivo"] == IGNOTO:
        print(" ATTENZIONE: STATO SCONOSCIUTO. Non rispondo \"acceso\" ne' \"spento\": non lo so.")
        for etichetta, valore, nota in (("passo 1", s["p1"], s["scout"].get("errore")),
                                        ("passo 2", s["p2"], None),
                                        ("passo 3", s["p3"], None)):
            if valore == IGNOTO:
                print(" %s non verificabile%s" % (etichetta, (": " + nota) if nota else ""))
        print(" Finche' resta cosi' NON dare per buono lo stato del mercato: uscita 2, non 0.")
        print(" Uno stato ignoto e' pericoloso quanto quello misto, perche' quello misto puo'")
        print(" esserlo davvero senza che nessuno lo veda (kb/RIPARTENZA.md §5).")
    elif s["complessivo"] == MISTO:
        print(" ATTENZIONE: STATO MISTO, il piu' pericoloso.")
        if s["p1"] != ACCESO and (s["p2"] == ACCESO or s["p3"] == ACCESO):
            print(" La board raccoglie notizie di MERCATO ma lo scout NON estrae i movimenti da->a:")
            print(" il campo \"nomi\" resta vuoto e nessuno se ne accorge (il workflow resta verde).")
        if s["p3"] == MISTO:
            print(" I feed diretti di mercato sono a meta': %d di %d in elenco."
                  % (len(s["feed_presenti"]), len(FEED_MERCATO)))
        if s["p2"] == MISTO:
            print(" Le parole chiave kw non sono allineate fra le tre lingue: %s."
                  % ", ".join("%s=%s" % (l, s["kw_per_lang"][l]) for l in ("it", "en", "es")))
        if s["p1"] == ACCESO and s["p2"] != ACCESO:
            print(" Lo scout gira su titoli di CAMPIONATO: o torna vuoto o allucina trasferimenti,")
            print(" che merge_nomi terrebbe in board per 3 giorni.")
        print(" Rimedio: py -X utf8 scripts/mercato.py --accendi   (oppure --spegni)")
    elif s["complessivo"] == ACCESO:
        print(" Mercato ACCESO e coerente. Verifica del §7 passo 6 qui sotto.")
        stampa_verifica()
    else:
        print(" Mercato SPENTO e coerente (sito su campionati e coppe).")
    linea("-")


def stampa_verifica():
    """§7 passo 6: la verifica NON va lasciata in un commento, va detta a chi lancia."""
    print("")
    print(" VERIFICA DOPO LA RIACCENSIONE (§7 passo 6), nell'ordine:")
    print("   1. push e poi un giro di build: Actions -> \"Aggiorna dati TransferBeat\" -> Run workflow")
    print("      (oppure aspetta il cron: ogni 2 ore fra le 06 e le 22 UTC)")
    print("   2. git fetch origin && git show origin/main:data/it/board.json")
    print("      -> il campo \"nomi\" deve essere di nuovo POPOLATO e \"aggiornato\" di poche ore fa")
    print("   3. se \"nomi\" resta vuoto, PRIMA di ogni altra cosa controlla i modelli Groq (§1):")
    print("      curl https://api.groq.com/openai/v1/models  -> SCOUT_MODEL deve esistere ancora")
    print("      (e' il guasto che si ripete: Groq dismette i modelli senza preavviso)")
    print("   4. py -X utf8 scripts/mercato.py --stato  -> deve dire ACCESO su tutti i passi")


def istruzioni_scout(s, verso):
    """Passo 1: si dice cosa cambiare, NON si tocca il workflow.
    Il passo 1 e' rimasto manuale APPOSTA (kb/RIPARTENZA.md §5): un workflow invalido non
    avvisa nessuno e ha gia' tenuto il sito fermo 36 ore. Quindi l'unica cosa che questo
    script deve fare bene qui e' dire ESATTAMENTE cosa scrivere: il blocco stampato ricalca
    l'indentazione vera del file (letta, non supposta) e il risultato viene riletto con
    yaml.safe_load prima di consigliarlo."""
    sc = s["scout"]
    print("")
    print(" [passo 1] SCOUT dei movimenti da->a  (%s)" % rel(s["radice"], s["yml"]))
    if s["p1"] == verso:
        print("   gia' %s: nessuna modifica al workflow. (SCOUT_OFF=%s)"
              % (verso, ('"%s"' % sc["valore"]) if sc["presente"]
                 else 'assente, default "%s"' % sc.get("default")))
        return False
    if s["p1"] == IGNOTO:
        print("   ATTENZIONE: lo stato attuale del passo 1 NON e' verificabile, quindi non so")
        print("   nemmeno se ci sia qualcosa da cambiare. Motivo: %s" % (sc.get("errore") or "?"))
        if sc.get("indizio"):
            print("   Indizio (NON una risposta): %s" % sc["indizio"])
    print("   DA FARE A MANO: update.yml non e' un file di questo script (lo tocca la sessione")
    print("   principale, e un workflow invalido ferma cron e workflow_dispatch senza avvisare).")

    blocco = sc.get("blocco")
    if not blocco or sc.get("testo") is None:
        print("   NON riesco a individuare lo step \"%s\" in %s: niente blocco da copiare."
              % (STEP_WORKFLOW, rel(s["radice"], s["yml"])))
        print("   Aprilo a mano e metti SCOUT_OFF=\"%s\" fra le env: di quello step."
              % ("0" if verso == ACCESO else "1"))
        return True

    nuovo, fatti = scout_simula(sc["testo"], blocco, verso)
    if nuovo is None:
        print("   Non c'e' una modifica da proporre: %s" % "; ".join(fatti))
        return True
    for f in fatti:
        print("   Cosa cambia: %s" % f)

    # Il blocco da mostrare lo rileggo dal testo SIMULATO: le colonne che stampo sono quelle
    # che finirebbero davvero nel file, non quelle che credo io.
    b2 = scout_blocco_yml(nuovo)
    rs2 = nuovo.splitlines()
    if b2 is None:                       # non deve succedere: se succede non invento un blocco
        print("   NON riesco a rileggere lo step nel testo che ho appena costruito:")
        print("   e' un difetto di questo script, non toccare il workflow a occhio.")
        return True
    if b2["riga_env"] is not None:
        da, a = b2["riga_env"], b2["fine_env"]
    else:
        da, a = b2["riga_step"], b2["fine_step"]
    print("")
    print("   Nello step \"%s\" il blocco env: deve diventare ESATTAMENTE cosi'" % blocco["nome"])
    print("   (le colonne contano: qui sotto sono quelle vere di %s, copiale come stanno)"
          % rel(s["radice"], s["yml"]))
    print("   ----------8<---------- copia da qui ----------8<----------")
    for r in rs2[da:a]:
        print(r)
    print("   ----------8<---------- fino a qui ----------8<----------")
    if verso == SPENTO and blocco["n_figli_env"] > 1:
        print("   (cioe': la riga SCOUT_OFF sparisce. Senza quella riga vale il default del")
        print("    codice, SCOUT_OFF=\"%s\" in scripts/build.py.)" % (sc.get("default") or "1"))

    esito, msg = scout_valida(nuovo, verso, sc.get("default"))
    print("")
    if esito is True:
        print("   PROVATO PRIMA DI DIRTELO: %s" % msg)
    elif esito is False:
        print("   !!! NON INCOLLARLO: %s" % msg)
        print("   !!! e' un difetto di questo script: segnalalo invece di aggiustare a occhio.")
    else:
        print("   NON VERIFICATO: %s" % msg)
    print("")
    print("   In ogni caso VALIDA il file prima del push (obbligatorio, kb/RIPARTENZA.md §5):")
    print("     py -c \"import yaml,sys;yaml.safe_load(open(sys.argv[1],encoding='utf-8'))\""
          " .github/workflows/update.yml")
    print("   e poi ricontrolla con: py -X utf8 scripts/mercato.py --stato")
    return True


def diff_testo(nome, vecchio, nuovo):
    a = [r.rstrip("\r\n") for r in vecchio.splitlines()]
    b = [r.rstrip("\r\n") for r in nuovo.splitlines()]
    return list(difflib.unified_diff(a, b, fromfile=nome + " (attuale)", tofile=nome + " (nuovo)", n=2, lineterm=""))


def applica(s, verso, con_mondo, dry, salta_verifica):
    intestazione(s)
    print("")
    print(" AZIONE: %s   (%s)" % ("--accendi" if verso == ACCESO else "--spegni",
                                  "PROVA A VUOTO, nessun file verra' scritto" if dry else "scrittura sui file"))
    print(" Stato di partenza: %s" % s["complessivo"])
    problemi = 0
    manuale = istruzioni_scout(s, verso)

    # ---- passo 2 e 5: data/teams.json ----
    nuovo_teams, fatti_teams = kw_scrivi(s["t_teams"], KW[verso])
    print("")
    print(" [passo 2] Parole chiave kw  (%s)" % rel(s["radice"], s["teams"]))
    if fatti_teams:
        for f in fatti_teams:
            print("   %s" % f)
    else:
        print("   gia' %s: nessuna modifica." % verso)
    print("")
    print(" [passo 5] \"Dal mondo\" mondo_home  (FACOLTATIVO)")
    if not con_mondo:
        print("   non toccato. Serve --con-mondo. Ora e' su: %s" % ", ".join(s["mondo"]))
    elif s["p5"] == verso:
        print("   gia' %s: nessuna modifica." % verso)
    else:
        if s["p5"] == IGNOTO:
            print("   ! il blocco attuale non e' ne' quello di mercato ne' quello di campionato:")
            print("     %s" % ", ".join(s["mondo"]))
            print("     verra' SOSTITUITO: se era una personalizzazione, annullala con git checkout.")
        nuovo_teams, fatti_m = mondo_scrivi(nuovo_teams, MONDO[verso])
        for f in fatti_m:
            print("   %s" % f)

    # ---- passo 3: data/sources.json ----
    print("")
    print(" [passo 3] Feed diretti di mercato  (%s)" % rel(s["radice"], s["sources"]))
    aggiungere, togliere = [], []
    if verso == ACCESO:
        candidati = list(s["feed_assenti"])
        for f in candidati:
            if f["url"] in FEED_VIETATI:      # cintura in piu': non deve poter succedere
                continue
            if salta_verifica:
                continue
            ok, msg = verifica_feed(f["url"])
            if ok:
                print("   verificato  %-32s %s" % (f["nome"], msg))
                aggiungere.append(f)
            else:
                problemi += 1
                print("   RIFIUTATO   %-32s %s" % (f["nome"], msg))
                print("               non lo aggiungo: un feed cosi' non porta NULLA e non lo")
                print("               segnala nessuno (regola d'oro §7). Ricontrolla la URL.")
        if salta_verifica and candidati:
            aggiungere = [f for f in candidati if f["url"] not in FEED_VIETATI]
            print("   !!! VERIFICA SALTATA (--salta-verifica-feed) su %d feed." % len(aggiungere))
            print("   !!! build.py scarta gli item senza data valida: se un feed ha pubDate non")
            print("   !!! standard resta in elenco e non porta nulla, in silenzio. Verificalo:")
            for f in aggiungere:
                print("   !!!   py -X utf8 -c \"import feedparser;d=feedparser.parse('%s');"
                      "print(len(d.entries),[e.get('published_parsed') for e in d.entries[:2]])\"" % f["url"])
            problemi += 1
    else:
        togliere = list(s["feed_presenti"])
    for f in s["feed_vietati_presenti"]:
        print("   !! in elenco c'e' un feed VIETATO dalla §7: %s (%s)"
              % (f.get("nome"), FEED_VIETATI[f["url"]]))
        print("      toglilo a mano: questo script non rimuove voci che non ha messo lui.")
    nuovo_sources, fatti_src = feeds_scrivi(s["t_sources"], aggiungere, togliere)
    if fatti_src:
        for f in fatti_src:
            print("   %s" % f)
    else:
        print("   nessuna modifica ai feed.")
    return nuovo_teams, nuovo_sources, problemi, manuale


def _solo_chiavi_attese(vecchio, nuovo, attese):
    """Rete di sicurezza: dopo la modifica testuale il file deve restare JSON valido e
    devono essere cambiate SOLO le chiavi che volevamo. Un file dati riscritto per sbaglio
    (e' gia' successo con rules/keywords.*.json il 2026-09-02) rompe il build in produzione."""
    a, b = json.loads(vecchio), json.loads(nuovo)
    if set(a) != set(b):
        raise Rifiuto("le chiavi di primo livello sono cambiate: %s -> %s" % (sorted(a), sorted(b)))
    diverse = {k for k in a if a[k] != b[k]}
    if not diverse <= set(attese):
        raise Rifiuto("modificate chiavi non previste: %s" % sorted(diverse - set(attese)))
    return sorted(diverse)


def concludi(s, coppie, dry, verso, problemi, manuale):
    print("")
    linea("-")
    print(" FILE, UNO PER UNO")
    scritti = 0
    for path, vecchio, nuovo, attese in coppie:
        nome = rel(s["radice"], path)
        if vecchio == nuovo:
            print("   %-20s invariato        sha %s" % (nome, sha(vecchio)))
            continue
        cambiate = _solo_chiavi_attese(vecchio, nuovo, attese)
        print("")
        print("   %-20s %s   sha %s -> %s   (chiavi: %s)"
              % (nome, "DA SCRIVERE" if dry else "SCRITTO", sha(vecchio), sha(nuovo), ", ".join(cambiate)))
        for r in diff_testo(nome, vecchio, nuovo):
            print("     %s" % r)
        if not dry:
            scrivi(path, nuovo)
            scritti += 1
    print("")
    print("   %-20s non letto e non toccato (§7 passo 4: la tassonomia non si tocca)"
          % "rules/keywords.*")
    print("   %-20s SOLA LETTURA, mai scritto da qui (%s, vedi passo 1)"
          % ("update.yml", rel(s["radice"], s["yml"])))
    linea("-")
    if dry:
        print(" PROVA A VUOTO: nessun file e' stato scritto. Rilancia senza --dry per applicare.")
    elif scritti:
        print(" Scritti %d file. Per annullare: git checkout -- data/teams.json data/sources.json" % scritti)
        print(" I file dati NON sono stati aggiunti a git: il commit lo fai tu.")
    else:
        print(" Nulla da scrivere: era gia' tutto a posto (il comando e' idempotente).")
    if manuale:
        print("")
        print(" RESTA DA FARE A MANO: la riga SCOUT_OFF in .github/workflows/update.yml (passo 1).")
        print(" Finche' non la fai lo stato resta MISTO: %s"
              % ("board di mercato senza scout" if verso == ACCESO else "scout acceso su titoli di campionato"))
        print(" Per questo l'uscita e' 2 e non 0: il lavoro NON e' finito e un 0 lo farebbe")
        print(" sembrare finito (e in questo progetto e' cosi' che passano i guasti).")
    if verso == ACCESO:
        stampa_verifica()
    else:
        print("")
        print(" DOPO LO SPEGNIMENTO: il campo \"nomi\" di data/it/board.json si svuota da solo per")
        print(" decadimento (merge_nomi tiene i movimenti 3 giorni, i residui fino a 60).")
    linea("-")
    print(" Ricontrolla quando vuoi con: py -X utf8 scripts/mercato.py --stato")
    # Il contratto dichiarato (docstring in testa e --help) e' "2 = stato misto oppure
    # modifiche rifiutate": anche il passo 1 lasciato a meta' LASCIA lo stato misto, quindi
    # deve dare 2. Prima dava 0, cioe' l'uscita che uno script chiamante legge come "fatto".
    return 2 if (problemi or manuale) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="mercato.py",
        description="Accende e spegne la macchina del calciomercato di TransferBeat "
                    "(kb/RIPARTENZA.md §7). Idempotente e reversibile.",
        epilog="Uscita: 0 coerente/fatto e niente da fare; 2 stato misto o SCONOSCIUTO, "
               "modifiche rifiutate, o passo 1 ancora da fare a mano; 1 errore.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--stato", action="store_true", help="dice se il mercato e' ACCESO o SPENTO, campo per campo")
    g.add_argument("--accendi", action="store_true", help="applica i passi della §7 (finestra di mercato)")
    g.add_argument("--spegni", action="store_true", help="riporta indietro i passi della §7")
    ap.add_argument("--dry", action="store_true", help="mostra il diff senza scrivere niente")
    ap.add_argument("--con-mondo", action="store_true",
                    help="tocca anche mondo_home (passo 5, FACOLTATIVO: senza questo flag non si tocca)")
    ap.add_argument("--salta-verifica-feed", action="store_true",
                    help="non verifica i feed prima di aggiungerli: SCONSIGLIATO, esce con codice 2")
    ap.add_argument("--radice", default=RADICE_DEFAULT,
                    help="radice del repo (per provare su copie: default %(default)s)")
    a = ap.parse_args(argv)

    radice = os.path.abspath(a.radice)
    try:
        s = rileva(radice)
    except FileNotFoundError as e:
        print("ERRORE: file mancante sotto %s -> %s" % (radice, e))
        return 1
    except Rifiuto as e:
        print("ERRORE: %s" % e)
        return 2

    if a.stato:
        stampa_stato(s)
        # IGNOTO esce 2 come MISTO: "non lo so" non deve somigliare a un successo.
        return 2 if s["complessivo"] in (MISTO, IGNOTO) else 0

    verso = ACCESO if a.accendi else SPENTO
    try:
        nuovo_teams, nuovo_sources, problemi, manuale = applica(
            s, verso, a.con_mondo, a.dry, a.salta_verifica_feed)
        coppie = [(s["teams"], s["t_teams"], nuovo_teams, ("kw", "mondo_home")),
                  (s["sources"], s["t_sources"], nuovo_sources, ("feeds",))]
        return concludi(s, coppie, a.dry, verso, problemi, manuale)
    except Rifiuto as e:
        print("")
        print(" FERMO, NIENTE SCRITTO: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
