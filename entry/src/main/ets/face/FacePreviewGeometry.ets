export interface FacePreviewRect {
  surfaceWidth: number;
  surfaceHeight: number;
  offsetX: number;
  offsetY: number;
}

// Sizes use the same unit (physical pixels for an XComponent surface).
// Rotate the stream dimensions first, then apply ONE scale to both axes.
export function facePreviewCoverRect(viewWidth: number, viewHeight: number,
  streamWidth: number, streamHeight: number, rotation: number): FacePreviewRect {
  const swapAxes = Math.abs(rotation % 180) === 90;
  const width = swapAxes ? streamHeight : streamWidth;
  const height = swapAxes ? streamWidth : streamHeight;
  const scale = Math.max(viewWidth / width, viewHeight / height);
  const surfaceWidth = width * scale;
  const surfaceHeight = height * scale;
  return {
    surfaceWidth,
    surfaceHeight,
    offsetX: (viewWidth - surfaceWidth) / 2,
    offsetY: (viewHeight - surfaceHeight) / 2,
  };
}
