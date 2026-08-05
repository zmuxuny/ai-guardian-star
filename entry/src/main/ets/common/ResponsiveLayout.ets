/**
 * ResponsiveLayout.ets — 断点与尺寸档位
 *
 * 断点取值沿用 ArkUI 栅格默认值：600vp / 840vp。
 *
 * 约定：尺寸（width/height/margin/padding）一律用 vp 定值，需要随屏幕变化时用 pick()
 * 按断点挑一档。不要用百分比做尺寸——ArkUI 的百分比相对父容器宽度，父容器从手机的
 * 360vp 变成平板的 1200vp 时所有百分比会被同比放大数倍。
 * 百分比只用于「就是要占满父容器某个比例」的场景，例如 width('100%')。
 */
export type WindowSizeClass = 'compact' | 'medium' | 'expanded';

export function getWindowSizeClass(width: number): WindowSizeClass {
  if (width >= 840) return 'expanded';
  if (width >= 600) return 'medium';
  return 'compact';
}

/** 按断点在三档定值中取一档。 */
export function pick(sizeClass: WindowSizeClass, compact: number, medium: number, expanded: number): number {
  if (sizeClass === 'expanded') return expanded;
  if (sizeClass === 'medium') return medium;
  return compact;
}
