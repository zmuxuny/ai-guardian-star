// Offline checks against the actual pure ArkTS transform and metrics modules.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require(process.env.GUARDIAN_TYPESCRIPT_PATH || 'typescript');

function loadModule(name, mocks = {}) {
  const file = path.resolve(__dirname, `../entry/src/main/ets/face/${name}.ets`);
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: `${name}.ts`
  }).outputText;
  const loaded = new Module(file, module);
  const nativeRequire = loaded.require.bind(loaded);
  loaded.require = key => Object.prototype.hasOwnProperty.call(mocks, key) ? mocks[key] : nativeRequire(key);
  loaded._compile(code, file);
  return loaded.exports;
}

function calibration(overrides = {}) {
  return {
    key: {
      deviceModel: 'Guardian Phone',
      systemVersion: '6.1.1',
      cameraId: 'front-0',
      sensorOrientation: 270,
      detectorVersion: 'core-vision-1',
      preprocessVersion: 'canonical-v1'
    },
    yawSign: -1,
    pitchSign: 1,
    rollSign: -1,
    yawOffset: 1,
    pitchOffset: 2,
    rollOffset: 3,
    ...overrides
  };
}

test('calibration key is complete and sign then offset produces canonical pose', () => {
  const transform = loadModule('FaceFrameTransform');
  const result = transform.normalizePose({ yaw: 10, pitch: -5, roll: 2 }, calibration());
  assert.equal(result.ok, true);
  assert.deepEqual(result.pose, { yaw: -9, pitch: -3, roll: 1 });

  const spec = transform.createFrameTransformSpec(270, 90, true, true);
  assert.deepEqual(spec, {
    sensorOrientation: 270,
    displayRotation: 90,
    frontFacing: true,
    mirroredPreview: true,
    outputPixelFormat: 'RGBA_8888',
    outputOrientation: 'portrait',
    outputMirrored: false,
    preserveExifOrientation: false
  });
  const wrongKey = { ...calibration().key, cameraId: 'front-1' };
  assert.equal(transform.normalizePoseForKey({ yaw: 0, pitch: 0, roll: 0 }, calibration(), wrongKey).errorCode,
    'CALIBRATION_MISSING');
});

test('missing calibration, invalid signs, and non-finite poses fail closed', () => {
  const transform = loadModule('FaceFrameTransform');
  assert.equal(transform.normalizePose({ yaw: 0, pitch: 0, roll: 0 }, undefined).errorCode,
    'CALIBRATION_MISSING');
  assert.equal(transform.normalizePose({ yaw: 0, pitch: 0, roll: 0 },
    calibration({ yawSign: 0 })).errorCode, 'CALIBRATION_MISSING');
  const missingKey = calibration();
  missingKey.key = { ...missingKey.key, detectorVersion: '' };
  assert.equal(transform.normalizePose({ yaw: 0, pitch: 0, roll: 0 }, missingKey).errorCode,
    'CALIBRATION_MISSING');
  assert.equal(transform.normalizePose({ yaw: Number.NaN, pitch: 0, roll: 0 }, calibration()).errorCode,
    'INVALID_POSE');
  assert.equal(transform.normalizePose({ yaw: 0, pitch: Number.POSITIVE_INFINITY, roll: 0 },
    calibration()).errorCode, 'INVALID_POSE');
});

