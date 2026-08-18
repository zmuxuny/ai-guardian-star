/**
 * GradientHeader.ets — 共享渐变头部组件
 * 统一管理所有页面的蓝色渐变头部样式，通过 @BuilderParam 接收各页面自定义内容
 *
 * 渐变背景铺满整个宽度，内部内容限宽居中，保证大屏上标题与正文内容列左右对齐。
 * 圆角用 vp 定值：百分比圆角在平板上会被放大到七八十 vp。
 */
@Component
export struct GradientHeader {
  @BuilderParam content: () => void;
  /** 头部内容的最大宽度，需与所在页面正文内容列保持一致 */
  @Prop contentMaxWidth: number = 640;

  build() {
    Column() {
      Column() { this.content() }
        .width('100%')
        .constraintSize({ maxWidth: this.contentMaxWidth })
    }
      .width('100%')
      .linearGradient({
        direction: GradientDirection.Bottom,
        colors: [['#1e3a8a', 0.0], ['#1d4ed8', 0.5], ['#2563eb', 1.0]],
      })
      .borderRadius({ bottomLeft: 24, bottomRight: 24 })
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
  }
}
