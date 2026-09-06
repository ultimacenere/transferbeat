/* FantaTB — app (vanilla JS + Supabase). Nessun build step. */
(function(){
'use strict';
const CFG = window.FANTATB_CONFIG || {};
const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
// Conferma a due clic al posto di confirm() (bloccato da alcuni browser): il primo clic arma il bottone per 5 s, il secondo esegue.
function sure(b, label){
  if (b.dataset.sure === '1') { b.dataset.sure = ''; return true; }
  b.dataset.sure = '1'; b.dataset.was = b.textContent; b.textContent = label || 'Sicuro?'; b.classList.add('warn');
  setTimeout(() => { if (b.dataset.sure === '1') { b.dataset.sure = ''; b.textContent = b.dataset.was; } }, 5000);
  return false;
}
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ROLES = ['P','D','C','A'];
const ROLE_NAME = {P:'Portieri', D:'Difensori', C:'Centrocampisti', A:'Attaccanti'};

let sb = null, user = null, players = [], playersById = {}, schede = {}, teamColors = {};   // schede/teamColors: /data/fanta/schede.json (URL scheda, MV, FMV, titolarità, presenze, gol, assist; colori sociali per squadra)
let L = null;            // lega corrente: {league, members, rosters, auction, bids}
let auctionTimer = null, channel = null;

function msg(text, kind){ const m = $('#msg'); m.innerHTML = text ? '<div class="msg '+(kind||'')+'">'+esc(text)+'</div>' : ''; if (text) setTimeout(()=>{ if (m.textContent === text) m.innerHTML=''; }, 6000); }
function err(e){ console.error(e); msg((e && (e.message || e.error_description)) || String(e), 'err'); }

/* ---------- viste ---------- */
function show(view){
  $$('main > section').forEach(s => s.classList.add('hidden'));
  const el = $('#view-' + view); if (el) el.classList.remove('hidden');
  $$('nav a').forEach(a => a.classList.toggle('on', a.dataset.view === view));
  if (view === 'home') { if (!$('#clForm').innerHTML) $('#clForm').innerHTML = settingsFormHtml(null, 'cl'); loadLeagues(); }
  if (view === 'listone') renderListone();
  if (view === 'voti') loadVoti();
  if (view === 'liste') { renderListe(); if (lsteTab === 'strategie') renderStrategie(); }
  if (view === 'messaggi') renderMessaggi();
  document.body.dataset.sec = view;   // colore di sezione (style.css: body[data-sec=...]); NON data-view: il gestore dei clic risale agli antenati con [data-view]
  if (['home', 'listone', 'voti', 'regole', 'messaggi'].includes(view)) history.replaceState(null, '', '#' + view);   // cosi' "indietro" dalle schede giocatore torna qui
  if (view === 'liste') history.replaceState(null, '', '#' + (lsteTab === 'strategie' ? 'strategie' : 'liste'));
}
document.addEventListener('click', e => {
  const a = e.target.closest('[data-view]'); if (a){ e.preventDefault(); if (!user && !['listone', 'voti', 'regole', 'liste'].includes(a.dataset.view)) return show('auth'); show(a.dataset.view); }
  const t = e.target.closest('[data-tab]'); if (t){ e.preventDefault(); renderTabs(t.dataset.tab); }
  const lt = e.target.closest('[data-ltab]'); if (lt){ e.preventDefault(); setLsteTab(lt.dataset.ltab); }
});

/* ---------- auth ---------- */
function renderUser(){
  const box = $('#userBox');
  if (!user){ box.innerHTML = '<a data-view="auth">Entra</a>'; return; }
  box.innerHTML = '<span>'+esc(user.user_metadata && user.user_metadata.username || user.email)+'</span><button class="small sec" id="btnLogout">Esci</button>';
  $('#btnLogout').onclick = async () => { await sb.auth.signOut(); };
}
async function initAuth(){
  const { data } = await sb.auth.getSession(); user = data.session ? data.session.user : null;
  sb.auth.onAuthStateChange((_ev, session) => {
    const prev = user ? user.id : null; user = session ? session.user : null; renderUser();
    if (prev !== (user ? user.id : null)) { loadLists().then(loadSharedLists).then(loadStrategies).then(() => initChat()).catch(() => {}); show(user ? 'home' : 'auth'); }   // solo a login/logout veri: l'evento iniziale non deve coprire la vista scelta dall'hash
  });
  renderUser(); show(user ? 'home' : 'auth');
}
$('#btnLogin').onclick = async () => {
  const { error } = await sb.auth.signInWithPassword({ email: $('#inEmail').value.trim(), password: $('#inPass').value });
  if (error) err(error);
};
$('#btnSignup').onclick = async () => {
  const username = $('#upName').value.trim(); if (!username) return msg('Scegli un nome utente', 'err');
  const { data, error } = await sb.auth.signUp({ email: $('#upEmail').value.trim(), password: $('#upPass').value, options: { data: { username } } });
  if (error) return err(error);
  if (data.session) msg('Account creato, benvenuto!', 'ok'); else msg('Account creato: controlla la mail per confermare, poi entra.', 'ok');
};

/* ---------- listone ---------- */
async function loadPlayers(){
  const [{ data, error }] = await Promise.all([
    sb.from('players').select('id,name,team,role,price,active,fvm:stats->qt->fvm').order('price', { ascending: false }).limit(2000),
    fetch('/data/fanta/schede.json', { cache: 'no-cache' }).then(r => r.ok ? r.json() : null).then(j => { schede = (j && j.players) || {}; teamColors = (j && j.teams) || {}; }).catch(() => {})
  ]);
  if (error) return err(error);
  players = data || []; playersById = {}; players.forEach(p => playersById[p.id] = p);
}
function roleTag(r){ return '<span class="role '+r+'">'+r+'</span>'; }
function shirtStyle(team){   // maglia con i colori sociali del club (schede.json -> teams), altrimenti il colore del ruolo dal CSS
  const c = teamColors[team]; if (!c) return '';
  return ' style="background:linear-gradient(135deg,'+c[0]+' 0 50%,'+c[1]+' 50% 100%);color:#fff;text-shadow:0 0 3px rgba(0,0,0,.9),0 1px 2px rgba(0,0,0,.8)"';
}
/* tabella del listone, condivisa fra la vista pubblica (#lsTable) e la scheda Listone della lega (#tab-listone, con stato libero/preso).
   Filtri: testo, ruolo, squadra, tier della lista attiva, solo con voto (+ solo liberi in lega). Colonna Tier modificabile se la lista e' mia. */
const lsState = { ls: { k: 'price', asc: false }, ll: { k: 'price', asc: false }, le: { k: 'price', asc: false } };
const TIERS = { 1: 'Top', 2: 'Obiettivo', 3: 'Alternativa', 4: 'Scommessa', 5: 'Da evitare' };
const fmt2 = v => v == null ? '—' : Number(v).toFixed(2).replace('.', ',');
const heatCls = v => v == null ? 'h0' : v >= 7 ? 'h1' : v >= 6.5 ? 'h2' : v >= 6 ? 'h3' : 'h4';   // colore di MV/FMV: verde forte, verde, neutro, rosso
const heatFmt = v => '<span class="heat '+heatCls(v)+'">'+fmt2(v)+'</span>';
function lsCell(v, f){ return '<td class="num">'+(v == null ? '—' : (f ? f(v) : v))+'</td>'; }
function tierOf(pid){ const it = curList && curList.items[pid]; return it ? it.tier : 0; }
function tierChip(t){ return t ? '<span class="tier t'+t+'" title="'+esc(TIERS[t])+'">T'+t+'</span>' : '<span class="muted">—</span>'; }
function tierSelect(pid, t, withRemove){ return '<select class="tierSel" data-pid="'+pid+'"><option value="0">'+(withRemove ? 'togli' : '—')+'</option>'+[1,2,3,4,5].map(x => '<option value="'+x+'"'+(x === t ? ' selected' : '')+'>T'+x+' '+TIERS[x]+'</option>').join('')+'</select>'; }
function lsVal(p, k){
  if (k === 'price') return p.price; if (k === 'name') return p.name; if (k === 'team') return p.team; if (k === 'role') return 'PDCA'.indexOf(p.role);
  if (k === 'stato') return p._stato || ''; if (k === 'tier') { const t = tierOf(p.id); return t ? 6 - t : 0; }
  const s = schede[p.id]; return (s && s[k] != null) ? s[k] : -1;
}
function filterBarHtml(px, withList){
  const teams = [...new Set(players.filter(p => p.active).map(p => p.team))].sort();
  return '<div class="row fbar"><input id="'+px+'Search" placeholder="Cerca giocatore o squadra">' +
    '<select id="'+px+'Role"><option value="">Tutti i ruoli</option><option value="P">Portieri</option><option value="D">Difensori</option><option value="C">Centrocampisti</option><option value="A">Attaccanti</option></select>' +
    '<select id="'+px+'Team"><option value="">Tutte le squadre</option>'+teams.map(t => '<option>'+esc(t)+'</option>').join('')+'</select>' +
    '<select id="'+px+'Tier"><option value="">Lista: tutti</option><option value="in">Solo in lista</option><option value="out">Non in lista</option>'+[1,2,3,4,5].map(t => '<option value="'+t+'">Tier '+t+' · '+TIERS[t]+'</option>').join('')+'</select>' +
    '<select id="'+px+'Voto"><option value="">Con e senza voto</option><option value="1">Solo con voto</option></select>' +
    (px === 'll' ? '<label class="small chk1"><input type="checkbox" id="llFree"> solo liberi</label>' : '') + '</div>' +
    (withList === false ? '' : '<div class="row fbar2"><span class="lab">🎯 Lista obiettivi attiva</span><select id="'+px+'List"></select><a data-view="liste">apri la lista →</a><span class="small" id="'+px+'ListInfo"></span></div>');
}
function fillListSelect(sel, rerender){
  if (!sel) return;
  const opt = (l, pre) => '<option value="'+l.id+'"'+(curList && curList.id === l.id ? ' selected' : '')+'>'+esc((pre || '') + l.name + (pre && l.author ? ' · di ' + l.author : ''))+'</option>';
  sel.innerHTML = '<option value="">— nessuna —</option>' +
    (lists.length ? '<optgroup label="Le mie liste">'+lists.map(l => opt(l)).join('')+'</optgroup>' : '') +
    (sharedLists.length ? '<optgroup label="Condivise e consigliate (sola lettura)">'+sharedLists.map(l => opt(l, l.featured ? '★ ' : '↗ ')).join('')+'</optgroup>' : '') +
    (!user ? '<option value="" disabled>entra per creare una lista tua</option>' : '');
  const info = $('#' + sel.id + 'Info');
  if (info) info.textContent = !curList ? 'scegli una lista e assegna i tier dalla colonna Tier' : (user && curList.owner_id === user.id ? 'stai compilando questa lista: cambia il tier dalla colonna Tier' : 'lista di ' + (curList.author || 'un altro utente') + ', sola lettura: dalla vista Obiettivi puoi copiarla');
  sel.onchange = async () => { await selectList(sel.value || null); rerender(); };
}
function filterPlayers(px){
  const g = id => { const e = $('#' + px + id); return e ? e.value : ''; };
  const q = (g('Search') || '').toLowerCase(), r = g('Role'), tm = g('Team'), tf = g('Tier'), vf = g('Voto');
  return players.filter(p => p.active && (!r || p.role === r) && (!tm || p.team === tm) && (!q || p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q))
    && (!vf || (schede[p.id] && schede[p.id].mv != null))
    && (!tf || (tf === 'in' ? tierOf(p.id) > 0 : tf === 'out' ? tierOf(p.id) === 0 : tierOf(p.id) === +tf)));
}
function listoneHtml(rows, sort, withStato){
  const th = (k, lab, title, num) => '<th class="srt'+(num ? ' num' : '')+(sort.k === k ? ' on' : '')+'" data-k="'+k+'"'+(title ? ' title="'+title+'"' : '')+'>'+lab+(sort.k === k ? (sort.asc ? ' ▲' : ' ▼') : '')+'</th>';
  const canTier = !!(curList && user && curList.owner_id === user.id);
  rows = rows.slice().sort((a, b) => { const x = lsVal(a, sort.k), y = lsVal(b, sort.k); const c = typeof x === 'string' ? x.localeCompare(y) : (x - y); return sort.asc ? c : -c; }).slice(0, 400);
  return '<div class="tw"><table><thead><tr>'+th('role','R')+th('name','Giocatore')+th('team','Squadra')+(withStato ? th('stato','Stato','Libero o già in una rosa di questa lega') : '')+
    (curList ? th('tier','Tier','Tier nella lista attiva: '+curList.name) : '')+
    th('price','Quot.','Quotazione FantaTB',true)+th('mv','MV','Media voto FantaTB, stagione in corso',true)+th('fmv','FMV','Fantamedia: media dei fantavoti con bonus e malus',true)+
    th('tit','Tit.','Indice di titolarità per la prossima giornata',true)+th('pres','Pres.','Presenze in Serie A',true)+th('gol','Gol','Gol in Serie A',true)+th('assist','Assist','Assist in Serie A',true)+'</tr></thead><tbody>' +
    rows.map(p => { const s = schede[p.id] || {}; const t = tierOf(p.id);
      const nm = s.url ? '<a class="pl" href="'+esc(s.url)+'" title="Apri la scheda con le statistiche (poi Torna al listone)">'+esc(p.name)+'</a>' : esc(p.name);
      const cls = ((withStato && p._stato) ? 'taken ' : '') + (t ? 'tr' + t : '');
      return '<tr data-pid="'+p.id+'"'+(cls ? ' class="'+cls.trim()+'"' : '')+'><td>'+roleTag(p.role)+'</td><td>'+nm+'</td><td>'+esc(p.team)+'</td>'+
        (withStato ? '<td class="muted">'+(p._stato ? esc(p._stato) : '<span class="free">libero</span>')+'</td>' : '')+
        (curList ? '<td class="tc">'+(canTier ? tierSelect(p.id, t, false) : tierChip(t))+'</td>' : '')+
        '<td class="num"><b>'+p.price+'</b></td>'+lsCell(s.mv, heatFmt)+lsCell(s.fmv, heatFmt)+lsCell(s.tit, v => '<span class="pct '+(v >= 70 ? 'g' : v >= 40 ? 'a' : 'r')+'">'+v+'%</span>')+
        lsCell(s.pres)+lsCell(s.gol)+lsCell(s.assist)+'</tr>'; }).join('') + '</tbody></table></div>' +
    '<p class="small">MV = media voto FantaTB, FMV = fantamedia (voto più bonus e malus), Tit. = indice di titolarità per la prossima giornata; presenze, gol e assist in Serie A. Clic sull\'intestazione per ordinare, sul nome per la scheda completa: da lì "Torna al listone" riporta qui.' +
    (curList ? ' Tier: '+[1,2,3,4,5].map(x => 'T'+x+' '+TIERS[x]).join(', ')+'.' : ' Scegli una lista obiettivi per vedere e assegnare i tier.')+'</p>';
}
/* ---------- scheda rapida del giocatore (pcard): finestra al passaggio del mouse sulle righe del listone, tocco sul telefono ---------- */
function pcardHtml(p){
  const s = schede[p.id] || {}; const col = teamColors[p.team] || ['#67727e', '#67727e']; const t = tierOf(p.id);
  const num = (v, d) => v == null ? '—' : (d == null ? v : Number(v).toFixed(d));
  const heat = v => v == null ? '<span class="heat h0">—</span>' : heatFmt(v);
  const last = (s.last || []).map(x => '<span class="heat '+heatCls(x[1])+'" title="Giornata '+x[0]+'">'+Number(x[1]).toFixed(1)+'</span>').join(' ');
  const prev = s.prev ? '<div class="pc-row"><span class="lab">'+esc(s.prev.lega || 'Stagione scorsa')+'</span> '+num(s.prev.pres)+' presenze ('+num(s.prev.tit)+' da titolare), '+num(s.prev.gol)+' gol, '+num(s.prev.assist)+' assist'+(s.prev.rating ? ', rating '+Number(s.prev.rating).toFixed(2) : '')+'</div>' : '';
  const inj = s.inj ? '<div class="pc-row pc-inj">✚ '+esc(s.inj)+(s.back ? ' · rientro '+esc(fmtDate(s.back + 'T12:00:00Z').replace(/,.*$/, '')) : '')+'</div>' : '';
  const tit = s.tit == null ? '—' : '<span class="pct '+(s.tit >= 70 ? 'g' : s.tit >= 40 ? 'a' : 'r')+'">'+s.tit+'%</span>';
  return '<div class="pc-head" style="border-left:6px solid '+esc(col[0])+'">'+(s.photo ? '<img src="'+esc(s.photo)+'" alt="" loading="lazy" onerror="this.style.display=\'none\'">' : '')+
    '<div><b>'+esc(p.name)+'</b> '+roleTag(p.role)+(t ? ' '+tierChip(t) : '')+'<div class="muted">'+esc(p.team)+(s.age ? ' · '+s.age+' anni' : '')+(s.nat ? ' · '+esc(s.nat) : '')+'</div></div><button class="pc-x" type="button" aria-label="Chiudi">×</button></div>' +
    '<div class="pc-grid"><div><span class="lab">Quot.</span><b>'+p.price+'</b></div><div><span class="lab">FVM</span><b>'+(p.fvm != null ? p.fvm : '—')+'</b></div><div><span class="lab">Titolare</span><b>'+tit+'</b></div>' +
    '<div><span class="lab">MV</span>'+heat(s.mv)+'</div><div><span class="lab">FMV</span>'+heat(s.fmv)+'</div><div><span class="lab">Pres · Gol · Assist</span><b>'+num(s.pres)+' · '+num(s.gol)+' · '+num(s.assist)+'</b></div></div>' +
    (last ? '<div class="pc-row"><span class="lab">Ultimi fantavoti</span> '+last+'</div>' : '') + prev + inj +
    '<div class="pc-foot">'+(s.url ? '<a class="pl" href="'+esc(s.url)+'">Scheda completa →</a>' : '<span class="muted">Scheda non disponibile</span>')+'<span class="muted small">Stagione '+SEASON+'-'+String(SEASON + 1).slice(2)+' · dati FantaTB</span></div>';
}
let pcTimer = null, pcPid = null;
function pcardEl(){ let el = $('#pcard'); if (!el) { el = document.createElement('div'); el.id = 'pcard'; el.className = 'pcard hidden'; document.body.appendChild(el); el.addEventListener('mouseenter', () => { clearTimeout(pcTimer); }); el.addEventListener('mouseleave', () => pcardHide(180)); el.addEventListener('click', e => { if (e.target.closest('.pc-x')) pcardHide(0); }); } return el; }
function pcardShow(pid, anchor){
  const p = playersById[pid]; if (!p) return; const el = pcardEl(); pcPid = pid; el.innerHTML = pcardHtml(p); el.classList.remove('hidden');
  const r = anchor.getBoundingClientRect(), w = Math.min(380, window.innerWidth - 16), h = el.offsetHeight || 260;
  let left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8), top = r.bottom + 6;
  if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 6);
  el.style.width = w + 'px'; el.style.left = left + 'px'; el.style.top = top + 'px';
}
function pcardHide(delay){ clearTimeout(pcTimer); pcTimer = setTimeout(() => { const el = $('#pcard'); if (el) el.classList.add('hidden'); pcPid = null; }, delay || 0); }
const pcTouch = window.matchMedia('(hover: none)').matches;
document.addEventListener('mouseover', e => {
  if (pcTouch) return; const row = e.target.closest('tr[data-pid]'); if (!row) return;
  clearTimeout(pcTimer); const pid = +row.dataset.pid; if (pid === pcPid) return;
  pcTimer = setTimeout(() => pcardShow(pid, row.querySelector('td:nth-child(2)') || row), 260);
});
document.addEventListener('mouseout', e => { if (pcTouch) return; const row = e.target.closest('tr[data-pid]'); if (row && !(e.relatedTarget && (e.relatedTarget.closest('#pcard') || e.relatedTarget.closest('tr[data-pid]') === row))) pcardHide(220); });
document.addEventListener('click', e => {
  const x = e.target.closest('a.pl'); const row = e.target.closest('tr[data-pid]');
  if (pcTouch && x && row && !e.target.closest('#pcard')) { e.preventDefault(); if (pcPid === +row.dataset.pid) pcardHide(0); else pcardShow(+row.dataset.pid, x); return; }
  if (!e.target.closest('#pcard') && !row) pcardHide(0);
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') pcardHide(0); });
function bindSort(el, key, rerender){
  $$('th.srt', el).forEach(h => { h.onclick = () => { const k = h.dataset.k, st = lsState[key]; if (st.k === k) st.asc = !st.asc; else lsState[key] = { k: k, asc: (k === 'name' || k === 'team' || k === 'role' || k === 'stato') }; rerender(); }; });
  el.onchange = e => { const s = e.target.closest('.tierSel'); if (s) setTier(+s.dataset.pid, +s.value); };
}
function ensureFilters(px, wrap, rerender, withList){
  if (!wrap || wrap.innerHTML) return;
  wrap.innerHTML = filterBarHtml(px, withList);
  $('#' + px + 'Search').oninput = rerender;
  ['Role', 'Team', 'Tier', 'Voto'].forEach(id => { $('#' + px + id).onchange = rerender; });
  if (px === 'll') $('#llFree').onchange = rerender;
}
function renderListone(){
  const el = $('#lsTable'); if (!el) return;
  ensureFilters('ls', $('#lsFilters'), renderListone);
  fillListSelect($('#lsList'), renderListone);
  el.innerHTML = players.length ? listoneHtml(filterPlayers('ls'), lsState.ls, false)
    : '<div class="msg">Listone non ancora caricato. Arriva con il primo aggiornamento dei dati.</div>';
  bindSort(el, 'ls', renderListone);
}
function renderLeagueListone(){
  const el = $('#tab-listone'); if (!el || !L) return;
  if (!$('#llFilters')) el.innerHTML = '<div id="llFilters" style="margin:10px 0"></div><div id="llTable"></div>';
  ensureFilters('ll', $('#llFilters'), renderLeagueListone);
  fillListSelect($('#llList'), renderLeagueListone);
  const owner = {}; L.rosters.forEach(r => { owner[r.player_id] = memberName(r.user_id) + ' (' + r.price + ')'; });
  let rows = filterPlayers('ll').map(p => Object.assign({}, p, { _stato: owner[p.id] || '' }));
  if ($('#llFree').checked) rows = rows.filter(p => !p._stato);
  $('#llTable').innerHTML = listoneHtml(rows, lsState.ll, true);
  bindSort($('#llTable'), 'll', renderLeagueListone);
}

/* ---------- voti ---------- */
async function loadVoti(){
  const { data: days } = await sb.from('matchdays').select('number,status').eq('season', CFG.SEASON || 2026).in('status', ['live', 'finished', 'rated']).order('number', { ascending: false });
  const sel = $('#vtDay');
  if (!days || !days.length){ sel.innerHTML = ''; $('#vtTable').innerHTML = '<div class="msg">Nessuna giornata calcolata finora.</div>'; return; }
  sel.innerHTML = days.map(d => '<option value="'+d.number+'">Giornata '+d.number+(d.status === 'live' ? ' (in corso)' : '')+'</option>').join('');
  sel.onchange = renderVoti; renderVoti();
}
async function renderVoti(){
  const md = Number($('#vtDay').value);
  const { data, error } = await sb.from('player_ratings').select('player_id,minutes,voto,bonus,fantavoto').eq('season', CFG.SEASON || 2026).eq('matchday', md).order('fantavoto', { ascending: false, nullsFirst: false }).limit(800);
  if (error) return err(error);
  const bon = b => Object.entries(b || {}).map(([k,v]) => k.replace('_',' ')+(v > 1 ? ' ×'+v : '')).join(', ');
  $('#vtTable').innerHTML = '<table><thead><tr><th>R</th><th>Giocatore</th><th>Squadra</th><th>Min</th><th>Voto</th><th>Bonus/malus</th><th>Fantavoto</th></tr></thead><tbody>' +
    data.map(r => { const p = playersById[r.player_id] || {name:'#'+r.player_id, team:'', role:'C'};
      return '<tr><td>'+roleTag(p.role)+'</td><td>'+esc(p.name)+'</td><td>'+esc(p.team)+'</td><td>'+r.minutes+'</td><td>'+(r.voto == null ? 's.v.' : Number(r.voto).toFixed(1))+'</td><td class="muted">'+esc(bon(r.bonus))+'</td><td><b>'+(r.fantavoto == null ? '–' : Number(r.fantavoto).toFixed(1))+'</b></td></tr>'; }).join('') + '</tbody></table>';
}

/* ---------- regole di lega: form condiviso (creazione e modifica) ---------- */
const BONUS_KEYS = [['gol', 'Gol', 3], ['assist', 'Assist', 1], ['rig_sbagliato', 'Rigore sbagliato', -3], ['rig_parato', 'Rigore parato', 3],
  ['gol_subito', 'Gol subito (portiere)', -1], ['autogol', 'Autogol', -2], ['amm', 'Ammonizione', -0.5], ['esp', 'Espulsione', -1], ['porta_inviolata', 'Porta inviolata (portiere)', 0]];
// modificatore difesa (fix 011): tabella a soglie come su Fantacalcio.it, con o senza portiere, bonus proprio o malus all'avversario
const MOD_DEF_TAB = [[6, 0.5], [6.25, 1], [6.5, 2], [6.75, 3], [7, 4.5], [7.25, 6], [7.5, 7.5]];
const MOD_OTHER = [['mod_portiere', 'Modificatore portiere'], ['mod_modulo', 'Modificatore modulo'], ['mod_rendimento', 'Fattore rendimento'], ['mod_fairplay', 'Fattore fairplay'], ['mod_capitano', 'Fattore capitano']];
const DEFAULT_SETTINGS = { type: 'classic', phase: 'asta', credits: 500, max_teams: 8, slots: { P: 3, D: 8, C: 8, A: 6 }, timer: 20, max_subs: 3, bench_size: 7,
  goal_base: 66, goal_step: 6, mod_difesa: true, mod_centrocampo: false, mod_attacco: false, bonus_casa: 0, bonus_trasferta: 0,
  mod_difesa_tab: MOD_DEF_TAB.map(([min, v]) => ({ min, v })), mod_difesa_portiere: true, mod_difesa_applica: 'propria',
  bonus: Object.fromEntries(BONUS_KEYS.map(k => [k[0], k[2]])) };
function modDefTab(s){ return (Array.isArray(s.mod_difesa_tab) && s.mod_difesa_tab.length) ? s.mod_difesa_tab : DEFAULT_SETTINGS.mod_difesa_tab; }
function modDefText(s){ const t = modDefTab(s); return (s.mod_difesa_portiere === false ? '4 migliori difensori' : '3 migliori difensori + portiere') + ', ' + (s.mod_difesa_applica === 'avversaria' ? 'malus all\'avversario' : 'bonus alla propria squadra') + ': ' + t.map(r => '≥' + r.min + ' +' + r.v).join(' · '); }
function settingsFormHtml(s, px){
  s = Object.assign({}, DEFAULT_SETTINGS, s || {}); const sl = Object.assign({}, DEFAULT_SETTINGS.slots, s.slots || {}); const bn = Object.assign({}, DEFAULT_SETTINGS.bonus, s.bonus || {});
  const num = (id, label, v, step) => '<div><label>'+label+'</label><input id="'+px+'_'+id+'" type="number" step="'+(step || 1)+'" value="'+v+'"></div>';
  const chk = (id, label, v) => '<div class="chk"><input type="checkbox" id="'+px+'_'+id+'" '+(v ? 'checked' : '')+'><label for="'+px+'_'+id+'" style="margin:0">'+label+'</label></div>';
  return '<fieldset><legend>Lega</legend><div class="settings-grid">' + num('credits', 'Crediti', s.credits) + num('max_teams', 'Squadre max', s.max_teams) + num('timer', 'Timer asta (s)', s.timer) + num('max_subs', 'Sostituzioni max', s.max_subs) + num('bench_size', 'Panchinari', s.bench_size) + '</div></fieldset>' +
    '<fieldset><legend>Rose</legend><div class="settings-grid">' + num('P', 'Portieri', sl.P) + num('D', 'Difensori', sl.D) + num('C', 'Centrocampisti', sl.C) + num('A', 'Attaccanti', sl.A) + '</div></fieldset>' +
    '<fieldset><legend>Gol e scontri</legend><div class="settings-grid">' + num('goal_base', 'Primo gol a', s.goal_base, 0.5) + num('goal_step', 'Un gol ogni', s.goal_step, 0.5) + num('bonus_casa', 'Fattore casa', s.bonus_casa, 0.5) + num('bonus_trasferta', 'Fattore trasferta', s.bonus_trasferta, 0.5) + '</div></fieldset>' +
    '<fieldset><legend>Modificatori</legend><div class="settings-grid">' + chk('mod_difesa', 'Modificatore difesa', s.mod_difesa) + chk('mod_centrocampo', 'Modificatore centrocampo', s.mod_centrocampo) + chk('mod_attacco', 'Modificatore attacco', s.mod_attacco) +
      MOD_OTHER.map(m => '<div class="chk muted"><input type="checkbox" disabled><label style="margin:0">'+m[1]+' <small>(non disponibile)</small></label></div>').join('') + '</div>' +
    '<div class="modtab"><b>Modificatore difesa</b>: si applica schierando almeno 4 difensori. Il calcolo avviene sul voto (senza bonus e malus) dei 3 migliori difensori più il portiere, oppure dei 4 migliori difensori se il portiere non è incluso.' +
      '<table><thead><tr><th>Media voto da</th><th>Bonus</th></tr></thead><tbody>' + modDefTab(s).map((row, i) => '<tr><td><input id="'+px+'_mdt_min'+i+'" type="number" step="0.25" value="'+row.min+'"></td><td><input id="'+px+'_mdt_v'+i+'" type="number" step="0.5" value="'+row.v+'"></td></tr>').join('') + '</tbody></table>' +
      '<div class="settings-grid">' + chk('mod_difesa_portiere', 'Includi portiere', s.mod_difesa_portiere !== false) +
      '<div><label>Applicazione bonus/malus</label><select id="'+px+'_mod_difesa_applica"><option value="propria" '+(s.mod_difesa_applica !== 'avversaria' ? 'selected' : '')+'>Propria squadra</option><option value="avversaria" '+(s.mod_difesa_applica === 'avversaria' ? 'selected' : '')+'>Squadra avversaria (malus)</option></select></div></div>' +
      '<p class="muted" style="margin:6px 0 0">Sotto la prima soglia il modificatore vale 0. Media voto inferiore a 6 non dà mai bonus.</p></div>' +
    '<p class="muted" style="margin-top:6px">Attacco: media voto degli attaccanti (almeno 2), scala fissa da +1 a +6. Centrocampo: confronto tra le medie dei centrocampisti delle due squadre, da +1 a +6 a chi ha la media più alta. Gli altri modificatori di Fantacalcio.it non sono ancora disponibili.</p></fieldset>' +
    '<fieldset><legend>Bonus e malus</legend><div class="settings-grid">' + BONUS_KEYS.map(k => num('b_' + k[0], k[1], bn[k[0]], 0.5)).join('') + '</div></fieldset>';
}
function readSettingsForm(px, base){
  const g = id => $('#' + px + '_' + id); const n = (id, d) => { const v = parseFloat(g(id).value); return isNaN(v) ? d : v; };
  const s = Object.assign({}, DEFAULT_SETTINGS, base || {});
  s.credits = n('credits', 500); s.max_teams = n('max_teams', 8); s.timer = n('timer', 20); s.max_subs = n('max_subs', 3); s.bench_size = n('bench_size', 7);
  s.slots = { P: n('P', 3), D: n('D', 8), C: n('C', 8), A: n('A', 6) };
  s.goal_base = n('goal_base', 66); s.goal_step = n('goal_step', 6); s.bonus_casa = n('bonus_casa', 0); s.bonus_trasferta = n('bonus_trasferta', 0);
  s.mod_difesa = g('mod_difesa').checked; s.mod_centrocampo = g('mod_centrocampo').checked; s.mod_attacco = g('mod_attacco').checked;
  s.mod_difesa_tab = MOD_DEF_TAB.map(([min, v], i) => ({ min: n('mdt_min' + i, min), v: n('mdt_v' + i, v) })).sort((a, b) => a.min - b.min);
  s.mod_difesa_portiere = g('mod_difesa_portiere').checked; s.mod_difesa_applica = g('mod_difesa_applica').value === 'avversaria' ? 'avversaria' : 'propria';
  s.bonus = Object.fromEntries(BONUS_KEYS.map(k => [k[0], n('b_' + k[0], k[2])]));
  return s;
}

/* ---------- home: leghe ---------- */
async function loadLeagues(){
  const { data, error } = await sb.from('league_members').select('league_id, team_name, role, credits, leagues(id,name,invite_code,settings)').eq('user_id', user.id);
  if (error) return err(error);
  const ul = $('#leagueList');
  ul.innerHTML = (data && data.length) ? data.map(m => '<li><div><b>'+esc(m.leagues.name)+'</b><div class="muted">'+esc(m.team_name)+' · '+(m.role === 'admin' ? 'admin' : 'partecipante')+' · crediti '+m.credits+'</div></div><button class="small" data-open="'+m.league_id+'">Apri</button></li>').join('')
    : '<li class="muted"><div><b>🏟️ Nessuna lega ancora.</b><div class="muted">Creane una con il modulo a destra, oppure entra con il codice invito che ti hanno mandato. Nel frattempo puoi già studiare il <a data-view="listone">listone</a> e preparare la tua <a data-view="liste">lista obiettivi</a>.</div></div></li>';
  $$('[data-open]', ul).forEach(b => b.onclick = () => openLeague(b.dataset.open));
}
$('#btnCreate').onclick = async () => {
  const name = $('#clName').value.trim(), team = $('#clTeam').value.trim();
  if (!name || !team) return msg('Servono nome lega e nome squadra', 'err');
  const settings = readSettingsForm('cl', {});
  const { data, error } = await sb.rpc('create_league', { p_name: name, p_team: team, p_settings: settings });
  if (error) return err(error);
  msg('Lega creata', 'ok'); openLeague(data);
};
$('#btnJoin').onclick = async () => {
  const code = $('#jnCode').value.trim(), team = $('#jnTeam').value.trim();
  const pick = $('#jnPickBox') && !$('#jnPickBox').classList.contains('hidden') ? $('#jnPick').value : '';
  if (!code || (!team && !pick)) return msg('Servono codice e nome squadra (o una squadra da reclamare)', 'err');
  const { data, error } = pick ? await sb.rpc('join_league_claim', { p_code: code, p_team: pick }) : await sb.rpc('join_league', { p_code: code, p_team: team });
  if (error) return err(error);
  msg(pick ? 'Sei dentro: la squadra "'+pick+'" con la sua rosa è tua' : 'Sei dentro!', 'ok'); openLeague(data);
};
$('#jnCode').oninput = () => { clearTimeout(window._jnT); window._jnT = setTimeout(checkPendingForCode, 400); };

/* ---------- lega ---------- */
const MEMBER_SEL = 'user_id, team_name, role, credits, call_order';
async function attachProfiles(members){
  if (!members || !members.length) return members;
  const { data } = await sb.from('profiles').select('id, username').in('id', members.map(m => m.user_id));
  const by = {}; (data || []).forEach(p => by[p.id] = p);
  members.forEach(m => m.profiles = by[m.user_id] || { username: '' });
  return members;
}
async function openLeague(id, tab){
  const [{ data: league, error: e1 }, { data: members, error: e2 }] = await Promise.all([
    sb.from('leagues').select('*').eq('id', id).single(),
    sb.from('league_members').select(MEMBER_SEL).eq('league_id', id).order('call_order')
  ]);
  if (e1 || e2) return err(e1 || e2);
  await attachProfiles(members);
  L = { league, members, rosters: [], auction: null, bids: [] };
  L.me = members.find(m => m.user_id === user.id); L.isAdmin = !!(L.me && L.me.role === 'admin');
  history.replaceState(null, '', '#lega/' + id + (tab ? '/' + tab : ''));
  $$('main > section').forEach(s => s.classList.add('hidden')); $('#view-league').classList.remove('hidden');
  $('#lgName').textContent = league.name;
  $('#lgSub').innerHTML = esc(L.me.team_name)+' · '+members.length+'/'+(league.settings.max_teams || 20)+' squadre · codice invito <span class="code">'+esc(league.invite_code)+'</span>';
  await refreshLeagueData();
  document.body.dataset.sec = 'league';
  renderTabs(tab); renderRules(); renderAuction(); subscribe(); loadSeasonData(); leagueKpis();
}
async function refreshLeagueData(){
  const [{ data: rosters }, { data: auction }, { data: members }, { data: bids }] = await Promise.all([
    sb.from('rosters').select('player_id, user_id, price').eq('league_id', L.league.id),
    sb.from('auctions').select('*').eq('league_id', L.league.id).single(),
    sb.from('league_members').select(MEMBER_SEL).eq('league_id', L.league.id).order('call_order'),
    sb.from('auction_bids').select('user_id, amount, player_id, created_at').eq('league_id', L.league.id).order('id', { ascending: false }).limit(10)
  ]);
  L.rosters = rosters || []; L.auction = auction; L.bids = bids || [];
  if (members) { await attachProfiles(members); L.members = members; L.me = members.find(m => m.user_id === user.id); }
  renderRosters();
}
function memberName(uid){ const m = L.members.find(x => x.user_id === uid); return m ? m.team_name : '?'; }
function slotsOf(){ return L.league.settings.slots || { P: 3, D: 8, C: 8, A: 6 }; }
function slotsLeft(uid, role){ return slotsOf()[role] - L.rosters.filter(r => r.user_id === uid && (playersById[r.player_id] || {}).role === role).length; }

/* ---------- lega: schede, partecipanti e rose, regole ---------- */
function phase(){ return (L.league.settings && L.league.settings.phase) || 'asta'; }
function renderTabs(active){
  const tabs = [];
  if (phase() === 'asta') tabs.push(['asta', 'Asta']);
  tabs.push(['listone', 'Listone'], ['schiera', 'Schiera'], ['classifica', 'Classifica'], ['calendario', 'Calendario'], ['risultati', 'Risultati'], ['regole', 'Regole'], ['membri', 'Partecipanti']);
  if (!active || !tabs.some(t => t[0] === active)) active = tabs[0][0];
  $('#lgTabs').innerHTML = tabs.map(t => '<a data-tab="'+t[0]+'" class="'+(t[0] === active ? 'on' : '')+'">'+t[1]+'</a>').join('');
  $$('#view-league [id^=tab-]').forEach(el => el.classList.toggle('hidden', el.id !== 'tab-' + active));
  if (active === 'listone') renderLeagueListone();
  if (L) history.replaceState(null, '', '#lega/' + L.league.id + '/' + active);   // ricaricando o tornando indietro si riapre la stessa scheda
}
function renderMembers(){
  const byUser = {}; L.rosters.forEach(r => (byUser[r.user_id] = byUser[r.user_id] || []).push(r));
  const slots = slotsOf();
  const table = '<table><thead><tr><th>#</th><th>Squadra</th><th>Utente</th><th></th><th>Crediti</th><th>Rosa</th></tr></thead><tbody>' +
    L.members.map(m => '<tr class="'+(m.user_id === user.id ? 'me' : '')+'"><td>'+(m.call_order || '')+'</td><td><b>'+esc(m.team_name)+'</b></td><td>'+esc(m.profiles && m.profiles.username)+'</td><td>'+(m.role === 'admin' ? '<span class="pill">admin</span>' : '')+'</td><td>'+m.credits+'</td><td>'+(byUser[m.user_id] || []).length+'</td></tr>').join('') + '</tbody></table>';
  const cards = '<h3 style="margin-top:18px">Rose</h3><div class="grid">' + L.members.map(m => {
    const rs = (byUser[m.user_id] || []).map(r => Object.assign({}, r, { p: playersById[r.player_id] || { name: '#'+r.player_id, role: 'C', team: '' } }))
      .sort((a, b) => ROLES.indexOf(a.p.role) - ROLES.indexOf(b.p.role) || b.price - a.price);
    const head = ROLES.map(r => r+' '+rs.filter(x => x.p.role === r).length+'/'+slots[r]).join(' · ');
    const rows = rs.map(r => '<tr><td>'+roleTag(r.p.role)+'</td><td>'+esc(r.p.name)+'</td><td class="muted">'+esc(r.p.team)+'</td><td><b>'+r.price+'</b></td>' +
      (L.isAdmin ? '<td><button class="small sec" data-release="'+r.player_id+'" title="Rimuovi e rimborsa">✕</button></td>' : '') + '</tr>').join('');
    return '<div class="card'+(m.user_id === user.id ? ' hi' : '')+'"><h2>'+esc(m.team_name)+' <span class="muted">crediti '+m.credits+' · '+head+'</span></h2>' +
      (rs.length ? '<table><tbody>'+rows+'</tbody></table>' : '<div class="muted">Rosa vuota</div>') + '</div>';
  }).join('') + '</div>';
  $('#tab-membri').innerHTML = table + cards + '<div id="pendingBox"></div>' + (L.isAdmin ? importHtml() : '');
  bindImport(); loadPending();
  $$('[data-release]').forEach(b => b.onclick = async () => {
    if (!sure(b, 'Svincolo?')) return;   // primo clic arma, secondo esegue (niente confirm(): il browser lo blocca)
    const { error } = await sb.rpc('release_player', { p_league: L.league.id, p_player: +b.dataset.release });
    if (error) err(error); else refreshLeagueData();
  });
}
function renderRosters(){ renderMembers(); leagueKpis(); const t = $('#tab-listone'); if (t && !t.classList.contains('hidden')) renderLeagueListone(); }
function renderRules(){
  const s = Object.assign({}, DEFAULT_SETTINGS, L.league.settings || {}), bn = Object.assign({}, DEFAULT_SETTINGS.bonus, s.bonus || {}), sl = Object.assign({}, DEFAULT_SETTINGS.slots, s.slots || {});
  const view = '<div class="card"><h2>Regole in vigore <span class="pill '+(phase() === 'asta' ? '' : 'live')+'">'+(phase() === 'asta' ? 'fase asta' : 'campionato')+'</span></h2><table><tbody>' +
    '<tr><td>Crediti</td><td>'+s.credits+'</td><td>Squadre max</td><td>'+s.max_teams+'</td></tr>' +
    '<tr><td>Rose</td><td colspan="3">'+ROLES.map(r => r+' '+sl[r]).join(' · ')+'</td></tr>' +
    '<tr><td>Sostituzioni</td><td>'+s.max_subs+'</td><td>Panchinari</td><td>'+s.bench_size+'</td></tr><tr><td>Timer asta</td><td colspan="3">'+s.timer+' s</td></tr>' +
    '<tr><td>Gol</td><td colspan="3">primo a '+s.goal_base+', poi uno ogni '+s.goal_step+' punti</td></tr>' +
    '<tr><td>Fattore casa / trasferta</td><td colspan="3">'+s.bonus_casa+' / '+s.bonus_trasferta+'</td></tr>' +
    '<tr><td>Modificatori</td><td colspan="3">'+[s.mod_difesa && ('difesa (' + modDefText(s) + ')'), s.mod_centrocampo && 'centrocampo', s.mod_attacco && 'attacco'].filter(Boolean).join(' · ') + (s.mod_difesa || s.mod_centrocampo || s.mod_attacco ? '' : 'nessuno')+'</td></tr>' +
    '<tr><td>Bonus e malus</td><td colspan="3">'+BONUS_KEYS.map(k => k[1].toLowerCase()+' '+(bn[k[0]] > 0 ? '+' : '')+bn[k[0]]).join(' · ')+'</td></tr>' +
    '</tbody></table></div>';
  if (!L.isAdmin) { $('#tab-regole').innerHTML = view; return; }
  $('#tab-regole').innerHTML = view + '<div class="card" style="margin-top:14px"><h2>Modifica regole (admin)</h2>' + settingsFormHtml(s, 'rg') +
    '<div class="row" style="margin-top:12px"><button id="rgSave">Salva regole</button><button id="rgPhase" class="sec">'+(phase() === 'asta' ? 'Chiudi l\'asta e inizia il campionato' : 'Riapri l\'asta')+'</button></div>' +
    '<p class="muted" style="margin-top:6px">Le regole di calcolo si applicano alle giornate calcolate da ora in poi: per le precedenti usa "Ricalcola" nel calendario.</p></div>';
  const save = async (extra) => {
    const ns = Object.assign(readSettingsForm('rg', L.league.settings), extra || {});
    const { error } = await sb.rpc('update_league_settings', { p_league: L.league.id, p_settings: ns });
    if (error) return err(error);
    L.league.settings = ns; msg('Regole salvate', 'ok'); renderRules(); renderTabs($('.tabs a.on') && $('.tabs a.on').dataset.tab); renderMembers();
  };
  $('#rgSave').onclick = () => save();
  $('#rgPhase').onclick = () => save({ phase: phase() === 'asta' ? 'campionato' : 'asta' });
}

/* ---------- asta live ---------- */
function renderAuction(){
  const a = L.auction, box = $('#tab-asta');
  if (!a) { box.innerHTML = '<div class="msg err">Asta non inizializzata per questa lega.</div>'; return; }
  const p = a.player_id ? (playersById[a.player_id] || { name: '#'+a.player_id, team: '', role: 'C', price: 1 }) : null;
  const live = a.status === 'live';
  let html = stratDashHtml() + '<div class="grid3"><div>';
  if (live && p) {
    const bidder = a.bidder_id ? memberName(a.bidder_id) : null;
    html += '<div class="auction"><div class="row" style="justify-content:space-between"><div><div class="pl">'+roleTag(p.role)+' '+esc(p.name)+'</div><div class="team">'+esc(p.team)+' · quotazione '+p.price+'</div></div><div class="timer" id="auTimer">--</div></div>' +
      '<div style="margin-top:14px"><div class="bid">'+a.current_bid+'</div><div class="who">'+(bidder ? 'miglior offerta di <b>'+esc(bidder)+'</b>' : 'base d\'asta, nessuna offerta')+'</div></div>';
    const mine = a.bidder_id === user.id, canBid = slotsLeft(user.id, p.role) > 0;
    if (!canBid) html += '<div class="who" style="margin-top:10px">Hai già completato il ruolo '+p.role+'.</div>';
    html += '<div class="btns">' + [1, 5, 10].map(n => '<button class="big" data-bid="'+(a.current_bid + (a.bidder_id ? n : n - 1))+'" '+(mine || !canBid ? 'disabled' : '')+'>+'+n+'</button>').join('') +
      '<span><input id="auCustom" type="number" min="1" placeholder="'+(a.current_bid + 1)+'"> <button data-bid="custom" '+(mine || !canBid ? 'disabled' : '')+'>Offri</button></span>' +
      (L.isAdmin ? '<button class="warn" id="auClose">Aggiudica / chiudi</button>' : '') + '</div></div>';
  } else {
    html += '<div class="card"><h2>Nessuna asta in corso</h2><p class="muted">' + (L.isAdmin ? 'Cerca un giocatore a destra e apri l\'asta.' : 'Aspetta che l\'admin chiami un giocatore. La pagina si aggiorna da sola.') + '</p>' +
      (a.status === 'closed' && p ? '<p style="margin-top:8px">Ultimo: <b>'+esc(p.name)+'</b> → '+(a.bidder_id ? esc(memberName(a.bidder_id))+' per '+a.current_bid : 'non assegnato')+'</p>' : '') + '</div>';
  }
  html += '<h3>Ultime offerte</h3><table><tbody>' + (L.bids.length ? L.bids.map(b => '<tr><td>'+esc((playersById[b.player_id] || {}).name || '#'+b.player_id)+'</td><td>'+esc(memberName(b.user_id))+'</td><td><b>'+b.amount+'</b></td></tr>').join('') : '<tr><td class="muted">Ancora nessuna offerta</td></tr>') + '</tbody></table>';
  html += '<h3>Crediti e slot</h3><table><tbody>' + L.members.map(m => '<tr class="'+(m.user_id === user.id ? 'me' : '')+'"><td>'+esc(m.team_name)+'</td><td><b>'+m.credits+'</b></td><td class="muted">'+ROLES.map(r => r+' '+slotsLeft(m.user_id, r)).join(' · ')+' liberi</td></tr>').join('') + '</tbody></table>';
  html += '</div><div>';
  if (L.isAdmin) {
    html += '<div class="card"><h2>Banditore</h2><div class="row"><input id="auSearch" placeholder="Cerca giocatore" '+(live ? 'disabled' : '')+'><select id="auRole" style="max-width:110px"><option value="">Tutti</option>'+ROLES.map(r => '<option value="'+r+'">'+r+'</option>').join('')+'</select></div>' +
      '<div class="search" id="auList" style="margin-top:8px"></div><label>Base d\'asta</label><div class="row"><input id="auStart" type="number" value="1" min="1"><button id="auOpen" '+(live ? 'disabled' : '')+'>Apri asta</button></div><div class="muted" id="auPick" style="margin-top:6px">Nessun giocatore selezionato</div></div>';
  }
  html += '</div></div>';
  box.innerHTML = html; lastSig = auctionSig();
  $$('[data-bid]', box).forEach(b => b.onclick = () => bid(b.dataset.bid === 'custom' ? +$('#auCustom').value : +b.dataset.bid));
  const c = $('#auClose'); if (c) c.onclick = closeAuction;
  if (L.isAdmin) setupPicker(live);
  startTimer();
}
let picked = null, picker = { q: '', role: '' }, lastSig = '';
function auctionSig(){ return JSON.stringify([L.auction, L.rosters.length, L.members.map(m => m.credits), L.bids.length && L.bids[0].amount]); }
function setupPicker(live){
  const list = $('#auList'), inp = $('#auSearch'), sel = $('#auRole');
  inp.value = picker.q; sel.value = picker.role;
  if (picked) $('#auPick').innerHTML = 'Selezionato: <b>'+esc(picked.name)+'</b> ('+esc(picked.team)+')';
  const taken = new Set(L.rosters.map(r => r.player_id));
  const draw = () => {
    picker.q = inp.value || ''; picker.role = sel.value;
    const q = picker.q.toLowerCase(), r = picker.role;
    const rows = players.filter(p => p.active && !taken.has(p.id) && (!r || p.role === r) && (!q || p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q))).slice(0, 60);
    list.innerHTML = rows.map(p => '<div data-pick="'+p.id+'">'+roleTag(p.role)+' '+esc(p.name)+' <span class="muted">'+esc(p.team)+'</span><span class="price">'+p.price+'</span></div>').join('') || '<div class="muted">Nessun risultato</div>';
    $$('[data-pick]', list).forEach(d => d.onclick = () => { picked = playersById[+d.dataset.pick]; $('#auPick').innerHTML = 'Selezionato: <b>'+esc(picked.name)+'</b> ('+picked.team+')'; $('#auStart').value = Math.max(1, picked.price); });
  };
  inp.oninput = draw; sel.onchange = draw; draw();
  $('#auOpen').onclick = async () => {
    if (live) return; if (!picked) return msg('Seleziona un giocatore', 'err');
    const { error } = await sb.rpc('start_auction', { p_league: L.league.id, p_player: picked.id, p_start: +$('#auStart').value || 1 });
    if (error) return err(error); picked = null; await refreshLeagueData(); renderAuction();
  };
}
async function bid(amount){
  if (!amount || amount < 1) return msg('Inserisci un importo', 'err');
  const { error } = await sb.rpc('place_bid', { p_league: L.league.id, p_amount: amount });
  if (error) return err(error);
  await refreshLeagueData(); renderAuction();
}
async function closeAuction(){
  const { data, error } = await sb.rpc('close_auction', { p_league: L.league.id });
  if (error) return err(error);
  msg(data && data.assigned ? 'Aggiudicato a '+memberName(data.user_id)+' per '+data.price : 'Chiusa senza offerte', 'ok');
  await refreshLeagueData(); renderAuction();
}
function startTimer(){
  clearInterval(auctionTimer);
  const el = $('#auTimer'); if (!el || !L.auction || L.auction.status !== 'live') return;
  let closing = false;
  auctionTimer = setInterval(() => {
    const left = Math.max(0, Math.round((new Date(L.auction.ends_at) - Date.now()) / 1000));
    el.textContent = left + ' s'; el.classList.toggle('hot', left <= 5);
    if (left === 0 && L.isAdmin && !closing) { closing = true; clearInterval(auctionTimer); closeAuction(); }
  }, 250);
}
function subscribe(){
  if (channel) sb.removeChannel(channel);
  const f = 'league_id=eq.' + L.league.id, onChange = async () => { await refreshLeagueData(); if (auctionSig() !== lastSig) renderAuction(); };
  channel = sb.channel('lega-' + L.league.id)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'auctions', filter: f }, onChange)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'rosters', filter: f }, onChange)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'league_members', filter: f }, onChange)
    .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'auction_bids', filter: f }, onChange)
    .subscribe();
  clearInterval(window.__fantaPoll); window.__fantaPoll = setInterval(() => { if (L && !document.hidden) onChange(); }, 7000); // rete di sicurezza se il realtime salta
}

