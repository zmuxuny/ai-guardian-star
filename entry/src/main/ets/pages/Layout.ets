import { mainPage } from "./mainpage";
import { person } from "./person";
import { record } from "./record";
import { AiChat } from "./AiChat";
import { ThemeManager } from "../common/ThemeManager";

@Builder
export function LayoutBuilder(): void {
  Layout();
}
@Component
export struct Layout {
  @State currentIndex: number = 0;
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  pathStack: NavPathStack = new NavPathStack();

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

  @Builder
  tabItem(index: number): void {
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
        .fontColor(this.currentIndex === index ? "#2563eb" : this.themeManager.colors.secondaryTextColor)
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
    .layoutWeight(1)
    .padding({ top: 6, bottom: 6 })
    .onClick(() => { this.currentIndex = index; })
  }

  build() {
    NavDestination() {
      Column() {
        Column() {
          if (this.currentIndex === 0) { mainPage() }
          if (this.currentIndex === 1) { record() }
          if (this.currentIndex === 2) { AiChat() }
          if (this.currentIndex === 3) { person({ pathStack: this.pathStack }) }
        }
        .layoutWeight(1)

        Row() {
          this.tabItem(0)
          this.tabItem(1)
          this.tabItem(2)
          this.tabItem(3)
        }
        .width('100%')
        .height(56)
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .border({
          width: { top: 0.5 },
          color: this.themeManager.colors.borderColor
        })
      }
      .width('100%').height('100%')
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
    }
    .hideTitleBar(true)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
    .onReady((context: NavDestinationContext): void => {
      this.pathStack = context.pathStack;
    })
  }
}
