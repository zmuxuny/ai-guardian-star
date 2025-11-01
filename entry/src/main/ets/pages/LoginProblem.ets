@Builder
export function LoginProblemBuilder() {
  LoginProblem();
}

interface FaqList{
  question: string,
  answer: string,
}

@Component
struct LoginProblem {
  pathStack: NavPathStack = new NavPathStack();
  @State currentAnswer: string = ''
  @State aiInputText: string = ''
  @State isExpanded:boolean=false
  @State faqList: Array<FaqList> = [
    {
      question: '忘记密码怎么办？',
      answer: '您可以通过手机验证码找回密码，点击登录页面的"忘记密码"链接进行操作。'

    },
    {
      question: '收不到短信验证码？',
      answer: '请检查手机信号及短信拦截设置，60秒后可重新获取，或尝试语音验证码。'
    },
    {
      question: '账号被锁定如何解决？',
      answer: '连续输错密码会导致临时锁定，请2小时后再试或联系客服解锁。'
    },
    {
     question: '身份验证安全问题忘记答案？',
     answer: '可通过绑定的备用邮箱接收重置链接，或在安全设置中通过人脸识别进行身份核验后重置。'
    },
    {
      question: '企业账号无法发送员工验证短信？',
      answer: '根据最新网络安全法规，企业需自行备案短信通道并通过华为云对接第三方短信服务平台。'
    }
  ]

  build() {
    NavDestination() {
      Column() {

        // 主内容区域
        Column() {
          Text('常见问题')
            .fontSize(24)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
            .margin({ bottom: 20, left: 16, top: 20 })
            .alignSelf(ItemAlign.Start)

          // 问题列表
          List({ space: 10 }) {
            ForEach(this.faqList, (item: FaqList, index) => {
              ListItem() {
                Column() {
                  Text(item.question)
                    .align(Alignment.Center)
                    .fontSize(16)
                    .fontColor('#333333')
                    .padding(16)
                    .width('100%')
                    .backgroundColor('#F5F5F5')
                    .borderRadius(20)

                  Text(item.answer)
                    .width('100%')
                    .fontSize(14)
                    .fontColor('#666666')
                    .padding(16)
                    .backgroundColor('#F5F5F5')
                    .borderRadius(8)
                    .margin({ top: 8 })
                        // .transition({ type: TransitionType.All, duration: 200 })
                    .transition(TransitionEffect.OPACITY.animation({
                          duration: 200, // 动画持续时间
                          curve: Curve.Ease  // 动画曲线类型
                    })
                    )
                }
              }
            })
          }
          .width('100%')
          .height('70%')
          .divider({ strokeWidth: 0 })
        }
        .width('100%')
        .height('80%')

        // AI输入区域
        Row() {
          TextInput({
            text: this.aiInputText,
            placeholder: '输入您的问题...'
          })
            .layoutWeight(1)
            .height(50)
            .fontSize(14)
            .backgroundColor(Color.White)
            .border({ width: 1, color: '#E5E5E5', radius: 25 })

          Button('发送')
            .width(80)
            .height(50)
            .fontColor(Color.White)
            .backgroundColor('#007AFF')
            .borderRadius(25)
            .margin({ left: 10 })
            .onClick(() => {
              // 处理AI提问逻辑
            })
        }
        .width('100%')
        .alignItems(VerticalAlign.Center)
        .padding(16)
        .backgroundColor(Color.White)
      }
      .width('100%')
      .height('100%')
    }
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack
    })

  }
}








