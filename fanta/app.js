/* FantaTB — app (vanilla JS + Supabase). Nessun build step. */
(function(){
'use strict';
const CFG = window.FANTATB_CONFIG || {};
const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ROLES = ['P','D','C','A'];
const ROLE_NAME = {P:'Portieri', D:'Difensori', C:'Centrocampisti', A:'Attaccanti'};

let sb = null, user = null, players = [], playersById = {}, schede = {};   // schede: /data/fanta/schede.json (URL scheda, MV, FMV, titolarità, presenze, gol, assist)
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
  if (['home', 'listone', 'voti', 'regole'].includes(view)) history.replaceState(null, '', '#' + view);   // cosi' "indietro" dalle schede giocatore torna qui
}
document.addEventListener('click', e => {
  const a = e.target.closest('[data-view]'); if (a){ e.preventDefault(); if (!user && a.dataset.view !== 'listone' && a.dataset.view !== 'voti' && a.dataset.view !== 'regole') return show('auth'); show(a.dataset.view); }
  const t = e.target.closest('[data-tab]'); if (t){ e.preventDefault(); renderTabs(t.dataset.tab); }
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
    if (prev !== (user ? user.id : null)) show(user ? 'home' : 'auth');   // solo a login/logout veri: l'evento iniziale non deve coprire la vista scelta dall'hash
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
    sb.from('players').select('id,name,team,role,price,active').order('price', { ascending: false }).limit(2000),
    fetch('/data/fanta/schede.json', { cache: 'no-cache' }).then(r => r.ok ? r.json() : null).then(j => { schede = (j && j.players) || {}; }).catch(() => {})
  ]);
  if (error) return err(error);
  players = data || []; playersById = {}; players.forEach(p => playersById[p.id] = p);
}
function roleTag(r){ return '<span class="role '+r+'">'+r+'</span>'; }
/* tabella del listone, condivisa fra la vista pubblica (#lsTable) e la scheda Listone della lega (#tab-listone, con stato libero/preso) */
const lsState = { ls: { k: 'price', asc: false }, ll: { k: 'price', asc: false } };
const fmt2 = v => v == null ? '—' : Number(v).toFixed(2).replace('.', ',');
function lsCell(v, f){ return '<td class="num">'+(v == null ? '—' : (f ? f(v) : v))+'</td>'; }
function lsVal(p, k){
  if (k === 'price') return p.price; if (k === 'name') return p.name; if (k === 'team') return p.team; if (k === 'role') return 'PDCA'.indexOf(p.role);
  if (k === 'stato') return p._stato || '';
  const s = schede[p.id]; return (s && s[k] != null) ? s[k] : -1;
}
function filterPlayers(q, r){
  q = (q || '').toLowerCase();
  return players.filter(p => p.active && (!r || p.role === r) && (!q || p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q)));
}
function listoneHtml(rows, sort, withStato){
  const th = (k, lab, title, num) => '<th class="srt'+(num ? ' num' : '')+(sort.k === k ? ' on' : '')+'" data-k="'+k+'"'+(title ? ' title="'+title+'"' : '')+'>'+lab+(sort.k === k ? (sort.asc ? ' ▲' : ' ▼') : '')+'</th>';
  rows = rows.slice().sort((a, b) => { const x = lsVal(a, sort.k), y = lsVal(b, sort.k); const c = typeof x === 'string' ? x.localeCompare(y) : (x - y); return sort.asc ? c : -c; }).slice(0, 400);
  return '<div class="tw"><table><thead><tr>'+th('role','R')+th('name','Giocatore')+th('team','Squadra')+(withStato ? th('stato','Stato','Libero o già in una rosa di questa lega') : '')+
    th('price','Quot.','Quotazione FantaTB',true)+th('mv','MV','Media voto FantaTB, stagione in corso',true)+th('fmv','FMV','Fantamedia: media dei fantavoti con bonus e malus',true)+
    th('tit','Tit.','Indice di titolarità per la prossima giornata',true)+th('pres','Pres.','Presenze in Serie A',true)+th('gol','Gol','Gol in Serie A',true)+th('assist','Assist','Assist in Serie A',true)+'</tr></thead><tbody>' +
    rows.map(p => { const s = schede[p.id] || {};
      const nm = s.url ? '<a class="pl" href="'+esc(s.url)+'" title="Apri la scheda con le statistiche (poi Torna al listone)">'+esc(p.name)+'</a>' : esc(p.name);
      return '<tr'+(withStato && p._stato ? ' class="taken"' : '')+'><td>'+roleTag(p.role)+'</td><td>'+nm+'</td><td>'+esc(p.team)+'</td>'+
        (withStato ? '<td class="muted">'+(p._stato ? esc(p._stato) : '<span class="free">libero</span>')+'</td>' : '')+
        '<td class="num"><b>'+p.price+'</b></td>'+lsCell(s.mv, fmt2)+lsCell(s.fmv, fmt2)+lsCell(s.tit, v => '<span class="pct '+(v >= 70 ? 'g' : v >= 40 ? 'a' : 'r')+'">'+v+'%</span>')+
        lsCell(s.pres)+lsCell(s.gol)+lsCell(s.assist)+'</tr>'; }).join('') + '</tbody></table></div>' +
    '<p class="small">MV = media voto FantaTB, FMV = fantamedia (voto più bonus e malus), Tit. = indice di titolarità per la prossima giornata; presenze, gol e assist in Serie A. Clic sull\'intestazione per ordinare, sul nome per la scheda completa: da lì "Torna al listone" riporta qui.</p>';
}
function bindSort(el, key, rerender){
  $$('th.srt', el).forEach(h => { h.onclick = () => { const k = h.dataset.k, st = lsState[key]; if (st.k === k) st.asc = !st.asc; else lsState[key] = { k: k, asc: (k === 'name' || k === 'team' || k === 'role' || k === 'stato') }; rerender(); }; });
}
function renderListone(){
  const el = $('#lsTable');
  el.innerHTML = players.length ? listoneHtml(filterPlayers($('#lsSearch').value, $('#lsRole').value), lsState.ls, false)
    : '<div class="msg">Listone non ancora caricato. Arriva con il primo aggiornamento dei dati.</div>';
  bindSort(el, 'ls', renderListone);
}
function renderLeagueListone(){
  const el = $('#tab-listone'); if (!el || !L) return;
  if (!$('#llSearch')) el.innerHTML = '<div class="row" style="max-width:720px;margin:10px 0;align-items:center"><input id="llSearch" placeholder="Cerca giocatore o squadra">' +
    '<select id="llRole"><option value="">Tutti i ruoli</option><option value="P">Portieri</option><option value="D">Difensori</option><option value="C">Centrocampisti</option><option value="A">Attaccanti</option></select>' +
    '<label class="small" style="white-space:nowrap"><input type="checkbox" id="llFree"> solo liberi</label></div><div id="llTable"></div>';
  const owner = {}; L.rosters.forEach(r => { owner[r.player_id] = memberName(r.user_id) + ' (' + r.price + ')'; });
  let rows = filterPlayers($('#llSearch').value, $('#llRole').value).map(p => Object.assign({}, p, { _stato: owner[p.id] || '' }));
  if ($('#llFree').checked) rows = rows.filter(p => !p._stato);
  $('#llTable').innerHTML = listoneHtml(rows, lsState.ll, true);
  bindSort($('#llTable'), 'll', renderLeagueListone);
  $('#llSearch').oninput = renderLeagueListone; $('#llRole').onchange = renderLeagueListone; $('#llFree').onchange = renderLeagueListone;
}
$('#lsSearch').oninput = renderListone; $('#lsRole').onchange = renderListone;

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
const DEFAULT_SETTINGS = { type: 'classic', phase: 'asta', credits: 500, max_teams: 8, slots: { P: 3, D: 8, C: 8, A: 6 }, timer: 20, max_subs: 3, bench_size: 7,
  goal_base: 66, goal_step: 6, mod_difesa: true, mod_centrocampo: false, mod_attacco: false, bonus_casa: 0, bonus_trasferta: 0,
  bonus: Object.fromEntries(BONUS_KEYS.map(k => [k[0], k[2]])) };
