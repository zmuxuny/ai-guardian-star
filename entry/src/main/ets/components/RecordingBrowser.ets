import { ThemeManager } from '../common/ThemeManager';
import { CloudService } from '../common/CloudService';
import { RecordingClip, RecordingQuery, RecordingPlaybackRequest, queryRecordings } from '../common/RecordingService';
import { SURFACE_RADIUS } from './GradientHeader';
import { common } from '@kit.AbilityKit';
import fs from '@ohos.file.fs';
import { media } from '@kit.MediaKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { CacheManager } from '../common/CacheManager';

/** Shared by the navigation tab and the personal/history destination. */
@Component
export struct RecordingBrowser {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State filter: string = 'all';
  @State clips: RecordingClip[] = [];
  @State asOf: number = Date.now();
  @State windowStart: number = Date.now() - 7 * 86400000;
  @State status: string = 'waiting';
  @State wholeSegments: boolean = false;
  @State loading: boolean = true;
  @State error: string = '';
  @State preparing: boolean = false;
  @State playbackError: string = '';
  @State videoSource: string = '';
  @State playing: boolean = false;
  @State videoReady: boolean = false;
  @State playPosition: number = 0;
  @State duration: number = 0;
  @State selectedId: string = '';
  @State selectedLabel: string = '';
  private xController: XComponentController = new XComponentController();
  private avPlayer: media.AVPlayer | undefined = undefined;
  private surfaceId: string = '';
  private mediaLength: number = 0;
  private openFile: fs.File | undefined = undefined;
  private cacheFile: string = '';
  private queryVersion: number = 0;
  private playbackVersion: number = 0;
  private disposed: boolean = false;

  aboutToAppear(): void { this.disposed = false; this.reload(true); }
  aboutToDisappear(): void {
    this.disposed = true;
    this.queryVersion++;
    this.playbackVersion++;
    this.releaseVideo();
  }

  private releaseVideo(): void {
    this.videoSource = '';
    this.stopPlayback();
    if (this.openFile !== undefined) {
      try { fs.closeSync(this.openFile); } catch (_error) {}
      this.openFile = undefined;
    }
    this.mediaLength = 0;
    if (this.cacheFile !== '') {
      try { fs.unlinkSync(this.cacheFile); } catch (_error) {}
      CacheManager.getInstance().release(this.cacheFile);
      this.cacheFile = '';
    }
  }

  /** ArkUI Video 不接受沙箱文件（fd:// 与裸路径都会停在 PLAYER_IDLE），改用 AVPlayer.fdSrc。 */
  private async startPlayback(): Promise<void> {
    const file = this.openFile;
    if (file === undefined || this.surfaceId === '' || this.mediaLength <= 0) return;
    this.stopPlayback();
    const version = this.playbackVersion;
    try {
      const player = await media.createAVPlayer();
      if (this.disposed || version !== this.playbackVersion) {
        player.release().catch((): void => {});
        return;
      }
      this.avPlayer = player;
      player.on('error', (_error: BusinessError): void => {
        this.videoReady = false;
        this.playbackError = '播放失败，请重新下载';
      });
      player.on('stateChange', (state: media.AVPlayerState): void => { this.onPlayerState(state); });
      player.on('timeUpdate', (time: number): void => { this.playPosition = time; });
      const source: media.AVFileDescriptor = { fd: file.fd, offset: 0, length: this.mediaLength };
      player.fdSrc = source;
    } catch (_error) {
      this.playbackError = '播放失败，请重新下载';
    }
  }

  private async onPlayerState(state: media.AVPlayerState): Promise<void> {
    const player = this.avPlayer;
    if (player === undefined) return;
    try {
      if (state === 'initialized') {
        if (this.surfaceId === '') return;
        player.surfaceId = this.surfaceId;
        await player.prepare();
      } else if (state === 'prepared') {
        this.duration = player.duration;
        this.videoReady = true;
        await player.play();
      } else if (state === 'playing') {
        this.playing = true;
      } else if (state === 'paused') {
        this.playing = false;
      } else if (state === 'completed') {
        this.playing = false;
        this.playPosition = this.duration;
      }
    } catch (_error) {
      this.videoReady = false;
      this.playbackError = '播放失败，请重新下载';
    }
  }

