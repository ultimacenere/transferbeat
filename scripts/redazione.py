#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - redazione.py: la procedura comune a TUTTE le pianificate che scrivono articoli.

Perche' esiste. L'8 settembre 2026 le tre pianificate del giorno hanno rigenerato gli articoli con gli script di
una copia locale ferma a qualche giorno prima: 609 pagine sono tornate alla grafica vecchia e ci sono rimaste sei
giorni, mentre ogni pianificata dichiarava "pubblicato". La procedura di pubblicazione stava scritta a parole in
nove prompt diversi e ognuno la eseguiva a modo suo. Qui la procedura e' codice, uguale per tutti, e si ferma da
sola quando qualcosa non torna.

Uso (dalla radice del repo, strumento Bash, timeout 600000):
  py -X utf8 scripts/redazione.py prepara  --pianificata NOME
  py -X utf8 scripts/redazione.py pubblica --pianificata NOME --slug SLUG [--corpo MIN-MAX] [--prova]
  py -X utf8 scripts/redazione.py rilascia --pianificata NOME [--slug SLUG]
  py -X utf8 scripts/redazione.py stato

La prima volta la copia locale puo' essere cosi' vecchia da non avere questo file: le pianificate lo prendono da
origin/main e lo lanciano da .git/ (kb/PIANIFICATE.md, passo 0).

REGOLA DI COSTRUZIONE: questo processo NON importa mai i moduli del sito (render_articles, articles, guard).
Rigenerazione e controlli li fa un SOTTOPROCESSO nuovo (`_rigenera`), lanciato dopo che la copia e' stata
riallineata a origin/main. Un processo che importa i moduli e poi riallinea continua a usare quelli vecchi gia'
caricati: e' lo stesso incidente dell'8 settembre, spostato dentro lo script.

NESSUNA ATTESA SUPERA 8 MINUTI: le pianificate lanciano i comandi con lo strumento Bash, che ha un tempo massimo
di 10 minuti; un comando che dura di piu' viene staccato e la pianificata non riceve mai il codice di uscita.

