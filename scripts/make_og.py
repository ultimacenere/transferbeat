#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Genera le immagini di anteprima social (og:image) del sito in img/.

Perche' uno script e non un file disegnato a mano: le immagini devono restare allineate ai token
di kb/SEO.md 7.1 (--ink #1b1140, --brand #ff6a00, --violet #4b1d95, Georgia sul logo). Se cambiano
i colori del sito si rilancia `py scripts/make_og.py` e le anteprime seguono.

Formato: 1200x630 (rapporto 1.91:1, quello che Facebook, X, LinkedIn, WhatsApp e Telegram ritagliano meno).
Il testo sta dentro un margine di sicurezza del 10% per resistere ai ritagli quadrati di alcune anteprime.
Uscita: img/og-default.png (tutto il sito) + una per sezione, cosi' una condivisione della sezione
fantacalcio non mostra la stessa figura della home.
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "img")
W, H = 1200, 630
INK = (27, 17, 64)          # --ink
BRAND = (255, 106, 0)       # --brand
VIOLET = (75, 29, 149)      # --violet
WHITE = (255, 255, 255)
MUTED = (176, 168, 200)

FONTS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts")

def font(name, size):
    """Georgia per il logo e i titoli (come sul sito), Segoe UI per il resto. Fallback: font di default di PIL."""
    for cand in (os.path.join(FONTS, name), name):
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default()

def w_of(d, text, f):
    b = d.textbbox((0, 0), text, font=f)
    return b[2] - b[0]

def card(titolo, sotto, kicker):
    im = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(im)

    # Fondo: due aloni morbidi (viola in alto a destra, arancio caldo in basso a sinistra).
    # Si disegnano su una maschera in scala di grigi e si sfocano: cerchi concentrici "a mano"
    # lasciano bordi netti, la sfocatura no. Poi la maschera fa da alfa per il colore dell'alone.
    def alone(cx, cy, raggio, colore, forza):
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).ellipse([cx - raggio, cy - raggio, cx + raggio, cy + raggio], fill=int(255 * forza))
        m = m.filter(ImageFilter.GaussianBlur(raggio * 0.55))
        return Image.composite(Image.new("RGB", (W, H), colore), im, m)

    im = alone(W - 210, -60, 470, VIOLET, 0.95)
    d = ImageDraw.Draw(im)
    im = alone(90, H + 80, 400, (196, 77, 0), 0.55)      # --brand-ink: arancio scuro, non fango
    d = ImageDraw.Draw(im)

    # barra arancio a sinistra: la firma visiva del sito
    d.rectangle([0, 0, 14, H], fill=BRAND)

    x = 96
    # occhiello
    fk = font("seguisb.ttf", 30)
    d.text((x, 96), kicker.upper(), font=fk, fill=BRAND)

    # titolo, a capo automatico su due righe al massimo
    ft = font("georgiab.ttf", 74)
    parole, righe, cur = titolo.split(), [], ""
    for p in parole:
        prova = (cur + " " + p).strip()
        if w_of(d, prova, ft) > W - x - 96 and cur:
            righe.append(cur); cur = p
        else:
            cur = prova
    righe.append(cur)
    y = 168
    for r in righe[:2]:
        d.text((x, y), r, font=ft, fill=WHITE)
        y += 88

    # sottotitolo
    fs = font("segoeui.ttf", 34)
    y += 14
    parole, righe, cur = sotto.split(), [], ""
    for p in parole:
        prova = (cur + " " + p).strip()
        if w_of(d, prova, fs) > W - x - 96 and cur:
            righe.append(cur); cur = p
        else:
            cur = prova
    righe.append(cur)
    for r in righe[:2]:
        d.text((x, y), r, font=fs, fill=MUTED)
        y += 46

    # logo in basso: Transfer bianco + Beat arancio, Georgia come sul sito
    fl = font("georgiab.ttf", 46)
    ly = H - 112
    d.text((x, ly), "Transfer", font=fl, fill=WHITE)
    d.text((x + w_of(d, "Transfer", fl), ly), "Beat", font=fl, fill=BRAND)
    fu = font("segoeui.ttf", 26)
    d.text((x, ly + 62), "transferbeat.com", font=fu, fill=MUTED)
    return im

