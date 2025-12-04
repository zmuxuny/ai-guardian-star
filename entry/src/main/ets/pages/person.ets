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
  
  // ========== 原有代码开始（已注释） ==========
  /*
  build() {
      Column() {
        // 导航栏
          Text('个人信息')
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
            .width('100%')
            //.height(44)
            .margin({ left: 20,top:20,bottom:20 })
            //.padding({left:10})
            .alignSelf(ItemAlign.Start)
        
        // 个人信息内容
        Column() {
          // 基本资料区域
          Column() {
            // 头像
            Row() {
              Text('头像')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Image($r('app.media.person'))
                .width(30)
                .height(30)
                .borderRadius(4)
                .fillColor(Color.Black)
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('AvatarEdit', null, false);
            })
            
            // 昵称
            Row() {
              Text('昵称')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('张三')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('NicknameEdit', null, false);
            })
            
            // 微信号
            Row() {
              Text('微信号')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('zhangsan5200')
                .fontSize(16)
                .fontColor(Color.Black)
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            
            // 二维码名片
            Row() {
              Text('二维码名片')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Image($r('app.media.qrcode'))
                .width(25)
                .height(25)
                .fillColor(Color.Black)
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('QRCodeCard', null, false);
            })
            
            // 更多
            Row() {
              Text('更多')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('MoreInfo', null, false);
            })
          }
          .width('100%')
          .margin({ top: 20 })
          
          // 分隔线
          Divider()
            .width('100%')
            .color('#F2F2F7')
            .strokeWidth(1)
            .margin({ top: 10, bottom: 10 })
          
          // 其他信息区域
          Column() {
            // 我的地址
            Row() {
              Text('我的地址')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('MyAddress', null, false);
            })
            
            // 我的发票抬头
            Row() {
              Text('我的发票抬头')
                .fontSize(16)
                .fontColor(Color.Black)
              
              Blank()
              
              Text('>')
                .fontSize(16)
                .fontColor('#C7C7CC')
                .margin({ left: 8 })
            }
            .width('100%')
            .height(50)
            .padding({ left: 16, right: 16 })
            .justifyContent(FlexAlign.SpaceBetween)
            .alignItems(VerticalAlign.Center)
            .backgroundColor(Color.White)
            .onClick(() => {
              this.pathStack.pushPathByName('InvoiceInfo', null, false);
            })
          }
          .width('100%')
          
          Blank()
        }
        .width('100%')
        .backgroundColor('#F2F2F7')
        Blank()
        // 底部按钮区域
        Column() {
          //Button('切换账号')
            //.width('80%')
            //.height(50)
            //.fontSize(18)
            //.fontColor(Color.White)
            //.backgroundColor('#007AFF')
            //.borderRadius(30)
            //.margin({ bottom: 16 })
            //.onClick(() => {
              // 这里可以添加切换账号的逻辑
              //console.log('切换账号')
            //})
          
          Button('退出登录')
            .width('80%')
            .height(50)
            .fontSize(18)
            .fontColor('#FF3B30')
            .backgroundColor(Color.Transparent)
            .border({ width: 1, color: '#FF3B30' })
            .borderRadius(30)
            .onClick(() => {
              // 这里可以添加退出登录的逻辑
              console.log('退出登录')
              this.pathStack.replacePathByName('Login', {}, false);
            })
        }
        .width('100%')
        .padding({ bottom: 40 })
        .alignItems(HorizontalAlign.Center)
      }
      .width('100%')
      .height('100%')
      .backgroundColor('#F2F2F7')
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
  */
  // ========== 原有代码结束 ==========
  
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