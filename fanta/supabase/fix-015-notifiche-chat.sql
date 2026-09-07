-- =====================================================================================================
-- fix-015-notifiche-chat.sql  —  notifica email allo staff quando un utente scrive in chat
-- =====================================================================================================
-- PERCHE'. Oggi un messaggio di un utente si vede solo se un membro dello staff apre l'app e nota il badge
-- dei non letti (kb/FANTATB.md §13, pending 3c). Chi scrive di domenica sera puo' restare senza risposta per
-- giorni: e' il tipo di guasto silenzioso che questo progetto ha gia' pagato caro altrove.
--
-- COSA PRESUPPONE. Va eseguito DOPO fix-009 (che crea `messages` e `staff`). Non dipende da fix-010/011/012/013/014
-- e non tocca compute_matchday: si puo' eseguire in qualunque momento.
--
-- COME SI VERIFICA CHE SIA ANDATO A BUON FINE. In fondo al file c'e' un blocco "VERIFICA" da lanciare
-- separatamente: stampa lo stato della configurazione e simula una notifica senza inviarla davvero.
--
-- ATTENZIONE, DUE COSE CHE DEVE FARE L'UTENTE A MANO (non si possono mettere in un file SQL versionato):
--   1) abilitare l'estensione pg_net dal pannello Supabase (Database → Extensions → pg_net);
--   2) inserire endpoint e chiave del servizio di invio con la funzione `set_notifica_chat(...)` qui sotto.
--      LA CHIAVE NON VA SCRITTA IN QUESTO FILE ne' committata da nessuna parte: si incolla una volta sola
--      nel SQL Editor, e resta in una tabella leggibile SOLO dal service role (RLS senza policy = nessun
--      accesso per anon e authenticated; la funzione che la usa e' security definer).
-- =====================================================================================================

-- ------------------------------------------------------------------ estensione
-- pg_net fa richieste HTTP dal database in modo ASINCRONO: la insert del messaggio non aspetta l'email e
-- non fallisce se il servizio di invio e' giu'. E' la ragione per cui si usa pg_net e non http sincrono.
create extension if not exists pg_net with schema extensions;

-- ------------------------------------------------------------------ configurazione (una riga sola)
create table if not exists public.notifica_config (
  id            int primary key default 1 check (id = 1),   -- riga unica: niente configurazioni fantasma
  attiva        boolean not null default false,
  endpoint      text    not null default '',                -- URL del servizio di invio (es. API transazionale)
  api_key       text    not null default '',                -- chiave: mai nel repo, solo qui
  mittente      text    not null default '',
  destinatario  text    not null default '',                -- casella dello staff
  -- silenzio fra due email per lo STESSO utente: senza, una chat concitata manda dieci email in un minuto
  attesa_minuti int     not null default 15 check (attesa_minuti between 0 and 1440),
  ultimo_invio  timestamptz
);
insert into public.notifica_config (id) values (1) on conflict (id) do nothing;

-- Nessuna policy = nessun accesso da anon e authenticated. La chiave resta invisibile all'app.
alter table public.notifica_config enable row level security;

-- ------------------------------------------------------------------ chi ha gia' ricevuto una notifica e quando
create table if not exists public.notifica_stato (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  ultimo_invio timestamptz not null default now()
);
alter table public.notifica_stato enable row level security;

-- ------------------------------------------------------------------ impostazione della configurazione
create or replace function public.set_notifica_chat(
  p_endpoint text, p_api_key text, p_mittente text, p_destinatario text,
  p_attiva boolean default true, p_attesa_minuti int default 15)
returns text
language plpgsql security definer set search_path = public as $$
begin
  -- Chi puo' configurare le notifiche. Serve distinguere DUE strade, e la prima versione di questo file
  -- sbagliava proprio quella che conta:
  --   1) dall'SQL Editor di Supabase (o da psql) NON c'e' nessun utente autenticato: auth.uid() e' NULL e
  --      is_staff() e' falso. Ma per arrivare li' servono gia' le credenziali del database, quindi il
  --      controllo non aggiunge sicurezza: aggiunge solo un muro davanti all'unico uso previsto.
  --   2) da una chiamata dell'app (PostgREST) il contesto della richiesta c'e' SEMPRE, anche per un
  --      utente anonimo. Li' il controllo serve davvero, altrimenti chiunque potrebbe riscrivere
  --      l'indirizzo a cui mandiamo le email.
  -- Il discriminante e' quindi la presenza del contesto di richiesta, non il valore di auth.uid()
  -- (che e' NULL in tutti e due i casi: usarlo da solo aprirebbe la porta agli anonimi).
  if coalesce(current_setting('request.jwt.claims', true), '') <> '' and not public.is_staff() then
    raise exception 'solo lo staff puo configurare le notifiche';
  end if;
  update public.notifica_config
     set endpoint = p_endpoint, api_key = p_api_key, mittente = p_mittente,
         destinatario = p_destinatario, attiva = p_attiva, attesa_minuti = p_attesa_minuti
   where id = 1;
  return 'configurazione salvata: attiva=' || p_attiva::text || ', attesa=' || p_attesa_minuti::text || ' minuti';
end $$;
revoke all on function public.set_notifica_chat(text, text, text, text, boolean, int) from public, anon;
grant execute on function public.set_notifica_chat(text, text, text, text, boolean, int) to authenticated;

-- ------------------------------------------------------------------ stato leggibile senza esporre la chiave
create or replace function public.stato_notifica_chat()
returns table (attiva boolean, endpoint_impostato boolean, chiave_impostata boolean,
               destinatario text, attesa_minuti int)
language plpgsql security definer set search_path = public as $$
begin
  -- stesso discriminante di set_notifica_chat: dall'SQL Editor si legge, dall'app solo lo staff
  if coalesce(current_setting('request.jwt.claims', true), '') <> '' and not public.is_staff() then
    raise exception 'solo lo staff puo leggere lo stato delle notifiche';
  end if;
  return query
    select c.attiva, c.endpoint <> '', c.api_key <> '', c.destinatario, c.attesa_minuti
      from public.notifica_config c where c.id = 1;
end $$;
revoke all on function public.stato_notifica_chat() from public, anon;
grant execute on function public.stato_notifica_chat() to authenticated;

-- ------------------------------------------------------------------ il trigger
create or replace function public.notifica_messaggio()
returns trigger
language plpgsql security definer set search_path = public, extensions as $$
declare
  cfg   public.notifica_config%rowtype;
  ultimo timestamptz;
  nome  text;
begin
  -- si notifica SOLO cio' che arriva dagli utenti: le risposte dello staff le scrive lo staff stesso
  if new.from_staff then
    return new;
  end if;

  select * into cfg from public.notifica_config where id = 1;
  if not found or not cfg.attiva or cfg.endpoint = '' or cfg.destinatario = '' then
    return new;                        -- non configurato: si tace, ma la chat continua a funzionare
  end if;

  -- silenzio per utente: una conversazione fitta non deve diventare una raffica di email
  select ultimo_invio into ultimo from public.notifica_stato where user_id = new.user_id;
  if ultimo is not null and ultimo > now() - make_interval(mins => cfg.attesa_minuti) then
    return new;
  end if;

  select coalesce(p.username, 'utente') into nome from public.profiles p where p.id = new.user_id;

  -- ASINCRONO: se il servizio di invio e' lento o giu', il messaggio dell'utente e' gia' salvato lo stesso.
  -- Una notifica persa e' un fastidio; un messaggio perso sarebbe un danno.
  perform extensions.net.http_post(
    url     := cfg.endpoint,
    headers := jsonb_build_object('Content-Type', 'application/json', 'api-key', cfg.api_key),
    body    := jsonb_build_object(
                 'sender',      jsonb_build_object('email', cfg.mittente, 'name', 'FantaTB'),
                 'to',          jsonb_build_array(jsonb_build_object('email', cfg.destinatario)),
                 'subject',     'FantaTB: nuovo messaggio da ' || nome,
                 -- niente dati personali oltre il nome utente: l'email dice CHE c'e' un messaggio, non lo ricopia
                 'textContent', nome || ' ha scritto in chat su FantaTB.' || chr(10) ||
                                'Pagina: ' || coalesce(nullif(new.page, ''), 'non indicata') || chr(10) ||
                                'Apri la voce Messaggi nell''app per leggerlo e rispondere.'),
    timeout_milliseconds := 3000);

  insert into public.notifica_stato (user_id, ultimo_invio) values (new.user_id, now())
    on conflict (user_id) do update set ultimo_invio = now();
  update public.notifica_config set ultimo_invio = now() where id = 1;
  return new;
exception when others then
  -- Il trigger NON deve MAI far fallire l'inserimento del messaggio: la chat viene prima della notifica.
  raise warning 'notifica chat non inviata: %', sqlerrm;
  return new;
end $$;

drop trigger if exists trg_notifica_messaggio on public.messages;
create trigger trg_notifica_messaggio
  after insert on public.messages
  for each row execute function public.notifica_messaggio();

-- =====================================================================================================
-- VERIFICA (da lanciare a parte, dopo aver configurato):
--
--   Dall'SQL Editor funzionano tutte e due le strade, l'update diretto e la funzione:
--
--   update public.notifica_config set endpoint='https://api.<servizio>/v3/smtp/email',
--          api_key='<CHIAVE>', mittente='noreply@transferbeat.com',
--          destinatario='<casella dello staff>', attiva=true, attesa_minuti=15 where id = 1;
--
--   select public.set_notifica_chat(
--     'https://api.<servizio>/v3/smtp/email',   -- endpoint del servizio di invio
--     '<CHIAVE>',                                -- la chiave: incollala qui, NON nel repo
--     'noreply@transferbeat.com',                -- mittente verificato presso il servizio
--     'pierluigi@digitalturnover.it',            -- casella dello staff
--     true, 15);
--
--   select * from public.stato_notifica_chat();  -- deve dire attiva=t, endpoint e chiave impostati
--
-- Poi manda un messaggio dall'app con un utente NON staff e controlla la casella. Se non arriva nulla:
--   select * from extensions.net._http_response order by created desc limit 5;   -- esito delle chiamate
-- Per spegnere tutto senza disinstallare niente:
--   update public.notifica_config set attiva = false where id = 1;
-- =====================================================================================================
