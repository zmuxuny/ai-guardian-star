import { CarePalette, carePalette, careIconTint } from '../common/CarePalette';
import { MqttManager } from './MqttManager';
import { DatabaseHelper, HealthEvent } from '../database/DatabaseHelper';
import { UserManager } from '../common/UserManager';
import { isHomeEventType, homeEventTitle } from '../common/HomeEventRules';
import { CameraStreamView } from '../components/CameraStreamView';
import { AudioTransferManager } from '../common/AudioTransferManager';
import { toggleDeviceCall } from '../common/CallControl';
import { curves } from '@kit.ArkUI';
import { reduceMotion, softTap } from '../common/UiFeedback';

// 样张 docs/ui-demo 的深色状态页取值
const GLASS: string = '#24FFFFFF';
const GLASS_EDGE: string = '#2EFFFFFF';
const ON2: string = '#B8FFFFFF';
const LINE: string = '#29FFFFFF';
const PANEL_RADIUS: number = 28;

@Component
export struct mainPage {
  @Prop bottomInset: number = 0;
  onTabScroll: (delta: number, state: ScrollState) => void = () => {};
  pathStack: NavPathStack = new NavPathStack();
  @StorageLink('homeCameraFullscreenActive') @Watch('onFullscreenChange') cameraFullscreenActive: boolean = false;
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State homeEvents: HealthEvent[] = [];
  @State homeLoading: boolean = true;
  @State homeLoadFailed: boolean = false;
  @State isTalking: boolean = false;
  @State callBusy: boolean = false;
  @State pressed: string = '';
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
      await toggleDeviceCall(this.getUIContext(), (): boolean => this.homeVisible);
    } finally {
      this.callBusy = false;
      this.isTalking = this.audioManager.isCallActive();
    }
  }

  /** 从全屏画面返回时立即同步通话状态（全屏里可能挂断或接通） */
  onFullscreenChange(): void {
    if (!this.cameraFullscreenActive) this.isTalking = this.audioManager.isCallActive();
  }

  private palette(): CarePalette {
    return carePalette(this.mqttManager.isFallDetected, this.mqttManager.isSedentaryDetected,
      this.mqttManager.deviceOnline);
  }

  /** 按下回弹（样张 .press）：减弱动态效果时不缩放 */
  private pressScale(key: string, shrink: number): number {
    return this.pressed === key && !reduceMotion() ? shrink : 1;
  }

  private trackPress(key: string, event: TouchEvent): void {
    if (event.type === TouchType.Down) this.pressed = key;
    else if (event.type === TouchType.Up || event.type === TouchType.Cancel) this.pressed = '';
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

  private todayEvents(): HealthEvent[] {
    const start = this.todayStart();
    return this.homeEvents.filter((event: HealthEvent): boolean => event.eventTime >= start);
  }

  private todayCountOf(type: string): number {
    return this.todayEvents().filter((event: HealthEvent): boolean => event.eventType === type).length;
  }

  private dataReady(): boolean {
    return UserManager.getInstance().isLoggedIn() && !this.homeLoading && !this.homeLoadFailed;
  }

  private todaySummary(): string {
    if (!UserManager.getInstance().isLoggedIn()) return '登录后查看';
    if (this.homeLoading) return '正在加载';
    if (this.homeLoadFailed) return '加载失败，点击重试';
    const parts: string[] = [];
    const sit = this.todayCountOf('sedentary');
    const visitor = this.todayCountOf('stranger');
    if (sit > 0) parts.push(`久坐 ${sit} 次`);
    if (visitor > 0) parts.push(`陌生人 ${visitor} 次`);
    return parts.length > 0 ? parts.join(' · ') : '一切正常';
  }

  /** 大字下方两行说明（样张 .sub） */
  private heroLines(): string {
    if (this.callBusy) return this.isTalking ? '正在结束通话…' : '正在连接通话…';
    if (this.isTalking) return '通话中，点挂断结束';
    if (!this.dataReady()) return this.palette().detail;
    const falls = this.todayCountOf('fall');
    const first = falls > 0 ? `今天跌倒 ${falls} 次` : '今天没有跌倒';
    const latest = this.homeEvents.length > 0
      ? `最近事件 ${this.eventTime(this.homeEvents[0].eventTime)} ${this.eventTitle(this.homeEvents[0])}`
      : this.palette().detail;
    return `${first}\n${latest}`;
  }

  private eventTitle(event: HealthEvent): string {
    return homeEventTitle(event.eventType);
  }

  private eventTime(timestamp: number): string {
    const date = new Date(timestamp);
    return `${`${date.getHours()}`.padStart(2, '0')}:${`${date.getMinutes()}`.padStart(2, '0')}`;
  }

  private eventDate(timestamp: number): string {
    const date = new Date(timestamp);
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  }

  private eventWhen(event: HealthEvent): string {
    return `${event.eventTime >= this.todayStart() ? '今天' : this.eventDate(event.eventTime)} ${this.eventTime(event.eventTime)}`;
  }

  private eventLine(event: HealthEvent): string {
    const when = event.eventTime >= this.todayStart() ? this.eventTime(event.eventTime) : this.eventWhen(event);
    return event.remark ? `${when} · ${event.remark}` : when;
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

  private eventIcon(event: HealthEvent): Resource {
    return event.eventType === 'fall' ? $r('app.media.ic_alert_red')
      : event.eventType === 'stranger' ? $r('app.media.ic_home_visitor') : $r('app.media.ic_home_sitting');
  }

  private eventInk(event: HealthEvent): string {
    return event.eventType === 'fall' ? '#C7361F' : event.eventType === 'stranger' ? '#1B2E5E' : '#3A2600';
  }

  private eventThumb(event: HealthEvent): string {
    return event.eventType === 'fall' ? '#FFFFFF' : event.eventType === 'stranger' ? '#C9D6FF' : '#FFD27A';
  }

  // ───────── 背景光斑（样张 .amb） ─────────
  @Builder
  Ambient(): void {
    Stack() {
      this.Blob(this.palette().tone, '8C', 460, 420, '30%', -40)
      this.Blob(this.palette().tone2, '8C', 460, 520, -190, 120)
      this.Blob(this.palette().accent, '40', 420, 360, 20, 520)
    }.width('100%').height('100%').backgroundColor(this.palette().backdrop)
    .animation({ duration: reduceMotion() ? 0 : 900, curve: Curve.EaseInOut })
    .hitTestBehavior(HitTestMode.None)
    // 光斑铺满状态栏和手势条，只裁掉横向溢出，保证安全区和页面同色
    .clip(true)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }

  /** 柔光斑：径向渐变代替 CSS blur(54px) */
  @Builder
  Blob(hex: string, alpha: string, w: number, h: number, x: Length, y: number): void {
    Column().width(w).height(h).position({ x: x, y: y })
      .radialGradient({
        center: ['50%', '50%'], radius: Math.max(w, h) / 2,
        colors: [['#' + alpha + hex.substring(1), 0], ['#' + alpha + hex.substring(1), 0.15],
          ['#00' + hex.substring(1), 1]],
      })
  }

  // ───────── 顶部：位置、状态大字、小画面、两颗按钮 ─────────
  @Builder
  Hero(): void {
    Column() {
      Row() {
        Row({ space: 6 }) {
          Image($r('app.media.ic_home')).width(18).height(18).supportSvg2(true)
            .colorFilter(careIconTint('#FFFFFF'))
          Text('爸妈家 · 客厅').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#FFFFFF')
        }
        Blank()
        Row({ space: 6 }) {
          Circle().width(7).height(7).fill('#FFFFFF')
            .opacity(this.mqttManager.deviceOnline ? 1 : 0.5)
          Text(this.mqttManager.deviceOnline ? '设备在线' : '设备离线').fontSize(13).fontColor('#FFFFFF')
        }.padding({ left: 10, right: 12, top: 6, bottom: 6 }).borderRadius(99).backgroundColor(GLASS)
        .border({ width: 1, color: GLASS_EDGE })
      }.width('100%').margin({ top: 6 })

      Row() {
        Column() {
          Text(this.palette().word)
            .fontSize(this.palette().word.length > 2 ? 64 : 96).fontWeight(FontWeight.Bold)
            .fontColor('#FFFFFF').lineHeight(this.palette().word.length > 2 ? 70 : 100)
            .textShadow({ radius: 40, color: '#40000000', offsetY: 18 })
            .maxLines(1)
          Text(this.heroLines()).fontSize(15).lineHeight(22).fontColor(ON2)
            .margin({ top: 12 }).constraintSize({ minHeight: 45 })
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)

        // 小画面：点开全屏（样张 .live）
        Stack({ alignContent: Alignment.TopStart }) {
          Stack() {
            if (!this.cameraFullscreenActive) {
              CameraStreamView({ placeholderSurface: this.palette().backdrop })
            } else {
              Column().width('100%').height('100%').backgroundColor('#06110D')
            }
          }.width('100%').height('100%').borderRadius(15).clip(true)
          Row({ space: 5 }) {
            Circle().width(6).height(6).fill('#FF6B57')
            Text('实时').fontSize(11).fontColor('#FFFFFF')
          }.padding({ left: 8, right: 10, top: 4, bottom: 4 }).borderRadius(99)
          .backgroundColor('#D110231C').margin({ left: 6, top: 6 })
          // 右下角全屏标记：提示小画面可点开
          Image($r('app.media.ic_home_expand')).width(24).height(24).supportSvg2(true)
            .padding(5).borderRadius(99).backgroundColor('#D110231C')
            .position({ right: 6, bottom: 6 })
        }
        .width(132).height(100).padding(5).borderRadius(20).backgroundColor(GLASS)
        .border({ width: 1, color: GLASS_EDGE })
        .shadow({ radius: 30, offsetY: 16, color: '#59000000' })
        .scale({ x: this.pressScale('live', 0.94), y: this.pressScale('live', 0.94) })
        .animation({ curve: curves.springMotion(0.4, 0.7) })
        .onTouch((event: TouchEvent): void => { this.trackPress('live', event); })
        .onClick((): void => { softTap(); this.openCamera(); })
        .accessibilityText('实时画面，点击全屏查看')
      }.width('100%').alignItems(VerticalAlign.Bottom).margin({ top: 20 })

      Row({ space: 10 }) {
        Button({ type: ButtonType.Capsule }) {
          Row({ space: 8 }) {
            Image(this.isTalking ? $r('app.media.ic_call_end') : $r('app.media.ic_phone'))
              .width(20).height(20).supportSvg2(true)
              .colorFilter(careIconTint(this.isTalking ? '#FFFFFF' : this.palette().solid))
            Text(this.callBusy ? (this.isTalking ? '结束中' : '连接中') : this.isTalking ? '挂断' : '通话')
              .fontSize(17).fontWeight(FontWeight.Medium)
              .fontColor(this.isTalking ? '#FFFFFF' : this.palette().solid)
          }
        }
        .width('100%').height(54).stateEffect(false)
        .backgroundColor(this.isTalking ? '#C7361F' : '#FFFFFF')
        .shadow({ radius: 26, offsetY: 14, color: '#80000000' })
        .enabled(!this.callBusy)
        .scale({ x: this.pressScale('call', 0.93), y: this.pressScale('call', 0.93) })
        .animation({ curve: curves.springMotion(0.4, 0.7) })
        .onTouch((event: TouchEvent): void => { this.trackPress('call', event); })
        .onClick((): void => { softTap(); this.toggleCall(); })
        .accessibilityText(this.isTalking ? '挂断通话' : '和老人语音通话')
      }.width('100%').margin({ top: 20 })
    }.width('100%').padding({ left: 20, right: 20, top: 8 })
  }

  /** 最近 7 个整点加“现在”，与样张 .hours 一致 */
  private hourSlots(): number[] {
    const now = new Date();
    now.setMinutes(0, 0, 0);
    const slots: number[] = [];
    for (let i = 7; i >= 0; i--) slots.push(now.getTime() - i * 3600000);
    return slots;
  }

  /** 该小时内最严重的事件：跌倒 > 陌生人 > 久坐 > 无 */
  private hourMark(start: number): string {
    const inHour = this.homeEvents.filter((event: HealthEvent): boolean =>
      event.eventTime >= start && event.eventTime < start + 3600000);
    if (inHour.some((event: HealthEvent): boolean => event.eventType === 'fall')) return 'fall';
    if (inHour.some((event: HealthEvent): boolean => event.eventType === 'stranger')) return 'stranger';
    if (inHour.some((event: HealthEvent): boolean => event.eventType === 'sedentary')) return 'sedentary';
    return 'ok';
  }

  /** “现在”格显示当前状态 */
  private nowMark(): string {
    if (this.mqttManager.isFallDetected) return 'fall';
    if (this.mqttManager.isSedentaryDetected) return 'sedentary';
    return 'ok';
  }

  @Builder
  Mark(kind: string): void {
    if (kind === 'ok') {
      Stack() { Circle().width(8).height(8).fill('#99FFFFFF') }.width(28).height(28)
    } else {
      Stack() {
        Image(kind === 'fall' ? $r('app.media.ic_alert_red')
          : kind === 'stranger' ? $r('app.media.ic_home_visitor') : $r('app.media.ic_home_sitting'))
          .width(16).height(16).supportSvg2(true)
          .colorFilter(careIconTint(kind === 'fall' ? '#C7361F' : kind === 'stranger' ? '#1B2E5E' : '#3A2600'))
      }.width(28).height(28).borderRadius(14)
      .backgroundColor(kind === 'fall' ? '#FFFFFF' : kind === 'stranger' ? '#C9D6FF' : '#FFD27A')
    }
  }

  @Builder
  Hour(start: number, isNow: boolean): void {
    Column({ space: 8 }) {
      Text(isNow ? '现在' : `${new Date(start).getHours()}`.padStart(2, '0'))
        .fontSize(12).fontColor(isNow ? '#FFFFFF' : ON2)
        .fontWeight(isNow ? FontWeight.Bold : FontWeight.Normal)
      this.Mark(isNow ? this.nowMark() : this.dataReady() ? this.hourMark(start) : 'ok')
    }
    .layoutWeight(1).padding({ top: 8, bottom: 8 }).borderRadius(14)
    .backgroundColor(isNow ? '#29FFFFFF' : Color.Transparent)
    .border(isNow ? { width: { top: 1 }, color: '#66FFFFFF' } : { width: 0 })
  }

  @Builder
  LegendItem(label: string, dot: string, ring: boolean): void {
    Row({ space: 5 }) {
      Circle().width(8).height(8).fill(dot).stroke(ring ? '#C7361F' : Color.Transparent).strokeWidth(ring ? 2 : 0)
      Text(label).fontSize(12).fontColor(ON2)
    }
  }

  // ───────── 今天（样张 今天 卡：逐小时条 + 图例） ─────────
  @Builder
  TodayCard(): void {
    Column() {
      Row() {
        Text('今天').fontSize(17).fontWeight(FontWeight.Bold).fontColor('#FFFFFF')
        Blank()
        Text(this.todaySummary()).fontSize(13).fontColor(ON2)
      }.width('100%')
      Row() {
        ForEach(this.hourSlots(), (start: number, index: number) => {
          this.Hour(start, index === 7)
        }, (start: number, index: number): string => `${start}-${index}-${this.homeEvents.length}-${this.nowMark()}`)
      }.width('100%').margin({ top: 10 })
      Row({ space: 14 }) {
        this.LegendItem('无事件', '#99FFFFFF', false)
        this.LegendItem('久坐', '#FFD27A', false)
        this.LegendItem('陌生人', '#C9D6FF', false)
        this.LegendItem('跌倒', '#FFFFFF', true)
      }.width('100%').padding({ left: 4, right: 4, top: 10 })
    }
    .width('100%').padding(16).borderRadius(PANEL_RADIUS).backgroundColor(GLASS)
    .border({ width: 1, color: GLASS_EDGE })
    .shadow({ radius: 40, offsetY: 22, color: '#4D000000' })
    .onClick((): void => { if (this.homeLoadFailed) this.loadHomeEvents(); else this.openHistory(); })
  }

  @Builder
  EventRow(event: HealthEvent, first: boolean): void {
    Row({ space: 12 }) {
      Stack() {
        Image(this.eventIcon(event)).width(26).height(26).supportSvg2(true)
          .colorFilter(careIconTint(this.eventInk(event)))
      }.width(72).height(54).borderRadius(14).backgroundColor(this.eventThumb(event))
      .border({ width: 1, color: '#59FFFFFF' })
      Column({ space: 3 }) {
        Text(this.eventTitle(event)).fontSize(16).fontWeight(FontWeight.Medium).fontColor('#FFFFFF')
        Text(this.eventLine(event)).fontSize(13).fontColor(ON2).maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
      }.layoutWeight(1).alignItems(HorizontalAlign.Start)
      // 样张四种标签：跌倒未处理=待处理，其他未处理=待查看，久坐已处理=已查看，其他已处理=已处理
      if (event.isHandled === 1) {
        Text(event.eventType === 'sedentary' ? '已查看' : '已处理').fontSize(12).fontWeight(FontWeight.Medium)
          .fontColor('#FFFFFF')
          .padding({ left: 10, right: 10, top: 5, bottom: 5 }).borderRadius(99)
          .border({ width: 1, color: '#73FFFFFF' })
      } else {
        Text(event.eventType === 'fall' ? '待处理' : '待查看').fontSize(12).fontWeight(FontWeight.Medium)
          .fontColor(event.eventType === 'fall' ? '#9E2714' : '#3A2600')
          .padding({ left: 10, right: 10, top: 5, bottom: 5 }).borderRadius(99)
          .backgroundColor(event.eventType === 'fall' ? '#FFFFFF' : '#FFD27A')
      }
    }
    .width('100%').padding({ top: 12, bottom: 12 })
    .border({ width: { top: first ? 0 : 1 }, color: LINE })
    .onClick((): void => { this.showEventDetails(event); })
    .accessibilityText(`${this.eventTitle(event)}，${this.eventWhen(event)}，查看详情`)
  }

  @Builder
  EventsCard(): void {
    Column() {
      Row() {
        Text('最新事件').fontSize(17).fontWeight(FontWeight.Bold).fontColor('#FFFFFF')
        Blank()
        Text('查看全部').fontSize(13).fontColor(ON2).padding({ top: 8, bottom: 8, left: 8 })
          .onClick((): void => { this.openHistory(); })
      }.width('100%')
      if (this.homeLoading) {
        Row({ space: 10 }) {
          LoadingProgress().width(22).height(22).color('#FFFFFF')
          Text('正在加载家中事件…').fontSize(13).fontColor(ON2)
        }.width('100%').justifyContent(FlexAlign.Center).padding({ top: 16, bottom: 16 })
      } else if (this.homeLoadFailed) {
        Button('记录加载失败，点击重试').height(48).width('100%').margin({ top: 8 })
          .fontSize(13).fontColor('#FFFFFF').backgroundColor(GLASS)
          .onClick((): void => { this.loadHomeEvents(); })
      } else if (this.homeEvents.length === 0) {
        Column({ space: 5 }) {
          Text(UserManager.getInstance().isLoggedIn() ? '暂无告警记录' : '登录后查看告警记录')
            .fontSize(15).fontWeight(FontWeight.Medium).fontColor('#FFFFFF')
          Text('收到跌倒、久坐或陌生人事件后，会在这里展示').fontSize(13).fontColor(ON2)
        }.width('100%').alignItems(HorizontalAlign.Start).padding({ top: 12, bottom: 4 })
      } else {
        ForEach(this.homeEvents.slice(0, 3), (event: HealthEvent, index: number) => {
          this.EventRow(event, index === 0)
        }, (event: HealthEvent): string => event.id !== undefined ? event.id.toString() : event.eventType + event.eventTime.toString())
      }
    }
    .width('100%').padding({ left: 16, right: 16, top: 14, bottom: 4 }).borderRadius(PANEL_RADIUS)
    .backgroundColor(GLASS).border({ width: 1, color: GLASS_EDGE })
    .shadow({ radius: 40, offsetY: 22, color: '#4D000000' })
  }

  // ───────── 近 7 天（样张 .week） ─────────
  private dayStart(daysAgo: number): number {
    return this.todayStart() - daysAgo * 86400000;
  }

  private dayCount(daysAgo: number, type: string): number {
    const start = this.dayStart(daysAgo);
    return this.homeEvents.filter((event: HealthEvent): boolean => event.eventType === type
      && event.eventTime >= start && event.eventTime < start + 86400000).length;
  }

  private dayLabel(daysAgo: number): string {
    if (daysAgo === 0) return '今天';
    if (daysAgo === 1) return '昨天';
    return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(this.dayStart(daysAgo)).getDay()];
  }

  @Builder
  WeekCell(count: number, fall: boolean): void {
    Text(this.dataReady() ? `${count}` : '—').fontSize(14).width(56).height(38).textAlign(TextAlign.Center)
      .fontWeight(fall && count > 0 ? FontWeight.Bold : FontWeight.Normal)
      .fontColor(fall && count > 0 ? '#9E2714' : count === 0 ? '#B8FFFFFF' : '#FFFFFF')
      .backgroundColor(fall && count > 0 ? '#FFFFFF' : Color.Transparent).borderRadius(10)
  }

  @Builder
  WeekCard(): void {
    Column() {
      Row() {
        Text('近 7 天').fontSize(17).fontWeight(FontWeight.Bold).fontColor('#FFFFFF')
        Blank()
        Text(`${this.eventDate(this.dayStart(6))} — ${this.eventDate(this.dayStart(0))}`).fontSize(13).fontColor(ON2)
      }.width('100%')
      Row() {
        Blank().layoutWeight(1)
        Text('跌倒').fontSize(12).fontColor(ON2).width(56).textAlign(TextAlign.Center)
        Text('久坐').fontSize(12).fontColor(ON2).width(56).textAlign(TextAlign.Center)
        Text('陌生人').fontSize(12).fontColor(ON2).width(56).textAlign(TextAlign.Center)
      }.width('100%').margin({ top: 8 }).padding({ top: 4, bottom: 4 })
      ForEach([0, 1, 2, 3, 4, 5, 6], (daysAgo: number) => {
        Row() {
          Text(this.dayLabel(daysAgo)).fontSize(14).fontColor('#FFFFFF').layoutWeight(1)
          this.WeekCell(this.dayCount(daysAgo, 'fall'), true)
          this.WeekCell(this.dayCount(daysAgo, 'sedentary'), false)
          this.WeekCell(this.dayCount(daysAgo, 'stranger'), false)
        }.width('100%').border({ width: { top: 1 }, color: LINE })
      }, (daysAgo: number): string => `${daysAgo}-${this.homeEvents.length}-${this.dataReady()}`)
    }
    .width('100%').padding({ left: 16, right: 16, top: 16, bottom: 8 }).borderRadius(PANEL_RADIUS)
    .backgroundColor(GLASS).border({ width: 1, color: GLASS_EDGE })
    .shadow({ radius: 40, offsetY: 22, color: '#4D000000' })
    .onClick((): void => { this.openHistory(); })
  }

  build() {
    Stack() {
      this.Ambient()
      Scroll() {
        Column({ space: 14 }) {
          this.Hero()
          Column({ space: 14 }) {
            this.TodayCard()
            this.EventsCard()
            this.WeekCard()
          }.width('100%').padding({ left: 16, right: 16 }).margin({ top: 10 })
          Blank().height(24 + this.bottomInset)
        }.width('100%').constraintSize({ maxWidth: 640 })
      }.width('100%').height('100%').scrollBar(BarState.Off).align(Alignment.Top)
      .onDidScroll((_x: number, y: number, state: ScrollState): void => { this.onTabScroll(y, state); })
    }.width('100%').height('100%')
  }
}
