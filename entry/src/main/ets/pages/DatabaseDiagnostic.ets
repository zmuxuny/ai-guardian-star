/**
 * DatabaseDiagnostic.ets — 数据库诊断工具
 * 用于查看 GuardianStar.db 中的所有数据，帮助调试
 *
 * 访问方式：在 DevEco Studio 中通过 NavDestination 跳转
 * 或临时在 Index.ets 中添加跳转按钮
 */
import { DatabaseHelper, HealthEvent, UserInfo, VideoRecord } from "../database/DatabaseHelper";
import { ThemeManager } from "../common/ThemeManager";
import { UserManager } from "../common/UserManager";
import { promptAction } from "@kit.ArkUI";
import { relationalStore } from "@kit.ArkData";
@Builder
export function DatabaseDiagnosticBuilder(): void {
  DatabaseDiagnostic();
}

@Component
struct DatabaseDiagnostic {
  pathStack: NavPathStack = new NavPathStack();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @StorageProp("topSafeHeight") topSafeHeight: number = 48;

  @State currentUser: string = "";
  @State allEvents: HealthEvent[] = [];
  @State userEvents: HealthEvent[] = [];
  @State allUsers: UserInfo[] = [];
  @State allVideos: VideoRecord[] = [];
  @State isLoading: boolean = true;
  @State logMessages: string[] = [];

  aboutToAppear(): void {
    this.currentUser = UserManager.getInstance().getCurrentUsername();
    this.runDiagnostics();
  }

  private runDiagnostics(): void {
    this.isLoading = true;
    this.logMessages = [];
    const db = DatabaseHelper.getInstance();
    const now = new Date().toLocaleString("zh-CN");
    this.addLog(`=== 数据库诊断开始 ${now} ===`);

    // 1. 查询所有健康事件（不过滤）
    this.addLog("查询所有健康事件...");
    db.queryAllHealthEventsForDebug()
      .then((events: HealthEvent[]) => {
        this.allEvents = events;
        this.addLog(`✓ 所有健康事件：${events.length} 条`);
        events.forEach((e: HealthEvent) => {
          this.addLog(`  - [${e.eventType}] ${e.dateStr} ${e.timeStr} user=${e.username}`);
        });
      })
      .catch((err: Error) => this.addLog(`✗ 查询失败：${err.message}`));

    // 2. 查询当前用户的事件
    this.addLog(`查询用户 "${this.currentUser}" 的事件...`);
    db.queryHealthEvents(undefined, this.currentUser)
      .then((events: HealthEvent[]) => {
        this.userEvents = events;
        this.addLog(`✓ 用户事件：${events.length} 条`);
      })
      .catch((err: Error) => this.addLog(`✗ 查询失败：${err.message}`));

    // 3. 查询所有用户
    this.addLog("查询所有用户...");
    this.queryAllUsers()
      .then((users: UserInfo[]) => {
        this.allUsers = users;
        this.addLog(`✓ 用户总数：${users.length} 人`);
        users.forEach((u: UserInfo) => {
          this.addLog(`  - ${u.username} (phone: ${u.phone ?? "-"})`);
        });
      })
      .catch((err: Error) => this.addLog(`✗ 查询失败：${err.message}`));

    // 4. 查询所有视频记录
    this.addLog("查询所有视频记录...");
    db.queryVideoRecords(999)
      .then((videos: VideoRecord[]) => {
        this.allVideos = videos;
        this.addLog(`✓ 视频记录：${videos.length} 条`);
        this.isLoading = false;
        this.addLog(`=== 诊断完成 ===`);
      })
      .catch((err: Error) => {
        this.addLog(`✗ 查询失败：${err.message}`);
        this.isLoading = false;
      });
  }

  private addLog(msg: string): void {
    this.logMessages.push(msg);
  }

  /** 查询所有用户（DatabaseHelper 未提供此方法，临时实现） */
  private async queryAllUsers(): Promise<UserInfo[]> {
    const db = DatabaseHelper.getInstance();
    const predicates = new relationalStore.RdbPredicates("t_user");
    let resultSet: relationalStore.ResultSet | undefined = undefined;
    try {
      const store = db.getRdbStore();
      resultSet = await store.query(predicates, [
        "id",
        "username",
        "phone",
        "password_hash",
        "avatar_path",
        "email",
        "address",
        "bind_elder_id",
        "create_time",
      ]);
      const list: UserInfo[] = [];
      while (resultSet.goToNextRow()) {
        list.push({
          id: resultSet.getLong(resultSet.getColumnIndex("id")),
          username: resultSet.getString(resultSet.getColumnIndex("username")),
          phone: resultSet.getString(resultSet.getColumnIndex("phone")),
          passwordHash: resultSet.getString(resultSet.getColumnIndex("password_hash")),
          avatarPath: resultSet.getString(resultSet.getColumnIndex("avatar_path")),
          email: resultSet.getString(resultSet.getColumnIndex("email")),
          address: resultSet.getString(resultSet.getColumnIndex("address")),
          bindElderId: resultSet.getString(resultSet.getColumnIndex("bind_elder_id")),
          createTime: resultSet.getLong(resultSet.getColumnIndex("create_time")),
        });
      }
      return list;
    } catch (err) {
      const error = err as Error;
      throw new Error(error.message);
    } finally {
      if (resultSet !== undefined) {
        resultSet.close();
      }
    }
  }

