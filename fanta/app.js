/* FantaTB — app (vanilla JS + Supabase). Nessun build step. */
(function(){
'use strict';
const CFG = window.FANTATB_CONFIG || {};
const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ROLES = ['P','D','C','A'];
const ROLE_NAME = {P:'Portieri', D:'Difensori', C:'Centrocampisti', A:'Attaccanti'};

let sb = null, user = null, players = [], playersById = {};
let L = null;            // lega corrente: {league, members, rosters, auction, bids}
let auctionTimer = null, channel = null;

function msg(text, kind){ const m = $('#msg'); m.innerHTML = text ? '<div class="msg '+(kind||'')+'">'+esc(text)+'</div>' : ''; if (text) setTimeout(()=>{ if (m.textContent === text) m.innerHTML=''; }, 6000); }
function err(e){ console.error(e); msg((e && (e.message || e.error_description)) || String(e), 'err'); }

/* ---------- viste ---------- */
function show(view){
  $$('main > section').forEach(s => s.classList.add('hidden'));
  const el = $('#view-' + view); if (el) el.classList.remove('hidden');
  $$('nav a').forEach(a => a.classList.toggle('on', a.dataset.view === view));
  if (view === 'home') loadLeagues();
  if (view === 'listone') renderListone();
  if (view === 'voti') loadVoti();
}
document.addEventListener('click', e => {
  const a = e.target.closest('[data-view]'); if (a){ e.preventDefault(); if (!user && a.dataset.view !== 'listone' && a.dataset.view !== 'voti' && a.dataset.view !== 'regole') return show('auth'); show(a.dataset.view); }
  const t = e.target.closest('[data-tab]'); if (t){ e.preventDefault(); $$('.tabs a').forEach(x => x.classList.toggle('on', x === t)); ['asta','formazione','rose','calendario','classifica','membri','regole'].forEach(k => $('#tab-'+k).classList.toggle('hidden', k !== t.dataset.tab)); }
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
  sb.auth.onAuthStateChange((_ev, session) => { user = session ? session.user : null; renderUser(); show(user ? 'home' : 'auth'); });
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
  const { data, error } = await sb.from('players').select('id,name,team,role,price,active').order('price', { ascending: false }).limit(2000);
  if (error) return err(error);
  players = data || []; playersById = {}; players.forEach(p => playersById[p.id] = p);
}
function roleTag(r){ return '<span class="role '+r+'">'+r+'</span>'; }
function renderListone(){
  const q = ($('#lsSearch').value || '').toLowerCase(); const r = $('#lsRole').value;
  const rows = players.filter(p => p.active && (!r || p.role === r) && (!q || p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q))).slice(0, 400);
  $('#lsTable').innerHTML = players.length ? '<table><thead><tr><th>R</th><th>Giocatore</th><th>Squadra</th><th>Quot.</th></tr></thead><tbody>' +
    rows.map(p => '<tr><td>'+roleTag(p.role)+'</td><td>'+esc(p.name)+'</td><td>'+esc(p.team)+'</td><td><b>'+p.price+'</b></td></tr>').join('') + '</tbody></table>'
    : '<div class="msg">Listone non ancora caricato. Arriva con il primo aggiornamento dei dati.</div>';
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
  const settings = { type: 'classic', credits: +$('#clCredits').value || 500, max_teams: +$('#clMax').value || 8,
    slots: { P: +$('#clP').value || 3, D: +$('#clD').value || 8, C: +$('#clC').value || 8, A: +$('#clA').value || 6 },
    timer: +$('#clTimer').value || 20, mod_difesa: $('#clModDif').checked,
    bonus: { gol: 3, assist: 1, rig_sbagliato: -3, rig_parato: 3, gol_subito: -1, autogol: -2, amm: -0.5, esp: -1 } };
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
async function openLeague(id){
  const [{ data: league, error: e1 }, { data: members, error: e2 }] = await Promise.all([
    sb.from('leagues').select('*').eq('id', id).single(),
    sb.from('league_members').select(MEMBER_SEL).eq('league_id', id).order('call_order')
  ]);
  if (e1 || e2) return err(e1 || e2);
  await attachProfiles(members);
  L = { league, members, rosters: [], auction: null, bids: [] };
  L.me = members.find(m => m.user_id === user.id); L.isAdmin = !!(L.me && L.me.role === 'admin');
  location.hash = 'lega/' + id;
  $$('main > section').forEach(s => s.classList.add('hidden')); $('#view-league').classList.remove('hidden');
  $('#lgName').textContent = league.name;
  $('#lgSub').innerHTML = esc(L.me.team_name)+' · '+members.length+'/'+(league.settings.max_teams || 20)+' squadre · codice invito <span class="code">'+esc(league.invite_code)+'</span>';
  await refreshLeagueData();
  renderRules(); renderAuction(); subscribe(); loadSeasonData();
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

function renderMembers(){
  $('#tab-membri').innerHTML = '<table><thead><tr><th>#</th><th>Squadra</th><th>Utente</th><th></th><th>Crediti</th><th>Rosa</th></tr></thead><tbody>' +
    L.members.map(m => '<tr class="'+(m.user_id === user.id ? 'me' : '')+'"><td>'+(m.call_order || '')+'</td><td><b>'+esc(m.team_name)+'</b></td><td>'+esc(m.profiles && m.profiles.username)+'</td><td>'+(m.role === 'admin' ? '<span class="pill">admin</span>' : '')+'</td><td>'+m.credits+'</td><td>'+L.rosters.filter(r => r.user_id === m.user_id).length+'</td></tr>').join('') + '</tbody></table>';
}
function renderRosters(){
  const byUser = {}; L.rosters.forEach(r => (byUser[r.user_id] = byUser[r.user_id] || []).push(r));
  const slots = slotsOf();
  $('#tab-rose').innerHTML = '<div class="grid">' + L.members.map(m => {
    const rs = (byUser[m.user_id] || []).map(r => Object.assign({}, r, { p: playersById[r.player_id] || { name: '#'+r.player_id, role: 'C', team: '' } }))
      .sort((a, b) => ROLES.indexOf(a.p.role) - ROLES.indexOf(b.p.role) || b.price - a.price);
    const head = ROLES.map(r => r+' '+rs.filter(x => x.p.role === r).length+'/'+slots[r]).join(' · ');
    const rows = rs.map(r => '<tr><td>'+roleTag(r.p.role)+'</td><td>'+esc(r.p.name)+'</td><td class="muted">'+esc(r.p.team)+'</td><td><b>'+r.price+'</b></td>' +
      (L.isAdmin ? '<td><button class="small sec" data-release="'+r.player_id+'" title="Rimuovi e rimborsa">✕</button></td>' : '') + '</tr>').join('');
    return '<div class="card'+(m.user_id === user.id ? ' hi' : '')+'"><h2>'+esc(m.team_name)+' <span class="muted">crediti '+m.credits+' · '+head+'</span></h2>' +
      (rs.length ? '<table><tbody>'+rows+'</tbody></table>' : '<div class="muted">Rosa vuota</div>') + '</div>';
  }).join('') + '</div>';
  $$('[data-release]').forEach(b => b.onclick = async () => {
    if (!confirm('Rimuovere il giocatore dalla rosa e rimborsare i crediti?')) return;
    const { error } = await sb.rpc('release_player', { p_league: L.league.id, p_player: +b.dataset.release });
    if (error) err(error); else refreshLeagueData();
  });
  renderMembers();
}
function renderRules(){
  const s = L.league.settings || {}, bon = s.bonus || {}, slots = s.slots || {};
  $('#tab-regole').innerHTML = '<div class="card"><h2>Regole della lega</h2><table><tbody>' +
    '<tr><td>Modalità</td><td>'+(s.type === 'mantra' ? 'Mantra' : 'Classic')+'</td></tr>' +
    '<tr><td>Crediti iniziali</td><td>'+(s.credits || 500)+'</td></tr>' +
    '<tr><td>Rose</td><td>'+ROLES.map(r => r+' '+(slots[r] || '')).join(' · ')+'</td></tr>' +
    '<tr><td>Timer asta</td><td>'+(s.timer || 20)+' s</td></tr>' +
    '<tr><td>Modificatore difesa</td><td>'+(s.mod_difesa ? 'sì' : 'no')+'</td></tr>' +
    '<tr><td>Bonus/malus</td><td>'+Object.entries(bon).map(([k, v]) => k.replace('_', ' ')+' '+(v > 0 ? '+' : '')+v).join(' · ')+'</td></tr>' +
    '</tbody></table>' + (L.isAdmin ? '<p class="muted" style="margin-top:8px">La modifica delle regole dopo la creazione arriva in fase 2.</p>' : '') + '</div>';
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
  box.innerHTML = html;
  $$('[data-bid]', box).forEach(b => b.onclick = () => bid(b.dataset.bid === 'custom' ? +$('#auCustom').value : +b.dataset.bid));
  const c = $('#auClose'); if (c) c.onclick = closeAuction;
  if (L.isAdmin) setupPicker(live);
  startTimer();
}
let picked = null;
function setupPicker(live){
  const list = $('#auList'), inp = $('#auSearch'), sel = $('#auRole');
  const taken = new Set(L.rosters.map(r => r.player_id));
  const draw = () => {
    const q = (inp.value || '').toLowerCase(), r = sel.value;
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
  const f = 'league_id=eq.' + L.league.id, onChange = async () => { await refreshLeagueData(); renderAuction(); };
  channel = sb.channel('lega-' + L.league.id)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'auctions', filter: f }, onChange)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'rosters', filter: f }, onChange)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'league_members', filter: f }, onChange)
    .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'auction_bids', filter: f }, onChange)
    .subscribe();
  clearInterval(window.__fantaPoll); window.__fantaPoll = setInterval(() => { if (L && !document.hidden) onChange(); }, 7000); // rete di sicurezza se il realtime salta
}

