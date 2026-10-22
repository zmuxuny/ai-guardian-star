/**
 * HealthHistory.ets — 健康历史记录页
 * 从 ArkDB 加载保留期内的摔倒/久坐事件，按日期展示并支持筛选和 CSV 导出。
 * 入口：person.ets → 历史记录按钮
 */
import { DatabaseHelper, HealthEvent } from "../database/DatabaseHelper";
import { ThemeManager } from "../common/ThemeManager";
import { UserManager } from "../common/UserManager";
import { GradientHeader, ICON_FRAME_SIZE, PAGE_HORIZONTAL_GUTTER, PAGE_TITLE_SIZE, SURFACE_RADIUS } from '../components/GradientHeader';
import { common } from '@kit.AbilityKit';
import fs from '@ohos.file.fs';
import picker from '@ohos.file.picker';
import { showToast } from '../common/UiFeedback';
import { RecordingBrowser } from '../components/RecordingBrowser';

interface HistoryDateGroup {
  dateKey: string;
  dateLabel: string;
  events: HealthEvent[];
}
@Builder
export function HealthHistoryBuilder(): void {
  HealthHistory();
}

@Component
struct HealthHistory {
  pathStack: NavPathStack = new NavPathStack();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State events: HealthEvent[] = [];
  @State currentTab: number = 0;
  @State isLoading: boolean = true;
  @State isExporting: boolean = false;
  @StorageProp("topSafeHeight") topSafeHeight: number = 48;
  aboutToAppear(): void {
    this.loadHistory();
  }

  onPageShow(): void {
    // 每次页面显示时重新拉取，防止进入时数据未及时同步
    this.loadHistory();
  }

  /** 从数据库加载历史记录 */
  private async loadHistory(): Promise<void> {
    this.isLoading = true;
    try {
      const currentUser = UserManager.getInstance().getCurrentUsername();
      const result = await DatabaseHelper.getInstance().queryHealthEvents(undefined, currentUser);
      this.events = result
        .filter((event: HealthEvent): boolean => event.eventType === 'fall' || event.eventType === 'sedentary')
        .sort((first: HealthEvent, second: HealthEvent): number => second.eventTime - first.eventTime);
    } catch (error) {
      this.events = [];
      console.error(`[HealthHistory]: 历史记录加载失败 ${JSON.stringify(error)}`);
      showToast(this.getUIContext(), { message: '历史记录加载失败，请稍后重试' });
    } finally {
      this.isLoading = false;
    }
  }

  private selectedEvents(): HealthEvent[] {
    if (this.currentTab === 1) {
      return this.events.filter((event: HealthEvent): boolean => event.eventType === 'fall');
    }
    if (this.currentTab === 2) {
      return this.events.filter((event: HealthEvent): boolean => event.eventType === 'sedentary');
    }
    return this.events;
  }

  private dateKey(timestamp: number): string {
    const date = new Date(timestamp);
    const month = `${date.getMonth() + 1}`.padStart(2, '0');
    const day = `${date.getDate()}`.padStart(2, '0');
    return `${date.getFullYear()}-${month}-${day}`;
  }

  private dateLabel(timestamp: number): string {
    const key = this.dateKey(timestamp);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
    const todayKey = this.dateKey(today.getTime());
    const yesterdayKey = this.dateKey(yesterday.getTime());
    const date = new Date(timestamp);
    const formatted = `${date.getFullYear()}年${`${date.getMonth() + 1}`.padStart(2, '0')}月${`${date.getDate()}`.padStart(2, '0')}日`;
    if (key === todayKey) return `今天 · ${formatted}`;
    if (key === yesterdayKey) return `昨天 · ${formatted}`;
    return formatted;
  }

  private formatTime(timestamp: number): string {
    const date = new Date(timestamp);
    const hour = `${date.getHours()}`.padStart(2, '0');
    const minute = `${date.getMinutes()}`.padStart(2, '0');
    const second = `${date.getSeconds()}`.padStart(2, '0');
    return `${hour}:${minute}:${second}`;
  }

  private displayDate(event: HealthEvent): string {
    if (event.dateStr && event.dateStr.trim() !== '') return event.dateStr;
    return this.dateKey(event.eventTime);
  }

  private displayTime(event: HealthEvent): string {
    if (event.timeStr && event.timeStr.trim() !== '') return event.timeStr;
    return this.formatTime(event.eventTime);
  }

  private groupedEvents(): HistoryDateGroup[] {
    const groups: HistoryDateGroup[] = [];
    const sortedEvents = this.selectedEvents()
      .slice()
      .sort((first: HealthEvent, second: HealthEvent): number => second.eventTime - first.eventTime);
    for (const event of sortedEvents) {
      const key = this.dateKey(event.eventTime);
      let group = groups.length > 0 ? groups[groups.length - 1] : undefined;
      if (group === undefined || group.dateKey !== key) {
        group = { dateKey: key, dateLabel: this.dateLabel(event.eventTime), events: [] };
        groups.push(group);
      }
      group.events.push(event);
    }
    return groups;
  }

