import { ThemeManager, ThemeMode } from '../common/ThemeManager';
import { MqttManager } from './MqttManager';
import { promptAction } from '@kit.ArkUI';

@Builder
export function personBuilder(): void {
  NavDestination() { person() }.hideTitleBar(true)
}

@Component
export struct person {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State userName: string = "超级管理员";
  @State userId: string = "ID: 69175890";
  @State useDays: number = 128;
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;
  pathStack: NavPathStack | undefined = undefined;

  private safePush(pageName: string): void {
    if (this.pathStack) this.pathStack.pushPathByName(pageName, null);
  }

  @Builder
  GradientHeader(): void {
    Column() {
      Stack() {
        Circle().width('60%').aspectRatio(1)
          .fill('rgba(255,255,255,0.2)').border({ width: 2, color: 'rgba(255,255,255,0.6)' })
        Image($r('app.media.ic_user'))
          .width('50%').aspectRatio(1).objectFit(ImageFit.Contain)
      }
      .width('22%').aspectRatio(1).onClick((): void => this.safePush("AvatarEdit"))

      Text(this.userName).fontSize(22).fontWeight(FontWeight.Bold)
        .fontColor('#ffffff').margin({ top: '4%' })
      Text(this.userId).fontSize(13).fontColor('#CCFFFFFF').margin({ top: '2%' })
    }
    .width('100%').padding({ top: this.topSafeHeight + 24, bottom: 20 })
    .linearGradient({ direction: GradientDirection.Bottom,
      colors: [['#1e40af', 0.0], ['#3b82f6', 0.5], ['#60a5fa', 1.0]] })
    .borderRadius({ bottomLeft: '6%', bottomRight: '6%' })
  }

