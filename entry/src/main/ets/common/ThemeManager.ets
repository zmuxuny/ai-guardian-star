import preferences from '@ohos.data.preferences';
import { window } from '@kit.ArkUI';

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
  
  // 应用主题模式
  public async applyThemeMode() {
    let shouldBeDark = false;
    
    if (this.themeMode === ThemeMode.FOLLOW_SYSTEM) {
      // 跟随系统
      shouldBeDark = await this.getSystemTheme();
    } else if (this.themeMode === ThemeMode.DARK) {
      // 强制深色
      shouldBeDark = true;
    } else {
      // 强制浅色
      shouldBeDark = false;
    }
    
    if (this.isDarkMode !== shouldBeDark) {
      this.isDarkMode = shouldBeDark;
      this.applyTheme();
    }
  }
  
  // 获取系统主题
  private async getSystemTheme(): Promise<boolean> {
    if (!this.context) return false;
    
    try {
      const appContext = this.context.getApplicationContext();
      const resourceManager = appContext.resourceManager;
      const config = await resourceManager.getConfiguration();
      
      if (config && config.colorMode !== undefined) {
        // 修复：ColorMode.COLOR_MODE_DARK = 0, COLOR_MODE_LIGHT = 1
        // 这里需要反过来判断
        const isSystemDark = config.colorMode === 0;
        console.log(`[Theme]:系统主题: colorMode=${config.colorMode}, isDark=${isSystemDark}`);
        return isSystemDark;
      }
    } catch (error) {
      console.error('[Theme]:获取系统主题失败:', error);
    }
    
    return false;
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
  
  // 更新系统 UI（状态栏）
  private async updateSystemUI() {
    try {
      if (!this.context) {
        console.log(`[Theme]:Context 未初始化，跳过系统UI更新`);
        return;
      }
      
      const mainWindow = await window.getLastWindow(this.context);
      if (mainWindow) {
        // 设置状态栏内容颜色（深色模式用白色文字，浅色模式用黑色文字）
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
