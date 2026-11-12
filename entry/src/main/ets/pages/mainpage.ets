import { CarePalette, carePalette, careIconTint } from '../common/CarePalette';
import { MqttManager } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';
import { DatabaseHelper, HealthEvent } from '../database/DatabaseHelper';
import { UserManager } from '../common/UserManager';
import { isHomeEventType, homeEventTitle, homeEventAccent, homeEventSurface } from '../common/HomeEventRules';
import { CameraStreamView } from '../components/CameraStreamView';
import { SURFACE_RADIUS } from '../components/GradientHeader';
import { AudioTransferManager } from '../common/AudioTransferManager';
import { abilityAccessCtrl, common } from '@kit.AbilityKit';
import { showToast, softTap } from '../common/UiFeedback';

@Component
export struct mainPage {
  @Prop bottomInset: number = 0;
  onTabScroll: (delta: number, state: ScrollState) => void = () => {};
  pathStack: NavPathStack = new NavPathStack();
  @StorageLink('homeCameraFullscreenActive') cameraFullscreenActive: boolean = false;
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State homeEvents: HealthEvent[] = [];
  @State homeLoading: boolean = true;
  @State homeLoadFailed: boolean = false;
  @State isTalking: boolean = false;
  @State callBusy: boolean = false;
  private audioManager: AudioTransferManager = AudioTransferManager.getInstance();
  private homeVisible: boolean = false;
  private homeDataTimer: number = -1;
  private homeDataLoading: boolean = false;
  private homeDataUser: string = '';

  aboutToAppear(): void {
    this.homeVisible = true;
    this.mqttManager.connectAndSubscribe();
    this.loadHomeEvents();
    this.homeDataTimer = setInterval((): void => {
      this.loadHomeEvents();
      this.isTalking = this.audioManager.isCallActive();
    }, 2000) as number;
  }

  aboutToDisappear(): void {
    this.homeVisible = false;
    this.audioManager.stopCall();
    this.isTalking = false;
    if (this.homeDataTimer !== -1) clearInterval(this.homeDataTimer);
    this.homeDataTimer = -1;
  }

  onPageShow(): void { this.loadHomeEvents(); }

  private openCamera(): void {
    this.cameraFullscreenActive = true;
    this.pathStack.pushPathByName('CameraFullscreen', null);
  }

  private async toggleCall(): Promise<void> {
    if (this.callBusy) return;
    this.callBusy = true;
    try {
      if (this.isTalking || this.audioManager.isCallActive()) {
        await this.audioManager.stopCall();
        this.isTalking = false;
        return;
      }
      if (!this.mqttManager.deviceOnline) {
        showToast(this.getUIContext(), { message: '设备未连接，无法发起通话' });
        return;
      }
      const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
      const permission = await abilityAccessCtrl.createAtManager()
        .requestPermissionsFromUser(context, ['ohos.permission.MICROPHONE']);
      if (!this.homeVisible) return;
      if (permission.authResults[0] !== 0) {
        showToast(this.getUIContext(), { message: '需要麦克风权限才能通话' });
        return;
      }
      await this.audioManager.startCall();
      if (!this.homeVisible) { await this.audioManager.stopCall(); return; }
      this.isTalking = this.audioManager.isCallActive();
    } catch (_) {
      this.isTalking = false;
      if (this.homeVisible) showToast(this.getUIContext(), { message: '通话连接失败，请稍后重试' });
    } finally {
      this.callBusy = false;
    }
  }

  private palette(): CarePalette {
    return carePalette(this.mqttManager.isFallDetected, this.mqttManager.isSedentaryDetected,
      this.mqttManager.deviceOnline);
  }

  private panelColor(): string {
    return '#24FFFFFF';
  }