Codici di uscita
  0  fatto
  2  articolo non valido o argomenti non validi: si corregge e si rilancia (il turno resta preso)
  3  questa pianificata ha gia' pubblicato per il giorno di oggi: niente da fare
  4  un'altra pianificata sta lavorando: riprovare piu' tardi
  5  turno non preso (manca `prepara`) o preso da un'altra pianificata
  6  pagine del sito con una grafica diversa da quella corrente: NON si pubblica (turno liberato)
  7  gli articoli non tornano (uno sparirebbe o ce n'e' uno in piu'): NON si pubblica (turno liberato)
  8  pubblicato su GitHub, ma la pagina con questa versione non risulta online entro l'attesa (turno liberato)
  9  errore di git, di rete o imprevisto (turno liberato)
"""
import argparse, datetime as dt, json, os, re, shutil, subprocess, sys, time, traceback, urllib.request, uuid

RAMO = "main"
PERCORSI_ARTICOLI = ("data/articles/", "articoli/", "sitemap-articoli.xml", "sitemap.xml")
SITO = "https://transferbeat.com"
ATTESA_TURNO_MIN = 8           # attesa massima di prepara se un'altra pianificata sta lavorando
TURNO_STANTIO_MIN = 60         # un turno senza segni di vita da un'ora e' di una pianificata morta
ATTESA_ONLINE_MIN = 4          # attesa massima per vedere la pagina nuova servita da Vercel
BACKUP_GIORNI = 14
LINGUE = ("it", "en", "es")


# ----------------------------------------------------------------------------------------------- tempo
def ora_roma(t_utc=None):
    """Ora italiana senza tzdata (su questa macchina zoneinfo non ha Europe/Rome): ora legale dall'ultima domenica di
    marzo alle 01:00 UTC all'ultima domenica di ottobre alle 01:00 UTC."""
    t = t_utc or dt.datetime.now(dt.timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    t = t.astimezone(dt.timezone.utc)

    def ultima_domenica(mese):
        g = dt.date(t.year, mese, 31)
        while g.weekday() != 6:
            g -= dt.timedelta(days=1)
        return dt.datetime.combine(g, dt.time(1), dt.timezone.utc)
    offset = 2 if ultima_domenica(3) <= t < ultima_domenica(10) else 1
    return (t + dt.timedelta(hours=offset)).replace(tzinfo=dt.timezone(dt.timedelta(hours=offset)))


def da_iso(s, serve_fuso=False):
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if serve_fuso and t.tzinfo is None:
        return None
    return t


# ----------------------------------------------------------------------------------------------- git
class ErroreGit(RuntimeError):
    pass


def sh(args, cwd, env=None, check=True, input_bytes=None):
    r = subprocess.run(args, cwd=cwd, env=env, capture_output=True, input=input_bytes)
    out = r.stdout.decode("utf-8", "replace")
    if check and r.returncode != 0:
        raise ErroreGit("%s -> uscito con %d: %s" % (" ".join(args[:4]), r.returncode,
                                                    r.stderr.decode("utf-8", "replace").strip()[:400]))
    return out


def env_git(repo, **extra):
    """Ambiente per i comandi che creano commit: se il repo non ha un'identita' configurata, commit-tree fallisce
    ("Author identity unknown"). Sulla copia del Desktop c'e', su una copia nuova no: lo script non deve funzionare
    per caso."""
    env = dict(os.environ, **extra)
    if not sh(["git", "config", "user.email"], repo, check=False).strip():
        for k, v in (("GIT_AUTHOR_NAME", "TransferBeat Bot"), ("GIT_AUTHOR_EMAIL", "bot@transferbeat.com"),
                     ("GIT_COMMITTER_NAME", "TransferBeat Bot"), ("GIT_COMMITTER_EMAIL", "bot@transferbeat.com")):
            env.setdefault(k, v)
    return env


def radice_repo(partenza):
    return sh(["git", "rev-parse", "--show-toplevel"], partenza).strip()


def git_dir(repo):
    return sh(["git", "rev-parse", "--absolute-git-dir"], repo).strip()


def fetch(repo):
    for tentativo in range(3):
        try:
            sh(["git", "fetch", "-q", "origin", RAMO], repo)
            return
        except ErroreGit:
            if tentativo == 2:
                raise
            time.sleep(10)


def origine(repo):
    return sh(["git", "rev-parse", "origin/" + RAMO], repo).strip()


def json_articoli(repo, rev):
    """{percorso: dict} di tutti i data/articles/*.json a una revisione, letti con un solo processo git."""
    elenco = sh(["git", "ls-tree", "--name-only", rev, "data/articles/"], repo).split()
    nomi = [n for n in elenco if n.endswith(".json") and not n.endswith("index.json")]
    if not nomi:
        return {}
    richiesta = "".join("%s:%s\n" % (rev, n) for n in nomi).encode("utf-8")
    r = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, input=richiesta, capture_output=True)
    dati, pos, out = r.stdout, 0, {}
    for n in nomi:
        a_capo = dati.index(b"\n", pos)
        testa = dati[pos:a_capo].split()
        if len(testa) < 3:
            pos = a_capo + 1
            continue
        lung = int(testa[2])
        corpo = dati[a_capo + 1:a_capo + 1 + lung]
        pos = a_capo + 1 + lung + 1
        try:
            out[n] = json.loads(corpo.decode("utf-8"))
        except ValueError:
            out[n] = {}
    return out


def impronta_origine(repo):
    """La riga ':root{--bg:...' di site_common.py COME E' SU origin/main: l'impronta della grafica corrente.
    Presa da origin e non dal file locale, che potrebbe essere vecchio."""
    css = sh(["git", "show", "origin/%s:scripts/site_common.py" % RAMO], repo)
    i = css.find(":root{--bg:")
    return css[i:css.index("\n", i)] if i >= 0 else None


# ----------------------------------------------------------------------------------------------- turno
def file_turno(repo):
    return os.path.join(git_dir(repo), "redazione.lock")


def leggi_turno(repo):
    try:
        with open(file_turno(repo), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def eta_turno_min(repo):
    """Minuti dall'ultimo segno di vita del turno (la data di modifica del file, aggiornata a ogni comando)."""
    try:
        return (time.time() - os.path.getmtime(file_turno(repo))) / 60
    except OSError:
        return None


def battito(repo):
    try:
        os.utime(file_turno(repo), None)
    except OSError:
        pass


def _scrivi_turno(percorso, dati):
    tmp = percorso + ".tmp-" + uuid.uuid4().hex
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dati, f)
    os.replace(tmp, percorso)


def prendi_turno(repo, pianificata, attesa_min):
    """Turno atomico: O_EXCL crea il file solo se non esiste, quindi due pianificate non possono prenderlo insieme.
    Un turno stantio o illeggibile si riprende scrivendo un file temporaneo, rinominandolo e rileggendo."""
    percorso = file_turno(repo)
    mio = {"pianificata": pianificata, "id": uuid.uuid4().hex, "pid": os.getpid(),
           "inizio": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    fine = time.time() + attesa_min * 60
    while True:
        try:
            fd = os.open(percorso, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(mio, f)
            return mio, None
        except FileExistsError:
            pass
        t, eta = leggi_turno(repo), eta_turno_min(repo)
        motivo = None
        if t is None:
            motivo = "turno illeggibile"
        elif t.get("pianificata") == pianificata:
            motivo = "turno lasciato da un giro precedente della stessa pianificata"
        elif eta is not None and eta >= TURNO_STANTIO_MIN:
            motivo = "turno di '%s' senza segni di vita da %.0f minuti" % (t.get("pianificata"), eta)
        if motivo:
            _scrivi_turno(percorso, mio)
            if (leggi_turno(repo) or {}).get("id") == mio["id"]:
                return mio, motivo
        if time.time() >= fine:
            return None, "turno di '%s', ultimo segno di vita %.0f minuti fa" % ((t or {}).get("pianificata"), eta or 0)
        time.sleep(30)


def turno_mio(repo, pianificata):
    t = leggi_turno(repo)
    return t if t and t.get("pianificata") == pianificata else None


def rilascia_turno(repo, pianificata=None):
    t = leggi_turno(repo)
    if t is None or (pianificata and t.get("pianificata") != pianificata):
        return False
    try:
        os.remove(file_turno(repo))
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------------------------------- copia locale
def backup_copia(repo):
    """Prima di riallineare: le modifiche ai file tracciati e un eventuale commit locale non pubblicato finiscono in
    ref di backup. Riallineare serve a buttare via una copia vecchia, ma "buttare via" deve restare recuperabile."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    salvati = []
    testa = sh(["git", "rev-parse", "HEAD"], repo).strip()
    dentro = subprocess.run(["git", "merge-base", "--is-ancestor", testa, "origin/" + RAMO], cwd=repo).returncode == 0
    if not dentro:
        sh(["git", "update-ref", "refs/backup/redazione/%s-head" % stamp, testa], repo)
        salvati.append("commit locale %s non in main -> refs/backup/redazione/%s-head" % (testa[:10], stamp))
    sporchi = [l for l in sh(["git", "status", "--porcelain", "--untracked-files=no"], repo).splitlines() if l.strip()]
    if sporchi:
        env = env_git(repo, GIT_INDEX_FILE=os.path.join(git_dir(repo), "redazione_backup_idx"))
        try:
            sh(["git", "read-tree", "HEAD"], repo, env=env)
            sh(["git", "add", "-u", "--", "."], repo, env=env)
            albero = sh(["git", "write-tree"], repo, env=env).strip()
            commit = sh(["git", "commit-tree", albero, "-p", "HEAD", "-m",
                         "backup automatico di redazione.py prima del riallineamento (%d file)" % len(sporchi)],
                        repo, env=env).strip()
        finally:
            try:
                os.remove(env["GIT_INDEX_FILE"])
            except OSError:
                pass
        sh(["git", "update-ref", "refs/backup/redazione/%s" % stamp, commit], repo)
        salvati.append("%d file tracciati modificati -> refs/backup/redazione/%s" % (len(sporchi), stamp))
    soglia = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=BACKUP_GIORNI)).strftime("%Y%m%d")
    for ref in sh(["git", "for-each-ref", "--format=%(refname)", "refs/backup/redazione/"], repo).split():
        if ref.rsplit("/", 1)[-1][:8] < soglia:
            sh(["git", "update-ref", "-d", ref], repo, check=False)
    return salvati


def sposta_avanzi(repo, tranne_slug=None):
    """I file NON tracciati sotto data/articles/ e articoli/ sono avanzi di un giro fallito (un JSON scritto e poi
    abbandonato, pagine di un render non pubblicato). Se restano, il giro successivo li conta, si ferma con 7 e cosi'
    tutti quelli dopo: un solo abbandono bloccherebbe ogni pubblicazione. Vanno via, ma in una cartella di backup."""
    righe = sh(["git", "ls-files", "--others", "--exclude-standard", "--", "data/articles", "articoli"], repo).splitlines()
    tieni = set()
    if tranne_slug:
        tieni = {"data/articles/%s.json" % tranne_slug} | {"articoli/%s/%s.html" % (l, tranne_slug) for l in LINGUE}
    avanzi = [r for r in righe if r.strip() and r not in tieni]
    if not avanzi:
        return None, []
    dest = os.path.join(git_dir(repo), "redazione-avanzi", dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S"))
    for rel in avanzi:
        src = os.path.join(repo, rel)
        tgt = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        try:
            shutil.move(src, tgt)
        except OSError:
            pass
    return dest, avanzi


def togli_lock_stantii(repo):
    """I lock di git lasciati da un processo morto. Non e' un'ipotesi: l'8 settembre alle 20:42 il commit del recap si
    e' interrotto a meta' e ha lasciato .git/HEAD.lock; da quel momento ogni pianificata falliva al passo di commit, e
    per sei giorni non e' uscito un articolo. Un'operazione git non tiene un lock per 10 minuti: oltre, e' un residuo."""
    gd = git_dir(repo)
    tolti = []
    candidati = [os.path.join(gd, n) for n in os.listdir(gd) if n.endswith(".lock")]
    for sotto in ("refs/heads", "refs/remotes/origin"):
        d = os.path.join(gd, *sotto.split("/"))
        if os.path.isdir(d):
            candidati += [os.path.join(d, n) for n in os.listdir(d) if n.endswith(".lock")]
    for p in candidati:
        if os.path.basename(p) == "redazione.lock":
            continue
        try:
            eta = time.time() - os.path.getmtime(p)
            if eta > 600:
                os.remove(p)
                tolti.append("%s (fermo da %.0f ore)" % (os.path.relpath(p, gd), eta / 3600))
        except OSError:
            pass
    return tolti


def riallinea(repo):
    for t in togli_lock_stantii(repo):
        print("ATTENZIONE: tolto un lock di git abbandonato da un processo morto: %s" % t)
    ramo = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo).strip()
    if ramo == RAMO:
        sh(["git", "reset", "-q", "--hard", "origin/" + RAMO], repo)
    else:
        sh(["git", "checkout", "-q", "-f", "--detach", "origin/" + RAMO], repo)
    testa = sh(["git", "rev-parse", "HEAD"], repo).strip()
    if testa != origine(repo):
        raise ErroreGit("dopo il riallineamento HEAD %s non coincide con origin/%s" % (testa[:10], RAMO))
    return testa


# ----------------------------------------------------------------------------------------------- prepara
def cmd_prepara(a):
    repo = radice_repo(a.repo or os.getcwd())
    fetch(repo)
    oggi = ora_roma().date().isoformat()

    # 1. "gia' pubblicato" si decide dal GIORNO DI REDAZIONE scritto nel JSON, non dall'ora di pubblicazione: un
    #    Dopopartita delle 23 che esce alle 00:10 ha created del giorno dopo e bloccherebbe quello della sera dopo.
    for nome, art in json_articoli(repo, "origin/" + RAMO).items():
        if art.get("pianificata") != a.pianificata:
            continue
        giorno = art.get("giorno")
        if not giorno:                                    # firmati prima del campo giorno: data italiana di creazione
            t = da_iso(art.get("created"))
            giorno = ora_roma(t).date().isoformat() if t else None
        if giorno == oggi:
            print("GIA' PUBBLICATO per il %s: %s. Niente da fare." % (oggi, nome))
            return 3

    turno, nota = prendi_turno(repo, a.pianificata, a.attesa)
    if turno is None:
        print("TURNO OCCUPATO (%s): non parto. Riprova piu' tardi." % nota)
        return 4
    if nota:
        print("turno ripreso: %s" % nota)
    try:
        for riga in backup_copia(repo):
            print("backup:", riga)
        dest, avanzi = sposta_avanzi(repo)
        if avanzi:
            print("avanzi di un giro precedente spostati in %s: %s" % (dest, ", ".join(avanzi[:6])))
        testa = riallinea(repo)
    except ErroreGit as e:
        rilascia_turno(repo, a.pianificata)
        print("ERRORE GIT durante il riallineamento:", e)
        return 9

    turno.update(giorno=oggi, testa=testa)
    _scrivi_turno(file_turno(repo), turno)
    # la grafica delle pagine gia' su main: il controllo gira in un processo nuovo, con i moduli appena riallineati
    r = subprocess.run([sys.executable, "-X", "utf8", "-c",
                        "import sys; sys.path.insert(0, 'scripts'); import guard; i, p = guard.veste_disallineata('.');"
                        "print('NO_IMPRONTA' if i is None else len(p))"], cwd=repo, capture_output=True, text=True)
    esito = (r.stdout or "").strip()
    print("PRONTO: copia allineata a origin/%s %s, turno di '%s', giorno di redazione %s." % (RAMO, testa[:10], a.pianificata, oggi))
    print("Da qui in poi i file locali coincidono con origin/main.")
    if r.returncode != 0 or esito == "NO_IMPRONTA":
        print("ATTENZIONE: controllo della grafica non eseguito (%s)" % ((r.stderr or esito).strip()[-200:]))
    elif esito != "0":
        print("ATTENZIONE: %s pagine gia' su main hanno una grafica diversa dalla corrente: la pubblicazione verra' rifiutata." % esito)
    return 0


# ----------------------------------------------------------------------------------------------- pubblica
def prima_frase(testo):
    m = re.search(r"^(.+?[.!?])(\s|$)", (testo or "").strip(), re.S)
    return (m.group(1) if m else (testo or "")).strip()


def valida(art, slug, pianificata, corpo):
    """Controlli che non richiedono i moduli del sito (il tipo lo controlla _rigenera)."""
    errori, avvisi = [], []
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug or ""):
        errori.append("lo slug %r deve contenere solo lettere minuscole a-z, cifre e trattini (niente accenti, apostrofi, "
                      "punti): rinomina il file e rilancia con il nuovo --slug" % slug)
    if art.get("slug") != slug:
        errori.append("il campo slug vale %r, deve essere %r (uguale al nome del file)" % (art.get("slug"), slug))
    for campo in ("created", "updated"):
        if not da_iso(art.get(campo), serve_fuso=True):
            errori.append("campo %s mancante o senza fuso orario (es. 2026-09-14T21:05:00Z)" % campo)
    if art.get("stato") in (None, ""):
        errori.append("campo stato mancante (di solito \"done\")")
    cont = art.get("content") or {}
    for lang in LINGUE:
        c = cont.get(lang) or {}
        if not isinstance(c.get("title"), str) or not c["title"].strip():
            errori.append("content.%s.title vuoto" % lang)
        if not isinstance(c.get("lead"), str) or not c["lead"].strip():
            errori.append("content.%s.lead vuoto" % lang)
        corpo_l = c.get("body")
        if not isinstance(corpo_l, list) or not corpo_l or not all(isinstance(p, str) and p.strip() for p in corpo_l):
            errori.append("content.%s.body deve essere una lista di paragrafi di testo non vuoti" % lang)
    it = cont.get("it") or {}
    titolo = (it.get("title") or "").strip() if isinstance(it.get("title"), str) else ""
    if len(titolo) > 60:
        errori.append("titolo italiano di %d caratteri: il massimo e' 60 (diventa il <title> della pagina)" % len(titolo))
    pf = prima_frase(it.get("lead") if isinstance(it.get("lead"), str) else "")
    if len(pf) > 150:
        errori.append("la prima frase del lead italiano e' di %d caratteri: il massimo e' 150 (diventa la meta description)" % len(pf))
    if corpo:
        n = sum(len(p) for p in (it.get("body") or []) if isinstance(p, str))
        if not corpo[0] <= n <= corpo[1]:
            errori.append("corpo italiano di %d caratteri: deve stare fra %d e %d. Se non ci arrivi senza inventare, "
                          "non pubblicare: `rilascia --pianificata %s --slug %s`" % (n, corpo[0], corpo[1], pianificata, slug))
    for lang in ("en", "es"):
        t = ((cont.get(lang) or {}).get("title") or "")
        if isinstance(t, str) and len(t.strip()) > 70:
            avvisi.append("titolo %s di %d caratteri (consigliato entro 60)" % (lang, len(t.strip())))
    if art.get("pianificata") not in (None, pianificata):
        avvisi.append("il campo pianificata valeva %r: ora lo firma %r" % (art.get("pianificata"), pianificata))
    return errori, avvisi


def cmd_rigenera(a):
    """SOTTOPROCESSO: rigenera con i moduli della copia gia' riallineata e fa i controlli. Stampa una riga RISULTATO."""
    repo = radice_repo(a.repo or os.getcwd())
    sys.path.insert(0, os.path.join(repo, "scripts"))
    os.chdir(os.path.join(repo, "scripts"))
    import render_articles, articles, guard
    res = {"esito": 0}
    art = json.load(open(os.path.join(repo, "data", "articles", a.slug + ".json"), encoding="utf-8"))
    if art.get("tipo") not in render_articles.TIPI:
        res.update(esito=2, errore="tipo %r non riconosciuto dal sito (validi: %s)" % (art.get("tipo"), ", ".join(sorted(render_articles.TIPI))))
        print("RISULTATO " + json.dumps(res)); return 0
    tutti = articles.all_articles()
    res["rigenerati"] = render_articles.render_all(tutti, SITO, articles.PAGES, articles.DATA)
    impronta = impronta_origine(repo)
    _, indietro = guard.veste_disallineata(repo)
    pagina = open(os.path.join(repo, "articoli", "it", a.slug + ".html"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(repo, "articoli", "it", a.slug + ".html")) else ""
    if impronta is None:
        res.update(esito=6, errore="non trovo l'impronta della grafica in site_common.py su origin/main")
    elif indietro or impronta not in pagina:
        cartelle = sorted({p.rsplit("/", 1)[0] for p in indietro})
        res.update(esito=6, errore="%d pagine con una grafica diversa da quella di origin/main (%s)%s" % (
            len(indietro), ", ".join(cartelle[:6]), "" if impronta in pagina else "; anche la pagina dell'articolo"))
    else:
        su_origine = {p: v for p, v in json_articoli(repo, "origin/" + RAMO).items() if isinstance(v, dict) and v.get("content")}
        locali = {"data/articles/" + x.get("slug", "") + ".json" for x in tutti}
        spariti = sorted(set(su_origine) - locali)
        in_piu = sorted(locali - set(su_origine) - {"data/articles/%s.json" % a.slug})
        atteso = len(su_origine) + (0 if "data/articles/%s.json" % a.slug in su_origine else 1)
        if spariti or in_piu or len(tutti) != atteso:
            res.update(esito=7, errore="articoli: attesi %d, trovati %d; spariti %s; in piu' %s" % (atteso, len(tutti), spariti[:5], in_piu[:5]))
        elif not pagina:
            res.update(esito=7, errore="la rigenerazione non ha prodotto articoli/it/%s.html" % a.slug)
        res["atteso"], res["trovati"] = atteso, len(tutti)
    res["impronta"] = impronta
    print("RISULTATO " + json.dumps(res))
    return 0


def trova_bash():
    """Il bash di Git per Windows, non il primo 'bash' del PATH (che puo' essere quello di WSL)."""
    esecuzione = subprocess.run(["git", "--exec-path"], capture_output=True, text=True).stdout.strip()
    radice_git = os.path.normpath(os.path.join(esecuzione, "..", "..", ".."))
    for cand in (os.path.join(radice_git, "bin", "bash.exe"), os.path.join(radice_git, "usr", "bin", "bash.exe")):
        if os.path.exists(cand):
            return cand
    return shutil.which("bash")


def consentito(percorso, slug, su_origine):
    """I file che il commit di un articolo puo' toccare: i suoi, gli indici, le sitemap, e le pagine degli articoli
    gia' pubblicati (che cambiano perche' elencano gli ultimi usciti)."""
    if percorso in ("sitemap.xml", "sitemap-articoli.xml", "data/articles/index.json", "data/articles/%s.json" % slug):
        return True
    m = re.fullmatch(r"articoli/(it|en|es)/([^/]+)\.html", percorso)
    if not m:
        return False
    return m.group(2) in ("index", slug) or ("data/articles/%s.json" % m.group(2)) in su_origine


def commit_articoli(repo, slug, impronta):
    gd = git_dir(repo)
    env = env_git(repo, GIT_INDEX_FILE=os.path.join(gd, "redazione_idx"))
    genitore = origine(repo)
    try:
        sh(["git", "read-tree", genitore], repo, env=env)
        sh(["git", "add", "-A", "--"] + list(PERCORSI_ARTICOLI), repo, env=env)
        albero = sh(["git", "write-tree"], repo, env=env).strip()
    finally:
        try:
            os.remove(env["GIT_INDEX_FILE"])
        except OSError:
            pass
    commit = sh(["git", "commit-tree", albero, "-p", genitore, "-m",
                 "articolo: %s\n\nPubblicato da scripts/redazione.py.\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>" % slug],
                repo, env=env).strip()
    righe = [l.split("\t") for l in sh(["git", "diff", "--no-renames", "--name-status", genitore, commit], repo).splitlines() if l.strip()]
    su_origine = json_articoli(repo, genitore)
    cancellati = [r[-1] for r in righe if r[0].startswith("D")]
    fuori = [r[-1] for r in righe if not consentito(r[-1], slug, su_origine)]
    if cancellati or fuori:
        raise ErroreGit("commit rifiutato prima del push: cancellati %s, file non consentiti %s" % (cancellati[:5], fuori[:5]))
    if "data/articles/%s.json" % slug not in {r[-1] for r in righe}:
        return None, genitore, 0                           # l'articolo e' identico a quello gia' pubblicato
    pagina = sh(["git", "show", "%s:articoli/it/%s.html" % (commit, slug)], repo, check=False)
    if impronta not in pagina:
        raise ErroreGit("la pagina nel commit non ha la grafica di origin/main: commit rifiutato")
    return commit, genitore, len(righe)


def pagina_online(slug, impronta, aggiornato, minuti):
    """La pagina servita deve avere la grafica corrente E questa versione dell'articolo (dateModified = updated):
    una pagina vecchia gia' in cache passerebbe il solo controllo della grafica."""
    url = "%s/articoli/it/%s.html" % (SITO, slug)
    fine = time.time() + minuti * 60
    ultimo = ""
    while True:
        try:
            req = urllib.request.Request(url + "?v=%d" % int(time.time()), headers={"User-Agent": "TransferBeat redazione"})
            with urllib.request.urlopen(req, timeout=20) as r:
                testo = r.read().decode("utf-8", "replace")
                if r.status == 200 and impronta in testo and aggiornato in testo:
                    return True, url
                ultimo = "HTTP %d, grafica %s, versione %s" % (r.status, "corrente" if impronta in testo else "vecchia",
                                                              "nuova" if aggiornato in testo else "precedente")
        except Exception as e:
            ultimo = str(e)[:80]
        if time.time() >= fine:
            return False, "%s (ultimo tentativo: %s)" % (url, ultimo)
        time.sleep(20)


def leggi_corpo(testo):
    if testo is None:
        return None, None
    m = re.fullmatch(r"(\d+)-(\d+)", testo.replace(".", "").strip())
    if not m or int(m.group(1)) > int(m.group(2)):
        return None, "--corpo %r non valido: scrivilo come MIN-MAX, per esempio 2000-3500" % testo
    return (int(m.group(1)), int(m.group(2))), None


def cmd_pubblica(a):
    repo = radice_repo(a.repo or os.getcwd())
    turno = turno_mio(repo, a.pianificata)
    if not turno:
        print("TURNO NON TUO: esegui prima `prepara --pianificata %s` (turno attuale: %s)" % (
            a.pianificata, (leggi_turno(repo) or {}).get("pianificata")))
        return 5
    battito(repo)
    corpo, errore = leggi_corpo(a.corpo)
    if errore:
        print("ARGOMENTI NON VALIDI:", errore)
        return 2
    percorso = os.path.join(repo, "data", "articles", a.slug + ".json")
    try:
        art = json.load(open(percorso, encoding="utf-8"))
    except FileNotFoundError:
        print("ARTICOLO NON VALIDO: non trovo data/articles/%s.json" % a.slug)
        return 2
    except ValueError as e:
        print("ARTICOLO NON VALIDO: data/articles/%s.json non e' JSON valido: %s" % (a.slug, e))
        return 2
    errori, avvisi = valida(art, a.slug, a.pianificata, corpo)
    for w in avvisi:
        print("avviso:", w)
    if errori:
        print("ARTICOLO NON VALIDO, correggi il JSON e rilancia lo stesso comando:")
        for e in errori:
            print("  -", e)
        return 2
    art["pianificata"] = a.pianificata                     # la firma usata da `prepara` e da palinsesto.py
    art["giorno"] = turno.get("giorno") or ora_roma().date().isoformat()
    art.setdefault("smentita", False)

    for tentativo in range(1, 4):
        try:
            battito(repo)
            fetch(repo)
            # 1. se main e' avanzato, la copia si riallinea PRIMA di rigenerare: gli script da usare sono quelli di adesso
            if sh(["git", "rev-parse", "HEAD"], repo).strip() != origine(repo):
                riallinea(repo)
                print("main avanzato dal passo 0: copia riallineata a %s prima di rigenerare" % origine(repo)[:10])
            sh(["git", "checkout", "origin/" + RAMO, "--", "data/articles/", "articoli/", "sitemap-articoli.xml", "sitemap.xml"], repo)
            dest, avanzi = sposta_avanzi(repo, tranne_slug=a.slug)
            if avanzi:
                print("avanzi spostati in %s: %s" % (dest, ", ".join(avanzi[:6])))
            with open(percorso, "w", encoding="utf-8", newline="\n") as f:
                json.dump(art, f, ensure_ascii=False, indent=1)
            # 2. rigenerazione e controlli in un processo nuovo, con i moduli della copia riallineata
            r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(repo, "scripts", "redazione.py"),
                                "--repo", repo, "_rigenera", "--slug", a.slug], cwd=repo, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            riga = next((l for l in (r.stdout or "").splitlines() if l.startswith("RISULTATO ")), None)
            if r.returncode != 0 or not riga:
                raise ErroreGit("rigenerazione fallita: %s" % ((r.stderr or r.stdout or "").strip()[-600:]))
            res = json.loads(riga[len("RISULTATO "):])
            if res["esito"] == 2:
                print("ARTICOLO NON VALIDO:", res["errore"])
                return 2
            if res["esito"] in (6, 7):
                print("FERMO:", res["errore"], "- non pubblico.")
                rilascia_turno(repo, a.pianificata)
                return res["esito"]
            impronta = res["impronta"]
            if a.prova:
                print("PROVA: articolo valido, %d articoli rigenerati, grafica uniforme, articoli %d. Nessun commit; "
                      "JSON e turno restano per la pubblicazione vera." % (res["rigenerati"], res["trovati"]))
                return 0
            # 3. commit con i soli file degli articoli, verificato, poi push
            commit, genitore, n_file = commit_articoli(repo, a.slug, impronta)
            if commit is None:
                print("ARTICOLO NON VALIDO: identico a quello gia' pubblicato, niente da pubblicare. Se volevi aggiornarlo, "
                      "modifica il contenuto e l'updated.")
                return 2
            if a.remoto:
                p = subprocess.run(["git", "push", a.remoto, "%s:refs/heads/%s" % (commit, RAMO)], cwd=repo, capture_output=True)
                spinto, dettaglio = p.returncode == 0, p.stderr.decode("utf-8", "replace").strip()[-300:]
            else:
                sh(["git", "update-ref", "HEAD", commit], repo)
                sh(["git", "read-tree", commit], repo)
                p = subprocess.run([trova_bash(), "scripts/pubblica.sh", "HEAD:refs/heads/%s" % RAMO], cwd=repo, capture_output=True)
                uscita = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
                spinto, dettaglio = p.returncode == 0 and "Pubblicato" in uscita, uscita.strip()[-300:]
            if not spinto:
                print("push non riuscito (tentativo %d): %s" % (tentativo, dettaglio))
                if tentativo < 3:
                    time.sleep(20)
                    continue
                rilascia_turno(repo, a.pianificata)
                return 9
            # 4. il push lo si verifica sul remoto
            if a.remoto:
                remoto_ora = sh(["git", "ls-remote", a.remoto, "refs/heads/" + RAMO], repo).split()[0]
            else:
                fetch(repo)
                remoto_ora = origine(repo)
            if subprocess.run(["git", "merge-base", "--is-ancestor", commit, remoto_ora], cwd=repo).returncode != 0:
                print("FERMO: il push risulta riuscito ma il commit %s non e' in main (%s)" % (commit[:10], remoto_ora[:10]))
                rilascia_turno(repo, a.pianificata)
                return 9
            print("PUBBLICATO su GitHub: commit %s sopra %s, %d file (solo articoli)." % (commit[:10], genitore[:10], n_file))
            if not a.remoto:
                subprocess.run([sys.executable, "-X", "utf8", "scripts/indexnow.py", genitore, commit], cwd=repo,
                               capture_output=True)
            break
        except ErroreGit as e:
            print("errore (tentativo %d): %s" % (tentativo, e))
            if tentativo == 3:
                rilascia_turno(repo, a.pianificata)
                return 9
            time.sleep(20)

    titolo = ((art.get("content") or {}).get("it") or {}).get("title")
    print("TITOLO: %s" % titolo)
    if a.remoto:
        rilascia_turno(repo, a.pianificata)
        return 0
    online, dove = pagina_online(a.slug, impronta, art["updated"], ATTESA_ONLINE_MIN)
    rilascia_turno(repo, a.pianificata)
    if online:
        print("ONLINE: %s" % dove)
        return 0
    print("ATTENZIONE: pubblicato su GitHub ma questa versione NON risulta online dopo %d minuti: %s" % (ATTESA_ONLINE_MIN, dove))
    return 8


def cmd_rilascia(a):
    repo = radice_repo(a.repo or os.getcwd())
    if a.slug:
        su_origine = json_articoli(repo, "origin/" + RAMO) if a.slug else {}
        if "data/articles/%s.json" % a.slug not in su_origine:
            tolti = []
            for rel in ["data/articles/%s.json" % a.slug] + ["articoli/%s/%s.html" % (l, a.slug) for l in LINGUE]:
                try:
                    os.remove(os.path.join(repo, rel))
                    tolti.append(rel)
                except OSError:
                    pass
            print("bozza tolta: %s" % (", ".join(tolti) or "nessun file"))
        else:
            sh(["git", "checkout", "origin/" + RAMO, "--", "data/articles/%s.json" % a.slug], repo, check=False)
            print("articolo gia' pubblicato: riportato alla versione di main")
    ok = rilascia_turno(repo, a.pianificata)
    print("turno liberato" if ok else "nessun turno di questa pianificata da liberare")
    return 0


def cmd_stato(a):
    repo = radice_repo(a.repo or os.getcwd())
    fetch(repo)
    t, eta = leggi_turno(repo), eta_turno_min(repo)
    print("turno:", ("%s, giorno %s, ultimo segno di vita %.0f minuti fa" % (t.get("pianificata"), t.get("giorno"), eta)) if t else "libero")
    testa = sh(["git", "rev-parse", "HEAD"], repo).strip()
    dietro = sh(["git", "rev-list", "--count", "HEAD..origin/" + RAMO], repo).strip()
    print("copia locale: HEAD %s, origin/%s %s, indietro di %s commit" % (testa[:10], RAMO, origine(repo)[:10], dietro))
    avanzi = sh(["git", "ls-files", "--others", "--exclude-standard", "--", "data/articles", "articoli"], repo).split()
    print("file non tracciati negli articoli: %d%s" % (len(avanzi), (" (" + ", ".join(avanzi[:4]) + ")") if avanzi else ""))
    print("ora italiana:", ora_roma().strftime("%Y-%m-%d %H:%M"))
    return 0


class Parser(argparse.ArgumentParser):
    def error(self, message):                              # argomenti sbagliati: codice 2 come un JSON non valido
        self.print_usage(sys.stderr)
        print("ARGOMENTI NON VALIDI: %s" % message)
        sys.exit(2)


def main(argv=None):
    p = Parser(description=__doc__.split("\n")[0])
    p.add_argument("--repo", help="radice del repo (predefinita: la cartella corrente)")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    s = sub.add_parser("prepara")
    s.add_argument("--pianificata", required=True)
    s.add_argument("--attesa", type=int, default=ATTESA_TURNO_MIN)
    s = sub.add_parser("pubblica")
    s.add_argument("--pianificata", required=True)
    s.add_argument("--slug", required=True)
    s.add_argument("--corpo", help="lunghezza ammessa del corpo italiano, es. 2500-4000")
    s.add_argument("--prova", action="store_true", help="tutti i controlli, nessun commit; JSON e turno restano")
    s.add_argument("--remoto", help=argparse.SUPPRESS)          # solo per i test: push verso un repo locale
    s = sub.add_parser("_rigenera")
    s.add_argument("--slug", required=True)
    s = sub.add_parser("rilascia")
    s.add_argument("--pianificata")
    s.add_argument("--slug")
    sub.add_parser("stato")
    a = p.parse_args(argv)
    comandi = {"prepara": cmd_prepara, "pubblica": cmd_pubblica, "_rigenera": cmd_rigenera,
               "rilascia": cmd_rilascia, "stato": cmd_stato}
    try:
        return comandi[a.cmd](a)
    except Exception as e:
        # un errore imprevisto non deve lasciare il turno preso ne' passare sotto silenzio
        print("ERRORE IMPREVISTO in %s: %s" % (a.cmd, e))
        traceback.print_exc(limit=3)
        pianificata = getattr(a, "pianificata", None)
        if pianificata and a.cmd in ("prepara", "pubblica"):
            try:
                rilascia_turno(radice_repo(a.repo or os.getcwd()), pianificata)
            except Exception:
                pass
        return 9


if __name__ == "__main__":
    sys.exit(main())
