import { ThemeManager } from '../common/ThemeManager';
import { CloudService } from '../common/CloudService';
import { RecordingClip, RecordingQuery, RecordingPlaybackRequest, queryRecordings } from '../common/RecordingService';
import { SURFACE_RADIUS } from './GradientHeader';
import { common } from '@kit.AbilityKit';
import fs from '@ohos.file.fs';
import { CacheManager } from '../common/CacheManager';

/** Shared by the navigation tab and the personal/history destination. */
@Component
export struct RecordingBrowser {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State filter: string = 'all';
  @State clips: RecordingClip[] = [];
  @State asOf: number = Date.now();
  @State windowStart: number = Date.now() - 86400000;
  @State status: string = 'waiting';
  @State wholeSegments: boolean = false;
  @State loading: boolean = true;
  @State error: string = '';
  @State preparing: boolean = false;
  @State playbackError: string = '';
  @State videoSource: string = '';
  @State selectedId: string = '';
  @State selectedLabel: string = '';
  private controller: VideoController = new VideoController();
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
    try { this.controller.stop(); } catch (_error) {}
    if (this.openFile !== undefined) {
      try { fs.closeSync(this.openFile); } catch (_error) {}
      this.openFile = undefined;
    }
    if (this.cacheFile !== '') {
      try { fs.unlinkSync(this.cacheFile); } catch (_error) {}
      CacheManager.getInstance().release(this.cacheFile);
      this.cacheFile = '';
    }
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
      this.clips = result.clips.sort((a: RecordingClip, b: RecordingClip): number => a.startTime - b.startTime);
    } catch (error) {
      if (this.disposed || version !== this.queryVersion) return;
      this.clips = [];
      this.error = (error as Error).message || '录像加载失败，请重试';
    } finally {
      if (!this.disposed && version === this.queryVersion) this.loading = false;
    }
  }

  private chooseFilter(value: string): void {
    if (this.filter === value) return;
    this.filter = value;
    this.reload(false);
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
    if (this.status === 'disk_full') return '服务器存储不足，录制已暂停';
    if (this.status === 'recording') return '正在持续录像 · 最新片段完成后可查看';
    if (this.status === 'connecting') return '正在尝试连接摄像头';
    return '摄像头未连接 · 正在等待视频源';
  }

  private async play(clip: RecordingClip): Promise<void> {
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
      this.videoSource = `fd://${this.openFile.fd}`;
    } catch (_error) { this.playbackError = '录像无法打开，请重新播放'; }
  }

  private playNext(): void {
    const index = this.clips.findIndex((clip: RecordingClip): boolean => clip.id === this.selectedId);
    if (index >= 0 && index + 1 < this.clips.length) this.play(this.clips[index + 1]);
  }

  @Builder
  Filter(label: string, value: string): void {
    Text(label).fontSize(15).fontWeight(this.filter === value ? FontWeight.Bold : FontWeight.Medium)
      .fontColor(this.filter === value ? '#ffffff' : this.themeManager.colors.primaryTextColor)
      .height(46).textAlign(TextAlign.Center).layoutWeight(1).borderRadius(12)
      .backgroundColor(this.filter === value ? '#2563eb' : this.themeManager.colors.cardBackgroundColor)
      .accessibilityText(`${label}录像${this.filter === value ? '，已选中' : ''}`)
      .onClick((): void => { this.chooseFilter(value); })
  }

  @Builder
  Playback(): void {
    Column({ space: 8 }) {
      if (this.videoSource !== '') {
        Video({ src: this.videoSource, controller: this.controller })
          .width('100%').aspectRatio(4 / 3).objectFit(ImageFit.Contain)
          .autoPlay(true).controls(true)
          .onFinish((): void => { this.playNext(); })
          .onError((): void => { this.playbackError = '播放失败，请重新选择片段'; })
      } else {
        Column({ space: 10 }) {
          if (this.preparing) { LoadingProgress().width(32).height(32).color('#2563eb') }
          else { Image($r('app.media.ic_camera')).width(36).height(36).objectFit(ImageFit.Contain) }
          Text(this.preparing ? '正在准备录像…' : this.playbackError !== '' ? this.playbackError : '选择下方片段开始回放')
            .fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor).textAlign(TextAlign.Center)
          if (this.playbackError !== '' && this.selectedId !== '') {
            Button('重试播放').height(44).backgroundColor('#2563eb')
              .onClick((): void => {
                const selected = this.clips.find((clip: RecordingClip): boolean => clip.id === this.selectedId);
                if (selected !== undefined) this.play(selected);
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
          Text('最近24小时录像').fontSize(17).fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.colors.primaryTextColor)
          Text(`${this.format(this.windowStart, true)} — ${this.format(this.asOf, true)}`)
            .fontSize(11).fontColor(this.themeManager.colors.secondaryTextColor).maxLines(2)
        }.alignItems(HorizontalAlign.Start).layoutWeight(1)
        Button('刷新').height(44).fontSize(14).backgroundColor('#2563eb')
          .accessibilityText('以当前时间刷新最近24小时录像').onClick((): void => { this.reload(true); })
      }.width('100%')
      Row({ space: 8 }) {
        this.Filter('全部', 'all')
        this.Filter('摔倒', 'fall')
        this.Filter('久坐', 'sedentary')
      }.width('100%')
      Text(this.filter === 'all' ? '展示范围内所有可用录像 · 按时间顺序连续播放'
        : this.wholeSegments ? '展示与事件时间重叠的完整录像分段'
        : '保留事件开始前1分钟至结束后1分钟 · 重叠片段合并')
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
            Text(this.filter === 'all' ? '这24小时内暂无可用录像' : `这24小时内暂无${this.filter === 'fall' ? '摔倒' : '久坐'}相关录像`)
              .fontSize(17).fontWeight(FontWeight.Medium).fontColor(this.themeManager.colors.primaryTextColor)
              .textAlign(TextAlign.Center)
            Text('设备联网后自动录制，已有录像不会因手机退出而中断。未录制的时段无法补回。')
              .fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).textAlign(TextAlign.Center)
          }.layoutWeight(1).justifyContent(FlexAlign.Center).padding(20).width('100%')
        } else {
          List({ space: 8 }) {
            ListItem() { this.Playback() }
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
                      Text(`${this.format(clip.startTime)} — ${this.format(clip.endTime)}`)
                        .fontSize(14).fontWeight(FontWeight.Medium).fontColor(this.themeManager.colors.primaryTextColor)
                      Text(`${this.filter === 'all' ? '连续录像' : this.filter === 'fall' ? '摔倒相关' : '久坐相关'} · ${Math.ceil((clip.endTime - clip.startTime) / 1000)}秒${clip.endUnconfirmed ? ' · 结束时间待确认' : ''}`)
                        .fontSize(11).fontColor(this.themeManager.colors.secondaryTextColor)
                    }.alignItems(HorizontalAlign.Start).layoutWeight(1)
                    Text(this.selectedId === clip.id ? '已选择' : '播放').fontSize(14).fontColor('#2563eb')
                  }.width('100%').padding(14).borderRadius(SURFACE_RADIUS)
                    .backgroundColor(this.selectedId === clip.id ? (this.themeManager.isDarkMode ? '#1e3a5f' : '#dbeafe')
                      : this.themeManager.colors.cardBackgroundColor)
                    .onClick((): void => { this.play(clip); })
                  if (index > 0 && clip.startTime - this.clips[index - 1].endTime > 1500 && this.filter === 'all') {
                    Text('前一片段与此片段之间存在录像缺口').fontSize(11)
                      .fontColor(this.themeManager.colors.secondaryTextColor).width('100%')
                  }
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
