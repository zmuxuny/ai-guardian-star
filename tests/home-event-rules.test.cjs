// Run with DevEco's Node and GUARDIAN_TYPESCRIPT_PATH pointing to its compiler.
// Exercises the actual pure ArkTS rules without MQTT, RDB, or production data.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require(process.env.GUARDIAN_TYPESCRIPT_PATH || 'typescript');

function loadRules(name, dependencies = {}) {
  const file = path.resolve(__dirname, '../entry/src/main/ets/common', name + '.ets');
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: name + '.ts'
  }).outputText;
  const loaded = new Module(file, module);
  loaded.require = id => {
    assert.ok(Object.hasOwn(dependencies, id), 'Unexpected real dependency: ' + id);
    return dependencies[id];
  };
  loaded._compile(code, file);
  return loaded.exports;
}

const parser = loadRules('MqttParser');
const rules = loadRules('HomeEventRules', { './MqttParser': parser });

test('today includes midnight and excludes adjacent calendar dates', () => {
  const now = new Date(2026, 9, 26, 18).getTime();
  const start = new Date(2026, 9, 26).getTime();
  const end = new Date(2026, 9, 27).getTime();
  assert.equal(rules.isTodayHomeEvent('fall', start, now), true);
  assert.equal(rules.isTodayHomeEvent('stranger', end - 1, now), true);
  assert.equal(rules.isTodayHomeEvent('sedentary', start - 1, now), false);
  assert.equal(rules.isTodayHomeEvent('fall', end, now), false);
});

test('today is a calendar day rather than the previous 24 hours', () => {
  const now = new Date(2026, 9, 26, 1).getTime();
  assert.equal(rules.isTodayHomeEvent('stranger', now - 2 * 3600000, now), false);
  assert.equal(rules.isTodayHomeEvent('heartbeat', now, now), false);
  assert.equal(rules.isTodayHomeEvent('fall', NaN, now), false);
});

test('today changes correctly across midnight and year end', () => {
  const before = new Date(2026, 11, 31, 23, 59, 59).getTime();
  const after = new Date(2027, 0, 1).getTime();
  assert.equal(rules.isTodayHomeEvent('sedentary', before, before), true);
  assert.equal(rules.isTodayHomeEvent('sedentary', before, after), false);
  assert.equal(rules.isTodayHomeEvent('stranger', after, after), true);
});

test('homepage includes stranger alongside fall and sedentary events', () => {
  assert.deepEqual(['fall', 'sedentary', 'stranger', 'heartbeat', 'normal', 'unknown']
    .filter(rules.isHomeEventType), ['fall', 'sedentary', 'stranger']);
});

test('stranger messages have an explicit homepage label', () => {
  assert.equal(parser.parseAlert('{"event":"stranger_detected"}').type, 'stranger');
  assert.equal(rules.homeEventTitle('stranger'), '陌生人到来');
  assert.equal(rules.homeEventTitle('fall'), '摔倒告警');
  assert.equal(rules.homeEventTitle('sedentary'), '久坐提醒');
});

const routinePayload = {
  event: 'routine_alert', schema_version: '2', event_id: 'routine-id', alert_type: 'late_wakeup',
  timestamp: '2026-11-24T08:30:00+08:00', reason: '平时约 07:00 离开床区。',
};

test('App parses UTF-8 routine payloads and labels each rule as a home event', () => {
  for (const [type, title] of [
    ['late_wakeup', '晚起提醒'],
    ['daytime_inactivity', '白天活动提醒'],
    ['night_bathroom_stay', '夜间卫生间停留提醒'],
  ]) {
    const payload = { ...routinePayload, alert_type: type };
    const bytes = new Uint8Array(Buffer.from(JSON.stringify(payload), 'utf8'));
    const result = parser.parseAlert(bytes.buffer);
    assert.equal(result.type, 'routine_alert');
    assert.deepEqual(result.routine, {
      eventId: routinePayload.event_id, alertType: type, timestamp: Date.parse(payload.timestamp),
      reason: routinePayload.reason,
    });
    assert.equal(rules.isTodayHomeEvent(type, result.routine.timestamp, result.routine.timestamp), true);
    assert.equal(rules.homeEventTitle(type), title);
  }
});

test('malformed and unknown routine payloads cannot masquerade as normal status', () => {
  for (const change of [
    { schema_version: 2 }, { schema_version: '5' }, { alert_type: 'unknown' }, { event_id: '' },
    { timestamp: '2026-11-24T08:30:00' }, { reason: '  ' },
  ]) {
    assert.equal(parser.parseAlert(JSON.stringify({ ...routinePayload, ...change })).type, 'unknown');
  }
});

function arrivals(times) {
  let activity = 0;
  return times.filter(time => {
    const isNew = rules.startsStrangerArrival(time, activity);
    activity = time;
    return isNew;
  });
}

test('continuous five-second notifications produce one arrival', () => {
  assert.deepEqual(arrivals([100000, 105000, 110000, 115000, 120000]), [100000]);
});

test('a later visit after a quiet interval produces another arrival', () => {
  assert.deepEqual(arrivals([100000, 105000, 125000, 130000]), [100000, 125000]);
});

