// Offline checks against the actual pure ArkTS pose gate.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require(process.env.GUARDIAN_TYPESCRIPT_PATH || 'typescript');

function loadGate() {
  const file = path.resolve(__dirname, '../entry/src/main/ets/face/FacePoseGate.ets');
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: 'FacePoseGate.ts'
  }).outputText;
  const loaded = new Module(file, module);
  loaded._compile(code, file);
  return loaded.exports.FacePoseGate;
}

function sample(overrides = {}) {
  return {
    frameId: 1,
    capturedAtMs: 0,
    receivedAtMs: 0,
    pose: 'front',
    yaw: 0,
    pitch: 0,
    roll: 0,
    singleFace: true,
    livenessMatched: true,
    complete: true,
    clear: true,
    ...overrides
  };
}

function feed(gate, pose, values = {}, times = [0, 125, 250, 375, 500]) {
  let state;
  times.forEach((capturedAtMs, index) => {
    state = gate.accept(sample({
      ...values,
      pose,
      frameId: index + 1,
      capturedAtMs,
      receivedAtMs: capturedAtMs
    }));
  });
  return state;
}

test('angle boundaries are inclusive for front, left, right, pitch, and roll', () => {
  const FacePoseGate = loadGate();
  for (const yaw of [-15, 15]) {
    assert.equal(feed(new FacePoseGate(), 'front', { yaw }).allowed, true);
  }
  for (const yaw of [-15.01, 15.01]) {
    assert.equal(feed(new FacePoseGate(), 'front', { yaw }).reason, 'yaw');
  }
  assert.equal(feed(new FacePoseGate(), 'left', { yaw: -25 }).allowed, true);
  assert.equal(feed(new FacePoseGate(), 'left', { yaw: -24.99 }).reason, 'yaw');
  assert.equal(feed(new FacePoseGate(), 'right', { yaw: 25 }).allowed, true);
  assert.equal(feed(new FacePoseGate(), 'right', { yaw: 24.99 }).reason, 'yaw');
  for (const pitch of [-20, 20]) {
    assert.equal(feed(new FacePoseGate(), 'front', { pitch }).allowed, true);
  }
  for (const roll of [-15, 15]) {
    assert.equal(feed(new FacePoseGate(), 'front', { roll }).allowed, true);
  }
  assert.equal(feed(new FacePoseGate(), 'front', { pitch: -20.01 }).reason, 'pitch');
  assert.equal(feed(new FacePoseGate(), 'front', { pitch: 20.01 }).reason, 'pitch');
  assert.equal(feed(new FacePoseGate(), 'front', { roll: -15.01 }).reason, 'roll');
  assert.equal(feed(new FacePoseGate(), 'front', { roll: 15.01 }).reason, 'roll');
});

test('failure priority and Chinese prompts are deterministic', () => {
  const FacePoseGate = loadGate();
  const cases = [
    [{ singleFace: false, livenessMatched: false, complete: false, clear: false,
       roll: 30, pitch: 30, yaw: 30 }, 'face_count', '请确保画面中只有一张人脸'],
    [{ livenessMatched: false, complete: false, clear: false, roll: 30, pitch: 30, yaw: 30 },
      'liveness', '请先完成活体检测'],
    [{ complete: false, clear: false, roll: 30, pitch: 30, yaw: 30 },
      'completeness', '请将完整面部放入取景框'],
    [{ clear: false, roll: 30, pitch: 30, yaw: 30 },
      'clarity', '请保持光线充足并避免晃动'],
    [{ roll: 30, pitch: 30, yaw: 30 }, 'roll', '请保持头部水平'],
    [{ pitch: -20.01, yaw: 30 }, 'pitch', '请抬头'],
    [{ pitch: 20.01, yaw: 30 }, 'pitch', '请低头'],
    [{ pose: 'left', yaw: -24.99 }, 'yaw', '请继续向左转头'],
    [{ pose: 'right', yaw: 24.99 }, 'yaw', '请继续向右转头'],
    [{ pose: 'front', yaw: -15.01 }, 'yaw', '请向右转回正面'],
    [{ pose: 'front', yaw: 15.01 }, 'yaw', '请向左转回正面']
  ];
  for (const [values, reason, prompt] of cases) {
    const state = new FacePoseGate().accept(sample(values));
    assert.equal(state.reason, reason);
    assert.equal(state.prompt, prompt);
    assert.equal(state.allowed, false);
  }
});

test('five distinct frames spanning 500 ms are required', () => {
  const FacePoseGate = loadGate();
  const gate = new FacePoseGate();
  const states = [0, 125, 250, 375, 500].map((capturedAtMs, index) => gate.accept(sample({
    frameId: index + 1,
    capturedAtMs,
    receivedAtMs: capturedAtMs
  })));
  assert.deepEqual(states.slice(0, 4).map(value => value.allowed), [false, false, false, false]);
  assert.equal(states[3].reason, 'stabilizing');
  assert.equal(states[4].allowed, true);
  assert.equal(states[4].reason, 'ready');
  assert.equal(states[4].validFrameCount, 5);
  assert.equal(states[4].stableSinceMs, 0);

  assert.equal(feed(new FacePoseGate(), 'front', {}, [0, 100, 200, 300, 400]).allowed, false);
});

