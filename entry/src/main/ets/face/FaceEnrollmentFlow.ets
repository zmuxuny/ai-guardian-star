import {
  normalizeFaceEnrollmentName,
  validateFaceEnrollmentName,
} from './FaceEnrollmentName';

export type FaceEnrollmentStep = 'name' | 'capture';

export interface FaceEnrollmentTransition {
  step: FaceEnrollmentStep;
  normalizedName: string;
  message: string;
}

export function advanceFaceEnrollmentFromName(value: string): FaceEnrollmentTransition {
  const normalizedName = normalizeFaceEnrollmentName(value);
  const validation = validateFaceEnrollmentName(value);
  if (!validation.isValid) {
    return { step: 'name', normalizedName: normalizedName, message: validation.message };
  }
  return { step: 'capture', normalizedName: normalizedName, message: '' };
}
