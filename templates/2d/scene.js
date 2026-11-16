// Crewcut 2D scene frame: shared base of every scene in templates/2d/. Needs motion.js (window.M) first.
// A scene calls SCENE(EXAMPLE, S => { ... S.start(f => { ... }) }).
// Data: window.DATA (set by tools/render_html.js --data). Without DATA, or with DATA.example === true, the scene's
// EXAMPLE is used (DATA keys then override single example keys, e.g. {"example": true, "format": "portrait"}).
// Brand: window.BRAND (tools/render_html.js --brand tokens.json, from crewcut.brand.Pack.render_tokens()).
// The scene builds only after its fonts are loaded (widths are measured); window.SCENE_READY is that promise and the
// renderer waits for it. Data keys of every scene: templates/2d/BLOCKS.md.
window.SCENE=function(example,build){
  'use strict';
  const M=window.M,BRAND=window.BRAND||{},RAW=window.DATA;
  const D=Object.assign({},(!RAW||RAW.example)?(example||{}):{},RAW||{});
  const portrait=D.format==='portrait',W=portrait?1080:1920,H=portrait?1920:1080;
  const root=document.documentElement,body=document.body;
  let stage=document.getElementById('stage');
  if(!stage){stage=document.createElement('div');stage.id='stage';body.appendChild(stage);}
  // brand tokens as CSS variables on :root
  for(const[k,v]of Object.entries(BRAND.css||{})){if(v!=null&&v!=='')root.style.setProperty(k,String(v));}
  [root,body,stage].forEach(e=>{e.style.width=W+'px';e.style.height=H+'px';});
  root.classList.add(portrait?'portrait':'landscape');
  if(window.TRANSPARENT)root.classList.add('transparent');
  M.FPS=Number(D.fps)||25;
  const frames=Math.max(1,parseInt(D.frames||(example&&example.frames)||75,10));
  const S={M,D,B:stage,portrait,landscape:!portrait,W,H,frames,seed:D.seed,info:{},brand:BRAND};
  window.SCENE_INFO=S.info;window.FRAMES=frames;
  // Cue: frame number for a name; when missing, `fallback` (may be null).
  S.cue=(name,fallback=null)=>{const c=D.cues&&D.cues[name];return typeof c==='number'&&isFinite(c)?c:fallback;};
  // Fine values: the scene's defaults, overridden by DATA.fine (optional, for special cases).
  S.fine=defaults=>Object.assign({},defaults,D.fine||{});
  S.esc=M.esc;
  // A layer as large as the stage; it carries the drift. Origin in stage pixels.
  S.layer=(ox=W/2,oy=H/2,parent=stage)=>{const E=M.el('div','layer',parent);E.style.width=W+'px';E.style.height=H+'px';E.style.transformOrigin=ox+'px '+oy+'px';return E;};
  // Chip size: {height,size,spacing(em),pad,radius}
  S.chipStyle=(el,o)=>{if(o.height)el.style.height=o.height+'px';if(o.size)el.style.fontSize=o.size+'px';if(o.spacing!=null)el.style.letterSpacing=o.spacing+'em';
    if(o.pad!=null)el.style.padding='0 '+o.pad+'px';if(o.radius!=null)el.style.borderRadius=o.radius+'px';return el;};
  // Shrink a chip proportionally until it is at most `max` wide.
  S.chipFit=(el,o,max)=>{S.chipStyle(el,o);const w=el.offsetWidth;if(w<=max)return o;const t=max/w,n={};
    for(const k of['height','size','pad','radius'])if(o[k]!=null)n[k]=Math.floor(o[k]*t*10)/10;
    if(n.size!=null&&n.size<M.MIN_TEXT){const r=M.MIN_TEXT/n.size;n.size=M.MIN_TEXT;if(n.height!=null)n.height=Math.round(n.height*r);}   // never below the minimum text size
    S.chipStyle(el,n);return Object.assign({},o,n);};
  // Decor: only when the pack asks for it (BRAND.motion.decor), or DATA.decor overrides it for one insert.
  // avoid: [[x0,y0,x1,y1],...] content boxes the floating bits keep out of.
  S.decor=(o={})=>{const kind=String(D.decor||M.DECOR);if(window.TRANSPARENT||kind==='none')return{update(){}};
    const L=S.layer();const u=Math.min(W,H)/1080;
    if(kind==='shapes'){
      const set=portrait?
        [{type:'ring',x:60,y:220,g:420*u,thick:96*u,vx:4,vy:3,alpha:0.9},{type:'bar',x:W-40,y:H-240,g:620*u,thick:120*u,rot:-30,vx:-4,vy:-2,alpha:0.9},{type:'plus',x:W-150,y:300,g:120*u,thick:36*u,rot:15,vr:1.2,vx:-2,vy:3,alpha:0.9,delay:2}]:
        [{type:'ring',x:90,y:110,g:380*u,thick:86*u,vx:4,vy:3,alpha:0.9},{type:'bar',x:W-120,y:H-60,g:560*u,thick:110*u,rot:-30,vx:-4,vy:-2,alpha:0.9},{type:'plus',x:150,y:H-150,g:110*u,thick:34*u,rot:15,vr:1.2,vx:2,vy:-3,alpha:0.9,delay:2}];
      const parts=set.map(s=>M.shape(L,s));return{update(f){parts.forEach(p=>p.update(f));}};
    }
    if(kind==='float'){
      const avoid=(o.avoid||[[W*0.22,H*0.2,W*0.78,H*0.8]]).concat(S.logoBox?[S.logoBox]:[]);
      return M.floaters(L,{seed:S.seed??17,W,H,avoid,center:[W/2,H/2]});
    }
    return{update(){}};
  };
  // Logo: only when the pack has one (BRAND.logo.file) and places it; never on transparent overlays; DATA.logo=false hides it.
  const LOGO=BRAND.logo||{};
  const place=String(LOGO.placement||'none');
  S.logoBox=null;
  if(LOGO.file&&place!=='none'&&!window.TRANSPARENT&&D.logo!==false){
    const size=Number(LOGO.size)||54,mx=Math.round(Math.min(W,H)*0.045),my=Math.round(Math.min(W,H)*0.04);
    const right=place.endsWith('right'),bottom=place.startsWith('bottom');
    S.logoBox=[right?W-mx-size*4:0,bottom?H-my-size*1.6:0,right?W:mx+size*4,bottom?H:my+size*1.6];
    S._logo=()=>{const el=M.el('div','brand-logo',stage,'<img alt="" src="'+M.esc(fileUrl(LOGO.file))+'">'+(LOGO.text?'<span>'+M.esc(LOGO.text)+'</span>':''));
      el.querySelector('img').style.height=size+'px';
      el.style[right?'right':'left']=mx+'px';el.style[bottom?'bottom':'top']=my+'px';};
  }
  S.start=frame=>{if(S._logo)S._logo();M.register({frames,frame});};
  window.SCENE_READY=loadFonts(BRAND).then(()=>{build(S);return true;});
  return S;
};
// Absolute paths from the brand tokens become file:// URLs (the page itself is a file:// page).
function fileUrl(p){p=String(p);if(/^[a-z]+:\/\//i.test(p))return p;return 'file://'+encodeURI(p.startsWith('/')?p:'/'+p);}
// Pack font files (BRAND.fonts.<role>.files) are added as FontFace; system fonts (Inter in the image) are just loaded.
// A file that fails to load stays in document.fonts with status "error"; the renderer reports it and fails the run.
function loadFonts(BRAND){
  const jobs=[],seen=new Set();
  for(const[role,spec]of Object.entries(BRAND.fonts||{})){
    if(!spec||!spec.family)continue;const fam=String(spec.family),w=String(spec.weight||400);
    for(const file of(spec.files||[])){
      const key=fam+'|'+w+'|'+file;if(seen.has(key))continue;seen.add(key);
      try{const ff=new FontFace(fam,'url("'+fileUrl(file)+'")',{weight:w});document.fonts.add(ff);jobs.push(ff.load().catch(()=>null));}
      catch(e){/* reported by the renderer */}
    }
    if(role!=='mono')jobs.push(document.fonts.load(w+' 40px "'+fam+'"').catch(()=>null));
  }
  if(!BRAND.fonts){jobs.push(document.fonts.load('800 40px "Inter"').catch(()=>null),document.fonts.load('500 40px "Inter"').catch(()=>null));}
  return Promise.all(jobs).then(()=>document.fonts.ready).catch(()=>null);
}
