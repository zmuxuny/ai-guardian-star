/**
 * GradientHeader.ets — 共享页头组件
 * 通过 @BuilderParam 接收各页面自定义内容。
 *
 * 页头放在页面的滚动内容里、随内容一起滑走；所在的 Scroll/List 加 expandSafeArea TOP 铺进状态栏。
 * 系统仍会给滚动内容的起点留出状态栏高度（实测），所以这里不再自己加顶部空隙；滑动时内容从状态栏下面穿过。
 * 内部内容限宽居中，保证大屏上页头与正文内容列左右对齐。
 * 圆角用 vp 定值：百分比圆角在平板上会被放大到七八十 vp。
 */

export const PAGE_HORIZONTAL_GUTTER: number = 20;
export const PAGE_TITLE_SIZE: number = 30;
export const PAGE_TITLE_ROW_HEIGHT: number = 44;
export const ICON_FRAME_SIZE: number = 40;
export const SURFACE_RADIUS: number = 16;
export const SURFACE_PADDING: number = 16;

@Component
export struct GradientHeader {
  @BuilderParam content: () => void;
  @Prop useHomeStyle: boolean = false;
  /** 头部内容的最大宽度，需与所在页面正文内容列保持一致 */
  @Prop contentMaxWidth: number = 640;

  build() {
    Column() {
      Column() { this.content() }
        .width('100%')
        .constraintSize({ maxWidth: this.contentMaxWidth })
    }
      .width('100%')
  }
}
