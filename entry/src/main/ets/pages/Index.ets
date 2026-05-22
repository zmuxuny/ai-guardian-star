import { common } from '@kit.AbilityKit';
import { preferences } from '@kit.ArkData';
import { STORAGE_KEY_LOGGED_IN_USER } from './Login';
import { CloudSyncService } from '../common/CloudSyncService';
import { CloudService } from '../common/CloudService';
import { DatabaseHelper } from '../database/DatabaseHelper';
import { PREF_NAME_AUTH, PREF_KEY_LAST_USERNAME, PREF_KEY_LAST_NICKNAME } from '../config';

@Entry
@Component
struct Index {
  pathStack: NavPathStack = new NavPathStack();

  build() {
    Navigation(this.pathStack) {
    }.onAppear(() => {
      this.checkAutoLogin();
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
