import { ThemeManager } from '../common/ThemeManager';

@Builder
export function NicknameEditBuilder() {
  NicknameEdit();
}

@Component
export struct NicknameEdit {
  @State nickname: string = '张三'
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  pathStack: NavPathStack = new NavPathStack();

  // 自定义标题栏：中间标题 + 右侧保存按钮，左侧系统返回键保留
  @Builder
  TitleBar(): void {
    Row() {
      Text('昵称')
        .fontSize(18).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .layoutWeight(1)
        .textAlign(TextAlign.Center)
      Blank();
      Text('保存')
        .fontSize(16).fontColor('#2563eb')
        .padding({ right: 16 })
        .onClick(() => {
          console.log('保存昵称:', this.nickname);
          this.pathStack.pop();
        })
    }
    .width('100%').height(56).alignItems(VerticalAlign.Center)
  }

  build() {
    NavDestination() {
      Column() {
        Column() {
          Text('昵称')
            .fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
            .alignSelf(ItemAlign.Start).margin({ bottom: 10 })
          TextInput({ placeholder: '请输入昵称', text: this.nickname })
            .width('100%').height(48).fontSize(16)
            .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#F8F8F8')
            .fontColor(this.themeManager.colors.primaryTextColor)
            .placeholderColor(this.themeManager.colors.tertiaryTextColor)
            .borderRadius(10)
            .padding({ left: 14, right: 14 })
            .onChange((value: string) => { this.nickname = value })
        }
        .width('100%')
        .padding({ left: 16, right: 16, top: 20, bottom: 20 })
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .margin({ top: 16 }).borderRadius(12)

        Blank()
      }
      .width('100%').height('100%')
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .title(this.TitleBar)
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }
}
