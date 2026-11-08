const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require(process.env.GUARDIAN_TYPESCRIPT_PATH || 'typescript');

// Execute the actual component lifecycle and scheduler, excluding only its ArkUI DSL.
const source = fs.readFileSync('entry/src/main/ets/components/CameraStreamView.ets', 'utf8');
const logic = (source.slice(0, source.indexOf('  build() {')) + '}')
  .replace('@Component', '')
  .replace('export struct CameraStreamView', 'export class CameraStreamView')
  .replace(/@(Prop|State)\s+/g, '');
const code = ts.transpileModule(logic, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;

function setup() {
  let now = 1000, timerId = 0, calls = 0, cancelled = 0;
  const replies = [], scheduled = [];
  class Client {
    async fetch() {
      calls++;
      const reply = replies.shift();
      if (reply instanceof Error) throw reply;
      return await reply;
    }
    cancel() { cancelled++; }
  }
  class Clock extends Date { static now() { return now; } }
  const exports = {};
  vm.runInNewContext(code, {
    exports, Date: Clock, Math,
    require: name => name.includes('CameraFrameClient') ? { CameraFrameClient: Client } : { ECS_BASE_URL: 'https://example' },
    setTimeout: (fn, delay) => { scheduled.push(delay); return ++timerId; },
    clearTimeout: () => {}, console: { info() {} }
  });
  const view = new exports.CameraStreamView();
  view.aboutToAppear();
  scheduled.length = 0;
  return { view, replies, scheduled, setNow: value => now = value,
    counts: () => ({ calls, cancelled }) };
}
function frame(sequence = '1') {
  return { pixels: { release: async () => {} }, sequence, requestMs: 40, decodeMs: 10 };
}

test('brief source gaps retain the last image and keep polling without error backoff', async () => {
  const h = setup();
  h.replies.push(frame()); await h.view.loadFrame();
  h.setNow(1200); h.replies.push(undefined); await h.view.loadFrame();
  assert.equal(h.view.unavailable, false);
  assert.equal(h.view.sequence, '1');
  assert.equal(h.scheduled.at(-1), 67);
});

test('repeated duplicates or empty responses become interrupted and a new frame recovers immediately', async () => {
  const h = setup();
  h.replies.push(frame()); await h.view.loadFrame();
  h.setNow(3100); h.replies.push(undefined); await h.view.loadFrame();
  assert.equal(h.view.unavailable, true);
  h.setNow(3200); h.replies.push(frame('2')); await h.view.loadFrame();
  assert.equal(h.view.unavailable, false);
  assert.equal(h.view.sequence, '2');
});

test('network failures retry quickly then back off with a cap and reset on recovery', async () => {
  const h = setup();
  for (let i = 0; i < 6; i++) {
    h.replies.push(Error('offline')); await h.view.loadFrame();
  }
  assert.deepEqual(h.scheduled, [200, 400, 800, 1500, 1500, 1500]);
  h.replies.push(frame()); await h.view.loadFrame();
  h.replies.push(Error('brief')); await h.view.loadFrame();
  assert.equal(h.scheduled.at(-1), 200);
});

test('a single transient failure does not flash interruption while the image is fresh', async () => {
  const h = setup();
  h.replies.push(frame()); await h.view.loadFrame();
  h.setNow(1100); h.replies.push(Error('temporary')); await h.view.loadFrame();
  assert.equal(h.view.unavailable, false);
});

test('hiding or leaving during a request discards the late result without restarting polling', async () => {
  const h = setup();
  let complete, released = 0;
  h.replies.push(new Promise(resolve => complete = resolve));
  const pending = h.view.loadFrame();
  h.view.suspend();
  complete({ ...frame(), pixels: { release: async () => released++ } });
  await pending;
  assert.equal(released, 1);
  assert.equal(h.view.frame, undefined);
  assert.equal(h.scheduled.length, 0);
  assert.equal(h.counts().calls, 1);
});
