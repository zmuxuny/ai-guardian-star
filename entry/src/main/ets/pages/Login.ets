import { prompt } from "@kit.ArkUI";
import { media } from "@kit.MediaKit";
import { authentication, LoginWithHuaweiIDButton, loginComponentManager } from '@kit.AccountKit'; // 引入华为账号服务
import { BusinessError } from '@kit.BasicServicesKit'; // 引入基础错误类型

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
  @State username: string = '';
  @State password: string = '';

  build() {
    NavDestination() {
      Column() {
        // Logo 和 标题区域
        Column(){
          Image($r('app.media.logo')) // 确保你有这个图片资源，如果没有请暂时注释掉或换成 $r('app.media.app_icon')
            .width(100)
            .height(100)
            .margin({bottom:6})

          Text('智护星')
            .fontColor($r('app.color.primary_text_color')) // 确保 colors.json 中有这个颜色定义，否则改成 Color.Black
            .fontSize(20)
            .fontWeight(10)
        }

        // 输入区域
        Column() {
          // 用户名输入框
          TextInput({ placeholder: '请输入账号/手机号/邮箱', text: this.username })
            .onChange((value: string) => {
              this.username = value;
            })
            .width('100%')
            .height(55)
            .fontSize(16)
            .backgroundColor(Color.Transparent)
            .placeholderColor($r('app.color.tertiary_text_color')) // 确保有颜色定义，否则改 Color.Gray
            .fontColor($r('app.color.primary_text_color'))
            .border({ width: { bottom: 1 }, color: $r('app.color.separator_color') }) // 确保有颜色定义

          // 密码输入框
          TextInput({ placeholder: '请输入密码', text: this.password })
            .onChange((value: string) => {
              this.password = value;
            })
            .width('100%')
            .height(55)
            .fontSize(16)
            .backgroundColor(Color.Transparent)
            .placeholderColor($r('app.color.tertiary_text_color'))
            .fontColor($r('app.color.primary_text_color'))
            .border({ width: { bottom: 1 }, color: $r('app.color.separator_color') })
            .type(InputType.Password)
            .margin({ top: 45 })

          Row() {
            // 帮助链接
            Text('登录遇到问题?')
              .fontSize(16)
              .fontColor($r('app.color.primary_button_color')) // 确保有颜色定义，否则改 '#007AFF'
              .margin({ top: 30 })
              .alignSelf(ItemAlign.Start)
              .onClick(() => {
                // 处理登录问题
                this.pathStack.pushPathByName('LoginProblem', null, true)
              })

            Blank()
            //验证码登录
            Text('验证码登录')
              .fontSize(16)
              .fontColor('#007AFF')
              .margin({ top: 30 })
              .onClick(() => {
                this.pathStack.pushPathByName('LoginCode', null, true)
              })
              .alignSelf(ItemAlign.End)
          }
          .width('100%')
        }
        .width('100%')
        .padding({ top:50, left: 16, right: 16 })
        .alignItems(HorizontalAlign.Start)

        // 账号密码登录按钮
        Button('登录/注册')
          .onClick(() => {
            const FIXED_ACCOUNT = '192.168.137.100';
            const FIXED_PASSWORD = 'Mind@123';

            if (this.username.trim() === '') {
              this.showCenterAlert('未输入账号');
              return;
            }

            if (this.password.trim() === '') {
              this.showCenterAlert('未输入密码');
              return;
            }

            if (this.username === FIXED_ACCOUNT && this.password === FIXED_PASSWORD) {
              // 登录成功跳转
              this.pathStack.replacePathByName('Layout', {}, false);
            } else {
              this.showCenterAlert('帐号或密码输入错误');
            }
          })
          .width('80%')
          .height(50)
          .fontSize(18)
          .fontColor(Color.White)
          .backgroundColor($r('app.color.primary_button_color'))
          .borderRadius(30)
          .margin({ top: 70 })

        // 提示文本
        Text('未注册将会自动注册账号')
          .fontSize(14)
          .fontColor('#007AFF')
          .margin({ top: 10, bottom: 20 })
          .alignSelf(ItemAlign.Center)

        // -------- 新增：华为账号一键登录区域 --------
        Row() {
          Divider().strokeWidth(1).color('#E0E0E0').width('30%')
          Text(' 其他登录方式 ').fontSize(12).fontColor('#999999')
          Divider().strokeWidth(1).color('#E0E0E0').width('30%')
        }
        .width('100%')
        .justifyContent(FlexAlign.Center)
        .margin({ bottom: 20 })

        // 官方华为账号登录按钮
        LoginWithHuaweiIDButton({
          params: {
            // 设置按钮样式，红色按钮通常比较显眼，也可以选 BLACK 或 WHITE
            style: loginComponentManager.Style.BUTTON_RED,
            borderRadius: 30, // 圆角跟上面的按钮保持一致
            // 注意：这里删除了 loginType，避免报错，使用默认配置
          },
          controller: new loginComponentManager.LoginWithHuaweiIDButtonController()
          // 注意：这里去掉了显式类型定义，让编译器自动推断，解决报错问题
            .onClickLoginWithHuaweiIDButton((error, response) => {
              if (error) {
                console.error(`华为账号登录失败: code: ${error.code}, message: ${error.message}`);
                this.showCenterAlert('华为账号登录失败');
                return;
              }

              if (response) {
                // 强制类型转换为 AuthenticationResponse 以获取数据
                const loginResponse = response as authentication.LoginWithHuaweiIDResponse;
                const credential = loginResponse.data;

                if (credential) {
                  const openID = credential.openID;
                  const unionID = credential.unionID;
                  const authCode = credential.authorizationCode;

                  console.info('华为账号登录成功！');
                  console.info('OpenID: ' + openID);
                  // 可以在这里将 authCode 发送给你的后端服务器进行验证

                  // === 核心：登录成功后的跳转逻辑 ===
                  this.pathStack.replacePathByName('Layout', {}, false);
                }
              }
            })
        })
          .width('80%') // 宽度与上方按钮保持一致
          .height(50)   // 高度与上方按钮保持一致
          .margin({ bottom: 20 })

      }
      .width('100%')
      .height('100%')
      .backgroundColor($r('app.color.background_color')) // 确保有颜色定义，否则改 Color.White
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])

    }.onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }

  // 自定义居中弹窗方法
  private showCenterAlert(message: string): void {
    AlertDialog.show({
      title: '提示',
      message: message,
      alignment: DialogAlignment.Center,
      offset: { dx: 0, dy: 0 },
      primaryButton: {
        value: '确定',
        action: () => {
          console.log('确认按钮被点击');
        }
      },
      gridCount: 6,
      autoCancel: true,
    });
  }
}