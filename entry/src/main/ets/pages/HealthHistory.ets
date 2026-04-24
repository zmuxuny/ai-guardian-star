/**
 * HealthHistory.ets — 健康历史记录页
 * 从 ArkDB 加载保留期内的全部摔倒/久坐事件，支持导出为文本。
 * 入口：person.ets → 历史记录按钮
 */
import { DatabaseHelper, HealthEvent } from "../database/DatabaseHelper";
import { ThemeManager } from "../common/ThemeManager";
import { UserManager } from "../common/UserManager";
import { FallRecord, SedentaryRecord } from "./MqttManager";
import { promptAction } from "@kit.ArkUI";
@Builder
export function HealthHistoryBuilder(): void {
  HealthHistory();
}

@Component
struct HealthHistory {
  pathStack: NavPathStack = new NavPathStack();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State currentTab: number = 0;
  @State fallRecords: FallRecord[] = [];
  @State sedentaryRecords: SedentaryRecord[] = [];
  @State isLoading: boolean = true;
  @StorageProp("topSafeHeight") topSafeHeight: number = 48;

  aboutToAppear(): void {
    this.loadHistory();
  }

  onPageShow(): void {
    // 每次页面显示时重新拉取，防止进入时数据未及时同步
    this.loadHistory();
  }

  /** 从数据库加载历史记录 */
  private loadHistory(): void {
    this.isLoading = true;
    const db = DatabaseHelper.getInstance();
    const currentUser = UserManager.getInstance().getCurrentUsername();

    console.log(`[HealthHistory]: 开始加载数据 user=${currentUser}`);

    // 加载摔倒记录
    db.queryHealthEvents("fall", currentUser)
      .then((events: HealthEvent[]) => {
        this.fallRecords = events.map(
          (e: HealthEvent): FallRecord => ({
            time: e.timeStr,
            date: e.dateStr,
            timestamp: e.eventTime,
          }),
        );
        console.log(`[HealthHistory]: 摔倒记录加载完成 count=${events.length}`);
      })
      .catch((err: Error) => {
        this.fallRecords = [];
        console.error(`[HealthHistory]: 加载摔倒记录失败 ${err.message}`);
      });

    // 加载久坐记录
    db.queryHealthEvents("sedentary", currentUser)
      .then((events: HealthEvent[]) => {
        this.sedentaryRecords = events.map(
          (e: HealthEvent): SedentaryRecord => ({
            time: e.timeStr,
            date: e.dateStr,
            timestamp: e.eventTime,
          }),
        );
        console.log(`[HealthHistory]: 久坐记录加载完成 count=${events.length}`);
        this.isLoading = false;
      })
      .catch((err: Error) => {
        this.sedentaryRecords = [];
        this.isLoading = false;
        console.error(`[HealthHistory]: 加载久坐记录失败 ${err.message}`);
      });
  }

  @Builder
  GradientHeader(): void {
    Stack({ alignContent: Alignment.Top }) {
      // 层1：渐变背景（固定高度 = 标题栏区，通过 expandSafeArea 延伸到状态栏，同 Profile 写法）
      Column()
        .width("100%")
        .height(this.topSafeHeight + 100)
        .linearGradient({
          direction: GradientDirection.Bottom,
          colors: [
            ["#1e40af", 0.0],
            ["#3b82f6", 0.5],
            ["#60a5fa", 1.0],
          ],
        })
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
        .borderRadius({ bottomLeft: "6%", bottomRight: "6%" })

      // 层2：标题栏内容区
      Row() {
        Image($r("app.media.ic_chevron_right"))
          .width(36)
          .height(36)
          .objectFit(ImageFit.Contain)
          .padding(8)
          .backgroundColor("#33FFFFFF")
          .borderRadius(100)
          .rotate({ angle: 180 })
          // 向右箭头旋转180°当作返回箭头
          .onClick((): void => {
            this.pathStack.pop();
          })
        Text("历史记录")
          .fontSize(22)
          .fontWeight(FontWeight.Bold)
          .fontColor("#ffffff")
          .margin({ left: "5%" })
        Blank()
        // 导出按钮
        Text("导出")
          .fontSize(15)
          .fontColor("#ffffff")
          .padding({ left: 14, right: 14, top: 6, bottom: 6 })
          .backgroundColor("#33FFFFFF")
          .borderRadius(20)
          .onClick((): void => {
            this.exportRecords();
          })
      }
      .width("100%")
      .padding({ left: "4%", right: "4%", top: this.topSafeHeight})
    }
    .width("100%")
  }

