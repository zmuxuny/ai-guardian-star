import { describe, beforeAll, beforeEach, afterEach, afterAll, it, expect } from '@ohos/hypium';
import { getWindowSizeClass } from '../main/ets/common/ResponsiveLayout';
import { EventType, parseAlert } from '../main/ets/common/MqttParser';
import { buildRecordingDays, recordingQueryErrorText } from '../main/ets/common/RecordingService';

export default function localUnitTest() {
  describe('localUnitTest', () => {
    // Defines a test suite. Two parameters are supported: test suite name and test suite function.
    beforeAll(() => {
      // Presets an action, which is performed only once before all test cases of the test suite start.
      // This API supports only one parameter: preset action function.
    });
    beforeEach(() => {
      // Presets an action, which is performed before each unit test case starts.
      // The number of execution times is the same as the number of test cases defined by **it**.
      // This API supports only one parameter: preset action function.
    });
    afterEach(() => {
      // Presets a clear action, which is performed after each unit test case ends.
      // The number of execution times is the same as the number of test cases defined by **it**.
      // This API supports only one parameter: clear action function.
    });
    afterAll(() => {
      // Presets a clear action, which is performed after all test cases of the test suite end.
      // This API supports only one parameter: clear action function.
    });
    it('assertContain', 0, () => {
      // Defines a test case. This API supports three parameters: test case name, filter parameter, and test case function.
      let a = 'abc';
      let b = 'b';
      // Defines a variety of assertion methods, which are used to declare expected boolean conditions.
      expect(a).assertContain(b);
      expect(a).assertEqual(a);
    });
    it('classifies current window width instead of device model', 0, () => {
      expect(getWindowSizeClass(360)).assertEqual('compact');
      expect(getWindowSizeClass(599)).assertEqual('compact');
      expect(getWindowSizeClass(600)).assertEqual('medium');
      expect(getWindowSizeClass(839)).assertEqual('medium');
      expect(getWindowSizeClass(840)).assertEqual('expanded');
    });
    it('classifies heartbeat without treating it as a normal monitoring event', 0, () => {
      const heartbeat = parseAlert('{"event":"heartbeat","deviceId":"ascend_board"}');
      expect(heartbeat.type).assertEqual(EventType.HEARTBEAT);
      expect(heartbeat.raw).assertEqual('heartbeat');
    });
  });

  describe('recordingDayBuckets', () => {
    const RETENTION: number = 168 * 3600000;
    // 固定本地时间 2026-10-26 19:30，保证断言与运行当天无关。
    const NOW: number = new Date(2026, 9, 26, 19, 30, 0, 0).getTime();
    const RETENTION_START: number = NOW - RETENTION;

    it('lists local calendar days from today to the oldest one', 0, () => {
      const days = buildRecordingDays(NOW, RETENTION);
      expect(days.length).assertEqual(8);
      expect(days[0].label).assertEqual('今天');
      expect(days[0].windowEnd).assertEqual(NOW);
      expect(days[0].windowStart).assertEqual(new Date(2026, 9, 26, 0, 0, 0, 0).getTime());
      expect(days[1].label).assertEqual('10月25日');
      expect(days[1].windowStart).assertEqual(new Date(2026, 9, 25, 0, 0, 0, 0).getTime());
      expect(days[1].windowEnd).assertEqual(days[0].windowStart);
      expect(days[2].label).assertEqual('10月24日');
      expect(days[days.length - 1].label).assertEqual('10月19日');
    });

    it('covers the whole rolling window without overlap or holes', 0, () => {
      const days = buildRecordingDays(NOW, RETENTION);
      expect(days[days.length - 1].windowStart).assertEqual(RETENTION_START);
      expect(days[0].windowEnd).assertEqual(NOW);
      for (let index = 1; index < days.length; index++) {
        expect(days[index].windowEnd).assertEqual(days[index - 1].windowStart);
        expect(days[index].windowStart < days[index].windowEnd).assertTrue();
      }
    });

    it('marks the oldest day as partial when it starts before the window', 0, () => {
      const days = buildRecordingDays(NOW, RETENTION);
      const oldest = days[days.length - 1];
      expect(oldest.partial).assertTrue();
      expect(oldest.windowStart).assertEqual(RETENTION_START);
      for (let index = 0; index < days.length - 1; index++) {
        expect(days[index].partial).assertFalse();
      }
    });

    it('returns a single partial day when the window is shorter than today', 0, () => {
      const shorter = buildRecordingDays(NOW, 3 * 3600000);
      expect(shorter.length).assertEqual(1);
      expect(shorter[0].label).assertEqual('今天');
      expect(shorter[0].partial).assertTrue();
      expect(shorter[0].windowStart).assertEqual(NOW - 3 * 3600000);
      expect(shorter[0].windowEnd).assertEqual(NOW);
    });

    it('reports recording query timeouts separately from a broken network', 0, () => {
      expect(recordingQueryErrorText(0, 2300028)).assertEqual('录像服务响应超时，请重试');
      expect(recordingQueryErrorText(0, 2300007)).assertEqual('网络不可用，请检查连接');
      expect(recordingQueryErrorText(0, undefined)).assertEqual('网络不可用，请检查连接');
    });
  });
}
