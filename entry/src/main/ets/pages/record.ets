import { MqttManager, FallRecord, SedentaryRecord } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';

@Component
export struct record {
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State currentTab: number = 0;
  @State fallRecords: FallRecord[] = [];
  @State sedentaryRecords: SedentaryRecord[] = [];
  // 刷新按钮缩放动画
  @State refreshBtnScale: number = 1.0;
  // 顶部安全高度
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;

  aboutToAppear(): void { this.refreshData(); }
  private refreshData(): void {
    if (this.mqttManager) {
      this.fallRecords = [...this.mqttManager.fallRecords];
      this.sedentaryRecords = [...this.mqttManager.sedentaryRecords];
    }
  }

  @Builder
  GradientHeader(): void {
    Row() {
      Text('事件追踪').fontSize(26).fontWeight(FontWeight.Bold).fontColor('#ffffff')
      Blank()
      Image($r('app.media.ic_refresh_white'))
        .width(36).height(36).objectFit(ImageFit.Contain).padding(9)
        .backgroundColor('#33FFFFFF').borderRadius(100)
        .scale({ x: this.refreshBtnScale, y: this.refreshBtnScale })
        .animation({ duration: 150, curve: Curve.EaseInOut })
        .onClick((): void => {
          this.refreshBtnScale = 0.8;
          setTimeout(() => { this.refreshBtnScale = 1.0; }, 150);
          this.refreshData();
        })
    }
    // top 与主页统一：状态栏高度 + 16；bottom 加大让渐变区域更饱满
    .width('100%').padding({ left: '6%', right: '6%', top: this.topSafeHeight + 16, bottom: 34 })
    .linearGradient({ direction: GradientDirection.Bottom,
      colors: [['#1e40af', 0.0], ['#3b82f6', 0.5], ['#60a5fa', 1.0]] })
    .borderRadius({ bottomLeft: '6%', bottomRight: '6%' })
  }


  @Builder
  StatDashboard(): void {
    Row() {
      Column() {
        Text('累计摔倒').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
        Text(`${this.mqttManager.fallRecords.length}`)
          .fontSize(28).fontWeight(FontWeight.Bold).margin({ top: 8 }).fontColor('#ef4444')
      }
      .layoutWeight(1).padding({ top: 20, bottom: 20 })
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .borderRadius({ topLeft: '4%', bottomLeft: '4%' })

      // 竖向分隔线，居中显示
      Column()
        .width(1).height(44)
        .backgroundColor(this.themeManager.colors.separatorColor)

      Column() {
        Text('累计久坐').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
        Text(`${this.mqttManager.sedentaryRecords.length}`)
          .fontSize(28).fontWeight(FontWeight.Bold).margin({ top: 8 }).fontColor('#ef4444')
      }
      .layoutWeight(1).padding({ top: 20, bottom: 20 })
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .borderRadius({ topRight: '4%', bottomRight: '4%' })
    }
    .width('92%').margin({ top: '-4%' })
    .shadow({ radius: 12, color: '#1A3b82f6', offsetY: 6 })
    .borderRadius('4%').clip(true)
    .alignItems(VerticalAlign.Center)
  }

  @Builder
  EmptyState(title: string, subTitle: string): void {
    Column() {
      Image($r('app.media.ic_shield_blue'))
        .width(100).height(100).objectFit(ImageFit.Contain).padding(22)
        .linearGradient({ direction: GradientDirection.Bottom,
          colors: [['#dbeafe', 0.0], ['#eff6ff', 1.0]] })
        .borderRadius(32).margin({ bottom: 28 })
      Text(title).fontSize(22).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
      Text(subTitle).fontSize(15).fontColor(this.themeManager.colors.secondaryTextColor)
        .margin({ top: 12 }).textAlign(TextAlign.Center).lineHeight(24)
    }
    .width('100%').margin({ top: '18%' }).padding({ left: '12%', right: '12%' })
  }

  @Builder
  RecordItem(title: string, date: string, time: string, isDanger: boolean): void {
    Row() {
      Image(isDanger ? $r('app.media.ic_alert_red') : $r('app.media.ic_list_blue'))
        .width(36).height(36).objectFit(ImageFit.Contain).padding(8)
        .backgroundColor(isDanger
          ? (this.themeManager.isDarkMode ? '#2d1515' : '#fff1f2')
          : (this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff'))
        .borderRadius(10).margin({ right: '4%' })
      Column() {
        Text(title).fontSize(15).fontWeight(FontWeight.Medium)
          .fontColor(this.themeManager.colors.primaryTextColor)
        Row() {
          Text(date).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
          Text(time).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).margin({ left: '3%' })
        }.margin({ top: '1.5%' })
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
      Image($r('app.media.ic_chevron_right')).width(16).height(16).objectFit(ImageFit.Contain)
    }
    .width('100%').padding({ left: '4%', right: '4%', top: '3.5%', bottom: '3.5%' })
    .margin({ bottom: '3%' }).borderRadius('4%')
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .shadow({ radius: 8, color: '#0000000F', offsetY: 4 })
  }


  build() {
    Column() {
      this.GradientHeader()
      this.StatDashboard()

      Row() {
        Text('摔倒记录').fontSize(15)
          .fontWeight(this.currentTab === 0 ? FontWeight.Bold : FontWeight.Normal)
          .fontColor(this.currentTab === 0 ? '#2563eb' : this.themeManager.colors.secondaryTextColor)
          .layoutWeight(1).textAlign(TextAlign.Center).padding({ bottom: '3%' })
          .border({ width: { bottom: this.currentTab === 0 ? 3 : 0 }, color: '#2563eb' })
          .onClick((): void => { this.currentTab = 0 })
        Text('久坐记录').fontSize(15)
          .fontWeight(this.currentTab === 1 ? FontWeight.Bold : FontWeight.Normal)
          .fontColor(this.currentTab === 1 ? '#2563eb' : this.themeManager.colors.secondaryTextColor)
          .layoutWeight(1).textAlign(TextAlign.Center).padding({ bottom: '3%' })
          .border({ width: { bottom: this.currentTab === 1 ? 3 : 0 }, color: '#2563eb' })
          .onClick((): void => { this.currentTab = 1 })
      }
      .width('100%').padding({ left: '8%', right: '8%', top: '5%', bottom: 0 })

      List({ space: 0 }) {
        if (this.currentTab === 0) {
          if (this.mqttManager.fallRecords.length === 0) {
            ListItem() { this.EmptyState('暂无摔倒告警', '一切正常，老人安全受到监护') }
          } else {
            ForEach(this.mqttManager.fallRecords, (item: FallRecord): void => {
              ListItem() { this.RecordItem('疑似跌倒警报', item.date, item.time, true) }
            })
          }
        } else {
          if (this.mqttManager.sedentaryRecords.length === 0) {
            ListItem() { this.EmptyState('健康状态良好', '近日未检测到长时间久坐行为') }
          } else {
            ForEach(this.mqttManager.sedentaryRecords, (item: SedentaryRecord): void => {
              ListItem() { this.RecordItem('久坐超时提醒', item.date, item.time, false) }
            })
          }
        }
      }
      .layoutWeight(1).width('92%').padding({ top: '3%' })
      .edgeEffect(EdgeEffect.Spring).scrollBar(BarState.Off)
    }
    .width('100%').height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .alignItems(HorizontalAlign.Center)
  }
}