test('metrics report deterministic percentiles, counts, resets, and errors', () => {
  const { FaceProbeMetrics } = loadModule('FaceProbeMetrics');
  const metrics = new FaceProbeMetrics({
    deviceModel: 'Guardian Phone',
    systemVersion: '6.1.1',
    cameraId: 'front-0',
    detectorVersion: 'core-vision-1',
    preprocessVersion: 'canonical-v1'
  });
  [10, 20, 30, 40, 50].forEach((latencyMs, index) => metrics.record({
    processed: true,
    latencyMs,
    normalizeMs: index + 1,
    detectMs: index + 5,
    gateMs: 1,
    endToEndMs: latencyMs
  }));
  metrics.record({ processed: false, latencyMs: 0, resetReason: 'background', errorCode: 'STALE' });
  metrics.record({ processed: false, latencyMs: 0, resetReason: 'background', errorCode: 'STALE' });
  metrics.record({ processed: false, latencyMs: 0, resetReason: 'camera_restart', errorCode: 'CAMERA_BUSY' });
  metrics.record({ processed: false, latencyMs: 0, resetReason: 'SECRET_NAME', errorCode: 'SECRET_FACE_PATH' });

  const snapshot = metrics.snapshot();
  assert.equal(snapshot.processedFrames, 5);
  assert.equal(snapshot.droppedFrames, 4);
  assert.equal(snapshot.latencySampleCount, 5);
  assert.equal(snapshot.latencyP50Ms, 30);
  assert.equal(snapshot.latencyP95Ms, 50);
  assert.equal(snapshot.latencyP99Ms, 50);
  assert.deepEqual(snapshot.normalizeLatency, { sampleCount: 5, p50Ms: 3, p95Ms: 5, p99Ms: 5 });
  assert.deepEqual(snapshot.detectLatency, { sampleCount: 5, p50Ms: 7, p95Ms: 9, p99Ms: 9 });
  assert.deepEqual(snapshot.gateLatency, { sampleCount: 5, p50Ms: 1, p95Ms: 1, p99Ms: 1 });
  assert.deepEqual(snapshot.endToEndLatency, { sampleCount: 5, p50Ms: 30, p95Ms: 50, p99Ms: 50 });
  assert.deepEqual(snapshot.resetReasons, [
    { key: 'background', count: 2 },
    { key: 'camera_restart', count: 1 }
  ]);
  assert.deepEqual(snapshot.errorCodes, [
    { key: 'CAMERA_BUSY', count: 1 },
    { key: 'STALE', count: 2 }
  ]);
  assert.equal(JSON.stringify(snapshot).includes('SECRET_'), false);
});

test('metrics retain only the newest 600 latency values and never echo image or identity data', () => {
  const { FaceProbeMetrics } = loadModule('FaceProbeMetrics');
  const metrics = new FaceProbeMetrics({
    deviceModel: 'Device',
    systemVersion: 'System',
    cameraId: 'Camera',
    detectorVersion: 'Detector',
    preprocessVersion: 'Preprocess'
  });
  for (let latencyMs = 1; latencyMs <= 601; latencyMs++) {
    metrics.record({
      processed: true,
      latencyMs,
      pixelMap: 'SECRET_PIXEL_MAP',
      filePath: 'SECRET_FACE_PATH',
      jpegBytes: 'SECRET_JPEG',
      name: 'SECRET_NAME'
    });
  }
  const snapshot = metrics.snapshot();
  assert.equal(snapshot.processedFrames, 601);
  assert.equal(snapshot.latencySampleCount, 600);
  assert.equal(snapshot.latencyP50Ms, 301);
  assert.equal(snapshot.latencyP95Ms, 571);
  assert.equal(snapshot.latencyP99Ms, 595);
  const serialized = JSON.stringify(snapshot);
  for (const secret of ['SECRET_PIXEL_MAP', 'SECRET_FACE_PATH', 'SECRET_JPEG', 'SECRET_NAME']) {
    assert.equal(serialized.includes(secret), false);
  }
});

function visionModule(serviceOverrides = {}) {
  const service = {
    FaceBlock: { UNBLOCKED: 0, BLOCKED: 1 },
    init: async () => true,
    detect: async () => [],
    release: async () => {},
    ...serviceOverrides
  };
  return loadModule('FaceVisionAnalyzer', {
    '@hms.ai.face.faceDetector': { __esModule: true, default: service },
    '@kit.ImageKit': { image: {} }
  });
}

