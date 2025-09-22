// 跳转页面入口函数
@Builder
export function NicknameEditBuilder() {
  NicknameEdit();
}

@Component
export struct NicknameEdit {
  @State nickname: string = '张三'
  pathStack: NavPathStack = new NavPathStack();

  build() {
    NavDestination() {
      Column() {
        // 导航栏
        Row() {
          Blank()
          
          Text('昵称')
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
          
          Blank()
          
          Text('保存')
            .fontSize(16)
            .fontColor('#007AFF')
            .onClick(() => {
              // 这里可以添加保存昵称的逻辑
              console.log('保存昵称:', this.nickname)
              this.pathStack.replacePathByName('person', null, false);
            })
        }
      .width('100%')
      .height(56)
      .padding({ left: 16, right: 16 })
      .alignItems(VerticalAlign.Center)
      .backgroundColor(Color.White)

      // 输入区域
      Column() {
        Text('昵称')
          .fontSize(16)
          .fontColor(Color.Black)
          .alignSelf(ItemAlign.Start)
          .margin({ bottom: 12 })

        TextInput({ placeholder: '请输入昵称' })
          .width('100%')
          .height(44)
          .fontSize(16)
          .backgroundColor('#F8F8F8')
          .borderRadius(8)
          .padding({ left: 12, right: 12 })
          .onChange((value: string) => {
            this.nickname = value
          })
      }
      .width('100%')
      .padding({
        left: 16,
        right: 16,
        top: 20,
        bottom: 20
      })
      .backgroundColor(Color.White)
      .margin({ top: 20 })

      Blank()
    }
      .width('100%')
      .height('100%')
      .backgroundColor('#F2F2F7')
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }
}
