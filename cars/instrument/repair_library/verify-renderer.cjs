// Exercise the actual Figment renderer with a real Canvas implementation.
// npm install --prefix OUTPUT/repaired/review/runtime @napi-rs/canvas
// node instrument/repair_library/verify-renderer.cjs OUTPUT [--pilot]
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const root = path.resolve(process.argv[2]);
const { createCanvas, loadImage } = require(path.join(root, 'repaired/review/runtime/node_modules/@napi-rs/canvas'));
const source = fs.readFileSync(path.join(__dirname, '../figment/highway.js'), 'utf8');
const ports = {};
const node = new Proxy({}, { get: (o, k) => o[k] || ((name, value) => ports[name] = { value, set() {} }) });
const sandbox = { node, OffscreenCanvas: function(w,h) { return createCanvas(w,h); }, performance, console };
vm.createContext(sandbox);
vm.runInContext(source + '\nthis.api = {repairedBox, drawRepaired, shifted, assignLanes, frameOf, draw, setContext(c){ctx=c;}, setMasks(m){laneMasks=m;}, setCars(v){cars=v;}, buildLaneMasks};', sandbox);
const api = sandbox.api;
async function main() {
  const pilot = process.argv.includes('--pilot');
  const manifest = pilot ? { clips: fs.readdirSync(path.join(root,'repaired/jobs')).flatMap(id => {
    const p=path.join(root,'repaired/jobs',id,'job.json'); if(!fs.existsSync(p))return [];
    const j=JSON.parse(fs.readFileSync(p));const mp=path.join(path.dirname(p),'motion.json');const boxes=fs.existsSync(mp)?JSON.parse(fs.readFileSync(mp)).boxes:j.boxes;
    return j.status==='ingested' ? [{...j.clip, cars:1, sheet:'repaired/clips/'+id+'.png', boxes, poses:j.poses}] : [];
  })} : JSON.parse(fs.readFileSync(path.join(root,'manifest-repaired.json')));
  const canvas=createCanvas(1920,1080), ctx=canvas.getContext('2d'); api.setContext(ctx);
  const plate=await loadImage(path.join(root,'plate.png'));
  const report={ clips:[], reverse:true, fractionalMotion:true, crossfadeOpaque:true };
  // A deliberately opaque fixture catches incorrect source-over crossfades.
  const fixture=createCanvas(20,10), fg=fixture.getContext('2d'); fg.fillStyle='red';fg.fillRect(0,0,10,10);fg.fillStyle='blue';fg.fillRect(10,0,10,10);
  api.drawRepaired({sheet:fixture,poses:[{frame:0,x:0,y:0,w:10,h:10},{frame:10,x:10,y:0,w:10,h:10}]},5,[0,415,10,10],1);
  const pixel=ctx.getImageData(5,420,1,1).data;assert.equal(pixel[3],255);assert(Math.abs(pixel[0]-pixel[2])<3);
  assert.equal(ctx.getImageData(5,416,1,1).data[3],0,'Bridge must occlude the vehicle');
  const masks=api.buildLaneMasks(1920,1080,1,.35,18);
  for(const c of manifest.clips) {
    const file=c.sheet;c.sheet=await loadImage(path.join(root,file));c.n=c.boxes.length;
    assert(c.n>1 && c.poses.length>=2);assert.equal(c.cars,1);
    for(const b of c.boxes)assert(b.every(Number.isFinite)&&b[2]>0&&b[3]>0);
    for(const p of c.poses)assert(p.x>=0&&p.y>=0&&p.x+p.w<=c.sheet.width&&p.y+p.h<=c.sheet.height);
    for(const pos of [0,.5,c.n*.25,c.n*.5,c.n*.75,c.n-1].reverse()) {
      ctx.clearRect(0,0,1920,1080);api.setMasks(null);
      const b=api.repairedBox(c,pos);api.drawRepaired(c,pos,b,1);
      assert.equal(api.frameOf({clip:c,pos:Math.min(pos,c.n-1)}),Math.round(Math.min(pos,c.n-1)));
    }
    const mid=api.repairedBox(c,.5);assert(Math.abs(mid[0]-(c.boxes[0][0]+c.boxes[1][0])/2)<1e-6);
    // Each output is also composited through the production lane mask.
    api.setMasks(masks);ctx.globalAlpha=1;ctx.drawImage(plate,0,0);
    const pos=(c.n-1)*.6;api.drawRepaired(c,pos,api.repairedBox(c,pos),1);
    fs.writeFileSync(path.join(root,'repaired/review',path.basename(file)),canvas.toBuffer('image/png'));
    const shifted=api.shifted(c,c.lane%4,1);assert.equal(shifted.poses,c.poses);assert.equal(shifted.n,c.n);
    report.clips.push({id:c.id,lane:c.lane,frames:c.n,poses:c.poses.length,width:c.sheet.width,height:c.sheet.height});
  }
  fs.writeFileSync(path.join(root,'repaired/review/renderer-verification.json'),JSON.stringify(report,null,2));
  if(process.argv.includes('--video')) {
    const choices=['lane1_f383_0183','lane2_f1753_0003','lane3_w107_0103','lane4_w107_0342'];
    const clips=choices.map(id=>manifest.clips.find(c=>'lane'+c.lane+'_'+c.id===id));
    assert(clips.every(Boolean),'Preview clips are missing');
    const ff=spawn('ffmpeg',['-y','-loglevel','error','-f','rawvideo','-pixel_format','rgba','-video_size','1920x1080','-framerate','25','-i','pipe:0','-an','-c:v','libx264','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',path.join(root,'repaired/review/repaired-library.mp4')],{stdio:['pipe','inherit','inherit']});
    const completion=once(ff,'close');
    for(let frame=0;frame<200;frame++) {
      ctx.globalAlpha=1;ctx.drawImage(plate,0,0);api.setMasks(masks);
      const active=clips.map(c=>({c,pos:(frame/199)*(c.n-1)}));
      active.sort((a,b)=>api.repairedBox(a.c,a.pos)[1]-api.repairedBox(b.c,b.pos)[1]);
      for(const {c,pos} of active)api.drawRepaired(c,pos,api.repairedBox(c,pos),1);
      const pixels=Buffer.from(ctx.getImageData(0,0,1920,1080).data);
      if(!ff.stdin.write(pixels))await once(ff.stdin,'drain');
    }
    ff.stdin.end();const [code]=await completion;assert.equal(code,0,'Video encoding failed');
  }
  console.log(JSON.stringify({tested:report.clips.length,opaqueCrossfade:true,fractionalMotion:true,reverse:true,laneMasks:true}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
