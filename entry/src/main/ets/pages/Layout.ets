import { mainPage } from "./mainpage";
import { person } from "./person";
import { record } from "./record";
import { AiChat } from "./AiChat";
import { ThemeManager } from "../common/ThemeManager";
import { getWindowSizeClass } from "../common/ResponsiveLayout";
import { STORE_KEY_AI_ENABLED } from "../config";

@Builder
export function LayoutBuilder(): void {
  Layout();
}
@Component
export struct Layout {
  @State currentIndex: number = 0;
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @StorageLink(STORE_KEY_AI_ENABLED) aiEnabled: boolean = true;
  @State viewportWidth: number = 360;
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
        .opacity(1.0)
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

  @Builder
  pageStack(): void {
    Stack() {
      Column() { mainPage() }.width('100%').height('100%')
        .visibility(this.currentIndex === 0 ? Visibility.Visible : Visibility.None)
      Column() { record() }.width('100%').height('100%')
        .visibility(this.currentIndex === 1 ? Visibility.Visible : Visibility.None)
      if (this.aiEnabled) {
        Column() { AiChat() }.width('100%').height('100%')
          .visibility(this.currentIndex === 2 ? Visibility.Visible : Visibility.None)
      }
      Column() { person({ pathStack: this.pathStack }) }.width('100%').height('100%')
        .visibility(this.currentIndex === 3 ? Visibility.Visible : Visibility.None)
    }
  }

  @Builder
  railItem(index: number): void {
    Column({ space: 6 }) {
      Image(this.getTabIconResource(index))
        .width(28).height(28)
        .objectFit(ImageFit.Contain)
        .opacity(this.currentIndex === index ? 1.0 : 0.7)
      Text(this.getTabText(index))
        .fontSize(12)
        .fontWeight(this.currentIndex === index ? FontWeight.Bold : FontWeight.Normal)
        .fontColor(this.currentIndex === index ? '#2563EB' : this.themeManager.colors.secondaryTextColor)
    }
    .width(80).height(64)
    .justifyContent(FlexAlign.Center)
    .backgroundColor(this.currentIndex === index
      ? (this.themeManager.isDarkMode ? '#1E3A5F' : '#EFF6FF')
      : Color.Transparent)
    .borderRadius(16)
    .onClick(() => { this.currentIndex = index; })
  }

  @Builder
  sideNavigation(): void {
    Column({ space: 10 }) {
      Blank()
      this.railItem(0)
      this.railItem(1)
      if (this.aiEnabled) {
        this.railItem(2)
      }
      this.railItem(3)
      Blank()
    }
    .width(96).height('100%')
    .alignItems(HorizontalAlign.Center)
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .border({ width: { right: 0.5 }, color: this.themeManager.colors.borderColor })
  }

  build() {
    NavDestination() {
      Column() {
        if (getWindowSizeClass(this.viewportWidth) === 'compact') {
          Column() {
            this.pageStack()
          }.layoutWeight(1).width('100%')
          Row() {
            this.tabItem(0)
            this.tabItem(1)
            if (this.aiEnabled) {
              this.tabItem(2)
            }
            this.tabItem(3)
          }
          .width('100%')
          .height(56)
          .backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .border({ width: { top: 0.5 }, color: this.themeManager.colors.borderColor })
        } else {
          Row() {
            this.sideNavigation()
            Column() { this.pageStack() }
              .layoutWeight(1).height('100%')
              .backgroundColor(this.themeManager.colors.backgroundColor)
          }.width('100%').height('100%')
        }
      }
      .width('100%').height('100%')
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
      .onAreaChange((_oldValue: Area, newValue: Area): void => {
        const width = Number(newValue.width);
        if (width > 0) this.viewportWidth = width;
      })
    }
    .hideTitleBar(true)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
    .onReady((context: NavDestinationContext): void => {
      this.pathStack = context.pathStack;
    })
  }
}
