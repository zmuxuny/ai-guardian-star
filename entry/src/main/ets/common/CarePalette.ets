import { drawing } from '@kit.ArkGraphics2D';

export interface CarePalette {
  label: string;
  detail: string;
  backdrop: string;
  glow: string;
  solid: string;
  accent: string;
  wash: string;
}

const SAFE: CarePalette = {
  label: '家里平安', detail: '设备在线，未收到当前异常提醒',
  backdrop: '#052A1F', glow: '#0B6248', solid: '#0A5C43', accent: '#2FD39A', wash: '#DDF4E9',
};
const REMIND: CarePalette = {
  label: '久坐提醒', detail: '收到久坐提醒，可以通话确认',
  backdrop: '#2E1D00', glow: '#75501A', solid: '#5C3A00', accent: '#F2B544', wash: '#FFF1D4',
};
const FALL: CarePalette = {
  label: '跌倒 · 立即查看', detail: '收到跌倒提醒，请及时确认现场',
  backdrop: '#330A04', glow: '#831F13', solid: '#8C1D0C', accent: '#FF9C86', wash: '#FDE5DF',
};
const UNKNOWN: CarePalette = {
  label: '设备未确认', detail: '等待设备连接后确认当前状态',
  backdrop: '#142824', glow: '#2F4B43', solid: '#345149', accent: '#C5DED4', wash: '#E5EEEA',
};

export function carePalette(fall: boolean, sedentary: boolean, online: boolean): CarePalette {
  if (fall) return FALL;
  if (sedentary) return REMIND;
  return online ? SAFE : UNKNOWN;
}

export function careIconTint(hex: string): drawing.ColorFilter {
  const rgb = parseInt(hex.substring(1), 16);
  return drawing.ColorFilter.createBlendModeColorFilter({
    alpha: 255,
    red: (rgb >> 16) & 255,
    green: (rgb >> 8) & 255,
    blue: rgb & 255,
  }, drawing.BlendMode.SRC_IN);
}
