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
  const t = e.target.closest('[data-tab]'); if (t){ e.preventDefault(); $$('.tabs a').forEach(x => x.classList.toggle('on', x === t)); ['asta','rose','membri','regole'].forEach(k => $('#tab-'+k).classList.toggle('hidden', k !== t.dataset.tab)); }
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
  const { data, error } = await sb.from('players').select('id,name,team,role,price,active').eq('active', true).order('price', { ascending: false }).limit(2000);
  if (error) return err(error);
  players = data || []; playersById = {}; players.forEach(p => playersById[p.id] = p);
}
function roleTag(r){ return '<span class="role '+r+'">'+r+'</span>'; }
function renderListone(){
  const q = ($('#lsSearch').value || '').toLowerCase(); const r = $('#lsRole').value;
  const rows = players.filter(p => (!r || p.role === r) && (!q || p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q))).slice(0, 400);
  $('#lsTable').innerHTML = players.length ? '<table><thead><tr><th>R</th><th>Giocatore</th><th>Squadra</th><th>Quot.</th></tr></thead><tbody>' +
    rows.map(p => '<tr><td>'+roleTag(p.role)+'</td><td>'+esc(p.name)+'</td><td>'+esc(p.team)+'</td><td><b>'+p.price+'</b></td></tr>').join('') + '</tbody></table>'
    : '<div class="msg">Listone non ancora caricato. Arriva con il primo aggiornamento dei dati.</div>';
}
$('#lsSearch').oninput = renderListone; $('#lsRole').onchange = renderListone;

/* ---------- voti ---------- */
async function loadVoti(){
  const { data: days } = await sb.from('matchdays').select('number,status').eq('season', CFG.SEASON || 2026).order('number', { ascending: false });
  const sel = $('#vtDay');
  if (!days || !days.length){ sel.innerHTML = ''; $('#vtTable').innerHTML = '<div class="msg">Nessuna giornata calcolata finora.</div>'; return; }
  sel.innerHTML = days.map(d => '<option value="'+d.number+'">Giornata '+d.number+(d.status === 'rated' ? '' : ' (parziale)')+'</option>').join('');
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
const MEMBER_SEL = 'user_id, team_name, role, credits, call_order, profiles(username)';
async function openLeague(id){
  const [{ data: league, error: e1 }, { data: members, error: e2 }] = await Promise.all([
    sb.from('leagues').select('*').eq('id', id).single(),
    sb.from('league_members').select(MEMBER_SEL).eq('league_id', id).order('call_order')
  ]);
  if (e1 || e2) return err(e1 || e2);
  L = { league, members, rosters: [], auction: null, bids: [] };
  L.me = members.find(m => m.user_id === user.id); L.isAdmin = !!(L.me && L.me.role === 'admin');
  location.hash = 'lega/' + id;
  $$('main > section').forEach(s => s.classList.add('hidden')); $('#view-league').classList.remove('hidden');
  $('#lgName').textContent = league.name;
  $('#lgSub').innerHTML = esc(L.me.team_name)+' · '+members.length+'/'+(league.settings.max_teams || 20)+' squadre · codice invito <span class="code">'+esc(league.invite_code)+'</span>';
  await refreshLeagueData();
  renderRules(); renderAuction(); subscribe();
}
async function refreshLeagueData(){
  const [{ data: rosters }, { data: auction }, { data: members }, { data: bids }] = await Promise.all([
    sb.from('rosters').select('player_id, user_id, price').eq('league_id', L.league.id),
    sb.from('auctions').select('*').eq('league_id', L.league.id).single(),
    sb.from('league_members').select(MEMBER_SEL).eq('league_id', L.league.id).order('call_order'),
    sb.from('auction_bids').select('user_id, amount, player_id, created_at').eq('league_id', L.league.id).order('id', { ascending: false }).limit(10)
  ]);
  L.rosters = rosters || []; L.auction = auction; L.bids = bids || [];
  if (members) { L.members = members; L.me = members.find(m => m.user_id === user.id); }
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
    const rows = players.filter(p => !taken.has(p.id) && (!r || p.role === r) && (!q || p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q))).slice(0, 60);
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

/* ---------- avvio ---------- */
async function init(){
  if (!CFG.SUPABASE_URL || CFG.SUPABASE_URL.includes('INSERISCI')) { msg('FantaTB non è ancora configurato (fanta/config.js).', 'err'); show('regole'); return; }
  sb = window.supabase.createClient(CFG.SUPABASE_URL, CFG.SUPABASE_ANON_KEY);
  await loadPlayers();
  await initAuth();
  const m = location.hash.match(/^#lega\/([0-9a-f-]{36})$/);
  if (m && user) openLeague(m[1]);
}
init().catch(err);
})();
