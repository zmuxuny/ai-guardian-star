import { ThemeManager } from '../common/ThemeManager';
import { CloudService } from '../common/CloudService';
import {
  RecordingClip,
  RecordingDayRange,
  RecordingQuery,
  RecordingPlaybackRequest,
  RECORDING_RETENTION_MS,
  buildRecordingDays,
  queryRecordings
} from '../common/RecordingService';
import { SURFACE_RADIUS } from './GradientHeader';
import { common } from '@kit.AbilityKit';
import fs from '@ohos.file.fs';
import { media } from '@kit.MediaKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { CacheManager } from '../common/CacheManager';

/** 一个日期分组在页面生命周期内的缓存状态；只有展开过的日期才会去查询。 */
interface RecordingDay {
  key: string;
  label: string;
  windowStart: number;
  windowEnd: number;
  partial: boolean;
  loaded: boolean;
  loading: boolean;
  error: string;
  clips: RecordingClip[];
  status: string;
}

/** Shared by the navigation tab and the personal/history destination. */
@Component
export struct RecordingBrowser {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State filter: string = 'all';
  @State days: RecordingDay[] = [];
  @State expandedKey: string = '';
  @State asOf: number = Date.now();
  @State status: string = 'waiting';
  @State wholeSegments: boolean = false;
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
  private dayTokens: Map<string, number> = new Map<string, number>();
  private playbackVersion: number = 0;
  private disposed: boolean = false;

  aboutToAppear(): void {
    this.disposed = false;
    this.asOf = Date.now();
    const ranges: RecordingDayRange[] = buildRecordingDays(this.asOf, RECORDING_RETENTION_MS);
    const days: RecordingDay[] = [];
    ranges.forEach((range: RecordingDayRange): void => { days.push(this.emptyDay(range)); });
    this.days = days;
    if (this.days.length > 0) {
      this.expandedKey = this.days[0].key;
      this.loadDay(this.expandedKey, false);
    }
  }

  aboutToDisappear(): void {
    this.disposed = true;
    this.playbackVersion++;
    this.releaseVideo();
  }

  private emptyDay(range: RecordingDayRange): RecordingDay {
    const day: RecordingDay = {
      key: range.key,
      label: range.label,
      windowStart: range.windowStart,
      windowEnd: range.windowEnd,
      partial: range.partial,
      loaded: false,
      loading: false,
      error: '',
      clips: [],
      status: ''
    };
    return day;
  }

  private patchDay(key: string, windowEnd: number, loaded: boolean, loading: boolean, error: string,
    clips: RecordingClip[], status: string): void {
    this.days = this.days.map((day: RecordingDay): RecordingDay => {
      if (day.key !== key) return day;
      const next: RecordingDay = {
        key: day.key,
        label: day.label,
        windowStart: day.windowStart,
        windowEnd: windowEnd,
        partial: day.partial,
        loaded: loaded,
        loading: loading,
        error: error,
        clips: clips,
        status: status
      };
      return next;
    });
  }

  /** 只查询被展开的那一天；已加载成功的日期在页面生命周期内不再重复请求。 */
  private async loadDay(key: string, force: boolean): Promise<void> {
    const index = this.days.findIndex((day: RecordingDay): boolean => day.key === key);
    if (index < 0) return;
    const day = this.days[index];
    if (day.loading) return;
    if (day.loaded && !force) return;
    const previous = this.dayTokens.get(key);
    const token = previous === undefined ? 1 : previous + 1;
    this.dayTokens.set(key, token);
    // 今天的时间窗在打开页面后仍会向前走，查询和下载都以本次实际使用的窗口为准。
    const windowEnd = index === 0 ? Date.now() : day.windowEnd;
    const query: RecordingQuery = {
      asOf: windowEnd,
      filter: this.filter,
      windowStart: day.windowStart,
      windowEnd: windowEnd
    };
    this.patchDay(key, windowEnd, day.loaded, true, '', day.clips, day.status);
    try {
      const result = await queryRecordings(query);
      if (this.disposed || this.dayTokens.get(key) !== token) return;
      this.asOf = Math.max(this.asOf, result.asOf);
      this.status = result.status;
      this.wholeSegments = result.wholeSegments === true;
      const clips: RecordingClip[] = result.clips.slice().sort(
        (left: RecordingClip, right: RecordingClip): number => right.startTime - left.startTime);
      this.patchDay(key, windowEnd, true, false, '', clips, result.status);
    } catch (error) {
      if (this.disposed || this.dayTokens.get(key) !== token) return;
      const message: string = (error as Error).message || '该日录像加载失败，请重试';
      this.patchDay(key, windowEnd, day.loaded, false, message, day.clips, day.status);
    }
  }

