// 跳转页面入口函数
@Builder
export function AvatarEditBuilder() {
  AvatarEdit();
}

@Component
export struct AvatarEdit {
  pathStack: NavPathStack = new NavPathStack();
  
  build() {
    NavDestination() {
      Column() {
        // 导航栏
        Row() {
          Blank()
          
          Text('头像')
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
          
          Blank()
        }
        .width('100%')
        .height(56)
        .padding({ left: 16, right: 16 })
        .alignItems(VerticalAlign.Center)
        .backgroundColor(Color.White)
        
        // 头像显示区域
        Column() {
          Text('当前头像')
            .fontSize(16)
            .fontColor('#666666')
            .margin({ bottom: 20 })
          
          Image($r('app.media.person'))
            .width(120)
            .height(120)
            .borderRadius(60)
            .border({ width: 2, color: '#E5E5E5' })
          
          Text('点击更换头像')
            .fontSize(14)
            .fontColor('#007AFF')
            .margin({ top: 16 })
            .onClick(() => {
              // 这里可以添加选择图片的逻辑
              console.log('选择新头像')
            })
        }
        .width('100%')
        .padding({ top: 40, bottom: 40 })
        .alignItems(HorizontalAlign.Center)
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