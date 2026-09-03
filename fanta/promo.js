/* FantaTB — banner promozionali (testata + laterali) per tutte le pagine di TransferBeat.
   Inclusione: <script src="/fanta/promo.js" defer></script>. Lingua da localStorage tb_lang o <html lang>. */
(function(){
  if (location.pathname.indexOf('/fanta/') === 0) return;          // dentro l'app niente banner
  var lang = (localStorage.getItem('tb_lang') || document.documentElement.lang || 'it').slice(0,2);
  var T = {
    it: {kicker:'IL FANTACALCIO DI TRANSFERBEAT', h:'FantaTB è gratis. Per sempre.', p:'Asta live dal telefono, regole su misura, voti statistici trasparenti, risultati partita per partita.', cta:'Crea la tua lega ora', side1:'Asta live con gli amici', side2:'Regole e modificatori su misura', side3:'Voti e infortuni ogni giornata', more:'Scopri FantaTB', close:'Chiudi'},
    en: {kicker:'TRANSFERBEAT FANTASY FOOTBALL', h:'FantaTB is free. Forever.', p:'Live auction from your phone, custom rules, transparent statistical ratings, match-by-match results.', cta:'Create your league now', side1:'Live auction with friends', side2:'Custom rules and modifiers', side3:'Ratings and injuries every week', more:'Discover FantaTB', close:'Close'},
    es: {kicker:'EL FANTASY DE TRANSFERBEAT', h:'FantaTB es gratis. Para siempre.', p:'Subasta en vivo desde el móvil, reglas a medida, votos estadísticos transparentes, resultados partido a partido.', cta:'Crea tu liga ahora', side1:'Subasta en vivo con amigos', side2:'Reglas y modificadores a medida', side3:'Votos y lesiones cada jornada', more:'Descubre FantaTB', close:'Cerrar'}
  }[lang] || null;
  if (!T) T = arguments.callee ? null : null;
  T = T || {kicker:'IL FANTACALCIO DI TRANSFERBEAT', h:'FantaTB è gratis. Per sempre.', p:'', cta:'Crea la tua lega ora', side1:'', side2:'', side3:'', more:'Scopri FantaTB', close:'Chiudi'};
  var base = (location.pathname.indexOf('/articoli/') === 0) ? '/' : '';   // le pagine articolo stanno due livelli sotto
  var landing = base + 'fantatb.html?lang=' + lang, app = landing;
  var css = '.tbp-top{background:linear-gradient(100deg,#ff2e88,#ff7a1a 55%,#ffd400);color:#1b1140;font-family:"Segoe UI",system-ui,sans-serif;position:relative}'+
    '.tbp-top .w{max-width:1180px;margin:0 auto;padding:12px 56px 12px 18px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}'+
    '.tbp-top .k{font-size:10px;font-weight:800;letter-spacing:1.2px;opacity:.85}.tbp-top .h{font-family:Georgia,serif;font-size:20px;font-weight:700;line-height:1.1}'+
    '.tbp-top .p{font-size:12.5px;opacity:.92;max-width:520px}.tbp-top .t{flex:1;min-width:240px}'+
    '.tbp-top .cta{background:#1b1140;color:#fff;font-weight:800;font-size:14px;padding:10px 18px;border-radius:8px;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.25)}'+
    '.tbp-top .cta:hover{background:#000}.tbp-top .more{font-size:12px;color:#1b1140;font-weight:700;text-decoration:underline;white-space:nowrap}'+
    '.tbp-top .cover{position:absolute;inset:0;z-index:1}.tbp-top .w{position:relative;z-index:2;pointer-events:none}.tbp-top .w a{pointer-events:auto}'+
    '.tbp-top .x{position:absolute;z-index:3;right:14px;top:10px;background:rgba(27,17,64,.35);color:#fff;border:0;border-radius:50%;width:26px;height:26px;cursor:pointer;font-size:14px;line-height:26px;text-align:center}'+
    '.tbp-side{position:fixed;top:120px;width:150px;background:linear-gradient(180deg,#ff2e88,#ff7a1a 60%,#ffd400);color:#1b1140;border-radius:12px;padding:16px 12px;font-family:"Segoe UI",system-ui,sans-serif;text-align:center;box-shadow:0 6px 20px rgba(0,0,0,.18);z-index:50;display:none}'+
    '.tbp-side.l{left:calc(50% - 590px - 170px)}.tbp-side.r{right:calc(50% - 590px - 170px)}'+
    '@media(min-width:1540px){.tbp-side{display:block}}'+
    '.tbp-side .logo{font-family:Georgia,serif;font-size:22px;font-weight:700;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.25)}.tbp-side .logo b{color:#1b1140}'+
    '.tbp-side .k{font-size:9px;font-weight:800;letter-spacing:1px;opacity:.8;margin-top:2px}'+
    '.tbp-side ul{list-style:none;padding:0;margin:14px 0;text-align:left;font-size:12px;line-height:1.35}.tbp-side li{margin:8px 0;padding-left:16px;position:relative}.tbp-side li:before{content:"✓";position:absolute;left:0;color:#1b1140;font-weight:800}'+
    '.tbp-side{cursor:pointer}.tbp-side .cta{display:block;background:#1b1140;color:#fff;font-weight:800;font-size:12.5px;padding:9px 6px;border-radius:8px;margin-top:8px}.tbp-side .cta:hover{background:#000}'+
    '.tbp-side .free{display:inline-block;background:#1b1140;color:#ffd400;font-size:10px;font-weight:900;padding:2px 8px;border-radius:10px;margin-top:10px}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  var side = function(cls){ return '<a class="tbp-side '+cls+'" href="'+landing+'"><div class="logo">Fanta<b>TB</b></div><div class="k">'+esc(T.kicker)+'</div><ul><li>'+esc(T.side1)+'</li><li>'+esc(T.side2)+'</li><li>'+esc(T.side3)+'</li></ul><span class="cta">'+esc(T.cta)+'</span><span class="free">100% GRATIS</span></a>'; };
  var top = '<div class="tbp-top" id="tbpTop"><a class="cover" href="'+landing+'" aria-label="FantaTB"></a><div class="w"><div class="t"><div class="k">'+esc(T.kicker)+'</div><div class="h">'+esc(T.h)+'</div><div class="p">'+esc(T.p)+'</div></div><a class="cta" href="'+app+'">'+esc(T.cta)+'</a><a class="more" href="'+landing+'">'+esc(T.more)+' →</a></div><button class="x" title="'+esc(T.close)+'" aria-label="'+esc(T.close)+'">×</button></div>';
  var anchor = document.querySelector('nav') || document.querySelector('header');
  var wrap = document.createElement('div'); wrap.innerHTML = top;
  if (anchor && anchor.parentNode) { var after = anchor.closest('header') || anchor; after.parentNode.insertBefore(wrap.firstChild, after.nextSibling); } else document.body.insertBefore(wrap.firstChild, document.body.firstChild);
  if (sessionStorage.getItem('tbp_closed')) { var t0 = document.getElementById('tbpTop'); if (t0) t0.style.display = 'none'; }
  var x = document.querySelector('#tbpTop .x'); if (x) x.onclick = function(){ document.getElementById('tbpTop').style.display = 'none'; try { sessionStorage.setItem('tbp_closed', '1'); } catch(e) {} };
  var s = document.createElement('div'); s.innerHTML = side('l') + side('r'); while (s.firstChild) document.body.appendChild(s.firstChild);
})();