  private stopPlayback(): void {
    const player = this.avPlayer;
    this.avPlayer = undefined;
    this.playing = false;
    this.videoReady = false;
    this.playPosition = 0;
    this.duration = 0;
    if (player === undefined) return;
    try {
      player.off('stateChange');
      player.off('timeUpdate');
      player.off('error');
    } catch (_error) {}
    player.release().catch((): void => {});
  }

  private togglePlay(): void {
    const player = this.avPlayer;
    if (player === undefined || !this.videoReady) return;
    if (this.playing) player.pause().catch((): void => {});
    else {
      if (this.duration > 0 && this.playPosition >= this.duration - 200) player.seek(0);
      player.play().catch((): void => {});
    }
  }

  private seekTo(value: number): void {
    const player = this.avPlayer;
    if (player === undefined || !this.videoReady) return;
    player.seek(value);
    this.playPosition = value;
  }

  private clock(ms: number): string {
    const total = Math.max(0, Math.floor(ms / 1000));
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${minutes < 10 ? '0' : ''}${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
  }

  private async reload(refresh: boolean): Promise<void> {
    const version = ++this.queryVersion;
    this.playbackVersion++;
    this.preparing = false;
    this.releaseVideo();
    this.selectedId = '';
    this.playbackError = '';
    this.loading = true;
    this.error = '';
    if (refresh) this.asOf = Date.now();
    const query: RecordingQuery = { asOf: this.asOf, filter: this.filter };
    try {
      const result = await queryRecordings(query);
      if (this.disposed || version !== this.queryVersion) return;
      this.asOf = result.asOf;
      this.windowStart = result.windowStart;
      this.status = result.status;
      this.wholeSegments = result.wholeSegments === true;
      this.clips = result.clips.sort((a: RecordingClip, b: RecordingClip): number => b.startTime - a.startTime);
    } catch (error) {
      if (this.disposed || version !== this.queryVersion) return;
      this.clips = [];
      this.error = (error as Error).message || '录像加载失败，请重试';
    } finally {
      if (!this.disposed && version === this.queryVersion) this.loading = false;
    }
  }

  private format(timestamp: number, includeDate: boolean = false): string {
    const date = new Date(timestamp);
    const time = `${`${date.getHours()}`.padStart(2, '0')}:${`${date.getMinutes()}`.padStart(2, '0')}:${`${date.getSeconds()}`.padStart(2, '0')}`;
    return includeDate ? `${date.getMonth() + 1}月${date.getDate()}日 ${time}` : time;
  }

  private day(timestamp: number): string {
    const date = new Date(timestamp);
    return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
  }

  private statusText(): string {
    if (this.status === 'disk_full') return '硬件存储不足，异常录像已暂停';
    if (this.status === 'idle' || this.status === 'running' || this.status === 'recording') {
      return '异常检测中 · 视频保存在硬件端7天，点击下载后才传到本机';
    }
    return '硬件录像服务暂不可用，请稍后刷新';
  }

  private eventLabel(type: string): string {
    if (type === 'fall') return '摔倒';
    if (type === 'sedentary') return '久坐';
    if (type === 'stranger') return '陌生人';
    return '异常行为';
  }

  private async download(clip: RecordingClip): Promise<void> {
    if (this.preparing) return;
    const version = ++this.playbackVersion;
    this.preparing = true;
    this.playbackError = '';
    this.releaseVideo();
    this.selectedId = clip.id;
    this.selectedLabel = `${this.format(clip.startTime, true)} — ${this.format(clip.endTime, true)}`;
    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    const destination = `${context.cacheDir}/recording-${Date.now()}-${version}.mp4`;
    await CacheManager.getInstance().retain(destination);
    const body: RecordingPlaybackRequest = { asOf: this.asOf, filter: this.filter, clipId: clip.id };
    const message = await CloudService.getInstance().downloadRecording(body, destination);
    if (this.disposed || version !== this.playbackVersion) {
      try { fs.unlinkSync(destination); } catch (_error) {}
      CacheManager.getInstance().release(destination);
      return;
    }
    this.preparing = false;
    if (message !== '') {
      try { fs.unlinkSync(destination); } catch (_error) {}
      CacheManager.getInstance().release(destination);
      this.playbackError = message;
      return;
    }
    this.cacheFile = destination;
    try {
      this.openFile = fs.openSync(destination, fs.OpenMode.READ_ONLY);
      this.mediaLength = fs.statSync(destination).size;
      this.videoSource = destination;
      if (this.surfaceId !== '') this.startPlayback();
    } catch (_error) { this.playbackError = '录像无法打开，请重新下载'; }
  }

  @Builder
  Playback(): void {
    Column({ space: 8 }) {
      if (this.videoSource !== '') {
        Column({ space: 6 }) {
          XComponent({ id: 'recording_surface', type: XComponentType.SURFACE, controller: this.xController })
            .width('100%').height(150)
            .onLoad((): void => {
              this.surfaceId = this.xController.getXComponentSurfaceId();
              this.startPlayback();
            })
            .onDestroy((): void => {
              this.surfaceId = '';
              this.stopPlayback();
            })
          Row({ space: 8 }) {
            Button(this.playing ? '暂停' : '播放').height(36).fontSize(13).backgroundColor('#2563eb')
              .enabled(this.videoReady)
              .onClick((): void => { this.togglePlay(); })
            Text(this.clock(this.playPosition)).fontSize(11)
              .fontColor(this.themeManager.colors.secondaryTextColor).width(40)
            Slider({
              value: this.playPosition,
              min: 0,
              max: this.duration > 0 ? this.duration : 1,
              step: 100,
              style: SliderStyle.OutSet
            }).layoutWeight(1).enabled(this.videoReady)
              .onChange((value: number, mode: SliderChangeMode): void => {
                if (mode === SliderChangeMode.End) this.seekTo(value);
              })
            Text(this.clock(this.duration)).fontSize(11)
              .fontColor(this.themeManager.colors.secondaryTextColor).width(40)
          }.width('100%')
          if (!this.videoReady && this.playbackError === '') {
            Text('正在准备播放…').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
          }
          if (this.playbackError !== '') {
            Text(this.playbackError).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
          }
        }.width('100%')
      } else {
        Column({ space: 10 }) {
          if (this.preparing) { LoadingProgress().width(32).height(32).color('#2563eb') }
          else { Image($r('app.media.ic_camera')).width(36).height(36).objectFit(ImageFit.Contain) }
          Text(this.preparing ? '正在从硬件下载录像…' : this.playbackError !== '' ? this.playbackError : '录像下载完成后可在这里播放')
            .fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor).textAlign(TextAlign.Center)
          if (this.playbackError !== '' && this.selectedId !== '') {
            Button('重新下载').height(44).backgroundColor('#2563eb')
              .onClick((): void => {
                const selected = this.clips.find((clip: RecordingClip): boolean => clip.id === this.selectedId);
                if (selected !== undefined) this.download(selected);
              })
          }
        }.width('100%').height(140).justifyContent(FlexAlign.Center)
      }
      if (this.selectedId !== '') {
        Text(this.selectedLabel).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
          .width('100%').maxLines(2)
      }
    }.width('100%').padding(12).borderRadius(SURFACE_RADIUS)
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
  }

