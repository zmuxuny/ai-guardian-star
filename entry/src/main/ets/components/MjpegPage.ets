/**
 * Latest-frame transport: one finite request/decode at a time, never a queued MJPEG stream.
 * Keep the exported name for existing callers; path points to a finite JPEG preview endpoint.
 * body.dataset.state: connecting / live / reconnecting.
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
  var ctrl=null,timer=null,deadline=null,shown=null,candidate=null,stopped=false,generation=0;
  var statsAt=Date.now(),frames=0,requestMs=0,decodeMs=0,lastShownAt=0,maxGapMs=0;
  function recordFrame(started,received){
    var now=Date.now();frames++;requestMs+=received-started;decodeMs+=now-received;
    if(lastShownAt)maxGapMs=Math.max(maxGapMs,now-lastShownAt);lastShownAt=now;
    if(now-statsAt>=5000){
      console.info('[CameraPreviewMetrics]'+JSON.stringify({fps:Math.round(frames*10000/(now-statsAt))/10,
        requestMs:Math.round(requestMs/frames),decodeMs:Math.round(decodeMs/frames),maxGapMs:maxGapMs}));
      statsAt=now;frames=0;requestMs=0;decodeMs=0;maxGapMs=0;
    }
  }
  function setState(s){document.body.dataset.state=s;tip.style.display=(s==='reconnecting'&&shown)?'block':'none';}
  function revoke(url){if(url)URL.revokeObjectURL(url);}
  function schedule(delay){
    if(stopped||document.hidden)return;
    clearTimeout(timer);timer=setTimeout(run,delay);
  }
  function run(){
    if(stopped||document.hidden||ctrl)return;
    var c=ctrl=new AbortController(),g=generation,started=Date.now(),received=started;
    function current(){return !stopped&&g===generation&&ctrl===c;}
    function finish(ok){
      if(!current())return;
      clearTimeout(deadline);deadline=null;
      img.onload=null;img.onerror=null;
      if(!ok){
        c.abort();
        if(candidate){img.src=shown||'';revoke(candidate);candidate=null;}
        setState(shown?'reconnecting':'connecting');
      }
      // Target up to 15 fps. Network/decode time counts toward the interval;
      // do not add another fixed sleep after an already slow request.
      ctrl=null;schedule(ok?Math.max(0,67-(Date.now()-started)):800);
    }
    // A slow or stuck request is cancelled; another request never waits behind it.
    deadline=setTimeout(function(){finish(false);},5000);
    fetch('${path}?t='+Date.now(),{cache:'no-store',signal:c.signal}).then(function(r){
      if(!current())return null;
      if(r.status!==200)throw new Error('no current frame');
      return r.blob();
    }).then(function(blob){
      if(!current()||!blob)return;
      if(!blob.size||blob.type.indexOf('image/jpeg')!==0)throw new Error('invalid frame');
      received=Date.now();
      candidate=URL.createObjectURL(blob);
      img.onload=function(){
        if(!current())return;
        revoke(shown);shown=candidate;candidate=null;
        recordFrame(started,received);setState('live');finish(true);
      };
      img.onerror=function(){finish(false);};
      img.src=candidate;
    }).catch(function(){finish(false);});
  }
  function stop(){
    stopped=true;generation++;
    clearTimeout(timer);clearTimeout(deadline);timer=null;deadline=null;
    if(ctrl)ctrl.abort();ctrl=null;
    img.onload=null;img.onerror=null;img.removeAttribute('src');
    revoke(candidate);revoke(shown);candidate=null;shown=null;
  }
  function resume(){
    if(document.hidden)return;
    stopped=false;statsAt=Date.now();frames=0;requestMs=0;decodeMs=0;lastShownAt=0;maxGapMs=0;
    setState('connecting');schedule(0);
  }
  window.stopCameraPreview=stop;
  document.addEventListener('visibilitychange',function(){if(document.hidden)stop();else resume();});
  window.addEventListener('pagehide',stop);
  window.addEventListener('pageshow',resume);
  run();
})();
</script></body></html>`;
}