  @Builder
  StatDashboard(): void {
    Row() {
      Column() {
        Text(`${this.useDays}`).fontSize(28).fontWeight(FontWeight.Bold).fontColor('#1e40af')
        Text('天·已监护').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: 6 })
      }.layoutWeight(1)
      // 竖向分隔线
      Column()
        .width(1)
        .height(36)
        .backgroundColor(this.themeManager.colors.separatorColor)
      Column() {
        Text(`${this.mqttManager.fallRecords.length}`).fontSize(28).fontWeight(FontWeight.Bold).fontColor('#1e40af')
        Text('次·已预警').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: 6 })
      }.layoutWeight(1)
    }
    .width('88%').padding({ top: 20, bottom: 20 })
    .margin({ top: -36 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius('4%')
    .shadow({ radius: 12, color: '#1A3b82f6', offsetY: 6 })
  }


  @Builder
  MenuRow(imgRes: Resource, bgColorLight: string, bgColorDark: string, title: string, subTitle: string, onClickAction: () => void): void {
    Row() {
      Image(imgRes)
        .width(36).height(36).objectFit(ImageFit.Contain)
        .padding(8)
        .backgroundColor(this.themeManager.isDarkMode ? bgColorDark : bgColorLight)
        .borderRadius(10).margin({ right: '4%' })
      Column() {
        Text(title).fontSize(15).fontWeight(FontWeight.Medium)
          .fontColor(this.themeManager.colors.primaryTextColor)
        Text(subTitle).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: '2%' })
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
      Image($r('app.media.ic_chevron_right'))
        .width(16).height(16).objectFit(ImageFit.Contain)
    }
    .width('100%').padding({ left: '4%', right: '4%', top: '3.5%', bottom: '3.5%' })
    .constraintSize({ minHeight: 64 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .onClick((): void => { if (onClickAction) onClickAction(); })
  }

  build() {
    Scroll() {
      Column() {
        this.GradientHeader()
        this.StatDashboard()

        Column() {
          Text("服务设置").fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ left: '6%', bottom: '3%', top: '6%' }).alignSelf(ItemAlign.Start)
          Column() {
            this.MenuRow($r('app.media.ic_user_blue'), '#eff6ff', '#1e3a5f',
              "个人资料", "修改头像、昵称及手机号", (): void => this.safePush("NicknameEdit"))
            Divider().margin({ left: '15%', right: '4%' }).color(this.themeManager.colors.separatorColor)
            this.MenuRow($r('app.media.ic_map_pin_green'), '#f0fdf4', '#14302a',
              "常用地址", "管理家庭地址及位置信息", (): void => this.safePush("MyAddress"))
            Divider().margin({ left: '15%', right: '4%' }).color(this.themeManager.colors.separatorColor)
            this.MenuRow($r('app.media.ic_phone_orange'), '#fff7ed', '#3d2000',
              "紧急联系人", "危急时刻一键呼叫通知",
              (): void => { promptAction.showToast({ message: "功能开发中" }) })
          }
          .width('92%').backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .borderRadius('4%').clip(true)
          .shadow({ radius: 8, color: '#0000000F', offsetY: 4 })
        }.width('100%')

        Column() {
          Text("系统偏好").fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ left: '6%', bottom: '3%', top: '5%' }).alignSelf(ItemAlign.Start)
          Column() {
            Row() {
              Image(this.themeManager.isDarkMode ? $r('app.media.ic_shield_light') : $r('app.media.ic_shield_gray'))
                .width(36).height(36).objectFit(ImageFit.Contain)
                .padding(8)
                .backgroundColor(this.themeManager.isDarkMode ? '#334155' : '#f1f5f9')
                .borderRadius(10).margin({ right: '4%' })
              Text("外观模式").fontSize(15).fontWeight(FontWeight.Medium)
                .fontColor(this.themeManager.colors.primaryTextColor)
              Blank()
              Row() {
                Text(this.themeManager.themeMode === ThemeMode.LIGHT ? "浅色" :
                  this.themeManager.themeMode === ThemeMode.DARK ? "深色" : "跟随")
                  .fontSize(12).fontColor('#2563eb').fontWeight(FontWeight.Medium)
              }
              .padding({ left: '3%', right: '3%', top: '1.5%', bottom: '1.5%' })
              .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
              .borderRadius(100)
              .onClick((): void => {
                this.themeManager.setThemeMode(((this.themeManager.themeMode + 1) % 3) as ThemeMode);
              })
            }
            .width('100%').padding({ left: '4%', right: '4%', top: '3.5%', bottom: '3.5%' })
            .constraintSize({ minHeight: 64 })
            .backgroundColor(this.themeManager.colors.cardBackgroundColor)
            Divider().margin({ left: '15%', right: '4%' }).color(this.themeManager.colors.separatorColor)
            Row() {
              Image(this.themeManager.isDarkMode ? $r('app.media.ic_refresh_light') : $r('app.media.ic_refresh_gray'))
                .width(36).height(36).objectFit(ImageFit.Contain)
                .padding(8)
                .backgroundColor(this.themeManager.isDarkMode ? '#334155' : '#f1f5f9')
                .borderRadius(10).margin({ right: '4%' })
              Column() {
                Text("清理缓存").fontSize(15).fontWeight(FontWeight.Medium)
                  .fontColor(this.themeManager.colors.primaryTextColor)
                Text("释放存储空间，优化运行速度").fontSize(12)
                  .fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: '2%' })
              }.alignItems(HorizontalAlign.Start).layoutWeight(1)
              Image($r('app.media.ic_chevron_right')).width(16).height(16).objectFit(ImageFit.Contain)
            }
            .width('100%').padding({ left: '4%', right: '4%', top: '3.5%', bottom: '3.5%' })
            .constraintSize({ minHeight: 64 })
            .backgroundColor(this.themeManager.colors.cardBackgroundColor)
            .onClick((): void => {
              this.mqttManager.clearAllCache();
              promptAction.showToast({ message: "清理完成" });
            })
          }
          .width('92%').backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .borderRadius('4%').clip(true)
          .shadow({ radius: 8, color: '#0000000F', offsetY: 4 })
        }.width('100%')

        Button("退出登录", { type: ButtonType.Capsule })
          .width('80%').height('6%').constraintSize({ minHeight: 48 })
          .margin({ top: '10%', bottom: '6%' })
          .backgroundColor('#fee2e2').fontColor('#ef4444').fontWeight(FontWeight.Medium)
          .onClick((): void => {
            promptAction.showDialog({
              title: '退出确认', message: '您确定要退出当前账号吗？',
              buttons: [{ text: '取消', color: '#64748b' }, { text: '退出', color: '#ef4444' }]
            }).then(data => {
              if (data.index === 1 && this.pathStack) {
                this.pathStack.clear(); this.pathStack.pushPathByName("Login", null);
              }
            })
          })
        Text("Version 2.0.24 (API 20)").fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).margin({ bottom: '10%' })
      }
      .width('100%').alignItems(HorizontalAlign.Center)
    }
    .width('100%').height('100%').backgroundColor(this.themeManager.colors.backgroundColor)
    .scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
  }
}
