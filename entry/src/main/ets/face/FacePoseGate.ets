import type {
  GateResetReason,
  PoseGateReason,
  PoseGateSample,
  PoseGateState
} from './FaceProbeTypes';

const MAX_SAMPLE_AGE_MS: number = 300;
const MAX_SAMPLE_GAP_MS: number = 300;
const REQUIRED_STABLE_MS: number = 500;
const REQUIRED_DISTINCT_FRAMES: number = 5;

interface GateFailure {
  reason: PoseGateReason;
  prompt: string;
}

export class FacePoseGate {
  private validFrameCount: number = 0;
  private stableSinceMs?: number;
  private lastValidCapturedAtMs?: number;
  private lastSeenFrameId?: number;
  private lastSeenCapturedAtMs?: number;
  private lastSeenReceivedAtMs?: number;
  private lastState: PoseGateState = this.state(false, 'stabilizing', '请保持当前姿势');

  accept(sample: PoseGateSample): PoseGateState {
    if (!this.isFiniteSample(sample)) {
      this.clearWindow();
      return this.remember(this.state(false, 'invalid_pose', '未检测到有效头姿，请重新对准'));
    }

    if (this.isOutOfOrder(sample)) {
      this.clearWindow();
      return this.remember(this.state(false, 'out_of_order', '检测结果异常，请重新对准'));
    }

    if (sample.receivedAtMs - sample.capturedAtMs > MAX_SAMPLE_AGE_MS) {
      this.clearWindow();
      this.updateOrdering(sample);
      return this.remember(this.state(false, 'stale', '检测结果已过期，请保持姿势'));
    }

    const failure: GateFailure | undefined = this.singleFrameFailure(sample);
    if (failure !== undefined) {
      this.clearWindow();
      if (sample.frameId !== this.lastSeenFrameId) {
        this.updateOrdering(sample);
      }
      return this.remember(this.state(false, failure.reason, failure.prompt));
    }

    if (sample.frameId === this.lastSeenFrameId) {
      return this.remember(this.state(false, 'out_of_order', '检测结果重复，请保持姿势'));
    }

    this.updateOrdering(sample);

    if (this.lastValidCapturedAtMs !== undefined &&
      sample.capturedAtMs - this.lastValidCapturedAtMs > MAX_SAMPLE_GAP_MS) {
      this.clearWindow();
    }

    if (this.stableSinceMs === undefined) {
      this.stableSinceMs = sample.capturedAtMs;
    }
    this.validFrameCount += 1;
    this.lastValidCapturedAtMs = sample.capturedAtMs;

    const stableDuration: number = sample.capturedAtMs - this.stableSinceMs;
    const allowed: boolean = this.validFrameCount >= REQUIRED_DISTINCT_FRAMES &&
      stableDuration >= REQUIRED_STABLE_MS;
    if (allowed) {
      return this.remember(this.state(true, 'ready', '角度合格，可以拍摄'));
    }
    return this.remember(this.state(false, 'stabilizing', '请保持当前姿势'));
  }

  reset(_reason: GateResetReason): void {
    this.clearWindow();
    this.lastSeenFrameId = undefined;
    this.lastSeenCapturedAtMs = undefined;
    this.lastSeenReceivedAtMs = undefined;
    this.lastState = this.state(false, 'stabilizing', '请保持当前姿势');
  }

  stateAt(nowMs: number): PoseGateState {
    if (!this.lastState.allowed) {
      return this.lastState;
    }
    if (!Number.isFinite(nowMs) || this.lastSeenReceivedAtMs === undefined ||
      nowMs < this.lastSeenReceivedAtMs || nowMs - this.lastSeenReceivedAtMs > MAX_SAMPLE_AGE_MS) {
      this.clearWindow();
      return this.remember(this.state(false, 'stale', '检测结果已过期，请保持姿势'));
    }
    return this.lastState;
  }

  private singleFrameFailure(sample: PoseGateSample): GateFailure | undefined {
    if (!sample.singleFace) {
      return { reason: 'face_count', prompt: '请确保画面中只有一张人脸' };
    }
    if (!sample.livenessMatched) {
      return { reason: 'liveness', prompt: '请先完成活体检测' };
    }
    if (!sample.complete) {
      return { reason: 'completeness', prompt: '请将完整面部放入取景框' };
    }
    if (!sample.clear) {
      return { reason: 'clarity', prompt: '请保持光线充足并避免晃动' };
    }
    if (sample.roll < -15 || sample.roll > 15) {
      return { reason: 'roll', prompt: '请保持头部水平' };
    }
    if (sample.pitch < -20) {
      return { reason: 'pitch', prompt: '请抬头' };
    }
    if (sample.pitch > 20) {
      return { reason: 'pitch', prompt: '请低头' };
    }
    if (sample.pose === 'front') {
      if (sample.yaw < -15) {
        return { reason: 'yaw', prompt: '请向右转回正面' };
      }
      if (sample.yaw > 15) {
        return { reason: 'yaw', prompt: '请向左转回正面' };
      }
    } else if (sample.pose === 'left' && sample.yaw > -25) {
      return { reason: 'yaw', prompt: '请继续向左转头' };
    } else if (sample.pose === 'right' && sample.yaw < 25) {
      return { reason: 'yaw', prompt: '请继续向右转头' };
    }
    return undefined;
  }

  private isFiniteSample(sample: PoseGateSample): boolean {
    return Number.isFinite(sample.frameId) && Number.isInteger(sample.frameId) &&
      Number.isFinite(sample.capturedAtMs) && Number.isFinite(sample.receivedAtMs) &&
      Number.isFinite(sample.yaw) && Number.isFinite(sample.pitch) &&
      Number.isFinite(sample.roll) && sample.receivedAtMs >= sample.capturedAtMs;
  }

  private isOutOfOrder(sample: PoseGateSample): boolean {
    return (this.lastSeenFrameId !== undefined && sample.frameId < this.lastSeenFrameId) ||
      (this.lastSeenCapturedAtMs !== undefined && sample.capturedAtMs < this.lastSeenCapturedAtMs) ||
      (this.lastSeenReceivedAtMs !== undefined && sample.receivedAtMs < this.lastSeenReceivedAtMs);
  }

  private updateOrdering(sample: PoseGateSample): void {
    this.lastSeenFrameId = sample.frameId;
    this.lastSeenCapturedAtMs = sample.capturedAtMs;
    this.lastSeenReceivedAtMs = sample.receivedAtMs;
  }

  private clearWindow(): void {
    this.validFrameCount = 0;
    this.stableSinceMs = undefined;
    this.lastValidCapturedAtMs = undefined;
  }

  private state(allowed: boolean, reason: PoseGateReason, prompt: string): PoseGateState {
    const current: PoseGateState = {
      allowed,
      reason,
      prompt,
      validFrameCount: this.validFrameCount
    };
    if (this.stableSinceMs !== undefined) {
      current.stableSinceMs = this.stableSinceMs;
    }
    return current;
  }

  private remember(state: PoseGateState): PoseGateState {
    this.lastState = state;
    return state;
  }
}
