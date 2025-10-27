// 跳转页面入口函数
@Builder
export function LoginBuilder() {
  Login();
}

@Preview
@Component
struct Login {
  //控制跳转的对象
  pathStack: NavPathStack = new NavPathStack();

  build() {
    NavDestination() {
      Column() {
        // 页面标题
        Text('账号密码登录')
          .fontSize(20)
          .fontColor(Color.Black)
          .fontWeight(FontWeight.Bold)
          .margin({ top: 20, bottom: 40,left: 20 })
          .alignSelf(ItemAlign.Start)

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

          Row() {
            // 帮助链接
            Text('登录遇到问题?')
              .fontSize(16)
              .fontColor('#007AFF')
              .margin({ top: 16 })
              .alignSelf(ItemAlign.Start)
              .onClick(() => {
                // 处理登录问题
                this.pathStack.pushPathByName('LoginProblem',null, true)
              })

            Blank()
            // 验证码登录
            Text('验证码登录')
              .fontSize(16)
              .fontColor('#007AFF')
              .margin({ top: 16 })
              .onClick(() => {
                // 切换到验证码登录
                this.pathStack.pushPathByName('LoginCode',null,true)
              })
              .alignSelf(ItemAlign.End)
          }
          .width('100%')
        }
        .width('100%')
        .padding({ left: 16, right: 16 })
        .alignItems(HorizontalAlign.Start)

        Row() {
          Column() {
            Column() {
              Button() {
                Image($r('app.media.icon_QQ'))
                  .width(48)
                  .height(48)
              }
              .backgroundColor(Color.White)

              Text('QQ登录')
                .fontColor(Color.Black)
                .margin({top:6})
                .fontSize(15)
                .textAlign(TextAlign.Center)
            }
            .alignItems(HorizontalAlign.Center)
          }
          .onClick(() => {
            // QQ跳转逻辑
          })

          Column() {
            Button() {
              Image($r('app.media.weixin'))
                .width(43)
                .height(43)
            }
            .backgroundColor(Color.White)
            .onClick(() => {
              //微信跳转页面
            })

            Text('微信登录')
              .margin({top:8})
              .fontColor(Color.Black)
              .fontSize(15)
              .textAlign(TextAlign.Center)
          }

          Column() {
            Button() {
              Image($r('app.media.guestLogin'))
                .width(48)
                .height(48)
            }
            .backgroundColor(Color.White)

            Text('游客登录')
              .fontColor(Color.Black)
              .margin({top:6})
              .fontSize(15)
              .textAlign(TextAlign.Center)
          }
          .alignItems(HorizontalAlign.Center)

        .onClick(() => {
          // 游客跳转逻辑
          this.pathStack.replacePathByName('Layout',null, false);
        })
        }
        .width('100%')
        .margin({top:50})
        .justifyContent(FlexAlign.SpaceEvenly)

        Blank()

        // 登录按钮
        Button('登录/注册')
          .width('80%')
          .height(50)
          .fontSize(18)
          .fontColor(Color.White)
          .backgroundColor('#007AFF')
          .borderRadius(30)
          //.margin({ bottom: 40 })
          .onClick(() => {
            // 直接跳转，不进行数据验证，使用replacePathByName确保不能返回
            this.pathStack.replacePathByName('Layout',null, false);
          })

        //提示
        Text('未注册将会自动注册账号')
          .fontSize(14)
          .fontColor('#007AFF')
          .margin({ top: 10,bottom:30 })
          .alignSelf(ItemAlign.Center)

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