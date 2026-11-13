const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const ts=require(process.env.GUARDIAN_TYPESCRIPT_PATH||'typescript');
const code=ts.transpileModule(fs.readFileSync('entry/src/main/ets/common/CameraFrameClient.ets','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
function setup({status=200,sequence='9',size=100,decodeError=false,networkError=false,pending=false}={}){
 let destroyed=0,released=0,decoded=0,requests=0,rejectPending;const pixels={};
 const native={createHttp:()=>({request:async(_url,options)=>{requests++;assert.equal(options.usingCache,false);assert.equal(options.connectTimeout,1500);assert.equal(options.readTimeout,1500);if(pending)return new Promise((_,reject)=>rejectPending=reject);if(networkError)throw Error('network');return {responseCode:status,header:{'x-camera-sequence':sequence},result:new ArrayBuffer(size)};},destroy:()=>{destroyed++;if(rejectPending)rejectPending(Error('cancelled'));}}),RequestMethod:{GET:'GET'},HttpDataType:{ARRAY_BUFFER:1}};
 const image={createImageSource:()=>({createPixelMap:async()=>{decoded++;if(decodeError)throw Error('decode');return pixels;},release:async()=>released++})};
 const exports={};vm.runInNewContext(code,{exports,require:name=>name==='@ohos.net.http'?{default:native}:{image},ArrayBuffer,Date,Error});
 return {client:new exports.CameraFrameClient(),pixels,counts:()=>({destroyed,released,decoded,requests})};
}
test('valid bytes decode to native pixels and release network/source resources',async()=>{const h=setup();const frame=await h.client.fetch('https://example/frame','');assert.equal(frame.pixels,h.pixels);assert.equal(frame.sequence,'9');assert.deepEqual(h.counts(),{destroyed:1,released:1,decoded:1,requests:1});});
test('duplicate sequence does not decode again',async()=>{const h=setup();assert.equal(await h.client.fetch('url','9'),undefined);assert.equal(h.counts().decoded,0);assert.equal(h.counts().destroyed,1);});
test('204 waits for a new source frame without throwing or decoding an empty bitmap',async()=>{const h=setup({status:204});assert.equal(await h.client.fetch('url',''),undefined);assert.equal(h.counts().decoded,0);assert.equal(h.counts().destroyed,1);});
test('server errors remain recoverable errors rather than fresh frames',async()=>{const h=setup({status:503});await assert.rejects(h.client.fetch('url',''));assert.equal(h.counts().decoded,0);assert.equal(h.counts().destroyed,1);});
test('bad JPEG still releases both image source and HTTP request',async()=>{const h=setup({decodeError:true});await assert.rejects(h.client.fetch('url',''));assert.equal(h.counts().released,1);assert.equal(h.counts().destroyed,1);});
test('network failure releases request',async()=>{const h=setup({networkError:true});await assert.rejects(h.client.fetch('url',''));assert.equal(h.counts().destroyed,1);});
test('hidden/disposed view can cancel pending I/O',async()=>{const h=setup({pending:true});const promise=h.client.fetch('url','');h.client.cancel();await assert.rejects(promise,/cancelled/);assert.ok(h.counts().destroyed>=1);});
test('oversized response is rejected before native allocation',async()=>{const h=setup({size:1024*1024+1});await assert.rejects(h.client.fetch('url',''));assert.equal(h.counts().decoded,0);assert.equal(h.counts().destroyed,1);});
