import { MqttManager } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';
import webview from '@ohos.web.webview';
import fileUri from '@ohos.file.fileuri';
import { AudioTransferManager } from '../common/AudioTransferManager';
import { abilityAccessCtrl } from '@kit.AbilityKit';
import { common } from '@kit.AbilityKit';
import http from '@ohos.net.http';
import { VIDEO_FEED_URL, HEALTH_CHECK_URL, STORE_KEY_AVATAR } from '../config';
import { DatabaseHelper, HealthEvent } from '../database/DatabaseHelper';
import { UserManager } from '../common/UserManager';
import { SURFACE_RADIUS } from '../components/GradientHeader';
import { showToast } from '../common/UiFeedback';
import { getWindowSizeClass } from '../common/ResponsiveLayout';

@Component
export struct mainPage {
  pathStack: NavPathStack = new NavPathStack();
  @StorageProp(STORE_KEY_AVATAR) userAvatarPath: string = '';
  @State homeHeaderHeight: number = 64;
  @State showMonitorDetails: boolean = false;
  @State expandedVideo: boolean = false;
  @State homeEvents: HealthEvent[] = [];
  @State homeLoading: boolean = true;
  @State homeLoadFailed: boolean = false;
  private homeDataTimer: number = -1;
  private homeDataLoading: boolean = false;
  private homeDataUser: string = '';
  private homeScroller: Scroller = new Scroller();
  @State videoUrl: string = VIDEO_FEED_URL;
  @State volumeLevel: number = 50;
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State deviceOnline: boolean = false;
  @State isManualHealthCheck: boolean = false;
  @State manualHealthCheckMessage: string = '';
  @State latestMessage: string = '正在初始化...';
  @State isFallDetected: boolean = false;
  @State isSedentaryDetected: boolean = false;
  @State isStrangerDetected: boolean = false;
  @State isTalking: boolean = false;
  // 通话按钮缩放
  @State btnScale: number = 1.0;
  // 当前视口宽度，用于大屏左右分栏
  @State viewportWidth: number = 360;
  // 手机页滚动时，把同一个 Web 播放视图收进浮动小窗
  @State compactScrollOffset: number = 0;
  @State compactVideoProgress: number = 0;
  @State compactAreaWidth: number = 360;
  @State compactAreaHeight: number = 600;
  @State isCompactVideoMini: boolean = false;
  @State miniVideoWidth: number = 168;
  @State miniVideoX: number = 0;
  @State miniVideoY: number = 12;
  private miniVideoDragStartX: number = 0;
  private miniVideoDragStartY: number = 0;
  private miniVideoDragEnabled: boolean = false;
  private videoPanScrollEnabled: boolean = false;
  private videoPanScrollStart: number = 0;
  @State resizingVideo: boolean = false;
  private resizeStartWidth: number = 168;
  private resizeStartX: number = 0;
  private resizeStartY: number = 0;

  private updateTimer: number = -1;
  private healthCheckTimer: number = -1;
  private readonly healthCheckUrl: string = HEALTH_CHECK_URL;
  private webController: webview.WebviewController = new webview.WebviewController();
  private videoFitAttempt: number = 0;
  private audioManager: AudioTransferManager = AudioTransferManager.getInstance();
  private context: common.UIAbilityContext = this.getUIContext().getHostContext() as common.UIAbilityContext;

  aboutToAppear(): void {
    this.mqttManager.connectAndSubscribe();
    this.syncState();
    this.updateTimer = setInterval(() => { this.syncState(); }, 100);
    this.runHealthCheck();
    this.loadHomeEvents();
    this.homeDataTimer = setInterval((): void => { this.loadHomeEvents(); }, 10000) as number;
    this.healthCheckTimer = setInterval(() => { this.runHealthCheck(); }, 5000) as number;
  }
  aboutToDisappear(): void {
    if (this.updateTimer !== -1) { clearInterval(this.updateTimer); this.updateTimer = -1; }
    if (this.healthCheckTimer !== -1) { clearInterval(this.healthCheckTimer); this.healthCheckTimer = -1; }
    if (this.homeDataTimer !== -1) { clearInterval(this.homeDataTimer); this.homeDataTimer = -1; }
  }
  onPageShow(): void {
    this.loadHomeEvents();
  }

  /** 实时画面是裸 MJPEG 文档，浏览器按图像原始像素居中显示，四周留黑边；这里让它铺满预留画面区。 */
  private fitVideoDocument(): void {
    const script = `(() => {
      const body = document.body;
      const image = document.querySelector('img');
      if (!body || !image) return 'wait';
      const root = document.documentElement;
      root.style.margin = '0';
      root.style.padding = '0';
      root.style.overflow = 'hidden';
      root.style.background = '#0f172a';
      body.style.margin = '0';
      body.style.padding = '0';
      body.style.overflow = 'hidden';
      body.style.height = '100vh';
      body.style.background = '#0f172a';
      image.style.display = 'block';
      image.style.width = '100vw';
      image.style.height = '100vh';
      image.style.maxWidth = 'none';
      image.style.maxHeight = 'none';
      image.style.margin = '0';
      image.style.objectFit = 'cover';
      return 'ok';
    })()`;
    this.webController.runJavaScript(script).then((result: string): void => {
      if (result === 'ok') {
        this.videoFitAttempt = 0;
        return;
      }
      this.retryFitVideoDocument();
    }).catch((): void => { this.retryFitVideoDocument(); });
  }

