import preferences from '@ohos.data.preferences';
import { window } from '@kit.ArkUI';
import { ConfigurationConstant } from '@kit.AbilityKit';

// 主题颜色定义
export class ThemeColors {
  // 背景色
  backgroundColor: string = '#F0F4FF';
  secondaryBackgroundColor: string = '#F2F2F7';
  cardBackgroundColor: string = '#FFFFFF';
  
  // 文字色
  primaryTextColor: string = '#1C1C1E';
  secondaryTextColor: string = '#94A3B8';
  tertiaryTextColor: string = '#C7C7CC';
  
  // 分割线色
  separatorColor: string = '#E5E5EA';
  
  // 按钮色
  primaryButtonColor: string = '#2563EB';
  dangerButtonColor: string = '#FF3B30';
  
  // 卡片边框色
  borderColor: string = '#E5E5EA';
}

// 深色主题
export class DarkThemeColors extends ThemeColors {
  backgroundColor: string = '#0F172A';
  secondaryBackgroundColor: string = '#1E293B';
  cardBackgroundColor: string = '#1E293B';
  
  primaryTextColor: string = '#F8FAFC';
  secondaryTextColor: string = '#94A3B8';
  tertiaryTextColor: string = '#64748B';
  
  separatorColor: string = '#334155';
  
  primaryButtonColor: string = '#3B82F6';
  dangerButtonColor: string = '#EF4444';
  
  borderColor: string = '#334155';
}

// 浅色主题
export class LightThemeColors extends ThemeColors {
  // 使用默认值
}

// 主题模式枚举
export enum ThemeMode {
  FOLLOW_SYSTEM = 0,  // 跟随系统
  LIGHT = 1,          // 浅色
  DARK = 2            // 深色
}

// 主题管理器（单例模式）
@Observed
export class ThemeManager {
  private static instance: ThemeManager;
  private context: Context | null = null;
  private systemDarkMode: boolean = false;
  // 防止 setColorMode 触发 onConfigurationUpdate 导致的递归调用
  private applyingTheme: boolean = false;

  @Track public isDarkMode: boolean = false;
  @Track public colors: ThemeColors = new LightThemeColors();
  @Track public themeMode: ThemeMode = ThemeMode.FOLLOW_SYSTEM; // 当前主题模式
  
  private constructor() {
    // 私有构造函数
  }
  
  public static getInstance(): ThemeManager {
    if (!ThemeManager.instance) {
      ThemeManager.instance = new ThemeManager();
    }
    return ThemeManager.instance;
  }
  
  // 初始化主题管理器
  public async init(context: Context) {
    this.context = context;
    // 获取真实的系统主题并缓存
    this.systemDarkMode = await this.getRealSystemTheme();
    // 加载保存的主题模式
    await this.loadThemeMode();
    // 应用主题
    await this.applyThemeMode();
  }
  
  // 设置主题模式
  public async setThemeMode(mode: ThemeMode) {
    this.themeMode = mode;
    await this.saveThemeMode();
    await this.applyThemeMode();
    console.log(`[Theme]:主题模式已设置为: ${mode === ThemeMode.FOLLOW_SYSTEM ? '跟随系统' : mode === ThemeMode.LIGHT ? '浅色' : '深色'}`);
  }

  // 由 EntryAbility.onConfigurationUpdate 回调调用
  // 系统主题变化时直接传入真实值（避免异步读配置的时序问题）
  public onSystemThemeChanged(isRealDark: boolean) {
    if (this.themeMode !== ThemeMode.FOLLOW_SYSTEM) {
      return; // 非跟随模式不响应系统变化
    }
    if (this.applyingTheme) {
      console.log(`[Theme]:跳过递归onSystemThemeChanged`);
      return;
    }
    this.applyingTheme = true;
    
    console.log(`[Theme]:系统主题变化: isDark=${isRealDark}`);
    this.systemDarkMode = isRealDark;
    
    // 同步系统 colorMode（让 NavDestination 标题文字颜色跟随）
    this.trySetColorMode(isRealDark
      ? ConfigurationConstant.ColorMode.COLOR_MODE_DARK
      : ConfigurationConstant.ColorMode.COLOR_MODE_LIGHT);
    
    if (this.isDarkMode !== isRealDark) {
      this.isDarkMode = isRealDark;
      this.applyTheme();
    } else {
      this.applyTheme();
    }
    
    this.applyingTheme = false;
  }

  // 由 EntryAbility.onForeground 调用
  // app 切回前台时，直接实时读取系统主题来刷新
  public async onAppForeground() {
    if (this.themeMode !== ThemeMode.FOLLOW_SYSTEM) {
      return; // 非跟随模式不做任何事
    }
    if (this.applyingTheme) {
      return;
    }
    this.applyingTheme = true;
    
    try {
      const realDark = await this.getRealSystemTheme();
      this.systemDarkMode = realDark;
      // 注意：getRealSystemTheme() 的第三步已经设了正确的 colorMode
      // 不需要再额外调用 trySetColorMode
      
      if (this.isDarkMode !== realDark) {
        this.isDarkMode = realDark;
        this.applyTheme();
      } else {
        this.applyTheme();
      }
    } catch (error) {
      console.error('[Theme]:onAppForeground 失败:', error);
    }
    
    this.applyingTheme = false;
  }
  
