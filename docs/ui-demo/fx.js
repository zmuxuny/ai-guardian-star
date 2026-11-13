// 声音与触感：全部用 WebAudio 现场合成，不依赖音频文件；手机上同时触发振动。
(() => {
  let ac, out, on = true;
  try { on = localStorage.getItem('zhx-sound') !== '0'; } catch (e) {}
  const A = () => {
    if (!ac) {
      const C = window.AudioContext || window.webkitAudioContext;
      if (!C) return null;
      ac = new C();
      const comp = ac.createDynamicsCompressor();
      out = ac.createGain(); out.gain.value = 0.55;
      out.connect(comp); comp.connect(ac.destination);
    }
    if (ac.state === 'suspended') ac.resume();
    return ac;
  };
  function tone(f, at, dur, vol, type, f2) {
    const a = A(); if (!a || !on) return;
    const t = a.currentTime + at, o = a.createOscillator(), g = a.createGain();
    o.type = type || 'sine'; o.frequency.setValueAtTime(f, t);
    if (f2) o.frequency.exponentialRampToValueAtTime(f2, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.006);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(out); o.start(t); o.stop(t + dur + 0.03);
  }
  function hiss(at, dur, f, vol, f2) {
    const a = A(); if (!a || !on) return;
    const t = a.currentTime + at, n = Math.max(1, a.sampleRate * dur | 0);
    const b = a.createBuffer(1, n, a.sampleRate), d = b.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    const s = a.createBufferSource(), bp = a.createBiquadFilter(), g = a.createGain();
    s.buffer = b; bp.type = 'bandpass'; bp.Q.value = 1.2; bp.frequency.setValueAtTime(f, t);
    if (f2) bp.frequency.exponentialRampToValueAtTime(f2, t + dur);
    g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(bp); bp.connect(g); g.connect(out); s.start(t);
  }
  const vib = p => { try { navigator.vibrate && navigator.vibrate(p); } catch (e) {} };
  const S = {
    tap() { tone(1900, 0, 0.05, 0.12, 'sine', 1300); hiss(0, 0.02, 3200, 0.07); vib(8); },
    tick() { tone(2400, 0, 0.025, 0.06, 'sine', 2000); vib(4); },
    on() { tone(1320, 0, 0.09, 0.13); tone(1980, 0.06, 0.18, 0.11); vib([10, 30, 14]); },
    off() { tone(1320, 0, 0.08, 0.11); tone(880, 0.06, 0.16, 0.1); vib(10); },
    open() { hiss(0, 0.22, 500, 0.09, 2600); tone(660, 0, 0.12, 0.05, 'sine', 990); vib(12); },
    close() { hiss(0, 0.16, 2400, 0.07, 500); vib(8); },
    ok() { tone(784, 0, 0.5, 0.13); tone(988, 0.12, 0.5, 0.11); tone(1175, 0.24, 0.9, 0.11); vib([12, 40, 12]); },
    remind() { tone(880, 0, 0.35, 0.15, 'triangle'); tone(660, 0.2, 0.7, 0.13, 'triangle'); vib([30, 60, 30]); },
    fall() { [0, 0.3, 0.6].forEach(t => { tone(587, t, 0.22, 0.2, 'triangle', 554); tone(294, t, 0.24, 0.16); }); vib([120, 80, 120, 80, 200]); },
    ring() { tone(1175, 0, 0.18, 0.11); tone(1568, 0.2, 0.3, 0.11); },
    connect() { tone(660, 0, 0.1, 0.12); tone(990, 0.1, 0.22, 0.12); vib([15, 40, 15]); },
    hang() { tone(520, 0, 0.12, 0.13); tone(392, 0.12, 0.26, 0.13); vib(30); },
    send() { hiss(0, 0.18, 900, 0.07, 3000); tone(1400, 0.02, 0.12, 0.07, 'sine', 2100); vib(10); },
    get enabled() { return on; },
    toggle() { on = !on; try { localStorage.setItem('zhx-sound', on ? '1' : '0'); } catch (e) {} if (on) S.on(); return on; },
    vib
  };
  // 所有按钮和链接按下时都有一声轻响；data-fx="none" 的自己另外发声
  document.addEventListener('pointerdown', e => {
    const t = e.target.closest('button,a,[data-fx]');
    if (!t || t.disabled) return;
    const k = t.dataset.fx || 'tap';
    if (k !== 'none' && S[k]) S[k]();
  }, true);
  // 同一个开关管住嵌在页面里的样机
  addEventListener('storage', e => { if (e.key === 'zhx-sound') on = e.newValue !== '0'; });
  window.FX = S;
})();