  private retryFitVideoDocument(): void {
    if (this.videoFitAttempt >= 25) return;
    this.videoFitAttempt++;
    setTimeout((): void => { this.fitVideoDocument(); }, 300);
  }

  private async loadHomeEvents(): Promise<void> {
    if (this.homeDataLoading) return;
    const userManager = UserManager.getInstance();
    const username = userManager.getCurrentUsername();
    if (!userManager.isLoggedIn()) {
      this.homeEvents = [];
      this.homeDataUser = '';
      this.homeLoading = false;
      this.homeLoadFailed = false;
      return;
    }
    if (this.homeDataUser !== username) {
      this.homeEvents = [];
      this.homeLoading = true;
      this.homeDataUser = username;
    }
    this.homeDataLoading = true;
    try {
      const events = await DatabaseHelper.getInstance().queryHealthEvents(undefined, username);
      if (!userManager.isLoggedIn() || userManager.getCurrentUsername() !== username) return;
      this.homeEvents = events.filter((event: HealthEvent): boolean => event.eventType === 'fall' || event.eventType === 'sedentary')
        .sort((first: HealthEvent, second: HealthEvent): number => second.eventTime - first.eventTime);
      this.homeLoadFailed = false;
    } catch (_) {
      this.homeLoadFailed = true;
    } finally {
      this.homeLoading = false;
      this.homeDataLoading = false;
    }
  }

  private todayStart(): number {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    return date.getTime();
  }

  private todayCount(): string {
    if (!UserManager.getInstance().isLoggedIn() || this.homeLoading || this.homeLoadFailed) return '—';
    const start = this.todayStart();
    return `${this.homeEvents.filter((event: HealthEvent): boolean => event.eventTime >= start).length}`;
  }

  private comparisonText(): string {
    if (!UserManager.getInstance().isLoggedIn()) return '登录后查看记录';
    if (this.homeLoading) return '正在加载记录';
    if (this.homeLoadFailed) return '加载失败，点击重试';
    const start = this.todayStart();
    const previousDate = new Date(start);
    previousDate.setDate(previousDate.getDate() - 1);
    const today = this.homeEvents.filter((event: HealthEvent): boolean => event.eventTime >= start).length;
    const yesterday = this.homeEvents.filter((event: HealthEvent): boolean => event.eventTime >= previousDate.getTime() && event.eventTime < start).length;
    const difference = today - yesterday;
    return difference === 0 ? '较昨日持平' : difference > 0 ? `较昨日增加 ${difference} 次` : `较昨日减少 ${-difference} 次`;
  }

  private eventTitle(event: HealthEvent): string {
    return event.eventType === 'fall' ? '摔倒告警' : '久坐提醒';
  }

  private eventTime(timestamp: number): string {
    const date = new Date(timestamp);
    return `${`${date.getHours()}`.padStart(2, '0')}:${`${date.getMinutes()}`.padStart(2, '0')}`;
  }

