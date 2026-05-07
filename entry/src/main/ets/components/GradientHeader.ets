/**
 * GradientHeader.ets — 共享渐变头部组件
 * 统一管理所有页面的蓝色渐变头部样式，通过 @BuilderParam 接收各页面自定义内容
 */
@Component
export struct GradientHeader {
  @BuilderParam content: () => void;

  build() {
    Column() { this.content() }
      .width('100%')
      .linearGradient({
        direction: GradientDirection.Bottom,
        colors: [['#1e40af', 0.0], ['#3b82f6', 0.5], ['#60a5fa', 1.0]],
      })
      .borderRadius({ bottomLeft: '6%', bottomRight: '6%' })
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
  }
}
