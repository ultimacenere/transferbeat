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
        "Usa ESCLUSIVAMENTE i nomi di giocatori e club presenti nelle note: NON aggiungere altri "
        "giocatori, trasferimenti o dettagli, e NON citare ex giocatori o trasferimenti del passato. "
        "Se un'informazione non e' nelle note, non scriverla. NON inventare nulla. Rispondi SOLO con JSON valido."
    )

# --- Estrazione movimenti (vista Nomi in build.py) ---
def movements_system():
    return (
        CHARTER + "\n" + glossary_block() + "\n"
        "Dalle notizie estrai i movimenti di singoli giocatori per la squadra indicata. "
        "Ignora notizie che non sono il movimento di un calciatore. Non inventare. Rispondi SOLO con JSON valido."
    )

# --- Estrazione movimenti v2: GLOBALE, con club espliciti da->a ---
MOVES_RULES = (
    "Estrai dai titoli i MOVIMENTI di mercato di SINGOLI CALCIATORI.\n"
    "- SOLO calciatori: ignora allenatori, dirigenti, procuratori, arbitri.\n"
    "- SOLO club ESPLICITAMENTE scritti nel titolo: NON dedurre club dalla tua memoria. "
    "Se la provenienza o la destinazione non e' scritta, lascia il campo vuoto.\n"
    "- Ignora: rinnovi di contratto, convocazioni, infortuni, opinioni, interviste, "
    "titoli-raccolta generici senza movimenti espliciti.\n"
    "- Ignora movimenti STORICI o passati, amarcord, anniversari e riferimenti a EX giocatori "
    "(es. 'l'ex Inter X', 'ai tempi di'): estrai SOLO trasferimenti del mercato ATTUALE in corso.\n"
    "- Un titolo puo' contenere PIU' movimenti: estraili tutti.\n"
    "- Usa il nome COSI' come scritto: se c'e' solo il cognome riporta solo il cognome, "
    "NON aggiungere ne inventare il nome di battesimo.\n"
    '- Formato: {"movimenti":[{"giocatore":"","da":"","a":"","stato":"rumor|obj|conf|done"}]}'
)
MOVES_EXAMPLE_IN = ("Notizie:\n"
 "- Dumfries via dall'Inter: accordo col Real Madrid, pronta la clausola\n"
 "- Calciomercato: le news di oggi e le trattative LIVE\n"
 "- Inter, Provedel e' sempre piu' vicino\n"
 "- Slot-Milan, contatti avviati con l'allenatore olandese\n"
 "- Hojlund firma per il Napoli: lascia il Manchester United, e' ufficiale\n"
 "- Altro che Premier: la volonta' di Stankovic e' chiara\n"
 "- Solet rinnova con l'Udinese... per ora: l'Inter osserva")
MOVES_EXAMPLE_OUT = ('{"movimenti":['
 '{"giocatore":"Denzel Dumfries","da":"Inter","a":"Real Madrid","stato":"conf"},'
 '{"giocatore":"Ivan Provedel","da":"","a":"Inter","stato":"obj"},'
 '{"giocatore":"Rasmus Hojlund","da":"Manchester United","a":"Napoli","stato":"done"},'
 '{"giocatore":"Oumar Solet","da":"Udinese","a":"Inter","stato":"rumor"}'
 ']}')

def movements_messages(titles):
    """Messaggi per l'estrazione globale: system compatto + 1 esempio guida + titoli."""
    sys_p = ("Sei l'analista di calciomercato di TransferBeat (Serie A, La Liga, Premier League). "
             "STATI: rumor=voce/interesse; obj=trattativa/contatti/offerta; conf=affare dato per fatto/accordo; "
             "done=ufficiale/firmato/visite mediche.\n" + glossary_block() + "\n" + MOVES_RULES +
             "\nRispondi SOLO con JSON valido.")
    return [{"role": "system", "content": sys_p},
            {"role": "user", "content": MOVES_EXAMPLE_IN},
            {"role": "assistant", "content": MOVES_EXAMPLE_OUT},
            {"role": "user", "content": "Notizie:\n- " + "\n- ".join(titles)}]

# --- Allenatori/tecnici noti: MAI giocatori (rete deterministica anti-errore) ---
COACHES = {"slot","gasperini","sarri","allegri","conte","mourinho","ancelotti","simeone",
           "guardiola","arteta","klopp","ten hag","emery","iraola","de zerbi","italiano",
           "palladino","baroni","tudor","vanoli","chivu","inzaghi","pioli","spalletti",
           "thiago motta","fonseca","xavi","flick","luis enrique","xabi alonso","zidane",
           "de rossi","gilardino","nesta","gattuso","jaissle","postecoglou","maresca"}

def is_coach(name):
    import re as _re
    n = _re.sub(r"[^a-z ]", "", (name or "").lower()).strip()
    if not n:
        return False
    if n in COACHES:
        return True
    last = n.split()[-1] if n.split() else ""
    return last in COACHES
