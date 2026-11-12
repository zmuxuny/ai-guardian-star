/**
 * GradientHeader.ets — 共享渐变头部组件
 * 阅读页的状态光带，通过 @BuilderParam 接收各页面自定义内容
 *
 * 渐变背景铺满整个宽度，内部内容限宽居中，保证大屏上标题与正文内容列左右对齐。
 * 圆角用 vp 定值：百分比圆角在平板上会被放大到七八十 vp。
 */
import { carePalette } from '../common/CarePalette';
import { MqttManager } from '../pages/MqttManager';
import { ThemeManager } from '../common/ThemeManager';

export const PAGE_HORIZONTAL_GUTTER: number = 20;
export const PAGE_TITLE_SIZE: number = 24;
export const PAGE_TITLE_ROW_HEIGHT: number = 44;
export const ICON_FRAME_SIZE: number = 40;
export const SURFACE_RADIUS: number = 16;
export const SURFACE_PADDING: number = 16;

@Component
export struct GradientHeader {
  @BuilderParam content: () => void;
  @Prop useHomeStyle: boolean = false;
  @State mqtt: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
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
        colors: [
          [this.themeManager.isDarkMode ? this.themeManager.colors.cardBackgroundColor
            : carePalette(this.mqtt.isFallDetected, this.mqtt.isSedentaryDetected, this.mqtt.deviceOnline).wash, 0],
          [this.themeManager.colors.backgroundColor, 1],
        ],
      })
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
  }
}