  // 应用主题模式
  public async applyThemeMode() {
    // 防止递归：如果因为 setColorMode 回调触发 onConfigurationUpdate 再进到这里，
    // 直接跳过，因为等原始调用完成结果就是正确的
    if (this.applyingTheme) {
      console.log(`[Theme]:跳过递归applyThemeMode`);
      return;
    }
    this.applyingTheme = true;

    let shouldBeDark = false;
    
    if (this.themeMode === ThemeMode.FOLLOW_SYSTEM) {
      // 跟随系统：实时获取真实系统主题
      // getRealSystemTheme() 内部会处理 setColorMode 的清除和重设
      shouldBeDark = await this.getRealSystemTheme();
      // 更新缓存
      this.systemDarkMode = shouldBeDark;
    } else if (this.themeMode === ThemeMode.DARK) {
      // 强制深色
      shouldBeDark = true;
      this.trySetColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_DARK);
    } else {
      // 强制浅色
      shouldBeDark = false;
      this.trySetColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_LIGHT);
    }
    
    if (this.isDarkMode !== shouldBeDark) {
      this.isDarkMode = shouldBeDark;
      this.applyTheme();
    } else {
      // 即使 isDarkMode 没变，也要确保 statusBar 和 colors 正确（例如系统主题被动改变了）
      this.applyTheme();
    }

    this.applyingTheme = false;
  }

  // 尝试设置系统 colorMode（用于强制模式，跟随系统用 getRealSystemTheme 统一处理）
  private trySetColorMode(mode: number) {
    try {
      if (this.context) {
        this.context.getApplicationContext().setColorMode(mode);
        console.log(`[Theme]:trySetColorMode: ${mode}`);
      }
    } catch (error) {
      console.log(`[Theme]:trySetColorMode 失败:`, JSON.stringify(error));
    }
  }

  // 获取真实的系统主题（实时）
  // 原理：因为 setColorMode 会污染 getConfiguration() 返回的值，
  // 所以需要先清除污染（NOT_SET），读取真实值，再根据结果重新设回去
  private async getRealSystemTheme(): Promise<boolean> {
    if (!this.context) return false;

    try {
      const appContext = this.context.getApplicationContext();

      // 第一步：清除 setColorMode 的污染
      appContext.setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_NOT_SET);

      // 第二步：读取真实的系统 colorMode
      const resourceManager = appContext.resourceManager;
      const config = await resourceManager.getConfiguration();

      let isRealDark = false;
      if (config && config.colorMode !== undefined) {
        // COLOR_MODE_DARK = 0, COLOR_MODE_LIGHT = 1
        isRealDark = config.colorMode === 0;
        console.log(`[Theme]:实时获取系统主题: colorMode=${config.colorMode}, isDark=${isRealDark}`);
      }

      // 第三步：根据保存的主题模式重新设回去
      if (this.themeMode === ThemeMode.FOLLOW_SYSTEM) {
        appContext.setColorMode(isRealDark
          ? ConfigurationConstant.ColorMode.COLOR_MODE_DARK
          : ConfigurationConstant.ColorMode.COLOR_MODE_LIGHT);
      } else if (this.isDarkMode) {
        appContext.setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_DARK);
      } else {
        appContext.setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_LIGHT);
      }

      return isRealDark;
    } catch (error) {
      console.error('[Theme]:获取真实系统主题失败:', error);
      return false;
    }
  }
  
  // 应用主题
  private applyTheme() {
    if (this.isDarkMode) {
      this.colors = new DarkThemeColors();
    } else {
      this.colors = new LightThemeColors();
    }
    
    // 更新系统状态栏样式
    this.updateSystemUI();
  }
  
  // 更新系统 UI（只设置状态栏样式，不设 colorMode — colorMode 由 applyThemeMode 统一管理）
  private async updateSystemUI() {
    try {
      if (!this.context) {
        console.log(`[Theme]:Context 未初始化，跳过系统UI更新`);
        return;
      }

      // ── 设置状态栏内容颜色 ──
      const mainWindow = await window.getLastWindow(this.context);
      if (mainWindow) {
        await mainWindow.setWindowSystemBarProperties({
          statusBarContentColor: this.isDarkMode ? '#FFFFFF' : '#000000'
        });
        console.log(`[Theme]:系统状态栏已更新为 ${this.isDarkMode ? '白色' : '黑色'} 文字`);
      }
    } catch (error) {
      console.log(`[Theme]:更新系统UI失败（可能不支持）:`, JSON.stringify(error));
    }
  }
  
  // 保存主题模式
  private async saveThemeMode() {
    try {
      if (!this.context) return;
      
      const dataPreferences = await preferences.getPreferences(this.context, 'theme_preferences');
      await dataPreferences.put('themeMode', this.themeMode);
      await dataPreferences.flush();
      console.log(`[Theme]:主题模式已保存: ${this.themeMode}`);
    } catch (error) {
      console.error(`[Theme]:保存主题模式失败:`, error);
    }
  }
  
  // 加载主题模式
  private async loadThemeMode() {
    try {
      if (!this.context) return;
      
      const dataPreferences = await preferences.getPreferences(this.context, 'theme_preferences');
      const savedMode = await dataPreferences.get('themeMode', ThemeMode.FOLLOW_SYSTEM);
      this.themeMode = savedMode as ThemeMode;
      console.log(`[Theme]:主题模式已加载: ${this.themeMode}`);
    } catch (error) {
      console.error(`[Theme]:加载主题模式失败:`, error);
      this.themeMode = ThemeMode.FOLLOW_SYSTEM;
    }
  }
}