/* ---------- schiera: campo visivo ---------- */
const SEASON = CFG.SEASON || 2026;
const MODULES = ['3-4-3', '3-5-2', '4-3-3', '4-4-2', '4-5-1', '5-3-2', '5-4-1'];
let matchdays = [], S = { fixtures: [], results: [], lineup: null, md: null, rmd: null };
async function loadMatchdays(){ const { data } = await sb.from('matchdays').select('number,starts_at,ends_at,status').eq('season', SEASON).order('number'); matchdays = data || []; }
function mdInfo(n){ return matchdays.find(m => m.number === n) || { number: n }; }
function mdOpen(n){ const m = mdInfo(n); return !m.starts_at || new Date(m.starts_at) > new Date(); }
function nextMatchday(){ for (let n = 1; n <= 38; n++) if (mdOpen(n)) return n; return 38; }
function fmtDate(d){ return d ? new Date(d).toLocaleString('it-IT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'da definire'; }
async function loadSeasonData(){
  const [{ data: fixtures }, { data: results }] = await Promise.all([
    sb.from('league_fixtures').select('*').eq('league_id', L.league.id).order('round'),
    sb.from('results').select('user_id, matchday, total, goals, points, detail').eq('league_id', L.league.id)
  ]);
  S.fixtures = fixtures || []; S.results = results || [];
  if (!S.md) S.md = nextMatchday();
  renderLineup(); renderCalendar(); renderStandings(); renderResults();
}
function myPlayers(){ return L.rosters.filter(r => r.user_id === user.id).map(r => playersById[r.player_id]).filter(Boolean); }
function wantOf(module){ const p = module.split('-').map(Number); return { P: 1, D: p[0], C: p[1], A: p[2] }; }
function benchNormalize(cur, mine, bmax){
  const st = new Set(cur.starters), ids = new Set(mine.map(p => p.id));
  cur.starters = cur.starters.filter(id => ids.has(id));
  cur.bench = cur.bench.filter(id => ids.has(id) && !st.has(id)).slice(0, bmax || 7);
}
function moveBench(cur, id, dir){ const i = cur.bench.indexOf(id), j = i + dir; if (i < 0 || j < 0 || j >= cur.bench.length) return; [cur.bench[i], cur.bench[j]] = [cur.bench[j], cur.bench[i]]; }
function statusTag(x){
  if (!x) return '';
  const c = x.prob >= 70 ? 'ok' : (x.prob >= 40 ? 'mid' : 'low');
  const inj = x.injury ? '<span class="inj" title="'+esc(x.reason || x.injury)+'">✚ '+esc(x.injury.replace('infortunio: ', ''))+(x.back_at ? ' · rientro ~'+Math.max(1, Math.ceil((new Date(x.back_at) - Date.now()) / 6048e5))+' sett.' : '')+'</span> ' : '';
  return inj + '<span class="prob '+c+'" title="'+esc(x.reason || '')+'">'+x.prob+'%</span>';
}
function injCross(x){ return x && x.injury ? '<span class="inj" title="'+esc(x.reason || x.injury)+'">✚</span> ' : ''; }
function shortName(n){ const parts = (n || '').split(' '); return parts.length > 1 ? parts.slice(1).join(' ') : n; }
function pitchHtml(cur){
  const want = wantOf(cur.module);
  return '<div class="pitch">' + ['A', 'C', 'D', 'P'].map(r => {
    const ids = cur.starters.filter(id => (playersById[id] || {}).role === r);
    const slots = [];
    for (let i = 0; i < want[r]; i++) {
      const p = ids[i] ? playersById[ids[i]] : null;
      slots.push(p ? '<div class="slot '+r+'" data-out="'+p.id+'" title="Togli dal campo"><div class="shirt"'+shirtStyle(p.team)+'>'+r+'</div><span class="nm">'+esc(shortName(p.name))+'</span><span class="tm">'+esc(p.team)+'</span></div>'
                   : '<div class="slot '+r+' empty"><div class="shirt">'+r+'</div><span class="nm">&nbsp;</span></div>');
    }
    return '<div class="prow">'+slots.join('')+'</div>';
  }).join('') + '</div>';
}

async function renderLineup(force){
  const box = $('#tab-schiera'), md = S.md, mine = myPlayers(), bmax = L.league.settings.bench_size || 7;
  if (force || !S.luData || S.luData.md !== md) {
    const [{ data: lu }, { data: all }, { data: st }] = await Promise.all([
      sb.from('lineups').select('*').eq('league_id', L.league.id).eq('user_id', user.id).eq('matchday', md).maybeSingle(),
      sb.from('lineups').select('user_id, module, starters, submitted_at').eq('league_id', L.league.id).eq('matchday', md),
      sb.from('player_status').select('player_id, prob, reason, injury, back_at').eq('season', SEASON).eq('matchday', md)
    ]);
    S.luData = { md, lu, all, prob: Object.fromEntries((st || []).map(x => [x.player_id, x])) };
  }
  const { lu, all, prob } = S.luData;
  const rs = $('.roster', box), keepScroll = rs ? rs.scrollTop : 0, keepY = window.scrollY;
  if (!S.lineup || S.lineup.md !== md) S.lineup = { md, module: lu ? lu.module : '4-3-3', starters: lu ? lu.starters.slice() : [], bench: lu ? lu.bench.slice(0, bmax) : [] };
  const cur = S.lineup; benchNormalize(cur, mine, bmax);
  const want = wantOf(cur.module), info = mdInfo(md), open = mdOpen(md);
  const count = r => cur.starters.filter(id => (playersById[id] || {}).role === r).length;
  const head = '<div class="row"><div><label>Giornata</label><select id="luMd">' + Array.from({ length: 38 }, (_, i) => i + 1).map(n => '<option value="'+n+'" '+(n === md ? 'selected' : '')+'>Giornata '+n+(mdOpen(n) ? '' : ' (chiusa)')+'</option>').join('') + '</select></div>' +
    '<div><label>Modulo</label><select id="luMod">' + MODULES.map(m => '<option '+(m === cur.module ? 'selected' : '')+'>'+m+'</option>').join('') + '</select></div>' +
    '<div><label>&nbsp;</label><span class="row"><button id="luSave" '+(open ? '' : 'disabled')+'>Salva formazione</button><button id="luClear" class="sec">Svuota</button></span></div></div>' +
    '<p class="muted" style="margin:8px 0">Deadline: '+fmtDate(info.starts_at)+' · '+(open ? 'formazioni aperte' : 'giornata iniziata, formazioni chiuse')+(lu ? ' · salvata il '+fmtDate(lu.submitted_at) : ' · nessuna formazione salvata')+' · in campo '+cur.starters.length+'/11 · panchina '+cur.bench.length+'/'+bmax+'</p>';
  const benchStrip = '<div class="bench"><div class="bt">Panchina <span class="muted">(ordine di ingresso)</span></div><div class="brow">' + Array.from({ length: bmax }, (_, i) => { const p = cur.bench[i] ? playersById[cur.bench[i]] : null;
    return p ? '<div class="slot '+p.role+'" data-bout="'+p.id+'" title="Togli dalla panchina"><div class="shirt"'+shirtStyle(p.team)+'>'+(i + 1)+'</div><span class="nm">'+esc(shortName(p.name))+'</span><span class="tm">'+p.role+' · '+esc(p.team)+'</span><span class="mv"><button class="small sec" data-bl="'+p.id+'">◀</button><button class="small sec" data-br="'+p.id+'">▶</button></span></div>'
             : '<div class="slot empty"><div class="shirt">'+(i + 1)+'</div><span class="nm">&nbsp;</span></div>'; }).join('') + '</div></div>';
  const roster = '<div class="card"><h2>La tua rosa <span class="muted">clicca: prima in campo, poi in panchina · % = probabilità di giocare titolare</span></h2><div class="roster">' + ROLES.map(r => {
    const list = mine.filter(p => p.role === r).sort((a, b) => b.price - a.price);
    return '<h3>'+ROLE_NAME[r]+' <span class="pill">'+count(r)+'/'+want[r]+'</span></h3>' + list.map(p => {
      const on = cur.starters.includes(p.id), bi = cur.bench.indexOf(p.id);
      return '<div class="pl'+(on || bi >= 0 ? ' on' : '')+'" data-in="'+p.id+'">'+roleTag(r)+'<span class="who">'+esc(p.name)+' '+statusTag(prob[p.id])+' <span class="muted">'+esc(p.team)+'</span></span><span class="muted">'+(on ? 'in campo' : (bi >= 0 ? 'panchina '+(bi + 1) : ''))+'</span></div>'; }).join('');
  }).join('') + '</div></div>';
  const others = '<div class="card" style="margin-top:14px"><h2>Formazioni giornata '+md+'</h2><ul class="list">' + L.members.map(m => { const l2 = (all || []).find(x => x.user_id === m.user_id);
    return '<li><span>'+esc(m.team_name)+'</span><span class="muted">'+(l2 ? 'inviata ('+l2.module+')' : 'non inviata')+'</span></li>'; }).join('') + '</ul><p class="muted">Il dettaglio è nella scheda Risultati.</p></div>';
  box.innerHTML = head + '<div class="grid3"><div>' + pitchHtml(cur) + benchStrip + '<p class="muted" style="margin-top:8px">In caso di senza voto entra il primo panchinaro dello stesso ruolo, fino a '+(L.league.settings.max_subs || 3)+' cambi. Clicca un giocatore in campo o in panchina per toglierlo.</p></div><div>' + roster + '</div></div>' + others;
  const rs2 = $('.roster', box); if (rs2) rs2.scrollTop = keepScroll; window.scrollTo(0, keepY);
  const redraw = () => renderLineup();
  $('#luMd').onchange = e => { S.md = +e.target.value; S.lineup = null; renderLineup(true); };
  $('#luMod').onchange = e => { cur.module = e.target.value; const w = wantOf(cur.module), cnt = { P: 0, D: 0, C: 0, A: 0 };
    cur.starters = cur.starters.filter(id => { const r = (playersById[id] || {}).role; cnt[r]++; return cnt[r] <= w[r]; }); redraw(); };
  $('#luClear').onclick = () => { cur.starters = []; cur.bench = []; redraw(); };
  $$('[data-in]', box).forEach(el => el.onclick = () => {
    const p = playersById[+el.dataset.in]; if (!p || cur.starters.includes(p.id) || cur.bench.includes(p.id)) return;
    if (count(p.role) < want[p.role]) { cur.starters.push(p.id); return redraw(); }
    if (cur.bench.length < bmax) { cur.bench.push(p.id); return redraw(); }
    msg('Campo pieno per il ruolo '+p.role+' e panchina completa ('+bmax+')', 'err');
  });
  $$('[data-out]', box).forEach(el => el.onclick = () => { cur.starters = cur.starters.filter(x => x !== +el.dataset.out); redraw(); });
  $$('[data-bout]', box).forEach(el => el.onclick = e => { if (e.target.closest('button')) return; cur.bench = cur.bench.filter(x => x !== +el.dataset.bout); redraw(); });
  $$('[data-bl]', box).forEach(b => b.onclick = e => { e.stopPropagation(); moveBench(cur, +b.dataset.bl, -1); redraw(); });
  $$('[data-br]', box).forEach(b => b.onclick = e => { e.stopPropagation(); moveBench(cur, +b.dataset.br, 1); redraw(); });
  $('#luSave').onclick = async () => {
    if (cur.starters.length !== 11) return msg('Servono 11 titolari, ne hai '+cur.starters.length, 'err');
    const { error } = await sb.rpc('save_lineup', { p_league: L.league.id, p_matchday: md, p_module: cur.module, p_starters: cur.starters, p_bench: cur.bench });
    if (error) return err(error);
    msg('Formazione salvata per la giornata '+md, 'ok'); renderLineup(true);
  };
}

/* ---------- calendario ---------- */
function renderCalendar(){
  const box = $('#tab-calendario'); let html = '';
  if (L.isAdmin) html += '<div class="card" style="margin-bottom:14px"><h2>Genera calendario</h2><div class="row"><div><label>Prima giornata di Serie A</label><input id="calStart" type="number" value="'+nextMatchday()+'" min="1" max="38"></div><div><label>Gironi (2 = andata e ritorno)</label><input id="calG" type="number" value="2" min="1" max="6"></div><div><label>&nbsp;</label><button id="calGen">Genera</button></div></div><p class="muted">Girone all\'italiana tra le squadre iscritte. Rigenerare cancella calendario e risultati. Con squadre dispari una riposa a turno.</p></div>';
  if (!S.fixtures.length) html += '<div class="msg">Calendario non ancora generato.</div>';
  const rounds = {}; S.fixtures.forEach(f => (rounds[f.round] = rounds[f.round] || []).push(f));
  html += Object.keys(rounds).sort((a, b) => a - b).map(r => {
    const fs = rounds[r], md = fs[0].matchday, done = fs.some(f => f.home_goals != null);
    return '<h3>Turno '+r+' · giornata '+md+' di Serie A '+(L.isAdmin ? '<button class="small sec" data-calc="'+md+'">'+(done ? 'Ricalcola' : 'Calcola')+'</button>' : '')+'</h3><table><tbody>' + fs.map(f => f.away_id
      ? '<tr><td style="text-align:right;width:40%">'+esc(memberName(f.home_id))+'</td><td style="text-align:center"><b>'+(f.home_goals != null ? f.home_goals+' - '+f.away_goals : 'vs')+'</b>'+(f.home_points != null ? '<div class="muted">'+Number(f.home_points).toFixed(1)+' · '+Number(f.away_points).toFixed(1)+'</div>' : '')+'</td><td style="width:40%">'+esc(memberName(f.away_id))+'</td></tr>'
      : '<tr><td style="text-align:right;width:40%">'+esc(memberName(f.home_id))+'</td><td style="text-align:center" class="muted">riposa'+(f.home_points != null ? ' · '+Number(f.home_points).toFixed(1) : '')+'</td><td></td></tr>').join('') + '</tbody></table>';
  }).join('');
  box.innerHTML = html;
  const g = $('#calGen'); if (g) g.onclick = async () => {
    if (S.fixtures.length && !sure(g, 'Sicuro? Cancella calendario e risultati')) return;
    const { data, error } = await sb.rpc('generate_calendar', { p_league: L.league.id, p_start: +$('#calStart').value, p_gironi: +$('#calG').value });
    if (error) return err(error); msg('Calendario generato: '+data+' partite', 'ok'); loadSeasonData();
  };
  $$('[data-calc]', box).forEach(b => b.onclick = async () => {
    const { data, error } = await sb.rpc('compute_matchday', { p_league: L.league.id, p_matchday: +b.dataset.calc });
    if (error) return err(error); msg('Giornata '+b.dataset.calc+' calcolata per '+data.teams+' squadre', 'ok'); loadSeasonData();
  });
}

/* ---------- classifica ---------- */
function renderStandings(){
  const t = {}; L.members.forEach(m => t[m.user_id] = { name: m.team_name, pts: 0, g: 0, v: 0, n: 0, p: 0, gf: 0, gs: 0, fp: 0 });
  S.fixtures.filter(f => f.home_goals != null && f.away_id).forEach(f => {
    const h = t[f.home_id], a = t[f.away_id]; if (!h || !a) return;
    h.g++; a.g++; h.gf += f.home_goals; h.gs += f.away_goals; a.gf += f.away_goals; a.gs += f.home_goals; h.fp += +f.home_points; a.fp += +f.away_points;
    if (f.home_goals > f.away_goals) { h.v++; a.p++; h.pts += 3; } else if (f.home_goals < f.away_goals) { a.v++; h.p++; a.pts += 3; } else { h.n++; a.n++; h.pts++; a.pts++; }
  });
  const rows = Object.values(t).sort((x, y) => y.pts - x.pts || y.fp - x.fp);
  $('#tab-classifica').innerHTML = '<table><thead><tr><th>#</th><th>Squadra</th><th>Pt</th><th>G</th><th>V</th><th>N</th><th>P</th><th>GF</th><th>GS</th><th>Fantapunti</th></tr></thead><tbody>' +
    rows.map((r, i) => '<tr><td>'+(i + 1)+'</td><td><b>'+esc(r.name)+'</b></td><td><b>'+r.pts+'</b></td><td>'+r.g+'</td><td>'+r.v+'</td><td>'+r.n+'</td><td>'+r.p+'</td><td>'+r.gf+'</td><td>'+r.gs+'</td><td>'+r.fp.toFixed(1)+'</td></tr>').join('') + '</tbody></table>' +
    (S.results.length ? '' : '<p class="muted" style="margin-top:8px">La classifica si popola quando l\'admin calcola le giornate.</p>');
}

/* ---------- risultati ---------- */
const EMOJI = { gol: '⚽', assist: '👟', amm: '🟨', esp: '🟥', gol_subito: '🥅', autogol: '🙈', rig_sbagliato: '❌', rig_parato: '🧤' };
const EMOJI_LABEL = { gol: 'gol', assist: 'assist', amm: 'ammonizione', esp: 'espulsione', gol_subito: 'gol subito', autogol: 'autogol', rig_sbagliato: 'rigore sbagliato', rig_parato: 'rigore parato' };
function emojis(b){ return Object.entries(b || {}).filter(([k, v]) => EMOJI[k] && v).map(([k, v]) => '<span title="'+EMOJI_LABEL[k]+(v > 1 ? ' ×'+v : '')+'">'+EMOJI[k].repeat(Math.min(v, 3))+'</span>').join(''); }
function f1(x){ return x == null ? '–' : Number(x).toFixed(1); }
function sheetOpts(list){
  // unione ordinata delle voci extra e lunghezza massima della panchina, per allineare le colonne di una partita
  const labels = [], seen = new Set(); let benchN = 0;
  list.filter(Boolean).forEach(r => { const d = r.detail || {}; (d.extras || []).forEach(e => { if (!seen.has(e.label)) { seen.add(e.label); labels.push(e.label); } }); benchN = Math.max(benchN, (d.bench || []).length); });
  return { labels, benchN };
}
function teamSheet(r, name, opts){
  opts = opts || sheetOpts([r]);
  const d = (r && r.detail) || {}, pl = d.players || [], bench = d.bench || [], extras = d.extras || [];
  const missing = !r || d.lineup === false;
  const nm = id => injCross((S.rstatus || {})[id]) + shortName((playersById[id] || { name: '#'+id }).name);
  const empty = '<tr><td>&nbsp;</td><td class="muted">–</td><td></td><td></td></tr>';
  // p.pending (fix 012): giornata live e partita del giocatore non ancora finita -> "6 politico" in arancione, niente sostituzione
  let rows = pl.map(p => '<tr'+(p.pending ? ' class="pol"' : '')+'><td>'+roleTag(p.role)+'</td><td>'+(p.sub ? '<span class="muted" style="text-decoration:line-through">'+esc(nm(p.player_id))+'</span> 🔁 '+esc(nm(p.sub)) : esc(nm(p.player_id)))+' <span class="em">'+emojis(p.bonus)+'</span></td><td>'+(p.pending ? '<span class="pol" title="6 politico: deve ancora giocare">6*</span>' : (p.voto == null ? 's.v.' : f1(p.voto)))+'</td><td><b>'+(p.pending ? '<span class="pol">6.0*</span>' : f1(p.fv))+'</b></td></tr>').join('');
  for (let i = pl.length; i < 11; i++) rows += empty;
  const labels = opts.labels.length ? opts.labels : (!extras.length && d.mod_difesa ? ['Modificatore difesa'] : []);
  const exRows = labels.map(lb => { const e = extras.find(x => x.label === lb) || (lb === 'Modificatore difesa' && d.mod_difesa ? { v: d.mod_difesa } : { v: 0 });
    return '<tr class="ex"><td></td><td>'+esc(lb)+'</td><td></td><td>'+(e.v > 0 ? '+' : '')+f1(e.v)+'</td></tr>'; }).join('');
  let brows = bench.map((p, i) => '<tr class="'+(p.used ? '' : 'ex')+'"><td><span class="pill">'+(i + 1)+'</span></td><td>'+roleTag(p.role)+' '+esc(nm(p.player_id))+(p.used ? ' 🔁' : '')+' <span class="em">'+emojis(p.bonus)+'</span></td><td>'+(p.voto == null ? 's.v.' : f1(p.voto))+'</td><td>'+(p.fv == null ? '–' : f1(p.fv))+'</td></tr>').join('');
  for (let i = bench.length; i < opts.benchN; i++) brows += empty;
  const base = d.base != null ? d.base : pl.reduce((a, p) => a + (+p.fv || 0), 0);
  return '<div><h3>'+esc(name)+(missing ? ' <span class="pill">formazione non inviata</span>' : '')+(d.live ? ' <span class="pill live">provvisorio</span>' : '')+'</h3><table><thead><tr><th></th><th>Giocatore</th><th>V</th><th>FV</th></tr></thead><tbody>' + rows +
    '<tr class="tot"><td></td><td>Totale parziale</td><td></td><td>'+f1(missing ? 0 : base)+'</td></tr>' + exRows +
    '<tr class="grand"><td></td><td>Totale</td><td></td><td>'+f1(r ? r.total : 0)+'</td></tr>' +
    (opts.benchN ? '<tr><td colspan="4" class="muted" style="padding-top:10px"><b>Panchina</b></td></tr>' + brows : '') + '</tbody></table></div>';
}
function lineupSheet(lu, name){
  if (!lu) return '<div><h3>'+esc(name)+'</h3><div class="muted">Formazione non ancora schierata</div></div>';
  const nm = id => { const p = playersById[id] || { name: '#'+id, role: 'C', team: '' }; return '<tr><td>'+roleTag(p.role)+'</td><td>'+injCross((S.rstatus || {})[id])+esc(shortName(p.name))+' <span class="muted">'+esc(p.team)+'</span></td></tr>'; };
  return '<div><h3>'+esc(name)+' <span class="muted">'+lu.module+' · inviata '+fmtDate(lu.submitted_at)+'</span></h3><table><tbody>' + lu.starters.map(nm).join('') +
    '<tr><td colspan="2" class="muted" style="padding-top:10px"><b>Panchina</b></td></tr>' + lu.bench.map(nm).join('') + '</tbody></table></div>';
}
async function renderResults(){
  const box = $('#tab-risultati');
  const withRes = new Set(S.results.map(r => r.matchday)), cur = nextMatchday();
  const mds = [...new Set([...withRes, ...S.fixtures.map(f => f.matchday).filter(n => n <= cur)])].sort((a, b) => b - a);
  if (!mds.length) { box.innerHTML = '<div class="msg">Nessuna giornata in calendario o calcolata finora.</div>'; return; }
  if (!S.rmd || !mds.includes(S.rmd)) S.rmd = mds[0];
  const md = S.rmd, computed = withRes.has(md), fxs = S.fixtures.filter(f => f.matchday === md);
  const res = uid => S.results.find(r => r.matchday === md && r.user_id === uid);
  const { data: stRows } = await sb.from('player_status').select('player_id, injury, reason').eq('season', SEASON).eq('matchday', md).not('injury', 'is', null);
  S.rstatus = Object.fromEntries((stRows || []).map(x => [x.player_id, x]));
  let lus = [];
  if (!computed) { const { data } = await sb.from('lineups').select('user_id, module, starters, bench, submitted_at').eq('league_id', L.league.id).eq('matchday', md); lus = data || []; }
  const lu = uid => lus.find(x => x.user_id === uid);
  const liveMds = new Set(S.results.filter(r => r.detail && r.detail.live).map(r => r.matchday));   // fix 010: risultati provvisori
  let html = '<div class="row" style="max-width:360px"><select id="rsMd">' + mds.map(n => '<option value="'+n+'" '+(n === md ? 'selected' : '')+'>Giornata '+n+(withRes.has(n) ? (liveMds.has(n) ? ' (live, provvisoria)' : '') : (mdOpen(n) ? ' (da giocare)' : ' (in corso)'))+'</option>').join('') + '</select></div>';
  if (!computed) html += '<p class="muted" style="margin:8px 0">Giornata non ancora calcolata: formazioni schierate finora. Deadline '+fmtDate(mdInfo(md).starts_at)+'.</p>';
  else if (liveMds.has(md)) html += '<p class="muted" style="margin:8px 0">Risultati provvisori: voti e bonus delle partite già finite, aggiornati ogni 30 minuti nei giorni di gara. <span class="pol">6*</span> = <b>6 politico</b>: il giocatore deve ancora giocare, il 6 non è un voto reale ma serve a simulare il risultato. Le sostituzioni dalla panchina si applicano solo a giornata completa.</p>';
  if (fxs.length) html += fxs.map(f => { const h = res(f.home_id), a = f.away_id ? res(f.away_id) : null;
    return '<div class="match"><div class="score"><div class="t r">'+esc(memberName(f.home_id))+'</div><div class="g">'+(computed ? (f.home_goals != null ? f.home_goals : '-')+' - '+(f.away_id ? (f.away_goals != null ? f.away_goals : '-') : '') : 'vs')+'</div><div class="t">'+(f.away_id ? esc(memberName(f.away_id)) : '<span class="muted">riposo</span>')+'</div>' +
      (computed ? '<div class="fp" style="text-align:right">'+f1(h && h.total)+' fantapunti</div><div></div><div class="fp">'+(a ? f1(a.total)+' fantapunti' : '')+'</div>' : '') + '</div>' +
      '<div class="sides">' + (computed ? teamSheet(h, memberName(f.home_id), sheetOpts([h, a])) + (f.away_id ? teamSheet(a, memberName(f.away_id), sheetOpts([h, a])) : '')
                                       : lineupSheet(lu(f.home_id), memberName(f.home_id)) + (f.away_id ? lineupSheet(lu(f.away_id), memberName(f.away_id)) : '')) + '</div></div>'; }).join('');
  else html += '<p class="muted">Nessuna partita in calendario per questa giornata.</p><div class="grid">' + L.members.map(m => '<div class="card">'+(computed ? teamSheet(res(m.user_id), m.team_name) : lineupSheet(lu(m.user_id), m.team_name))+'</div>').join('') + '</div>';
  box.innerHTML = html;
  $('#rsMd').onchange = e => { S.rmd = +e.target.value; renderResults(); };
}

/* ---------- avvio ---------- */
/* ---------- liste obiettivi con tier 1-5 (tabelle lists / list_items, fix-008), condivisibili per codice ---------- */
let lists = [], sharedLists = [], curList = null, sharedList = null, keyCache = null;
async function loadSharedLists(){
  if (!sb) return;
  const { data, error } = await sb.from('lists').select('id,name,description,author,share_code,featured,is_public,owner_id,updated_at').or('featured.eq.true,is_public.eq.true').order('featured', { ascending: false }).order('updated_at', { ascending: false }).limit(50);
  sharedLists = error ? [] : (data || []).filter(l => !user || l.owner_id !== user.id);
}
async function restoreActiveList(){
  const want = localStorage.getItem('fantatb_list');
  if (want && !curList && (lists.some(l => l.id === want) || sharedLists.some(l => l.id === want))) await selectList(want);
}
async function loadLists(){
  if (!user || !sb) { lists = []; curList = null; return; }
  const { data, error } = await sb.from('lists').select('*').eq('owner_id', user.id).order('created_at');
  if (error) { lists = []; if (!/relation|does not exist|schema cache/i.test(error.message || '')) err(error); return; }
  lists = data || [];
  if (curList && !lists.some(l => l.id === curList.id)) curList = null;
  const want = localStorage.getItem('fantatb_list');
  if (!curList && want && lists.some(l => l.id === want)) await selectList(want);
}
async function selectList(id){
  if (!id) { curList = null; localStorage.removeItem('fantatb_list'); return; }
  const l = lists.find(x => x.id === id) || sharedLists.find(x => x.id === id); if (!l) return;   // le condivise si usano in sola lettura
  const { data, error } = await sb.from('list_items').select('player_id,tier,note').eq('list_id', id);
  if (error) return err(error);
  curList = Object.assign({ items: {} }, l); (data || []).forEach(it => { curList.items[it.player_id] = { tier: it.tier, note: it.note || '' }; });
  localStorage.setItem('fantatb_list', id);
}
async function setTier(pid, tier){
  if (!curList) return msg('Scegli o crea prima una lista obiettivi', 'err');
  if (!user || curList.owner_id !== user.id) return msg('Puoi modificare solo le tue liste: copiala prima', 'err');
  if (!tier) { const { error } = await sb.from('list_items').delete().eq('list_id', curList.id).eq('player_id', pid); if (error) return err(error); delete curList.items[pid]; }
  else { const note = (curList.items[pid] || {}).note || ''; const { error } = await sb.from('list_items').upsert({ list_id: curList.id, player_id: pid, tier: tier, note: note }); if (error) return err(error); curList.items[pid] = { tier: tier, note: note }; }
  sb.from('lists').update({ updated_at: new Date().toISOString() }).eq('id', curList.id).then(() => {});
  const v = $('#view-liste'); if (v && !v.classList.contains('hidden')) { renderListTiers(curList, true); renderListBrowse(); }
}
const TIER_HELP = '<details class="help"><summary>ℹ️ Come funzionano le liste e i tier</summary>' +
  '<p>Una lista obiettivi è il tuo elenco personale dei giocatori da tenere d\'occhio all\'asta, ognuno con un <b>tier</b>: <span class="tier t1">T1</span> Top (i pochi per cui vale la pena spendere), <span class="tier t2">T2</span> Obiettivo (quelli che vuoi davvero), <span class="tier t3">T3</span> Alternativa (se i primi sfuggono), <span class="tier t4">T4</span> Scommessa (poco costo, potenziale alto), <span class="tier t5">T5</span> Da evitare (per ricordarti di non farti tentare).</p>' +
  '<ul><li>Il tier si assegna dalla colonna <b>Tier</b> del listone qui sotto, filtrando per ruolo, squadra o voto, oppure dal Listone principale con la lista attiva.</li>' +
  '<li>Nel riepilogo per tier vedi quotazione ufficiale, media voto (MV), fantamedia (FMV) e titolarità: puoi aggiungere una nota a ogni giocatore.</li>' +
  '<li><b>Condividi</b> rende la lista pubblica con un link: chi la apre la vede in sola lettura e può copiarla; le liste di TransferBeat sono quelle marcate ⭐.</li>' +
  '<li>La lista collegata a una <b>strategia d\'asta</b> diventa il piano di spesa: budget per ruolo, quanti giocatori per tier, tetti e prezzi attesi (scheda "Strategie d\'asta").</li></ul></details>';
async function renderListe(){
  const bar = $('#lsteBar'); if (!bar) return;
  await loadLists(); await loadSharedLists();
  const on = l => !!(curList && curList.id === l.id && !sharedList);
  bar.innerHTML = (user ? '<span class="newbox"><input id="lsteNew" placeholder="Nome della nuova lista, es. Asta 2026"><button id="lsteCreateBtn">＋ Crea</button></span>' : '<a data-view="auth" class="btn">Entra per creare la tua lista</a>') +
    lists.map(l => '<a class="chip'+(on(l) ? ' on' : '')+'" data-list="'+l.id+'" data-name="'+esc(l.name)+'" title="'+(l.is_public ? 'condivisa · codice '+esc(l.share_code) : 'privata')+'">'+(on(l) ? '✓ ' : '')+esc(l.name)+(l.is_public ? ' 🔗' : '')+'</a>').join('') +
    (user && !lists.length ? '<span class="small" style="align-self:center">Nessuna lista ancora: creane una e assegna i tier dal listone qui sotto.</span>' : '');
  $$('[data-list]', bar).forEach(b => { b.onclick = async () => { sharedList = null; await selectList(b.dataset.list); history.replaceState(null, '', '#liste'); await renderListe(); msg('Lista "'+b.dataset.name+'" attiva: assegna i tier dal listone qui sotto o dal Listone', 'ok'); }; });
  const cb = $('#lsteCreateBtn');
  if (cb) cb.onclick = async () => { const name = (($('#lsteNew') || {}).value || '').trim(); if (!name) { msg('Scrivi il nome della nuova lista nel campo accanto al pulsante', 'err'); return; }
    const { data, error } = await sb.from('lists').insert({ owner_id: user.id, name: name.trim(), author: (user.user_metadata && user.user_metadata.username) || '' }).select().single();
    if (error) return err(error); sharedList = null; await loadLists(); await selectList(data.id); renderListe(); };
  const tb = $('#lsteTb'); const feat = sharedLists.filter(l => l.featured);
  if (tb) { tb.innerHTML = feat.length ? feat.map(l => '<div class="tcard"><b>⭐ '+esc(l.name)+'</b><div class="small">'+esc(l.description || '')+'</div><div class="row" style="margin-top:6px"><button class="small sec" data-shared="'+esc(l.share_code)+'">Apri</button></div></div>').join('') : '<span class="small">Le liste obiettivi di TransferBeat compariranno qui.</span>';
    $$('[data-shared]', tb).forEach(b => { b.onclick = () => openSharedList(b.dataset.shared); }); }
  renderFeatured();
  renderListEditor();
}
function renderListEditor(){
  const ed = $('#lsteEditor'), br = $('#lsteBrowse'); if (!ed) return;
  const l = sharedList || curList;
  if (!l) {
    ed.innerHTML = TIER_HELP + '<div class="msg hint">🎯 <b>Apri o crea una lista</b> con il pulsante qui sopra. Poi scorri il <b>listone completo qui sotto</b>, filtra per ruolo, squadra o voto e assegna un tier a ogni giocatore dalla colonna Tier. ' +
      'Tier: <span class="tier t1">T1</span> Top · <span class="tier t2">T2</span> Obiettivo · <span class="tier t3">T3</span> Alternativa · <span class="tier t4">T4</span> Scommessa · <span class="tier t5">T5</span> Da evitare.</div>';
    if (br) { br.innerHTML = ''; br.dataset.list = ''; }
    return;
  }
  const own = !!(user && l.owner_id === user.id && !sharedList);
  const link = location.origin + '/fanta/#lista/' + l.share_code;
  ed.innerHTML = TIER_HELP + '<div class="card lhead"><div class="row" style="justify-content:space-between;align-items:flex-start"><div style="flex:1 1 auto"><h2 style="margin:0">🎯 '+esc(l.name)+(l.featured ? ' <span class="pill">consigliata</span>' : '')+'</h2><div class="muted">'+(l.author ? 'di '+esc(l.author)+' · ' : '')+'<span id="lsteCount">'+Object.keys(l.items).length+'</span> giocatori'+(l.description ? ' · '+esc(l.description) : '')+'</div></div>' +
    '<div class="row" style="flex:0 0 auto">' + (own ? '<button class="small sec" id="lsteShare">'+(l.is_public ? '🔗 Condivisa ✓' : '🔗 Condividi')+'</button><button class="small sec" id="lsteRename">Rinomina</button><button class="small warn" id="lsteDelete">Elimina</button>'
      : (user ? '<button class="small" id="lsteCopy">Copia nelle mie liste</button>' : '<a data-view="auth" class="btn small">Entra per copiarla</a>')) + '</div></div>' +
    (own && l.is_public ? '<p class="small">Link da condividere: <a href="'+esc(link)+'">'+esc(link)+'</a> · codice <b>'+esc(l.share_code)+'</b>. Chi lo apre vede la lista e può copiarla.</p>' : '') +
    (own ? '<div class="tiers-legend">'+[1,2,3,4,5].map(t => '<span><span class="tier t'+t+'">T'+t+'</span> '+TIERS[t]+'</span>').join('')+'</div>' +
      '<div class="row" style="margin-top:8px"><input id="lsteAdd" placeholder="Aggiunta rapida: scrivi un nome (oppure usa il listone qui sotto)"><select id="lsteAddTier" style="flex:0 0 auto">'+[1,2,3,4,5].map(t => '<option value="'+t+'">Tier '+t+' · '+TIERS[t]+'</option>').join('')+'</select></div><div id="lsteHits" class="hits"></div>' : '') +
    '<div id="lsteTiers"></div></div>';
  renderListTiers(l, own);
  if (own) {
    $('#lsteShare').onclick = async () => { const { error } = await sb.from('lists').update({ is_public: !l.is_public }).eq('id', l.id); if (error) return err(error); await loadLists(); await selectList(l.id); renderListe(); };
    $('#lsteRename').onclick = () => { const h2 = $('#lsteEditor h2'); if (!h2 || $('#lsteRenameInp')) return;
      h2.innerHTML = '<input id="lsteRenameInp" value="'+esc(l.name)+'" style="width:auto;min-width:240px"> <button class="small" id="lsteRenameOk">Salva nome</button>'; $('#lsteRenameInp').focus();
      $('#lsteRenameOk').onclick = async () => { const name = $('#lsteRenameInp').value.trim(); if (!name) return; const { error } = await sb.from('lists').update({ name: name }).eq('id', l.id); if (error) return err(error); await loadLists(); await selectList(l.id); renderListe(); };
      $('#lsteRenameInp').onkeydown = e => { if (e.key === 'Enter') $('#lsteRenameOk').click(); }; };
    $('#lsteDelete').onclick = async () => { const b = $('#lsteDelete'); if (b.dataset.sure !== '1') { b.dataset.sure = '1'; b.textContent = 'Sicuro? Elimina davvero'; return; } const { error } = await sb.from('lists').delete().eq('id', l.id); if (error) return err(error); curList = null; localStorage.removeItem('fantatb_list'); await loadLists(); renderListe(); };
    const add = $('#lsteAdd');
    add.oninput = () => {
      const q = add.value.trim().toLowerCase(); const hits = $('#lsteHits'); if (q.length < 2) { hits.innerHTML = ''; return; }
      const found = players.filter(p => p.active && !l.items[p.id] && (p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q))).slice(0, 8);
      hits.innerHTML = found.map(p => '<a data-add="'+p.id+'">'+roleTag(p.role)+' '+esc(p.name)+' <span class="muted">'+esc(p.team)+' · quot. '+p.price+'</span></a>').join('') || '<span class="muted small">Nessun giocatore trovato</span>';
      $$('[data-add]', hits).forEach(a => { a.onclick = async () => { await setTier(+a.dataset.add, +$('#lsteAddTier').value); add.value = ''; hits.innerHTML = ''; }; });
    };
    // il listone completo con i filtri: e' il modo principale per costruire la lista
    if (br) {
      if (br.dataset.list !== l.id) { br.innerHTML = '<div class="card"><h2>📋 Scegli dal listone</h2><p class="small">Filtra per ruolo, squadra, voto o tier già assegnato e imposta il tier nella colonna <b>Tier</b>: la lista sopra si aggiorna subito. Clic sul nome per la scheda del giocatore.</p><div id="leFilters"></div><div id="leTable" style="margin-top:8px"></div></div>'; br.dataset.list = l.id; }
      ensureFilters('le', $('#leFilters'), renderListBrowse, false);
      renderListBrowse();
    }
  } else {
    if (br) { br.innerHTML = ''; br.dataset.list = ''; }
  }
  if (!own && user && $('#lsteCopy')) {
    $('#lsteCopy').onclick = async () => {
      const { data, error } = await sb.rpc('copy_list', { p_code: l.share_code, p_name: null }); if (error) return err(error);
      sharedList = null; history.replaceState(null, '', '#liste'); await loadLists(); await selectList(data); msg('Lista copiata fra le tue', 'ok'); renderListe();
    };
  }
}
function renderListTiers(l, own){
  const box = $('#lsteTiers'); if (!box || !l) return;
  const byTier = {}; Object.keys(l.items).forEach(pid => { const it = l.items[pid]; (byTier[it.tier] = byTier[it.tier] || []).push(+pid); });
  const cnt = $('#lsteCount'); if (cnt) cnt.textContent = Object.keys(l.items).length;
  let h = '';
  for (let t = 1; t <= 5; t++) {
    const ps = (byTier[t] || []).map(pid => playersById[pid]).filter(Boolean).sort((a, b) => ROLES.indexOf(a.role) - ROLES.indexOf(b.role) || b.price - a.price);
    h += '<h3><span class="tier t'+t+'">T'+t+'</span> '+TIERS[t]+' <span class="muted">('+ps.length+')</span></h3>' + (ps.length ? '<div class="tw"><table><thead><tr><th>R</th><th>Giocatore</th><th>Squadra</th><th class="num">Quot.</th><th class="num">MV</th><th class="num">FMV</th><th class="num">Tit.</th><th>'+(own ? 'Nota' : '')+'</th>'+(own ? '<th></th>' : '')+'</tr></thead><tbody>' +
      ps.map(p => { const s = schede[p.id] || {}; const it = l.items[p.id];
        return '<tr class="tr'+t+'"><td>'+roleTag(p.role)+'</td><td>'+(s.url ? '<a class="pl" href="'+esc(s.url)+'">'+esc(p.name)+'</a>' : esc(p.name))+'</td><td class="muted">'+esc(p.team)+'</td><td class="num"><b>'+p.price+'</b></td><td class="num">'+heatFmt(s.mv)+'</td><td class="num">'+heatFmt(s.fmv)+'</td><td class="num">'+(s.tit != null ? '<span class="pct '+(s.tit >= 70 ? 'g' : s.tit >= 40 ? 'a' : 'r')+'">'+s.tit+'%</span>' : '—')+'</td>' +
          (own ? '<td><input class="note" data-note="'+p.id+'" value="'+esc(it.note || '')+'" placeholder="nota"></td><td>'+tierSelect(p.id, it.tier, true)+'</td>' : '<td class="muted">'+esc(it.note || '')+'</td>') + '</tr>'; }).join('') + '</tbody></table></div>' : '<div class="muted small">Nessun giocatore in questo tier.</div>');
  }
  box.innerHTML = h;
  if (own) box.onchange = async e => {
    const s = e.target.closest('.tierSel'); if (s) return setTier(+s.dataset.pid, +s.value);
    const n = e.target.closest('[data-note]'); if (n) { const pid = +n.dataset.note; const { error } = await sb.from('list_items').update({ note: n.value }).eq('list_id', l.id).eq('player_id', pid); if (error) err(error); else if (l.items[pid]) l.items[pid].note = n.value; }
  };
}
function renderListBrowse(){
  const el = $('#leTable'); if (!el || !curList) return;
  el.innerHTML = players.length ? listoneHtml(filterPlayers('le'), lsState.le, false) : '<div class="msg">Listone non ancora caricato.</div>';
  bindSort(el, 'le', renderListBrowse);
}
async function renderFeatured(){
  const box = $('#lsteFeatured'); if (!box) return;
  const rows = sharedLists.filter(l => !l.featured);
  box.innerHTML = (rows.length ? '<ul class="list">' + rows.map(l => '<li><div><b>'+esc(l.name)+'</b><div class="muted">'+(l.author ? 'di '+esc(l.author) : 'lista condivisa')+(l.description ? ' · '+esc(l.description) : '')+'</div></div><button class="small sec" data-shared="'+esc(l.share_code)+'">Apri</button></li>').join('') + '</ul>' : '<div class="muted small">Nessuna lista condivisa dagli utenti al momento. Chi condivide la sua lista compare qui.</div>') +
    '<div class="row" style="margin-top:10px"><input id="lsteCode" placeholder="Codice di una lista condivisa" style="text-transform:uppercase"><button id="lsteOpen" class="sec" style="flex:0 0 auto">Apri</button></div>';
  $$('[data-shared]', box).forEach(b => { b.onclick = () => openSharedList(b.dataset.shared); });
  $('#lsteOpen').onclick = () => openSharedList($('#lsteCode').value.trim());
}
async function openSharedList(code){
  if (!code) return;
  const { data, error } = await sb.from('lists').select('*').eq('share_code', code.toUpperCase()).maybeSingle();
  if (error || !data) return msg('Lista non trovata o non condivisa', 'err');
  const { data: items } = await sb.from('list_items').select('player_id,tier,note').eq('list_id', data.id);
  sharedList = Object.assign({ items: {} }, data); (items || []).forEach(it => { sharedList.items[it.player_id] = { tier: it.tier, note: it.note || '' }; });
  show('liste'); history.replaceState(null, '', '#lista/' + data.share_code);
}

/* ---------- import rose da Excel/CSV (admin di lega) e squadre in attesa (fix-008) ---------- */
let impRows = [];
const normTxt = s => String(s == null ? '' : s).replace(/[ðđ]/g, 'd').replace(/[ÐĐ]/g, 'D').replace(/ø/g, 'o').replace(/Ø/g, 'O').replace(/ł/g, 'l').replace(/Ł/g, 'L').replace(/ß/g, 'ss').replace(/æ/g, 'ae').replace(/þ/g, 'th').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();
const numv = v => { if (v == null || v === '') return null; const f = parseFloat(String(v).replace(',', '.').replace(/[^\d.\-]/g, '')); return isNaN(f) ? null : Math.round(f); };
const HDR = { team: ['fantasquadra', 'fanta squadra', 'squadra fantacalcio', 'fantallenatore', 'allenatore', 'proprietario', 'team', 'squadra'], player: ['giocatore', 'calciatore', 'nome', 'player', 'name'],
  price: ['prezzo', 'costo', 'crediti', 'quotazione', 'pagato', 'euro', 'price', 'valore'], role: ['ruolo', 'r', 'role'], real: ['squadra reale', 'club', 'sq', 'squadra calciatore', 'squadra del giocatore', 'squadra serie a'] };
function loadXlsx(){ return new Promise((res, rej) => { if (window.XLSX) return res(); const s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js'; s.onload = res; s.onerror = () => rej(new Error('Libreria Excel non caricata: controlla la connessione')); document.head.appendChild(s); }); }
function detectCols(row){
  const cols = {};
  (row || []).forEach((c, i) => { const n = normTxt(c); if (!n) return;
    if (n === 'squadra' && cols.team != null && cols.real == null) { cols.real = i; return; }
    for (const k in HDR) { if (cols[k] == null && HDR[k].some(h => n === normTxt(h))) { cols[k] = i; return; } } });
  return cols;
}
function parseRows(rows){
  let head = -1, cols = {};
  for (let i = 0; i < Math.min(rows.length, 20); i++) { const c = detectCols(rows[i]); if (c.player != null && c.team != null) { head = i; cols = c; break; } }
  const out = [];
  if (head >= 0) {
    for (let i = head + 1; i < rows.length; i++) { const r = rows[i] || []; if (!r[cols.player]) continue;
      out.push({ team: String(r[cols.team] || '').trim(), player: String(r[cols.player]).trim(), price: cols.price != null ? numv(r[cols.price]) : null,
        role: cols.role != null ? String(r[cols.role] || '').trim().toUpperCase() : '', real: cols.real != null ? String(r[cols.real] || '').trim() : '' }); }
  } else {   // blocchi (export "rose" di Fantacalcio.it): riga con una sola cella = fantasquadra; poi righe Ruolo, Calciatore, Squadra, Costo
    let team = '';
    for (const r of rows) {
      const cells = (r || []).map(c => String(c == null ? '' : c).trim()).filter(Boolean); if (!cells.length) continue;
      if (cells.length === 1) { if (!/^(ruolo|calciatore|giocatore|squadra|costo|prezzo|crediti)$/i.test(cells[0])) team = cells[0]; continue; }
      if (cells.every(c => /^(ruolo|calciatore|giocatore|squadra|costo|prezzo|crediti|r|nome)$/i.test(c))) continue;
      const role = cells.find(c => /^[PDCA]$/i.test(c)) || ''; const nums = cells.filter(c => /^\d+([.,]\d+)?$/.test(c));
      const texts = cells.filter(c => c !== role && !nums.includes(c)); if (!texts.length) continue;
      out.push({ team: team, player: texts[0], real: texts[1] || '', price: nums.length ? numv(nums[nums.length - 1]) : null, role: role.toUpperCase() });
    }
  }
  return out.filter(x => x.player && x.team);
}
function playerKeys(p){
  const s = schede[p.id] || {}; const slug = s.url ? s.url.replace(/^\/giocatori\//, '').replace(/\.html$/, '').replace(/-\d+$/, '').replace(/-/g, ' ') : '';
  const sur = normTxt(p.name.replace(/^[A-Za-zÀ-ɏ]\.\s*/, ''));
  return { sur: sur, toks: new Set((sur + ' ' + normTxt(slug)).split(' ').filter(t => t.length > 1)) };
}
function matchPlayer(row){
  if (!keyCache) { keyCache = {}; players.forEach(p => { if (p.active) keyCache[p.id] = playerKeys(p); }); }
  const full = normTxt(row.player), inToks = full.split(' ').filter(t => t.length > 1);
  if (!inToks.length) return { list: [], sure: false };
  const score = p => { const k = keyCache[p.id]; let s = inToks.filter(t => k.toks.has(t)).length * 2;
    if (full === k.sur || k.sur === inToks.join(' ')) s += 3;
    if (row.role && p.role === row.role) s += 2; else if (row.role && /^[PDCA]$/.test(row.role) && p.role !== row.role) s -= 3;
    if (row.real) { const rt = normTxt(row.real), pt = normTxt(p.team); if (pt === rt || pt.includes(rt) || rt.includes(pt.split(' ').pop())) s += 2; }
    return s; };
  let cands = players.filter(p => p.active && keyCache[p.id] && inToks.some(t => t.length >= 3 && keyCache[p.id].toks.has(t))).map(p => [p, score(p)]).sort((a, b) => b[1] - a[1]);
  if (!cands.length) return { list: [], sure: false };
  return { list: cands.slice(0, 6).map(c => c[0]), sure: cands.length === 1 || cands[0][1] > cands[1][1] };
}
function importHtml(){
  return '<div class="card imp" style="margin-top:18px" id="impCard"><h2>Importa le rose da Excel o CSV</h2>' +
    '<p class="small">Formati accettati: una tabella con colonne <b>Fantasquadra</b>, <b>Giocatore</b>, <b>Prezzo</b> (e se ci sono Ruolo e Squadra reale, aiutano l\'abbinamento), oppure l\'export "rose" di Fantacalcio.it a blocchi (riga con il nome della fantasquadra, poi Ruolo · Calciatore · Squadra · Costo). ' +
    'Se il nome della fantasquadra coincide con quello di un partecipante (maiuscole e spazi non contano), la rosa va a lui con i prezzi e i crediti si scalano; altrimenti la squadra resta <b>in attesa</b> e chi entra con il codice invito la sceglie come propria.</p>' +
    '<div class="row"><input type="file" id="impFile" accept=".xlsx,.xls,.csv"><label class="small chk1"><input type="checkbox" id="impReplace" checked> sostituisci le rose già presenti (rimborsando i crediti)</label></div>' +
    '<div id="impPreview"></div></div>';
}
function bindImport(){
  const f = $('#impFile'); if (!f) return;
  f.onchange = async () => { const file = f.files && f.files[0]; if (!file) return; msg('Leggo il file…', 'ok');
    try { await loadXlsx(); const buf = await file.arrayBuffer(); const wb = XLSX.read(buf, { type: 'array' }); const ws = wb.Sheets[wb.SheetNames[0]];
      const rows = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: '' });
      const parsed = parseRows(rows);
      if (!parsed.length) return msg('Nessuna riga riconosciuta: servono almeno le colonne Fantasquadra, Giocatore e Prezzo (o il formato a blocchi)', 'err');
      keyCache = null;
      impRows = parsed.map(r => { const m = matchPlayer(r); return Object.assign(r, { cands: m.list, pid: (m.list.length && m.sure) ? m.list[0].id : null, sure: m.sure }); });
      msg(''); renderImportPreview();
    } catch (e) { err(e); } };
}
function renderImportPreview(){
  const box = $('#impPreview'); if (!box) return;
  const teams = {}; impRows.forEach((r, i) => { (teams[r.team] = teams[r.team] || []).push(i); });
  const memberOf = {}; L.members.forEach(m => { memberOf[normTxt(m.team_name)] = m; });
  const optOf = (r, i) => '<select data-row="'+i+'"><option value="">— salta —</option>' + r.cands.map(p => '<option value="'+p.id+'"'+(p.id === r.pid ? ' selected' : '')+'>'+esc(p.role+' '+p.name+' · '+p.team)+'</option>').join('') + '</select><input class="fix" data-fix="'+i+'" placeholder="cerca…">';
  let h = ''; let tot = 0;
  Object.keys(teams).forEach(t => { const m = memberOf[normTxt(t)]; const idx = teams[t];
    h += '<h3>'+esc(t)+' <span class="muted">('+idx.length+' righe · '+(m ? 'partecipante: '+esc(m.team_name) : 'nessun partecipante con questo nome: resterà in attesa')+')</span></h3><div class="tw"><table><thead><tr><th>Nel file</th><th>Giocatore FantaTB</th><th class="num">Prezzo</th><th>Esito</th></tr></thead><tbody>';
    idx.forEach(i => { const r = impRows[i]; if (r.pid) tot++;
      h += '<tr><td>'+esc(r.player)+(r.role ? ' <span class="muted">'+esc(r.role)+'</span>' : '')+(r.real ? ' <span class="muted">'+esc(r.real)+'</span>' : '')+'</td><td>'+optOf(r, i)+'</td><td class="num">'+(r.price != null ? r.price : '<span class="ko">—</span>')+'</td>' +
        '<td>'+(r.pid ? (r.sure ? '<span class="ok">✓ abbinato</span>' : '<span class="amb">scelto fra più candidati</span>') : (r.cands.length ? '<span class="amb">⚠ ambiguo: scegli</span>' : '<span class="ko">✗ non trovato</span>'))+'</td></tr>'; });
    h += '</tbody></table></div>'; });
  box.innerHTML = h + '<div class="row" style="margin-top:10px"><button id="impGo" style="flex:0 0 auto">Importa '+tot+' giocatori in '+Object.keys(teams).length+' squadre</button><span class="small">Le righe senza abbinamento vengono saltate. Controlla i prezzi: quelli mancanti valgono 0.</span></div>';
  box.onchange = e => { const s = e.target.closest('select[data-row]'); if (s) { const r = impRows[+s.dataset.row]; r.pid = s.value ? +s.value : null; r.sure = true; renderImportPreview(); } };
  box.oninput = e => { const f = e.target.closest('input[data-fix]'); if (!f) return; const q = f.value.trim().toLowerCase(); if (q.length < 2) return;
    const r = impRows[+f.dataset.fix]; r.cands = players.filter(p => p.active && (p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q))).slice(0, 8);
    const sel = f.previousElementSibling; sel.innerHTML = '<option value="">— salta —</option>' + r.cands.map(p => '<option value="'+p.id+'">'+esc(p.role+' '+p.name+' · '+p.team)+'</option>').join(''); };
  $('#impGo').onclick = async () => {
    const replace = $('#impReplace').checked; const results = [];
    for (const t of Object.keys(teams)) {
      const roster = teams[t].map(i => impRows[i]).filter(r => r.pid).map(r => ({ player_id: r.pid, price: r.price || 0 }));
      const { data, error } = await sb.rpc('import_roster', { p_league: L.league.id, p_team: t, p_roster: roster, p_replace: replace });
      results.push(error ? esc(t)+': errore ('+esc(error.message)+')' : esc(data.team)+': '+(data.pending ? data.players+' giocatori, squadra <b>in attesa</b> di chi entrerà col codice' : data.players+' giocatori assegnati'+(data.skipped ? ', '+data.skipped+' saltati (già in altre rose o non validi)' : '')));
    }
    box.innerHTML = '<div class="msg ok"><b>Import completato.</b><br>'+results.join('<br>')+'</div>';
    impRows = []; await refreshLeagueData(); loadPending();
  };
}
async function loadPending(){
  const box = $('#pendingBox'); if (!box || !L) return;
  const { data, error } = await sb.from('league_pending').select('team_name,roster,created_at').eq('league_id', L.league.id).order('team_name');
  if (error || !data || !data.length) { box.innerHTML = ''; return; }
  box.innerHTML = '<h3 style="margin-top:18px">Squadre in attesa ('+data.length+')</h3><p class="small">Rose già caricate: chi entra con il codice invito <b>'+esc(L.league.invite_code)+'</b> sceglie una di queste squadre e la eredita con giocatori e prezzi.</p><ul class="list">' +
    data.map(p => '<li><div><b>'+esc(p.team_name)+'</b><div class="muted">'+(p.roster || []).length+' giocatori · '+(p.roster || []).reduce((a, x) => a + (x.price || 0), 0)+' crediti spesi</div></div>'+(L.isAdmin ? '<button class="small warn" data-delpend="'+esc(p.team_name)+'">Elimina</button>' : '')+'</li>').join('') + '</ul>';
  $$('[data-delpend]', box).forEach(b => { b.onclick = async () => { if (!sure(b, 'Sicuro? Elimina')) return; const { error } = await sb.rpc('delete_pending', { p_league: L.league.id, p_team: b.dataset.delpend }); if (error) err(error); else loadPending(); }; });
}
async function checkPendingForCode(){
  const code = $('#jnCode').value.trim(); const box = $('#jnPickBox'), sel = $('#jnPick');
  if (!box || code.length < 8) { if (box) box.classList.add('hidden'); return; }
  const { data, error } = await sb.rpc('pending_teams', { p_code: code });
  if (error || !data || !data.length) { box.classList.add('hidden'); return; }
  sel.innerHTML = '<option value="">— squadra nuova (scrivi il nome qui sotto) —</option>' + data.map(t => '<option value="'+esc(t.team_name)+'">'+esc(t.team_name)+' ('+t.players+' giocatori già in rosa)</option>').join('');
  box.classList.remove('hidden');
}

/* ---------- chat rapida utente <-> staff (tabelle messages/staff, fix-009) ---------- */
let isStaff = false, chatOpen = false, chatChannel = null, chatUnread = 0;
function fmtWhen(iso){ const d = new Date(iso); return d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' }) + ' ' + d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }); }
async function initChat(){
  const btn = $('#chatBtn'); if (!btn) return;
  btn.onclick = () => { if (!user) { msg('Entra o crea un account per scriverci: rispondiamo qui dentro.', 'ok'); return show('auth'); } chatOpen = !chatOpen; $('#chatPanel').classList.toggle('hidden', !chatOpen); if (chatOpen) { loadChat(); $('#chatText').focus(); } };
  $('#chatClose').onclick = () => { chatOpen = false; $('#chatPanel').classList.add('hidden'); };
  $('#chatSend').onclick = sendChat;
  $('#chatText').onkeydown = e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) sendChat(); };
  isStaff = false;
  if (chatChannel) { try { sb.removeChannel(chatChannel); } catch (e) {} chatChannel = null; }
  if (!user) { $$('nav a[data-view=messaggi]').forEach(a => a.classList.add('hidden')); return; }
  const { data } = await sb.from('staff').select('user_id').eq('user_id', user.id).maybeSingle();
  isStaff = !!data;
  $$('nav a[data-view=messaggi]').forEach(a => a.classList.toggle('hidden', !isStaff));
  await refreshUnread();
  chatChannel = sb.channel('chat-' + user.id).on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'messages' }, () => {
    refreshUnread(); if (chatOpen) loadChat(); const v = $('#view-messaggi'); if (isStaff && v && !v.classList.contains('hidden')) renderMessaggi(); }).subscribe();
}
async function refreshUnread(){
  if (!user) return;
  const q = isStaff ? sb.from('messages').select('id', { count: 'exact', head: true }).eq('from_staff', false).eq('read_by_staff', false)
                    : sb.from('messages').select('id', { count: 'exact', head: true }).eq('user_id', user.id).eq('from_staff', true).eq('read_by_user', false);
  const { count, error } = await q; chatUnread = error ? 0 : (count || 0);
  const b = $('#chatBadge'); if (b) { b.textContent = chatUnread; b.classList.toggle('hidden', !chatUnread); }
  const n = $('nav a[data-view=messaggi] .nbadge'); if (n) { n.textContent = chatUnread; n.classList.toggle('hidden', !chatUnread); }
}
async function loadChat(){
  const box = $('#chatMsgs'); if (!box || !user) return;
  const { data, error } = await sb.from('messages').select('id,from_staff,text,created_at,read_by_user').eq('user_id', user.id).order('created_at');
  if (error) { box.innerHTML = '<div class="msg err">Chat non disponibile: '+esc(error.message)+'</div>'; return; }
  box.innerHTML = (data && data.length) ? data.map(m => '<div class="cm '+(m.from_staff ? 'staff' : 'user')+'"><div>'+esc(m.text).replace(/\n/g, '<br>')+'</div><span>'+(m.from_staff ? 'TransferBeat · ' : '')+fmtWhen(m.created_at)+'</span></div>').join('')
    : '<div class="msg hint">👋 Scrivici un suggerimento, una segnalazione o una domanda: rispondiamo qui, e vedrai un pallino sul pulsante quando c\'è una risposta.</div>';
  box.scrollTop = box.scrollHeight;
  const unread = (data || []).filter(m => m.from_staff && !m.read_by_user).map(m => m.id);
  if (unread.length) { await sb.from('messages').update({ read_by_user: true }).in('id', unread); refreshUnread(); }
}
async function sendChat(){
  const t = $('#chatText'); const text = (t.value || '').trim(); if (!text) return;
  const { error } = await sb.from('messages').insert({ user_id: user.id, author: user.id, from_staff: false, text: text, page: location.hash || '#home' });
  if (error) return err(error);
  t.value = ''; loadChat();
}
async function renderMessaggi(){
  const box = $('#msgList'); if (!box) return;
  if (!isStaff) { box.innerHTML = '<div class="msg">Questa vista è riservata allo staff.</div>'; return; }
  const { data, error } = await sb.from('messages').select('id,user_id,from_staff,text,page,created_at,read_by_staff').order('created_at', { ascending: false }).limit(500);
  if (error) return err(error);
  const conv = {}; (data || []).forEach(m => { (conv[m.user_id] = conv[m.user_id] || []).push(m); });
  const ids = Object.keys(conv);
  const { data: profs } = ids.length ? await sb.from('profiles').select('id,username').in('id', ids) : { data: [] };
  const name = {}; (profs || []).forEach(p => { name[p.id] = p.username; });
  box.innerHTML = ids.length ? ids.map(uid => { const ms = conv[uid].slice().reverse(); const unread = ms.filter(m => !m.from_staff && !m.read_by_staff).length;
    return '<div class="card conv"><h2>'+esc(name[uid] || uid.slice(0, 8))+(unread ? ' <span class="pill live">'+unread+' da leggere</span>' : '')+' <span class="muted">ultimo: '+fmtWhen(ms[ms.length - 1].created_at)+'</span></h2>' +
      '<div class="cmlist">'+ms.map(m => '<div class="cm '+(m.from_staff ? 'staff' : 'user')+'"><div>'+esc(m.text).replace(/\n/g, '<br>')+'</div><span>'+(m.from_staff ? 'staff' : esc(name[uid] || 'utente'))+' · '+fmtWhen(m.created_at)+(m.page ? ' · da '+esc(m.page) : '')+'</span></div>').join('')+'</div>' +
      '<div class="row"><input data-reply="'+uid+'" placeholder="Rispondi a '+esc(name[uid] || 'utente')+'…"><button class="small" data-send="'+uid+'" style="flex:0 0 auto">Invia</button></div></div>'; }).join('')
    : '<div class="msg hint">Nessun messaggio ancora. Quando un utente scrive dal pulsante "Scrivici", compare qui.</div>';
  $$('[data-send]', box).forEach(b => { b.onclick = async () => { const inp = $('[data-reply="'+b.dataset.send+'"]'); const text = inp.value.trim(); if (!text) return;
    const { error } = await sb.from('messages').insert({ user_id: b.dataset.send, author: user.id, from_staff: true, text: text }); if (error) return err(error); inp.value = ''; renderMessaggi(); }; });
  const unreadIds = (data || []).filter(m => !m.from_staff && !m.read_by_staff).map(m => m.id);
  if (unreadIds.length) { await sb.from('messages').update({ read_by_staff: true }).in('id', unreadIds); refreshUnread(); }
}

