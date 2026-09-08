# -*- coding: utf-8 -*-
"""Riconosce i giocatori per cui API-Football non ha una vera foto e serve la sagoma anonima.

Il CDN risponde 200 anche quando la foto non ce l'ha: manda un segnaposto grigio, sempre lo stesso
file, per tutti i giocatori senza ritratto. Controllare lo stato HTTP non basta - e' il tipo di
verifica che risponde "tutto a posto" senza aver guardato niente. Qui le immagini si scaricano
davvero e si confrontano per contenuto: il file che si ripete decine di volte NON e' una foto.

Scrive `data/stats/foto-placeholder.json`, che `render_stats.py` legge per NON mettere in pagina
una sagoma spacciata per il ritratto del giocatore. Va rilanciato ogni tanto (API-Football aggiunge
ritratti nel tempo): senza rilanciarlo, l'elenco invecchia e qualche foto vera resta nascosta -
il danno minore fra i due.

    py -X utf8 scripts/foto_check.py            # aggiorna l'elenco
    py -X utf8 scripts/foto_check.py --mostra   # solo il conto, non scrive
"""
import concurrent.futures as cf
import hashlib
import io
import json
import os
import sys
import time
import urllib.request

QUI = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(QUI), "data")
STATS = os.path.join(DATA, "stats")
USCITA = os.path.join(STATS, "foto-placeholder.json")

# quante volte deve ripetersi un'immagine identica perche' sia un segnaposto e non una coincidenza.
# Due giocatori non possono avere lo stesso identico file: sotto questa soglia preferisco lasciar
# passare piuttosto che nascondere una foto vera per un caso strano.
SOGLIA = 5
TIMEOUT = 20


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TransferBeat/1.0 (foto_check)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def impronta(coppia):
    pid, url = coppia
    for tentativo in range(3):
        try:
            b = scarica(url)
            return pid, hashlib.md5(b).hexdigest(), len(b), None
        except Exception as e:
            if tentativo == 2:
                return pid, None, 0, str(e)
            time.sleep(1.5 * (tentativo + 1))


def main():
    solo_mostra = "--mostra" in sys.argv
    players = json.load(io.open(os.path.join(STATS, "players.json"), encoding="utf-8"))["players"]
    lavoro = [(pid, p["photo"]) for pid, p in players.items() if p.get("photo")]
    print("foto da controllare: %d" % len(lavoro))

    esiti = []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for e in ex.map(impronta, lavoro):
            esiti.append(e)

    errori = [(pid, err) for pid, h, _, err in esiti if h is None]
    buoni = [(pid, h, n) for pid, h, n, err in esiti if h is not None]

    conteggio = {}
    for _, h, _ in buoni:
        conteggio[h] = conteggio.get(h, 0) + 1

    segnaposto = {h: n for h, n in conteggio.items() if n >= SOGLIA}
    ids = sorted(pid for pid, h, _ in buoni if h in segnaposto)

    print("immagini distinte: %d su %d scaricate" % (len(conteggio), len(buoni)))
    if errori:
        print("NON scaricate: %d (restano trattate come foto valide)" % len(errori))
        for pid, err in errori[:5]:
            print("   id %s: %s" % (pid, err[:80]))
    if not segnaposto:
        print("nessun segnaposto trovato: tutte le foto sono diverse fra loro")
    for h, n in sorted(segnaposto.items(), key=lambda x: -x[1]):
        peso = [p for _, hh, p in buoni if hh == h][0]
        print("SEGNAPOSTO %s ripetuto %d volte (%d byte)" % (h[:12], n, peso))

    if solo_mostra:
        print("(--mostra: non scrivo niente)")
        return 0

    fuori = {
        "generato": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fonte": "media.api-sports.io",
        "soglia_ripetizioni": SOGLIA,
        "hash_segnaposto": sorted(segnaposto),
        "controllate": len(buoni),
        "non_scaricate": [pid for pid, _ in errori],
        "senza_foto_vera": ids,
    }
    io.open(USCITA, "w", encoding="utf-8", newline="\n").write(
        json.dumps(fuori, ensure_ascii=False, indent=1))
    print("scritto %s: %d giocatori senza una foto vera (%.1f%%)" % (
        os.path.relpath(USCITA), len(ids), 100.0 * len(ids) / max(1, len(buoni))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
