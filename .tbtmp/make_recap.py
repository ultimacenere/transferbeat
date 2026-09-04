import json, datetime, os

slug = "recap-2026-09-03"
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

it = {
 "title": "Coppa Italia accende il giovedì, campionati pronti a ripartire",
 "lead": "Giovedì senza gare concluse nei sei campionati seguiti da TransferBeat: il palcoscenico è tutto della Coppa Italia, con il secondo turno che vale gli ottavi. In serata si riaccendono Liga e Ligue 1, mentre da domani tornano in campo Serie A, Premier e Bundesliga.",
 "body": [
  "Nessuna delle partite dei sei tornei principali risulta chiusa oggi: i dati non registrano risultati finali per giovedì 3 settembre. A tenere banco è la Coppa Italia: nel pomeriggio sono scesi in campo Palermo-Mantova e Sassuolo-Frosinone, mentre in serata tocca a Cagliari-Verona (Calciomercato.com). Nel turno l'Udinese ha superato il Venezia per 2-1, con il raddoppio di Bayo, ed è agli ottavi, dove affronterà l'Atalanta (Calciomercato.com); i punteggi delle sfide ancora in corso non sono nei dati ufficiali di TransferBeat e restano quindi provvisori.",
  "In classifica non cambia nulla, perché senza gare concluse le graduatorie restano quelle dell'ultimo turno. In Serie A comanda la Roma con 6 punti e 8 gol fatti, a punteggio pieno insieme a Inter, Milan, Juventus, Atalanta e Lazio. In Liga guidano Barcellona e Real Madrid a quota 9; in Premier League avanti Manchester City e Arsenal a 6; in Ligue 1 il Monaco a punteggio pieno con 6; in Bundesliga, dopo una sola giornata, in testa c'è il Bayern.",
  "Sul fronte societario e delle ufficialità, il Napoli ha blindato Giovanni Di Lorenzo con il rinnovo fino al 2030 (Gianluca Di Marzio) e ha diramato la lista Champions, con Favasuli incluso e Marianucci e Giovane esclusi (napolicalcionews.it); Scott McTominay ha spiegato di aver concordato con il club uno stop per un problema fisico (ANSA). All'Inter è ufficiale l'addio del direttore sportivo Piero Ausilio con effetto immediato, con Baccin promosso al suo posto (Gianluca Di Marzio, ANSA); Lautaro Martinez ha ammesso che l'interesse del Barcellona era reale ma ha scelto di restare in nerazzurro (Gianluca Di Marzio).",
  "Sul piano dei casi e delle liste, la UEFA ha aperto un procedimento nei confronti di Guendouzi e Greenwood, mentre Roma, Napoli, Como e Juventus registrano esclusioni dalle liste europee (Calciomercato.com); la Lazio ha lasciato fuori Pellegrini e Patric dalla lista per la Serie A (Calciomercato.com). In infermeria, il Bologna perde Riccardo Orsolini per circa tre settimane (Calciomercato.com). Per la terza giornata di Serie A la designazione arbitrale affida Inter-Napoli a Sozza e Juventus-Milan a Mariani (ANSA). Tra le dichiarazioni, Luka Modric ha chiesto un Milan piu ambizioso e promesso il massimo impegno, mentre Cesc Fabregas si e detto convinto che il Como possa competere su tutti i fronti (ANSA).",
  "Stasera i campionati si riaccendono con due anticipi: in Liga la Real Sociedad ospita il Celta Vigo (21:00), in Ligue 1 il Tolosa sfida il Lille (20:45); entrambe, all'ultimo aggiornamento dei dati, risultavano ancora da giocare. In Coppa Italia chiude il programma odierno Cagliari-Verona.",
  "Domani, venerdi 4 settembre, si entra nel vivo: la Serie A apre la terza giornata con Genoa-Como (20:45), la Premier League propone Ipswich-Liverpool (21:00), la Bundesliga schiera Stoccarda-Colonia (20:30) e la Ligue 1 mette in fila Lione-Auxerre (19:00) e il big match PSG-Monaco (21:05). Orari italiani."
 ]
}

