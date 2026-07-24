import { common, Want } from '@kit.AbilityKit';
import { preferences } from '@kit.ArkData';
import { CloudService } from '../common/CloudService';
import { UserManager } from '../common/UserManager';
import { DatabaseHelper } from '../database/DatabaseHelper';
import { STORE_KEY_LOGGED_IN_USER, STORE_KEY_AI_ENABLED, STORE_KEY_AI_ACCESS_LEVEL, PREF_NAME_AUTH, PREF_KEY_PRIVACY_ACCEPTED, PRIVACY_POLICY_URL } from '../config';

@CustomDialog
struct PrivacyDialog {
  controller: CustomDialogController;
  onAgree: () => void = () => {};
  onDisagree: () => void = () => {};

  build() {
    Column({ space: 0 }) {
      Text('隐私政策与用户协议')
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor('#1e293b')
        .margin({ top: 24, bottom: 16 })
        .textAlign(TextAlign.Center)
        .width('100%')

      Scroll() {
        Column({ space: 8 }) {
          Text('智护星（Guardian Star）非常重视您的隐私保护。使用本应用前，请阅读以下说明：')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
          Text('• 账号信息（手机号 / 邮箱）：用于身份识别和跨设备登录')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
          Text('• 健康监测数据（摔倒 / 久坐事件）：存储于本机及您的云端账号，仅用于监护服务')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
          Text('• 摄像头（人脸录入，可选）：照片仅上传至您自己的开发板，不经过第三方服务器')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
          Text('• AI 健康助手：为回答您的提问，会将健康统计摘要（如近7天摔倒次数、久坐告警次数等聚合数据，不含姓名、人脸、位置等身份信息）发送至第三方智能对话服务（扣子 Coze，底层为豆包大模型）以生成回复')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
          Text('除上述 AI 问答场景外，数据不会向其他第三方共享或出售。')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
            .margin({ top: 4 })
          Text('查看完整隐私政策 →')
            .fontSize(13)
            .fontColor('#3b82f6')
            .decoration({ type: TextDecorationType.Underline, color: '#3b82f6' })
            .margin({ top: 4 })
            .onClick(() => {
              const ctx = getContext(this) as common.UIAbilityContext;
              const want: Want = {
                action: 'ohos.want.action.viewData',
                entities: ['entity.system.browsable'],
                uri: PRIVACY_POLICY_URL,
              };
              ctx.startAbility(want).catch((e: Error) => {
                console.warn('[PrivacyDialog]: 打开隐私政策链接失败', e.message);
              });
            })
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)
      }
      .height(260)
      .width('100%')
      .padding({ left: 20, right: 20 })

      Row({ space: 12 }) {
        Button('不同意', { type: ButtonType.Normal })
          .layoutWeight(1)
          .height(44)
          .backgroundColor('#f1f5f9')
          .fontColor('#64748b')
          .borderRadius(10)
          .onClick(() => { this.onDisagree(); })
        Button('同意并继续', { type: ButtonType.Normal })
          .layoutWeight(1)
          .height(44)
          .backgroundColor('#3b82f6')
          .fontColor('#ffffff')
          .borderRadius(10)
          .onClick(() => { this.onAgree(); })
      }
      .width('100%')
      .padding({ left: 20, right: 20, top: 16, bottom: 24 })
    }
    .width('100%')
    .backgroundColor('#ffffff')
    .borderRadius(16)
  }
}

@Entry
@Component
struct Index {
  pathStack: NavPathStack = new NavPathStack();

  private privacyDialogController: CustomDialogController = new CustomDialogController({
    builder: PrivacyDialog({
      onAgree: () => {
        this.privacyDialogController.close();
        this.savePrivacyAccepted();
        this.checkAutoLogin();
      },
      onDisagree: () => {
        this.privacyDialogController.close();
        const ctx = getContext(this) as common.UIAbilityContext;
        ctx.terminateSelf();
      },
    }),
    autoCancel: false,
    alignment: DialogAlignment.Center,
    customStyle: false,
    cornerRadius: 16,
    width: '88%',
  });

  private savePrivacyAccepted(): void {
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME_AUTH };
      const pref = preferences.getPreferencesSync(ctx, options);
      pref.putSync(PREF_KEY_PRIVACY_ACCEPTED, true);
      pref.flushSync();
    } catch (e) {
      console.warn('[Index]: 保存隐私协议状态失败', JSON.stringify(e));
    }
  }

  private checkPrivacyThenLogin(): void {
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME_AUTH };
      const pref = preferences.getPreferencesSync(ctx, options);
      const accepted = pref.getSync(PREF_KEY_PRIVACY_ACCEPTED, false) as boolean;
      if (!accepted) {
        this.privacyDialogController.open();
        return;
      }
    } catch (e) {
      console.warn('[Index]: 读取隐私协议状态失败', JSON.stringify(e));
    }
    this.checkAutoLogin();
  }

  build() {
    Navigation(this.pathStack) {
    }.onAppear(() => {
      this.checkPrivacyThenLogin();
    })
    .hideNavBar(true)
  }

  /** 内存会话或经 Asset Store 恢复并换新的服务端会话才可进入应用。 */
  private async checkAutoLogin(): Promise<void> {
    const cloud = CloudService.getInstance();
    if (!cloud.hasSession() && !await cloud.restorePersistedSession()) {
      this.pathStack.pushPathByName('Login', null, false);
      return;
    }

    const result = await cloud.getMe();
    const sessionUserKey = cloud.getSessionUserKey();
    if (!result.success || !result.user || sessionUserKey === '') {
      cloud.clearSession();
      UserManager.getInstance().clearCurrentUsername();
      AppStorage.setOrCreate<string>(STORE_KEY_LOGGED_IN_USER, '');
      this.pathStack.pushPathByName('Login', null, false);
      return;
    }

    UserManager.getInstance().setCurrentUsername(sessionUserKey);
    AppStorage.setOrCreate<string>(STORE_KEY_LOGGED_IN_USER, sessionUserKey);
    const aiEnabled = await DatabaseHelper.getInstance().loadSetting(sessionUserKey, STORE_KEY_AI_ENABLED);
    const savedAccessLevel = await DatabaseHelper.getInstance().loadSetting(sessionUserKey, STORE_KEY_AI_ACCESS_LEVEL);
    const aiAccessLevel = savedAccessLevel === 'full' || savedAccessLevel === 'basic'
      ? savedAccessLevel : 'privacy';
    AppStorage.setOrCreate<boolean>(STORE_KEY_AI_ENABLED, aiEnabled !== 'false');
    AppStorage.setOrCreate<string>(STORE_KEY_AI_ACCESS_LEVEL, aiAccessLevel);
    this.pathStack.pushPathByName('Layout', null, false);
  }

}