  private eventTitle(event: HealthEvent): string {
    return event.eventType === 'fall' ? '跌倒告警' : '久坐提醒';
  }

  private severityLabel(severity: number): string {
    if (severity >= 3) return '高风险';
    if (severity === 2) return '中风险';
    return '低风险';
  }

  private showEventDetails(event: HealthEvent): void {
    const handledText = event.isHandled === 1 ? '已处理' : '待处理';
    const remark = event.remark && event.remark.trim() !== '' ? `\n详情：${event.remark}` : '';
    this.getUIContext().showAlertDialog({
      title: this.eventTitle(event),
      message: `${this.displayDate(event)}  ${this.displayTime(event)}\n${this.severityLabel(event.severity)} · ${handledText}${remark}`,
      primaryButton: { value: '关闭', action: (): void => {} },
      alignment: DialogAlignment.Center,
    });
  }

  private csvCell(value: string): string {
    const safeValue = /^[=+\-@]/.test(value.trimStart()) ? `'${value}` : value;
    return `"${safeValue.replace(/"/g, '""')}"`;
  }

  private buildCsv(): string {
    const lines: string[] = [];
    lines.push(['事件类型', '发生日期', '发生时间', '风险等级', '处理状态', '详情'].map((value: string): string => this.csvCell(value)).join(','));
    for (const event of this.events) {
      lines.push([
        this.eventTitle(event),
        this.displayDate(event),
        this.displayTime(event),
        this.severityLabel(event.severity),
        event.isHandled === 1 ? '已处理' : '待处理',
        event.remark ?? '',
      ].map((value: string): string => this.csvCell(value)).join(','));
    }
    return `\uFEFF${lines.join('\r\n')}\r\n`;
  }