  private eventDate(timestamp: number): string {
    const date = new Date(timestamp);
    return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`;
  }

  private eventWhen(event: HealthEvent): string {
    return `${event.eventTime >= this.todayStart() ? '今天' : this.eventDate(event.eventTime)} ${this.eventTime(event.eventTime)}`;
  }

  private openHistory(): void {
    this.pathStack.pushPathByName('HealthHistory', null);
  }

  private showEventDetails(event: HealthEvent): void {
    this.getUIContext().showAlertDialog({
      title: this.eventTitle(event),
      message: `${this.eventWhen(event)}\n${event.isHandled === 1 ? '已处理' : '待处理'}${event.remark ? `\n${event.remark}` : ''}`,
      primaryButton: { value: '关闭', action: (): void => {} },
      secondaryButton: { value: '全部记录', action: (): void => { this.openHistory(); } },
    });
  }

  private showDeviceStatus(): void {
    this.getUIContext().showAlertDialog({
      title: '家中设备',
      message: `视频服务：${this.deviceOnline ? '可访问' : '暂不可用'}\n告警通道：${this.mqttManager.isConnected ? '已连接' : '未连接'}\n开发板：${this.mqttManager.deviceOnline ? '在线' : '离线'}`,
      primaryButton: { value: '检查连接', action: (): void => { this.runHealthCheck(true); } },
      secondaryButton: { value: '关闭', action: (): void => {} },
    });
  }
  private runHealthCheck(manual: boolean = false): void {
    if (manual && this.isManualHealthCheck) return;
    if (manual) {
      this.isManualHealthCheck = true;
      this.manualHealthCheckMessage = '正在检查服务连接…';
    }
    const req = http.createHttp();
    req.request(this.healthCheckUrl, {
      method: http.RequestMethod.GET,
      connectTimeout: 4000,
      readTimeout: 4000,
    }).then((resp) => {
      this.deviceOnline = resp.responseCode === 200;
      if (!this.deviceOnline) this.expandedVideo = false;
      if (manual) {
        this.isManualHealthCheck = false;
        this.manualHealthCheckMessage = resp.responseCode === 200
          ? '检查完成，服务连接正常'
          : `服务暂不可用（HTTP ${resp.responseCode}），请稍后重试`;
      }
      req.destroy();
    }).catch(() => {
      this.deviceOnline = false;
      this.expandedVideo = false;
      if (manual) {
        this.isManualHealthCheck = false;
        this.manualHealthCheckMessage = '请求失败，请检查网络后重试';
      }
      req.destroy();
    });
  }
  private syncState(): void {
    const userManager = UserManager.getInstance();
    const activeUser = userManager.isLoggedIn() ? userManager.getCurrentUsername() : '';
    if (activeUser !== this.homeDataUser) {
      this.homeEvents = [];
      this.homeLoading = true;
      this.loadHomeEvents();
    }
    if (this.mqttManager) {
      this.latestMessage = this.mqttManager.latestMessage;
      this.isFallDetected = this.mqttManager.isFallDetected;
      this.isSedentaryDetected = this.mqttManager.isSedentaryDetected;
      this.isStrangerDetected = this.mqttManager.isStrangerDetected;
      if (!this.deviceOnline) {
        this.latestMessage = '设备离线';
        this.isFallDetected = false;
        this.isSedentaryDetected = false;
        this.isStrangerDetected = false;
      }
    }
  }

  @Builder
  GradientHeader(): void {
    Column() {
      Row({ space: 10 }) {
        Image($r('app.media.APPicon')).width(38).height(38).borderRadius(11)
          .objectFit(ImageFit.Cover).accessibilityText('智护星应用图标')
        Text('智护星').fontSize(22).fontWeight(FontWeight.Bold)
          .fontColor(this.themeManager.colors.primaryTextColor).layoutWeight(1)
        Button({ type: ButtonType.Normal }) {
          Stack({ alignContent: Alignment.TopEnd }) {
            Image($r('app.media.ic_home_bell')).width(26).height(26)
            if (this.homeEvents.some((event: HealthEvent): boolean => event.isHandled !== 1)) {
              Row().width(7).height(7).borderRadius(4).backgroundColor('#ef4444')
            }
          }
        }.width(44).height(44).backgroundColor(Color.Transparent).borderRadius(22)
          .accessibilityText('查看告警记录').onClick((): void => { this.openHistory(); })
        Button({ type: ButtonType.Normal }) {
          if (this.userAvatarPath.length > 0) {
            Image(fileUri.getUriFromPath(this.userAvatarPath)).width(40).height(40)
              .objectFit(ImageFit.Cover).borderRadius(20)
          } else {
            Image($r('app.media.ic_user_blue')).width(24).height(24)
          }
        }.width(42).height(42).borderRadius(21)
          .backgroundColor(this.themeManager.isDarkMode ? '#20365a' : '#e1ebff')
          .accessibilityText('个人资料')
          .onClick((): void => { this.pathStack.pushPathByName('Profile', null); })
      }.width('100%')
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 8, bottom: 12 })
    .onAreaChange((_oldValue: Area, newValue: Area): void => {
      const height = Number(newValue.height);
      if (height > 0 && Math.abs(height - this.homeHeaderHeight) > 1) this.homeHeaderHeight = height;
    })
  }

  @Builder
  VideoArea(frameWidth: number | string = '92%'): void {
    Stack({ alignContent: Alignment.TopEnd }) {
      if (this.deviceOnline) {
        Web({ src: this.videoUrl, controller: this.webController })
          .width('100%').height('100%').borderRadius(SURFACE_RADIUS)
          .onPageBegin((): void => {
            this.videoFitAttempt = 0;
            this.fitVideoDocument();
          })
        if (this.compactVideoProgress === 0 || this.expandedVideo) {
        Row({ space: 6 }) {
          Row().width(7).height(7).borderRadius(4).backgroundColor('#60a5fa')
          Text('实时画面').fontSize(12).fontWeight(FontWeight.Medium).fontColor('#ffffff')
        }
        .padding({ left: 10, right: 10, top: 7, bottom: 7 })
        .backgroundColor('#b31e293b')
        .borderRadius(100)
        .align(Alignment.TopStart)
        .margin({ left: 12, top: 12 })
        Row({ space: 6 }) {
          Row().width(7).height(7).borderRadius(4).backgroundColor('#34d399')
          Text('在线').fontSize(12).fontWeight(FontWeight.Medium).fontColor('#ffffff')
        }
        .padding({ left: 10, right: 10, top: 7, bottom: 7 })
        .backgroundColor('#b31e293b')
        .borderRadius(100)
        .align(Alignment.BottomStart)
        .margin({ left: 12, bottom: 12 })
        if (getWindowSizeClass(this.viewportWidth) === 'compact') {
          Button({ type: ButtonType.Normal }) {
            Image($r('app.media.ic_home_expand')).width(21).height(21)
          }.width(40).height(40).borderRadius(20).backgroundColor('#b31e293b')
            .align(Alignment.BottomEnd).margin({ right: 12, bottom: 12 })
            .accessibilityText(this.expandedVideo ? '退出画面放大' : '放大实时画面')
            .onClick((): void => { this.expandedVideo = !this.expandedVideo; })
        }
        }
      } else {
        Column({ space: 9 }) {
          Image($r('app.media.ic_camera_off'))
            .width(this.compactVideoProgress === 0 ? 58 : Math.min(42, this.compactVideoFrameWidth() * 0.3))
            .height(this.compactVideoProgress === 0 ? 58 : Math.min(42, this.compactVideoFrameWidth() * 0.3))
            .objectFit(ImageFit.Contain)
            .padding(this.compactVideoProgress === 0 ? 12 : Math.min(8, this.compactVideoFrameWidth() * 0.04))
            .backgroundColor(this.themeManager.isDarkMode ? '#334155' : '#d2e2ff')
            .borderRadius(100)
            .opacity(0.9)
          if (this.compactVideoProgress === 0 || this.compactVideoFrameWidth() >= 110) {
          Text('摄像头未连接')
            .fontSize(this.compactVideoProgress === 0 ? 18 : 13)
            .fontWeight(FontWeight.Medium)
            .fontColor(this.themeManager.colors.primaryTextColor)
          }
          if (this.compactVideoProgress === 0) {
            Text('实时画面与智能监测暂不可用')
              .fontSize(13)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .textAlign(TextAlign.Center)
              .width('90%')
              .maxLines(2)
            Button() {
              Row({ space: 8 }) {
                if (this.isManualHealthCheck) {
                  LoadingProgress().width(16).height(16).color('#ffffff')
                }
                Text(this.isManualHealthCheck ? '正在检查连接' : '立即检查状态')
                  .fontSize(14).fontWeight(FontWeight.Medium).fontColor('#ffffff')
              }.justifyContent(FlexAlign.Center)
            }
            .height(48)
            .padding({ left: 20, right: 20 })
            .backgroundColor('#2563eb')
            .borderRadius(14)
            .enabled(!this.isManualHealthCheck)
            .accessibilityText('立即检查设备状态')
            .onClick((): void => { this.runHealthCheck(true); })
            if (this.manualHealthCheckMessage.length > 0) {
              Text(this.manualHealthCheckMessage)
                .fontSize(12)
                .fontColor(this.isManualHealthCheck ? this.themeManager.colors.linkTextColor
                  : this.deviceOnline ? this.themeManager.colors.successTextColor : this.themeManager.colors.dangerTextColor)
                .textAlign(TextAlign.Center)
                .width('92%')
                .maxLines(2)
            }
          } else if (this.compactVideoFrameWidth() >= 110) {
            Text('设备离线').fontSize(11).fontColor(this.themeManager.colors.secondaryTextColor)
          }
        }
        .width('100%').height('100%').justifyContent(FlexAlign.Center)
        .padding({ left: this.compactVideoProgress === 0 ? 20 : 0, right: this.compactVideoProgress === 0 ? 20 : 0 })
        .backgroundColor(this.themeManager.isDarkMode ? '#1a2744' : '#e5eeff')
        .border({
          width: 1,
          color: this.themeManager.isDarkMode ? '#2d4a7a' : '#d6e4ff'
        })
        .borderRadius(SURFACE_RADIUS)
      }
      if (this.compactVideoProgress === 0 || this.expandedVideo || getWindowSizeClass(this.viewportWidth) !== 'compact') {
        Button({ type: ButtonType.Normal }) {
          Row({ space: 6 }) {
            Image($r('app.media.ic_home')).width(18).height(18)
            Text('家中设备').fontSize(13).fontWeight(FontWeight.Medium)
              .fontColor(this.themeManager.colors.primaryTextColor)
            Image($r('app.media.ic_chevron_right')).width(14).height(14)
          }
          .height('100%')
          .alignItems(VerticalAlign.Center)
          .justifyContent(FlexAlign.Center)
        }.height(40).padding({ left: 12, right: 12 }).borderRadius(20)
          .backgroundColor(this.themeManager.isDarkMode ? '#20365a' : '#ffffff')
          .align(Alignment.TopEnd).margin({ right: 12, top: 12 })
          .accessibilityText('查看家中设备连接状态')
          .onClick((): void => { this.showDeviceStatus(); })
      }
    }
    .width(frameWidth)
    .aspectRatio(4 / 3)
    .border({
      width: 1,
      color: this.themeManager.isDarkMode ? '#2d4a7a' : 'transparent'
    })
    .borderRadius(SURFACE_RADIUS)
  }

  private compactVideoThreshold(): number {
    return Math.max(1, this.compactAreaWidth - 168);
  }

  private compactVideoFrameWidth(): number {
    const fullWidth = Math.max(0, this.compactAreaWidth);
    return fullWidth + (this.miniVideoWidth - fullWidth) * this.compactVideoProgress;
  }

  private compactVideoPositionX(): number {
    return this.miniVideoX * this.compactVideoProgress;
  }

  private compactVideoPositionY(): number {
    return this.homeHeaderHeight * (1 - this.compactVideoProgress) + this.miniVideoY * this.compactVideoProgress;
  }

  private clampMiniVideoWidth(width: number): number {
    return Math.max(0, Math.min(this.compactAreaWidth, width));
  }

  private clampMiniVideoX(x: number): number {
    return Math.max(0, Math.min(this.compactAreaWidth - this.miniVideoWidth, x));
  }

  private clampMiniVideoY(y: number): number {
    const groupHeight = this.miniVideoWidth * 0.75;
    return Math.max(0, Math.min(this.compactAreaHeight - groupHeight, y));
  }

  private updateCompactScroll(absoluteYOffset: number): void {
    // Use the actual offset: accumulating spring rebound deltas can leave a false offset at the top.
    this.compactScrollOffset = Math.max(0, absoluteYOffset);
    if (this.compactScrollOffset === 0 && this.miniVideoWidth === 0) this.miniVideoWidth = 168;
    const progress = Math.min(1, this.compactScrollOffset / this.compactVideoThreshold());
    // Fixed travel distance and linear interpolation keep size proportional to scrolling.
    this.compactVideoProgress = progress;
    if (!this.isCompactVideoMini && progress >= 1) {
      this.isCompactVideoMini = true;
      this.miniVideoX = this.clampMiniVideoX(0);
      this.miniVideoY = this.clampMiniVideoY(12);
    } else if (this.isCompactVideoMini && progress < 1) {
      this.isCompactVideoMini = false;
    }
  }

  @Builder
  VideoResizeEdge(horizontal: boolean, leading: boolean) {
    Stack() {
      Row().width(horizontal ? 3 : 24).height(horizontal ? 24 : 3)
        .borderRadius(2).backgroundColor('#2563eb')
    }
    .width(horizontal ? Math.min(24, Math.max(8, this.miniVideoWidth)) : Math.max(8, this.miniVideoWidth))
    .height(horizontal ? Math.max(8, this.miniVideoWidth * 0.75) : Math.min(24, Math.max(8, this.miniVideoWidth * 0.75)))
    .position({
      x: this.miniVideoX + (horizontal && !leading ? Math.max(0, this.miniVideoWidth - 24) : 0),
      y: this.miniVideoY + (!horizontal && !leading ? Math.max(0, this.miniVideoWidth * 0.75 - 24) : 0)
    })
    .zIndex(4)
    .accessibilityText('拖动画面边框等比缩放，缩到零后回到顶部恢复')
    .gesture(PanGesture({ direction: PanDirection.All, distance: 1 })
      .onActionStart((): void => {
        this.resizingVideo = true;
        this.resizeStartWidth = this.miniVideoWidth;
        this.resizeStartX = this.miniVideoX;
        this.resizeStartY = this.miniVideoY;
      })
      .onActionUpdate((event: GestureEvent): void => {
        const delta = (horizontal ? event.offsetX : event.offsetY / 0.75) * (leading ? -1 : 1);
        this.miniVideoWidth = this.clampMiniVideoWidth(this.resizeStartWidth + delta);
        this.miniVideoX = this.clampMiniVideoX(this.resizeStartX + (horizontal && leading ? this.resizeStartWidth - this.miniVideoWidth : 0));
        this.miniVideoY = this.clampMiniVideoY(this.resizeStartY + (!horizontal && leading ? (this.resizeStartWidth - this.miniVideoWidth) * 0.75 : 0));
      })
      .onActionEnd((): void => { this.resizingVideo = false; })
      .onActionCancel((): void => { this.resizingVideo = false; }))
  }

  @Builder
  MonitorStatusItem(title: string, icon: Resource, detected: boolean, alertText: string, warning: boolean = false): void {
    Column({ space: 6 }) {
      Image(icon).width(26).height(26).objectFit(ImageFit.Contain)
      Text(title).fontSize(15).fontWeight(FontWeight.Medium)
        .fontColor(this.themeManager.colors.primaryTextColor)
      Text(!this.mqttManager.deviceOnline ? '设备未连接' : detected ? alertText : '监测中')
        .fontSize(12)
        .fontColor(!this.mqttManager.deviceOnline ? this.themeManager.colors.secondaryTextColor
          : detected ? warning ? this.themeManager.colors.warningTextColor : this.themeManager.colors.dangerTextColor
          : this.themeManager.colors.successTextColor)
    }.layoutWeight(1).alignItems(HorizontalAlign.Center)
      .accessibilityGroup(true)
      .accessibilityText(`${title}，${!this.mqttManager.deviceOnline ? '设备未连接'
        : detected ? alertText : '监测中'}`)
  }

  @Builder
  MonitorOverview(): void {
    Row() {
      this.MonitorStatusItem('摔倒监测', $r('app.media.ic_shield_blue'), this.isFallDetected, '检测到摔倒')
      Divider().vertical(true).height(48).color(this.themeManager.colors.borderColor)
      this.MonitorStatusItem('人脸监测', $r('app.media.ic_user_blue'), this.isStrangerDetected, '发现陌生人')
      Divider().vertical(true).height(48).color(this.themeManager.colors.borderColor)
      this.MonitorStatusItem('久坐识别', $r('app.media.ic_home_sitting'), this.isSedentaryDetected, '检测到久坐', true)
    }.width('100%').padding({ left: 8, right: 8, top: 14, bottom: 14 })
      .borderRadius(SURFACE_RADIUS)
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
  }

  @Builder
  StatusCards(): void {
    Column({ space: 14 }) {
      Button({ type: ButtonType.Normal }) {
        Row({ space: 10 }) {
          Image($r('app.media.ic_camera')).width(26).height(26)
          Column({ space: 3 }) {
            Text(this.deviceOnline ? '视频服务可访问' : '视频服务暂不可用')
              .fontSize(14).fontWeight(FontWeight.Medium).fontColor(this.themeManager.colors.primaryTextColor)
            Text(this.isManualHealthCheck ? '正在检查连接…' : this.manualHealthCheckMessage.length > 0
              ? this.manualHealthCheckMessage : '查看服务与设备连接状态')
              .fontSize(11).fontColor(this.themeManager.colors.secondaryTextColor)
              .maxLines(2).textOverflow({ overflow: TextOverflow.Ellipsis })
          }.alignItems(HorizontalAlign.Start).layoutWeight(1)
          Image($r('app.media.ic_chevron_right')).width(18).height(18)
        }.width('100%')
      }.width('100%').padding(14).borderRadius(SURFACE_RADIUS)
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .onClick((): void => { this.showDeviceStatus(); })

      Row() {
        Column({ space: 8 }) {
          Row({ space: 8 }) {
            Image($r('app.media.ic_shield_blue')).width(30).height(30)
            Text('今日告警').fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
          }
          Row({ space: 4 }) {
            Text(this.todayCount()).fontSize(34).fontWeight(FontWeight.Bold)
              .fontColor(this.themeManager.colors.primaryTextColor)
            Text('次').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: 14 })
          }
          Text(this.comparisonText()).fontSize(11).fontColor(this.themeManager.colors.secondaryTextColor)
            .maxLines(1).textOverflow({ overflow: TextOverflow.Ellipsis })
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
          .onClick((): void => { if (this.homeLoadFailed) this.loadHomeEvents(); else this.openHistory(); })
        Divider().vertical(true).height(76).color(this.themeManager.colors.borderColor).margin({ left: 12, right: 16 })
        Column({ space: 8 }) {
          Row({ space: 8 }) {
            Image($r('app.media.ic_record')).width(30).height(30)
            Text('最近活动').fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
          }
          Text(this.homeLoading || this.homeLoadFailed || this.homeEvents.length === 0
            ? '—' : this.eventTime(this.homeEvents[0].eventTime))
            .fontSize(30).fontWeight(FontWeight.Bold).fontColor(this.themeManager.colors.primaryTextColor)
          Text(this.homeLoading ? '正在加载' : this.homeLoadFailed ? '加载失败' : this.homeEvents.length === 0
            ? '暂无事件' : this.eventTitle(this.homeEvents[0]))
            .fontSize(11).fontColor(this.themeManager.colors.secondaryTextColor)
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
          .onClick((): void => { this.openHistory(); })
      }.width('100%').padding(16).borderRadius(SURFACE_RADIUS)
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)

      Column({ space: 14 }) {
        Row() {
          Text('最新事件').fontSize(19).fontWeight(FontWeight.Bold).fontColor(this.themeManager.colors.primaryTextColor)
          Blank()
          Button({ type: ButtonType.Normal }) {
            Row({ space: 4 }) {
              Text('查看全部').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
              Image($r('app.media.ic_chevron_right')).width(16).height(16)
            }
          }.height(40).padding({ left: 8, right: 0 }).backgroundColor(Color.Transparent)
            .onClick((): void => { this.openHistory(); })
        }.width('100%')
        if (this.homeLoading) {
          Row({ space: 10 }) {
            LoadingProgress().width(22).height(22).color('#2563eb')
            Text('正在加载家中事件…').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor)
          }.width('100%').justifyContent(FlexAlign.Center).padding({ top: 16, bottom: 16 })
        } else if (this.homeLoadFailed) {
          Button('记录加载失败，点击重试').height(48).width('100%')
            .fontSize(13).fontColor(this.themeManager.colors.linkTextColor)
            .backgroundColor(this.themeManager.isDarkMode ? '#20365a' : '#edf3ff')
            .onClick((): void => { this.loadHomeEvents(); })
        } else if (this.homeEvents.length === 0) {
          Row({ space: 12 }) {
            Image($r('app.media.ic_record')).width(34).height(34)
            Column({ space: 5 }) {
              Text(UserManager.getInstance().isLoggedIn() ? '暂无告警记录' : '登录后查看告警记录').fontSize(14).fontWeight(FontWeight.Medium)
                .fontColor(this.themeManager.colors.primaryTextColor)
              Text('收到摔倒或久坐事件后，会在这里展示').fontSize(12)
                .fontColor(this.themeManager.colors.secondaryTextColor)
            }.alignItems(HorizontalAlign.Start).layoutWeight(1)
          }.width('100%').padding({ top: 12, bottom: 16 })
        } else {
          ForEach(this.homeEvents.slice(0, 3), (event: HealthEvent) => {
            Button({ type: ButtonType.Normal }) {
              Row({ space: 12 }) {
                Image(event.eventType === 'fall' ? $r('app.media.ic_alert_red') : $r('app.media.ic_home_sitting'))
                  .width(42).height(42).padding(8).borderRadius(21)
                  .backgroundColor(this.themeManager.isDarkMode ? '#20365a' : '#edf3ff')
                Column({ space: 5 }) {
                  Text(this.eventTitle(event)).fontSize(15).fontWeight(FontWeight.Medium)
                    .fontColor(this.themeManager.colors.primaryTextColor)
                  Text(this.eventWhen(event)).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
                }.alignItems(HorizontalAlign.Start).layoutWeight(1)
                Text('查看详情').fontSize(12).fontColor(this.themeManager.colors.linkTextColor)
                Image($r('app.media.ic_chevron_right')).width(16).height(16)
              }.width('100%')
            }.width('100%').padding(12).borderRadius(12).backgroundColor(Color.Transparent)
              .border({ width: 1, color: this.themeManager.colors.borderColor })
              .onClick((): void => { this.showEventDetails(event); })
          }, (event: HealthEvent): string => event.id !== undefined ? event.id.toString() : event.eventType + event.eventTime.toString())
        }
      }.width('100%').padding({ left: 16, right: 16, top: 10, bottom: 16 }).borderRadius(SURFACE_RADIUS)
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)

      Button({ type: ButtonType.Normal }) {
        Row() {
          Text('通话与设备信息').fontSize(14).fontWeight(FontWeight.Medium)
            .fontColor(this.themeManager.colors.primaryTextColor)
          Blank()
          Image($r('app.media.ic_chevron_right')).width(18).height(18)
            .rotate({ angle: this.showMonitorDetails ? 90 : 0 })
        }.width('100%')
      }.height(48).width('100%').padding({ left: 16, right: 16 }).borderRadius(SURFACE_RADIUS)
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .accessibilityText(this.showMonitorDetails ? '收起通话与设备信息' : '展开通话与设备信息')
        .onClick((): void => { this.showMonitorDetails = !this.showMonitorDetails; })
      if (this.showMonitorDetails) {
        Column({ space: 14 }) {
          Text(this.latestMessage).fontSize(14).fontColor(this.themeManager.colors.primaryTextColor)
          Divider().color(this.themeManager.colors.borderColor)
          Row() {
            Text('通话音量').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor)
            Blank()
            Text(Math.floor(this.volumeLevel).toString() + '%').fontSize(13).fontColor(this.themeManager.colors.primaryTextColor)
          }.width('100%')
          Slider({ value: this.volumeLevel, style: SliderStyle.InSet })
            .width('100%').selectedColor('#2563eb')
            .trackColor(this.themeManager.isDarkMode ? '#334155' : '#e7eeff')
            .onChange((value: number): void => { this.volumeLevel = value; })
        }.width('100%').padding(16).borderRadius(SURFACE_RADIUS)
          .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      }
    }.width('100%').padding({ left: 12, right: 12, top: 0 })
  }

  /** 状态卡滚动区，手机竖排 / 大屏右栏共用 */
  @Builder
  CardsScroll(): void {
    Scroll() {
      Column() {
        Column() { this.StatusCards() }.width('100%').constraintSize({ maxWidth: 640 }).alignItems(HorizontalAlign.Center)
        Blank().height(24)
      }.width('100%')
    }
    .width('100%').height('100%')
    .scrollBar(BarState.Off)
    .edgeEffect(EdgeEffect.Spring)
  }

  build() {
    Column() {
      if (getWindowSizeClass(this.viewportWidth) === 'compact') {
        Stack({ alignContent: Alignment.TopStart }) {
          Scroll(this.homeScroller) {
            Column() {
              this.GradientHeader()
              Blank().width('100%').height(Math.max(0, this.compactAreaWidth) * 0.75)
              Column() { this.MonitorOverview() }
                .width('100%').padding({ left: 12, right: 12, top: 12, bottom: 14 })
              this.StatusCards()
              this.CallButton()
              Blank().height(12)
            }.width('100%')
          }.width('100%').height('100%').scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
            .onDidScroll((_xOffset: number, _yOffset: number, _scrollState: ScrollState): void => {
              this.updateCompactScroll(this.homeScroller.currentOffset().yOffset);
            })
          Stack({ alignContent: Alignment.Center }) { this.VideoArea('100%') }
            .width(this.expandedVideo ? this.compactAreaWidth : this.compactVideoFrameWidth())
            .height(this.expandedVideo ? this.compactAreaHeight : this.compactVideoFrameWidth() * 0.75)
            .backgroundColor(this.expandedVideo ? '#0f172a' : Color.Transparent)
            .position({ x: this.expandedVideo ? 0 : this.compactVideoPositionX(), y: this.expandedVideo ? 0 : this.compactVideoPositionY() })
            .clip(true)
            .borderRadius(this.expandedVideo ? 0 : SURFACE_RADIUS)
            .border({ width: this.isCompactVideoMini && this.miniVideoWidth > 0 ? 2 : 0, color: '#2563eb' })
            .visibility(this.compactVideoFrameWidth() > 0 || this.expandedVideo ? Visibility.Visible : Visibility.Hidden)
            .zIndex(2)
            .parallelGesture(PanGesture({ direction: PanDirection.All, distance: 4 })
              .onActionStart((): void => {
                this.miniVideoDragEnabled = this.isCompactVideoMini && !this.expandedVideo;
                this.videoPanScrollEnabled = !this.isCompactVideoMini && !this.expandedVideo;
                this.videoPanScrollStart = this.homeScroller.currentOffset().yOffset;
                if (this.miniVideoDragEnabled) {
                  this.miniVideoDragStartX = this.miniVideoX;
                  this.miniVideoDragStartY = this.miniVideoY;
                }
              })
              .onActionUpdate((event: GestureEvent): void => {
                if (this.miniVideoDragEnabled && this.isCompactVideoMini && !this.expandedVideo) {
                  this.miniVideoX = this.clampMiniVideoX(this.miniVideoDragStartX + event.offsetX);
                  this.miniVideoY = this.clampMiniVideoY(this.miniVideoDragStartY + event.offsetY);
                } else if (this.videoPanScrollEnabled) {
                  this.homeScroller.scrollTo({
                    xOffset: 0,
                    yOffset: Math.max(0, this.videoPanScrollStart - event.offsetY),
                    animation: false
                  });
                }
              })
              .onActionEnd((): void => { this.miniVideoDragEnabled = false; this.videoPanScrollEnabled = false; })
              .onActionCancel((): void => { this.miniVideoDragEnabled = false; this.videoPanScrollEnabled = false; }))
            .accessibilityText('实时画面，拖动中央移动，拖动边框等比缩放')
          if (this.isCompactVideoMini && !this.expandedVideo && (this.miniVideoWidth > 0 || this.resizingVideo)) {
            this.VideoResizeEdge(true, true)
            this.VideoResizeEdge(true, false)
            this.VideoResizeEdge(false, true)
            this.VideoResizeEdge(false, false)
          }
        }.layoutWeight(1).width('100%').height('100%')
          .onAreaChange((_oldValue: Area, newValue: Area): void => {
            const width = Number(newValue.width);
            const height = Number(newValue.height);
            if (width > 0) this.compactAreaWidth = width;
            if (height > 0) this.compactAreaHeight = height;
            if (this.isCompactVideoMini) {
              this.miniVideoWidth = this.clampMiniVideoWidth(this.miniVideoWidth);
              this.miniVideoX = this.clampMiniVideoX(this.miniVideoX);
              this.miniVideoY = this.clampMiniVideoY(this.miniVideoY);
            }
          })
      } else {
        this.GradientHeader()
        Row() {
          Column() {
            this.VideoArea('100%')
            Column() { this.MonitorOverview() }.width('100%').margin({ top: 12 })
            this.CallButton()
          }.layoutWeight(1).height('100%').padding({ left: 12, right: 12 })
            .justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
          Column() { this.CardsScroll() }.layoutWeight(1).height('100%')
        }.layoutWeight(1).width('100%').constraintSize({ maxWidth: 1100 }).alignItems(VerticalAlign.Top)
      }
    }.width('100%').height('100%')
      .linearGradient({
        direction: GradientDirection.Bottom,
        colors: this.themeManager.isDarkMode ? [['#0f172a', 0], ['#0f172a', 1]]
          : [['#dce9ff', 0], ['#f0f5ff', 0.45], ['#f0f4ff', 1]]
      })
      .onAreaChange((_oldValue: Area, newValue: Area): void => {
        const width = Number(newValue.width);
        if (width > 0) this.viewportWidth = width;
      })
  }

  @Builder
  CallButton(): void {
    Button() {
        Row() {
          Image($r(this.isTalking ? 'app.media.ic_offcall' : 'app.media.ic_phone_white'))
            .width(22).height(22).objectFit(ImageFit.Contain).margin({ right: '3%' })
          Text(this.isTalking ? '结束通话' : '发起通话')
            .fontSize(16).fontWeight(FontWeight.Medium).fontColor('#ffffff')
        }.justifyContent(FlexAlign.Center)
      }
      .width('88%').height(52).constraintSize({ maxWidth: 560 })
      .linearGradient({
        direction: GradientDirection.Left,
        colors: this.isTalking
          ? [['#991b1b', 0.0], ['#dc2626', 1.0]]
          : [['#1e3a8a', 0.0], ['#2563eb', 1.0]]
      })
      .borderRadius(100)
      .shadow({ radius: 16, color: this.isTalking ? '#ef444440' : '#3b82f640', offsetY: 8 })
      .scale({ x: this.btnScale, y: this.btnScale })
      .animation({ duration: 150, curve: Curve.EaseInOut })
      .margin({ bottom: 14, top: 20 })
      .onClick(async (): Promise<void> => {
        this.btnScale = 0.93;
        setTimeout(() => { this.btnScale = 1.0; }, 150);
        if (this.isTalking) {
          await this.audioManager.stopCall(); this.isTalking = false;
        } else {
          // 设备未连接时不允许发起通话，仅提示
          if (!this.deviceOnline) {
            showToast(this.getUIContext(), { message: '设备未连接，无法发起通话' });
            return;
          }
          const atManager = abilityAccessCtrl.createAtManager();
          const res = await atManager.requestPermissionsFromUser(this.context, ['ohos.permission.MICROPHONE']);
          if (res.authResults[0] === 0) { await this.audioManager.startCall(); this.isTalking = true; }
        }
      })
  }
}