/* ---------- stagione: giornate e formazioni ---------- */
const SEASON = CFG.SEASON || 2026;
const MODULES = ['3-4-3', '3-5-2', '4-3-3', '4-4-2', '4-5-1', '5-3-2', '5-4-1'];
let matchdays = [], S = { fixtures: [], results: [], lineup: null, md: null };
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
  renderLineup(); renderCalendar(); renderStandings();
}
function myPlayers(){ return L.rosters.filter(r => r.user_id === user.id).map(r => playersById[r.player_id]).filter(Boolean); }
function wantOf(module){ const p = module.split('-').map(Number); return { P: 1, D: p[0], C: p[1], A: p[2] }; }
function benchNormalize(cur, mine){
  const st = new Set(cur.starters), ids = new Set(mine.map(p => p.id));
  cur.bench = cur.bench.filter(id => ids.has(id) && !st.has(id));
  mine.filter(p => !st.has(p.id) && !cur.bench.includes(p.id)).sort((a, b) => ROLES.indexOf(a.role) - ROLES.indexOf(b.role) || b.price - a.price).forEach(p => cur.bench.push(p.id));
}
function moveBench(cur, id, dir){ const i = cur.bench.indexOf(id), j = i + dir; if (i < 0 || j < 0 || j >= cur.bench.length) return; [cur.bench[i], cur.bench[j]] = [cur.bench[j], cur.bench[i]]; }
function lineupHtml(cur, mine, md, lu){
  const want = wantOf(cur.module), info = mdInfo(md), open = mdOpen(md);
  let html = '<div class="row"><div><label>Giornata</label><select id="luMd">' + Array.from({ length: 38 }, (_, i) => i + 1).map(n => '<option value="'+n+'" '+(n === md ? 'selected' : '')+'>Giornata '+n+(mdOpen(n) ? '' : ' (chiusa)')+'</option>').join('') + '</select></div>' +
    '<div><label>Modulo</label><select id="luMod">' + MODULES.map(m => '<option '+(m === cur.module ? 'selected' : '')+'>'+m+'</option>').join('') + '</select></div></div>' +
    '<p class="muted" style="margin:8px 0">Deadline: '+fmtDate(info.starts_at)+' · '+(open ? 'formazioni aperte' : 'giornata iniziata, formazioni chiuse')+(lu ? ' · salvata il '+fmtDate(lu.submitted_at) : ' · nessuna formazione salvata')+'</p>';
  if (!mine.length) html += '<div class="msg">La tua rosa è vuota: prima l\'asta.</div>';
  html += ROLES.map(r => {
    const list = mine.filter(p => p.role === r).sort((a, b) => b.price - a.price);
    const n = cur.starters.filter(id => (playersById[id] || {}).role === r).length;
    return '<h3>'+ROLE_NAME[r]+' <span class="pill">'+n+'/'+want[r]+'</span></h3><table><tbody>' + list.map(p => {
      const on = cur.starters.includes(p.id), bi = cur.bench.indexOf(p.id);
      return '<tr><td style="width:30px"><input type="checkbox" data-st="'+p.id+'" '+(on ? 'checked' : '')+' '+(!on && n >= want[r] ? 'disabled' : '')+'></td><td>'+esc(p.name)+' <span class="muted">'+esc(p.team)+'</span></td><td class="muted">'+(on ? 'titolare' : 'panchina '+(bi + 1))+'</td>' +
        (on ? '<td></td>' : '<td><button class="small sec" data-bup="'+p.id+'">▲</button> <button class="small sec" data-bdown="'+p.id+'">▼</button></td>') + '</tr>'; }).join('') + '</tbody></table>';
  }).join('');
  html += '<div class="row" style="margin-top:14px"><button id="luSave" '+(open ? '' : 'disabled')+'>Salva formazione</button></div>';
  return html;
}

