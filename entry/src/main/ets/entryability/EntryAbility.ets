import { AbilityConstant, Configuration, ConfigurationConstant, UIAbility, Want } from '@kit.AbilityKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { window } from '@kit.ArkUI';
import { ThemeManager } from '../common/ThemeManager';
import { DatabaseHelper } from '../database/DatabaseHelper';

const DOMAIN = 0x0000;

export default class EntryAbility extends UIAbility {
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    try {
      this.context.getApplicationContext().setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_NOT_SET);
    } catch (error) {
      hilog.error(DOMAIN, 'testTag', 'setColorMode failed: %{public}s', JSON.stringify(error));
    }
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onCreate');
    ThemeManager.getInstance().init(this.context);
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'ThemeManager initialized');
  }

  onConfigurationUpdate(newConfig: Configuration): void {
    hilog.info(DOMAIN, 'testTag', 'Configuration updated, colorMode: %{public}d', newConfig.colorMode);
    ThemeManager.getInstance().applyThemeMode();
  }

  onDestroy(): void {
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onDestroy');
    DatabaseHelper.getInstance().close();
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'DatabaseHelper closed');
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onWindowStageCreate');

    // ── 先初始化数据库，完成后再加载页面，保证建表在页面跳转之前完成 ──
    DatabaseHelper.getInstance().init(this.context)
      .then(() => {
        hilog.info(DOMAIN, 'testTag', '%{public}s', 'DatabaseHelper initialized, loading content');
        windowStage.loadContent('pages/Index', (err) => {
          if (err.code) {
            hilog.error(DOMAIN, 'testTag', 'Failed to load content: %{public}s', JSON.stringify(err));
            return;
          }
          hilog.info(DOMAIN, 'testTag', 'Content loaded successfully');
        });
      })
      .catch((e: Error) => {
        hilog.error(DOMAIN, 'testTag', 'DB init failed, loading anyway: %{public}s', e.message);
        // 数据库初始化失败也继续加载页面，不影响 APP 基本功能
        windowStage.loadContent('pages/Index', (err) => {
          if (err.code) {
            hilog.error(DOMAIN, 'testTag', 'Failed to load content: %{public}s', JSON.stringify(err));
          }
        });
      });

    windowStage.getMainWindow().then((win) => {
      const avoidArea = win.getWindowAvoidArea(window.AvoidAreaType.TYPE_SYSTEM);
      const topHeight = px2vp(avoidArea.topRect.height);
      AppStorage.setOrCreate('topSafeHeight', topHeight > 0 ? topHeight : 48);
    }).catch(() => {
      AppStorage.setOrCreate('topSafeHeight', 48);
    });
  }

  onWindowStageDestroy(): void {
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onWindowStageDestroy');
  }

  onForeground(): void {
    hilog.info(DOMAIN, 'testTag', '%{s}', 'Ability onForeground');
    // 切回前台时刷新跟随系统主题（比 onConfigurationUpdate 更可靠）
    ThemeManager.getInstance().refreshFollowSystem();
  }

  onBackground(): void {
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onBackground');
  }
}
