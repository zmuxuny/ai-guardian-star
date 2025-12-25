import { ThemeManager, ThemeMode } from '../common/ThemeManager';
import { MqttManager } from './MqttManager';
import promptAction from '@ohos.promptAction';

// 跳转页面入口函数
@Builder
export function personBuilder() {
  person();
}

@Component
export struct person{
  pathStack?: NavPathStack = new NavPathStack();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  private scroller: Scroller = new Scroller(); // 滚动控制器
  private mqttManager: MqttManager = MqttManager.getInstance();
  
  // 主题模式选项
  private themeModeOptions: SelectOption[] = [
    { value: '跟随系统' },
    { value: '浅色' },
    { value: '深色' }
  ];
  
  // 处理清理缓存
  private handleClearCache() {
    const stats = this.mqttManager.getCacheStats();
    console.log('清理前统计:', stats);
    
    const totalCount = stats.fallCount + stats.sedentaryCount;
    
    // 执行清理
    this.mqttManager.clearAllCache();
    
    // 显示成功提示
    try {
      promptAction.showToast({
        message: `已清理 ${totalCount} 条记录 (摔倒${stats.fallCount} + 久坐${stats.sedentaryCount})`,
        duration: 2000
      });
    } catch (error) {
      console.error('显示提示失败:', error);
    }
  }
  
  // 显示缓存统计信息
  private showCacheStatsDialog() {
    const stats = this.mqttManager.getCacheStats();
    
    AlertDialog.show({
      title: '清理缓存',
      message: `当前缓存信息：\n\n【摔倒记录】\n记录数：${stats.fallCount} 条\n最早记录：${stats.oldestFallRecord}\n最新记录：${stats.newestFallRecord}\n\n【久坐记录】\n记录数：${stats.sedentaryCount} 条\n最早记录：${stats.oldestSedentaryRecord}\n最新记录：${stats.newestSedentaryRecord}\n\n确定要清空所有记录吗？`,
      primaryButton: {
        value: '取消',
        action: () => {
          console.log('取消清理');
        }
      },
      secondaryButton: {
        value: '确定',
        fontColor: Color.Red,
        action: () => {
          this.handleClearCache();
        }
      },
      alignment: DialogAlignment.Center
    });
  }
  
  // 获取当前主题模式文本
  private getThemeModeText(): string {
    switch (this.themeManager.themeMode) {
      case ThemeMode.FOLLOW_SYSTEM:
        return '跟随系统';
      case ThemeMode.LIGHT:
        return '浅色';
      case ThemeMode.DARK:
        return '深色';
      default:
        return '跟随系统';
    }
  }

  build() {
    Column() {
      // 可滚动区域
      Scroll(this.scroller) {
        Column() {
          // 用户头像和基本信息区域
          Column() {
            // 用户头像（圆形）
            Image($r('app.media.person'))
              .width(80)
              .height(80)
              .borderRadius(40)
              .fillColor(this.themeManager.colors.secondaryTextColor)
              .margin({ top: 40, bottom: 16 })
            
            // 用户文本
            Text('管理员')
              .fontSize(24)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.themeManager.colors.primaryTextColor)
              .margin({ bottom: 8 })
            
            // 账号信息
            Text('192.168.137.100')
              .fontSize(14)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .margin({ bottom: 40 })
          }
          .width('100%')
          .alignItems(HorizontalAlign.Center)
          
          // 外观设置选项
          Row() {
            Text('外观')
              .fontSize(16)
              .fontColor(this.themeManager.colors.primaryTextColor)
            
            Blank()
            
            Select(this.themeModeOptions)
              .selected(this.themeManager.themeMode)
              .value(this.getThemeModeText())
              .font({ size: 16 })
              .fontColor(this.themeManager.colors.primaryTextColor)
              .selectedOptionFont({ size: 16 })
              .optionFont({ size: 16 })
              .backgroundColor(Color.Transparent)
              .width(120)
              .menuBackgroundColor(this.themeManager.colors.cardBackgroundColor)
              .divider({ strokeWidth: 0 })
              .onSelect((index: number) => {
                console.log(`选择主题模式: ${index}`);
                this.themeManager.setThemeMode(index as ThemeMode);
              })
          }
          .width('80%')
          .height(50)
          .padding({ left: 16, right: 16 })
          .justifyContent(FlexAlign.SpaceBetween)
          .alignItems(VerticalAlign.Center)
          .borderRadius(15)
          .backgroundColor(this.themeManager.isDarkMode ? '#3A3A3C' : '#F8F8F8')
          .margin({ top: 20 })
          .alignSelf(ItemAlign.Center)
          
          // 清理缓存选项
          Row() {
            Text('清理缓存')
              .fontSize(16)
              .fontColor(this.themeManager.colors.primaryTextColor)
            
            Blank()
            
            Text('＞')
              .fontSize(16)
              .fontColor(this.themeManager.colors.primaryTextColor)
          }
          .width('80%')
          .height(50)
          .padding({ left: 16, right: 16 })
          .justifyContent(FlexAlign.SpaceBetween)
          .alignItems(VerticalAlign.Center)
          .borderRadius(15)
          .backgroundColor(this.themeManager.isDarkMode ? '#3A3A3C' : '#F8F8F8')
          .margin({ top: 20 })
          .alignSelf(ItemAlign.Center)
          .onClick(() => {
            this.showCacheStatsDialog();
          })
          
          Blank()
        }
        .width('100%')
      }
      .width('100%')
      .layoutWeight(1)
      .scrollBar(BarState.Off)
      .edgeEffect(EdgeEffect.Spring)
      
      // 版本信息 - 固定在底部，不参与滚动
      Text('版本号 1.0.0')
        .fontSize(16)
        .fontColor(this.themeManager.colors.secondaryTextColor)
        .margin({ bottom: 30 })
    }
    .width('100%')
    .height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}