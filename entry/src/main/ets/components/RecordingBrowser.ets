import { ThemeManager } from '../common/ThemeManager';
import { CloudService } from '../common/CloudService';
import {
  RecordingClip,
  RecordingDayRange,
  RecordingQuery,
  RecordingPlaybackRequest,
  RECORDING_RETENTION_MS,
  buildRecordingDays,
  queryRecordings,
  requestStreamUrl
} from '../common/RecordingService';
import { SURFACE_RADIUS } from './GradientHeader';
import { common } from '@kit.AbilityKit';
import picker from '@ohos.file.picker';
import { media } from '@kit.MediaKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { showToast } from '../common/UiFeedback';
import { CarePalette, carePalette, careIconTint } from '../common/CarePalette';
import { MqttManager } from '../pages/MqttManager';

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
  @Prop bottomInset: number = 0;
  onTabScroll: (delta: number, state: ScrollState) => void = () => {};
  /** 页头：放进列表第一项，随内容滑走；筛选条浮在上面，滑到顶后固定 */
  @BuilderParam header: () => void = this.noHeader;
  @State headerHeight: number = 0;
  @State filterHeight: number = 56;
  @State listOffset: number = 0;
  private listScroller: Scroller = new Scroller();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State mqtt: MqttManager = MqttManager.getInstance();
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
  @State downloadingId: string = '';
  private xController: XComponentController = new XComponentController();
  private avPlayer: media.AVPlayer | undefined = undefined;
  private surfaceId: string = '';
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
  }

  /** 在线播放：AVPlayer 直接拉云端签名地址（支持 Range 拖动），不在本机落地文件。 */
  private async startPlayback(): Promise<void> {
    const url = this.videoSource;
    if (url === '' || this.surfaceId === '') return;
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
        this.playbackError = '播放失败，请重新播放';
      });
      player.on('stateChange', (state: media.AVPlayerState): void => { this.onPlayerState(state); });
      player.on('timeUpdate', (time: number): void => { this.playPosition = time; });
      player.url = url;
    } catch (_error) {
      this.playbackError = '播放失败，请重新播放';
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
      this.playbackError = '播放失败，请重新播放';
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

  private formatDate(timestamp: number): string {
    const date = new Date(timestamp);
    return `${date.getMonth() + 1}月${date.getDate()}日`;
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
      return '异常检测中 · 视频保存在硬件端7天，在线播放不占手机空间';
    }
    return '硬件录像服务暂不可用，请稍后刷新';
  }

  private eventLabel(type: string): string {
    if (type === 'fall') return '摔倒';
    if (type === 'sedentary') return '久坐提醒';
    if (type === 'stranger') return '陌生人';
    return '异常行为';
  }

  /** 请求必须带上该事件所属日期的窗口，云端才不会为找一个 clip 重新扫描七天。 */
  private clipRequest(clip: RecordingClip): RecordingPlaybackRequest | undefined {
    const day = this.days.find((item: RecordingDay): boolean => item.key === this.expandedKey);
    if (day === undefined) return undefined;
    const body: RecordingPlaybackRequest = {
      asOf: day.windowEnd,
      filter: this.filter,
      clipId: clip.id,
      windowStart: day.windowStart,
      windowEnd: day.windowEnd
    };
    return body;
  }

  /** 点击片段：换取签名地址后在线播放，不下载到本机。 */
  private async play(clip: RecordingClip): Promise<void> {
    if (clip.downloadable === false) {
      this.toast('异常视频正在生成，请稍后刷新');
      return;
    }
    const body = this.clipRequest(clip);
    if (body === undefined) return;
    const version = ++this.playbackVersion;
    this.preparing = true;
    this.playbackError = '';
    this.releaseVideo();
    this.selectedId = clip.id;
    this.selectedLabel = `${this.eventLabel(clip.eventType)} · ${this.format(clip.startTime, true)}`;
    try {
      const url = await requestStreamUrl(body);
      if (this.disposed || version !== this.playbackVersion) return;
      this.preparing = false;
      this.videoSource = url;
      if (this.surfaceId !== '') this.startPlayback();
    } catch (error) {
      if (this.disposed || version !== this.playbackVersion) return;
      this.preparing = false;
      this.playbackError = (error as Error).message || '录像暂不可用，请重试';
    }
  }

  /** 下载按钮：先让用户选保存位置，再从云端取完整片段写进去。 */
  private async saveClip(clip: RecordingClip): Promise<void> {
    if (this.downloadingId !== '' || clip.downloadable === false) return;
    const body = this.clipRequest(clip);
    if (body === undefined) return;
    const time = new Date(clip.startTime);
    const pad = (value: number): string => `${value}`.padStart(2, '0');
    const name = `守护星${this.eventLabel(clip.eventType)}_${time.getFullYear()}${pad(time.getMonth() + 1)}` +
      `${pad(time.getDate())}_${pad(time.getHours())}${pad(time.getMinutes())}${pad(time.getSeconds())}.mp4`;
    let uri = '';
    try {
      const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
      const uris = await new picker.DocumentViewPicker(context).save({
        newFileNames: [name],
        fileSuffixChoices: ['MP4 视频|.mp4']
      });
      if (uris.length === 0) return;
      uri = uris[0];
    } catch (_error) {
      this.toast('无法打开保存位置，请重试');
      return;
    }
    this.downloadingId = clip.id;
    const message = await CloudService.getInstance().downloadRecording(body, uri);
    if (this.disposed) return;
    this.downloadingId = '';
    this.toast(message === '' ? '视频已保存' : message);
  }

  private toast(message: string): void {
    showToast(this.getUIContext(), { message: message });
  }

  private retrySelected(): void {
    const day = this.days.find((item: RecordingDay): boolean => item.key === this.expandedKey);
    if (day === undefined) return;
    const selected = day.clips.find((clip: RecordingClip): boolean => clip.id === this.selectedId);
    if (selected !== undefined) this.play(selected);
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
            Button(this.playing ? '暂停' : '播放').height(36).fontSize(13).backgroundColor('#0A5C43')
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
            Text('正在缓冲…').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
          }
          if (this.playbackError !== '') {
            Text(this.playbackError).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
          }
        }.width('100%')
      } else {
        Column({ space: 10 }) {
          if (this.preparing) { LoadingProgress().width(32).height(32).color('#0A5C43') }
          else { Image($r('app.media.ic_camera')).width(36).height(36).objectFit(ImageFit.Contain) }
          Text(this.preparing ? '正在连接硬件录像…' : this.playbackError !== '' ? this.playbackError : '点击下方片段即可在线播放')
            .fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor).textAlign(TextAlign.Center)
          if (this.playbackError !== '' && this.selectedId !== '') {
            Button('重新播放').height(44).backgroundColor('#0A5C43')
              .onClick((): void => { this.retrySelected(); })
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

  private palette(): CarePalette {
    return carePalette(this.mqtt.isFallDetected, this.mqtt.isSedentaryDetected, this.mqtt.deviceOnline);
  }

  private ink(): string {
    return this.themeManager.colors.primaryTextColor;
  }

  private ink2(): string {
    return this.themeManager.colors.secondaryTextColor;
  }

  private line(): string {
    return this.themeManager.isDarkMode ? '#1FFFFFFF' : '#1A10231C';
  }

  private thumbSurface(type: string): string {
    if (type === 'fall') return '#FDE5DF';
    if (type === 'stranger') return '#DCE3FF';
    return '#DCE9E2';
  }

  /** 切换筛选：结果随类型变化，所有日期的缓存作废，只重查当前展开的那天 */
  private setFilter(kind: string): void {
    if (this.filter === kind) return;
    this.filter = kind;
    this.dayTokens.clear();
    const ranges: RecordingDayRange[] = buildRecordingDays(Date.now(), RECORDING_RETENTION_MS);
    const days: RecordingDay[] = [];
    ranges.forEach((range: RecordingDayRange): void => { days.push(this.emptyDay(range)); });
    this.days = days;
    if (this.expandedKey === '' || !days.some((day: RecordingDay): boolean => day.key === this.expandedKey)) {
      this.expandedKey = days.length > 0 ? days[0].key : '';
    }
    this.playbackVersion++;
    this.preparing = false;
    this.playbackError = '';
    this.selectedId = '';
    this.selectedLabel = '';
    this.releaseVideo();
    if (this.expandedKey !== '') this.loadDay(this.expandedKey, true);
  }

  @Builder
  FilterChip(kind: string, label: string): void {
    Button(label, { type: ButtonType.Capsule, stateEffect: true })
      .height(40).padding({ left: 16, right: 16 }).fontSize(14).fontWeight(FontWeight.Medium)
      .fontColor(this.filter === kind ? '#FFFFFF' : this.ink())
      .backgroundColor(this.filter === kind ? this.palette().solid : this.themeManager.colors.cardBackgroundColor)
      .shadow(this.filter === kind ? { radius: 0, color: Color.Transparent }
        : { radius: 12, offsetY: 6, color: '#1410231C' })
      .accessibilitySelected(this.filter === kind)
      .onClick((): void => { this.setFilter(kind); })
  }

  @Builder
  DayRow(day: RecordingDay): void {
    Row({ space: 8 }) {
      Text(day.label).fontSize(17).fontWeight(FontWeight.Bold).fontColor(this.ink())
      if (day.partial) {
        Text('部分时段').fontSize(12).fontColor(this.ink2())
      }
      Blank()
      if (day.loaded) {
        Text(`${day.clips.length} 条`).fontSize(13).fontColor(this.ink2())
      }
      Image($r('app.media.ic_chevron_right')).width(16).height(16)
        .rotate({ angle: this.expandedKey === day.key ? 90 : 0 })
    }.width('100%').height(48)
      .accessibilityText(`${day.label}异常录像，${day.partial ? '仅保留部分时段，' : ''}点击${this.expandedKey === day.key ? '收起' : '展开'}`)
      .onClick((): void => { this.toggleDay(day.key); })
  }

  @Builder
  ClipRow(clip: RecordingClip): void {
    Row({ space: 12 }) {
      Stack() {
        Image($r('app.media.ic_camera')).width(30).height(30).opacity(0.35).objectFit(ImageFit.Contain)
        Stack() {
          Image($r('app.media.ic_play')).width(12).height(12)
        }.width(26).height(26).borderRadius(13).backgroundColor('#B810231C')
      }.width(72).height(54).borderRadius(14).backgroundColor(this.thumbSurface(clip.eventType))
      .border({ width: 1, color: this.line() })
      Column({ space: 3 }) {
        Text(this.eventLabel(clip.eventType)).fontSize(16).fontWeight(FontWeight.Medium).fontColor(this.ink())
        // 板端暂未写事件结束时间，endUnconfirmed 恒为 true，不再显示“持续中”
        Text(this.format(clip.startTime)).fontSize(13).fontColor(this.ink2())
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
      Button({ type: ButtonType.Circle }) {
        if (this.downloadingId === clip.id) {
          LoadingProgress().width(20).height(20).color(this.palette().solid)
        } else {
          Image($r('app.media.ic_download')).width(20).height(20).supportSvg2(true)
            .colorFilter(careIconTint(this.themeManager.isDarkMode ? '#FFFFFF' : this.palette().solid))
        }
      }
      .width(44).height(44)
      .backgroundColor(this.themeManager.isDarkMode ? '#24FFFFFF' : '#26' + this.palette().tone.substring(1))
      .enabled(clip.downloadable !== false && this.downloadingId === '')
      .opacity(clip.downloadable === false ? 0.4 : 1)
      .accessibilityText(clip.downloadable === false ? '视频生成中' : `把${this.eventLabel(clip.eventType)}视频保存到手机`)
      .onClick((): void => { this.saveClip(clip); })
    }.width('100%').padding({ top: 12, bottom: 12 })
      .border({ width: { top: 1 }, color: this.line() })
      .backgroundColor(this.selectedId === clip.id ? '#14' + this.palette().tone.substring(1) : Color.Transparent)
      .accessibilityText(`在线播放${this.eventLabel(clip.eventType)}视频`)
      .onClick((): void => { this.play(clip); })
  }

  @Builder
  DayContent(day: RecordingDay): void {
    Column() {
      if (day.loading) {
        Row({ space: 8 }) {
          LoadingProgress().width(20).height(20).color(this.palette().solid)
          Text('正在读取该日记录…').fontSize(13).fontColor(this.ink2())
        }.width('100%').padding({ top: 12, bottom: 14 }).border({ width: { top: 1 }, color: this.line() })
      } else if (day.error !== '') {
        Column({ space: 10 }) {
          Text(day.error).fontSize(13).fontColor(this.ink()).textAlign(TextAlign.Center)
          Button('重试', { type: ButtonType.Capsule }).height(40).padding({ left: 22, right: 22 })
            .fontSize(14).backgroundColor(this.palette().solid)
            .onClick((): void => { this.loadDay(day.key, true); })
        }.width('100%').padding({ top: 12, bottom: 14 }).border({ width: { top: 1 }, color: this.line() })
      } else if (day.clips.length === 0) {
        Text('这一天没有异常').fontSize(13).fontColor(this.ink2())
          .width('100%').padding({ top: 12, bottom: 14 }).border({ width: { top: 1 }, color: this.line() })
      } else {
        ForEach(day.clips, (clip: RecordingClip) => {
          this.ClipRow(clip)
        }, (clip: RecordingClip): string => clip.id)
      }
    }.width('100%')
  }

  @Builder
  noHeader(): void {}

  @Builder
  FilterBar(): void {
    Row({ space: 8 }) {
      Scroll() {
        Row({ space: 8 }) {
          this.FilterChip('all', '全部')
          this.FilterChip('fall', '跌倒')
          this.FilterChip('sedentary', '久坐')
          this.FilterChip('stranger', '陌生人')
        }.padding({ top: 4, bottom: 8 })
      }.scrollable(ScrollDirection.Horizontal).scrollBar(BarState.Off).align(Alignment.Start).layoutWeight(1)
      Button({ type: ButtonType.Circle }) {
        Image($r('app.media.ic_refresh_gray')).width(20).height(20).supportSvg2(true)
          .colorFilter(careIconTint(this.themeManager.isDarkMode ? '#FFFFFF' : this.palette().solid))
      }.width(44).height(44).backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .shadow({ radius: 12, offsetY: 6, color: '#1410231C' }).margin({ bottom: 4 })
      .accessibilityText('刷新当前展开日期的异常录像').onClick((): void => { this.refreshCurrent(); })
  }.width('100%')
  }

  /** 筛选条的位置：先跟着页头往上走，页头滑出后贴在顶部（状态栏下沿） */
  private filterTop(): number {
    return Math.max(0, this.headerHeight - this.listOffset);
  }

  build() {
    Stack({ alignContent: Alignment.Top }) {
      List({ space: 12, scroller: this.listScroller }) {
        ListItem() {
          Column() { this.header() }.width('100%')
            .onAreaChange((_o: Area, n: Area): void => { this.headerHeight = Number(n.height); })
        }
        // 给浮起的筛选条占位
        ListItem() { Column().width('100%').height(Math.max(0, this.filterHeight - 12)) }
        if (this.selectedId !== '') {
          ListItem() { this.Playback() }.padding({ left: 16, right: 16 })
        }
        if (this.anyDayLoaded()) {
          ListItem() { Text(this.statusText()).fontSize(12).fontColor(this.ink2()).width('100%') }.padding({ left: 16, right: 16 })
        }
        ForEach(this.days, (day: RecordingDay) => {
          ListItem() {
            Column() {
              this.DayRow(day)
              if (this.expandedKey === day.key) {
                this.DayContent(day)
              }
            }.width('100%').padding({ left: 16, right: 16, bottom: this.expandedKey === day.key ? 4 : 0 })
            .borderRadius(28).backgroundColor(this.themeManager.colors.cardBackgroundColor)
            .shadow({ radius: 30, offsetY: 16, color: '#1F10231C' })
          }.padding({ left: 16, right: 16 })
        // key 必须包含加载状态：patchDay 生成新对象，只用日期作 key 时 ForEach 不会重建该项，界面会卡在“正在读取”。
        }, (day: RecordingDay): string =>
          `${this.filter}|${day.key}|${day.loading}|${day.loaded}|${day.error}|${day.windowEnd}|${day.clips.length}|${this.expandedKey === day.key}`)
      }.width('100%').height('100%').scrollBar(BarState.Off)
        .contentEndOffset(this.bottomInset + 12)
        // 列表铺进状态栏：滑动时录像卡片从状态栏下面穿过
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
        .onDidScroll((y: number, state: ScrollState): void => {
          this.listOffset = this.listScroller.currentOffset().yOffset;
          this.onTabScroll(y, state);
        })
      Column() { this.FilterBar() }
        .width('100%').padding({ left: 16, right: 16, top: 4 })
        // 贴顶后加一层磨砂，滑过的卡片不会和筛选按钮叠在一起看不清
        .backgroundBlurStyle(this.listOffset > this.headerHeight ? BlurStyle.COMPONENT_THIN : BlurStyle.NONE)
        .translate({ y: this.filterTop() })
        .onAreaChange((_o: Area, n: Area): void => { this.filterHeight = Number(n.height); })
    }.width('100%').height('100%')
  }
}