  private async exportRecords(): Promise<void> {
    if (this.isExporting) return;
    if (this.events.length === 0) {
      showToast(this.getUIContext(), { message: '暂无历史记录可导出' });
      return;
    }
    this.isExporting = true;
    try {
      const now = new Date();
      const date = `${now.getFullYear()}${`${now.getMonth() + 1}`.padStart(2, '0')}${`${now.getDate()}`.padStart(2, '0')}`;
      const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
      const documentPicker = new picker.DocumentViewPicker(context);
      const uris = await documentPicker.save({
        newFileNames: [`守护星健康记录_${date}.csv`],
        fileSuffixChoices: ['CSV 表格|csv'],
      });
      if (uris.length === 0) return;
      const file = fs.openSync(uris[0], fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
      try {
        fs.writeSync(file.fd, this.buildCsv(), { encoding: 'utf-8' });
      } finally {
        fs.closeSync(file);
      }
      showToast(this.getUIContext(), { message: `已导出 ${this.events.length} 条记录` });
    } catch (error) {
      console.error(`[HealthHistory]: 导出失败 ${JSON.stringify(error)}`);
      showToast(this.getUIContext(), { message: '导出失败，请重新选择保存位置' });
    } finally {
      this.isExporting = false;
    }
  }

  @Builder
  PageHeader(): void {
    GradientHeader({ contentMaxWidth: 640 }) {
      Row() {
        Image($r('app.media.ic_chevron_right'))
          .width(ICON_FRAME_SIZE).height(ICON_FRAME_SIZE).padding(9)
          .objectFit(ImageFit.Contain).backgroundColor('#33FFFFFF')
          .borderRadius(20).rotate({ angle: 180 }).accessibilityText('返回')
          .onClick((): void => { this.pathStack.pop(); })
        Text('历史记录')
          .fontSize(PAGE_TITLE_SIZE).fontWeight(FontWeight.Bold).fontColor('#ffffff')
          .margin({ left: 12 }).layoutWeight(1)
        Text(this.isExporting ? '准备中' : '导出事件 CSV')
          .fontSize(14).fontWeight(FontWeight.Medium).fontColor('#ffffff')
          .padding({ left: 14, right: 14, top: 9, bottom: 9 })
          .backgroundColor('#33FFFFFF').borderRadius(18)
          .opacity(this.isExporting ? 0.65 : 1).enabled(!this.isExporting)
          .onClick((): void => { this.exportRecords(); })
      }
      .width('100%')
      .padding({ left: PAGE_HORIZONTAL_GUTTER, right: PAGE_HORIZONTAL_GUTTER, top: this.topSafeHeight + 8, bottom: 12 })
    }
  }

  @Builder
  TabBar(): void {
    Row() {
      Text(`全部 ${this.events.length}`)
        .fontSize(14)
        .fontWeight(this.currentTab === 0 ? FontWeight.Bold : FontWeight.Medium)
        .fontColor(this.currentTab === 0 ? '#1d4ed8' : this.themeManager.colors.secondaryTextColor)
        .textAlign(TextAlign.Center)
        .layoutWeight(1)
        .height(42)
        .backgroundColor(this.currentTab === 0 ? '#dbeafe' : this.themeManager.colors.cardBackgroundColor)
        .borderRadius(12)
        .margin({ right: 8 })
        .onClick((): void => { this.currentTab = 0; })
      Text(`摔倒 ${this.events.filter((event: HealthEvent): boolean => event.eventType === 'fall').length}`)
        .fontSize(14)
        .fontWeight(this.currentTab === 1 ? FontWeight.Bold : FontWeight.Medium)
        .fontColor(this.currentTab === 1 ? '#1d4ed8' : this.themeManager.colors.secondaryTextColor)
        .textAlign(TextAlign.Center)
        .layoutWeight(1)
        .height(42)
        .backgroundColor(this.currentTab === 1 ? '#dbeafe' : this.themeManager.colors.cardBackgroundColor)
        .borderRadius(12)
        .margin({ right: 8 })
        .onClick((): void => { this.currentTab = 1; })
      Text(`久坐 ${this.events.filter((event: HealthEvent): boolean => event.eventType === 'sedentary').length}`)
        .fontSize(14)
        .fontWeight(this.currentTab === 2 ? FontWeight.Bold : FontWeight.Medium)
        .fontColor(this.currentTab === 2 ? '#1d4ed8' : this.themeManager.colors.secondaryTextColor)
        .textAlign(TextAlign.Center)
        .layoutWeight(1)
        .height(42)
        .backgroundColor(this.currentTab === 2 ? '#dbeafe' : this.themeManager.colors.cardBackgroundColor)
        .borderRadius(12)
        .onClick((): void => { this.currentTab = 2; })
    }
    .width("100%")
    .constraintSize({ maxWidth: 640 })
    .padding({ left: 20, right: 20, top: 14, bottom: 10 });
  }

  @Builder
  DateHeading(group: HistoryDateGroup): void {
    Row() {
      Text(group.dateLabel)
        .fontSize(14)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
      Blank()
      Text(`${group.events.length} 条`)
        .fontSize(12)
        .fontColor(this.themeManager.colors.secondaryTextColor)
    }
    .width('100%')
    .padding({ top: 18, bottom: 10, left: 2, right: 2 });
  }

  @Builder
  EventRow(event: HealthEvent): void {
    Column() {
      Row() {
        Column() {
          Text(event.eventType === 'fall' ? '跌倒' : '久坐')
            .fontSize(12)
            .fontWeight(FontWeight.Bold)
            .fontColor(event.eventType === 'fall' ? '#b91c1c' : '#1d4ed8')
            .padding({ left: 9, right: 9, top: 5, bottom: 5 })
            .backgroundColor(event.eventType === 'fall' ? '#fee2e2' : '#dbeafe')
            .borderRadius(8)
        }
        .alignItems(HorizontalAlign.Start)
        Column() {
          Text(this.eventTitle(event))
            .fontSize(15)
            .fontWeight(FontWeight.Medium)
            .fontColor(this.themeManager.colors.primaryTextColor)
          Text(this.displayTime(event))
            .fontSize(13)
            .fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ top: 4 })
        }
        .alignItems(HorizontalAlign.Start)
        .layoutWeight(1)
        Text(event.isHandled === 1 ? '已处理' : this.severityLabel(event.severity))
          .fontSize(12)
          .fontColor(event.isHandled === 1 ? '#15803d' : '#9a3412')
      }
      Row() {
        Text(event.remark && event.remark.trim() !== '' ? event.remark : '暂无详情')
          .fontSize(13)
          .fontColor(this.themeManager.colors.secondaryTextColor)
          .maxLines(2)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
          .layoutWeight(1)
        Text('查看')
          .fontSize(12)
          .fontColor('#2563eb')
          .margin({ left: 10 })
      }
      .width('100%')
      .margin({ top: 10 })
    }
    .width('100%')
    .padding({ left: 14, right: 14, top: 14, bottom: 14 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .border({ width: 1, color: this.themeManager.colors.borderColor })
    .borderRadius(SURFACE_RADIUS)
    .margin({ bottom: 10 })
    .onClick((): void => { this.showEventDetails(event); });
  }

  @Builder
  EmptyState(): void {
    Column() {
      Text(this.currentTab === 1 ? '暂无摔倒记录' : (this.currentTab === 2 ? '暂无久坐记录' : '暂无历史记录'))
        .fontSize(18)
        .fontWeight(FontWeight.Medium)
        .fontColor(this.themeManager.colors.primaryTextColor)
      Text(`当前保留 ${DatabaseHelper.getInstance().getRetentionDays()} 天内的数据`)
        .fontSize(14)
        .fontColor(this.themeManager.colors.secondaryTextColor)
        .margin({ top: 8 })
    }
    .width("100%")
    .margin({ top: 72 })
    .alignItems(HorizontalAlign.Center);
  }

  build() {
    NavDestination() {
      Column() {
        this.PageHeader()
        RecordingBrowser().layoutWeight(1)
      }
      .width("100%")
      .height("100%")
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .alignItems(HorizontalAlign.Center)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .hideTitleBar(true)
    .onReady((ctx: NavDestinationContext) => {
      this.pathStack = ctx.pathStack;
    });
  }
}
