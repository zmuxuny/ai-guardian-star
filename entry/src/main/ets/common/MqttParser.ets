/**
 * MqttParser.ets — MQTT 消息解析（纯函数，无副作用，可独立测试）
 */
export enum EventType {
  FALL = 'fall',
  SEDENTARY = 'sedentary',
  STRANGER = 'stranger',
  NORMAL = 'normal',
  UNKNOWN = 'unknown',
}

export interface AlertResult {
  type: EventType;
  raw: string; // 原始 event 字段值（用于日志）
}

/** ArrayBuffer → 字符串 */
export function payloadToString(payload: string | ArrayBuffer): string {
  if (typeof payload === 'string') return payload;
  try {
    const uint8Array = new Uint8Array(payload as ArrayBuffer);
    const charCodes: number[] = [];
    for (let i = 0; i < uint8Array.length; i++) charCodes.push(uint8Array[i]);
    return String.fromCharCode(...charCodes);
  } catch (_e) {
    return '';
  }
}

/** 解析 JSON 并分类事件类型 */
export function parseAlert(payload: string | ArrayBuffer): AlertResult {
  const content = payloadToString(payload);
  if (!content) return { type: EventType.UNKNOWN, raw: '' };

  try {
    const data = JSON.parse(content) as Record<string, string | number>;
    const eventField = String(data.event ?? data.alert_type ?? data.type ?? '').toLowerCase().trim();
    if (eventField === '' || eventField === 'null' || eventField === 'none') {
      return { type: EventType.NORMAL, raw: eventField };
    }

    const hasFall = eventField.includes('fall') || eventField.includes('跌倒');
    const hasSedentary = eventField.includes('sedentary') || eventField.includes('久坐') ||
      eventField.includes('sitting_long') || eventField.includes('sit');
    const hasNormal = eventField.includes('no fall') || eventField.includes('normal') ||
      eventField.includes('stand') || eventField.includes('walk');
    const hasStranger = eventField.includes('stranger');

    if (hasStranger && !hasNormal) return { type: EventType.STRANGER, raw: eventField };
    if (hasFall && !hasNormal && !hasSedentary) return { type: EventType.FALL, raw: eventField };
    if (hasSedentary && !hasNormal) return { type: EventType.SEDENTARY, raw: eventField };
    return { type: EventType.NORMAL, raw: eventField };
  } catch (_e) {
    return { type: EventType.UNKNOWN, raw: '' };
  }
}
