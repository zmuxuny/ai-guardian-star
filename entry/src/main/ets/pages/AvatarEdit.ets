import { ThemeManager } from '../common/ThemeManager';

@Builder
export function AvatarEditBuilder() {
  AvatarEdit();
}

@Component
export struct AvatarEdit {
  pathStack: NavPathStack = new NavPathStack();
  @State themeManager: ThemeManager = ThemeManager.getInstance();

  build() {
    NavDestination() {
      Column() {
        // 头像显示区域
        Column() {
          Text('当前头像')
            .fontSize(16).fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ bottom: 20 })
          Circle()
            .width(120).height(120)
            .fill(this.themeManager.isDarkMode ? '#1e293b' : '#e2e8f0')
            .border({ width: 2, color: this.themeManager.colors.separatorColor })
          Text('点击更换头像')
            .fontSize(14).fontColor('#2563eb').margin({ top: 16 })
            .onClick(() => { console.log('选择新头像') })
        }
        .width('100%').padding({ top: 40, bottom: 40 })
        .alignItems(HorizontalAlign.Center)
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .margin({ top: 16 }).borderRadius(12)

        Blank()
      }
      .width('100%').height('100%')
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .title('头像')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }
}
