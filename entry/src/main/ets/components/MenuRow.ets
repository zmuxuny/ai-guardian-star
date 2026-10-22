/**
 * MenuRow.ets — 通用菜单行组件（图标 + 标题/副标题 + 右箭头）
 */
import { ThemeManager } from '../common/ThemeManager';
import { ICON_FRAME_SIZE, PAGE_HORIZONTAL_GUTTER } from './GradientHeader';

@Component
export struct MenuRow {
  @Prop imgRes: Resource = $r("app.media.ic_user_blue");
  @Prop bgColorLight: string = "#eff6ff";
  @Prop bgColorDark: string = "#1e3a5f";
  @Prop title: string = "";
  @Prop subTitle: string = "";
  onClickAction: () => void = () => {};
  @State pressed: boolean = false;
  @State themeManager: ThemeManager = ThemeManager.getInstance();

  build() {
    Row() {
      Image(this.imgRes)
        .width(ICON_FRAME_SIZE).height(ICON_FRAME_SIZE).objectFit(ImageFit.Contain)
        .padding(10)
        .backgroundColor(this.themeManager.isDarkMode ? this.bgColorDark : this.bgColorLight)
        .borderRadius(12)
        .margin({ right: 14 })
      Column() {
        Text(this.title)
          .fontSize(15).fontWeight(FontWeight.Medium)
          .fontColor(this.themeManager.colors.primaryTextColor)
        Text(this.subTitle)
          .fontSize(12)
          .fontColor(this.themeManager.colors.secondaryTextColor)
          .margin({ top: "2%" })
      }
      .alignItems(HorizontalAlign.Start).layoutWeight(1)
      Image($r("app.media.ic_chevron_right"))
        .width(16).height(16).objectFit(ImageFit.Contain)
    }
    .width("100%")
    .padding({ left: PAGE_HORIZONTAL_GUTTER, right: PAGE_HORIZONTAL_GUTTER, top: 12, bottom: 12 })
    .constraintSize({ minHeight: 64 })
    .backgroundColor(
      this.pressed
        ? this.themeManager.isDarkMode ? "#2a3a50" : "#e8edf5"
        : this.themeManager.colors.cardBackgroundColor
    )
    .animation({ duration: 80, curve: Curve.EaseOut })
    .gesture(TapGesture().onAction(() => { this.onClickAction(); }))
    .onTouch((e: TouchEvent): void => {
      if (e.type === TouchType.Down) {
        this.pressed = true;
      } else if (e.type === TouchType.Up || e.type === TouchType.Cancel) {
        setTimeout(() => { this.pressed = false; }, 150);
      }
    })
  }
}
