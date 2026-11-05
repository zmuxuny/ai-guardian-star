export interface FaceEnrollmentNameValidation {
  isValid: boolean;
  message: string;
}

const FACE_ENROLLMENT_NAME_MAX_LENGTH: number = 64;

export function normalizeFaceEnrollmentName(value: string): string {
  return value.trim();
}

export function validateFaceEnrollmentName(value: string): FaceEnrollmentNameValidation {
  const normalized = normalizeFaceEnrollmentName(value);
  if (normalized.length === 0) {
    return { isValid: false, message: '请填写人脸用户姓名' };
  }
  if (normalized.length > FACE_ENROLLMENT_NAME_MAX_LENGTH) {
    return { isValid: false, message: '姓名不能超过64个字符' };
  }
  if (normalized === '.' || normalized === '..') {
    return { isValid: false, message: '请填写有效姓名' };
  }
  for (let index = 0; index < normalized.length; index++) {
    const character = normalized[index];
    if (character === '/' || character === '\\' || normalized.charCodeAt(index) < 32) {
      return { isValid: false, message: '姓名不能包含路径符号或控制字符' };
    }
  }
  return { isValid: true, message: '' };
}