async function renderLineup(){
  const box = $('#tab-formazione'), md = S.md, mine = myPlayers();
  const [{ data: lu }, { data: all }] = await Promise.all([
    sb.from('lineups').select('*').eq('league_id', L.league.id).eq('user_id', user.id).eq('matchday', md).maybeSingle(),
    sb.from('lineups').select('user_id, module, starters, submitted_at').eq('league_id', L.league.id).eq('matchday', md)
  ]);
  if (!S.lineup || S.lineup.md !== md) { S.lineup = { md, module: lu ? lu.module : '4-3-3', starters: lu ? lu.starters.slice() : [], bench: lu ? lu.bench.slice() : [] }; }
  const cur = S.lineup; benchNormalize(cur, mine);
  const open = mdOpen(md);
  const others = '<div class="card" style="margin-top:14px"><h2>Formazioni giornata '+md+'</h2>' + L.members.map(m => { const l2 = (all || []).find(x => x.user_id === m.user_id);
    return '<div class="list"><li><span>'+esc(m.team_name)+'</span><span class="muted">'+(l2 ? (open ? 'inviata ('+l2.module+')' : l2.module+': '+l2.starters.map(id => (playersById[id] || {}).name || '#'+id).join(', ')) : 'non inviata')+'</span></li></div>'; }).join('') +
    (open ? '<p class="muted">I titolari degli altri si vedono dopo la deadline.</p>' : '') + '</div>';
  box.innerHTML = '<div class="grid3"><div>' + lineupHtml(cur, mine, md, lu) + '</div><div><div class="card"><h2>Come funziona</h2><p class="muted">Scegli il modulo e spunta 11 titolari. Gli altri vanno in panchina nell\'ordine mostrato: in caso di senza voto entra il primo panchinaro dello stesso ruolo, fino a '+(L.league.settings.max_subs || 3)+' sostituzioni. Si salva fino all\'inizio della giornata.</p></div>' + others + '</div></div>';
  $('#luMd').onchange = e => { S.md = +e.target.value; S.lineup = null; renderLineup(); };
  $('#luMod').onchange = e => { cur.module = e.target.value; const want = wantOf(cur.module), cnt = { P: 0, D: 0, C: 0, A: 0 };
    cur.starters = cur.starters.filter(id => { const r = (playersById[id] || {}).role; cnt[r]++; return cnt[r] <= want[r]; }); renderLineup(); };
  $$('[data-st]', box).forEach(c => c.onchange = () => { const id = +c.dataset.st; if (c.checked) cur.starters.push(id); else cur.starters = cur.starters.filter(x => x !== id); renderLineup(); });
  $$('[data-bup]', box).forEach(b => b.onclick = () => { moveBench(cur, +b.dataset.bup, -1); renderLineup(); });
  $$('[data-bdown]', box).forEach(b => b.onclick = () => { moveBench(cur, +b.dataset.bdown, 1); renderLineup(); });
  $('#luSave').onclick = async () => {
    if (cur.starters.length !== 11) return msg('Servono 11 titolari, ne hai '+cur.starters.length, 'err');
    const { error } = await sb.rpc('save_lineup', { p_league: L.league.id, p_matchday: md, p_module: cur.module, p_starters: cur.starters, p_bench: cur.bench });
    if (error) return err(error);
    msg('Formazione salvata per la giornata '+md, 'ok'); renderLineup();
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

/* ---------- classifica e dettaglio giornata ---------- */
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
    (S.results.length ? renderResultsDetail() : '<p class="muted" style="margin-top:8px">La classifica si popola quando l\'admin calcola le giornate.</p>');
}
function renderResultsDetail(){
  const md = Math.max.apply(null, S.results.map(r => r.matchday));
  const rs = S.results.filter(r => r.matchday === md).sort((a, b) => b.total - a.total);
  return '<h3>Ultima giornata calcolata: '+md+'</h3><div class="grid">' + rs.map(r => {
    const d = r.detail || {}, pl = d.players || [];
    return '<div class="card"><h2>'+esc(memberName(r.user_id))+' <span class="muted">'+Number(r.total).toFixed(1)+' · '+r.goals+' gol</span></h2>' +
      (d.lineup === false ? '<div class="muted">Formazione non inviata</div>' : '<table><tbody>' + pl.map(p => {
        const x = playersById[p.player_id] || { name: '#'+p.player_id }, sub = p.sub ? (playersById[p.sub] || { name: '#'+p.sub }) : null;
        return '<tr><td>'+roleTag(p.role)+'</td><td>'+esc(x.name)+(sub ? ' → '+esc(sub.name) : '')+'</td><td>'+(p.voto == null ? 's.v.' : Number(p.voto).toFixed(1))+'</td><td><b>'+Number(p.fv).toFixed(1)+'</b></td></tr>'; }).join('') +
        (d.mod_difesa ? '<tr><td></td><td>Modificatore difesa</td><td></td><td><b>+'+d.mod_difesa+'</b></td></tr>' : '') + '</tbody></table>') + '</div>';
  }).join('') + '</div>';
}

/* ---------- avvio ---------- */
async function init(){
  if (!CFG.SUPABASE_URL || CFG.SUPABASE_URL.includes('INSERISCI')) { msg('FantaTB non è ancora configurato (fanta/config.js).', 'err'); show('regole'); return; }
  sb = window.supabase.createClient(CFG.SUPABASE_URL, CFG.SUPABASE_ANON_KEY);
  await Promise.all([loadPlayers(), loadMatchdays()]);
  await initAuth();
  const m = location.hash.match(/^#lega\/([0-9a-f-]{36})$/);
  if (m && user) openLeague(m[1]);
}
init().catch(err);
})();
