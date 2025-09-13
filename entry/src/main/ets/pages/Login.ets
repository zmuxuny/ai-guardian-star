// 跳转页面入口函数
@Builder
export function LoginBuilder() {
  Login();
}

@Component
struct Login {
  //控制跳转的对象
  pathStack: NavPathStack = new NavPathStack();

  build() {
    NavDestination() {
      Column() {
        // 导航栏区域
        Row() {
          Text('✖')
            .fontSize(24)
            .fontColor(Color.Black)
            .fontWeight(FontWeight.Normal)
            .onClick(() => {
              // 使用replacePathByName确保不能返回
              this.pathStack.replacePathByName('Layout', null, false);
            })
          
          Blank()
          
          Text('验证码登录')
            .fontSize(16)
            .fontColor('#007AFF')
            .onClick(() => {
              // 切换到验证码登录
            })
        }
        .width('100%')
        .height(44)
        .padding({ left: 16, right: 16 })
        .justifyContent(FlexAlign.SpaceBetween)
        .alignItems(VerticalAlign.Center)

        // 页面标题
        Text('账号密码登录')
          .fontSize(24)
          .fontColor(Color.Black)
          .fontWeight(FontWeight.Bold)
          .margin({ top: 20, bottom: 40 })
          .alignSelf(ItemAlign.Start)
          .margin({ left: 16 })

        // 输入区域
        Column() {
          // 用户名输入框
          TextInput({ placeholder: '请输入手机号码/邮箱/用户名' })
            .width('100%')
            .height(50)
            .fontSize(16)
            .backgroundColor(Color.Transparent)
            .border({ width: { bottom: 1 }, color: '#E5E5E5' })

          // 密码输入框
          TextInput({ placeholder: '请输入密码' })
            .width('100%')
            .height(50)
            .fontSize(16)
            .backgroundColor(Color.Transparent)
            .border({ width: { bottom: 1 }, color: '#E5E5E5' })
            .type(InputType.Password)
            .margin({ top: 20 })

          // 帮助链接
          Text('登录遇到问题?')
            .fontSize(14)
            .fontColor('#007AFF')
            .margin({ top: 16 })
            .alignSelf(ItemAlign.Start)
            .onClick(() => {
              // 处理登录问题
            })
        }
        .width('100%')
        .padding({ left: 16, right: 16 })
        .alignItems(HorizontalAlign.Start)

        Blank()

        // 登录按钮
        Button('登录')
          .width('90%')
          .height(50)
          .fontSize(18)
          .fontColor(Color.White)
          .backgroundColor('#007AFF')
          .borderRadius(8)
          .margin({ bottom: 40 })
          .onClick(() => {
            // 直接跳转，不进行数据验证，使用replacePathByName确保不能返回
            this.pathStack.replacePathByName('Layout', null, false);
          })
      }
      .width('100%')
      .height('100%')
      .backgroundColor(Color.White)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }
}