test('Core Vision adapter enables occlusion and maps only complete finite single-face results', async () => {
  let initConfig;
  let releases = 0;
  const face = {
    probability: 0.98,
    block: 0,
    pose: { yaw: -26, pitch: 3, roll: 2 },
    rect: { left: 10, top: 20, width: 100, height: 120 },
    points: [
      { x: 20, y: 40 }, { x: 80, y: 40 }, { x: 50, y: 65 },
      { x: 35, y: 95 }, { x: 65, y: 95 }
    ]
  };
  const { CoreVisionFaceDetector } = visionModule({
    init: async config => { initConfig = config; return true; },
    detect: async () => [face],
    release: async () => { releases += 1; }
  });
  const detector = new CoreVisionFaceDetector();
  await detector.init();
  assert.deepEqual(initConfig, { faceBlock: true });
  const analysis = await detector.detect(fakePixelMap('core-vision'));
  assert.equal(analysis.faceCount, 1);
  assert.equal(analysis.complete, true);
  assert.equal(analysis.unblocked, true);
  assert.deepEqual([analysis.yaw, analysis.pitch, analysis.roll], [-26, 3, 2]);
  assert.equal(analysis.points.length, 5);
  await detector.release();
  assert.equal(releases, 1);

  face.block = 1;
  const blocked = await detector.detect(fakePixelMap('blocked'));
  assert.equal(blocked.complete, false);
  face.block = 0;
  face.points[0] = { x: Number.NaN, y: 40 };
  const invalid = await detector.detect(fakePixelMap('invalid'));
  assert.equal(invalid.complete, false);
  face.points[0] = { x: 20, y: 40 };
  face.rect = { left: 10, top: 20, width: 300, height: 120 };
  const outOfBounds = await detector.detect(fakePixelMap('out-of-bounds'));
  assert.equal(outOfBounds.complete, false);
});

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => {
    resolve = ok;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function fakePixelMap(name) {
  return {
    name,
    releases: 0,
    release() {
      this.releases += 1;
    },
    async getImageInfo() {
      return { size: { width: 200, height: 200 } };
    }
  };
}

test('latest-frame analyzer runs one inference and drops rather than queues while busy', async () => {
  const { LatestFrameAnalyzer } = visionModule();
  const pending = deferred();
  let active = 0;
  let maximumActive = 0;
  const detector = {
    async init() {},
    async detect() {
      active += 1;
      maximumActive = Math.max(maximumActive, active);
      const value = await pending.promise;
      active -= 1;
      return value;
    },
    async release() {}
  };
  const metrics = { records: [], record(value) { this.records.push(value); } };
  const delivered = [];
  const clock = { nowMs: () => 100 };
  const analyzer = new LatestFrameAnalyzer(detector, metrics, (_frame, analysis) => delivered.push(analysis), clock);
  analyzer.beginSession('session-1');

  const firstPixel = fakePixelMap('first');
  const secondPixel = fakePixelMap('second');
  const first = analyzer.offer({
    frameId: 1,
    sessionToken: 'session-1',
    capturedAtMs: 10,
    pixelMap: firstPixel
  });
  await Promise.resolve();
  const dropped = await analyzer.offer({
    frameId: 2,
    sessionToken: 'session-1',
    capturedAtMs: 20,
    pixelMap: secondPixel
  });
  assert.equal(dropped.status, 'DROPPED_BUSY');
  assert.equal(secondPixel.releases, 1);
  assert.equal(metrics.records.at(-1).errorCode, 'DROPPED_BUSY');

  pending.resolve({ faceCount: 1 });
  const completed = await first;
  assert.equal(completed.status, 'PROCESSED');
  assert.equal(firstPixel.releases, 1);
  assert.equal(maximumActive, 1);
  assert.equal(delivered.length, 1);
});

test('session changes and destroy discard late results and release every PixelMap once', async () => {
  const { LatestFrameAnalyzer } = visionModule();
  const pending = deferred();
  let detectorReleases = 0;
  const detector = {
    async init() {},
    async detect() { return pending.promise; },
    async release() { detectorReleases += 1; }
  };
  const metrics = { record() {} };
  const delivered = [];
  const clock = { nowMs: () => 100 };
  const analyzer = new LatestFrameAnalyzer(detector, metrics, (_frame, analysis) => delivered.push(analysis), clock);
  analyzer.beginSession('session-1');
  const pixel = fakePixelMap('late');
  const resultPromise = analyzer.offer({
    frameId: 1,
    sessionToken: 'session-1',
    capturedAtMs: 10,
    pixelMap: pixel
  });
  await Promise.resolve();
  analyzer.beginSession('session-2');
  pending.resolve({ faceCount: 1 });
  const result = await resultPromise;
  assert.equal(result.status, 'STALE_SESSION');
  assert.equal(delivered.length, 0);
  assert.equal(pixel.releases, 1);

  await analyzer.destroy();
  assert.equal(detectorReleases, 1);
  const afterDestroyPixel = fakePixelMap('after-destroy');
  const afterDestroy = await analyzer.offer({
    frameId: 2,
    sessionToken: 'session-2',
    capturedAtMs: 20,
    pixelMap: afterDestroyPixel
  });
  assert.equal(afterDestroy.status, 'DESTROYED');
  assert.equal(afterDestroyPixel.releases, 1);
});

test('analyzer rejects inactive sessions, uses one clock domain, and waits for pending detect before release', async () => {
  const { LatestFrameAnalyzer } = visionModule();
  const pending = deferred();
  let detectCalls = 0;
  let releases = 0;
  const detector = {
    async init() {},
    async detect() { detectCalls += 1; return pending.promise; },
    async release() { releases += 1; }
  };
  const records = [];
  const metrics = { record(value) { records.push(value); } };
  const ticks = [110, 150, 155];
  const clock = { nowMs: () => ticks.shift() ?? 155 };
  const delivered = [];
  const analyzer = new LatestFrameAnalyzer(detector, metrics, (frame, analysis) => delivered.push({ frame, analysis }), clock);

  const inactivePixel = fakePixelMap('inactive');
  const inactive = await analyzer.offer({ frameId: 1, sessionToken: '', capturedAtMs: 100, pixelMap: inactivePixel });
  assert.equal(inactive.status, 'STALE_SESSION');
  assert.equal(detectCalls, 0);
  assert.equal(inactivePixel.releases, 1);
  assert.throws(() => analyzer.beginSession(''));

  analyzer.beginSession('session-1');
  const pixel = fakePixelMap('pending-destroy');
  const offerPromise = analyzer.offer({
    frameId: 2,
    sessionToken: 'session-1',
    capturedAtMs: 100,
    normalizedAtMs: 105,
    pixelMap: pixel
  });
  await Promise.resolve();
  const destroyPromise = analyzer.destroy();
  await Promise.resolve();
  assert.equal(releases, 0);
  pending.resolve({ faceCount: 1 });
  const [outcome] = await Promise.all([offerPromise, destroyPromise]);
  assert.equal(outcome.status, 'STALE_SESSION');
  assert.equal(releases, 1);
  assert.equal(pixel.releases, 1);
  assert.equal(delivered.length, 0);
});

test('all offer paths await asynchronous PixelMap release and concurrent destroy callers share release', async () => {
  const { LatestFrameAnalyzer } = visionModule();
  const detectorRelease = deferred();
  let detectorReleaseCalls = 0;
  const detector = {
    async init() {},
    async detect() { return { faceCount: 0 }; },
    async release() { detectorReleaseCalls += 1; return detectorRelease.promise; }
  };
  const analyzer = new LatestFrameAnalyzer(detector, { record() {} }, () => {}, { nowMs: () => 0 });
  const pixelRelease = deferred();
  const pixel = {
    releases: 0,
    release() { this.releases += 1; return pixelRelease.promise; }
  };
  let offerSettled = false;
  const offerPromise = analyzer.offer({ frameId: 1, sessionToken: '', capturedAtMs: 0, pixelMap: pixel });
  offerPromise.then(() => { offerSettled = true; });
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(offerSettled, false);
  pixelRelease.resolve();
  assert.equal((await offerPromise).status, 'STALE_SESSION');
  assert.equal(pixel.releases, 1);

  const rejectedPixel = { release: async () => { throw new Error('release failed'); } };
  assert.equal((await analyzer.offer({
    frameId: 2,
    sessionToken: '',
    capturedAtMs: 0,
    pixelMap: rejectedPixel
  })).status, 'STALE_SESSION');

  const firstDestroy = analyzer.destroy();
  await Promise.resolve();
  const secondDestroy = analyzer.destroy();
  let secondSettled = false;
  secondDestroy.then(() => { secondSettled = true; });
  await Promise.resolve();
  assert.equal(secondSettled, false);
  assert.equal(detectorReleaseCalls, 1);
  detectorRelease.resolve();
  await Promise.all([firstDestroy, secondDestroy]);
  assert.equal(detectorReleaseCalls, 1);
});
