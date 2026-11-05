import { DatabaseHelper, HealthEvent } from '../database/DatabaseHelper';
import { ThemeManager } from '../common/ThemeManager';
import { UserManager } from '../common/UserManager';
import { isTodayHomeEvent, homeEventTitle, homeEventAccent, homeEventSurface } from '../common/HomeEventRules';
import { GradientHeader } from '../components/GradientHeader';

@Builder
export function TodayEventsBuilder(): void { TodayEvents(); }

@Component
struct TodayEvents {
  private pathStack: NavPathStack = new NavPathStack();
  @State theme: ThemeManager = ThemeManager.getInstance();
  @State events: HealthEvent[] = [];
  @State loading: boolean = true;
  @State failed: boolean = false;
  @State now: number = Date.now();
  private querying: boolean = false;
  private disposed: boolean = false;
  private timer: number = -1;

  aboutToAppear(): void {
    this.disposed = false;
    this.load();
    this.timer = setInterval((): void => { this.load(); }, 5000) as number;
  }

  aboutToDisappear(): void {
    this.disposed = true;
    if (this.timer !== -1) clearInterval(this.timer);
  }

  private async load(): Promise<void> {
    if (this.querying || this.disposed) return;
    const user = UserManager.getInstance();
    const username = user.getCurrentUsername();
    this.now = Date.now();
    this.querying = true;
    try {
      if (!user.isLoggedIn()) { this.events = []; return; }
      const rows = await DatabaseHelper.getInstance().queryHealthEvents(undefined, username);
      if (this.disposed) return;
      this.events = user.isLoggedIn() && user.getCurrentUsername() === username
        ? rows.filter((event: HealthEvent): boolean => isTodayHomeEvent(event.eventType, event.eventTime, this.now))
          .sort((left: HealthEvent, right: HealthEvent): number => right.eventTime - left.eventTime) : [];
      this.failed = false;
    } catch (_) {
      if (!this.disposed) this.failed = true;
    } finally {
      this.querying = false;
      if (!this.disposed) this.loading = false;
    }
  }

  private dateText(): string {
    const date = new Date(this.now);
    return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 · 时间倒序`;
  }

  private timeText(timestamp: number): string {
    const date = new Date(timestamp);
    return [date.getHours(), date.getMinutes(), date.getSeconds()]
      .map((part: number): string => `${part}`.padStart(2, '0')).join(':');
  }

  private details(event: HealthEvent): void {
    this.getUIContext().showAlertDialog({
      title: homeEventTitle(event.eventType),
      message: `${this.timeText(event.eventTime)}\n${event.isHandled === 1 ? '已处理' : '待处理'}${event.remark ? `\n${event.remark}` : ''}`,
      primaryButton: { value: '关闭', action: (): void => {} }
    });
  }

  @Builder
  EventRow(event: HealthEvent): void {
    Button({ type: ButtonType.Normal }) {
      Row({ space: 12 }) {
        Image(event.eventType === 'fall' ? $r('app.media.ic_alert_red')
          : event.eventType === 'stranger' ? $r('app.media.ic_home_visitor') : $r('app.media.ic_home_sitting'))
          .width(42).height(42).padding(8).borderRadius(21)
          .fillColor(homeEventAccent(event.eventType, this.theme.isDarkMode))
          .backgroundColor(homeEventSurface(event.eventType, this.theme.isDarkMode))
        Column({ space: 6 }) {
          Text(homeEventTitle(event.eventType)).fontSize(16).fontWeight(FontWeight.Medium)
            .fontColor(homeEventAccent(event.eventType, this.theme.isDarkMode))
          Text(this.timeText(event.eventTime)).fontSize(13).fontColor(this.theme.colors.secondaryTextColor)
          if (event.remark) {
            Text(event.remark).fontSize(12).fontColor(this.theme.colors.secondaryTextColor)
              .maxLines(2).textOverflow({ overflow: TextOverflow.Ellipsis })
          }
        }.alignItems(HorizontalAlign.Start).layoutWeight(1)
        Text('详情').fontSize(13).fontColor(this.theme.colors.linkTextColor)
        Image($r('app.media.ic_chevron_right')).width(16).height(16)
      }.width('100%')
    }.width('100%').padding(14).borderRadius(16)
      .backgroundColor(this.theme.colors.cardBackgroundColor)
      .onClick((): void => { this.details(event); })
  }

  build() {
    NavDestination() {
      Column() {
        GradientHeader({ useHomeStyle: true, contentMaxWidth: 640 }) {
          Row({ space: 8 }) {
            Button({ type: ButtonType.Normal }) {
              Image($r('app.media.ic_nav_back_dark')).width(20).height(20)
                .fillColor(this.theme.colors.primaryTextColor)
            }.width(44).height(44).borderRadius(22).backgroundColor(Color.Transparent)
              .accessibilityText('返回主页').onClick((): void => { this.pathStack.pop(); })
            Text('当天事件').fontSize(24).fontWeight(FontWeight.Bold)
              .fontColor(this.theme.colors.primaryTextColor).layoutWeight(1)
            Button('刷新').height(44).fontSize(14).fontColor(this.theme.colors.linkTextColor)
              .backgroundColor(Color.Transparent).onClick((): void => { this.load(); })
          }.width('100%').padding({ left: 8, right: 16, top: 8, bottom: 12 })
        }
        Row() {
          Text(this.dateText()).fontSize(13).fontColor(this.theme.colors.secondaryTextColor).layoutWeight(1)
          Text(`${this.events.length} 条`).fontSize(13).fontColor(this.theme.colors.secondaryTextColor)
        }.width('100%').padding({ left: 20, right: 20, top: 12, bottom: 16 })
        if (this.loading) {
          LoadingProgress().width(28).height(28).color('#2563eb').margin({ top: 40 })
          Text('正在读取当天记录…').fontSize(14).fontColor(this.theme.colors.secondaryTextColor)
        } else if (this.failed) {
          Text('当天记录加载失败').fontSize(16).fontColor(this.theme.colors.primaryTextColor).margin({ top: 40 })
          Button('重新加载').height(44).margin({ top: 16 }).onClick((): void => { this.load(); })
        } else if (this.events.length === 0) {
          Image($r('app.media.ic_record')).width(48).height(48).margin({ top: 48, bottom: 16 })
          Text('今天暂无事件').fontSize(18).fontWeight(FontWeight.Medium).fontColor(this.theme.colors.primaryTextColor)
          Text('当天的摔倒、久坐和陌生人记录会显示在这里').fontSize(13)
            .fontColor(this.theme.colors.secondaryTextColor).margin({ top: 8 }).padding(20)
        } else {
          List({ space: 12 }) {
            ForEach(this.events, (event: HealthEvent) => {
              ListItem() { this.EventRow(event) }
            }, (event: HealthEvent): string => `${event.id}:${event.eventTime}:${event.isHandled}:${event.remark}`)
          }.width('100%').layoutWeight(1).padding({ left: 16, right: 16, bottom: 20 }).scrollBar(BarState.Off)
        }
      }.width('100%').height('100%')
        .backgroundColor(this.theme.isDarkMode ? '#0f172a' : '#f0f4ff')
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }.hideTitleBar(true).backgroundColor(this.theme.isDarkMode ? '#0f172a' : '#f0f4ff')
      .onReady((context: NavDestinationContext): void => { this.pathStack = context.pathStack; })
  }
}
