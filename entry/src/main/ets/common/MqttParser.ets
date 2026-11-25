/**
 * MqttParser.ets — MQTT 消息解析（纯函数，无副作用，可独立测试）
 */
export enum EventType {
  FALL = 'fall',
  SEDENTARY = 'sedentary',
  STRANGER = 'stranger',
  ROUTINE = 'routine_alert',
  HEARTBEAT = 'heartbeat',
  NORMAL = 'normal',
  UNKNOWN = 'unknown',
}

export interface AlertResult {
  type: EventType;
  raw: string; // 原始 event 字段值（用于日志）
  routine?: RoutineAlert;
}

export interface RoutineAlert {
  eventId: string;
  alertType: string;
  timestamp: number;
  reason: string;
}

export const ROUTINE_ALERT_TOPIC: string = 'ai_guardian/alerts/routine';

export function isRoutineAlertType(type: string): boolean {
  return type === 'late_wakeup' || type === 'daytime_inactivity' || type === 'night_bathroom_stay';
}

/** ArrayBuffer → 字符串 */
export function payloadToString(payload: string | ArrayBuffer): string {
  if (typeof payload === 'string') return payload;
  try {
    const bytes = new Uint8Array(payload);
    const encoded: string[] = [];
    for (let i = 0; i < bytes.length; i++) encoded.push('%' + bytes[i].toString(16).padStart(2, '0'));
    return decodeURIComponent(encoded.join(''));
  } catch (_e) {
    return '';
  }
}

function parseRoutine(data: Record<string, string | number | boolean>): RoutineAlert | undefined {
  const type = data['alert_type'];
  const id = data['event_id'];
  const timestamp = data['timestamp'];
  const reason = data['reason'];
  if (data['event'] !== 'routine_alert' || data['schema_version'] !== '2' ||
    typeof type !== 'string' || !isRoutineAlertType(type) ||
    typeof id !== 'string' || id.trim().length === 0 || id.length > 128 ||
    typeof timestamp !== 'string' || !/T\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(timestamp) ||
    typeof reason !== 'string' || reason.trim().length === 0 || reason.length > 240) return undefined;
  const eventTime = Date.parse(timestamp);
  if (!Number.isFinite(eventTime)) return undefined;
  return { eventId: id.trim(), alertType: type, timestamp: eventTime, reason: reason.trim() };
}

/** 解析 JSON 并分类事件类型 */
export function parseAlert(payload: string | ArrayBuffer): AlertResult {
  const content = payloadToString(payload);
  if (!content) return { type: EventType.UNKNOWN, raw: '' };

  try {
    const data = JSON.parse(content) as Record<string, string | number | boolean>;
    const eventField = String(data.event ?? data.alert_type ?? data.type ?? '').toLowerCase().trim();
    if (eventField === EventType.ROUTINE) {
      const routine = parseRoutine(data);
      return routine ? { type: EventType.ROUTINE, raw: eventField, routine }
        : { type: EventType.UNKNOWN, raw: eventField };
    }
    if (eventField === 'heartbeat') {
      return { type: EventType.HEARTBEAT, raw: eventField };
    }
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