  @Builder
  TabBar(): void {
    Row() {
      Text(`摔倒记录 (${this.fallRecords.length})`)
        .fontSize(15)
        .fontWeight(this.currentTab === 0 ? FontWeight.Bold : FontWeight.Normal)
        .fontColor(this.currentTab === 0 ? "#2563eb" : this.themeManager.colors.secondaryTextColor)
        .layoutWeight(1)
        .textAlign(TextAlign.Center)
        .padding({ bottom: "3%" })
        .border({ width: { bottom: this.currentTab === 0 ? 3 : 0 }, color: "#2563eb" })
        .onClick((): void => {
          this.currentTab = 0;
        })
      Text(`久坐记录 (${this.sedentaryRecords.length})`)
        .fontSize(15)
        .fontWeight(this.currentTab === 1 ? FontWeight.Bold : FontWeight.Normal)
        .fontColor(this.currentTab === 1 ? "#2563eb" : this.themeManager.colors.secondaryTextColor)
        .layoutWeight(1)
        .textAlign(TextAlign.Center)
        .padding({ bottom: "3%" })
        .border({ width: { bottom: this.currentTab === 1 ? 3 : 0 }, color: "#2563eb" })
        .onClick((): void => {
          this.currentTab = 1;
        })
    }
    .width("100%")
    .padding({ left: "8%", right: "8%", top: "4%", bottom: 0 });
  }

  @Builder
  RecordItem(date: string, time: string, isDanger: boolean): void {
    Row() {
      Column()
        .width(4)
        .height(36)
        .borderRadius(2)
        .backgroundColor(isDanger ? "#ef4444" : "#3b82f6")
        .margin({ right: "4%" })
      Column() {
        Text(isDanger ? "⚠️ 疑似跌倒警报" : "🪑 久坐超时提醒")
          .fontSize(15)
          .fontWeight(FontWeight.Medium)
          .fontColor(this.themeManager.colors.primaryTextColor)
        Text(`${date}  ${time}`)
          .fontSize(12)
          .fontColor(this.themeManager.colors.secondaryTextColor)
          .margin({ top: 4 })
      }
      .alignItems(HorizontalAlign.Start)
      .layoutWeight(1)
    }
    .width("100%")
    .padding({ left: "4%", right: "4%", top: 14, bottom: 14 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .borderRadius("3%")
    .margin({ bottom: "2.5%" })
    .shadow({ radius: 6, color: "#0000000A", offsetY: 3 });
  }

  @Builder
  EmptyState(): void {
    Column() {
      Text("📭")
        .fontSize(56)
        .margin({ bottom: 16 })
      Text("暂无历史记录")
        .fontSize(18)
        .fontWeight(FontWeight.Medium)
        .fontColor(this.themeManager.colors.primaryTextColor)
      Text(`当前保留 ${DatabaseHelper.getInstance().getRetentionDays()} 天内的数据`)
        .fontSize(14)
        .fontColor(this.themeManager.colors.secondaryTextColor)
        .margin({ top: 8 })
    }
    .width("100%")
    .margin({ top: "20%" })
    .alignItems(HorizontalAlign.Center);
  }

  /** 导出记录为纯文本（目前实现为弹窗展示，可扩展为写文件） */
  private exportRecords(): void {
    const lines: string[] = [];
    lines.push("=== 守护星健康历史记录 ===");
    lines.push(`导出时间：${new Date().toLocaleString()}`);
    lines.push(`保留天数：${DatabaseHelper.getInstance().getRetentionDays()} 天`);
    lines.push("");
    lines.push(`--- 摔倒记录 (${this.fallRecords.length} 条) ---`);
    this.fallRecords.forEach((r) => lines.push(`  ${r.date}  ${r.time}  跌倒告警`));
    lines.push("");
    lines.push(`--- 久坐记录 (${this.sedentaryRecords.length} 条) ---`);
    this.sedentaryRecords.forEach((r) => lines.push(`  ${r.date}  ${r.time}  久坐提醒`));

    // 弹窗展示（可替换为 fs.writeFile 写到沙箱文件）
    AlertDialog.show({
      title: "历史记录导出",
      message: lines.slice(0, 20).join("\n") + (lines.length > 20 ? "\n..." : ""),
      primaryButton: { value: "关闭", action: () => {} },
      alignment: DialogAlignment.Center,
      gridCount: 8,
    });
  }

  build() {
    NavDestination() {
      Column() {
        this.GradientHeader()
        this.TabBar()

        if (this.isLoading) {
          Column() {
            LoadingProgress()
              .width(48)
              .height(48)
          }
          .width("100%")
          .margin({ top: "25%" });
        } else {
          List({ space: 0 }) {
            if (this.currentTab === 0) {
              if (this.fallRecords.length === 0) {
                ListItem() {
                  this.EmptyState()
                };
              } else {
                ForEach(this.fallRecords, (item: FallRecord) => {
                  ListItem() {
                    this.RecordItem(item.date, item.time, true)
                  };
                });
              }
            } else {
              if (this.sedentaryRecords.length === 0) {
                ListItem() {
                  this.EmptyState()
                };
              } else {
                ForEach(this.sedentaryRecords, (item: SedentaryRecord) => {
                  ListItem() {
                    this.RecordItem(item.date, item.time, false)
                  };
                });
              }
            }
          }
          .layoutWeight(1)
          .width("92%")
          .padding({ top: "3%" })
          .edgeEffect(EdgeEffect.Spring)
          .scrollBar(BarState.Off);
        }
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
