#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TransferBeat - brain.py  (il "cervello editoriale" condiviso)
Un'unica fonte di verita' iniettata in tutte le chiamate Groq: regole sugli stati,
perimetro, glossario squadre/gergo, esempi guida (few-shot) e stile degli articoli.
Tenuto COMPATTO di proposito per non sforare i limiti di token.
"""

# --- Carta editoriale: definizioni di stato e regole di coerenza ---
CHARTER = (
    "Sei l'analista di TransferBeat, sito di calciomercato di Serie A, La Liga e Premier League. "
    "Lavori SOLO su questi tre campionati: se nessun club delle tre leghe e' coinvolto, 'squadra' resta vuota.\n"
    "STATI (dal piu' debole al piu' forte):\n"
    "- rumor: voce, idea, interesse, sondaggio, 'piace', 'seguito'.\n"
    "- obj: obiettivo dichiarato, trattativa avviata, contatti, offerta presentata.\n"
    "- conf: affare dato per FATTO o accordo raggiunto. Anche 'X lascia il club' detto come certezza, 'intesa totale', 'manca solo la firma'.\n"
    "- done: UFFICIALE: annuncio, firma, visite mediche fatte, 'here we go', comunicato del club.\n"
    "REGOLA DI COERENZA: lo stato puo' solo SALIRE (rumor<obj<conf<done). Non declassare.\n"
    "SMENTITA: metti smentita=true solo se la notizia ANNULLA/NEGA un affare gia' dato ('salta tutto', 'naufragata', 'nessun accordo', 'resta').\n"
    "ANTI-INVENZIONE: usa SOLO cio' che e' scritto nel testo. Non inventare cifre, date, dichiarazioni o club non citati.\n"
    "Distingui sempre PROVENIENZA e DESTINAZIONE: direzione 'out' se lascia la 'squadra', 'in' se la raggiunge."
)

# --- Glossario: alias squadre e gergo di mercato ---
ALIAS = {
    "juve": "Juventus", "bianconeri": "Juventus", "vecchia signora": "Juventus",
    "nerazzurri": "Inter", "beneamata": "Inter", "biscione": "Inter",
    "rossoneri": "Milan", "diavolo": "Milan",
    "giallorossi": "Roma", "biancocelesti": "Lazio", "aquile": "Lazio",
    "partenopei": "Napoli", "azzurri": "Napoli", "viola": "Fiorentina",
    "blaugrana": "Barcelona", "cule": "Barcelona", "blancos": "Real Madrid",
    "merengues": "Real Madrid", "colchoneros": "Atletico Madrid", "rojiblancos": "Atletico Madrid",
    "red devils": "Manchester United", "gunners": "Arsenal", "reds": "Liverpool",
    "citizens": "Manchester City", "spurs": "Tottenham", "blues": "Chelsea",
}
JARGON = (
    "Gergo: 'here we go'/'fumata bianca'/'visite mediche' = done; 'intesa'/'accordo trovato' = conf; "
    "'sondaggio'/'idea'/'piace' = rumor; 'prestito', 'riscatto', 'clausola', 'parametro zero' = trasferimenti reali."
)

def glossary_block():
    al = "; ".join(f"{k}={v}" for k, v in ALIAS.items())
    return "ALIAS SQUADRE: " + al + ".\n" + JARGON

# --- Few-shot: esempi guida per la CLASSIFICAZIONE (compatti) ---
# Ogni esempio: (messaggio, json_atteso)
CLASSIFY_EXAMPLES = [
    ("Vlahovic lascia la Juventus, intesa totale col Milan",
     '{"transfer":true,"stato":"conf","giocatore":"Dusan Vlahovic","squadra":"Juventus","direzione":"out","club":"Milan","smentita":false}'),
    ("L\'Inter pensa a Tonali per rinforzare il centrocampo",
     '{"transfer":true,"stato":"rumor","giocatore":"Sandro Tonali","squadra":"Inter","direzione":"in","club":"","smentita":false}'),
    ("Here we go! Leao al Real Madrid, contratto depositato",
     '{"transfer":true,"stato":"done","giocatore":"Rafael Leao","squadra":"Real Madrid","direzione":"in","club":"Milan","smentita":false}'),
    ("Salta tutto: niente Napoli per Osimhen, trattativa naufragata",
     '{"transfer":true,"stato":"conf","giocatore":"Victor Osimhen","squadra":"Napoli","direzione":"out","club":"","smentita":true}'),
    ("De Laurentiis in conferenza: \'Il mondo e\' pieno di giocatori\'",
     '{"transfer":false}'),
]

def classify_system(langname="italiano"):
    """System prompt per classificare un messaggio. Campi attesi nel JSON di risposta."""
    return (
        CHARTER + "\n" + glossary_block() + "\n"
        "Classifica il messaggio dell'utente. Rispondi SOLO con JSON valido, campi:\n"
        "- transfer: true solo se riguarda trasferimento/trattativa/rinnovo/voce su un calciatore; false per gossip, partite, opinioni.\n"
        "- titolo: titolo conciso e neutro (max 100 caratteri) in " + langname + ", senza emoji/hashtag/virgolette.\n"
        "- stato: done|conf|obj|rumor secondo le definizioni sopra.\n"
        "- squadra: il club di Serie A/La Liga/Premier coinvolto (vuoto se nessuno).\n"
        "- giocatore: nome del calciatore (vuoto se non chiaro).\n"
        "- direzione: 'in' se arriva alla 'squadra', 'out' se la lascia.\n"
        "- club: l'altra squadra coinvolta (vuoto se non citata).\n"
        "- smentita: true se annulla un affare gia' dato; false altrimenti."
    )

def classify_messages(text, langname="italiano", n_examples=3):
    """Costruisce l'array di messaggi (system + few-shot + user) per la classificazione."""
    msgs = [{"role": "system", "content": classify_system(langname)}]
    for ex_in, ex_out in CLASSIFY_EXAMPLES[:n_examples]:
        msgs.append({"role": "user", "content": ex_in})
        msgs.append({"role": "assistant", "content": ex_out})
    msgs.append({"role": "user", "content": text[:500]})
    return msgs

# --- Stile articoli ---
def article_system():
    return (
        CHARTER + "\n"
        "Ora scrivi come GIORNALISTA di TransferBeat. Stile: breve, fattuale, professionale. "
        "Ogni affermazione ATTRIBUITA esplicitamente alla fonte (es. 'Secondo Gianluca Di Marzio...'). "
        "2-3 paragrafi brevi e in italiano scorrevole. Rispetta SEMPRE la direzione del movimento (chi lascia quale club e verso quale va). "
        "Se lo stato e' 'done' scrivi 'ufficiale'; se e' una smentita, spiega che l'affare e' saltato. "
        "Chiudi con UNA frase naturale sullo stato della trattativa: NON copiare etichette tecniche come 'rumor/obj/conf/done' ne definizioni interne. "
        "NON inventare nulla che non sia nelle note. Rispondi SOLO con JSON valido."
    )

# --- Estrazione movimenti (vista Nomi in build.py) ---
def movements_system():
    return (
        CHARTER + "\n" + glossary_block() + "\n"
        "Dalle notizie estrai i movimenti di singoli giocatori per la squadra indicata. "
        "Ignora notizie che non sono il movimento di un calciatore. Non inventare. Rispondi SOLO con JSON valido."
    )
