export type WindowSizeClass = 'compact' | 'medium' | 'expanded';

export function getWindowSizeClass(width: number): WindowSizeClass {
  if (width >= 840) return 'expanded';
  if (width >= 600) return 'medium';
  return 'compact';
}
