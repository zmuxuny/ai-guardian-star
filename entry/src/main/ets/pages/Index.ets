import { common, Want } from '@kit.AbilityKit';
import { preferences } from '@kit.ArkData';
import { CloudService } from '../common/CloudService';
import { AiPermissionService } from '../common/AiPermissionService';
import { AvatarSyncService } from '../common/AvatarSyncService';
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
            .fontColor('#1d4ed8')
            .decoration({ type: TextDecorationType.Underline, color: '#1d4ed8' })
            .margin({ top: 4 })
            .onClick(() => {
              const ctx = this.getUIContext().getHostContext() as common.UIAbilityContext;
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
          .fontColor('#475569')
          .borderRadius(10)
          .onClick(() => { this.onDisagree(); })
        Button('同意并继续', { type: ButtonType.Normal })
          .layoutWeight(1)
          .height(44)
          .backgroundColor('#2563eb')
          .fontColor('#ffffff')
          .borderRadius(10)
          .onClick(() => { this.onAgree(); })
      }
      .width('100%')
      .padding({ left: 20, right: 20, top: 16, bottom: 24 })
    }
    .width('90%')
    .constraintSize({ maxWidth: 480 })
    .backgroundColor('#ffffff')
    .borderRadius(16)
  }
}

@Entry
@Component
struct Index {
  pathStack: NavPathStack = new NavPathStack();
  @State showSplash: boolean = true;
  @StorageProp('startupLogoOffsetPx') startupLogoOffsetPx: number = 0;
  private startupStarted: boolean = false;
  private disposed: boolean = false;
  private startupTime: number = 0;
  private splashTimer: number = -1;
  private splashWaitResolve: (() => void) | null = null;

  aboutToDisappear(): void {
    this.disposed = true;
    if (this.splashTimer !== -1) clearTimeout(this.splashTimer);
    this.splashTimer = -1;
    if (this.splashWaitResolve !== null) this.splashWaitResolve();
    this.splashWaitResolve = null;
  }

  /** Keep the cold-start logo readable while session checks run in parallel. */
  private async waitForSplash(): Promise<void> {
    if (!this.showSplash) return;
    const remaining = Math.max(0, 1800 - (Date.now() - this.startupTime));
    if (remaining === 0 || this.disposed) return;
    await new Promise<void>((resolve: () => void): void => {
      this.splashWaitResolve = resolve;
      this.splashTimer = setTimeout((): void => {
        this.splashTimer = -1;
        this.splashWaitResolve = null;
        resolve();
      }, remaining);
    });
  }

  private async openStartupPage(name: string): Promise<void> {
    await this.waitForSplash();
    if (this.disposed) return;
    this.pathStack.pushPathByName(name, null, false);
    this.showSplash = false;
  }

  private async openPrivacyAfterSplash(): Promise<void> {
    await this.waitForSplash();
    if (this.disposed) return;
    this.showSplash = false;
    this.privacyDialogController.open();
  }

  private privacyDialogController: CustomDialogController = new CustomDialogController({
    builder: PrivacyDialog({
      onAgree: () => {
        this.privacyDialogController.close();
        this.savePrivacyAccepted();
        this.checkAutoLogin();
      },
      onDisagree: () => {
        this.privacyDialogController.close();
        const ctx = this.getUIContext().getHostContext() as common.UIAbilityContext;
        ctx.terminateSelf();
      },
    }),
    autoCancel: false,
    alignment: DialogAlignment.Center,
    // customStyle 让弹窗宽度完全由内容决定，否则百分比宽度在平板上会撑成一条空壳
    customStyle: true,
  });

  private savePrivacyAccepted(): void {
    try {
      const ctx = this.getUIContext().getHostContext() as common.UIAbilityContext;
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
      const ctx = this.getUIContext().getHostContext() as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME_AUTH };
      const pref = preferences.getPreferencesSync(ctx, options);
      const accepted = pref.getSync(PREF_KEY_PRIVACY_ACCEPTED, false) as boolean;
      if (!accepted) {
        this.openPrivacyAfterSplash();
        return;
      }
    } catch (e) {
      console.warn('[Index]: 读取隐私协议状态失败', JSON.stringify(e));
    }
    this.checkAutoLogin();
  }

  build() {
    Stack() {
      Navigation(this.pathStack) {
      }
      .hideNavBar(true).width('100%').height('100%')
      if (this.showSplash) {
        Column() {
          // Match the system starting window's 72vp icon without a size/shape jump.
          Image($r('app.media.APPicon')).width(72).height(72)
            .objectFit(ImageFit.Contain)
            .offset({ y: this.getUIContext().px2vp(this.startupLogoOffsetPx) })
            .accessibilityText('智护星正在启动')
        }.width('100%').height('100%').justifyContent(FlexAlign.Center)
          .backgroundColor('#ffffff')
          .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
          .hitTestBehavior(HitTestMode.Block)
          .onAppear(() => {
            if (this.startupStarted) return;
            this.startupStarted = true;
            this.startupTime = Date.now();
            this.checkPrivacyThenLogin();
          })
      }
    }.width('100%').height('100%').backgroundColor('#ffffff')
  }

  /** 内存会话或经 Asset Store 恢复并换新的服务端会话才可进入应用。 */
  private async checkAutoLogin(): Promise<void> {
    const cloud = CloudService.getInstance();
    if (!cloud.hasSession() && !await cloud.restorePersistedSession()) {
      await this.openStartupPage('Login');
      return;
    }

    const result = await cloud.getMe();
    const sessionUserKey = cloud.getSessionUserKey();
    if (!result.success || !result.user || sessionUserKey === '') {
      cloud.clearSession();
      UserManager.getInstance().clearCurrentUsername();
      AppStorage.setOrCreate<string>(STORE_KEY_LOGGED_IN_USER, '');
      await this.openStartupPage('Login');
      return;
    }

    UserManager.getInstance().setCurrentUsername(sessionUserKey);
    AppStorage.setOrCreate<string>(STORE_KEY_LOGGED_IN_USER, sessionUserKey);
    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    await AvatarSyncService.sync(context, sessionUserKey);
    await AiPermissionService.getInstance().sync();
    await this.openStartupPage('Layout');
  }

}
