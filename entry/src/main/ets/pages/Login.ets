import { prompt } from "@kit.ArkUI";

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
        // 页面标题
        Text('账号密码登录')
          .fontSize(20)
          .fontColor(Color.Black)
          .fontWeight(FontWeight.Bold)
          .margin({ top: 20, bottom: 40, left: 20 })
          .alignSelf(ItemAlign.Start)

        // 输入区域
        Column() {
          // 用户名输入框
          TextInput({ placeholder: '请输入账号', text: this.username })
            .onChange((value: string) => {
              this.username = value;
            })
            .width('100%')
            .height(55)
            .fontSize(16)
            .backgroundColor(Color.Transparent)
            .border({ width: { bottom: 1 }, color: '#E5E5E5' })

          // 密码输入框
          TextInput({ placeholder: '请输入密码', text: this.password })
            .onChange((value: string) => {
              this.password = value;
            })
            .width('100%')
            .height(55)
            .fontSize(16)
            .backgroundColor(Color.Transparent)
            .border({ width: { bottom: 1 }, color: '#E5E5E5' })
            .type(InputType.Password)
            .margin({ top: 45 })

          Row() {
            // 帮助链接
            Text('登录遇到问题?')
              .fontSize(16)
              .fontColor('#007AFF')
              .margin({ top: 30 })
              .alignSelf(ItemAlign.Start)
              .onClick(() => {
                // 处理登录问题
                this.pathStack.pushPathByName('LoginProblem', null, true)
              })

            Blank()
            // 验证码登录
            Text('验证码登录')
              .fontSize(16)
              .fontColor('#007AFF')
              .margin({ top: 30 })
              .onClick(() => {
                // 切换到验证码登录
                this.pathStack.pushPathByName('LoginCode', null, true)
              })
              .alignSelf(ItemAlign.End)
          }
          .width('100%')
        }
        .width('100%')
        .padding({ top:50,left: 16, right: 16 })
        .alignItems(HorizontalAlign.Start)

        //Blank()

        // 登录按钮
        Button('登录/注册')
          .onClick(() => {
            const FIXED_ACCOUNT = '192.168.137.100';
            const FIXED_PASSWORD = 'Mind@123';

            if (this.username.trim() === '') {
              // 使用自定义弹窗替代默认toast
              this.showCenterAlert('未输入账号');
              return;
            }

            if (this.password.trim() === '') {
              // 使用自定义弹窗替代默认toast
              this.showCenterAlert('未输入密码');
              return;
            }

            if (this.username === FIXED_ACCOUNT && this.password === FIXED_PASSWORD) {
              this.pathStack.replacePathByName('Layout', null, false);
            } else {
              // 使用自定义弹窗替代默认toast
              this.showCenterAlert('账号或密码输入错误');
            }
          })
          .width('80%')
          .height(50)
          .fontSize(18)
          .fontColor(Color.White)
          .backgroundColor('#007AFF')
          .borderRadius(30)
          .margin({top:70})

        //提示
        //Text('未注册将会自动注册账号')
          //.fontSize(14)
          //.fontColor('#007AFF')
          //.margin({ top: 10, bottom: 30 })
          //.alignSelf(ItemAlign.Center)

      }
      .width('100%')
      .height('100%')
      .backgroundColor(Color.White)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])

    }.onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }

  // 自定义居中弹窗方法
  private showCenterAlert(message: string): void {
    // 创建自定义弹窗
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
      // 设置弹窗样式
      gridCount: 6, // 控制弹窗宽度
      autoCancel: true, // 点击外部可关闭
    });
  }
}



