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
    "Sei l'analista di TransferBeat, sito di calcio su Serie A, La Liga e Premier League: "
    "campionati, coppe europee e mercato. "
    "Lavori SOLO su questi tre campionati: se nessun club delle tre leghe e' coinvolto, 'squadra' resta vuota.\n"
    "STATI: scala di CONCRETEZZA, valida sia per il calcio giocato sia per il mercato.\n"
    "In caso di DUBBIO scegli SEMPRE lo stato piu' BASSO:\n"
    "- rumor (DEFAULT): commento o voce. Calcio giocato: analisi, opinione, dichiarazione, classifica, pagelle, moviola, indiscrezione su un infortunio. Mercato: idea, interesse anche concreto, sondaggio, 'piace', 'seguito', 'possibile trattativa', 'sogno', 'tentativo', 'pista', 'ci pensa', 'spinge per'.\n"
    "- obj: qualcosa di IMMINENTE o gia' in corso. Calcio giocato: vigilia, probabili formazioni, convocati, presentazione, conferenza stampa, orario e dove vedere. Mercato: trattativa REALMENTE avviata con contatti diretti o OFFERTA gia' presentata: 'incontro con l'agente', 'pressing', 'sempre piu' vicino', 'affondo'.\n"
    "- conf: ATTO UFFICIALE di un club o di una lega. Calcio giocato: formazioni ufficiali, comunicato, squalifica, rinvio, sorteggio, esonero, nuovo allenatore. Mercato: accordo RAGGIUNTO esplicito: 'accordo trovato', 'intesa totale', 'fumata bianca', 'ha detto si', 'manca solo la firma'. Un interesse o una trattativa NON bastano per 'conf'.\n"
    "- done: FATTO AVVENUTO, non piu' modificabile. Calcio giocato: risultato, tabellino, gol, doppietta, espulsione, eliminazione, qualificazione, fine partita. Mercato: SOLO ufficialita' esplicita: 'ufficiale', comunicato del club, 'ha firmato', visite mediche FATTE, 'here we go', annuncio.\n"
    "REGOLA: classifica per cio' che la notizia dice ORA; NON gonfiare lo stato. Un interesse o una possibile trattativa resta 'rumor'.\n"
    "SMENTITA: metti smentita=true solo se la notizia ANNULLA/NEGA qualcosa gia' dato ('salta tutto', 'naufragata', 'nessun accordo', 'resta', 'partita rinviata').\n"
    "ANTI-INVENZIONE: usa SOLO cio' che e' scritto nel testo. Non inventare cifre, date, dichiarazioni, risultati o club non citati.\n"
    "Nei trasferimenti distingui sempre PROVENIENZA e DESTINAZIONE: direzione 'out' se lascia la 'squadra', 'in' se la raggiunge. Per le notizie di campionato i campi giocatore/direzione/club restano vuoti se non pertinenti."
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
    ("Cagliari-Inter 1-2, decide Lautaro nel recupero",
     '{"transfer":true,"titolo":"Cagliari-Inter 1-2, decide Lautaro nel recupero","stato":"done","giocatore":"","squadra":"Inter","direzione":"in","club":"","smentita":false}'),
    ("Vlahovic lascia la Juventus, intesa totale col Milan",
     '{"transfer":true,"titolo":"Vlahovic verso il Milan, intesa totale con la Juventus","stato":"conf","giocatore":"Dusan Vlahovic","squadra":"Juventus","direzione":"out","club":"Milan","smentita":false}'),
    ("Probabili formazioni Milan-Roma: Leao dal primo minuto, Dybala in panchina",
     '{"transfer":true,"titolo":"Probabili formazioni Milan-Roma: Leao titolare, Dybala in panchina","stato":"obj","giocatore":"","squadra":"Milan","direzione":"in","club":"","smentita":false}'),
    ("Formazioni ufficiali Napoli-Como: Lukaku guida l attacco",
     '{"transfer":true,"titolo":"Formazioni ufficiali Napoli-Como: Lukaku in attacco","stato":"conf","giocatore":"","squadra":"Napoli","direzione":"in","club":"","smentita":false}'),
    ("Inter, Bastoni out per infortunio: salta il derby",
     '{"transfer":true,"titolo":"Inter, Bastoni out per infortunio: salta il derby","stato":"rumor","giocatore":"","squadra":"Inter","direzione":"in","club":"","smentita":false}'),
    ("L\'Inter pensa a Tonali per rinforzare il centrocampo",
     '{"transfer":true,"titolo":"L Inter pensa a Tonali per il centrocampo","stato":"rumor","giocatore":"Sandro Tonali","squadra":"Inter","direzione":"in","club":"","smentita":false}'),
    ("Here we go! Leao al Real Madrid, contratto depositato",
     '{"transfer":true,"titolo":"Ufficiale: Leao al Real Madrid","stato":"done","giocatore":"Rafael Leao","squadra":"Real Madrid","direzione":"in","club":"Milan","smentita":false}'),
    ("Salta tutto: niente Napoli per Osimhen, trattativa naufragata",
     '{"transfer":true,"titolo":"Salta la trattativa tra Napoli e Osimhen","stato":"conf","giocatore":"Victor Osimhen","squadra":"Napoli","direzione":"out","club":"","smentita":true}'),
    ("Scarica la nostra app e vinci il fantacalcio! Codice promo TB2026",
     '{"transfer":false}'),
]

