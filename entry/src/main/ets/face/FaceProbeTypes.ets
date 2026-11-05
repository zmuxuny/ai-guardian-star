export type PoseKind = 'front' | 'left' | 'right';

export type GateResetReason = 'manual' | 'background' | 'camera_restart' | 'orientation_change';

export type PoseGateReason = 'face_count' | 'liveness' | 'completeness' | 'clarity' |
  'roll' | 'pitch' | 'yaw' | 'stale' | 'out_of_order' | 'invalid_pose' |
  'stabilizing' | 'ready';

export interface PoseGateSample {
  frameId: number;
  capturedAtMs: number;
  receivedAtMs: number;
  pose: PoseKind;
  yaw: number;
  pitch: number;
  roll: number;
  singleFace: boolean;
  livenessMatched: boolean;
  complete: boolean;
  clear: boolean;
}

export interface PoseGateState {
  allowed: boolean;
  reason: PoseGateReason;
  prompt: string;
  validFrameCount: number;
  stableSinceMs?: number;
}
