export type PoseSign = -1 | 1;
export type PoseTransformErrorCode = 'CALIBRATION_MISSING' | 'INVALID_POSE';

export interface RawPose {
  yaw: number;
  pitch: number;
  roll: number;
}

export interface CanonicalPose {
  yaw: number;
  pitch: number;
  roll: number;
}

export interface PoseCalibrationKey {
  deviceModel: string;
  systemVersion: string;
  cameraId: string;
  sensorOrientation: number;
  detectorVersion: string;
  preprocessVersion: string;
}

export interface PoseCalibration {
  key: PoseCalibrationKey;
  yawSign: PoseSign;
  pitchSign: PoseSign;
  rollSign: PoseSign;
  yawOffset: number;
  pitchOffset: number;
  rollOffset: number;
}

export interface PoseNormalizationResult {
  ok: boolean;
  errorCode?: PoseTransformErrorCode;
  pose?: CanonicalPose;
}

export interface FrameTransformSpec {
  sensorOrientation: number;
  displayRotation: number;
  frontFacing: boolean;
  mirroredPreview: boolean;
  outputPixelFormat: 'RGBA_8888';
  outputOrientation: 'portrait';
  outputMirrored: false;
  preserveExifOrientation: false;
}

export function createFrameTransformSpec(sensorOrientation: number, displayRotation: number,
  frontFacing: boolean, mirroredPreview: boolean): FrameTransformSpec {
  const spec: FrameTransformSpec = {
    sensorOrientation,
    displayRotation,
    frontFacing,
    mirroredPreview,
    outputPixelFormat: 'RGBA_8888',
    outputOrientation: 'portrait',
    outputMirrored: false,
    preserveExifOrientation: false
  };
  return spec;
}

export function normalizePose(raw: RawPose, calibration?: PoseCalibration): PoseNormalizationResult {
  if (!isCalibrationValid(calibration)) {
    const missing: PoseNormalizationResult = { ok: false, errorCode: 'CALIBRATION_MISSING' };
    return missing;
  }
  if (!Number.isFinite(raw.yaw) || !Number.isFinite(raw.pitch) || !Number.isFinite(raw.roll)) {
    const invalid: PoseNormalizationResult = { ok: false, errorCode: 'INVALID_POSE' };
    return invalid;
  }

  const pose: CanonicalPose = {
    yaw: raw.yaw * calibration.yawSign + calibration.yawOffset,
    pitch: raw.pitch * calibration.pitchSign + calibration.pitchOffset,
    roll: raw.roll * calibration.rollSign + calibration.rollOffset
  };
  if (!Number.isFinite(pose.yaw) || !Number.isFinite(pose.pitch) || !Number.isFinite(pose.roll)) {
    const invalid: PoseNormalizationResult = { ok: false, errorCode: 'INVALID_POSE' };
    return invalid;
  }
  const result: PoseNormalizationResult = { ok: true, pose };
  return result;
}

export function normalizePoseForKey(raw: RawPose, calibration: PoseCalibration | undefined,
  expectedKey: PoseCalibrationKey): PoseNormalizationResult {
  if (!isCalibrationValid(calibration) || !keysEqual(calibration.key, expectedKey)) {
    const missing: PoseNormalizationResult = { ok: false, errorCode: 'CALIBRATION_MISSING' };
    return missing;
  }
  return normalizePose(raw, calibration);
}

function keysEqual(left: PoseCalibrationKey, right: PoseCalibrationKey): boolean {
  return left.deviceModel === right.deviceModel && left.systemVersion === right.systemVersion &&
    left.cameraId === right.cameraId && left.sensorOrientation === right.sensorOrientation &&
    left.detectorVersion === right.detectorVersion &&
    left.preprocessVersion === right.preprocessVersion;
}

function isCalibrationValid(calibration?: PoseCalibration): calibration is PoseCalibration {
  if (calibration === undefined || calibration.key === undefined) {
    return false;
  }
  const key: PoseCalibrationKey = calibration.key;
  const strings: string[] = [
    key.deviceModel,
    key.systemVersion,
    key.cameraId,
    key.detectorVersion,
    key.preprocessVersion
  ];
  if (strings.some((value: string) => typeof value !== 'string' || value.trim().length === 0)) {
    return false;
  }
  if (![0, 90, 180, 270].includes(key.sensorOrientation)) {
    return false;
  }
  if (!isSign(calibration.yawSign) || !isSign(calibration.pitchSign) ||
    !isSign(calibration.rollSign)) {
    return false;
  }
  return Number.isFinite(calibration.yawOffset) && Number.isFinite(calibration.pitchOffset) &&
    Number.isFinite(calibration.rollOffset);
}

function isSign(value: number): value is PoseSign {
  return value === -1 || value === 1;
}
