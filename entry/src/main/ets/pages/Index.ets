import { common } from '@kit.AbilityKit';
import { preferences } from '@kit.ArkData';
import { STORAGE_KEY_LOGGED_IN_USER } from './Login';
import { CloudSyncService } from '../common/CloudSyncService';
import { PREF_NAME_AUTH, PREF_KEY_LAST_USERNAME } from '../config';

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
   * 同时启动云端数据预同步（后台异步执行）
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
      } else {
        this.pathStack.pushPathByName('Login', null, false);
      }
    } catch (e) {
      console.warn('[Index]: Preferences 读取失败，跳登录页');
      this.pathStack.pushPathByName('Login', null, false);
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
