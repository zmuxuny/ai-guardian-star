const MAX_LATENCY_SAMPLES: number = 600;

export interface ProbeMetricContext {
  deviceModel: string;
  systemVersion: string;
  cameraId: string;
  detectorVersion: string;
  preprocessVersion: string;
}

export type ProbeResetReason = 'manual' | 'background' | 'camera_restart' |
  'orientation_change' | 'gap' | 'stale';

export type ProbeErrorCode = 'STALE' | 'CAMERA_BUSY' | 'DROPPED_BUSY' |
  'STALE_SESSION' | 'DETECTOR_ERROR' | 'CALIBRATION_MISSING' | 'INVALID_POSE' |
  'UNSUPPORTED_OUTPUT_COMBINATION' | 'RETRYABLE';

export interface ProbeFrameMetric {
  processed: boolean;
  latencyMs: number;
  normalizeMs?: number;
  detectMs?: number;
  gateMs?: number;
  endToEndMs?: number;
  resetReason?: ProbeResetReason;
  errorCode?: ProbeErrorCode;
}

export interface MetricCount {
  key: string;
  count: number;
}

export interface StageLatencySnapshot {
  sampleCount: number;
  p50Ms: number;
  p95Ms: number;
  p99Ms: number;
}

export interface ProbeMetricsSnapshot {
  deviceModel: string;
  systemVersion: string;
  cameraId: string;
  detectorVersion: string;
  preprocessVersion: string;
  processedFrames: number;
  droppedFrames: number;
  latencySampleCount: number;
  latencyP50Ms: number;
  latencyP95Ms: number;
  latencyP99Ms: number;
  normalizeLatency: StageLatencySnapshot;
  detectLatency: StageLatencySnapshot;
  gateLatency: StageLatencySnapshot;
  endToEndLatency: StageLatencySnapshot;
  resetReasons: MetricCount[];
  errorCodes: MetricCount[];
}

export class FaceProbeMetrics {
  private readonly context: ProbeMetricContext;
  private readonly latencies: number[] = [];
  private readonly normalizeLatencies: number[] = [];
  private readonly detectLatencies: number[] = [];
  private readonly gateLatencies: number[] = [];
  private readonly endToEndLatencies: number[] = [];
  private readonly resetReasonCounts: MetricCount[] = [];
  private readonly errorCodeCounts: MetricCount[] = [];
  private processedFrames: number = 0;
  private droppedFrames: number = 0;

  constructor(context: ProbeMetricContext) {
    this.context = {
      deviceModel: context.deviceModel,
      systemVersion: context.systemVersion,
      cameraId: context.cameraId,
      detectorVersion: context.detectorVersion,
      preprocessVersion: context.preprocessVersion
    };
  }

  record(frame: ProbeFrameMetric): void {
    if (frame.processed) {
      this.processedFrames += 1;
      if (Number.isFinite(frame.latencyMs) && frame.latencyMs >= 0) {
        this.storeLatency(this.latencies, frame.latencyMs);
      }
      this.storeOptionalLatency(this.normalizeLatencies, frame.normalizeMs);
      this.storeOptionalLatency(this.detectLatencies, frame.detectMs);
      this.storeOptionalLatency(this.gateLatencies, frame.gateMs);
      this.storeOptionalLatency(this.endToEndLatencies, frame.endToEndMs);
    } else {
      this.droppedFrames += 1;
    }
    if (frame.resetReason !== undefined && this.isAllowedResetReason(frame.resetReason)) {
      this.increment(this.resetReasonCounts, frame.resetReason);
    }
    if (frame.errorCode !== undefined && this.isAllowedErrorCode(frame.errorCode)) {
      this.increment(this.errorCodeCounts, frame.errorCode);
    }
  }

  snapshot(): ProbeMetricsSnapshot {
    const orderedLatencies: number[] = this.latencies.slice().sort((left: number, right: number) => left - right);
    const snapshot: ProbeMetricsSnapshot = {
      deviceModel: this.context.deviceModel,
      systemVersion: this.context.systemVersion,
      cameraId: this.context.cameraId,
      detectorVersion: this.context.detectorVersion,
      preprocessVersion: this.context.preprocessVersion,
      processedFrames: this.processedFrames,
      droppedFrames: this.droppedFrames,
      latencySampleCount: orderedLatencies.length,
      latencyP50Ms: this.percentile(orderedLatencies, 0.50),
      latencyP95Ms: this.percentile(orderedLatencies, 0.95),
      latencyP99Ms: this.percentile(orderedLatencies, 0.99),
      normalizeLatency: this.stageSnapshot(this.normalizeLatencies),
      detectLatency: this.stageSnapshot(this.detectLatencies),
      gateLatency: this.stageSnapshot(this.gateLatencies),
      endToEndLatency: this.stageSnapshot(this.endToEndLatencies),
      resetReasons: this.sortedCounts(this.resetReasonCounts),
      errorCodes: this.sortedCounts(this.errorCodeCounts)
    };
    return snapshot;
  }

  private increment(counts: MetricCount[], key: string): void {
    const existing: MetricCount | undefined = counts.find((item: MetricCount) => item.key === key);
    if (existing !== undefined) {
      existing.count += 1;
      return;
    }
    const created: MetricCount = { key, count: 1 };
    counts.push(created);
  }

  private sortedCounts(counts: MetricCount[]): MetricCount[] {
    return counts.map((item: MetricCount) => {
      const copy: MetricCount = { key: item.key, count: item.count };
      return copy;
    }).sort((left: MetricCount, right: MetricCount) => left.key.localeCompare(right.key));
  }

  private storeOptionalLatency(target: number[], value?: number): void {
    if (value !== undefined && Number.isFinite(value) && value >= 0) {
      this.storeLatency(target, value);
    }
  }

  private storeLatency(target: number[], value: number): void {
    target.push(value);
    if (target.length > MAX_LATENCY_SAMPLES) {
      target.shift();
    }
  }

  private stageSnapshot(values: number[]): StageLatencySnapshot {
    const ordered: number[] = values.slice().sort((left: number, right: number) => left - right);
    const snapshot: StageLatencySnapshot = {
      sampleCount: ordered.length,
      p50Ms: this.percentile(ordered, 0.50),
      p95Ms: this.percentile(ordered, 0.95),
      p99Ms: this.percentile(ordered, 0.99)
    };
    return snapshot;
  }

  private percentile(sortedValues: number[], percentile: number): number {
    if (sortedValues.length === 0) {
      return 0;
    }
    const index: number = Math.max(0, Math.ceil(percentile * sortedValues.length) - 1);
    return sortedValues[index];
  }

  private isAllowedResetReason(value: string): boolean {
    return ['manual', 'background', 'camera_restart', 'orientation_change', 'gap', 'stale'].includes(value);
  }

  private isAllowedErrorCode(value: string): boolean {
    return ['STALE', 'CAMERA_BUSY', 'DROPPED_BUSY', 'STALE_SESSION', 'DETECTOR_ERROR',
      'CALIBRATION_MISSING', 'INVALID_POSE', 'UNSUPPORTED_OUTPUT_COMBINATION', 'RETRYABLE'].includes(value);
  }
}
