// Crewcut 2D motion helpers (window.M). Everything is a pure function of the frame number f.
// Motion values come from window.BRAND.motion (the style pack's brand.json "motion") with calm neutral defaults.
// Colours are never written here: elements use the CSS variables from base.css.
(function(){
'use strict';
const BM=(window.BRAND&&window.BRAND.motion)||{},BE=(window.BRAND&&window.BRAND.edit)||{};
const num=(v,d)=>(typeof v==='number'&&isFinite(v))?v:d;
const M={FPS:25};
M.clamp=(v,a=0,b=1)=>Math.min(b,Math.max(a,v));
M.lerp=(a,b,t)=>a+(b-a)*t;
// cubic-bezier as in CSS
M.bezier=function(x1,y1,x2,y2){
  const bx=t=>3*(1-t)*(1-t)*t*x1+3*(1-t)*t*t*x2+t*t*t, by=t=>3*(1-t)*(1-t)*t*y1+3*(1-t)*t*t*y2+t*t*t;
  return x=>{if(x<=0)return 0;if(x>=1)return 1;let a=0,b=1;for(let i=0;i<40;i++){const m=(a+b)/2;if(bx(m)<x)a=m;else b=m;}return by((a+b)/2);};
};
const EASE=Array.isArray(BM.ease)&&BM.ease.length===4?BM.ease.map(Number):[0.22,1,0.36,1];
M.ease=M.bezier(EASE[0],EASE[1],EASE[2],EASE[3]);
M.out3=t=>1-Math.pow(1-M.clamp(t),3);
M.prog=(f,start,dur)=>M.clamp((f-start)/Math.max(1e-6,dur));

// Motion tokens (frames at 25 fps). Neutral defaults: calm, no drift, no decor.
M.ENTER=num(BM.entrance_frames,10);       // frames for an element to appear
M.FROM=num(BM.entrance_from,0.94);        // scale it appears from
M.STAGGER=num(BM.stagger_frames,6);       // frames between parts that appear one after the other
M.EXIT=num(BM.exit_frames,6);             // frames to leave (keyword)
M.DRIFT=num(BM.drift_per_s,0);            // slow growth per second after the entrance; 0 = stands still
M.COUNTER=num(BM.counter_frames,30);      // frames a counter rolls
M.DIGIT=num(BM.digit_stagger_frames,3);   // frames between digits locking in
M.MARK=num(BM.mark_frames,12);            // frames the highlight needs to run over a phrase
M.DECOR=String(BM.decor||'none');         // none | shapes | float
M.MIN_TEXT=num(BE.min_text_px,40);        // smallest visible text in px (edit-style.json min_text_px)
M.text=px=>Math.max(M.MIN_TEXT,Math.round(px));

// Entrance: {o,s,p}; done at start+dur.
M.enter=(f,start,dur=M.ENTER,from=M.FROM)=>{const p=M.ease(M.prog(f,start,dur));return{o:p,s:from+(1-from)*p,p};};
// Exit: 0 before end-dur, 1 at end.
M.leave=(f,end,dur=M.EXIT)=>M.ease(M.prog(f,end-dur,dur));
M.drift=(f,perS=M.DRIFT)=>1+perS*f/M.FPS;
// Place an element with class .center/.chip/.card-frame/.frame: offset, scale, rotation, opacity
M.set=(el,{x=0,y=0,s=1,r=0,o=1}={})=>{
  el.style.transform=`translate(-50%,-50%) translate(${x.toFixed(3)}px,${y.toFixed(3)}px) rotate(${r.toFixed(3)}deg) scale(${s.toFixed(5)})`;
  el.style.opacity=M.clamp(o).toFixed(4);
};
M.scaleLayer=(el,s,o=1)=>{el.style.transform=`scale(${s.toFixed(5)})`;el.style.opacity=String(o);};
// Deterministic random numbers (mulberry32)
M.rng=seed=>()=>{seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};
M.el=(tag,cls,parent,html)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(html!=null)e.innerHTML=html;if(parent)parent.appendChild(e);return e;};
M.at=(el,x,y)=>{el.style.left=x+'px';el.style.top=y+'px';return el;};
M.esc=t=>String(t??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// A colour from the CSS variables (for SVG strokes or canvas): name without --c-, e.g. 'accent'
M.color=name=>getComputedStyle(document.documentElement).getPropertyValue('--c-'+name).trim()||'#000';

// Chip (text is escaped here)
M.chip=(parent,text,variant='')=>M.el('div','chip '+variant,parent,M.esc(text));
// Marker over a phrase: <span class="mark"><span>text</span></span>; p from 0 to 1
M.marker=(el,p)=>el.style.setProperty('--p',M.clamp(p).toFixed(4));

// Rolling counter. text e.g. "15,000"; digits roll for `frames` frames and lock in from left to right.
// update(f,end): the last digit stands at frame `end`. Each column gets a vertical motion blur while it rolls.
let rollId=0;
M.counter=function(el,text,o={}){
  el.classList.add('roll');const dur=o.frames||M.COUNTER,stagger=o.stagger??M.DIGIT,cols=[];
  const defs=M.el('div','',document.body,'');defs.style.cssText='position:absolute;width:0;height:0;overflow:hidden';
  [...String(text)].forEach(ch=>{
    if(!/\d/.test(ch)){M.el('span','roll-fixed',el,ch===' '?'&nbsp;':M.esc(ch));return;}
    const id='rollblur'+(rollId++);
    defs.insertAdjacentHTML('beforeend',`<svg width="0" height="0"><filter id="${id}" x="-20%" y="-5%" width="140%" height="110%"><feGaussianBlur stdDeviation="0 0"/></filter></svg>`);
    const c=M.el('span','roll-col',el,`<span class="roll-size">${ch}</span>`);let band='';for(let k=0;k<21;k++)band+=`<span>${k%10}</span>`;
    const b=M.el('span','roll-band',c,band);cols.push({c,b,target:+ch,blur:defs.querySelector('#'+id+' feGaussianBlur'),id});
  });
  const n=cols.length;
  const pos=(i,f,end,start)=>{const lock=end-(n-1-i)*stagger,p=M.clamp((f-start)/Math.max(1,lock-start));return cols[i].target+(o.turns||(10+i*2))*(1-M.out3(p));};
  return{cols,
    update(f,end){const start=end-(n-1)*stagger-dur;
      cols.forEach((c,i)=>{const p=pos(i,f,end,start),v=Math.abs(p-pos(i,f-1,end,start));
        const h=c.c.offsetHeight;const m=((p%10)+10)%10;
        c.b.style.transform=`translateY(${(-m*h).toFixed(2)}px)`;
        const sd=Math.min(v*h*0.2,h*0.18);if(c.blur)c.blur.setAttribute('stdDeviation','0 '+sd.toFixed(2));c.b.style.filter=sd>0.3?`url(#${c.id})`:'none';});
      return{start,locked:f>=end};}};
};

// Decor shape (only used when BRAND.motion.decor asks for it). type ring|plus|square|bar|dot; colour = currentColor (accent).
M.shape=function(parent,o){
  const g=o.g,d=o.thick||g*0.22;let inner='';
  if(o.type==='ring')inner=`<circle cx="${g/2}" cy="${g/2}" r="${(g-d)/2}" fill="none" stroke="currentColor" stroke-width="${d}"/>`;
  else if(o.type==='plus')inner=`<rect x="0" y="${(g-d)/2}" width="${g}" height="${d}" fill="currentColor"/><rect x="${(g-d)/2}" y="0" width="${d}" height="${g}" fill="currentColor"/>`;
  else if(o.type==='square')inner=`<rect x="${d/2}" y="${d/2}" width="${g-d}" height="${g-d}" fill="none" stroke="currentColor" stroke-width="${d}"/>`;
  else if(o.type==='bar')inner=`<rect x="0" y="${(g-d)/2}" width="${g}" height="${d}" rx="${d/2}" fill="currentColor"/>`;
  else inner=`<circle cx="${g/2}" cy="${g/2}" r="${g/2}" fill="currentColor"/>`;
  const el=M.el('div','decor-shape',parent,`<svg width="${g}" height="${g}" viewBox="0 0 ${g} ${g}" style="overflow:visible;display:block">${inner}</svg>`);
  M.at(el,o.x,o.y);if(o.blur)el.style.filter=`blur(${o.blur}px)`;const alpha=o.alpha??1;
  return{el,update(f){const t=f/M.FPS,a=M.enter(f,o.delay||0,M.ENTER*1.5,0.8);
    M.set(el,{x:(o.vx||0)*t,y:(o.vy||0)*t,r:(o.rot||0)+(o.vr||0)*t,s:a.s,o:alpha*a.o});}};
};

// Small floating bits in three depths that drift toward the camera (decor "float").
// o: seed, W, H, avoid [[x0,y0,x1,y1],...] (no bit overlaps these), center [x,y] (vanishing point)
M.DEPTHS=[{n:9,g:[14,26],blur:1,v:0.01,rise:4,alpha:0.5},{n:6,g:[40,64],blur:0,v:0.035,rise:10,alpha:0.85},{n:3,g:[110,160],blur:8,v:0.09,rise:24,alpha:0.9}];
M.floaters=function(parent,o){const r=M.rng(o.seed||11),T=[],[cx,cy]=o.center||[o.W/2,o.H/2];
  const blocked=(x,y,g)=>(o.avoid||[]).some(z=>x+g/2>z[0]&&x-g/2<z[2]&&y+g/2>z[1]&&y-g/2<z[3]);
  M.DEPTHS.forEach((l,li)=>{for(let i=0;i<l.n;i++){let x,y,g,tries=0;
    do{g=l.g[0]+r()*(l.g[1]-l.g[0]);x=r()*o.W;y=r()*o.H;tries++;}while(tries<600&&(blocked(x,y,g)||T.some(t=>Math.hypot(t.x-x,t.y-y)<(t.g+g)*0.8+40)));
    if(tries>=600)continue;
    const e=M.at(M.el('div','decor-bit',parent),x,y);e.style.width=e.style.height=g+'px';
    e.style.background=r()<0.6?'var(--c-accent)':'var(--c-highlight)';if(l.blur)e.style.filter=`blur(${l.blur}px)`;
    T.push({e,x,y,g,l,rot:(r()-0.5)*40,vr:(r()-0.5)*(3+li*4),start:-8+Math.floor(r()*6)});}});
  return{bits:T,update(f){const t=f/M.FPS;T.forEach(k=>{const a=M.enter(f,k.start,M.ENTER,0.6),z=1+k.l.v*t;
    M.set(k.e,{x:(k.x-cx)*(z-1),y:(k.y-cy)*(z-1)-k.l.rise*t,s:a.s*z,r:k.rot+k.vr*t,o:a.o*k.l.alpha});});}};
};

// Person symbol in a circle (outline) or filled with the accent
M.person=(g,filled=false)=>{const fg=filled?'var(--c-accent-ink)':'var(--c-accent)',bg=filled?'var(--c-accent)':'var(--card)';
  return `<svg width="${g}" height="${g}" viewBox="0 0 48 48" style="display:block;overflow:visible"><circle cx="24" cy="24" r="21.5" style="fill:${bg};stroke:var(--c-accent)" stroke-width="3"/><circle cx="24" cy="19" r="6.2" fill="none" style="stroke:${fg}" stroke-width="3"/><path d="M12.5 37.5c1.8-6 6-9 11.5-9s9.7 3 11.5 9" fill="none" style="stroke:${fg}" stroke-width="3" stroke-linecap="round"/></svg>`;};
M.dot=(g,filled=false)=>`<svg width="${g}" height="${g}" viewBox="0 0 48 48" style="display:block;overflow:visible"><circle cx="24" cy="24" r="21.5" style="fill:${filled?'var(--c-accent)':'var(--card)'};stroke:var(--c-accent)" stroke-width="3"/></svg>`;
M.square=(g,filled=false)=>`<svg width="${g}" height="${g}" viewBox="0 0 48 48" style="display:block;overflow:visible"><rect x="3" y="3" width="42" height="42" rx="9" style="fill:${filled?'var(--c-accent)':'var(--card)'};stroke:var(--c-accent)" stroke-width="3"/></svg>`;

// Register the scene: window.FRAMES and window.setFrame(n)
M.register=function(o){window.FRAMES=o.frames;window.setFrame=n=>{o.frame(Math.max(0,Math.min(o.frames-1,n|0)));return true;};window.setFrame(0);};
window.M=M;
})();