def classify_system(langname="italiano"):
    """System prompt per classificare un messaggio. Campi attesi nel JSON di risposta."""
    return (
        CHARTER + "\n" + glossary_block() + "\n"
        "Classifica il messaggio dell'utente. Rispondi SOLO con JSON valido, campi:\n"
        "- transfer: true se il messaggio e' una notizia di calcio PUBBLICABILE (risultato, tabellino, formazioni, infortunio, squalifica, sorteggio, esonero, dichiarazione tecnica, trasferimento o trattativa); false SOLO per cio' che non e' pubblicabile: pubblicita', scommesse, sondaggi, quiz, meme, saluti, contenuti non calcistici.\n"
        "- titolo: titolo conciso e neutro (max 100 caratteri) in " + langname + ", senza emoji/hashtag/virgolette.\n"
        "- stato: done|conf|obj|rumor secondo le definizioni sopra.\n"
        "- squadra: il club di Serie A/La Liga/Premier coinvolto (vuoto se nessuno).\n"
        "- giocatore: nome del calciatore (vuoto se non chiaro).\n"
        "- direzione: 'in' se arriva alla 'squadra', 'out' se la lascia.\n"
        "- club: l'altra squadra coinvolta (vuoto se non citata).\n"
        "- smentita: true se annulla un affare gia' dato; false altrimenti."
    )

def classify_batch_messages(testi, langname="italiano", n_examples=4):
    """Come classify_messages ma per PIU' messaggi in UNA sola chiamata.
    La parte fissa (carta editoriale + glossario + regole + esempi) pesa ~850 token:
    rispedirla per ogni singola notizia sfonda il tetto di 8000 token/minuto di Groq,
    le notizie oltre la nona prendono 429 e ricadono in silenzio sulle regole.
    In lotto il costo per notizia crolla di oltre dieci volte."""
    NL = chr(10)
    sistema = (classify_system(langname) + NL + NL +
        "LOTTO: l'utente invia PIU' messaggi numerati. Rispondi SOLO con JSON valido nella forma" + NL +
        '{"items":[{...},{...}]} con ESATTAMENTE un oggetto per messaggio ricevuto, nello STESSO' + NL +
        "ORDINE e con gli stessi campi descritti sopra. Nessun commento, nessun testo fuori dal JSON." + NL +
        'Ogni oggetto DEVE includere anche il campo "n" con il numero del messaggio a cui si riferisce.')
    msgs = [{"role": "system", "content": sistema}]
    for ex_in, ex_out in CLASSIFY_EXAMPLES[:n_examples]:
        msgs.append({"role": "user", "content": "1. " + ex_in})
        msgs.append({"role": "assistant", "content": '{"items":[{"n":1,' + ex_out[1:] + ']}'})
    corpo = NL.join(str(i + 1) + ". " + (x or "").replace(NL, " ")[:400]
                    for i, x in enumerate(testi))
    msgs.append({"role": "user", "content": corpo})
    return msgs

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
    "- STATO CONSERVATIVO: in dubbio usa 'rumor'. Marca 'done' SOLO con ufficialita' esplicita "
    "(ufficiale/ha firmato/visite mediche/comunicato/here we go); 'conf' SOLO con accordo esplicito "
    "(accordo/intesa/fumata bianca/manca solo la firma). Un interesse o una 'possibile trattativa' e' SEMPRE 'rumor'.\n"
    "- SOLO calcio MASCHILE dei club: ignora calcio femminile, giovanili/Primavera e nazionali.\n"
    '- Formato: {"movimenti":[{"giocatore":"","da":"","a":"","stato":"rumor|obj|conf|done"}]}'
)
MOVES_EXAMPLE_IN = ("Notizie:\n"
 "- Dumfries via dall'Inter: accordo raggiunto col Real Madrid, manca solo la firma\n"
 "- Calciomercato: le news di oggi e le trattative LIVE\n"
 "- Inter, offerta presentata al Lazio per Provedel: e' sempre piu' vicino\n"
 "- Slot-Milan, contatti avviati con l'allenatore olandese\n"
 "- Hojlund firma per il Napoli: lascia il Manchester United, e' ufficiale\n"
 "- Bastoni, possibile trattativa col Barcellona: i blaugrana ci pensano\n"
 "- Pio Esposito, blando interesse del Manchester United\n"
 "- Beth Mead saluta l'Arsenal femminile: va al Manchester City Women\n"
 "- Solet rinnova con l'Udinese... per ora: l'Inter osserva")
