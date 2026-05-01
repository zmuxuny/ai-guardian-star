/**
 * StatDashboard.ets — 个人中心统计数据展示（已监护天数 + 预警次数）
 */
import { ThemeManager } from '../common/ThemeManager';

@Component
export struct StatDashboard {
  @Prop useDays: number = 0;
  @Prop totalAlertCount: number = 0;
  @State themeManager: ThemeManager = ThemeManager.getInstance();

  build() {
    Row() {
      Column() {
        Text(`${this.useDays}`)
          .fontSize(28).fontWeight(FontWeight.Bold).fontColor("#1e40af")
        Text("天·已监护")
          .fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor)
          .margin({ top: 6 })
      }.layoutWeight(1)
      Column()
        .width(1).height(36)
        .backgroundColor(this.themeManager.colors.separatorColor)
      Column() {
        Text(`${this.totalAlertCount}`)
          .fontSize(28).fontWeight(FontWeight.Bold).fontColor("#1e40af")
        Text("次·已预警")
          .fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor)
          .margin({ top: 6 })
      }.layoutWeight(1)
    }
    .width("88%")
    .padding({ top: 20, bottom: 20 })
    .margin({ top: -36 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .borderRadius("4%")
    .shadow({ radius: 12, color: "#1A3b82f6", offsetY: 6 })
  }
}
