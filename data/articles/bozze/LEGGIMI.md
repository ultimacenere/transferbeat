# Bozze di articoli — NON pubblicate

`scripts/articles.py::all_articles()` legge **ogni `.json` dentro `data/articles/`** e `render_articles.render_all`
lo trasforma in pagina e lo mette in sitemap. Una sottocartella non viene letta (il filtro è `fn.endswith('.json')`,
che su una directory è falso), quindi questo è il posto sicuro dove tenere un articolo pronto ma **non approvato**.

## bilancio-mercato-estate-2026.json (2026-09-07)

Fase J di `kb/RIPARTENZA.md` §8: il bilancio del mercato estivo ricostruito dallo storico della board.
Il metodo regge e i conteggi sono riproducibili, ma una revisione avversariale lo ha giudicato **non pubblicabile**:

- fra le operazioni contate ce n'erano che i **titoli stessi dichiarano non concluse** (una negazione, e un marcatore
  di ufficialità riferito a una dichiarazione): un pezzo intitolato «in N operazioni ufficiali» non può contarle;
- **club attribuiti a operazioni da cui erano rimasti fuori** («Roma, sfuma anche Garnacho», «Real Oviedo beffato»):
  il club viene estratto dal titolo, e il titolo a volte lo nomina proprio per dire che l'affare non è suo;
- le fonti citate erano 12 link ma **9 editori**, perché la deduplica è sul nome visualizzato e non sul dominio
  («Sky Sport» e «sport.sky.it» sono lo stesso giornale), e il doppione finisce anche nel JSON-LD `citation`.

Rigenerarlo: `py -X utf8 scripts/bilancio.py` (deterministico, `--dry` per i soli conteggi).
Per pubblicarlo servono quelle tre correzioni, poi basta spostare il file in `data/articles/` e lanciare il render.

**Limiti dichiarati che restano anche dopo**, e che la pagina dice di sé: la direzione dei movimenti non è
ricostruibile dai titoli (per questo l'articolo non nomina nessun trasferimento), le cifre degli affari non ci sono,
e la graduatoria dei club risente della copertura delle fonti locali.
