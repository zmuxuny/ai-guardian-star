import { reduceMotion } from '../common/UiFeedback';
import { MqttManager } from './MqttManager';
import { CarePalette, carePalette } from '../common/CarePalette';
import { mainPage } from "./mainpage";
import { person } from "./person";
import { record } from "./record";
import { AiChat } from "./AiChat";
import { ThemeManager } from "../common/ThemeManager";
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
    if (index !== this.currentIndex) this.onTabChanged(this.currentIndex);
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

  // 四页常驻，切换统一用样张的 0.28 秒淡入 + 轻缩放；离场页动画结束后再隐藏
  @State leavingIndex: number = -1;
  private leaveTimer: number = -1;

  private onTabChanged(previous: number): void {
    if (this.leaveTimer !== -1) clearTimeout(this.leaveTimer);
    this.leavingIndex = previous;
    this.leaveTimer = setTimeout((): void => {
      this.leaveTimer = -1;
      this.leavingIndex = -1;
    }, 300) as number;
  }

  private tabVisibility(index: number): Visibility {
    return this.currentIndex === index || this.leavingIndex === index ? Visibility.Visible : Visibility.None;
  }

  @Builder
  tabPage(index: number, bottomInset: number): void {
    Column() {
      if (index === 0) {
        mainPage({ pathStack: this.pathStack, bottomInset: bottomInset,
          onTabScroll: (delta: number, state: ScrollState): void => { this.observeScroll(0, delta, state); } })
      } else if (index === 1) {
        record({ bottomInset: bottomInset, onOpenHome: (): void => { this.selectGlassTab(0); },
          onTabScroll: (delta: number, state: ScrollState): void => { this.observeScroll(1, delta, state); } })
      } else if (index === 2) {
        AiChat({
          bottomInset: bottomInset,
          onOpenHome: (): void => { this.selectGlassTab(0); },
          onTabScroll: (delta: number, state: ScrollState): void => { this.observeScroll(2, delta, state); },
        })
      } else {
        person({ pathStack: this.pathStack, bottomInset: bottomInset,
          onOpenHome: (): void => { this.selectGlassTab(0); },
          onTabScroll: (delta: number, state: ScrollState): void => { this.observeScroll(3, delta, state); } })
      }
    }
    .width('100%').height('100%')
    .visibility(this.tabVisibility(index))
    .zIndex(this.currentIndex === index ? 1 : 0)
    .hitTestBehavior(this.currentIndex === index ? HitTestMode.Default : HitTestMode.None)
    .opacity(this.currentIndex === index ? 1 : 0)
    .scale({ x: this.currentIndex === index ? 1 : 0.965, y: this.currentIndex === index ? 1 : 0.965 })
    .animation({ duration: reduceMotion() ? 0 : 280, curve: Curve.FastOutSlowIn })
  }

  @Builder
  pageStack(bottomInset: number = 0): void {
    Stack() {
      this.tabPage(0, bottomInset)
      this.tabPage(1, bottomInset)
      if (this.aiEnabled) {
        this.tabPage(2, bottomInset)
      }
      this.tabPage(3, bottomInset)
    }
  }

  build() {
    NavDestination() {
      Column() {
        // 手机、平板共用同一个玻璃底栏（形状、按压和左右拖动切换都一致），不再单独做平板侧栏
        Stack({ alignContent: Alignment.Bottom }) {
          this.pageStack(GLASS_TAB_CLEARANCE)
          GlassBottomBar({
            items: this.visibleTabs(),
            selected: !this.aiEnabled && this.currentIndex === 3 ? 2 : this.currentIndex,
            viewportWidth: this.viewportWidth,
            compact: this.glassCompact,
            darkSurface: this.currentIndex === 0 || this.themeManager.isDarkMode,
            accent: this.currentIndex === 0 || this.themeManager.isDarkMode ? this.palette().accent : this.palette().solid,
            tint: this.palette().wash,
            onSelect: (slot: number): void => { this.selectGlassTab(slot); },
          }).margin({ bottom: 12 })
        }.width('100%').height('100%')
      }
      .width('100%').height('100%')
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .onAreaChange((_oldValue: Area, newValue: Area): void => {
        const width = Number(newValue.width);
        if (width > 0) this.viewportWidth = width;
      })
    }
    .hideTitleBar(true)
    // 各页自己铺满安全区；这里只留与阅读页相同的底色，避免切换时露出别的颜色
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    .onShown((): void => { this.updateSystemBars(); })
    .onReady((context: NavDestinationContext): void => {
      this.pathStack = context.pathStack;
    })
  }
}