MOVES_EXAMPLE_OUT = ('{"movimenti":['
 '{"giocatore":"Denzel Dumfries","da":"Inter","a":"Real Madrid","stato":"conf"},'
 '{"giocatore":"Ivan Provedel","da":"Lazio","a":"Inter","stato":"obj"},'
 '{"giocatore":"Rasmus Hojlund","da":"Manchester United","a":"Napoli","stato":"done"},'
 '{"giocatore":"Alessandro Bastoni","da":"Inter","a":"Barcellona","stato":"rumor"},'
 '{"giocatore":"Pio Esposito","da":"","a":"Manchester United","stato":"rumor"},'
 '{"giocatore":"Oumar Solet","da":"Udinese","a":"Inter","stato":"rumor"}'
 ']}')

def movements_messages(titles):
    """Messaggi per l'estrazione globale: system compatto + 1 esempio guida + titoli."""
    sys_p = ("Sei l'analista di calciomercato di TransferBeat (Serie A, La Liga, Premier League). "
             "STATI: rumor=voce/interesse/possibile trattativa (DEFAULT); obj=trattativa avviata/contatti/offerta presentata; "
             "conf=accordo esplicito raggiunto; done=UFFICIALE (ufficiale/ha firmato/visite mediche/here we go). "
             "In DUBBIO usa 'rumor'; NON marcare done/conf senza parole esplicite.\n" + glossary_block() + "\n" + MOVES_RULES +
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

_PLAYERS = None
def _players():
    """Cognomi e nomi completi dei giocatori delle rose correnti (data/rosters.json), senza accenti.
    Serve a non scambiare per allenatori i giocatori che portano un cognome da allenatore
    (Giovanni Simeone, Vincenzo Italiano)."""
    global _PLAYERS
    if _PLAYERS is None:
        import unicodedata, os as _os, json as _json
        full, sur = set(), set()
        try:
            d = _json.load(open(_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "rosters.json"), encoding="utf-8"))
            for names in (d.get("rose") or {}).values():
                for nm in names:
                    n = unicodedata.normalize("NFKD", nm).encode("ascii", "ignore").decode("ascii").lower().strip()
                    full.add(n); sur.add(n.split()[-1] if n.split() else n)
        except Exception:
            pass
        _PLAYERS = (full, sur)
    return _PLAYERS

def is_coach(name):
    import re as _re, unicodedata as _ud
    n = _ud.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii").lower()
    n = _re.sub(r"[^a-z ]", "", n).strip()
    if not n:
        return False
    full, sur = _players()
    if n in full:                     # nome completo di un giocatore in rosa: mai allenatore
        return False
    parts = n.split(); last = parts[-1]
    if len(parts) == 1 and last in COACHES and last in sur:
        return False                  # solo cognome, e un giocatore in rosa lo porta (Simeone): ambiguo -> non allenatore
    return n in COACHES or last in COACHES
