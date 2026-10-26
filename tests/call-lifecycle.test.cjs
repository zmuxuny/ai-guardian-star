// Offline checks against actual ArkTS methods; no microphone or network access.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require(process.env.GUARDIAN_TYPESCRIPT_PATH||'typescript');
function compile(source,requireMock){
  const m=new Module(__filename);
  m.require=requireMock;
  m._compile(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,__filename);
  return m.exports;
}
function audioHarness(mode='success'){
  const handlers=new Map();let stopped=0,released=0,closed=0,timeout;
  const unit=()=>({on(){},async start(){},async stop(){stopped++},async release(){released++}});
  const socket={on:(key,fn)=>handlers.set(key,fn),off:key=>handlers.delete(key),send:async()=>{},close:async()=>{closed++},
    connect:async()=>{if(mode==='false')return false;if(mode==='reject')throw Error('offline');if(mode==='timeout'){return new Promise(()=>{})}handlers.get('open')?.();return true;}};
  const audio={createAudioRenderer:async()=>unit(),createAudioCapturer:async()=>unit(),
    AudioSamplingRate:{SAMPLE_RATE_48000:48000},AudioChannel:{CHANNEL_1:1},AudioSampleFormat:{SAMPLE_FORMAT_S16LE:1},
    AudioEncodingType:{ENCODING_TYPE_RAW:1},StreamUsage:{STREAM_USAGE_MUSIC:1},SourceType:{SOURCE_TYPE_MIC:1}};
  const deps={'@ohos.multimedia.audio':{default:audio},'@ohos.net.webSocket':{default:{createWebSocket:()=>socket}},'@ohos.base':{},'@kit.ArkTS':{},'../config':{WS_INTERCOM_URL:'ws://offline.invalid'}};
  let code=fs.readFileSync(path.join(__dirname,'../entry/src/main/ets/common/AudioTransferManager.ets'),'utf8');
  if(mode==='timeout')code='const setTimeout=(fn,ms)=>{globalThis.__callTimeout=fn;return 1};const clearTimeout=()=>{};\n'+code;
  const manager=compile(code,key=>{assert.ok(key in deps,key);return deps[key]}).AudioTransferManager.getInstance();
  return {manager,handlers,counts:()=>({stopped,released,closed})};
}
test('connected call can end and releases both audio devices',async()=>{
  const h=audioHarness();await h.manager.startCall();assert.equal(h.manager.isCallActive(),true);
  await h.manager.stopCall();assert.equal(h.manager.isCallActive(),false);assert.deepEqual(h.counts(),{stopped:2,released:2,closed:1});
});
for(const mode of ['reject','false'])test('failed connection '+mode+' throws and releases audio',async()=>{
  const h=audioHarness(mode);await assert.rejects(h.manager.startCall(),/通话连接失败/);
  assert.equal(h.manager.isCallActive(),false);assert.equal(h.counts().released,2);
});
test('a pending connection times out and releases its audio devices',async()=>{
  const h=audioHarness('timeout');const pending=h.manager.startCall();
  for(let i=0;i<12;i++)await Promise.resolve();
  assert.equal(typeof globalThis.__callTimeout,'function');globalThis.__callTimeout();delete globalThis.__callTimeout;
  await assert.rejects(pending,/通话连接失败/);assert.equal(h.manager.isCallActive(),false);assert.equal(h.counts().released,2);
});
test('remote close resets state and releases audio resources',async()=>{
  const h=audioHarness();await h.manager.startCall();h.handlers.get('close')();
  for(let i=0;i<12;i++)await Promise.resolve();
  assert.equal(h.manager.isCallActive(),false);assert.equal(h.counts().released,2);
});

// Extract the actual event handler without compiling ArkUI's build DSL.
function pageHarness({online=true,granted=true,active=false,fail=false}={}){
  const source=fs.readFileSync(path.join(__dirname,'../entry/src/main/ets/pages/mainpage.ets'),'utf8');
  const begin=source.indexOf('  private async toggleCall()');
  let end=source.indexOf('{',begin),depth=1;
  while(depth){end++;if(source[end]==='{')depth++;else if(source[end]==='}')depth--;}
  const method=source.slice(begin,end+1);const counts={permissions:0,starts:0,stops:0,toasts:[]};let state=active;
  const dependencies={abilityAccessCtrl:{createAtManager:()=>({requestPermissionsFromUser:async()=>{counts.permissions++;return {authResults:[granted?0:-1]}}})},
    showToast:(_ui,options)=>counts.toasts.push(options.message)};
  const code='const {abilityAccessCtrl,showToast}=require("mocks");\nexport class Page {'+method+'\n}';
  const page=new (compile(code,()=>dependencies).Page)();
  Object.assign(page,{callBusy:false,isTalking:active,homeVisible:true,mqttManager:{deviceOnline:online},
    getUIContext:()=>({getHostContext:()=>({})}),audioManager:{isCallActive:()=>state,
      startCall:async()=>{counts.starts++;if(fail)throw Error('offline');state=true},stopCall:async()=>{counts.stops++;state=false}}});
  return {page,counts};
}
test('offline button does not request microphone permission or start a call',async()=>{
  const h=pageHarness({online:false});await h.page.toggleCall();assert.equal(h.counts.permissions,0);assert.equal(h.counts.starts,0);
  assert.match(h.counts.toasts[0],/设备未连接/);assert.equal(h.page.callBusy,false);
});
test('denied microphone permission leaves call stopped',async()=>{
  const h=pageHarness({granted:false});await h.page.toggleCall();assert.equal(h.counts.starts,0);assert.equal(h.page.isTalking,false);assert.match(h.counts.toasts[0],/麦克风权限/);
});
test('permission granted starts call and a second press hangs up',async()=>{
  const h=pageHarness();await h.page.toggleCall();assert.equal(h.page.isTalking,true);await h.page.toggleCall();
  assert.equal(h.page.isTalking,false);assert.equal(h.counts.starts,1);assert.equal(h.counts.stops,1);
});
test('failed start stays stopped and gives feedback',async()=>{
  const h=pageHarness({fail:true});await h.page.toggleCall();assert.equal(h.page.isTalking,false);assert.equal(h.page.callBusy,false);assert.match(h.counts.toasts[0],/连接失败/);
});
test('hangup still works if device heartbeat goes offline',async()=>{
  const h=pageHarness({active:true,online:false});await h.page.toggleCall();assert.equal(h.counts.stops,1);assert.equal(h.counts.permissions,0);
});
test('repeated press during a pending operation is ignored',async()=>{
  const h=pageHarness();h.page.callBusy=true;await h.page.toggleCall();assert.equal(h.counts.starts,0);assert.equal(h.counts.permissions,0);
});
test('leaving homepage during permission request does not start audio',async()=>{
  const h=pageHarness();const pending=h.page.toggleCall();h.page.homeVisible=false;await pending;assert.equal(h.counts.starts,0);
});
