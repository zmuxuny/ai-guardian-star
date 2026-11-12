import { MqttManager } from '../pages/MqttManager';
import { ThemeManager } from '../common/ThemeManager';
import { CarePalette, carePalette } from '../common/CarePalette';

@Component
export struct CareStatusBadge {
  @State mqtt: MqttManager = MqttManager.getInstance();
  @State theme: ThemeManager = ThemeManager.getInstance();
  onOpenHome: () => void = () => {};

  private palette(): CarePalette {
    return carePalette(this.mqtt.isFallDetected, this.mqtt.isSedentaryDetected, this.mqtt.deviceOnline);
  }

  build() {
    Button({ type: ButtonType.Capsule }) {
      Row({ space: 5 }) {
        Circle().width(6).height(6)
          .fill(this.mqtt.isFallDetected || this.theme.isDarkMode ? this.palette().accent : this.palette().solid)
        Text(this.palette().label).fontSize(11).fontWeight(FontWeight.Medium).maxLines(1)
          .fontColor(this.mqtt.isFallDetected || this.theme.isDarkMode ? '#FFFFFF' : this.palette().solid)
      }
    }
    .height(44).padding({ left: 10, right: 10 })
    .backgroundColor(this.mqtt.isFallDetected || this.theme.isDarkMode ? this.palette().solid : this.palette().wash)
    .accessibilityText(this.palette().label + '，返回主页')
    .onClick((): void => { this.onOpenHome(); })
  }
}
