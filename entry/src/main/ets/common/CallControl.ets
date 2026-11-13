import { abilityAccessCtrl, common } from '@kit.AbilityKit';
import { AudioTransferManager } from './AudioTransferManager';
import { MqttManager } from '../pages/MqttManager';
import { showToast } from './UiFeedback';

/**
 * 首页和全屏画面共用的通话开关：通话中则挂断，否则检查设备在线和麦克风权限后发起。
 * alive 返回 false 表示发起页面已离开，连上后立即挂断，避免后台留着通话。
 * 结果以 AudioTransferManager.isCallActive() 为准，调用方结束后自行读取。
 */
export async function toggleDeviceCall(ui: UIContext, alive: () => boolean): Promise<void> {
  const audio = AudioTransferManager.getInstance();
  try {
    if (audio.isCallActive()) {
      await audio.stopCall();
      return;
    }
    if (!MqttManager.getInstance().deviceOnline) {
      showToast(ui, { message: '设备未连接，无法发起通话' });
      return;
    }
    const context = ui.getHostContext() as common.UIAbilityContext;
    const permission = await abilityAccessCtrl.createAtManager()
      .requestPermissionsFromUser(context, ['ohos.permission.MICROPHONE']);
    if (!alive()) return;
    if (permission.authResults[0] !== 0) {
      showToast(ui, { message: '需要麦克风权限才能通话' });
      return;
    }
    await audio.startCall();
    if (!alive()) await audio.stopCall();
  } catch (_) {
    if (alive()) showToast(ui, { message: '通话连接失败，请稍后重试' });
  }
}