  private toggleDay(key: string): void {
    if (this.expandedKey === key) {
      this.expandedKey = '';
      return;
    }
    this.expandedKey = key;
    this.playbackVersion++;
    this.preparing = false;
    this.playbackError = '';
    this.selectedId = '';
    this.selectedLabel = '';
    this.releaseVideo();
    const day = this.days.find((item: RecordingDay): boolean => item.key === key);
    if (day !== undefined && !day.loaded) this.loadDay(key, false);
  }

  /** 刷新只清空并重查当前展开日期，其他日期的缓存保持不变。 */
  private refreshCurrent(): void {
    const now = Date.now();
    const ranges: RecordingDayRange[] = buildRecordingDays(now, RECORDING_RETENTION_MS);
    let targetKey: string = ranges.length > 0 ? ranges[0].key : '';
    if (this.expandedKey !== '') {
      const matched = ranges.find((range: RecordingDayRange): boolean => range.key === this.expandedKey);
      if (matched !== undefined) targetKey = this.expandedKey;
    }
    const cached: Map<string, RecordingDay> = new Map<string, RecordingDay>();
    this.days.forEach((day: RecordingDay): void => { cached.set(day.key, day); });
    const days: RecordingDay[] = [];
    ranges.forEach((range: RecordingDayRange): void => {
      if (range.key === targetKey) {
        days.push(this.emptyDay(range));
        return;
      }
      const previous = cached.get(range.key);
      days.push(previous !== undefined && previous.loaded ? previous : this.emptyDay(range));
    });
    this.days = days;
    this.expandedKey = targetKey;
    this.asOf = now;
    this.playbackVersion++;
    this.preparing = false;
    this.playbackError = '';
    this.selectedId = '';
    this.selectedLabel = '';
    this.releaseVideo();
    if (targetKey !== '') this.loadDay(targetKey, true);
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

  private format(timestamp: number, includeDate: boolean = false): string {
    const date = new Date(timestamp);
    const time = `${`${date.getHours()}`.padStart(2, '0')}:${`${date.getMinutes()}`.padStart(2, '0')}:${`${date.getSeconds()}`.padStart(2, '0')}`;
    return includeDate ? `${date.getMonth() + 1}月${date.getDate()}日 ${time}` : time;
  }

  private rangeStart(): number {
    if (this.days.length > 0) return this.days[this.days.length - 1].windowStart;
    return this.asOf - RECORDING_RETENTION_MS;
  }

  private anyDayLoaded(): boolean {
    return this.days.some((day: RecordingDay): boolean => day.loaded);
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
    const day = this.days.find((item: RecordingDay): boolean => item.key === this.expandedKey);
    if (day === undefined) return;
    const version = ++this.playbackVersion;
    this.preparing = true;
    this.playbackError = '';
    this.releaseVideo();
    this.selectedId = clip.id;
    this.selectedLabel = `${this.format(clip.startTime, true)} — ${this.format(clip.endTime, true)}`;
    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    const destination = `${context.cacheDir}/recording-${Date.now()}-${version}.mp4`;
    await CacheManager.getInstance().retain(destination);
    // 下载时必须带上该事件所属日期的窗口，云端才不会为找一个 clip 重新扫描七天。
    const body: RecordingPlaybackRequest = {
      asOf: day.windowEnd,
      filter: this.filter,
      clipId: clip.id,
      windowStart: day.windowStart,
      windowEnd: day.windowEnd
    };
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

  private retrySelectedDownload(): void {
    const day = this.days.find((item: RecordingDay): boolean => item.key === this.expandedKey);
    if (day === undefined) return;
    const selected = day.clips.find((clip: RecordingClip): boolean => clip.id === this.selectedId);
    if (selected !== undefined) this.download(selected);
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
              .onClick((): void => { this.retrySelectedDownload(); })
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

  @Builder
  DayRow(day: RecordingDay): void {
    Row({ space: 8 }) {
      Column({ space: 3 }) {
        Row({ space: 6 }) {
          Text(day.label).fontSize(15).fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.colors.primaryTextColor)
          if (day.partial) {
            Text('仅保留部分时段').fontSize(11)
              .fontColor(this.themeManager.colors.secondaryTextColor)
          }
        }
        if (day.loaded) {
          Text(`${day.clips.length} 个异常事件`).fontSize(11)
            .fontColor(this.themeManager.colors.secondaryTextColor)
        }
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
      Text(this.expandedKey === day.key ? '▴' : '▾').fontSize(14)
        .fontColor(this.themeManager.colors.secondaryTextColor)
    }.width('100%').padding(12).borderRadius(SURFACE_RADIUS)
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .accessibilityText(`${day.label}异常录像，${day.partial ? '仅保留部分时段，' : ''}点击${this.expandedKey === day.key ? '收起' : '展开'}`)
      .onClick((): void => { this.toggleDay(day.key); })
  }

  @Builder
  DayContent(day: RecordingDay): void {
    Column({ space: 8 }) {
      if (day.loading) {
        Row({ space: 8 }) {
          LoadingProgress().width(20).height(20).color('#2563eb')
          Text('正在读取该日异常记录…').fontSize(13)
            .fontColor(this.themeManager.colors.secondaryTextColor)
        }.width('100%').padding({ left: 12, right: 12, bottom: 8 })
      } else if (day.error !== '') {
        Column({ space: 8 }) {
          Text(day.error).fontSize(13).fontColor(this.themeManager.colors.primaryTextColor)
            .textAlign(TextAlign.Center)
          Button('重试').height(40).fontSize(13).backgroundColor('#2563eb')
            .onClick((): void => { this.loadDay(day.key, true); })
        }.width('100%').padding({ left: 12, right: 12, bottom: 10 })
      } else if (day.clips.length === 0) {
        Text('该日暂无异常').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor)
          .width('100%').padding({ left: 12, right: 12, bottom: 10 })
      } else {
        ForEach(day.clips, (clip: RecordingClip) => {
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
        }, (clip: RecordingClip): string => clip.id)
      }
    }.width('100%')
  }

  build() {
    Column({ space: 12 }) {
      Row() {
        Column({ space: 4 }) {
          Text('近7天异常录像').fontSize(17).fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.colors.primaryTextColor)
          Text(`${this.format(this.rangeStart(), true)} — ${this.format(this.asOf, true)}`)
            .fontSize(11).fontColor(this.themeManager.colors.secondaryTextColor).maxLines(2)
        }.alignItems(HorizontalAlign.Start).layoutWeight(1)
        Button('刷新').height(44).fontSize(14).backgroundColor('#2563eb')
          .accessibilityText('刷新当前展开日期的异常录像').onClick((): void => { this.refreshCurrent(); })
      }.width('100%')
      Text('仅显示异常类型和发生时间；点击下载后才从硬件获取对应视频')
        .fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).width('100%').maxLines(2)
      if (this.selectedId !== '') {
        this.Playback()
      }
      if (this.anyDayLoaded()) {
        Text(this.statusText()).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).width('100%')
      }
      List({ space: 8 }) {
        ForEach(this.days, (day: RecordingDay) => {
          ListItem() {
            Column({ space: 2 }) {
              this.DayRow(day)
              if (this.expandedKey === day.key) {
                this.DayContent(day)
              }
            }.width('100%')
          }
        }, (day: RecordingDay): string => day.key)
      }.layoutWeight(1).width('100%').scrollBar(BarState.Off)
    }.width('100%').height('100%').padding({ left: 16, right: 16, top: 14, bottom: 12 })
      .backgroundColor(this.themeManager.colors.backgroundColor)
  }
}
