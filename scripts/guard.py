#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anti-troncamento: blocca il commit se un file sorgente critico (HTML/.py)
si e' rimpicciolito in modo sospetto rispetto all'ultima versione su git.
I file dati (data/*.json) sono esclusi perche' variano legittimamente di dimensione."""
import subprocess, sys, fnmatch, os

GUARDED = ["*.html", "scripts/*.py"]
EXCLUDE_DIRS = ("articoli/",)

def sh(*a):
    # encoding esplicito: senza, su Windows con locale italiano Python decodifica in cp1252
    # e muore su un byte non mappabile (nomi di file o contenuti con accenti).
    # Il returncode NON si butta via: un `git diff` fallito restituirebbe una lista vuota di file cambiati
    # e il guard direbbe "tutto a posto" proprio quando non ha potuto controllare niente.
    r = subprocess.run(a, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(" ".join(a) + " -> uscito con " + str(r.returncode) + ": " + (r.stderr or "").strip()[:200])
    return r.stdout

# NOTA sul perche' i due conteggi lavorano in BINARIO: contare le righe non richiede di
# decodificare il testo. Un file troncato e' spesso anche corrotto (byte non validi in UTF-8):
# decodificarlo poteva far fallire proprio il controllo che deve fermarlo. Contando i b"\n"
# nessun contenuto, per quanto corrotto, puo' far saltare o crashare il guard.
# I due lati vanno contati allo stesso modo, altrimenti il confronto HEAD/disco non ha senso.

def head_lines(path):
    """Righe della versione a HEAD, o None se il file non c'e' (file nuovo: niente confronto)."""
    out = subprocess.run(["git", "show", "HEAD:" + path], capture_output=True)
    if out.returncode != 0:
        return None  # file nuovo: niente confronto
    return out.stdout.count(b"\n")

def cur_lines(path):
    """Righe del file su disco. Se il file non e' leggibile solleva OSError: chi chiama
    deve BLOCCARE, non tacere e passare (un guard che si zittisce non protegge nulla)."""
    with open(path, "rb") as f:
        return f.read().count(b"\n")

def main():
    # via di fuga annunciata dal messaggio di stop piu' sotto: basta la DEFINIZIONE della variabile,
    # come in carica-modifiche.bat ("if not defined TB_FORCE"), altrimenti lo stesso comando darebbe
    # esiti diversi a seconda che il guard sia lanciato dal .bat o a mano
    if os.environ.get("TB_FORCE") is not None:
        print("guard: TB_FORCE impostata, controllo anti-troncamento saltato.")
        return 0

    try:
        changed = [l for l in sh("git", "diff", "--name-only", "HEAD").splitlines() if l.strip()]
    except (RuntimeError, OSError) as e:
        print("STOP: non riesco a chiedere a git quali file sono cambiati:", e)
        print("Il controllo anti-troncamento NON e' stato eseguito. Caricamento ANNULLATO.")
        return 1
    sospetti = []
    illeggibili = []
    for path in changed:
        if path.startswith(EXCLUDE_DIRS) or ("/" in path and not path.startswith("scripts/")):
            continue
        if not any(fnmatch.fnmatch(path, g) for g in GUARDED):
            continue
        # file cancellato: il guard controlla i troncamenti, non le rimozioni volute
        # (git diff --name-only elenca anche le cancellazioni)
        if not os.path.exists(path):
            continue
        try:
            old = head_lines(path)
            new = cur_lines(path)
        except OSError as e:
            # permessi, disco, file sparito o permessi negati: non sappiamo se il file e' integro,
            # quindi ci comportiamo come se fosse sospetto (prudenti: si blocca)
            illeggibili.append((path, str(e)))
            continue
        if old is None or old < 20:
            continue
        # sospetto se perde >15 righe E scende sotto il 70% dell'originale
        if new < old - 15 and new < 0.70 * old:
            sospetti.append((path, old, new))

    if sospetti or illeggibili:
        print("")
        print("  ====================  STOP: possibile TRONCAMENTO  ====================")
        for p, o, n in sospetti:
            print("   " + p + ": " + str(o) + " -> " + str(n) + " righe  (-" + str(o - n) + ")")
        for p, err in illeggibili:
            print("   " + p + ": NON LEGGIBILE (" + err + ")")
        # righe di spiegazione distinte: dire "si sono rimpiccioliti" per un file che non
        # siamo riusciti a leggere manderebbe l'utente a cercare un troncamento inesistente
        if sospetti:
            print("  Questi file sorgente si sono rimpiccioliti molto: probabile file tagliato.")
        if illeggibili:
            print("  Questi file non si sono potuti controllare: meglio fermarsi che pubblicare al buio.")
        print("  Commit ANNULLATO per sicurezza. Controlla i file prima di ricaricare.")
        print("  (Se la riduzione e' voluta, rilancia con:  set TB_FORCE=1 )")
        print("  ======================================================================")
        return 1
    print("guard: nessun troncamento sospetto.")
    return 0

# corpo in main(): cosi' guard.py resta importabile (prima l'uscita anticipata su TB_FORCE
# era a livello di modulo e un semplice import moriva con SystemExit)
if __name__ == "__main__":
    sys.exit(main())
