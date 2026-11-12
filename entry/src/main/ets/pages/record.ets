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

  // 不放页面标题：顶部是存储说明和状态胶囊，下面直接是筛选
  @Builder
  GradientHeader(): void {
    GradientHeader({ useHomeStyle: true }) {
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
      this.GradientHeader()
      RecordingBrowser({ bottomInset: this.bottomInset, onTabScroll: this.onTabScroll }).layoutWeight(1)
    }.width('100%').height('100%').backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
  }
}