  /** 清除所有数据（危险操作） */
  private clearAllData(): void {
    promptAction
      .showDialog({
        title: "⚠️ 危险操作",
        message: "确定要清除数据库中的所有健康事件记录吗？\n此操作不可恢复！",
        buttons: [
          { text: "取消", color: "#64748b" },
          { text: "确定清除", color: "#ef4444" },
        ],
      })
      .then((result) => {
        if (result.index === 1) {
          const db = DatabaseHelper.getInstance();
          db.clearAllHealthEvents()
            .then(() => {
              promptAction.showToast({ message: "已清除所有健康事件", duration: 2000 });
              this.runDiagnostics();
            })
            .catch((err: Error) => {
              promptAction.showToast({ message: `清除失败：${err.message}`, duration: 3000 });
            });
        }
      });
  }

  @Builder
  StatCard(value: string, label: string, color: string): void {
    Column() {
      Text(value)
        .fontSize(28)
        .fontWeight(FontWeight.Bold)
        .fontColor(color)
      Text(label)
        .fontSize(12)
        .fontColor("#64748b")
        .margin({ top: 4 })
    }
    .layoutWeight(1)
    .padding({ top: 16, bottom: 16 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .borderRadius(12)
    .shadow({ radius: 6, color: "#0A000000", offsetY: 4 });
  }

  @Builder
  LogCard(): void {
    Column() {
      Row() {
        Text("数据库日志")
          .fontSize(16)
          .fontWeight(FontWeight.Bold)
          .fontColor(this.themeManager.colors.primaryTextColor)
        Blank()
        Button("清除所有数据")
          .fontSize(12)
          .backgroundColor("#fee2e2")
          .fontColor("#ef4444")
          .padding({ left: 12, right: 12, top: 4, bottom: 4 })
          .borderRadius(8)
          .onClick(() => {
            this.clearAllData();
          })
      }
      .width("100%")
      .margin({ bottom: 12 })
      Divider()
        .color("#e2e8f0")
        .margin({ bottom: 12 })

      // 日志列表
      List() {
        ForEach(this.logMessages, (msg: string) => {
          ListItem() {
            Text(msg)
              .fontSize(12)
              .fontColor(
                msg.startsWith("✗")
                  ? "#ef4444"
                  : msg.startsWith("✓")
                    ? "#10b981"
                    : msg.startsWith("===")
                      ? "#3b82f6"
                      : "#475569",
              )
              .fontFamily("monospace")
          }
          .padding({ top: 8, bottom: 8 });
        })
      }
      .width("100%")
      .scrollBar(BarState.Auto)
    }
    .width("100%")
    .padding(16)
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .borderRadius(12)
    .shadow({ radius: 6, color: "#0A000000", offsetY: 4 });
  }

  build() {
    NavDestination() {
      Column() {
        // 标题栏
        Row() {
          Image($r("app.media.ic_chevron_right"))
            .width(36)
            .height(36)
            .objectFit(ImageFit.Contain)
            .padding(8)
            .backgroundColor("#33FFFFFF")
            .borderRadius(100)
            .rotate({ angle: 180 })
            .onClick(() => {
              this.pathStack.pop();
            })
          Text("数据库诊断工具")
            .fontSize(22)
            .fontWeight(FontWeight.Bold)
            .fontColor("#ffffff")
            .margin({ left: "3%" })
          Blank()
          Button("刷新")
            .fontSize(14)
            .fontColor("#ffffff")
            .backgroundColor("#33FFFFFF")
            .padding({ left: 16, right: 16, top: 6, bottom: 6 })
            .borderRadius(20)
            .onClick(() => {
              this.runDiagnostics();
            })
        }
        .width("100%")
        .padding({ left: "4%", right: "4%", top: this.topSafeHeight + 12, bottom: 24 })
        .linearGradient({
          direction: GradientDirection.Bottom,
          colors: [
            ["#1e40af", 0.0],
            ["#3b82f6", 0.5],
            ["#60a5fa", 1.0],
          ],
        })
        .borderRadius({ bottomLeft: "6%", bottomRight: "6%" })

        // 内容区
        Scroll() {
          Column() {
            // 当前用户信息
            Column() {
              Text("当前登录用户")
                .fontSize(14)
                .fontColor("#64748b")
              Text(this.currentUser)
                .fontSize(20)
                .fontWeight(FontWeight.Bold)
                .fontColor("#1e40af")
                .margin({ top: 8 })
            }
            .width("92%")
            .padding({ top: 16, bottom: 16 })
            .backgroundColor(this.themeManager.colors.cardBackgroundColor)
            .borderRadius(12)
            .shadow({ radius: 6, color: "#0A000000", offsetY: 4 })
            .margin({ top: 20 })

            // 统计卡片
            Row() {
              Column() {
                this.StatCard(`${this.allEvents.length}`, "总事件数", "#ef4444")
              }
              Column() {
                this.StatCard(`${this.userEvents.length}`, "当前用户事件", "#3b82f6")
              }
            }
            .width("92%")
            .margin({ top: 16 })

            // 详细日志
            Column() {
              this.LogCard()
            }
            .width("92%")
            .margin({ top: 16, bottom: 32 })

            if (this.isLoading) {
              Column() {
                LoadingProgress()
                  .width(48)
                  .height(48)
              }
              .width("100%")
              .margin({ top: 40 });
            }
          }
          .width("100%")
          .alignItems(HorizontalAlign.Center)
        }
        .width("100%")
        .height("100%")
        .backgroundColor(this.themeManager.colors.backgroundColor)
        .scrollBar(BarState.Off)
      }
      .width("100%")
      .height("100%")
    }
    .hideTitleBar(true)
    .onReady((ctx: NavDestinationContext) => {
      this.pathStack = ctx.pathStack;
    });
  }
}
