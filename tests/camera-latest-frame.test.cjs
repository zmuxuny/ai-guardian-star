const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const ts=require(process.env.GUARDIAN_TYPESCRIPT_PATH||'typescript');
const source=fs.readFileSync('entry/src/main/ets/components/MjpegPage.ets','utf8');
const mod={exports:{}};
vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports:mod.exports});
const html=mod.exports.buildMjpegPage('/video_frame','cover');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
function harness(){
 const requests=[],timers=new Map(),revoked=[],events={},docEvents={};let id=0,urlId=0;
 const img={src:'',removeAttribute(){this.src='';}},tip={style:{}};
 const document={hidden:false,body:{dataset:{state:'connecting'}},getElementById:k=>k==='v'?img:tip,addEventListener:(k,v)=>docEvents[k]=v};
 const window={addEventListener:(k,v)=>events[k]=v};
 vm.runInNewContext(script,{document,window,AbortController,Date,Error,
  URL:{createObjectURL:()=>`blob:${++urlId}`,revokeObjectURL:u=>revoked.push(u)},
  setTimeout:(fn,ms)=>{timers.set(++id,{fn,ms});return id;},clearTimeout:k=>timers.delete(k),
  fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
 return {requests,timers,revoked,img,document,window,docEvents,
  fire(ms){const entry=[...timers].find(([,v])=>v.ms===ms);assert.ok(entry,`timer ${ms}`);timers.delete(entry[0]);entry[1].fn();},
  async frame(index=0){requests[index].resolve({status:200,blob:async()=>({size:100,type:'image/jpeg'})});await flush();}};
}
test('single request; next request waits for download AND image decode',async()=>{
 const h=harness();assert.equal(h.requests.length,1);assert.match(h.requests[0].url,/^\/video_frame\?t=/);assert.equal(h.requests[0].options.cache,'no-store');
 await h.frame();assert.equal(h.requests.length,1);assert.equal(h.document.body.dataset.state,'connecting');assert.ok(![...h.timers.values()].some(t=>t.ms===80));
 h.img.onload();assert.equal(h.document.body.dataset.state,'live');h.fire(80);assert.equal(h.requests.length,2);
});
test('request deadline aborts slow network and reconnects without a frame queue',()=>{
 const h=harness();h.fire(5000);assert.equal(h.requests[0].options.signal.aborted,true);h.fire(800);assert.equal(h.requests.length,2);
});
test('late completion from timed-out request cannot replace the current image',async()=>{
 const h=harness();h.fire(5000);h.fire(800);await h.frame(1);h.img.onload();const current=h.img.src;await h.frame(0);assert.equal(h.img.src,current);
});
test('camera offline / 204 retries without marking an empty response live',async()=>{
 const h=harness();h.requests[0].resolve({status:204});await flush();assert.equal(h.img.src,'');assert.equal(h.document.body.dataset.state,'connecting');h.fire(800);assert.equal(h.requests.length,2);
});
test('hidden preview cancels traffic; resume fetches a new current frame',async()=>{
 const h=harness();h.document.hidden=true;h.docEvents.visibilitychange();assert.equal(h.requests[0].options.signal.aborted,true);assert.equal(h.timers.size,0);
 await h.frame();assert.equal(h.img.src,'');h.document.hidden=false;h.docEvents.visibilitychange();h.fire(0);assert.equal(h.requests.length,2);
});
test('replacement and disposal release blob URLs and all timers',async()=>{
 const h=harness();await h.frame();h.img.onload();h.fire(80);await h.frame(1);h.img.onload();assert.deepEqual(h.revoked,['blob:1']);
 h.window.stopCameraPreview();assert.deepEqual(h.revoked,['blob:1','blob:2']);assert.equal(h.timers.size,0);assert.equal(h.img.src,'');
});
test('broken image keeps last good frame and enters reconnecting state',async()=>{
 const h=harness();await h.frame();h.img.onload();h.fire(80);await h.frame(1);h.img.onerror();assert.equal(h.img.src,'blob:1');assert.equal(h.document.body.dataset.state,'reconnecting');assert.deepEqual(h.revoked,['blob:2']);
});
