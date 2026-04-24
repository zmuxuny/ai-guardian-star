import { ThemeManager } from '../common/ThemeManager';

@Builder
export function MyAddressBuilder() {
  MyAddress();
}

@Component
export struct MyAddress {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  pathStack: NavPathStack = new NavPathStack();
  @StorageProp("topSafeHeight") topSafeHeight: number = 48;

  // ── 自定义标题栏（沉浸式渐变，同 Profile 写法） ─────────────
  @Builder
  GradientHeader(): void {
    Stack({ alignContent: Alignment.Top }) {
      // 层1：渐变背景（固定高度 = 标题栏区，通过 expandSafeArea 延伸到状态栏）
      Column()
        .width("100%")
        .height(this.topSafeHeight + 100)
        .linearGradient({
          direction: GradientDirection.Bottom,
          colors: [
            ["#1e40af", 0.0],
            ["#3b82f6", 0.5],
            ["#60a5fa", 1.0],
          ],
        })
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
        .borderRadius({ bottomLeft: "6%", bottomRight: "6%" })

      // 层2：标题栏内容区
      Row() {
        Image($r("app.media.ic_chevron_right"))
          .width(36)
          .height(36)
          .objectFit(ImageFit.Contain)
          .padding(8)
          .backgroundColor("#33FFFFFF")
          .borderRadius(100)
          .rotate({ angle: 180 })
          .onClick((): void => {
            this.pathStack.pop();
          })
        Text("我的地址")
          .fontSize(22)
          .fontWeight(FontWeight.Bold)
          .fontColor("#ffffff")
          .margin({ left: "5%" })
      }
      .width("100%")
      .padding({ left: "4%", right: "4%", top: this.topSafeHeight})
    }
    .width("100%")
  }

  build() {
    NavDestination() {
      Column() {
        this.GradientHeader()

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
        .layoutWeight(1)

        Blank()
      }
      .width('100%').height('100%')
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .hideTitleBar(true)
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }
}
