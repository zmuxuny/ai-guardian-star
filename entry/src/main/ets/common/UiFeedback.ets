import { promptAction, UIContext } from '@kit.ArkUI';

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
