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

# Pagine che NON usano il guscio del sito e che quindi non devono avere i suoi token:
# l'app FantaTB ha un CSS proprio, i report in kb/ non sono pagine pubblicate.
SENZA_GUSCIO = ("fanta/", "kb/")

def riga_token():
    """La riga ':root{...}' del guscio: e' l'impronta della veste corrente."""
    qui = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(qui, "site_common.py"), encoding="utf-8") as f:
        css = f.read()
    i = css.find(":root{--bg:")
    if i < 0:
        return None
    return css[i:css.index("\n", i)]

def veste_disallineata(radice):
    """Le pagine che non hanno i token del guscio corrente, cioe' quelle rimaste a una veste vecchia.

    Perche' serve: l'8 settembre il guscio e' cambiato, sono stati rigenerati giocatori, squadre,
    campionati e fantacalcio, ma NON gli articoli - render_articles.py e' un generatore a parte e
    nessuno lo ha rilanciato. Risultato: 594 pagine su 1375 con la testata di ieri, nessun errore da
    nessuna parte, e `git status` che mostrava 807 file cambiati senza il minimo segnale che ne
    mancasse un'intera sezione. Un cambio di veste non e' finito finche' OGNI pagina non lo porta.
    """
    impronta = riga_token()
    if impronta is None:
        return None, []          # non so qual e' la veste corrente: lo dice il chiamante
    indietro = []
    for cartella, sub, files in os.walk(radice):
        sub[:] = [d for d in sub if d not in (".git", "node_modules", ".claude")]
        for nome in files:
            if not nome.endswith(".html"):
                continue
            p = os.path.join(cartella, nome)
            rel = os.path.relpath(p, radice).replace(os.sep, "/")
            if rel.startswith(SENZA_GUSCIO):
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    testo = f.read()
            except OSError:
                continue
            if ":root{--bg:" in testo and impronta not in testo:
                indietro.append(rel)
    return impronta, indietro

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
    radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    impronta, indietro = veste_disallineata(radice)
    if impronta is None:
        print("STOP: non trovo la riga ':root{--bg:' in site_common.py.")
        print("Non posso sapere qual e' la veste corrente, quindi non posso dire se le pagine sono allineate.")
        print("Caricamento ANNULLATO: meglio fermarsi che pubblicare al buio.")
        return 1
    if indietro:
        per_cartella = {}
        for rel in indietro:
            c = rel.rsplit("/", 1)[0] if "/" in rel else "(radice)"
            per_cartella[c] = per_cartella.get(c, 0) + 1
        print("")
        print("  ==================  STOP: pagine con una VESTE VECCHIA  ==================")
        for c in sorted(per_cartella):
            print("   " + c + ": " + str(per_cartella[c]) + " pagine")
        print("   totale: " + str(len(indietro)) + " pagine non rigenerate dopo l'ultimo cambio del guscio.")
        print("  Ogni generatore va rilanciato, non solo render_site.py. Gli articoli hanno il loro:")
        print("     cd scripts")
        print("     py -X utf8 -c \"import articles, render_articles; render_articles.render_all("
              "articles.all_articles(), 'https://transferbeat.com', articles.PAGES, articles.DATA)\"")
        print("     py -X utf8 render_site.py")
        print("  Commit ANNULLATO: pubblicare adesso darebbe un sito con due vesti diverse.")
        print("  =========================================================================")
        return 1
    print("guard: nessun troncamento sospetto; veste uniforme su tutte le pagine.")
    return 0

# corpo in main(): cosi' guard.py resta importabile (prima l'uscita anticipata su TB_FORCE
# era a livello di modulo e un semplice import moriva con SystemExit)
if __name__ == "__main__":
    sys.exit(main())
