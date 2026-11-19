#!/usr/bin/env node
// Deterministic frame renderer for Crewcut's 2D scenes (templates/2d/*.html).
// The page must expose window.setFrame(n): a pure function of the frame number (no clock, no CSS animation running on
// its own). setFrame may return a promise (a scene that shows clip frames); the renderer waits for it.
//
// Usage: node tools/render_html.js <scene.html> <out_dir> [--frames N] [--data file.json] [--brand tokens.json]
//                                  [--transparent] [--from A --to B] [--allow-font-fallback]
//   --frames N        total frames of the scene (0 ... N-1). Optional: else DATA.frames, else the scene's own count.
//   --data f.json     data for the scene, set as window.DATA before any page script runs.
//                     DATA.format "landscape" = 1920x1080 (default), "portrait" = 1080x1920.
//   --brand t.json    render tokens of the style pack (crewcut.brand.Pack.render_tokens()), set as window.BRAND;
//                     the page applies BRAND.css as CSS variables on :root.
//   --transparent     PNG with alpha (no stage background). Sets window.TRANSPARENT = true.
//   --from/--to       render only this range (inclusive), e.g. for a quick look; -1 is the last frame.
//   --allow-font-fallback   a missing brand font is a warning instead of an error.
// Output: <out_dir>/0000.png, 0001.png, ... and one JSON line on stdout.
// playwright-core comes from tools/node_modules or NODE_PATH; Chromium from env CHROMIUM_PATH when set.
'use strict';
const path=require('path'),fs=require('fs'),url=require('url');
const SIZES={landscape:[1920,1080],portrait:[1080,1920]};
const FLAGS=new Set(['transparent','allow-font-fallback','help']);
const USAGE='Usage: node tools/render_html.js <scene.html> <out_dir> [--frames N] [--data file.json] [--brand tokens.json] [--transparent] [--from A --to B]';

function fail(code,msg){console.error(msg);process.exit(code);}
function parse(argv){const pos=[],opt={};
  for(let i=0;i<argv.length;i++){const a=argv[i];
    if(a.startsWith('--')){const k=a.slice(2);if(FLAGS.has(k))opt[k]=true;else{if(i+1>=argv.length)fail(2,`--${k} needs a value\n${USAGE}`);opt[k]=argv[++i];}}
    else pos.push(a);}
  return{pos,opt};}
function readJson(p,what){try{return JSON.parse(fs.readFileSync(path.resolve(p),'utf8'));}catch(e){fail(2,`${what} not readable: ${p} (${e.message})`);}}
function int(v,name){const n=Number(v);if(!Number.isInteger(n))fail(2,`--${name} must be a whole number, got ${v}`);return n;}
function chromium(){
  for(const name of['playwright-core','playwright']){
    try{return require(name).chromium;}catch(e){if(e.code!=='MODULE_NOT_FOUND')throw e;}}
  fail(1,'playwright-core not found. Run "npm ci" in tools/ or set NODE_PATH to a node_modules folder that has it.');
}

const{pos,opt}=parse(process.argv.slice(2));
if(opt.help||pos.length<2)fail(2,USAGE);
const DATA=opt.data?readJson(opt.data,'Data'):null;
const BRAND=opt.brand?readJson(opt.brand,'Brand tokens'):null;
const format=(DATA&&DATA.format)||'landscape';
if(!SIZES[format])fail(2,'DATA.format must be "landscape" or "portrait", got '+JSON.stringify(format));
const[W,H]=SIZES[format];
const scene=path.resolve(pos[0]),out=path.resolve(pos[1]);
if(!fs.existsSync(scene))fail(2,'Scene not found: '+scene);

