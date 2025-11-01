
@Builder
export function LoginCodeBuilder() {
  LoginCode();
}

@Component
struct LoginCode {

  pathStack: NavPathStack = new NavPathStack();
  @State countdown: number = 60
  @State isCounting: boolean = false

  private timer: number = 0

  startCountdown() {
    this.isCounting = true
    this.timer = setInterval(() => {
      if (this.countdown > 0) {
        this.countdown--
      } else {
        clearInterval(this.timer)
        this.isCounting = false
        this.countdown = 60
      }
    }, 1000)
  }


  build() {
    NavDestination() {
      Column() {
        Text('验证码登录')
          .fontSize(24)
          .fontColor(Color.Black)
          .fontWeight(FontWeight.Bold)
          .margin({ top: 30, bottom: 40, left: 20 })
          .alignSelf(ItemAlign.Start)

        // 输入区域
        Column() {
          // 用户名输入框
          TextInput({ placeholder: '请输入手机号码' })
            .width('90%')
            .height(50)
            .fontSize(16)
            .backgroundColor(Color.Transparent)
            .border({ width: { bottom: 1 }, color: '#E5E5E5' })

          // 验证码输入框
          Stack({ alignContent: Alignment.End }) {
            TextInput({ placeholder: '请输入验证码' })
              .width('90%')
              .height(50)
              .fontSize(16)
              .backgroundColor(Color.Transparent)
              .border({ width: { bottom: 1 }, color: '#E5E5E5' })
              // .type(InputType.Password)
              .margin({ top: 25 })
              .layoutWeight(1)

            Button(this.isCounting ? `${this.countdown}s后重发` : '发送验证码')
              .fontColor(this.isCounting ? Color.Gray : Color.Black)
              .backgroundColor('#E5E5E5')
              .align(Alignment.End)
              .margin({ left: 10, top: 25 })
              .onClick(() => {
                if (!this.isCounting) {
                  this.startCountdown()
                  // 这里添加实际发送验证码逻辑
                }
              })


            // Button('发送验证码')
            //   .height(40)
            //   .fontSize(15)
            //   .fontColor(Color.Black)
            //   .backgroundColor('#E5E5E5')
            //   .align(Alignment.End)
            //   .margin({ left: 10, top: 25 })
            //   .onClick(() => {
            //   //点击之后出现60s倒计时，结束后自动回到发送验证码按钮
            //
            //   })
          }

        }

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
            //this.pathStack.clear();
            //this.pathStack.replacePathByName('Layout', null, false);
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
