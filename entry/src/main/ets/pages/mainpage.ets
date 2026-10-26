import { MqttManager } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';
import { DatabaseHelper, HealthEvent } from '../database/DatabaseHelper';
import { UserManager } from '../common/UserManager';
import { isHomeEventType, homeEventTitle } from '../common/HomeEventRules';
import { CameraStreamView } from '../components/CameraStreamView';
import { SURFACE_RADIUS } from '../components/GradientHeader';

@Component
export struct mainPage {
  pathStack: NavPathStack = new NavPathStack();
  @StorageLink('homeCameraFullscreenActive') cameraFullscreenActive: boolean = false;
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State homeEvents: HealthEvent[] = [];
  @State homeLoading: boolean = true;
  @State homeLoadFailed: boolean = false;
  @State viewportWidth: number = 360;
  private homeDataTimer: number = -1;
  private homeDataLoading: boolean = false;
  private homeDataUser: string = '';

  aboutToAppear(): void {
    this.mqttManager.connectAndSubscribe();
    this.loadHomeEvents();
    this.homeDataTimer = setInterval((): void => { this.loadHomeEvents(); }, 2000) as number;
  }

  aboutToDisappear(): void {
    if (this.homeDataTimer !== -1) clearInterval(this.homeDataTimer);
    this.homeDataTimer = -1;
  }

  onPageShow(): void { this.loadHomeEvents(); }

  private openCamera(): void {
    this.cameraFullscreenActive = true;
    this.pathStack.pushPathByName('CameraFullscreen', null);
  }

  @Builder
  CameraHeader(): void {
    Row({ space: 16 }) {
      Button({ type: ButtonType.Normal }) {
        Column({ space: 8 }) {
          Image($r('app.media.ic_camera_round_solid')).width(72).height(80)
            .fillColor(this.mqttManager.isConnected ? this.themeManager.colors.successTextColor
              : this.themeManager.colors.dangerTextColor)
          Text(this.mqttManager.isConnected ? '通道正常' : '通道异常').fontSize(14).fontWeight(FontWeight.Medium)
            .fontColor(this.mqttManager.isConnected ? this.themeManager.colors.successTextColor
              : this.themeManager.colors.dangerTextColor)
          Text('点击全屏').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
        }.width('100%').height('100%').justifyContent(FlexAlign.Center)
      }.width(96).height(132).padding(0).borderRadius(16).backgroundColor(Color.Transparent)
        .accessibilityText(`点击全屏查看摄像头，告警通道${this.mqttManager.isConnected ? '正常' : '异常'}`)
        .onClick((): void => { this.openCamera(); })

      Stack() {
        if (!this.cameraFullscreenActive) {
          CameraStreamView()
        } else {
          Column().width('100%').height('100%').backgroundColor('#0f172a')
        }
        Column() {
          Blank()
          Row({ space: 6 }) {
            Text('点按全屏').fontSize(12).fontColor('#ffffff')
            Image($r('app.media.ic_home_expand')).width(18).height(18)
          }.padding(7).borderRadius(10).backgroundColor('#b31e293b')
        }.width('100%').height('100%').padding(8).alignItems(HorizontalAlign.End)
          .onClick((): void => { this.openCamera(); })
          .accessibilityText('实时摄像头预览，点击全屏查看')
      }.width(Math.min(220, Math.max(140, this.viewportWidth - 160))).aspectRatio(4 / 3)
        .clip(true).borderRadius(SURFACE_RADIUS).backgroundColor('#0f172a')
    }.width('100%').justifyContent(FlexAlign.SpaceBetween)
      .padding({ left: 16, right: 16, top: 8, bottom: 20 })
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
      this.homeEvents = events.filter((event: HealthEvent): boolean => isHomeEventType(event.eventType))
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
    return homeEventTitle(event.eventType);
  }

  private eventAccent(event: HealthEvent): string {
    if (event.eventType === 'fall') return this.themeManager.isDarkMode ? '#fca5a5' : '#b91c1c';
    if (event.eventType === 'stranger') return this.themeManager.isDarkMode ? '#fcd34d' : '#946200';
    return this.themeManager.isDarkMode ? '#93c5fd' : '#2563eb';
  }

  private eventSurface(event: HealthEvent): string {
    if (event.eventType === 'fall') return this.themeManager.isDarkMode ? '#3b2028' : '#fff1f2';
    if (event.eventType === 'stranger') return this.themeManager.isDarkMode ? '#352d18' : '#fff8db';
    return this.themeManager.colors.cardBackgroundColor;
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

  @Builder
  StatusCards(): void {
    Column({ space: 14 }) {
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
              Text('收到摔倒、久坐或陌生人事件后，会在这里展示').fontSize(12)
                .fontColor(this.themeManager.colors.secondaryTextColor)
            }.alignItems(HorizontalAlign.Start).layoutWeight(1)
          }.width('100%').padding({ top: 12, bottom: 16 })
        } else {
          ForEach(this.homeEvents.slice(0, 3), (event: HealthEvent) => {
            Button({ type: ButtonType.Normal }) {
              Row({ space: 12 }) {
                Image(event.eventType === 'fall' ? $r('app.media.ic_alert_red')
                  : event.eventType === 'stranger' ? $r('app.media.ic_home_visitor') : $r('app.media.ic_home_sitting'))
                  .width(42).height(42).padding(8).borderRadius(21)
                  .fillColor(this.eventAccent(event))
                  .backgroundColor(event.eventType === 'fall' || event.eventType === 'stranger'
                    ? this.eventSurface(event) : this.themeManager.isDarkMode ? '#20365a' : '#edf3ff')
                Column({ space: 5 }) {
                  Text(this.eventTitle(event)).fontSize(15).fontWeight(FontWeight.Medium)
                    .fontColor(this.eventAccent(event))
                  Text(this.eventWhen(event)).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
                }.alignItems(HorizontalAlign.Start).layoutWeight(1)
                Text('查看详情').fontSize(12).fontColor(this.themeManager.colors.linkTextColor)
                Image($r('app.media.ic_chevron_right')).width(16).height(16)
              }.width('100%')
            }.width('100%').padding(12).borderRadius(12).backgroundColor(this.eventSurface(event))
              .border({ width: 1, color: this.themeManager.colors.borderColor })
              .onClick((): void => { this.showEventDetails(event); })
          }, (event: HealthEvent): string => event.id !== undefined ? event.id.toString() : event.eventType + event.eventTime.toString())
        }
      }.width('100%').padding({ left: 16, right: 16, top: 10, bottom: 16 }).borderRadius(SURFACE_RADIUS)
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)

    }.width('100%').padding({ left: 16, right: 16 })
  }

  build() {
    Scroll() {
      Column() {
        this.CameraHeader()
        this.StatusCards()
        Blank().height(24)
      }.width('100%').constraintSize({ maxWidth: 640 })
    }.width('100%').height('100%').scrollBar(BarState.Off)
      .linearGradient({
        direction: GradientDirection.Bottom,
        colors: this.themeManager.isDarkMode ? [['#0f172a', 0], ['#0f172a', 1]]
          : [['#dce9ff', 0], ['#f0f5ff', 0.45], ['#f0f4ff', 1]]
      })
      .onAreaChange((_oldArea: Area, area: Area): void => {
        const width = Number(area.width);
        if (width > 0) this.viewportWidth = width;
      })
  }
}