(async()=>{
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium().launch({executablePath:process.env.CHROMIUM_PATH||undefined,
    // --disable-dev-shm-usage: Docker's small /dev/shm crashes Chromium on big pages. CREWCUT_CHROMIUM_ARGS adds flags,
    // e.g. "--no-zygote --single-process --disable-gpu" under CPU emulation (QEMU) in CI.
    args:['--font-render-hinting=none','--disable-lcd-text','--force-color-profile=srgb','--disable-dev-shm-usage',
      ...(process.env.CREWCUT_CHROMIUM_ARGS||'').split(/\s+/).filter(Boolean)]});
  const close=async(code,msg)=>{if(msg)console.error(msg);await browser.close().catch(()=>{});process.exit(code);};
  const page=await browser.newPage({viewport:{width:W,height:H},deviceScaleFactor:1,locale:'en-US'});
  const errors=[];
  page.on('pageerror',e=>errors.push('Page error: '+String(e)));
  page.on('console',m=>{if(m.type()==='error')errors.push('Console error: '+m.text());});
  page.on('requestfailed',r=>errors.push('Not loaded: '+r.url()));
  const legacy=DATA&&DATA.scene_contract==='video-studio';
  if(legacy&&DATA.fps!=null&&DATA.fps!==25)await close(2,'Video Studio scenes require 25 fps; adapt their timing before using another rate.');
  await page.addInitScript(({d,b,t,legacy})=>{
    if(d)window.DATA=d;if(b)window.BRAND=b;if(t)window.TRANSPARENT=true;
    if(legacy)window.DATEN={...d,format:d.format==='portrait'?'hoch':'quer',bilder:d.frames};
  },{d:DATA,b:BRAND,t:!!opt.transparent,legacy});
  await page.goto(url.pathToFileURL(scene).href,{waitUntil:'load'});
  await page.evaluate(()=>document.fonts.ready);
  await page.evaluate(legacy=>legacy?window.SZENE_BEREIT:window.SCENE_READY||null,legacy);
  // images the scene adds while it builds (cards, logo) must be decoded before the first frame
  const broken=await page.evaluate(async()=>{const bad=[];await Promise.all([...document.images].map(i=>i.decode().catch(()=>bad.push(i.src))));return bad;});
  if(broken.length)errors.push('Image not loaded: '+broken.join(', '));
  const badFonts=await page.evaluate(()=>[...document.fonts].filter(f=>f.status==='error').map(f=>f.family+' '+f.weight));
  if(badFonts.length)errors.push('Font file not loaded: '+badFonts.join(', '));
  // A brand font that is neither a loaded file nor installed falls back silently in Chromium. Detect it by width.
  const families=[];
  for(const[role,spec]of Object.entries((BRAND&&BRAND.fonts)||{display:{family:'Inter',weight:800},body:{family:'Inter',weight:500}})){
    if(role!=='mono'&&spec&&spec.family&&!families.some(x=>x[0]===spec.family))families.push([String(spec.family),String(spec.weight||400)]);}
  const missing=await page.evaluate(fams=>{const c=document.createElement('canvas').getContext('2d'),s='mmmmmmmmmmlli 0123456789 WQ@';const out=[];
    for(const[fam,w]of fams){if(/^(system-ui|sans-serif|serif|monospace)$/i.test(fam))continue;let same=true;
      for(const base of['monospace','serif']){c.font=`${w} 40px ${base}`;const a=c.measureText(s).width;c.font=`${w} 40px "${fam}", ${base}`;
        if(Math.abs(c.measureText(s).width-a)>0.01){same=false;break;}}
      if(same)out.push(fam);}return out;},families);
  if(missing.length){const msg='Font not available: '+missing.join(', ')+'. Install it, or add the font file to the style pack (brand.json fonts.<role>.files).';
    if(opt['allow-font-fallback'])console.error('Warning: '+msg);else errors.push(msg);}
  if(!(await page.evaluate(()=>typeof window.setFrame==='function')))errors.push('window.setFrame is missing');
  if(errors.length)await close(1,errors.join('\n'));
  const pageFrames=await page.evaluate(legacy=>(legacy?window.BILDER:window.FRAMES)||null,legacy);
  const N=opt.frames!=null?int(opt.frames,'frames'):(DATA&&DATA.frames!=null?int(DATA.frames,'frames'):pageFrames);
  // negative values count from the end: --from -1 --to -1 is the last frame
  const at=(v,d)=>{if(v==null)return d;const n=int(v,'from/to');return n<0?(N||0)+n:n;};
  const from=at(opt.from,0),to=at(opt.to,(N||0)-1);
  if(!(N>0)||from<0||to>=N||from>to)await close(2,`Bad frame range: frames ${N}, from ${from}, to ${to}`);
  for(let n=from;n<=to;n++){
    await page.evaluate(n=>window.setFrame(n),n);
    await page.screenshot({path:path.join(out,String(n).padStart(4,'0')+'.png'),omitBackground:!!opt.transparent});
    if(errors.length)break;
  }
  if(errors.length)await close(1,errors.join('\n'));
  const info=await page.evaluate(legacy=>(legacy?window.SZENE_INFO:window.SCENE_INFO)||null,legacy);
  await browser.close();
  console.log(JSON.stringify({scene:path.basename(scene),out,format,size:`${W}x${H}`,transparent:!!opt.transparent,from,to,frames:to-from+1,info}));
})().catch(e=>{console.error(e&&e.stack||String(e));process.exit(1);});
