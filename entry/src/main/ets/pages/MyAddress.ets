import { ThemeManager } from '../common/ThemeManager';

@Builder
export function MyAddressBuilder() {
  MyAddress();
}

@Component
export struct MyAddress {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  pathStack: NavPathStack = new NavPathStack();

  @Builder
  TitleBar(): void {
    Row() {
      Text('我的地址')
        .fontSize(18).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .layoutWeight(1)
        .textAlign(TextAlign.Center)
      Text('添加')
        .fontSize(16).fontColor('#2563eb')
        //.padding({ right: 16 })
        .onClick(() => { console.log('添加新地址') })
    }
    .width('100%').height(56).alignItems(VerticalAlign.Center)
  }

  build() {
    NavDestination() {
      Column() {
        // 地址列表
        Column() {
          // 默认地址
          Column() {
            Row() {
              Text('张三')
                .fontSize(16).fontWeight(FontWeight.Bold)
                .fontColor(this.themeManager.colors.primaryTextColor)
              Text('138****8888')
                .fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
                .margin({ left: 12 })
              Blank()
              Text('默认')
                .fontSize(12).fontColor('#FF6B35')
                .backgroundColor(this.themeManager.isDarkMode ? '#3d1f0d' : '#FFF2ED')
                .padding({ left: 8, right: 8, top: 2, bottom: 2 })
                .borderRadius(4)
            }
            .width('100%').margin({ bottom: 8 })

            Text('北京市朝阳区三里屯街道工体北路8号院')
              .fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
              .width('100%').margin({ bottom: 12 })

            Row() {
              Blank()
              Text('编辑').fontSize(14).fontColor('#2563eb').margin({ right: 16 })
                .onClick(() => { console.log('编辑地址') })
              Text('删除').fontSize(14).fontColor('#ef4444')
                .onClick(() => { console.log('删除地址') })
            }.width('100%')
          }
          .width('100%').padding(16)
          .backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .borderRadius(12).margin({ bottom: 12 })
          .shadow({ radius: 6, color: '#0000000A', offsetY: 2 })

          // 其他地址
          Column() {
            Row() {
              Text('李四')
                .fontSize(16).fontWeight(FontWeight.Bold)
                .fontColor(this.themeManager.colors.primaryTextColor)
              Text('139****9999')
                .fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
                .margin({ left: 12 })
              Blank()
            }
            .width('100%').margin({ bottom: 8 })

            Text('上海市浦东新区陆家嘴环路1000号')
              .fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
              .width('100%').margin({ bottom: 12 })

            Row() {
              Blank()
              Text('设为默认').fontSize(14).fontColor('#2563eb').margin({ right: 16 })
                .onClick(() => { console.log('设为默认地址') })
              Text('编辑').fontSize(14).fontColor('#2563eb').margin({ right: 16 })
                .onClick(() => { console.log('编辑地址') })
              Text('删除').fontSize(14).fontColor('#ef4444')
                .onClick(() => { console.log('删除地址') })
            }.width('100%')
          }
          .width('100%').padding(16)
          .backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .borderRadius(12)
          .shadow({ radius: 6, color: '#0000000A', offsetY: 2 })
        }
        .width('100%').padding({ left: 16, right: 16, top: 20 })

        Blank()
      }
      .width('100%').height('100%')
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .title(this.TitleBar)
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }
}
