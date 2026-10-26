import { ThemeManager } from '../common/ThemeManager';
import { GradientHeader, PAGE_HORIZONTAL_GUTTER, PAGE_TITLE_SIZE } from '../components/GradientHeader';
import { RecordingBrowser } from '../components/RecordingBrowser';

@Component
export struct record {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;

  @Builder
  GradientHeader(): void {
    GradientHeader({ useHomeStyle: true }) {
      Row() {
        Column() {
          Text('历史记录').fontSize(PAGE_TITLE_SIZE).fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.colors.primaryTextColor)
          Text('异常类型、时间与按需下载').fontSize(13)
            .fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: 4 })
        }.alignItems(HorizontalAlign.Start)
        Blank()

      }
      .width('100%').padding({ left: PAGE_HORIZONTAL_GUTTER, right: PAGE_HORIZONTAL_GUTTER, top: 16, bottom: 22 })
    }
  }


  build() {
    Column() {
      this.GradientHeader()
      RecordingBrowser().layoutWeight(1)
    }.width('100%').height('100%').backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
  }
}
