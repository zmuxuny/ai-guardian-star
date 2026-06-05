import { common, Want } from '@kit.AbilityKit';
import { preferences } from '@kit.ArkData';
import { STORAGE_KEY_LOGGED_IN_USER } from './Login';
import { CloudSyncService } from '../common/CloudSyncService';
import { CloudService } from '../common/CloudService';
import { DatabaseHelper } from '../database/DatabaseHelper';
import { PREF_NAME_AUTH, PREF_KEY_LAST_USERNAME, PREF_KEY_LAST_NICKNAME, PREF_KEY_PRIVACY_ACCEPTED, PRIVACY_POLICY_URL } from '../config';

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
          Text('数据不会向任何第三方共享或出售。')
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
      .height(200)
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

  /**
   * 数据库已在 EntryAbility.onWindowStageCreate 初始化完毕，
   * 这里只做登录态检测，直接读 Preferences 判断跳转。
   * 跳转 Layout 后后台验证云端账号是否仍然存在。
   */
  private checkAutoLogin(): void {
    try {
      // 启动云端数据预同步（后台异步，不阻塞UI）
      this.startCloudPreSync();

      const ctx = getContext(this) as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME_AUTH };
      const pref = preferences.getPreferencesSync(ctx, options);
      const savedUser = pref.getSync(PREF_KEY_LAST_USERNAME, '') as string;

      if (savedUser !== '') {
        AppStorage.setOrCreate<string>(STORAGE_KEY_LOGGED_IN_USER, savedUser);
        this.pathStack.pushPathByName('Layout', null, false);
        // 后台验证云端账号是否被删除
        this.validateAccountOnCloud(savedUser);
      } else {
        this.pathStack.pushPathByName('Login', null, false);
      }
    } catch (e) {
      console.warn('[Index]: Preferences 读取失败，跳登录页');
      this.pathStack.pushPathByName('Login', null, false);
    }
  }

  /**
   * 后台验证云端账号是否存在。
   * 如果云端返回"账号不存在"→ 清除本地数据，踢回登录页。
   * 网络错误时静默放行（离线可用）。
   */
  private async validateAccountOnCloud(loginId: string): Promise<void> {
    const ctx = getContext(this) as common.UIAbilityContext;
    try {
      const db = DatabaseHelper.getInstance();
      // loginId 可能是手机号/邮箱/用户名，用 identifier 查询
      const user = await db.queryUserByIdentifier(loginId);
      if (!user) {
        return; // 本地无数据，无法验证，放行
      }

      const cloud = CloudService.getInstance();
      const result = await cloud.login(loginId, user.passwordHash);

      if (!result.success && result.message === '账号不存在') {
        console.info('[Index]: 云端账号已被删除，清除本地数据:', loginId);

        // 清除本地数据库（用实际用户名查删）
        const dbUsername = user.username || loginId;
        try {
          await db.deleteUserByUsername(dbUsername);
        } catch (dbErr) {
          console.error('[Index]: 清除本地数据库失败:', dbErr);
        }

        // 清除 Preferences
        try {
          const options: preferences.Options = { name: PREF_NAME_AUTH };
          const pref = preferences.getPreferencesSync(ctx, options);
          pref.deleteSync(PREF_KEY_LAST_USERNAME);
          pref.deleteSync(PREF_KEY_LAST_NICKNAME);
          pref.flushSync();
        } catch (prefErr) {
          console.error('[Index]: 清除 Preferences 失败:', prefErr);
        }

        // 清除 AppStorage
        AppStorage.setOrCreate<string>(STORAGE_KEY_LOGGED_IN_USER, '');

        // 跳转登录页
        this.pathStack.clear();
        this.pathStack.pushPathByName('Login', null, false);
      }
    } catch (e) {
      // 网络错误等，静默放行
      console.info('[Index]: 云端验证失败（网络不可用），允许离线使用');
    }
  }
  
  /**
   * 启动云端数据预同步
   * 后台异步执行，不阻塞UI
   */
  private startCloudPreSync(): void {
    try {
      const cloudSync = CloudSyncService.getInstance();
      // 异步执行，不等待结果
      cloudSync.preSyncOnAppStart().then(() => {
        console.info('[Index]: 云端预同步完成');
      }).catch((e: Error) => {
        console.warn('[Index]: 云端预同步失败:', e.message);
      });
    } catch (e) {
      console.warn('[Index]: 启动云端预同步失败:', e);
    }
  }
}
