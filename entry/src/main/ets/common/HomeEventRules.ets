/** Homepage event rules shared with the MQTT event writer. */
export function isHomeEventType(type: string): boolean {
  return type === 'fall' || type === 'sedentary' || type === 'stranger';
}

/** Today's calendar date in the phone's local timezone, not a rolling 24 hours. */
export function isTodayHomeEvent(type: string, timestamp: number, now: number): boolean {
  if (!isHomeEventType(type) || !Number.isFinite(timestamp)) return false;
  const date = new Date(now);
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const end = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1).getTime();
  return timestamp >= start && timestamp < end;
}

export function homeEventAccent(type: string, dark: boolean): string {
  if (type === 'fall') return dark ? '#fca5a5' : '#b91c1c';
  if (type === 'stranger') return dark ? '#fcd34d' : '#946200';
  return dark ? '#93c5fd' : '#2563eb';
}

export function homeEventSurface(type: string, dark: boolean): string {
  if (type === 'fall') return dark ? '#3b2028' : '#fff1f2';
  if (type === 'stranger') return dark ? '#352d18' : '#fff8db';
  return dark ? '#172033' : '#ffffff';
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
