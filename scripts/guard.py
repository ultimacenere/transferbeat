#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anti-troncamento: blocca il commit se un file sorgente critico (HTML/.py)
si e' rimpicciolito in modo sospetto rispetto all'ultima versione su git.
I file dati (data/*.json) sono esclusi perche' variano legittimamente di dimensione."""
import subprocess, sys, fnmatch

GUARDED = ["*.html", "scripts/*.py"]
EXCLUDE_DIRS = ("articoli/",)

def sh(*a):
    return subprocess.run(a, capture_output=True, text=True).stdout

def head_lines(path):
    out = subprocess.run(["git", "show", "HEAD:" + path], capture_output=True, text=True)
    if out.returncode != 0:
        return None  # file nuovo: niente confronto
    return out.stdout.count("\n")

def cur_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().count("\n")
    except Exception:
        return None

changed = [l for l in sh("git", "diff", "--name-only", "HEAD").splitlines() if l.strip()]
sospetti = []
for path in changed:
    if path.startswith(EXCLUDE_DIRS) or ("/" in path and not path.startswith("scripts/")):
        continue
    if not any(fnmatch.fnmatch(path, g) for g in GUARDED):
        continue
    old = head_lines(path); new = cur_lines(path)
    if old is None or new is None or old < 20:
        continue
    # sospetto se perde >15 righe E scende sotto il 70% dell'originale
    if new < old - 15 and new < 0.70 * old:
        sospetti.append((path, old, new))

if sospetti:
    print("")
    print("  ====================  STOP: possibile TRONCAMENTO  ====================")
    for p, o, n in sospetti:
        print("   " + p + ": " + str(o) + " -> " + str(n) + " righe  (-" + str(o - n) + ")")
    print("  Questi file sorgente si sono rimpiccioliti molto: probabile file tagliato.")
    print("  Commit ANNULLATO per sicurezza. Controlla i file prima di ricaricare.")
    print("  (Se la riduzione e' voluta, rilancia con:  set TB_FORCE=1 )")
    print("  ======================================================================")
    sys.exit(1)
print("guard: nessun troncamento sospetto.")
sys.exit(0)
