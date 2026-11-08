import http from '@ohos.net.http';
import { image } from '@kit.ImageKit';

export interface CameraPreviewFrame {
  pixels: image.PixelMap;
  sequence: string;
  requestMs: number;
  decodeMs: number;
}

export class CameraFrameClient {
  private active?: http.HttpRequest;

  cancel(): void {
    this.active?.destroy();
    this.active = undefined;
  }

  async fetch(url: string, previousSequence: string): Promise<CameraPreviewFrame | undefined> {
    const request = http.createHttp();
    this.active = request;
    let source: image.ImageSource | undefined = undefined;
    try {
      const started = Date.now();
      const response = await request.request(url, {
        method: http.RequestMethod.GET,
        expectDataType: http.HttpDataType.ARRAY_BUFFER,
        header: { 'Cache-Control': 'no-cache' },
        usingCache: false,
        connectTimeout: 1500,
        readTimeout: 1500,
      });
      // The relay is reachable but waiting for a fresh source frame.
      if (response.responseCode === 204) return undefined;
      if (response.responseCode !== 200) throw new Error('No fresh camera frame');
      const headers = response.header as Record<string, string>;
      const sequence = headers['x-camera-sequence'] || headers['X-Camera-Sequence'] || '';
      if (sequence !== '' && sequence === previousSequence) return undefined;
      const bytes = response.result as ArrayBuffer;
      if (!(bytes instanceof ArrayBuffer) || bytes.byteLength === 0 || bytes.byteLength > 1024 * 1024) {
        throw new Error('Invalid camera frame');
      }
      const received = Date.now();
      source = image.createImageSource(bytes);
      const pixels = await source.createPixelMap();
      return { pixels, sequence, requestMs: received - started, decodeMs: Date.now() - received };
    } finally {
      try {
        if (source !== undefined) await source.release();
      } finally {
        request.destroy();
        if (this.active === request) this.active = undefined;
      }
    }
  }
}