test('arrival boundary uses a full fifteen-second quiet interval', () => {
  assert.equal(rules.startsStrangerArrival(114999, 100000), false);
  assert.equal(rules.startsStrangerArrival(115000, 100000), true);
});

test('a device clock adjustment cannot suppress future arrivals indefinitely', () => {
  assert.equal(rules.startsStrangerArrival(90000, 100000), true);
});

function mqttHarness() {
  const file = path.resolve(__dirname, '../entry/src/main/ets/pages/MqttManager.ets');
  const writes = [];
  let owner = 'synthetic-owner-a';
  let fail = false;
  const dependencies = {
    '@ohos/mqtt': {},
    '../database/DatabaseHelper': { DatabaseHelper: { getInstance: () => ({
      insertHealthEvent: event => {
        if (fail) return Promise.reject(new Error('synthetic write failure'));
        writes.push({ ...event });
        return Promise.resolve(writes.length);
      }
    }) } },
    '../common/UserManager': { UserManager: { getInstance: () => ({ getCurrentUsername: () => owner }) } },
    '../common/CloudService': { CloudService: { getInstance: () => ({ setSessionClearedListener() {} }) } },
    '../config': { ALERT_TOPIC: 'ai_guardian/alerts/#' },
    '../common/MqttParser': parser,
    '../common/HomeEventRules': rules
  };
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, experimentalDecorators: true },
    fileName: 'MqttManager.ts'
  }).outputText;
  const loaded = new Module(file, module);
  loaded.require = id => {
    assert.ok(Object.hasOwn(dependencies, id), 'Unexpected real dependency: ' + id);
    return dependencies[id];
  };
  loaded._compile('const Observed = target => target; const Track = () => {};\n' + code, file);
  const manager = loaded.exports.MqttManager.getInstance();
  manager.startStrangerRecoveryTimer = () => {}; // This suite checks event writes, not display timers.
  return { manager, writes, setOwner: value => { owner = value; }, setFailure: value => { fail = value; } };
}

test('routine handler preserves ID and reason under the account without clearing fall state', async () => {
  const h = mqttHarness();
  h.manager.isFallDetected = true;
  h.manager.deviceOnline = false;
  const payload = JSON.stringify(routinePayload);
  h.manager.handleMessage('ai_guardian/alerts/fall', payload);
  h.setOwner('');
  h.manager.handleMessage(parser.ROUTINE_ALERT_TOPIC, payload);
  h.setOwner('synthetic-owner-a');
  h.manager.handleMessage(parser.ROUTINE_ALERT_TOPIC, payload);
  await Promise.resolve();
  assert.equal(h.writes.length, 1);
  assert.equal(h.writes[0].sourceEventId, routinePayload.event_id);
  assert.equal(h.writes[0].eventTime, Date.parse(routinePayload.timestamp));
  assert.equal(h.writes[0].eventType, 'late_wakeup');
  assert.equal(h.writes[0].remark, routinePayload.reason);
  assert.equal(h.writes[0].username, 'synthetic-owner-a');
  assert.equal(h.manager.isFallDetected, true);
  assert.equal(h.manager.deviceOnline, false);
});

test('real MQTT handler persists each stranger arrival once for the current account', async t => {
  const h = mqttHarness();
  let now = 100000;
  t.mock.method(Date, 'now', () => now);
  const send = () => h.manager.handleMessage('ai_guardian/alerts/stranger', '{"event":"stranger_detected"}');
  send();
  now += 5000; send();
  now += 5000; send();
  await Promise.resolve();
  assert.equal(h.writes.length, 1);
  assert.equal(h.writes[0].eventType, 'stranger');
  assert.equal(h.writes[0].username, 'synthetic-owner-a');
  assert.equal(h.writes[0].isHandled, 0);
  now += 20000; send();
  await Promise.resolve();
  assert.equal(h.writes.length, 2);
});

test('switching account resets stranger arrival grouping', async t => {
  const h = mqttHarness();
  t.mock.method(Date, 'now', () => 100000);
  h.manager.handleMessage('ai_guardian/alerts/stranger', '{"event":"stranger_detected"}');
  h.setOwner('synthetic-owner-b');
  h.manager.resetMqttState();
  h.manager.handleMessage('ai_guardian/alerts/stranger', '{"event":"stranger_detected"}');
  await Promise.resolve();
  assert.deepEqual(h.writes.map(event => event.username), ['synthetic-owner-a', 'synthetic-owner-b']);
});

test('failed stranger storage can retry on the next notification', async t => {
  const h = mqttHarness();
  let now = 100000;
  t.mock.method(Date, 'now', () => now);
  h.setFailure(true);
  h.manager.handleMessage('ai_guardian/alerts/stranger', '{"event":"stranger_detected"}');
  await Promise.resolve();
  h.setFailure(false);
  now += 5000;
  h.manager.handleMessage('ai_guardian/alerts/stranger', '{"event":"stranger_detected"}');
  await Promise.resolve();
  assert.equal(h.writes.length, 1);
});