en = {
 "title": "Coppa Italia lights up Thursday as leagues get set to resume",
 "lead": "A Thursday with no completed games across the six competitions TransferBeat follows: the stage belongs to the Coppa Italia, whose second round decides the last-16 spots. Later tonight LaLiga and Ligue 1 return, and from tomorrow Serie A, the Premier League and the Bundesliga are back.",
 "body": [
  "None of the matches in the six main competitions is recorded as finished today: the data show no final results for Thursday 3 September. The spotlight is on the Coppa Italia: Palermo-Mantova and Sassuolo-Frosinone were played in the afternoon, with Cagliari-Verona to follow in the evening (Calciomercato.com). In this round Udinese beat Venezia 2-1, Bayo adding the second goal, and reached the last 16, where they will meet Atalanta (Calciomercato.com); scores of ties still in progress are not in TransferBeat's official data and remain provisional.",
  "Nothing changes in the tables, because with no games completed the standings are those from the last round. In Serie A, Roma lead with 6 points and 8 goals scored, on maximum points alongside Inter, Milan, Juventus, Atalanta and Lazio. In LaLiga, Barcelona and Real Madrid top the table on 9; in the Premier League, Manchester City and Arsenal lead on 6; in Ligue 1, Monaco are on a perfect 6; in the Bundesliga, after a single matchday, Bayern are on top.",
  "Off the pitch, Napoli tied down Giovanni Di Lorenzo with a renewal until 2030 (Gianluca Di Marzio) and released their Champions League list, with Favasuli included and Marianucci and Giovane left out (napolicalcionews.it); Scott McTominay said he had agreed a break with the club over a physical problem (ANSA). At Inter, sporting director Piero Ausilio's exit is official with immediate effect, with Baccin stepping up in his place (Gianluca Di Marzio, ANSA); Lautaro Martinez admitted Barcelona's interest was real but that he chose to stay (Gianluca Di Marzio).",
  "On cases and squad lists, UEFA opened proceedings against Guendouzi and Greenwood, while Roma, Napoli, Como and Juventus recorded exclusions from their European lists (Calciomercato.com); Lazio left Pellegrini and Patric off their Serie A list (Calciomercato.com). In the treatment room, Bologna lose Riccardo Orsolini for about three weeks (Calciomercato.com). For Serie A's third round the referee appointments give Inter-Napoli to Sozza and Juventus-Milan to Mariani (ANSA). Among the statements, Luka Modric called for a more ambitious Milan and promised his full commitment, while Cesc Fabregas said he is convinced Como can compete on every front (ANSA).",
  "Tonight the leagues return with two openers: in LaLiga, Real Sociedad host Celta Vigo (21:00), and in Ligue 1, Toulouse face Lille (20:45); both, as of the last data update, were still to be played. The Coppa Italia day closes with Cagliari-Verona.",
  "Tomorrow, Friday 4 September, it gets serious: Serie A opens its third round with Genoa-Como (20:45), the Premier League offers Ipswich-Liverpool (21:00), the Bundesliga lines up Stuttgart-Cologne (20:30), and Ligue 1 has Lyon-Auxerre (19:00) and the big match PSG-Monaco (21:05). Times are CET."
 ]
}

