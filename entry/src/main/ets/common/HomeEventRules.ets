/** Homepage event rules shared with the MQTT event writer. */
export function isHomeEventType(type: string): boolean {
  return type === 'fall' || type === 'sedentary' || type === 'stranger';
}

export function homeEventTitle(type: string): string {
  if (type === 'fall') return '摔倒告警';
  if (type === 'sedentary') return '久坐提醒';
  if (type === 'stranger') return '陌生人到来';
  return '监护事件';
}

/** Five-second repeated stranger alerts belong to one arrival until a 15s gap. */
export function startsStrangerArrival(timestamp: number, lastActivity: number): boolean {
  return lastActivity === 0 || timestamp < lastActivity || timestamp - lastActivity >= 15000;
}
