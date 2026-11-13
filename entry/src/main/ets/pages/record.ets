import { CareStatusBadge } from '../components/CareStatusBadge';
import { ThemeManager } from '../common/ThemeManager';
import { GradientHeader, PAGE_HORIZONTAL_GUTTER } from '../components/GradientHeader';
import { RecordingBrowser } from '../components/RecordingBrowser';

@Component
export struct record {
  onOpenHome: () => void = () => {};
  @Prop bottomInset: number = 0;
  onTabScroll: (delta: number, state: ScrollState) => void = () => {};
  @State themeManager: ThemeManager = ThemeManager.getInstance();

  // 不放页面标题：顶部是存储说明和状态胶囊，随列表滑走；下面的筛选条由 RecordingBrowser 固定在顶部
  @Builder
  GradientHeader(): void {
    GradientHeader({ useHomeStyle: true, contentMaxWidth: 880 }) {
      Row({ space: 10 }) {
        Text('录像在家中设备上保存 7 天，在线播放不占手机空间').fontSize(13)
          .fontColor(this.themeManager.colors.secondaryTextColor).layoutWeight(1)
        CareStatusBadge({ onOpenHome: this.onOpenHome })
      }
      .width('100%').padding({ left: PAGE_HORIZONTAL_GUTTER, right: PAGE_HORIZONTAL_GUTTER, top: 12, bottom: 4 })
    }
  }

  build() {
    Column() {
      // 外面套一层限宽：直接给 RecordingBrowser 加 maxWidth 时内部 width('100%') 仍按整屏算，会右移溢出
      Column() {
        RecordingBrowser({ bottomInset: this.bottomInset, onTabScroll: this.onTabScroll }) {
          this.GradientHeader()
        }
      }.width('100%').height('100%').constraintSize({ maxWidth: 880 })
    }.width('100%').height('100%')
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
  }
}
