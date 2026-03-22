import { prompt } from "@kit.ArkUI";
import { media } from "@kit.MediaKit";
import { authentication, LoginWithHuaweiIDButton, loginComponentManager } from '@kit.AccountKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { ThemeManager } from '../common/ThemeManager';

// 跳转页面入口函数
@Builder
export function LoginBuilder() {
  Login();
}

@Preview
@Component
struct Login {
  pathStack: NavPathStack = new NavPathStack();
  @State username: string = '';
  @State password: string = '';
  @State themeManager: ThemeManager = ThemeManager.getInstance();

  build() {
    NavDestination() {
      Column() {
        // Logo 和 标题区域
        Column(){
          Image($r('app.media.logo'))
            .width(100)
            .height(100)
            .margin({bottom:6})

          Text('智护星')
            .fontColor(this.themeManager.colors.primaryTextColor)
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
            .placeholderColor(this.themeManager.colors.tertiaryTextColor)
            .fontColor(this.themeManager.colors.primaryTextColor)
            .border({ width: { bottom: 1 }, color: this.themeManager.colors.separatorColor })

          // 密码输入框
          TextInput({ placeholder: '请输入密码', text: this.password })
            .onChange((value: string) => {
              this.password = value;
            })
            .width('100%')
            .height(55)
            .fontSize(16)
            .backgroundColor(Color.Transparent)
            .placeholderColor(this.themeManager.colors.tertiaryTextColor)
            .fontColor(this.themeManager.colors.primaryTextColor)
            .border({ width: { bottom: 1 }, color: this.themeManager.colors.separatorColor })
            .type(InputType.Password)
            .margin({ top: 45 })

          Row() {
            // 帮助链接
            Text('登录遇到问题?')
              .fontSize(16)
              .fontColor(this.themeManager.colors.primaryButtonColor)
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
          .backgroundColor(this.themeManager.colors.primaryButtonColor)
          .borderRadius(30)
          .margin({ top: 70 })

        // 提示文本
        Text('未注册将会自动注册账号')
          .fontSize(14)
          .fontColor('#007AFF')
          .margin({ top: 10, bottom: 20 })
          .alignSelf(ItemAlign.Center)

        // -------- 官方华为账号登录区域 --------
        Row() {
          Divider().strokeWidth(1).color(this.themeManager.colors.separatorColor).width('30%')
          Text(' 其他登录方式 ').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
          Divider().strokeWidth(1).color(this.themeManager.colors.separatorColor).width('30%')
        }
        .width('100%')
        .justifyContent(FlexAlign.Center)
        .margin({ bottom: 20 })

        // 官方华为账号登录按钮
        LoginWithHuaweiIDButton({
          params: {
            style: loginComponentManager.Style.BUTTON_RED,
            borderRadius: 30,
          },
          controller: new loginComponentManager.LoginWithHuaweiIDButtonController()
            .onClickLoginWithHuaweiIDButton((error: BusinessError, response: loginComponentManager.HuaweiIDCredential) => {
              if (error) {
                // 打印详细错误码，方便对照华为文档排查
                console.error(`[Login]: 华为登录失败! 错误码: ${error.code}, 消息: ${error.message}`);
                
                let errorMsg = '登录失败';
                if (error.code === 100004) errorMsg = '环境不支持(请检查HMS Core)';
                if (error.code === 6003) errorMsg = '证书指纹校验失败';
                
                this.showCenterAlert(errorMsg);
                return;
              }

              if (response) {
                try {
                  // 安全获取凭证信息
                  const credential = response as authentication.LoginWithHuaweiIDResponse;
                  const data = credential.data;

                  if (data) {
                    console.info('[Login]: 华为账号登录成功, OpenID: ' + data.openID);
                    // 登录成功跳转主框架
                    this.pathStack.replacePathByName('Layout', {}, false);
                  }
                } catch (e) {
                  console.error('[Login]: 解析登录数据异常: ' + JSON.stringify(e));
                }
              }
            })
        })
          .width('80%')
          .height(50)
          .margin({ bottom: 20 })

      }
      .width('100%')
      .height('100%')
      .backgroundColor(this.themeManager.colors.backgroundColor)
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