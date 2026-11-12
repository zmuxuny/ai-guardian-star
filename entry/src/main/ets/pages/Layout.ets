import { reduceMotion } from '../common/UiFeedback';
import { MqttManager } from './MqttManager';
import { CarePalette, carePalette } from '../common/CarePalette';
import { mainPage } from "./mainpage";
import { person } from "./person";
import { record } from "./record";
import { AiChat } from "./AiChat";
import { ThemeManager } from "../common/ThemeManager";
import { getWindowSizeClass } from "../common/ResponsiveLayout";
import { STORE_KEY_AI_ENABLED } from "../config";
import { GlassBottomBar, GlassTabItem, GLASS_TAB_CLEARANCE } from "../components/GlassBottomBar";

@Builder
export function LayoutBuilder(): void {
  Layout();
}
@Component
export struct Layout {
  @State @Watch('updateSystemBars') currentIndex: number = 0;
  @State mqtt: MqttManager = MqttManager.getInstance();

  private palette(): CarePalette {
    return carePalette(this.mqtt.isFallDetected, this.mqtt.isSedentaryDetected, this.mqtt.deviceOnline);
  }

  private updateSystemBars(): void {
    this.themeManager.updateSystemUI(this.currentIndex === 0);
  }

  @State glassCompact: boolean = false;
  private scrollTravel: number = 0;
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @StorageLink(STORE_KEY_AI_ENABLED) @Watch('onAiEnabledChanged') aiEnabled: boolean = false;
  @State viewportWidth: number = 360;
  pathStack: NavPathStack = new NavPathStack();

  private onAiEnabledChanged(): void {
    if (!this.aiEnabled && this.currentIndex === 2) this.currentIndex = 3;
  }

  private tabs: GlassTabItem[] = [
    { label: '主页', icon: $r('app.media.tab_home_inactive'), activeIcon: $r('app.media.tab_home_active') },
    { label: '记录', icon: $r('app.media.tab_record_inactive'), activeIcon: $r('app.media.tab_record_active') },
    { label: 'AI助手', icon: $r('app.media.tab_ai_inactive'), activeIcon: $r('app.media.tab_ai_active') },
    { label: '个人', icon: $r('app.media.tab_person_inactive'), activeIcon: $r('app.media.tab_person_active') },
  ];

  private visibleTabs(): GlassTabItem[] {
    return this.aiEnabled ? this.tabs : [this.tabs[0], this.tabs[1], this.tabs[3]];
  }

  private selectGlassTab(slot: number): void {
    const index = !this.aiEnabled && slot === 2 ? 3 : slot;
    this.currentIndex = index;
    this.scrollTravel = 0;
    this.glassCompact = false;
  }

  private observeScroll(index: number, delta: number, state: ScrollState): void {
    if (index !== this.currentIndex || state !== ScrollState.Scroll || delta === 0) return;
    if (this.scrollTravel * delta < 0) this.scrollTravel = 0;
    this.scrollTravel += delta;
    if (Math.abs(this.scrollTravel) < 20) return;
    const compact = this.scrollTravel > 0;
    this.scrollTravel = 0;
    if (this.glassCompact === compact) return;
    this.getUIContext().animateTo({ duration: reduceMotion() ? 0 : 270, curve: Curve.FastOutSlowIn }, () => {
      this.glassCompact = compact;
    });
  }

  @Builder
  pageStack(bottomInset: number = 0): void {
    Stack() {
      Column() { mainPage({ pathStack: this.pathStack, bottomInset: bottomInset,
        onTabScroll: (delta: number, state: ScrollState): void => { this.observeScroll(0, delta, state); } }) }.width('100%').height('100%')
        .visibility(this.currentIndex === 0 ? Visibility.Visible : Visibility.None)
      if (this.currentIndex === 1) {
        Column() { record({ bottomInset: bottomInset, onOpenHome: (): void => { this.selectGlassTab(0); },
          onTabScroll: (delta: number, state: ScrollState): void => { this.observeScroll(1, delta, state); } }) }.width('100%').height('100%')
      }
      if (this.aiEnabled) {
        Column() { AiChat({
          onOpenHome: (): void => { this.selectGlassTab(0); },
          onTabScroll: (delta: number, state: ScrollState): void => { this.observeScroll(2, delta, state); },
        }) }.width('100%').height('100%').padding({ bottom: bottomInset })
          .backgroundColor(this.themeManager.colors.backgroundColor)
          .visibility(this.currentIndex === 2 ? Visibility.Visible : Visibility.None)
      }
      Column() { person({ pathStack: this.pathStack, bottomInset: bottomInset,
        onOpenHome: (): void => { this.selectGlassTab(0); },
        onTabScroll: (delta: number, state: ScrollState): void => { this.observeScroll(3, delta, state); } }) }.width('100%').height('100%')
        .visibility(this.currentIndex === 3 ? Visibility.Visible : Visibility.None)
    }
  }

  @Builder
  railItem(index: number): void {
    Column({ space: 6 }) {
      Image(this.currentIndex === index ? this.tabs[index].activeIcon : this.tabs[index].icon)
        .width(28).height(28)
        .objectFit(ImageFit.Contain)
        .opacity(this.currentIndex === index ? 1.0 : 0.7)
      Text(this.tabs[index].label)
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
    // 侧栏需自行铺到状态栏下方，否则顶部会露出窗口默认底色（深色模式下是一块白）
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
  }

  build() {
    NavDestination() {
      Column() {
        if (getWindowSizeClass(this.viewportWidth) === 'compact') {
          Stack({ alignContent: Alignment.Bottom }) {
            this.pageStack(GLASS_TAB_CLEARANCE)
            GlassBottomBar({
              items: this.visibleTabs(),
              selected: !this.aiEnabled && this.currentIndex === 3 ? 2 : this.currentIndex,
              viewportWidth: this.viewportWidth,
              compact: this.glassCompact,
              darkSurface: this.currentIndex === 0,
              accent: this.currentIndex === 0 || this.themeManager.isDarkMode ? this.palette().accent : this.palette().solid,
              tint: this.palette().wash,
              solid: this.palette().solid,
              onSelect: (slot: number): void => { this.selectGlassTab(slot); },
            }).margin({ bottom: 12 })
          }.width('100%').height('100%')
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
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .onAreaChange((_oldValue: Area, newValue: Area): void => {
        const width = Number(newValue.width);
        if (width > 0) this.viewportWidth = width;
      })
    }
    .hideTitleBar(true)
    .linearGradient({
      direction: GradientDirection.Bottom,
      colors: this.currentIndex === 0
        ? [[this.palette().glow, 0], [this.palette().backdrop, 1]]
        : [[this.themeManager.isDarkMode ? this.themeManager.colors.cardBackgroundColor : this.palette().wash, 0],
          [this.themeManager.colors.backgroundColor, 0.36], [this.themeManager.colors.backgroundColor, 1]],
    })
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    .onShown((): void => { this.updateSystemBars(); })
    .onReady((context: NavDestinationContext): void => {
      this.pathStack = context.pathStack;
    })
  }
}
