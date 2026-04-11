import { mainPage } from "./mainpage";
import { person } from "./person";
import { record } from "./record";
import { AiChat } from "./AiChat";
import { ThemeManager, ThemeColors } from "../common/ThemeManager";

@Builder
export function LayoutBuilder(): void {
  Layout();
}
@Component
export struct Layout {
  @State currentIndex: number = 0;
  @State themeManager: ThemeManager = ThemeManager.getInstance();

  private controller: TabsController = new TabsController();
  pathStack: NavPathStack = new NavPathStack();

  @Builder
  tabBuilder(index: number): void {
    Column() {
      Image(this.getTabIconResource(index))
        .width(26).height(26)
        .objectFit(ImageFit.Contain)
        .scale({ x: this.currentIndex === index ? 1.15 : 1.0,
                 y: this.currentIndex === index ? 1.15 : 1.0 })
        .opacity(this.currentIndex === index ? 1.0 : 0.6)
        .animation({ duration: 220, curve: Curve.EaseOut })
      Text(this.getTabText(index))
        .fontSize(10)
        .margin({ top: 4 })
        .fontColor(this.currentIndex === index ? "#2563eb" : (this.themeManager.isDarkMode ? "#64748b" : "#94a3b8"))
        .fontWeight(this.currentIndex === index ? FontWeight.Bold : FontWeight.Normal)
        .opacity(this.currentIndex === index ? 1.0 : 0.7)
        .animation({ duration: 220, curve: Curve.EaseOut })
      Circle({ width: 4, height: 4 }).fill("#2563eb")
        .margin({ top: 3 })
        .scale({ x: this.currentIndex === index ? 1.0 : 0.0,
                 y: this.currentIndex === index ? 1.0 : 0.0 })
        .opacity(this.currentIndex === index ? 1.0 : 0.0)
        .animation({ duration: 250, curve: Curve.FastOutSlowIn })
    }
    .justifyContent(FlexAlign.Center)
    .alignItems(HorizontalAlign.Center)
    .width("100%").height("100%");
  }

  private getTabIconResource(index: number): Resource {
    const active = this.currentIndex === index;
    switch (index) {
      case 0: return active ? $r("app.media.tab_home_active")   : $r("app.media.tab_home_inactive");
      case 1: return active ? $r("app.media.tab_record_active") : $r("app.media.tab_record_inactive");
      case 2: return active ? $r("app.media.tab_ai_active")     : $r("app.media.tab_ai_inactive");
      case 3: return active ? $r("app.media.tab_person_active") : $r("app.media.tab_person_inactive");
      default: return $r("app.media.tab_home_inactive");
    }
  }

  private getTabText(index: number): string {
    switch (index) {
      case 0: return "主页";
      case 1: return "记录";
      case 2: return "AI助手";
      case 3: return "个人";
      default: return "主页";
    }
  }

  build() {
    NavDestination() {
      Tabs({
        barPosition: BarPosition.End,
        controller: this.controller,
        index: this.currentIndex,
      }) {
        // Tab 0: 主页
        TabContent() {
          mainPage()
        }.tabBar(this.tabBuilder(0))

        // Tab 1: 记录
        TabContent() {
          record()
        }.tabBar(this.tabBuilder(1))

        // Tab 2: AI 助手（文心守护）
        TabContent() {
          AiChat()
        }.tabBar(this.tabBuilder(2))

        // Tab 3: 个人
        TabContent() {
          person({ pathStack: this.pathStack })
        }.tabBar(this.tabBuilder(3))
      }
      .scrollable(true)
      .barMode(BarMode.Fixed)
      .onChange((index: number): void => {
        this.currentIndex = index;
      })
      .barBackgroundColor(this.themeManager.colors.cardBackgroundColor)
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
      .animationDuration(300)
    }
    .hideTitleBar(true)
    .onReady((context: NavDestinationContext): void => {
      this.pathStack = context.pathStack;
    });
  }
}
