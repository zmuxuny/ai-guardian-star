import preferences from '@ohos.data.preferences';
import { window } from '@kit.ArkUI';

// 主题颜色定义
export class ThemeColors {
  // 背景色
  backgroundColor: string = '#FFFFFF';
  secondaryBackgroundColor: string = '#F2F2F7';
  cardBackgroundColor: string = '#FFFFFF';
  
  // 文字色
  primaryTextColor: string = '#1C1C1E';
  secondaryTextColor: string = '#8E8E93';
  tertiaryTextColor: string = '#C7C7CC';
  
  // 分割线色
  separatorColor: string = '#E5E5EA';
  
  // 按钮色
  primaryButtonColor: string = '#007AFF';
  dangerButtonColor: string = '#FF3B30';
  
  // 卡片边框色
  borderColor: string = '#E5E5EA';
}

// 深色主题
export class DarkThemeColors extends ThemeColors {
  backgroundColor: string = '#000000';
  secondaryBackgroundColor: string = '#1C1C1E';
  cardBackgroundColor: string = '#2C2C2E';
  
  primaryTextColor: string = '#FFFFFF';
  secondaryTextColor: string = '#EBEBF5';
  tertiaryTextColor: string = '#8E8E93';
  
  separatorColor: string = '#38383A';
  
  primaryButtonColor: string = '#0A84FF';
  dangerButtonColor: string = '#FF453A';
  
  borderColor: string = '#38383A';
}

// 浅色主题
export class LightThemeColors extends ThemeColors {
  // 使用默认值
}

// 主题管理器（单例模式）
@Observed
export class ThemeManager {
  private static instance: ThemeManager;
  private context: Context | null = null;
  
  @Track public isDarkMode: boolean = false;
  @Track public colors: ThemeColors = new LightThemeColors();
  
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
    // 从本地存储读取主题设置
    await this.loadThemePreference();
  }
  
  // 切换主题
  public toggleTheme() {
    this.isDarkMode = !this.isDarkMode;
    this.applyTheme();
    this.saveThemePreference();
    console.log(`[Theme]:主题已切换为 ${this.isDarkMode ? '深色' : '浅色'} 模式`);
  }
  
  // 设置主题
  public setTheme(isDark: boolean) {
    if (this.isDarkMode !== isDark) {
      this.isDarkMode = isDark;
      this.applyTheme();
      this.saveThemePreference();
      console.log(`[Theme]:主题已设置为 ${this.isDarkMode ? '深色' : '浅色'} 模式`);
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
  
  // 保存主题偏好到本地存储
  private async saveThemePreference() {
    try {
      if (!this.context) return;
      
      const dataPreferences = await preferences.getPreferences(this.context, 'theme_preferences');
      await dataPreferences.put('isDarkMode', this.isDarkMode);
      await dataPreferences.flush();
      console.log(`[Theme]:主题偏好已保存: ${this.isDarkMode}`);
    } catch (error) {
      console.error(`[Theme]:保存主题偏好失败:`, error);
    }
  }
  
  // 从本地存储加载主题偏好
  private async loadThemePreference() {
    try {
      if (!this.context) return;
      
      const dataPreferences = await preferences.getPreferences(this.context, 'theme_preferences');
      const savedTheme = await dataPreferences.get('isDarkMode', false);
      this.isDarkMode = savedTheme as boolean;
      this.applyTheme();
      console.log(`[Theme]:主题偏好已加载: ${this.isDarkMode ? '深色' : '浅色'} 模式`);
    } catch (error) {
      console.error(`[Theme]:加载主题偏好失败:`, error);
      // 使用默认浅色主题
      this.isDarkMode = false;
      this.applyTheme();
    }
  }
}
