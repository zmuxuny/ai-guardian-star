// 跳转页面入口函数
@Builder
export function personBuilder() {
  person();
}

@Component
export struct person{
  pathStack: NavPathStack = new NavPathStack();
  
  build() {
      Column() {
        // 导航栏
          Text('个人信息')
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
            .width('100%')
            //.height(44)
            .margin({ left: 20,top:20,bottom:20 })
            //.padding({left:10})
            .alignSelf(ItemAlign.Start)
        
        // 个人信息内容
        Column() {
          // 基本资料区域
          Column() {
            // 头像
            Row() {
              Text('头像')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Image($r('app.media.person'))
                .width(30)
                .height(30)
                .borderRadius(4)
                .fillColor(Color.Black)
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('AvatarEdit', null, false);
            })
            
            // 昵称
            Row() {
              Text('昵称')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('张三')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('NicknameEdit', null, false);
            })
            
            // 微信号
            Row() {
              Text('微信号')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('zhangsan1900')
                .fontSize(16)
                .fontColor(Color.Black)
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            
            // 二维码名片
            Row() {
              Text('二维码名片')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Image($r('app.media.qrcode'))
                .width(25)
                .height(25)
                .fillColor(Color.Black)
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('QRCodeCard', null, false);
            })
            
            // 更多
            Row() {
              Text('更多')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('MoreInfo', null, false);
            })
          }
          .width('100%')
          .margin({ top: 20 })
          
          // 分隔线
          Divider()
            .width('100%')
            .color('#F2F2F7')
            .strokeWidth(1)
            .margin({ top: 10, bottom: 10 })
          
          // 其他信息区域
          Column() {
            // 我的地址
            Row() {
              Text('我的地址')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('MyAddress', null, false);
            })
            
            // 我的发票抬头
            Row() {
              Text('我的发票抬头')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('InvoiceInfo', null, false);
            })
          }
          .width('100%')
          
          Blank()
        }
        .width('100%')
        .backgroundColor('#F2F2F7')
        Blank()
        // 底部按钮区域
        Column() {
          Button('切换账号')
            .width('80%')
            .height(50)
            .fontSize(18)
            .fontColor(Color.White)
            .backgroundColor('#007AFF')
            .borderRadius(30)
            .margin({ bottom: 16 })
            .onClick(() => {
              // 这里可以添加切换账号的逻辑
              console.log('切换账号')
            })
          
          Button('退出登录')
            .width('80%')
            .height(50)
            .fontSize(18)
            .fontColor('#FF3B30')
            .backgroundColor(Color.Transparent)
            .border({ width: 1, color: '#FF3B30' })
            .borderRadius(30)
            .onClick(() => {
              // 这里可以添加退出登录的逻辑
              console.log('退出登录')
              this.pathStack.replacePathByName('Login', null, false);
            })
        }
        .width('100%')
        .padding({ bottom: 40 })
        .alignItems(HorizontalAlign.Center)
      }
      .width('100%')
      .height('100%')
      .backgroundColor('#F2F2F7')
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}