es = {
 "title": "La Copa Italia anima el jueves; las ligas listas para volver",
 "lead": "Un jueves sin partidos concluidos en las seis competiciones que sigue TransferBeat: el protagonismo es todo de la Copa Italia, cuya segunda ronda reparte los octavos. Esta noche vuelven LaLiga y la Ligue 1, y desde manana regresan la Serie A, la Premier League y la Bundesliga.",
 "body": [
  "Ninguno de los partidos de las seis competiciones principales figura como finalizado hoy: los datos no registran resultados definitivos para el jueves 3 de septiembre. El foco esta en la Copa Italia: por la tarde se jugaron Palermo-Mantova y Sassuolo-Frosinone, y por la noche llega el turno de Cagliari-Verona (Calciomercato.com). En esta ronda el Udinese gano 2-1 al Venezia, con el segundo gol de Bayo, y esta en octavos, donde se medira al Atalanta (Calciomercato.com); los marcadores de las eliminatorias aun en juego no estan en los datos oficiales de TransferBeat y son por tanto provisionales.",
  "En la clasificacion no cambia nada, porque sin partidos concluidos las tablas siguen siendo las de la ultima jornada. En la Serie A manda la Roma con 6 puntos y 8 goles a favor, con pleno de puntos junto a Inter, Milan, Juventus, Atalanta y Lazio. En LaLiga lideran Barcelona y Real Madrid con 9; en la Premier League van por delante Manchester City y Arsenal con 6; en la Ligue 1 el Monaco suma un pleno de 6; en la Bundesliga, tras una sola jornada, manda el Bayern.",
  "Fuera del campo, el Napoli blindo a Giovanni Di Lorenzo con la renovacion hasta 2030 (Gianluca Di Marzio) y comunico su lista de Champions, con Favasuli incluido y Marianucci y Giovane excluidos (napolicalcionews.it); Scott McTominay explico que acordo con el club una pausa por un problema fisico (ANSA). En el Inter es oficial la salida del director deportivo Piero Ausilio con efecto inmediato, con Baccin en su lugar (Gianluca Di Marzio, ANSA); Lautaro Martinez admitio que el interes del Barcelona era real pero que eligio quedarse (Gianluca Di Marzio).",
  "En cuanto a casos y listas, la UEFA abrio un procedimiento contra Guendouzi y Greenwood, mientras que Roma, Napoli, Como y Juventus registran exclusiones de sus listas europeas (Calciomercato.com); la Lazio dejo fuera a Pellegrini y Patric de su lista para la Serie A (Calciomercato.com). En la enfermeria, el Bologna pierde a Riccardo Orsolini unas tres semanas (Calciomercato.com). Para la tercera jornada de la Serie A las designaciones arbitrales dan Inter-Napoli a Sozza y Juventus-Milan a Mariani (ANSA). Entre las declaraciones, Luka Modric pidio un Milan mas ambicioso y prometio su maximo esfuerzo, mientras que Cesc Fabregas se dijo convencido de que el Como puede competir en todos los frentes (ANSA).",
  "Esta noche las ligas vuelven con dos aperturas: en LaLiga, la Real Sociedad recibe al Celta de Vigo (21:00), y en la Ligue 1, el Toulouse se mide al Lille (20:45); ambos, segun la ultima actualizacion de los datos, estaban aun por jugarse. La jornada de Copa Italia se cierra con Cagliari-Verona.",
  "Manana, viernes 4 de septiembre, la cosa va en serio: la Serie A abre su tercera jornada con Genoa-Como (20:45), la Premier League ofrece Ipswich-Liverpool (21:00), la Bundesliga alinea Stuttgart-Colonia (20:30) y la Ligue 1 presenta Lyon-Auxerre (19:00) y el gran duelo PSG-Monaco (21:05). Horario italiano (CET)."
 ]
}

art = {
 "slug": slug, "tipo": "recap", "giocatore": "", "team": "", "league": "",
 "lab": "RECAP", "col": "#0a9d57", "stato": "done", "smentita": False,
 "created": now, "updated": now, "updates": [],
 "content": {"it": it, "en": en, "es": es}
}

# title length checks
for lang in ("it","en","es"):
    t=art["content"][lang]["title"]
    print(lang, "title chars:", len(t), "->", t)

os.makedirs("data/articles", exist_ok=True)
with open("data/articles/%s.json" % slug, "w", encoding="utf-8") as f:
    json.dump(art, f, ensure_ascii=False, indent=1)
print("WROTE data/articles/%s.json" % slug)
