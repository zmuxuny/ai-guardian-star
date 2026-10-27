/**
 * 实时画面页面：用 fetch 逐帧读取 MJPEG，超过 6 秒没有新帧就断开重连。
 * 直接把 MJPEG 地址交给 Web 时，流断开后画面会停在黑屏或最后一帧，且不会自行恢复。
 * body.dataset.state：connecting / live / reconnecting，供 ArkTS 侧判断是否已出画面。
 */
export function buildMjpegPage(path: string, fit: string): string {
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0f172a}
img{display:block;width:100vw;height:100vh;object-fit:${fit}}
#tip{position:fixed;left:0;right:0;bottom:12px;text-align:center;color:#cbd5e1;font:13px sans-serif;display:none}
</style></head><body data-state="connecting"><img id="v" alt=""><div id="tip">画面中断，正在重连…</div>
<script>
(function(){
  var img=document.getElementById('v'),tip=document.getElementById('tip');
  var ctrl=null,last=0,shown=null,pending=false;
  function setState(s){document.body.dataset.state=s;tip.style.display=(s==='reconnecting'&&shown)?'block':'none';}
  function find(b,m,from){for(var i=from;i<b.length-1;i++){if(b[i]===255&&b[i+1]===m)return i;}return -1;}
  function show(bytes){
    last=Date.now();
    var url=URL.createObjectURL(new Blob([bytes],{type:'image/jpeg'}));
    var old=shown;shown=url;img.src=url;
    if(old)setTimeout(function(){URL.revokeObjectURL(old);},1000);
    if(document.body.dataset.state!=='live')setState('live');
  }
  function retry(){if(pending)return;pending=true;setState(shown?'reconnecting':'connecting');setTimeout(function(){pending=false;run();},2000);}
  function run(){
    ctrl=new AbortController();last=Date.now();
    var c=ctrl;
    fetch('${path}?t='+Date.now(),{cache:'no-store',signal:c.signal}).then(function(r){
      if(!r.ok||!r.body)throw new Error('http '+r.status);
      var rd=r.body.getReader(),buf=new Uint8Array(0);
      function pump(){return rd.read().then(function(x){
        if(x.done)throw new Error('closed');
        var nb=new Uint8Array(buf.length+x.value.length);nb.set(buf);nb.set(x.value,buf.length);buf=nb;
        for(;;){
          var s=find(buf,216,0);
          if(s<0){buf=buf.slice(Math.max(0,buf.length-1));break;}
          var e=find(buf,217,s+2);
          if(e<0){if(s>0)buf=buf.slice(s);break;}
          show(buf.slice(s,e+2));buf=buf.slice(e+2);
        }
        return pump();
      });}
      return pump();
    }).catch(function(){if(c===ctrl)retry();});
  }
  setInterval(function(){if(ctrl&&!pending&&Date.now()-last>6000){var c=ctrl;ctrl=null;c.abort();retry();}},1000);
  run();
})();
</script></body></html>`;
}
