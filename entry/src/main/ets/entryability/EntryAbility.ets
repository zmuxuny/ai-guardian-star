import { AbilityConstant, Configuration, ConfigurationConstant, UIAbility, Want } from '@kit.AbilityKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { window } from '@kit.ArkUI';
import { ThemeManager } from '../common/ThemeManager';

const DOMAIN = 0x0000;

export default class EntryAbility extends UIAbility {
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    try {
      this.context.getApplicationContext().setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_NOT_SET);
    } catch (error) {
      hilog.error(DOMAIN, 'testTag', 'setColorMode failed: %{public}s', JSON.stringify(error));
    }
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onCreate');
    
    // 初始化主题管理器
    ThemeManager.getInstance().init(this.context);
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'ThemeManager initialized');
  }
  
  // 监听配置变化（包括系统主题变化）
  onConfigurationUpdate(newConfig: Configuration): void {
    hilog.info(DOMAIN, 'testTag', 'Configuration updated, colorMode: %{public}d', newConfig.colorMode);
    
    const themeManager = ThemeManager.getInstance();
    // 如果是跟随系统模式，则重新应用主题
    themeManager.applyThemeMode();
    hilog.info(DOMAIN, 'testTag', 'Theme mode reapplied');
  }

  onDestroy(): void {
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onDestroy');
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onWindowStageCreate');

    windowStage.loadContent('pages/Index', (err) => {
      if (err.code) {
        hilog.error(DOMAIN, 'testTag', 'Failed to load the content. Cause: %{public}s', JSON.stringify(err));
        return;
      }
      hilog.info(DOMAIN, 'testTag', 'Succeeded in loading the content.');
    });

    // 获取状态栏实际高度存入 AppStorage，供各页面 Header 动态适配
    windowStage.getMainWindow().then((win) => {
      const avoidArea = win.getWindowAvoidArea(window.AvoidAreaType.TYPE_SYSTEM);
      const topHeight = px2vp(avoidArea.topRect.height);
      AppStorage.setOrCreate('topSafeHeight', topHeight > 0 ? topHeight : 48);
      hilog.info(DOMAIN, 'testTag', 'topSafeHeight: %{public}d', topHeight);
    }).catch(() => {
      AppStorage.setOrCreate('topSafeHeight', 48);
    });
  }

  onWindowStageDestroy(): void {
    // Main window is destroyed, release UI related resources
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onWindowStageDestroy');
  }

  onForeground(): void {
    // Ability has brought to foreground
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onForeground');
  }

  onBackground(): void {
    // Ability has back to background
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onBackground');
  }
}