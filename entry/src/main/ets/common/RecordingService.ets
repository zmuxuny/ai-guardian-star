import { CloudService } from './CloudService';
import { ECS_BASE_URL } from '../config';

export interface RecordingClip {
  id: string;
  segmentId: string;
  startTime: number;
  endTime: number;
  eventType: string;
  endUnconfirmed: boolean;
  downloadable?: boolean;
}

export interface RecordingResult {
  success: boolean;
  message?: string;
  asOf: number;
  windowStart: number;
  windowEnd: number;
  status: string;
  clips: RecordingClip[];
  eventCount: number;
  wholeSegments?: boolean;
}

export interface RecordingQuery {
  asOf: number;
  filter: string;
  windowStart: number;
  windowEnd: number;
}

export interface RecordingPlaybackRequest extends RecordingQuery {
  clipId: string;
}

/** 一个本地自然日对应的查询窗口；partial 表示该日只有一部分落在 168 小时留存窗口内。 */
export interface RecordingDayRange {
  key: string;
  label: string;
  windowStart: number;
  windowEnd: number;
  partial: boolean;
}

/** 硬件端异常录像的滚动留存窗口，与录像配置的 168 小时保持一致。 */
export const RECORDING_RETENTION_MS: number = 168 * 3600000;
/** HarmonyOS 网络栈读取超时（curl 28）对应的 BusinessError.code。 */
export const RECORDING_QUERY_TIMEOUT_CODE: number = 2300028;

function localDayStart(timestamp: number): number {
  const date = new Date(timestamp);
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0, 0, 0).getTime();
}

function dayKey(timestamp: number): string {
  const date = new Date(timestamp);
  const month: string = `${date.getMonth() + 1}`.padStart(2, '0');
  const day: string = `${date.getDate()}`.padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function dayLabel(timestamp: number): string {
  const date = new Date(timestamp);
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

/**
 * 按设备本地时区把 [now - retentionMs, now] 切成自然日，顺序从今天到最早一天。
 * 相邻窗口首尾相接且不重叠；最老的一天可能只有部分时段落在留存窗口内。
 */
export function buildRecordingDays(now: number, retentionMs: number): RecordingDayRange[] {
  const retentionStart = now - retentionMs;
  const todayStart = localDayStart(now);
  const days: RecordingDayRange[] = [];
  let segmentEnd = now;
  let dayStart = todayStart;
  while (segmentEnd > retentionStart) {
    const partial = dayStart < retentionStart;
    const windowStart = partial ? retentionStart : dayStart;
    days.push({
      key: dayKey(dayStart),
      label: dayStart === todayStart ? '今天' : dayLabel(dayStart),
      windowStart: windowStart,
      windowEnd: segmentEnd,
      partial: partial
    });
    segmentEnd = dayStart;
    if (dayStart <= retentionStart) break;
    dayStart = localDayStart(dayStart - 1);
  }
  return days;
}

/**
 * 录像查询的错误文案。responseCode === 0 时用原始 BusinessError.code 区分
 * “服务端读取超时”和“本机网络不可用”，避免把超时误报成断网。
 */
export function recordingQueryErrorText(responseCode: number, errorCode?: number): string {
  if (responseCode === 0) {
    return errorCode === RECORDING_QUERY_TIMEOUT_CODE
      ? '录像服务响应超时，请重试'
      : '网络不可用，请检查连接';
  }
  if (responseCode === 404) return '录像服务尚未接通，请稍后刷新';
  return '';
}

export async function queryRecordings(query: RecordingQuery): Promise<RecordingResult> {
  // 只有录像查询放宽到 30 秒读取超时；其他接口保持原有超时不变。
  const response = await CloudService.getInstance().authenticatedPost('/api/recordings/query', query, 30000);
  const errorText = recordingQueryErrorText(response.responseCode, response.errorCode);
  if (errorText !== '') throw new Error(errorText);
  let result: RecordingResult;
  try {
    result = JSON.parse(response.result) as RecordingResult;
  } catch (_error) {
    throw new Error('录像加载失败，请重试');
  }
  if (response.responseCode !== 200 || !result.success) throw new Error(result.message || '录像加载失败');
  return result;
}

interface StreamUrlResult {
  success: boolean;
  message?: string;
  path?: string;
  expires?: number;
}

/** 向云端换取 10 分钟有效的签名播放地址；播放器直接拉流，不落地到本机。 */
export async function requestStreamUrl(body: RecordingPlaybackRequest): Promise<string> {
  const response = await CloudService.getInstance().authenticatedPost('/api/recordings/stream-url', body, 30000);
  if (response.responseCode === 0) throw new Error(recordingQueryErrorText(0, response.errorCode));
  let result: StreamUrlResult;
  try {
    result = JSON.parse(response.result) as StreamUrlResult;
  } catch (_error) {
    throw new Error('录像暂不可用，请重试');
  }
  if (response.responseCode !== 200 || !result.success || !result.path) {
    throw new Error(result.message || '录像暂不可用，请重试');
  }
  return ECS_BASE_URL + result.path;
}