  build() {
    Column({ space: 12 }) {
      Row() {
        Column({ space: 4 }) {
          Text('近7天异常录像').fontSize(17).fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.colors.primaryTextColor)
          Text(`${this.format(this.windowStart, true)} — ${this.format(this.asOf, true)}`)
            .fontSize(11).fontColor(this.themeManager.colors.secondaryTextColor).maxLines(2)
        }.alignItems(HorizontalAlign.Start).layoutWeight(1)
        Button('刷新').height(44).fontSize(14).backgroundColor('#2563eb')
          .accessibilityText('刷新近7天异常录像').onClick((): void => { this.reload(true); })
      }.width('100%')
      Text('仅显示异常类型和发生时间；点击下载后才从硬件获取对应视频')
        .fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).width('100%').maxLines(2)
      if (this.loading) {
        Column({ space: 12 }) {
          LoadingProgress().width(38).height(38)
          Text('正在加载录像').fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
        }.layoutWeight(1).justifyContent(FlexAlign.Center).width('100%')
      } else if (this.error !== '') {
        Column({ space: 14 }) {
          Text(this.error).fontSize(15).fontColor(this.themeManager.colors.primaryTextColor).textAlign(TextAlign.Center)
          Button('重新加载').height(46).backgroundColor('#2563eb').onClick((): void => { this.reload(true); })
        }.layoutWeight(1).justifyContent(FlexAlign.Center).width('100%')
      } else {
        Text(this.statusText()).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).width('100%')
        if (this.clips.length === 0) {
          Column({ space: 10 }) {
            Image($r('app.media.ic_camera_off')).width(48).height(48).objectFit(ImageFit.Contain)
            Text('近7天暂无异常录像')
              .fontSize(17).fontWeight(FontWeight.Medium).fontColor(this.themeManager.colors.primaryTextColor)
              .textAlign(TextAlign.Center)
            Text('检测到摔倒、久坐或陌生人后，硬件会保存对应片段；超过7天自动删除。')
              .fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).textAlign(TextAlign.Center)
          }.layoutWeight(1).justifyContent(FlexAlign.Center).padding(20).width('100%')
        } else {
          if (this.selectedId !== '') {
            this.Playback()
          }
          List({ space: 8 }) {
            ForEach(this.clips, (clip: RecordingClip, index: number) => {
              ListItem() {
                Column({ space: 6 }) {
                  if (index === 0 || this.day(clip.startTime) !== this.day(this.clips[index - 1].startTime)) {
                    Text(this.day(clip.startTime)).fontSize(14).fontWeight(FontWeight.Bold)
                      .fontColor(this.themeManager.colors.primaryTextColor).width('100%').padding({ top: 8, bottom: 4 })
                  }
                  Row({ space: 10 }) {
                    Image($r('app.media.ic_camera')).width(28).height(28).objectFit(ImageFit.Contain)
                    Column({ space: 4 }) {
                      Text(this.eventLabel(clip.eventType))
                        .fontSize(15).fontWeight(FontWeight.Bold).fontColor(this.themeManager.colors.primaryTextColor)
                      Text(`${this.format(clip.startTime)}${clip.endUnconfirmed ? ' · 持续中' : ''}`)
                        .fontSize(11).fontColor(this.themeManager.colors.secondaryTextColor)
                    }.alignItems(HorizontalAlign.Start).layoutWeight(1)
                    Button(clip.downloadable === false ? '生成中' :
                      this.preparing && this.selectedId === clip.id ? '下载中' :
                      this.videoSource !== '' && this.selectedId === clip.id ? '已下载' : '下载')
                      .height(42).fontSize(14).backgroundColor('#2563eb')
                      .enabled(clip.downloadable !== false && !this.preparing)
                      .accessibilityText(`下载${this.eventLabel(clip.eventType)}视频`)
                      .onClick((): void => { this.download(clip); })
                  }.width('100%').padding(14).borderRadius(SURFACE_RADIUS)
                    .backgroundColor(this.selectedId === clip.id ? (this.themeManager.isDarkMode ? '#1e3a5f' : '#dbeafe')
                      : this.themeManager.colors.cardBackgroundColor)
                }.width('100%')
              }
            }, (clip: RecordingClip): string => clip.id)
          }.layoutWeight(1).width('100%').scrollBar(BarState.Off)
        }
      }
    }.width('100%').height('100%').padding({ left: 16, right: 16, top: 14, bottom: 12 })
      .backgroundColor(this.themeManager.colors.backgroundColor)
  }
}
