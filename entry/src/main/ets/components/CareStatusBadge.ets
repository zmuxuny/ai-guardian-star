import { MqttManager } from '../pages/MqttManager';
import { ThemeManager } from '../common/ThemeManager';
import { CarePalette, carePalette } from '../common/CarePalette';

/** 阅读页标题右侧的状态胶囊（样张 .stc），点了回主页；跌倒时变实色 */
@Component
export struct CareStatusBadge {
  @State mqtt: MqttManager = MqttManager.getInstance();
  @State theme: ThemeManager = ThemeManager.getInstance();
  onOpenHome: () => void = () => {};

  private palette(): CarePalette {
    return carePalette(this.mqtt.isFallDetected, this.mqtt.isSedentaryDetected, this.mqtt.deviceOnline);
  }

  private solidChip(): boolean {
    return this.mqtt.isFallDetected || this.theme.isDarkMode;
  }

  build() {
    Button({ type: ButtonType.Capsule }) {
      Row({ space: 7 }) {
        Circle().width(8).height(8)
          .fill(this.solidChip() ? '#FFFFFF' : this.palette().tone)
        Text(this.palette().label).fontSize(13).fontWeight(FontWeight.Medium).maxLines(1)
          .fontColor(this.solidChip() ? '#FFFFFF' : this.palette().solid)
      }
    }
    .height(32).padding({ left: 10, right: 12 })
    .backgroundColor(this.solidChip() ? this.palette().solid : '#29' + this.palette().tone.substring(1))
    .responseRegion({ x: 0, y: -6, width: '100%', height: 44 })
    .accessibilityText(this.palette().label + '，返回主页')
    .onClick((): void => { this.onOpenHome(); })
  }
}
