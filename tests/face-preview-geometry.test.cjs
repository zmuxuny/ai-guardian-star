const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const ts = require(process.env.GUARDIAN_TYPESCRIPT_PATH || 'typescript');
const file = require('node:path').resolve(__dirname, '../entry/src/main/ets/face/FacePreviewGeometry.ets');
const loaded = new Module(file, module);
loaded._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS }
}).outputText, file);
const { facePreviewCoverRect } = loaded.exports;

// Different viewport shapes and sensor mounting angles must never change a face's proportions.
for (const [name, vw, vh, sw, sh, rotation] of [
  ['tall phone/front sensor', 1224, 1560, 1280, 720, 270],
  ['short emulator/front sensor', 1080, 680, 640, 480, 90],
  ['emulator without sensor rotation', 1080, 680, 640, 480, 0],
  ['landscape', 1560, 700, 1280, 720, 180],
  ['square window', 720, 720, 1920, 1080, 90],
  ['portrait stream', 900, 1200, 720, 1280, 0],
]) {
  test(name + ': uniform scale, full coverage and symmetric crop', () => {
    const rect = facePreviewCoverRect(vw, vh, sw, sh, rotation);
    const rotatedWidth = rotation % 180 === 90 ? sh : sw;
    const rotatedHeight = rotation % 180 === 90 ? sw : sh;
    assert.ok(Math.abs(rect.surfaceWidth / rotatedWidth - rect.surfaceHeight / rotatedHeight) < 1e-9);
    assert.ok(rect.surfaceWidth >= vw - 1e-9 && rect.surfaceHeight >= vh - 1e-9);
    assert.ok(Math.abs(rect.surfaceWidth - vw) < 1e-9 || Math.abs(rect.surfaceHeight - vh) < 1e-9);
    assert.equal(rect.offsetX * 2 + rect.surfaceWidth, vw);
    assert.equal(rect.offsetY * 2 + rect.surfaceHeight, vh);
  });
}
