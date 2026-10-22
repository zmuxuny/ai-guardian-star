import { CloudService } from './CloudService';

export interface RecordingClip {
  id: string;
  segmentId: string;
  startTime: number;
  endTime: number;
  eventType: string;
  endUnconfirmed: boolean;
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
}

export interface RecordingPlaybackRequest extends RecordingQuery {
  clipId: string;
}

export async function queryRecordings(query: RecordingQuery): Promise<RecordingResult> {
  const response = await CloudService.getInstance().authenticatedPost('/api/recordings/query', query);
  if (response.responseCode === 0) throw new Error('网络不可用，请检查连接');
  if (response.responseCode === 404) throw new Error('录像服务尚未接通，请稍后刷新');
  const result = JSON.parse(response.result) as RecordingResult;
  if (response.responseCode !== 200 || !result.success) throw new Error(result.message || '录像加载失败');
  return result;
}