/* ---------- strategie d'asta (tabella strategies, fix-009): formato + budget per ruolo + obiettivi per tier, con tetti di spesa ---------- */
let strategies = [], sharedStrategies = [], curStrat = null, sharedStrat = null, lsteTab = 'liste';
const TIER_W = { 1: 1.0, 2: 0.6, 3: 0.38, 4: 0.22, 5: 0.1 };
const DEF_STRAT = { name: 'La mia strategia', teams: 8, credits: 500, slots: { P: 3, D: 8, C: 8, A: 6 }, budget: { P: 8, D: 22, C: 25, A: 45 },
  targets: { P: { 1: 1 }, D: { 1: 1, 2: 2, 3: 2 }, C: { 1: 1, 2: 2, 3: 2 }, A: { 1: 1, 2: 1, 3: 2 } }, list_id: null, description: '' };
function setLsteTab(t){
  lsteTab = t;
  $$('#lsteTabs a').forEach(a => a.classList.toggle('on', a.dataset.ltab === t));
  const lp = $('#lstePane'), sp = $('#strPane'); if (lp) lp.classList.toggle('hidden', t !== 'liste'); if (sp) sp.classList.toggle('hidden', t !== 'strategie');
  history.replaceState(null, '', '#' + (t === 'strategie' ? 'strategie' : 'liste'));
  if (t === 'strategie') renderStrategie();
}
async function loadStrategies(){
  if (!user || !sb) { strategies = []; if (!sharedStrat) curStrat = null; return; }
  const { data, error } = await sb.from('strategies').select('*').eq('owner_id', user.id).order('created_at');
  strategies = error ? [] : (data || []);
  if (curStrat && !sharedStrat && !strategies.some(s => s.id === curStrat.id)) curStrat = null;
  const want = localStorage.getItem('fantatb_strategy');
  if (!curStrat && want && strategies.some(s => s.id === want)) await selectStrategy(want);
}
async function loadSharedStrategies(){
  if (!sb) return;
  const { data, error } = await sb.from('strategies').select('*').or('featured.eq.true,is_public.eq.true').order('featured', { ascending: false }).order('updated_at', { ascending: false }).limit(50);
  sharedStrategies = error ? [] : (data || []).filter(s => !user || s.owner_id !== user.id);
}
async function stratList(st){
  if (!st || !st.list_id) return null;
  const l = lists.find(x => x.id === st.list_id) || sharedLists.find(x => x.id === st.list_id);
  let meta = l;
  if (!meta) { const { data } = await sb.from('lists').select('*').eq('id', st.list_id).maybeSingle(); meta = data; }
  if (!meta) return null;
  const { data: items } = await sb.from('list_items').select('player_id,tier,note').eq('list_id', st.list_id);
  const out = Object.assign({ items: {} }, meta); (items || []).forEach(it => { out.items[it.player_id] = { tier: it.tier, note: it.note || '' }; });
  return out;
}
async function selectStrategy(id){
  if (!id) { curStrat = null; localStorage.removeItem('fantatb_strategy'); return; }
  const s = strategies.find(x => x.id === id) || sharedStrategies.find(x => x.id === id); if (!s) return;
  curStrat = Object.assign({}, s); curStrat.list = await stratList(s);
  localStorage.setItem('fantatb_strategy', id);
}
function inflation(st){   // crediti in gioco / valore di listone di chi verra' davvero comprato (i migliori per quotazione, ruolo per ruolo)
  let val = 0;
  ROLES.forEach(r => { const n = (st.teams || 8) * ((st.slots || {})[r] || 0); val += players.filter(p => p.active && p.role === r).sort((a, b) => b.price - a.price).slice(0, n).reduce((a, p) => a + p.price, 0); });
  return val ? ((st.teams || 8) * (st.credits || 500)) / val : 1;
}
function stratPlan(st, list){
  const f = inflation(st); const plan = { f: f, roles: {} };
  ROLES.forEach(r => {
    const budget = Math.round((st.credits || 500) * ((st.budget || {})[r] || 0) / 100); const tg = (st.targets || {})[r] || {};
    const nTarget = Object.values(tg).reduce((a, v) => a + (+v || 0), 0); const reserve = Math.max(0, ((st.slots || {})[r] || 0) - nTarget);
    const wsum = Object.keys(tg).reduce((a, t) => a + (+tg[t] || 0) * TIER_W[t], 0);
    const caps = {}; Object.keys(tg).forEach(t => { if (+tg[t] > 0) caps[t] = wsum ? Math.max(1, Math.round((budget - reserve) * TIER_W[t] / wsum)) : 0; });
    const exp = {}, cand = {};
    if (list) for (let t = 1; t <= 5; t++) { const ps = Object.keys(list.items).filter(pid => list.items[pid].tier === t).map(pid => playersById[pid]).filter(p => p && p.role === r).sort((a, b) => b.price - a.price);
      cand[t] = ps; if (ps.length) exp[t] = Math.round(ps.reduce((a, p) => a + p.price, 0) / ps.length * f); }
    plan.roles[r] = { budget: budget, reserve: reserve, nTarget: nTarget, caps: caps, exp: exp, cand: cand };
  });
  return plan;
}
function stratForm(st){
  const num = (id, v, extra) => '<input type="number" id="st_'+id+'" value="'+v+'" '+(extra || '')+'>';
  return '<div class="strgrid"><div><label>Nome</label><input id="st_name" value="'+esc(st.name)+'"></div><div><label>Squadre</label>'+num('teams', st.teams, 'min="2" max="20"')+'</div><div><label>Crediti</label>'+num('credits', st.credits, 'min="50" step="10"')+'</div>' +
    ROLES.map(r => '<div><label>Slot '+ROLE_NAME[r]+'</label>'+num('slot_' + r, st.slots[r], 'min="0"')+'</div>').join('') + '</div>' +
    '<h3>Budget per ruolo (% dei crediti) <span id="st_sum" class="muted"></span></h3><div class="strgrid">' + ROLES.map(r => '<div><label>'+roleTag(r)+' '+ROLE_NAME[r]+'</label>'+num('b_' + r, st.budget[r], 'min="0" max="100"')+'</div>').join('') + '</div>' +
    '<h3>Quanti giocatori per tier vuoi prendere</h3><div class="tgrid"><div></div>'+[1,2,3,4,5].map(t => '<div class="muted" style="text-align:center"><span class="tier t'+t+'">T'+t+'</span> '+TIERS[t]+'</div>').join('') +
    ROLES.map(r => '<div>'+roleTag(r)+' '+ROLE_NAME[r]+'</div>'+[1,2,3,4,5].map(t => '<input type="number" min="0" id="tg_'+r+'_'+t+'" value="'+((st.targets[r] || {})[t] || 0)+'">').join('')).join('') + '</div>' +
    '<div class="strgrid" style="margin-top:8px"><div><label>Lista obiettivi collegata</label><select id="st_list"><option value="">— nessuna —</option>'+(lists.length ? '<optgroup label="Le mie liste">'+lists.map(l => '<option value="'+l.id+'"'+(st.list_id === l.id ? ' selected' : '')+'>'+esc(l.name)+'</option>').join('')+'</optgroup>' : '')+(sharedLists.length ? '<optgroup label="Condivise e consigliate">'+sharedLists.map(l => '<option value="'+l.id+'"'+(st.list_id === l.id ? ' selected' : '')+'>'+esc((l.featured ? '★ ' : '↗ ') + l.name)+'</option>').join('')+'</optgroup>' : '')+'</select></div>' +
    '<div><label>Note</label><input id="st_desc" value="'+esc(st.description || '')+'" placeholder="es. punto tutto su due top in attacco"></div></div>';
}
function readStratForm(base){
  const g = id => $('#st_' + id); const n = (id, d) => { const v = parseInt(g(id).value, 10); return isNaN(v) ? d : v; };
  const st = Object.assign({}, base);
  st.name = g('name').value.trim() || base.name; st.teams = n('teams', 8); st.credits = n('credits', 500); st.description = g('desc').value.trim(); st.list_id = g('list').value || null;
  st.slots = {}; st.budget = {}; st.targets = {};
  ROLES.forEach(r => { st.slots[r] = n('slot_' + r, 0); st.budget[r] = n('b_' + r, 0); st.targets[r] = {}; for (let t = 1; t <= 5; t++) { const v = parseInt($('#tg_' + r + '_' + t).value, 10) || 0; if (v > 0) st.targets[r][t] = v; } });
  return st;
}
const PLAN_HELP = '<details class="help"><summary>ℹ️ Come leggere il piano</summary>' +
  '<ul><li><b>Crediti in gioco</b> = squadre × crediti. <b>Inflazione</b> = crediti in gioco diviso il valore di listone dei giocatori che verranno davvero comprati (i migliori per quotazione in ogni ruolo, tanti quanti gli slot di tutte le squadre). Con 8 squadre da 500 crediti è di solito fra 1,3 e 2.</li>' +
  '<li><b>Prezzo atteso</b> = quotazione ufficiale × inflazione: quanto costerà probabilmente quel giocatore nella tua lega.</li>' +
  '<li><b>Budget del ruolo</b> = crediti × percentuale. Da questo si toglie 1 credito per ogni slot che non è un obiettivo (li riempirai a fine asta), e il resto si divide fra gli obiettivi con pesi per tier: T1 pesa 1, T2 0,6, T3 0,38, T4 0,22, T5 0,1. Il risultato è il <b>tetto</b>: il massimo da offrire per ogni giocatore di quel tier restando nel budget.</li>' +
  '<li>Per ogni tier vedi solo i giocatori <span class="prio p1">da prendere</span> (tanti quanti ne hai chiesti) e una o due <span class="prio p2">alternative</span>, presi dalla lista collegata in ordine di quotazione. Verde se il tetto copre il prezzo atteso, rosso se dovrai rinunciare a qualcosa.</li>' +
  '<li>La strategia <b>attiva</b> compare come cruscotto nella scheda Asta della tua lega: speso contro pianificato, ruolo per ruolo.</li></ul></details>';
