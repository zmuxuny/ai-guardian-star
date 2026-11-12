import { CareStatusBadge } from '../components/CareStatusBadge';
import { ThemeManager } from '../common/ThemeManager';
import { GradientHeader, PAGE_HORIZONTAL_GUTTER, PAGE_TITLE_SIZE } from '../components/GradientHeader';
import { RecordingBrowser } from '../components/RecordingBrowser';

@Component
export struct record {
  onOpenHome: () => void = () => {};
  @Prop bottomInset: number = 0;
  onTabScroll: (delta: number, state: ScrollState) => void = () => {};
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;

  @Builder
  GradientHeader(): void {
    GradientHeader({ useHomeStyle: true }) {
      Row() {
        Text('记录').fontSize(PAGE_TITLE_SIZE).fontWeight(FontWeight.Bold)
          .fontColor(this.themeManager.colors.primaryTextColor)
        Blank()
        CareStatusBadge({ onOpenHome: this.onOpenHome })
      }
      .width('100%').padding({ left: PAGE_HORIZONTAL_GUTTER, right: PAGE_HORIZONTAL_GUTTER, top: 16 })
      Text('录像在家中设备上保存 7 天，在线播放不占手机空间').fontSize(13)
        .fontColor(this.themeManager.colors.secondaryTextColor).width('100%')
        .padding({ left: PAGE_HORIZONTAL_GUTTER, right: PAGE_HORIZONTAL_GUTTER, top: 6, bottom: 4 })
    }
  }


  build() {
    Column() {
      this.GradientHeader()
      RecordingBrowser({ bottomInset: this.bottomInset, onTabScroll: this.onTabScroll }).layoutWeight(1)
    }.width('100%').height('100%').backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
  }
}
