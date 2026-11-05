import faceDetector from '@hms.ai.face.faceDetector';
import { image } from '@kit.ImageKit';

export interface FacePointData {
  x: number;
  y: number;
}

export interface FaceRectData {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface FaceAnalysis {
  faceCount: number;
  probability?: number;
  yaw?: number;
  pitch?: number;
  roll?: number;
  unblocked: boolean;
  complete: boolean;
  rect?: FaceRectData;
  points: FacePointData[];
}

export interface FaceDetectorPort {
  init(): Promise<void>;
  detect(pixelMap: image.PixelMap): Promise<FaceAnalysis>;
  release(): Promise<void>;
}

export interface AnalysisFrame {
  frameId: number;
  sessionToken: string;
  capturedAtMs: number;
  normalizedAtMs?: number;
  pixelMap: image.PixelMap;
}

export interface AnalysisFrameMetadata {
  frameId: number;
  sessionToken: string;
  capturedAtMs: number;
  normalizedAtMs?: number;
}

export type AnalysisStatus = 'PROCESSED' | 'DROPPED_BUSY' | 'STALE_SESSION' |
  'DESTROYED' | 'DETECTOR_ERROR';

export interface AnalysisOutcome {
  status: AnalysisStatus;
  analysis?: FaceAnalysis;
}

export interface AnalysisMetric {
  processed: boolean;
  latencyMs: number;
  normalizeMs?: number;
  detectMs?: number;
  gateMs?: number;
  endToEndMs?: number;
  errorCode?: string;
}

export interface AnalysisMetricsPort {
  record(frame: AnalysisMetric): void;
}

export interface MonotonicClockPort {
  nowMs(): number;
}

export type AnalysisConsumer = (frame: AnalysisFrameMetadata, analysis: FaceAnalysis) => void;

export class CoreVisionFaceDetector implements FaceDetectorPort {
  async init(): Promise<void> {
    const configuration: faceDetector.FaceRecognitionConfiguration = { faceBlock: true };
    const initialized: boolean = await faceDetector.init(configuration);
    if (!initialized) {
      throw new Error('FACE_DETECTOR_INIT_FAILED');
    }
  }

  async detect(pixelMap: image.PixelMap): Promise<FaceAnalysis> {
    const imageInfo: image.ImageInfo = await pixelMap.getImageInfo();
    const visionInfo: faceDetector.VisionInfo = { pixelMap };
    const faces: faceDetector.Face[] = await faceDetector.detect(visionInfo);
    if (faces.length !== 1) {
      const multiple: FaceAnalysis = {
        faceCount: faces.length,
        unblocked: false,
        complete: false,
        points: []
      };
      return multiple;
    }

    const face: faceDetector.Face = faces[0];
    const points: FacePointData[] = face.points.map((point: faceDetector.FacePoint) => {
      const mapped: FacePointData = { x: point.x, y: point.y };
      return mapped;
    });
    const rect: FaceRectData = {
      left: face.rect.left,
      top: face.rect.top,
      width: face.rect.width,
      height: face.rect.height
    };
    const finitePoints: boolean = points.length === 5 &&
      points.every((point: FacePointData) => Number.isFinite(point.x) && Number.isFinite(point.y));
    const finiteRect: boolean = Number.isFinite(rect.left) && Number.isFinite(rect.top) &&
      Number.isFinite(rect.width) && Number.isFinite(rect.height) && rect.left >= 0 && rect.top >= 0 &&
      rect.width > 0 && rect.height > 0 && rect.left + rect.width <= imageInfo.size.width &&
      rect.top + rect.height <= imageInfo.size.height;
    const pointsInside: boolean = finiteRect && finitePoints && points.every((point: FacePointData) =>
      point.x >= rect.left && point.x <= rect.left + rect.width &&
      point.y >= rect.top && point.y <= rect.top + rect.height);
    const orderedLandmarks: boolean = points.length === 5 && points[0].x < points[1].x &&
      points[3].x < points[4].x &&
      (points[0].y + points[1].y) / 2 < (points[3].y + points[4].y) / 2;
    const finitePose: boolean = Number.isFinite(face.pose.yaw) && Number.isFinite(face.pose.pitch) &&
      Number.isFinite(face.pose.roll);
    const finiteProbability: boolean = Number.isFinite(face.probability) &&
      face.probability >= 0 && face.probability <= 1;
    const unblocked: boolean = face.block === faceDetector.FaceBlock.UNBLOCKED;
    const result: FaceAnalysis = {
      faceCount: 1,
      probability: face.probability,
      yaw: face.pose.yaw,
      pitch: face.pose.pitch,
      roll: face.pose.roll,
      unblocked,
      complete: unblocked && finiteProbability && pointsInside && orderedLandmarks && finitePose,
      rect,
      points
    };
    return result;
  }