function planHtml(st, list){
  const plan = stratPlan(st, list); const tot = (st.teams || 8) * (st.credits || 500);
  let h = '<div class="card plan"><h2>📐 Il piano</h2><p class="small">Crediti in gioco nella lega <b>'+tot+'</b> · inflazione stimata <b>'+plan.f.toFixed(2)+'</b> · lista collegata: <b>'+(list ? esc(list.name) : 'nessuna')+'</b></p>' + PLAN_HELP;
  h += '<div class="tw"><table><thead><tr><th>Ruolo</th><th class="num">Budget</th><th class="num">Slot</th><th class="num">Obiettivi</th><th class="num">Riserva 1 cr.</th>' + [1,2,3,4,5].map(t => '<th class="num"><span class="tier t'+t+'">T'+t+'</span> n × tetto</th>').join('') + '</tr></thead><tbody>';
  ROLES.forEach(r => { const p = plan.roles[r];
    h += '<tr><td>'+roleTag(r)+' '+ROLE_NAME[r]+'</td><td class="num"><b>'+p.budget+'</b> <span class="muted">('+(st.budget[r] || 0)+'%)</span></td><td class="num">'+(st.slots[r] || 0)+'</td><td class="num">'+p.nTarget+'</td><td class="num">'+p.reserve+'</td>' +
      [1,2,3,4,5].map(t => { const n = (st.targets[r] || {})[t] || 0; return '<td class="num">'+(n ? n+' × <b>'+p.caps[t]+'</b>'+(p.exp[t] ? '<div class="muted">atteso '+p.exp[t]+'</div>' : '') : '—')+'</td>'; }).join('') + '</tr>'; });
  h += '</tbody></table></div>';
  const bsum = ROLES.reduce((a, r) => a + (st.budget[r] || 0), 0);
  if (bsum !== 100) h += '<div class="msg err">Le percentuali del budget sommano a '+bsum+'%, non a 100.</div>';
  if (list) {
    h += '<h2>🎯 Chi prendere, ruolo per ruolo</h2>';
    ROLES.forEach(r => { const p = plan.roles[r]; const rows = [];
      for (let t = 1; t <= 5; t++) { const n = (st.targets[r] || {})[t] || 0; if (!n) continue; const c = p.cand[t] || [];
        if (!c.length) { rows.push('<tr><td><span class="tier t'+t+'">T'+t+'</span></td><td colspan="7" class="muted">nessun '+ROLE_NAME[r].toLowerCase()+' di tier '+t+' nella lista: aggiungine dalla scheda Liste</td></tr>'); continue; }
        c.slice(0, n + Math.min(2, Math.max(1, n))).forEach((pl, i) => { const expv = Math.round(pl.price * plan.f); const cap = p.caps[t]; const s = schede[pl.id] || {};
          rows.push('<tr class="tr'+t+'"><td><span class="tier t'+t+'">T'+t+'</span></td><td><span class="prio '+(i < n ? 'p1">da prendere' : 'p2">alternativa')+'</span></td><td>'+(s.url ? '<a class="pl" href="'+esc(s.url)+'">'+esc(pl.name)+'</a>' : esc(pl.name))+'</td><td class="muted">'+esc(pl.team)+'</td><td class="num">'+pl.price+'</td><td class="num">'+expv+'</td><td class="num"><span class="'+(cap >= expv ? 'okc' : 'koc')+'">'+cap+'</span></td><td class="num">'+fmt2(s.mv)+'</td></tr>'); }); }
      if (rows.length) h += '<h3>'+roleTag(r)+' '+ROLE_NAME[r]+' <span class="muted">budget '+p.budget+' · '+p.nTarget+' obiettivi su '+(st.slots[r] || 0)+' slot</span></h3><div class="tw"><table><thead><tr><th>Tier</th><th>Priorità</th><th>Giocatore</th><th>Squadra</th><th class="num">Quot.</th><th class="num">Atteso</th><th class="num">Tetto</th><th class="num">MV</th></tr></thead><tbody>'+rows.join('')+'</tbody></table></div>'; });
  } else h += '<div class="msg hint">Collega una lista obiettivi (campo "Lista obiettivi collegata" qui sopra, poi Salva) per vedere chi prendere con prezzo atteso e tetto.</div>';
  return h + '</div>';
}
async function renderStrategie(){
  const bar = $('#strBar'), ed = $('#strEditor'), tb = $('#strTb'), sh = $('#strShared'); if (!ed) return;
  await Promise.all([loadStrategies(), loadSharedStrategies()]);
  const on = s => !!(curStrat && curStrat.id === s.id && !sharedStrat);
  bar.innerHTML = (user ? '<span class="newbox"><input id="strNewName" placeholder="Nome della nuova strategia"><button id="strNew">＋ Crea</button></span>' : '<a data-view="auth" class="btn">Entra per creare la tua strategia</a>') +
    strategies.map(s => '<a class="chip'+(on(s) ? ' on' : '')+'" data-strat="'+s.id+'" title="'+s.teams+' squadre · '+s.credits+' crediti'+(s.is_public ? ' · condivisa '+esc(s.share_code) : '')+'">'+(on(s) ? '✓ ' : '')+esc(s.name)+(s.is_public ? ' 🔗' : '')+'</a>').join('') +
    (user && !strategies.length ? '<span class="small" style="align-self:center">Nessuna strategia ancora: creane una o parti da una di TransferBeat con "Usa".</span>' : '');
  $$('[data-strat]', bar).forEach(b => { b.onclick = async () => { sharedStrat = null; await selectStrategy(b.dataset.strat); history.replaceState(null, '', '#strategie'); renderStrategie(); }; });
  const nb = $('#strNew');
  if (nb) nb.onclick = async () => { const name = (($('#strNewName') || {}).value || '').trim(); if (!name) { msg('Scrivi il nome della nuova strategia nel campo accanto al pulsante', 'err'); return; }
    const { data, error } = await sb.from('strategies').insert(Object.assign({}, DEF_STRAT, { name: name.trim(), owner_id: user.id, author: (user.user_metadata && user.user_metadata.username) || '', list_id: curList ? curList.id : null })).select().single();
    if (error) return err(error); sharedStrat = null; await loadStrategies(); await selectStrategy(data.id); renderStrategie(); };
  const feat = sharedStrategies.filter(s => s.featured), pub = sharedStrategies.filter(s => !s.featured);
  tb.innerHTML = feat.length ? feat.map(s => '<div class="tcard"><b>⭐ '+esc(s.name)+'</b><div class="small">'+esc(s.description || '')+'</div><div class="small" style="margin-top:4px">'+s.teams+' squadre · '+s.credits+' crediti · budget '+ROLES.map(r => r+' '+(s.budget[r] || 0)+'%').join(' ')+'</div><div class="row" style="margin-top:6px"><button class="small" data-sharedstrat="'+esc(s.share_code)+'">Usa</button></div></div>').join('')
    : '<span class="small">Le strategie di TransferBeat compariranno qui (le crea lo staff con fanta_strategie.py).</span>';
  $$('[data-sharedstrat]', tb).forEach(b => { b.onclick = () => openSharedStrategy(b.dataset.sharedstrat); });
  sh.innerHTML = (pub.length ? '<ul class="list">' + pub.map(s => '<li><div><b>'+esc(s.name)+'</b><div class="muted">'+s.teams+' squadre · '+s.credits+' crediti'+(s.author ? ' · di '+esc(s.author) : '')+(s.description ? ' · '+esc(s.description) : '')+'</div></div><button class="small sec" data-sharedstrat="'+esc(s.share_code)+'">Apri</button></li>').join('') + '</ul>' : '<div class="muted small">Nessuna strategia condivisa dagli utenti al momento: chi preme "Condividi" sulla sua compare qui.</div>') +
    '<div class="row" style="margin-top:10px"><input id="strCode" placeholder="Codice di una strategia condivisa" style="text-transform:uppercase"><button id="strOpen" class="sec" style="flex:0 0 auto">Apri</button></div>';
  $$('[data-sharedstrat]', sh).forEach(b => { b.onclick = () => openSharedStrategy(b.dataset.sharedstrat); });
  $('#strOpen').onclick = () => openSharedStrategy($('#strCode').value.trim());
  const st = sharedStrat || curStrat;
  if (!st) { ed.innerHTML = '<div class="msg hint">📐 <b>Crea la tua strategia</b> con il pulsante qui sopra, oppure parti da una di TransferBeat con "Usa" e poi copiala per modificarla. Scegli il formato, le percentuali di budget per ruolo e quanti giocatori per tier vuoi prendere: il piano ti dà il tetto di spesa per ogni obiettivo e il prezzo atteso con l\'inflazione della tua lega.</div>' + PLAN_HELP; return; }
  const own = !!(user && st.owner_id === user.id && !sharedStrat);
  const link = location.origin + '/fanta/#strategia/' + st.share_code;
  ed.innerHTML = '<div class="card lhead"><div class="row" style="justify-content:space-between;align-items:flex-start"><div style="flex:1 1 auto"><h2 style="margin:0">📐 '+esc(st.name)+(st.featured ? ' <span class="pill">TransferBeat</span>' : '')+(own && on(st) ? ' <span class="pill live">attiva</span>' : '')+'</h2><div class="muted">'+(st.author ? 'di '+esc(st.author)+' · ' : '')+st.teams+' squadre · '+st.credits+' crediti</div>'+(st.description ? '<p style="margin:6px 0 0;font-size:14px">'+esc(st.description)+'</p>' : '')+'</div>' +
    '<div class="row" style="flex:0 0 auto">' + (own ? '<button class="small" id="strSave">💾 Salva e ricalcola</button><button class="small sec" id="strShare">'+(st.is_public ? '🔗 Condivisa ✓' : '🔗 Condividi')+'</button>' : (user ? '<button class="small" id="strCopy">Copia e modifica</button>' : '<a data-view="auth" class="btn small">Entra per copiarla</a>')) + '<button class="small sec" id="strXlsx">⬇️ Excel</button>' + (own ? '<button class="small warn" id="strDelete">Elimina</button>' : '') + '</div></div>' +
    (own && st.is_public ? '<p class="small">Link da condividere: <a href="'+esc(link)+'">'+esc(link)+'</a> · codice <b>'+esc(st.share_code)+'</b>. Chi lo apre la vede e può copiarla.</p>' : '') +
    (own ? stratForm(st) : '<div class="strgrid"><div><label>Formato</label>'+st.teams+' squadre, '+st.credits+' crediti, slot '+ROLES.map(r => r+st.slots[r]).join(' ')+'</div><div><label>Budget</label>'+ROLES.map(r => r+' '+(st.budget[r] || 0)+'%').join(' · ')+'</div><div><label>Obiettivi per tier</label>'+ROLES.map(r => r+': '+[1,2,3,4,5].filter(t => (st.targets[r] || {})[t]).map(t => (st.targets[r] || {})[t]+'×T'+t).join(' ')).join(' · ')+'</div></div>') + '</div>' + planHtml(st, st.list);
  $('#strXlsx').onclick = () => exportStrategyXlsx(st);
  if (own) {
    const upd = () => { const s = ROLES.reduce((a, r) => a + (parseInt($('#st_b_' + r).value, 10) || 0), 0); $('#st_sum').textContent = '= ' + s + '%' + (s === 100 ? ' ✓' : ' (deve fare 100)'); }; upd(); ROLES.forEach(r => { $('#st_b_' + r).oninput = upd; });
    $('#strSave').onclick = async () => { const s = readStratForm(st); const row = { name: s.name, description: s.description, teams: s.teams, credits: s.credits, slots: s.slots, budget: s.budget, targets: s.targets, list_id: s.list_id, updated_at: new Date().toISOString() };
      const { error } = await sb.from('strategies').update(row).eq('id', st.id); if (error) return err(error); await loadStrategies(); await selectStrategy(st.id); msg('Strategia salvata', 'ok'); renderStrategie(); };
    $('#strShare').onclick = async () => { const { error } = await sb.from('strategies').update({ is_public: !st.is_public }).eq('id', st.id); if (error) return err(error); await loadStrategies(); await selectStrategy(st.id); renderStrategie(); };
    $('#strDelete').onclick = async () => { const b = $('#strDelete'); if (b.dataset.sure !== '1') { b.dataset.sure = '1'; b.textContent = 'Sicuro? Elimina davvero'; return; } const { error } = await sb.from('strategies').delete().eq('id', st.id); if (error) return err(error); curStrat = null; localStorage.removeItem('fantatb_strategy'); await loadStrategies(); renderStrategie(); };
  } else if (user && $('#strCopy')) {
    $('#strCopy').onclick = async () => { const { data, error } = await sb.rpc('copy_strategy', { p_code: st.share_code, p_name: null }); if (error) return err(error); sharedStrat = null; await loadLists(); await loadStrategies(); await selectStrategy(data); msg('Strategia copiata fra le tue: ora puoi modificarla', 'ok'); history.replaceState(null, '', '#strategie'); renderStrategie(); };
  }
}
async function exportStrategyXlsx(st){
  try { await loadXlsx(); } catch (e) { return err(e); }
  const list = st.list; const plan = stratPlan(st, list);
  const wb = XLSX.utils.book_new();
  const rows = [['Strategia', st.name], ['Formato', st.teams + ' squadre · ' + st.credits + ' crediti · slot P' + st.slots.P + ' D' + st.slots.D + ' C' + st.slots.C + ' A' + st.slots.A], ['Inflazione stimata', +plan.f.toFixed(2)], ['Lista collegata', list ? list.name : '—'], ['Note', st.description || ''], [],
    ['Ruolo', 'Budget %', 'Budget crediti', 'Slot', 'Obiettivi', 'Riserva (1 cr.)', 'Tetto T1', 'Tetto T2', 'Tetto T3', 'Tetto T4', 'Tetto T5']];
  ROLES.forEach(r => { const p = plan.roles[r]; rows.push([ROLE_NAME[r], st.budget[r] || 0, p.budget, st.slots[r] || 0, p.nTarget, p.reserve, p.caps[1] || '', p.caps[2] || '', p.caps[3] || '', p.caps[4] || '', p.caps[5] || '']); });
  rows.push([], ['Ruolo', 'Tier', 'Priorità', 'Giocatore', 'Squadra', 'Quotazione', 'Prezzo atteso', 'Tetto', 'MV', 'FMV', 'Titolarità %', 'Nota']);
  ROLES.forEach(r => { const p = plan.roles[r]; for (let t = 1; t <= 5; t++) { const n = (st.targets[r] || {})[t] || 0; if (!n) continue;
    (p.cand[t] || []).slice(0, n + Math.min(2, Math.max(1, n))).forEach((pl, i) => { const s = schede[pl.id] || {}; rows.push([ROLE_NAME[r], 'T' + t, i < n ? 'Da prendere' : 'Alternativa', pl.name, pl.team, pl.price, Math.round(pl.price * plan.f), p.caps[t], s.mv == null ? '' : s.mv, s.fmv == null ? '' : s.fmv, s.tit == null ? '' : s.tit, (list && list.items[pl.id] || {}).note || '']); }); } });
  const ws1 = XLSX.utils.aoa_to_sheet(rows); ws1['!cols'] = [{ wch: 16 }, { wch: 9 }, { wch: 13 }, { wch: 24 }, { wch: 14 }, { wch: 11 }, { wch: 13 }, { wch: 8 }, { wch: 7 }, { wch: 7 }, { wch: 11 }, { wch: 30 }];
  XLSX.utils.book_append_sheet(wb, ws1, 'Strategia');
  const lr = [['Ruolo', 'Giocatore', 'Squadra', 'Tier', 'Quotazione', 'Prezzo atteso', 'MV', 'FMV', 'Titolarità %', 'Presenze', 'Gol', 'Assist']];
  players.filter(p => p.active).sort((a, b) => ROLES.indexOf(a.role) - ROLES.indexOf(b.role) || b.price - a.price).forEach(p => { const s = schede[p.id] || {}; const t = (list && list.items[p.id]) ? 'T' + list.items[p.id].tier : '';
    lr.push([p.role, p.name, p.team, t, p.price, Math.round(p.price * plan.f), s.mv == null ? '' : s.mv, s.fmv == null ? '' : s.fmv, s.tit == null ? '' : s.tit, s.pres == null ? '' : s.pres, s.gol == null ? '' : s.gol, s.assist == null ? '' : s.assist]); });
  const ws2 = XLSX.utils.aoa_to_sheet(lr); ws2['!cols'] = [{ wch: 6 }, { wch: 24 }, { wch: 14 }, { wch: 6 }, { wch: 11 }, { wch: 13 }, { wch: 7 }, { wch: 7 }, { wch: 11 }, { wch: 9 }, { wch: 6 }, { wch: 7 }]; ws2['!autofilter'] = { ref: 'A1:L' + lr.length };
  XLSX.utils.book_append_sheet(wb, ws2, 'Listone');
  const mine = (L && user) ? L.rosters.filter(x => x.user_id === user.id) : [];
  const rr = [['Ruolo', 'Slot', 'Giocatore', 'Prezzo pagato', 'Tetto pianificato', 'Note']]; let line = 2; const span = {};
  ROLES.forEach(r => { const have = mine.filter(x => (playersById[x.player_id] || {}).role === r); span[r] = [line, line];
    for (let i = 0; i < (st.slots[r] || 0); i++) { const x = have[i]; rr.push([r, i + 1, x ? (playersById[x.player_id] || {}).name || '' : '', x ? x.price : '', '', '']); span[r][1] = line; line++; } });
  rr.push([], ['Ruolo', 'Budget pianificato', 'Speso', 'Residuo', 'Slot riempiti']);
  const first = rr.length + 1;
  ROLES.forEach(r => { const [a, b] = span[r]; rr.push([ROLE_NAME[r], plan.roles[r].budget, { t: 'n', f: 'SUM(D' + a + ':D' + b + ')' }, { t: 'n', f: plan.roles[r].budget + '-SUM(D' + a + ':D' + b + ')' }, { t: 'n', f: 'COUNTA(C' + a + ':C' + b + ')' }]); });
  const last = rr.length;
  rr.push(['Totale', st.credits, { t: 'n', f: 'SUM(C' + first + ':C' + last + ')' }, { t: 'n', f: st.credits + '-SUM(C' + first + ':C' + last + ')' }, { t: 'n', f: 'SUM(E' + first + ':E' + last + ')' }]);
  const ws3 = XLSX.utils.aoa_to_sheet(rr); ws3['!cols'] = [{ wch: 8 }, { wch: 6 }, { wch: 24 }, { wch: 14 }, { wch: 17 }, { wch: 24 }];
  XLSX.utils.book_append_sheet(wb, ws3, 'La mia rosa');
  const fname = 'FantaTB - ' + String(st.name).replace(/[\\/:*?"<>|]+/g, ' ') + '.xlsx';
  const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' }); const url = URL.createObjectURL(new Blob([out], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
  let a = $('#strXlsxLink'); if (!a) { a = document.createElement('a'); a.id = 'strXlsxLink'; a.className = 'btn small'; a.style.marginLeft = '6px'; $('#strXlsx').after(a); }
  a.href = url; a.download = fname; a.textContent = '⬇️ File pronto: clicca qui per salvarlo';
  try { XLSX.writeFile(wb, fname); } catch (e) { console.warn('download automatico fallito', e); }
  msg('Excel pronto: se il download non è partito, usa il pulsante "File pronto: clicca qui"', 'ok');
}
async function openSharedStrategy(code){
  if (!code) return;
  const { data, error } = await sb.from('strategies').select('*').eq('share_code', code.toUpperCase()).maybeSingle();
  if (error || !data) return msg('Strategia non trovata o non condivisa', 'err');
  sharedStrat = Object.assign({}, data); sharedStrat.list = await stratList(data);
  show('liste'); setLsteTab('strategie'); history.replaceState(null, '', '#strategia/' + data.share_code);
}
function stratDashHtml(){   // cruscotto nella scheda Asta: pianificato contro speso per ruolo, obiettivi ancora liberi
  if (!curStrat || !L) return '';
  const st = curStrat; const plan = stratPlan(st, st.list); const mine = L.rosters.filter(r => r.user_id === user.id);
  const taken = new Set(L.rosters.map(r => r.player_id));
  let h = '<div class="card plan" style="margin-bottom:14px"><h2>📐 '+esc(st.name)+' <span class="muted">crediti residui '+(L.me ? L.me.credits : '?')+' · inflazione stimata '+plan.f.toFixed(2)+'</span></h2><div class="strgrid">';
  ROLES.forEach(r => { const p = plan.roles[r]; const spent = mine.filter(x => (playersById[x.player_id] || {}).role === r).reduce((a, x) => a + x.price, 0); const pct = p.budget ? Math.min(100, Math.round(spent * 100 / p.budget)) : 0;
    h += '<div><div class="small">'+roleTag(r)+' '+ROLE_NAME[r]+' · speso <b>'+spent+'</b> su '+p.budget+' · slot '+(st.slots[r] - slotsLeft(user.id, r))+'/'+st.slots[r]+'</div><div class="bar"><i style="width:'+pct+'%;background:'+(spent > p.budget ? 'var(--red)' : 'var(--accent)')+'"></i></div></div>'; });
  h += '</div>';
  if (st.list) { const free = []; ROLES.forEach(r => { for (let t = 1; t <= 3; t++) (plan.roles[r].cand[t] || []).forEach(pl => { if (!taken.has(pl.id)) free.push([t, pl, plan.roles[r].caps[t], Math.round(pl.price * plan.f)]); }); });
    if (free.length) h += '<p class="small" style="margin-top:8px">Obiettivi ancora liberi: ' + free.slice(0, 14).map(x => '<span class="tier t'+x[0]+'">T'+x[0]+'</span> '+esc(x[1].name)+' <span class="muted">('+(x[2] ? 'tetto '+x[2] : 'atteso '+x[3])+')</span>').join(' · ') + (free.length > 14 ? ' …' : '') + '</p>'; }
  return h + '</div>';
}
function leagueKpis(){
  const box = $('#lgKpis'); if (!box || !L || !L.me) return;
  const next = (matchdays || []).find(m => m.status === 'scheduled' && m.starts_at && new Date(m.starts_at) > new Date());
  const kp = (l, v, s) => '<div class="kpi"><div class="l">'+l+'</div><div class="v">'+v+'</div>'+(s ? '<div class="s">'+s+'</div>' : '')+'</div>';
  box.innerHTML = kp('Crediti residui', L.me.credits, 'su '+(L.league.settings.credits || 500)) + ROLES.map(r => kp('Slot '+ROLE_NAME[r].toLowerCase(), (slotsOf()[r] - slotsLeft(user.id, r))+'/'+slotsOf()[r], slotsLeft(user.id, r) ? slotsLeft(user.id, r)+' liberi' : 'completo')).join('') +
    kp('Squadre', L.members.length+'/'+(L.league.settings.max_teams || 20), phase() === 'asta' ? 'fase asta' : 'campionato') + (next ? kp('Prossima giornata', 'G'+next.number, 'formazioni entro '+fmtWhen(next.starts_at)) : '');
}

async function init(){
  if (!CFG.SUPABASE_URL || CFG.SUPABASE_URL.includes('INSERISCI')) { msg('FantaTB non è ancora configurato (fanta/config.js).', 'err'); show('regole'); return; }
  sb = window.supabase.createClient(CFG.SUPABASE_URL, CFG.SUPABASE_ANON_KEY);
  const h = location.hash;   // letto PRIMA di initAuth: show() lo sovrascrive con la vista corrente
  await Promise.all([loadPlayers(), loadMatchdays()]);
  await initAuth();
  const m = h.match(/^#lega\/([0-9a-f-]{36})(?:\/([a-z]+))?$/);
  if (m && user) openLeague(m[1], m[2]);
  await loadLists(); await loadSharedLists(); await restoreActiveList(); await loadStrategies(); initChat();
  const v = h.slice(1);
  if (['listone', 'voti', 'regole', 'liste'].includes(v)) show(v);   // viste pubbliche raggiungibili anche senza login
  if (v === 'strategie') { show('liste'); setLsteTab('strategie'); }
  if (v === 'messaggi' && user) show('messaggi');
  const ml = h.match(/^#lista\/([A-Za-z0-9]{6,12})$/);
  if (ml) openSharedList(ml[1]);
  const ms = h.match(/^#strategia\/([A-Za-z0-9]{6,12})$/);
  if (ms) openSharedStrategy(ms[1]);
  if (h === '#crea') { if (user) { show('home'); setTimeout(() => { const f = $('#clName'); if (f) { f.scrollIntoView({ behavior: 'smooth', block: 'center' }); f.focus(); } }, 300); } else msg('Entra o crea un account: poi "Crea una lega" è nella tua pagina.', 'ok'); }
}
init().catch(err);
})();