function settingsFormHtml(s, px){
  s = Object.assign({}, DEFAULT_SETTINGS, s || {}); const sl = Object.assign({}, DEFAULT_SETTINGS.slots, s.slots || {}); const bn = Object.assign({}, DEFAULT_SETTINGS.bonus, s.bonus || {});
  const num = (id, label, v, step) => '<div><label>'+label+'</label><input id="'+px+'_'+id+'" type="number" step="'+(step || 1)+'" value="'+v+'"></div>';
  const chk = (id, label, v) => '<div class="chk"><input type="checkbox" id="'+px+'_'+id+'" '+(v ? 'checked' : '')+'><label for="'+px+'_'+id+'" style="margin:0">'+label+'</label></div>';
  return '<fieldset><legend>Lega</legend><div class="settings-grid">' + num('credits', 'Crediti', s.credits) + num('max_teams', 'Squadre max', s.max_teams) + num('timer', 'Timer asta (s)', s.timer) + num('max_subs', 'Sostituzioni max', s.max_subs) + num('bench_size', 'Panchinari', s.bench_size) + '</div></fieldset>' +
    '<fieldset><legend>Rose</legend><div class="settings-grid">' + num('P', 'Portieri', sl.P) + num('D', 'Difensori', sl.D) + num('C', 'Centrocampisti', sl.C) + num('A', 'Attaccanti', sl.A) + '</div></fieldset>' +
    '<fieldset><legend>Gol e scontri</legend><div class="settings-grid">' + num('goal_base', 'Primo gol a', s.goal_base, 0.5) + num('goal_step', 'Un gol ogni', s.goal_step, 0.5) + num('bonus_casa', 'Fattore casa', s.bonus_casa, 0.5) + num('bonus_trasferta', 'Fattore trasferta', s.bonus_trasferta, 0.5) + '</div></fieldset>' +
    '<fieldset><legend>Modificatori</legend><div class="settings-grid">' + chk('mod_difesa', 'Difesa', s.mod_difesa) + chk('mod_centrocampo', 'Centrocampo', s.mod_centrocampo) + chk('mod_attacco', 'Attacco', s.mod_attacco) + '</div>' +
    '<p class="muted" style="margin-top:6px">Difesa: media di portiere e 3 migliori difensori (almeno 4 schierati), da +1 a +6. Attacco: media voto degli attaccanti (almeno 2), stessa scala. Centrocampo: confronto tra le medie dei centrocampisti delle due squadre, da +1 a +6 a chi ha la media più alta.</p></fieldset>' +
    '<fieldset><legend>Bonus e malus</legend><div class="settings-grid">' + BONUS_KEYS.map(k => num('b_' + k[0], k[1], bn[k[0]], 0.5)).join('') + '</div></fieldset>';
}
function readSettingsForm(px, base){
  const g = id => $('#' + px + '_' + id); const n = (id, d) => { const v = parseFloat(g(id).value); return isNaN(v) ? d : v; };
  const s = Object.assign({}, DEFAULT_SETTINGS, base || {});
  s.credits = n('credits', 500); s.max_teams = n('max_teams', 8); s.timer = n('timer', 20); s.max_subs = n('max_subs', 3); s.bench_size = n('bench_size', 7);
  s.slots = { P: n('P', 3), D: n('D', 8), C: n('C', 8), A: n('A', 6) };
  s.goal_base = n('goal_base', 66); s.goal_step = n('goal_step', 6); s.bonus_casa = n('bonus_casa', 0); s.bonus_trasferta = n('bonus_trasferta', 0);
  s.mod_difesa = g('mod_difesa').checked; s.mod_centrocampo = g('mod_centrocampo').checked; s.mod_attacco = g('mod_attacco').checked;
  s.bonus = Object.fromEntries(BONUS_KEYS.map(k => [k[0], n('b_' + k[0], k[2])]));
  return s;
}