  async release(): Promise<void> {
    await faceDetector.release();
  }
}

export class LatestFrameAnalyzer {
  private busy: boolean = false;
  private destroyed: boolean = false;
  private detectorReleased: boolean = false;
  private destroyPromise?: Promise<void>;
  private sessionActive: boolean = false;
  private activeSessionToken: string = '';
  private activeOfferDone?: Promise<void>;
  private finishActiveOffer?: () => void;

  constructor(private readonly detector: FaceDetectorPort,
    private readonly metrics: AnalysisMetricsPort,
    private readonly consumer: AnalysisConsumer,
    private readonly clock: MonotonicClockPort) {
  }

  async init(): Promise<void> {
    await this.detector.init();
  }

  beginSession(sessionToken: string): void {
    if (this.destroyed || sessionToken.trim().length === 0) {
      throw new Error('INVALID_SESSION_TOKEN');
    }
    this.activeSessionToken = sessionToken;
    this.sessionActive = true;
  }

  endSession(): void {
    this.sessionActive = false;
    this.activeSessionToken = '';
  }

  async offer(frame: AnalysisFrame): Promise<AnalysisOutcome> {
    if (this.destroyed) {
      await this.releasePixelMap(frame.pixelMap);
      return this.outcome('DESTROYED');
    }
    if (!this.sessionActive || frame.sessionToken.length === 0 ||
      frame.sessionToken !== this.activeSessionToken) {
      await this.releasePixelMap(frame.pixelMap);
      this.metrics.record({ processed: false, latencyMs: 0, errorCode: 'STALE_SESSION' });
      return this.outcome('STALE_SESSION');
    }
    if (this.busy) {
      await this.releasePixelMap(frame.pixelMap);
      this.metrics.record({ processed: false, latencyMs: 0, errorCode: 'DROPPED_BUSY' });
      return this.outcome('DROPPED_BUSY');
    }

    this.busy = true;
    this.activeOfferDone = new Promise<void>((resolve: () => void) => {
      this.finishActiveOffer = resolve;
    });
    const acceptedSession: string = frame.sessionToken;
    const detectStartedAtMs: number = this.clock.nowMs();
    try {
      const analysis: FaceAnalysis = await this.detector.detect(frame.pixelMap);
      const detectFinishedAtMs: number = this.clock.nowMs();
      if (this.destroyed || !this.sessionActive || acceptedSession !== this.activeSessionToken) {
        this.metrics.record({ processed: false, latencyMs: 0, errorCode: 'STALE_SESSION' });
        return this.outcome('STALE_SESSION');
      }
      const gateStartedAtMs: number = this.clock.nowMs();
      const metadata: AnalysisFrameMetadata = {
        frameId: frame.frameId,
        sessionToken: frame.sessionToken,
        capturedAtMs: frame.capturedAtMs,
        normalizedAtMs: frame.normalizedAtMs
      };
      this.consumer(metadata, analysis);
      const finishedAtMs: number = this.clock.nowMs();
      const normalizedAtMs: number = frame.normalizedAtMs === undefined ? detectStartedAtMs : frame.normalizedAtMs;
      const endToEndMs: number = Math.max(0, finishedAtMs - frame.capturedAtMs);
      this.metrics.record({
        processed: true,
        latencyMs: endToEndMs,
        normalizeMs: Math.max(0, normalizedAtMs - frame.capturedAtMs),
        detectMs: Math.max(0, detectFinishedAtMs - detectStartedAtMs),
        gateMs: Math.max(0, finishedAtMs - gateStartedAtMs),
        endToEndMs
      });
      const processed: AnalysisOutcome = { status: 'PROCESSED', analysis };
      return processed;
    } catch {
      this.metrics.record({ processed: false, latencyMs: 0, errorCode: 'DETECTOR_ERROR' });
      return this.outcome('DETECTOR_ERROR');
    } finally {
      await this.releasePixelMap(frame.pixelMap);
      this.busy = false;
      const finish: (() => void) | undefined = this.finishActiveOffer;
      this.finishActiveOffer = undefined;
      this.activeOfferDone = undefined;
      if (finish !== undefined) {
        finish();
      }
    }
  }

  destroy(): Promise<void> {
    if (this.destroyPromise !== undefined) {
      return this.destroyPromise;
    }
    this.destroyed = true;
    this.endSession();
    this.destroyPromise = this.performDestroy();
    return this.destroyPromise;
  }

  private async performDestroy(): Promise<void> {
    const pending: Promise<void> | undefined = this.activeOfferDone;
    if (pending !== undefined) {
      await pending;
    }
    if (!this.detectorReleased) {
      this.detectorReleased = true;
      await this.detector.release();
    }
  }

  private outcome(status: AnalysisStatus): AnalysisOutcome {
    const result: AnalysisOutcome = { status };
    return result;
  }

  private async releasePixelMap(pixelMap: image.PixelMap): Promise<void> {
    try {
      await pixelMap.release();
    } catch {
      // The frame is already invalid; release remains best-effort and must not mask the outcome.
    }
  }
}
