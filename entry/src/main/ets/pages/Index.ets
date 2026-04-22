import { common } from '@kit.AbilityKit';
import { preferences } from '@kit.ArkData';
import { STORAGE_KEY_LOGGED_IN_USER } from './Login';

const PREF_NAME = 'guardian_auth';
const PREF_KEY_USERNAME = 'lastUsername';

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
   */
  private checkAutoLogin(): void {
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME };
      const pref = preferences.getPreferencesSync(ctx, options);
      const savedUser = pref.getSync(PREF_KEY_USERNAME, '') as string;
      const savedNickname = pref.getSync('lastNickname', '') as string;

      if (savedUser !== '') {
        // 同时恢复 username 和 nickname 到内存，个人页不会显示空白
        AppStorage.setOrCreate<string>(STORAGE_KEY_LOGGED_IN_USER, savedUser);
        AppStorage.setOrCreate<string>('loggedInNickname', savedNickname || savedUser);
        console.info('[Index]: 自动登录 ' + savedUser + ' / ' + (savedNickname || savedUser));
        this.pathStack.pushPathByName('Layout', null, false);
      } else {
        this.pathStack.pushPathByName('Login', null, false);
      }
    } catch (e) {
      console.warn('[Index]: Preferences 读取失败，跳登录页');
      this.pathStack.pushPathByName('Login', null, false);
    }
  }
}
