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
  // 控制跳转的对象
  pathStack: NavPathStack = new NavPathStack();
  @State username: string = '';
  @State password: string = '';

  build() {
    NavDestination() {
      Column() {
        // --- 1. Logo 和 标题区域 ---
        Column() {
          Image($r('app.media.logo'))
            .width(100)
            .height(100)
            .margin({ bottom: 6 })

          Text('智护星')
            .fontColor($r('app.color.primary_text_color')) // 确保有颜色定义
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
        }

        // --- 2. 输入区域 ---
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
            .placeholderColor($r('app.color.tertiary_text_color'))
            .fontColor($r('app.color.primary_text_color'))
            .border({ width: { bottom: 1 }, color: $r('app.color.separator_color') })

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
              .fontColor($r('app.color.primary_button_color'))
              .margin({ top: 30 })
              .alignSelf(ItemAlign.Start)
              .onClick(() => {
                this.pathStack.pushPathByName('LoginProblem', null, true)
              })
          }
          .width('100%')
        }
        .width('100%')
        .padding({ top: 50, left: 16, right: 16 })
        .alignItems(HorizontalAlign.Start)

        // --- 3. 账号密码登录按钮 ---
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

        // --- 4. 华为账号一键登录区域 ---
        Column() {
          // 分割线 UI
          Row() {
            Divider().strokeWidth(1).color('#E0E0E0').width('30%')
            Text(' 其他登录方式 ').fontSize(12).fontColor('#999999')
            Divider().strokeWidth(1).color('#E0E0E0').width('30%')
          }
          .width('100%')
          .justifyContent(FlexAlign.Center)
          .margin({ bottom: 20, top: 50 })

          // 官方登录按钮组件
          LoginWithHuaweiIDButton({
            params: {
              // 样式配置：红色按钮，圆角
              style: loginComponentManager.Style.BUTTON_RED,
              borderRadius: 24
            },
            // 控制器处理回调
            controller: new loginComponentManager.LoginWithHuaweiIDButtonController()
            // 注意：这里删除了显式类型定义，让编译器自动推断，解决报错
              .onClickLoginWithHuaweiIDButton((error, response) => {
                // --- 失败处理 ---
                if (error) {
                  this.handleLoginError(error);
                  return;
                }
                // --- 成功处理 ---
                if (response) {
                  // 强制类型转换
                  const loginResponse = response as authentication.LoginWithHuaweiIDResponse;
                  const credential = loginResponse.data;

                  if (credential) {
                    const openID = credential.openID;   // 用户唯一标识
                    console.info(`[Login] 登录成功! OpenID: ${openID}`);
                    // 跳转逻辑
                    this.pathStack.replacePathByName('Layout', {}, false);
                  }
                }
              })
          })
            .width('80%')
            .height(48)
        }
        .width('100%')

      } // Column end
      .width('100%')
      .height('100%')
      .backgroundColor($r('app.color.background_color')) // 确保有颜色
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])

    } // NavDestination end
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }

  // 统一错误处理方法
  private handleLoginError(error: BusinessError) {
    console.error(`[Login] 华为账号登录失败 Code: ${error.code}, Message: ${error.message}`);

    let msg = '登录失败';
    // 针对常见错误码做提示优化
    if (error.code === 1001500001) {
      msg = '配置错误：请检查Client ID和指纹是否匹配';
    } else if (error.code === 1001502001) {
      msg = '用户取消了登录';
    } else if (error.code === 1001502009) {
      msg = '签名指纹未在AGC后台配置';
    }

    // 弹窗提示
    AlertDialog.show({
      title: '华为登录提示',
      message: `${msg}\n(错误码: ${error.code})`,
      alignment: DialogAlignment.Center,
      confirm: {
        value: '知道了',
        action: () => {}
      }
    });
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