CARDS = [
    ("og-default.png",     "Serie A e coppe, squadra per squadra",   "Notizie, classifiche, statistiche e fantacalcio, aggiornate ogni due ore.", "TransferBeat"),
    ("og-fantacalcio.png", "Il fantacalcio con i dati veri",         "Listone, voti statistici, probabili formazioni e infortunati. Gratis.",     "Fantacalcio"),
    ("og-campionati.png",  "Classifiche e risultati in tempo reale", "Serie A, Premier, Liga, Bundesliga, Ligue 1 e coppe europee.",              "Campionati"),
    ("og-squadre.png",     "Ogni squadra, tutti i numeri",           "Rosa, statistiche di squadra, forma, xG e schede giocatore.",              "Squadre"),
]


# ---------- copertine degli articoli, gemelle PNG delle SVG ----------
# Perche': gli scraper social (Facebook, X, LinkedIn, WhatsApp, Telegram) NON leggono SVG.
# Le img/cover-*.svg restano per il <img class="cover"> dentro la pagina (piu' leggere e nitide);
# og:image punta alla gemella .png generata qui, con gli stessi colori e le stesse parole.
COVERS = [
    ("cover-lunch.png",  ("#e09100", "#9a5e00"), ["LUNCH", "BREAK"], "Il focus di metà giornata",                "Serie A · La Liga · Premier League"),
    ("cover-storia.png", ("#1f6fd6", "#123f7e"), ["FOCUS"],          "La storia del giorno, raccontata",           "Serie A · La Liga · Premier League"),
    ("cover-recap.png",  ("#0a9d57", "#056a3a"), ["RECAP"],          "Il punto di giornata su campionati e coppe", "Serie A · La Liga · Premier League"),
    ("cover-scoop.png",  ("#e0392b", "#8e1810"), ["SCOOP!"],         "La notizia, prima degli altri",              "Serie A · La Liga · Premier League"),
    ("cover-notti.png",  ("#16285a", "#0a1738"), ["NOTTI", "MONDIALI"], "La notte di Coppa, raccontata all'alba",  "Mondiale 2026"),
    ("cover-bilancio.png", ("#4b1d95", "#2a1055"), ["BILANCIO"], "Il mercato, rifatto con i numeri",         "Serie A · La Liga · Premier League"),
]

def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def cover(c1, c2, parole, claim, piede):
    """Copertina in stile SVG originale: diagonale da c1 a c2, campo da gioco a filo, parole grandi."""
    a, b = hex2rgb(c1), hex2rgb(c2)
    im = Image.new("RGB", (W, H))
    px = im.load()
    for y in range(H):                       # diagonale come il linearGradient x1=0 y1=0 x2=1 y2=1
        for x in range(0, W, 4):
            t = (x / float(W) + y / float(H)) / 2.0
            col = (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))
            for k in range(4):
                if x + k < W:
                    px[x + k, y] = col
    d = ImageDraw.Draw(im)
    linea = (255, 255, 255)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    o = ImageDraw.Draw(ov)
    o.line([(600, 0), (600, H)], fill=linea + (36,), width=3)
    o.ellipse([450, 165, 750, 465], outline=linea + (36,), width=3)
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(im)

    fl = font("georgiab.ttf", 46)
    d.text((70, 62), "Transfer", font=fl, fill=WHITE)
    d.text((70 + w_of(d, "Transfer", fl), 62), "Beat", font=fl, fill=(255, 227, 179))

    dim = 118 if len(parole) > 1 else 148
    fw = font("georgiab.ttf", dim)
    y = 215 if len(parole) > 1 else 240
    for parola in parole:
        d.text((70, y), parola, font=fw, fill=WHITE)
        y += int(dim * 1.02)
    fc = font("segoeui.ttf", 34)
    d.text((70, y + 16), claim, font=fc, fill=(255, 255, 255))
    fp = font("segoeui.ttf", 22)
    d.text((70, H - 62), "transferbeat.com · " + piede, font=fp, fill=(255, 255, 255))
    return im

def main():
    os.makedirs(IMG, exist_ok=True)
    for nome, t, s, k in CARDS:
        im = card(t, s, k)
        out = os.path.join(IMG, nome)
        im.save(out, "PNG", optimize=True)
        print("%-22s %6.1f KB" % (nome, os.path.getsize(out) / 1024.0))
    for nome, (c1, c2), parole, claim, piede in COVERS:
        im = cover(c1, c2, parole, claim, piede)
        out = os.path.join(IMG, nome)
        im.save(out, "PNG", optimize=True)
        print("%-22s %6.1f KB" % (nome, os.path.getsize(out) / 1024.0))

if __name__ == "__main__":
    sys.exit(main())
