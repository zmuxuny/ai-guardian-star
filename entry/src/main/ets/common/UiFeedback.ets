import { promptAction, UIContext } from '@kit.ArkUI';
import { accessibility } from '@kit.AccessibilityKit';
import { vibrator } from '@kit.SensorServiceKit';

export function showToast(uiContext: UIContext, options: promptAction.ShowToastOptions): void {
  try {
    uiContext.getPromptAction().showToast(options);
  } catch (error) {
    console.error(`[UiFeedback] showToast failed: ${JSON.stringify(error)}`);
  }
}

export async function showDialog(
  uiContext: UIContext,
  options: promptAction.ShowDialogOptions,
): Promise<promptAction.ShowDialogSuccessResponse | undefined> {
  try {
    return await uiContext.getPromptAction().showDialog(options);
  } catch (error) {
    console.error(`[UiFeedback] showDialog failed: ${JSON.stringify(error)}`);
    return undefined;
  }
}

let softHapticSupported: boolean | undefined;

export function reduceMotion(): boolean {
  try {
    return accessibility.isAnimationReduceEnabledSync();
  } catch (_error) {
    return false;
  }
}

export function softTap(): void {
  try {
    if (softHapticSupported === undefined) {
      softHapticSupported = vibrator.isSupportEffectSync('haptic.effect.soft');
    }
    if (softHapticSupported) {
      vibrator.startVibration({ type: 'preset', effectId: 'haptic.effect.soft', count: 1 },
        { usage: 'touch' }).catch((): void => {});
    }
  } catch (_error) {
    softHapticSupported = false;
  }
}