/* ---------- home: leghe ---------- */
async function loadLeagues(){
  const { data, error } = await sb.from('league_members').select('league_id, team_name, role, credits, leagues(id,name,invite_code,settings)').eq('user_id', user.id);
  if (error) return err(error);
  const ul = $('#leagueList');
  ul.innerHTML = (data && data.length) ? data.map(m => '<li><div><b>'+esc(m.leagues.name)+'</b><div class="muted">'+esc(m.team_name)+' · '+(m.role === 'admin' ? 'admin' : 'partecipante')+' · crediti '+m.credits+'</div></div><button class="small" data-open="'+m.league_id+'">Apri</button></li>').join('')
    : '<li class="muted">Non sei ancora in nessuna lega. Creane una o entra con un codice.</li>';
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
  if (!code || !team) return msg('Servono codice e nome squadra', 'err');
  const { data, error } = await sb.rpc('join_league', { p_code: code, p_team: team });
  if (error) return err(error);
  msg('Sei dentro!', 'ok'); openLeague(data);
};

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
  renderTabs(tab); renderRules(); renderAuction(); subscribe(); loadSeasonData();
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
  $('#tab-membri').innerHTML = table + cards;
  $$('[data-release]').forEach(b => b.onclick = async () => {
    if (!confirm('Rimuovere il giocatore dalla rosa e rimborsare i crediti?')) return;
    const { error } = await sb.rpc('release_player', { p_league: L.league.id, p_player: +b.dataset.release });
    if (error) err(error); else refreshLeagueData();
  });
}
function renderRosters(){ renderMembers(); const t = $('#tab-listone'); if (t && !t.classList.contains('hidden')) renderLeagueListone(); }
function renderRules(){
  const s = Object.assign({}, DEFAULT_SETTINGS, L.league.settings || {}), bn = Object.assign({}, DEFAULT_SETTINGS.bonus, s.bonus || {}), sl = Object.assign({}, DEFAULT_SETTINGS.slots, s.slots || {});
  const view = '<div class="card"><h2>Regole in vigore <span class="pill '+(phase() === 'asta' ? '' : 'live')+'">'+(phase() === 'asta' ? 'fase asta' : 'campionato')+'</span></h2><table><tbody>' +
    '<tr><td>Crediti</td><td>'+s.credits+'</td><td>Squadre max</td><td>'+s.max_teams+'</td></tr>' +
    '<tr><td>Rose</td><td colspan="3">'+ROLES.map(r => r+' '+sl[r]).join(' · ')+'</td></tr>' +
    '<tr><td>Sostituzioni</td><td>'+s.max_subs+'</td><td>Panchinari</td><td>'+s.bench_size+'</td></tr><tr><td>Timer asta</td><td colspan="3">'+s.timer+' s</td></tr>' +
    '<tr><td>Gol</td><td colspan="3">primo a '+s.goal_base+', poi uno ogni '+s.goal_step+' punti</td></tr>' +
    '<tr><td>Fattore casa / trasferta</td><td colspan="3">'+s.bonus_casa+' / '+s.bonus_trasferta+'</td></tr>' +
    '<tr><td>Modificatori</td><td colspan="3">'+[s.mod_difesa && 'difesa', s.mod_centrocampo && 'centrocampo', s.mod_attacco && 'attacco'].filter(Boolean).join(', ') + (s.mod_difesa || s.mod_centrocampo || s.mod_attacco ? '' : 'nessuno')+'</td></tr>' +
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
  let html = '<div class="grid3"><div>';
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
      slots.push(p ? '<div class="slot '+r+'" data-out="'+p.id+'" title="Togli dal campo"><div class="shirt">'+r+'</div><span class="nm">'+esc(shortName(p.name))+'</span><span class="tm">'+esc(p.team)+'</span></div>'
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
    return p ? '<div class="slot '+p.role+'" data-bout="'+p.id+'" title="Togli dalla panchina"><div class="shirt">'+(i + 1)+'</div><span class="nm">'+esc(shortName(p.name))+'</span><span class="tm">'+p.role+' · '+esc(p.team)+'</span><span class="mv"><button class="small sec" data-bl="'+p.id+'">◀</button><button class="small sec" data-br="'+p.id+'">▶</button></span></div>'
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
    if (S.fixtures.length && !confirm('Rigenerare il calendario? Calendario e risultati attuali verranno cancellati.')) return;
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
  let rows = pl.map(p => '<tr><td>'+roleTag(p.role)+'</td><td>'+(p.sub ? '<span class="muted" style="text-decoration:line-through">'+esc(nm(p.player_id))+'</span> 🔁 '+esc(nm(p.sub)) : esc(nm(p.player_id)))+' <span class="em">'+emojis(p.bonus)+'</span></td><td>'+(p.voto == null ? 's.v.' : f1(p.voto))+'</td><td><b>'+f1(p.fv)+'</b></td></tr>').join('');
  for (let i = pl.length; i < 11; i++) rows += empty;
  const labels = opts.labels.length ? opts.labels : (!extras.length && d.mod_difesa ? ['Modificatore difesa'] : []);
  const exRows = labels.map(lb => { const e = extras.find(x => x.label === lb) || (lb === 'Modificatore difesa' && d.mod_difesa ? { v: d.mod_difesa } : { v: 0 });
    return '<tr class="ex"><td></td><td>'+esc(lb)+'</td><td></td><td>'+(e.v > 0 ? '+' : '')+f1(e.v)+'</td></tr>'; }).join('');
  let brows = bench.map((p, i) => '<tr class="'+(p.used ? '' : 'ex')+'"><td><span class="pill">'+(i + 1)+'</span></td><td>'+roleTag(p.role)+' '+esc(nm(p.player_id))+(p.used ? ' 🔁' : '')+' <span class="em">'+emojis(p.bonus)+'</span></td><td>'+(p.voto == null ? 's.v.' : f1(p.voto))+'</td><td>'+(p.fv == null ? '–' : f1(p.fv))+'</td></tr>').join('');
  for (let i = bench.length; i < opts.benchN; i++) brows += empty;
  const base = d.base != null ? d.base : pl.reduce((a, p) => a + (+p.fv || 0), 0);
  return '<div><h3>'+esc(name)+(missing ? ' <span class="pill">formazione non inviata</span>' : '')+'</h3><table><thead><tr><th></th><th>Giocatore</th><th>V</th><th>FV</th></tr></thead><tbody>' + rows +
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
  let html = '<div class="row" style="max-width:360px"><select id="rsMd">' + mds.map(n => '<option value="'+n+'" '+(n === md ? 'selected' : '')+'>Giornata '+n+(withRes.has(n) ? '' : (mdOpen(n) ? ' (da giocare)' : ' (in corso)'))+'</option>').join('') + '</select></div>';
  if (!computed) html += '<p class="muted" style="margin:8px 0">Giornata non ancora calcolata: formazioni schierate finora. Deadline '+fmtDate(mdInfo(md).starts_at)+'.</p>';
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
async function init(){
  if (!CFG.SUPABASE_URL || CFG.SUPABASE_URL.includes('INSERISCI')) { msg('FantaTB non è ancora configurato (fanta/config.js).', 'err'); show('regole'); return; }
  sb = window.supabase.createClient(CFG.SUPABASE_URL, CFG.SUPABASE_ANON_KEY);
  const h = location.hash;   // letto PRIMA di initAuth: show() lo sovrascrive con la vista corrente
  await Promise.all([loadPlayers(), loadMatchdays()]);
  await initAuth();
  const m = h.match(/^#lega\/([0-9a-f-]{36})(?:\/([a-z]+))?$/);
  if (m && user) openLeague(m[1], m[2]);
  const v = h.slice(1);
  if (['listone', 'voti', 'regole'].includes(v)) show(v);   // viste pubbliche raggiungibili anche senza login
  if (h === '#crea') { if (user) { show('home'); setTimeout(() => { const f = $('#clName'); if (f) { f.scrollIntoView({ behavior: 'smooth', block: 'center' }); f.focus(); } }, 300); } else msg('Entra o crea un account: poi "Crea una lega" è nella tua pagina.', 'ok'); }
}
init().catch(err);
})();