// import { prompt } from "@kit.ArkUI";
//
// // 跳转页面入口函数
// @Builder
// export function LoginBuilder() {
//   Login();
// }
//
// @Preview
// @Component
// struct Login {
//   //控制跳转的对象
//   pathStack: NavPathStack = new NavPathStack();
//   @State username: string = '';
//   @State password: string = '';
//
//   build() {
//     NavDestination() {
//       Column() {
//         // 页面标题
//         Text('账号密码登录')
//
//           .fontSize(20)
//           .fontColor(Color.Black)
//           .fontWeight(FontWeight.Bold)
//           .margin({ top: 20, bottom: 40, left: 20 })
//           .alignSelf(ItemAlign.Start)
//
//         // 输入区域
//         Column() {
//           // 用户名输入框
//           TextInput({ placeholder: '请输入手机号码/邮箱/用户名', text: this.username })
//             .onChange((value: string) => {
//               this.username = value;
//             })
//             .width('100%')
//             .height(55)
//             .fontSize(16)
//             .backgroundColor(Color.Transparent)
//             .border({ width: { bottom: 1 }, color: '#E5E5E5' })
//
//           // 密码输入框
//           TextInput({ placeholder: '请输入密码', text: this.password })
//             .onChange((value: string) => {
//               this.password = value;
//             })
//             .width('100%')
//             .height(55)
//             .fontSize(16)
//             .backgroundColor(Color.Transparent)
//             .border({ width: { bottom: 1 }, color: '#E5E5E5' })
//             .type(InputType.Password)
//             .margin({ top: 45 })
//
//           Row() {
//             // 帮助链接
//             Text('登录遇到问题?')
//               .fontSize(16)
//               .fontColor('#007AFF')
//               .margin({ top: 30 })
//               .alignSelf(ItemAlign.Start)
//               .onClick(() => {
//                 // 处理登录问题
//                 this.pathStack.pushPathByName('LoginProblem', null, true)
//               })
//
//             Blank()
//             // 验证码登录
//             Text('验证码登录')
//               .fontSize(16)
//               .fontColor('#007AFF')
//               .margin({ top: 30 })
//               .onClick(() => {
//                 // 切换到验证码登录
//                 this.pathStack.pushPathByName('LoginCode', null, true)
//               })
//               .alignSelf(ItemAlign.End)
//           }
//           .width('100%')
//         }
//         .width('100%')
//         .padding({ top:50,left: 16, right: 16 })
//         .alignItems(HorizontalAlign.Start)
//
//         // Row () {
//         //     Column() {
//         //       Button() {
//         //         Image($r('app.media.icon_QQ'))
//         //           .width(48)
//         //           .height(48)
//         //       }
//         //       .backgroundColor(Color.White)
//         //       .onClick(() => {
//         //         // QQ跳转逻辑
//         //       })
//         //
//         //       Text('QQ登录')
//         //         .fontColor(Color.Black)
//         //         .margin({ top: 6 })
//         //         .fontSize(15)
//         //         .textAlign(TextAlign.Center)
//         //     }
//         //     .alignItems(HorizontalAlign.Center)
//         //
//         //   Column() {
//         //     Button() {
//         //       Image($r('app.media.weixin'))
//         //         .width(43)
//         //         .height(43)
//         //     }
//         //     .backgroundColor(Color.White)
//         //     .onClick(() => {
//         //       //微信跳转页面
//         //     })
//         //
//         //     Text('微信登录')
//         //       .margin({top:8})
//         //       .fontColor(Color.Black)
//         //       .fontSize(15)
//         //       .textAlign(TextAlign.Center)
//         //   }
//         //   .alignItems(HorizontalAlign.Center)
//         //
//         //     Column() {
//         //       Button() {
//         //         Image($r('app.media.guestLogin'))
//         //           .width(46)
//         //           .height(46)
//         //       }
//         //       .backgroundColor(Color.White)
//         //       .onClick(() => {
//         //         // 游客跳转逻辑
//         //         this.pathStack.replacePathByName('Layout',null, false);
//         //       })
//         //
//         //       Text('游客登录')
//         //         .fontColor(Color.Black)
//         //         .margin({top:5})
//         //         .fontSize(15)
//         //         .textAlign(TextAlign.Center)
//         //     }
//         //     .alignItems(HorizontalAlign.Center)
//         //
//         //   }
//         //   .width('100%')
//         //   .margin({top:50})
//         //   .justifyContent(FlexAlign.SpaceEvenly)
//
//             Blank()
//
//             // 登录按钮
//             Button('登录/注册')
//               .onClick(() => {
//                 const FIXED_ACCOUNT = '192.168.137.100';
//                 const FIXED_PASSWORD = 'Mind@123';
//
//                 if (this.username.trim() === '') {
//                   prompt.showToast({ message: '未输入账号', duration: 2000 });
//                   return;
//                 }
//
//                 if (this.password.trim() === '') {
//                   prompt.showToast({ message: '未输入密码', duration: 2000 });
//                   return;
//                 }
//
//
//                 if (this.username === FIXED_ACCOUNT && this.password === FIXED_PASSWORD) {
//                   this.pathStack.replacePathByName('Layout', null, false);
//                 } else {
//                   // 显示错误提示
//                   prompt.showToast({
//                     message: '账号或密码输入错误',
//                     duration: 2000
//                   });
//                 }
//               })
//               .width('80%')
//               .height(50)
//               .fontSize(18)
//               .fontColor(Color.White)
//               .backgroundColor('#007AFF')
//               .borderRadius(30)
//             //.margin({ bottom: 40 })
//
//
//             //提示
//             Text('未注册将会自动注册账号')
//               .fontSize(14)
//               .fontColor('#007AFF')
//               .margin({ top: 10, bottom: 30 })
//               .alignSelf(ItemAlign.Center)
//
//           }
//           .width('100%')
//           .height('100%')
//           .backgroundColor(Color.White)
//           .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
//
//       }.onReady((context: NavDestinationContext) => {
//       this.pathStack = context.pathStack;  })
//
//
//     }
//
//   }