test('duplicate frames do not count while gaps, stale samples, and quality failures reset', () => {
  const FacePoseGate = loadGate();
  const duplicateGate = new FacePoseGate();
  const duplicateIds = [1, 2, 2, 3, 4, 5];
  let state;
  duplicateIds.forEach((frameId, index) => {
    const capturedAtMs = index * 100;
    state = duplicateGate.accept(sample({ frameId, capturedAtMs, receivedAtMs: capturedAtMs }));
  });
  assert.equal(state.allowed, true);
  assert.equal(state.validFrameCount, 5);

  const gapGate = new FacePoseGate();
  feed(gapGate, 'front', {}, [0, 100, 200]);
  state = gapGate.accept(sample({ frameId: 4, capturedAtMs: 501, receivedAtMs: 501 }));
  assert.equal(state.allowed, false);
  assert.equal(state.validFrameCount, 1);
  assert.equal(state.stableSinceMs, 501);

  const staleGate = new FacePoseGate();
  feed(staleGate, 'front', {}, [0, 100, 200]);
  state = staleGate.accept(sample({ frameId: 4, capturedAtMs: 300, receivedAtMs: 601 }));
  assert.equal(state.reason, 'stale');
  assert.equal(state.validFrameCount, 0);

  const qualityGate = new FacePoseGate();
  feed(qualityGate, 'front', {}, [0, 100, 200]);
  state = qualityGate.accept(sample({ frameId: 4, capturedAtMs: 300, receivedAtMs: 300, clear: false }));
  assert.equal(state.reason, 'clarity');
  state = qualityGate.accept(sample({ frameId: 5, capturedAtMs: 400, receivedAtMs: 400 }));
  assert.equal(state.validFrameCount, 1);
  assert.equal(state.stableSinceMs, 400);

  const replayGate = new FacePoseGate();
  replayGate.accept(sample({ frameId: 1, capturedAtMs: 0, receivedAtMs: 0 }));
  const rejected = replayGate.accept(sample({
    frameId: 2,
    capturedAtMs: 100,
    receivedAtMs: 100,
    clear: false
  }));
  const replayed = replayGate.accept(sample({ frameId: 2, capturedAtMs: 100, receivedAtMs: 100 }));
  assert.equal(rejected.reason, 'clarity');
  assert.equal(replayed.allowed, false);
  assert.equal(replayed.reason, 'out_of_order');
  assert.equal(replayed.validFrameCount, 0);
  state = replayGate.accept(sample({ frameId: 3, capturedAtMs: 200, receivedAtMs: 200 }));
  assert.equal(state.validFrameCount, 1);
  assert.equal(state.stableSinceMs, 200);
});

test('out-of-order samples and explicit lifecycle resets cannot revive an old window', () => {
  const FacePoseGate = loadGate();
  for (const resetReason of ['background', 'camera_restart', 'orientation_change']) {
    const gate = new FacePoseGate();
    feed(gate, 'front', {}, [0, 100, 200, 300]);
    gate.reset(resetReason);
    const afterReset = gate.accept(sample({ frameId: 10, capturedAtMs: 400, receivedAtMs: 400 }));
    assert.equal(afterReset.validFrameCount, 1);
    assert.equal(afterReset.allowed, false);
    assert.equal(afterReset.stableSinceMs, 400);
  }

  const gate = new FacePoseGate();
  feed(gate, 'front', {}, [100, 200, 300]);
  const outOfOrder = gate.accept(sample({ frameId: 4, capturedAtMs: 250, receivedAtMs: 310 }));
  assert.equal(outOfOrder.reason, 'out_of_order');
  assert.equal(outOfOrder.allowed, false);
  assert.equal(outOfOrder.validFrameCount, 0);
  const restarted = gate.accept(sample({ frameId: 5, capturedAtMs: 400, receivedAtMs: 400 }));
  assert.equal(restarted.validFrameCount, 1);
  assert.equal(restarted.stableSinceMs, 400);

  const watermarkGate = new FacePoseGate();
  watermarkGate.accept(sample({ frameId: 10, capturedAtMs: 1000, receivedAtMs: 1000 }));
  const old = watermarkGate.accept(sample({ frameId: 4, capturedAtMs: 400, receivedAtMs: 1001 }));
  assert.equal(old.reason, 'out_of_order');
  const stillOld = watermarkGate.accept(sample({ frameId: 5, capturedAtMs: 500, receivedAtMs: 1002 }));
  assert.equal(stillOld.reason, 'out_of_order');
  assert.equal(stillOld.validFrameCount, 0);
});

test('click freshness and duplicate results can never inherit a ready state', () => {
  const FacePoseGate = loadGate();
  const gate = new FacePoseGate();
  const ready = feed(gate, 'front');
  assert.equal(ready.allowed, true);
  const staleClick = gate.stateAt(801);
  assert.equal(staleClick.allowed, false);
  assert.equal(staleClick.reason, 'stale');
  assert.equal(staleClick.validFrameCount, 0);

  const duplicateGate = new FacePoseGate();
  feed(duplicateGate, 'front');
  const duplicate = duplicateGate.accept(sample({
    frameId: 5,
    capturedAtMs: 500,
    receivedAtMs: 500
  }));
  assert.equal(duplicate.allowed, false);
  assert.equal(duplicate.reason, 'out_of_order');

  const conflictingGate = new FacePoseGate();
  feed(conflictingGate, 'front');
  const conflicting = conflictingGate.accept(sample({
    frameId: 5,
    capturedAtMs: 500,
    receivedAtMs: 500,
    clear: false
  }));
  assert.equal(conflicting.reason, 'clarity');
  assert.equal(conflicting.validFrameCount, 0);
});