  @Builder
  CameraHeader(): void {
    Column({ space: 15 }) {
      Text(this.palette().label).fontSize(34).fontWeight(FontWeight.Bold)
        .fontColor('#FFFFFF').width('100%')
      Text(this.palette().detail).fontSize(14).lineHeight(21).fontColor('#E2F0EA').width('100%')
      if (this.callBusy || this.isTalking) {
        Row({ space: 8 }) {
          Circle().width(7).height(7).fill(this.palette().accent)
          Text(this.callBusy ? (this.isTalking ? '正在结束通话…' : '正在连接通话…') : '通话中')
            .fontSize(13).fontColor('#FFFFFF')
        }.width('100%').padding(12).borderRadius(SURFACE_RADIUS).backgroundColor(this.panelColor())
      }
      Row({ space: 10 }) {
        Button(this.callBusy ? (this.isTalking ? '结束中' : '连接中') : this.isTalking ? '挂断' : '通话')
          .layoutWeight(1).height(46)
          .backgroundColor(this.isTalking ? '#8C1D0C' : this.palette().solid).fontColor('#FFFFFF')
          .enabled(!this.callBusy).onClick((): void => { softTap(); this.toggleCall(); })
        Button('看画面').layoutWeight(1).height(46)
          .backgroundColor(this.panelColor()).fontColor('#FFFFFF')
          .onClick((): void => { softTap(); this.openCamera(); })
      }.width('100%')
      Stack() {
        if (!this.cameraFullscreenActive) {
          CameraStreamView({ placeholderSurface: this.palette().backdrop })
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
          .onClick((): void => { softTap(); this.openCamera(); })
          .accessibilityText('实时摄像头预览，点击全屏查看')
      }.width('100%').aspectRatio(2.05)
        .clip(true).borderRadius(SURFACE_RADIUS).backgroundColor(this.palette().backdrop)
    }.width('100%').alignItems(HorizontalAlign.Start)
      .padding({ left: 16, right: 16, top: 16, bottom: 18 })
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
    return homeEventAccent(event.eventType, this.themeManager.isDarkMode);
  }

  private eventSurface(event: HealthEvent): string {
    return event.eventType === 'sedentary' ? this.themeManager.colors.cardBackgroundColor
      : homeEventSurface(event.eventType, this.themeManager.isDarkMode);
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
    this.pathStack.pushPathByName('TodayEvents', null);
  }

  private showEventDetails(event: HealthEvent): void {
    this.getUIContext().showAlertDialog({
      title: this.eventTitle(event),
      message: `${this.eventWhen(event)}\n${event.isHandled === 1 ? '已处理' : '待处理'}${event.remark ? `\n${event.remark}` : ''}`,
      primaryButton: { value: '关闭', action: (): void => {} },
      secondaryButton: { value: '当天记录', action: (): void => { this.openHistory(); } },
    });
  }

  @Builder
  StatusCards(): void {
    Column({ space: 12 }) {
      Row() {
        Column({ space: 8 }) {
          Row({ space: 8 }) {
            Image($r('app.media.ic_shield_blue')).width(30).height(30).supportSvg2(true).colorFilter(careIconTint(this.palette().accent))
            Text('今日提醒').fontSize(14).fontColor('#E2F0EA')
          }
          Row({ space: 4 }) {
            Text(this.todayCount()).fontSize(34).fontWeight(FontWeight.Bold)
              .fontColor('#FFFFFF')
            Text('次').fontSize(12).fontColor('#E2F0EA').margin({ top: 14 })
          }
          Text(this.comparisonText()).fontSize(11).fontColor('#E2F0EA')
            .maxLines(1).textOverflow({ overflow: TextOverflow.Ellipsis })
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
          .onClick((): void => { if (this.homeLoadFailed) this.loadHomeEvents(); else this.openHistory(); })
        Divider().vertical(true).height(76).color('#35FFFFFF').margin({ left: 12, right: 16 })
        Column({ space: 8 }) {
          Row({ space: 8 }) {
            Image($r('app.media.ic_record')).width(30).height(30).supportSvg2(true).colorFilter(careIconTint(this.palette().accent))
            Text('最近活动').fontSize(14).fontColor('#E2F0EA')
          }
          Text(this.homeLoading || this.homeLoadFailed || this.homeEvents.length === 0
            ? '—' : this.eventTime(this.homeEvents[0].eventTime))
            .fontSize(30).fontWeight(FontWeight.Bold).fontColor('#FFFFFF')
          Text(this.homeLoading ? '正在加载' : this.homeLoadFailed ? '加载失败' : this.homeEvents.length === 0
            ? '暂无事件' : this.eventTitle(this.homeEvents[0]))
            .fontSize(11).fontColor('#E2F0EA')
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
          .onClick((): void => { this.openHistory(); })
      }.width('100%').padding({
        left: 16, right: 16,
        top: 14,
        bottom: 14,
      }).borderRadius(SURFACE_RADIUS)
        .backgroundColor(this.panelColor())

      Column({ space: 14 }) {
        Row() {
          Text('最新事件').fontSize(19).fontWeight(FontWeight.Bold).fontColor('#FFFFFF')
          Blank()
          Button({ type: ButtonType.Normal }) {
            Row({ space: 4 }) {
              Text('查看全部').fontSize(12).fontColor('#E2F0EA')
              Image($r('app.media.ic_chevron_right')).width(16).height(16)
            }
          }.height(40).padding({ left: 8, right: 0 }).backgroundColor(Color.Transparent)
            .onClick((): void => { this.openHistory(); })
        }.width('100%')
        if (this.homeLoading) {
          Row({ space: 10 }) {
            LoadingProgress().width(22).height(22).color(this.palette().accent)
            Text('正在加载家中事件…').fontSize(13).fontColor('#E2F0EA')
          }.width('100%').justifyContent(FlexAlign.Center).padding({ top: 16, bottom: 16 })
        } else if (this.homeLoadFailed) {
          Button('记录加载失败，点击重试').height(48).width('100%')
            .fontSize(13).fontColor(this.palette().accent)
            .backgroundColor(this.panelColor())
            .onClick((): void => { this.loadHomeEvents(); })
        } else if (this.homeEvents.length === 0) {
          Row({ space: 12 }) {
            Image($r('app.media.ic_record')).width(34).height(34).supportSvg2(true).colorFilter(careIconTint(this.palette().accent))
            Column({ space: 5 }) {
              Text(UserManager.getInstance().isLoggedIn() ? '暂无告警记录' : '登录后查看告警记录').fontSize(14).fontWeight(FontWeight.Medium)
                .fontColor('#FFFFFF')
              Text('收到摔倒、久坐或陌生人事件后，会在这里展示').fontSize(12)
                .fontColor('#E2F0EA')
            }.alignItems(HorizontalAlign.Start).layoutWeight(1)
          }.width('100%').padding({
            top: 14,
            bottom: 14,
          })
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
                    .fontColor(this.palette().accent)
                  Text(this.eventWhen(event)).fontSize(12).fontColor('#E2F0EA')
                }.alignItems(HorizontalAlign.Start).layoutWeight(1)
                Text('查看详情').fontSize(12).fontColor(this.palette().accent)
                Image($r('app.media.ic_chevron_right')).width(16).height(16)
              }.width('100%')
            }.width('100%').padding(12).borderRadius(12).backgroundColor(this.panelColor())
              .border({ width: 1, color: '#35FFFFFF' })
              .onClick((): void => { this.showEventDetails(event); })
          }, (event: HealthEvent): string => event.id !== undefined ? event.id.toString() : event.eventType + event.eventTime.toString())
        }
      }.width('100%').padding({ left: 16, right: 16, top: 10, bottom: 16 }).borderRadius(SURFACE_RADIUS)
        .backgroundColor(this.panelColor())

    }.width('100%').padding({ left: 16, right: 16 })
  }

  build() {
    Scroll() {
      Column() {
        this.CameraHeader()
        this.StatusCards()
        Blank().height(24 + this.bottomInset)
      }.width('100%').constraintSize({ maxWidth: 640 })
    }.width('100%').height('100%').scrollBar(BarState.Off).align(Alignment.Top)
      .onDidScroll((_x: number, y: number, state: ScrollState): void => { this.onTabScroll(y, state); })
      .linearGradient({
        direction: GradientDirection.Bottom,
        colors: [[this.palette().glow, 0], [this.palette().backdrop, 0.72], [this.palette().backdrop, 1]],
      })
  }
}
