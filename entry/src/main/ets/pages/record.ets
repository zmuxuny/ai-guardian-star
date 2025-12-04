import { MqttManager, FallRecord, SedentaryRecord } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';

@Component
export struct record{
  // 使用MqttManager获取数据
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  // 添加本地状态用于强制 UI 刷新
  @State fallRecordCount: number = 0;
  @State sedentaryRecordCount: number = 0;
  @State fallRecordList: FallRecord[] = [];
  @State sedentaryRecordList: SedentaryRecord[] = [];
  @State currentTab: number = 0; // 0=摔倒记录，1=久坐记录
  private refreshTimer: number = -1;

  aboutToAppear() {
    console.log(`[record]:页面加载，当前记录数=${this.mqttManager.fallRecords.length}`);
    if (this.mqttManager.fallRecords.length > 0) {
      console.log(`[record]:当前记录:`, JSON.stringify(this.mqttManager.fallRecords.map(r => `${r.date} ${r.time}`)));
    }
    // 立即同步一次数据
    this.syncRecords();
    // 启动定时器，每 500ms 同步一次数据
    this.startRefreshTimer();
  }

  aboutToDisappear() {
    console.log(`[record]:页面销毁`);
    // 清理定时器
    if (this.refreshTimer !== -1) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = -1;
    }
  }

  // 同步记录数据
  private syncRecords() {
    // 同步摔倒记录
    const currentFallCount = this.mqttManager.fallRecords.length;
    if (this.fallRecordCount !== currentFallCount) {
      console.log(`[record]:检测到摔倒记录数变化 ${this.fallRecordCount} -> ${currentFallCount}`);
      this.fallRecordCount = currentFallCount;
      this.fallRecordList = [...this.mqttManager.fallRecords];
      console.log(`[record]:摔倒UI已同步，当前显示 ${this.fallRecordList.length} 条记录`);
    }
    
    // 同步久坐记录
    const currentSedentaryCount = this.mqttManager.sedentaryRecords.length;
    if (this.sedentaryRecordCount !== currentSedentaryCount) {
      console.log(`[record]:检测到久坐记录数变化 ${this.sedentaryRecordCount} -> ${currentSedentaryCount}`);
      this.sedentaryRecordCount = currentSedentaryCount;
      this.sedentaryRecordList = [...this.mqttManager.sedentaryRecords];
      console.log(`[record]:久坐UI已同步，当前显示 ${this.sedentaryRecordList.length} 条记录`);
    }
  }

  // 启动刷新定时器
  private startRefreshTimer() {
    this.refreshTimer = setInterval(() => {
      this.syncRecords();
    }, 500) as number;
  }

  // 摔倒记录项构建器
  @Builder
  fallRecordItemBuilder(item: FallRecord, index: number) {
    Row() {
      Column() {
        // 摔倒状态标识
        Row() {
          Text('🚨 摔倒')
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.colors.dangerButtonColor)
            .margin({ right: 8 })
          
          Text('检测到')
            .fontSize(14)
            .fontColor(this.themeManager.colors.secondaryTextColor)
        }
        .width('100%')
        .margin({ bottom: 8 })
        
        // 日期和时间
        Row() {
          Text(item.date)
            .fontSize(14)
            .fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ right: 12 })
          
          Text(item.time)
            .fontSize(14)
            .fontWeight(FontWeight.Medium)
            .fontColor(this.themeManager.colors.secondaryTextColor)
        }
        .width('100%')
      }
      .alignItems(HorizontalAlign.Start)
      .width('100%')
    }
    .width('100%')
    .padding({ top: 16, bottom: 16, left: 16, right: 16 })
    .backgroundColor(this.themeManager.isDarkMode ? '#3D1F1F' : '#FFF5F5')
    .borderRadius(8)
    .margin({ bottom: 12 })
  }
  
  // 久坐记录项构建器
  @Builder
  sedentaryRecordItemBuilder(item: SedentaryRecord, index: number) {
    Row() {
      Column() {
        // 久坐状态标识
        Row() {
          Text('⚠️ 久坐')
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.isDarkMode ? '#FFD700' : '#FF8C00')
            .margin({ right: 8 })
          
          Text('检测到')
            .fontSize(14)
            .fontColor(this.themeManager.colors.secondaryTextColor)
        }
        .width('100%')
        .margin({ bottom: 8 })
        
        // 日期和时间
        Row() {
          Text(item.date)
            .fontSize(14)
            .fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ right: 12 })
          
          Text(item.time)
            .fontSize(14)
            .fontWeight(FontWeight.Medium)
            .fontColor(this.themeManager.colors.secondaryTextColor)
        }
        .width('100%')
      }
      .alignItems(HorizontalAlign.Start)
      .width('100%')
    }
    .width('100%')
    .padding({ top: 16, bottom: 16, left: 16, right: 16 })
    .backgroundColor(this.themeManager.isDarkMode ? '#4D4D1F' : '#FFFACD')
    .borderRadius(8)
    .margin({ bottom: 12 })
  }

  build() {
    Column() {
      // 页面标题
      Text('事件记录')
        .fontSize(20)
        .width('100%')
        .fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .margin({ top: 20, bottom: 20, left: 20 })
        .alignSelf(ItemAlign.Start)
      
      // 标签页切换
      Row() {
        Button('摔倒记录')
          .fontSize(16)
          .fontColor(this.currentTab === 0 ? Color.White : this.themeManager.colors.primaryTextColor)
          .backgroundColor(this.currentTab === 0 ? 
            this.themeManager.colors.dangerButtonColor : 
            (this.themeManager.isDarkMode ? '#3A3A3C' : '#F8F8F8'))
          .borderRadius(8)
          .padding({ left: 16, right: 16, top: 8, bottom: 8 })
          .onClick(() => {
            this.currentTab = 0;
          })
        
        Button('久坐记录')
          .fontSize(16)
          .fontColor(this.currentTab === 1 ? Color.White : this.themeManager.colors.primaryTextColor)
          .backgroundColor(this.currentTab === 1 ? 
            (this.themeManager.isDarkMode ? '#FFD700' : '#FF8C00') : 
            (this.themeManager.isDarkMode ? '#3A3A3C' : '#F8F8F8'))
          .borderRadius(8)
          .padding({ left: 16, right: 16, top: 8, bottom: 8 })
          .margin({ left: 12 })
          .onClick(() => {
            this.currentTab = 1;
          })
      }
      .width('100%')
      .padding({ left: 20, right: 20 })
      .margin({ bottom: 16 })
      
      // 统计信息显示
      Row() {
        if (this.currentTab === 0) {
          Text('总摔倒次数：')
            .fontSize(16)
            .fontColor(this.themeManager.colors.secondaryTextColor)
          Text(`${this.fallRecordCount}`)
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.colors.dangerButtonColor)
        } else {
          Text('总久坐次数：')
            .fontSize(16)
            .fontColor(this.themeManager.colors.secondaryTextColor)
          Text(`${this.sedentaryRecordCount}`)
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.isDarkMode ? '#FFD700' : '#FF8C00')
        }
      }
      .width('100%')
      .padding({ left: 20, right: 20, top: 12, bottom: 12 })
      .margin({ bottom: 16 })
      .alignItems(VerticalAlign.Center)
      
      // 记录列表
      if (this.currentTab === 0) {
        // 摔倒记录列表
        if (this.fallRecordCount === 0) {
          Column() {
            Text('暂无摔倒记录')
              .fontSize(16)
              .fontColor(this.themeManager.colors.tertiaryTextColor)
          }
          .width('100%')
          .layoutWeight(1)
          .justifyContent(FlexAlign.Center)
        } else {
          Scroll() {
            Column() {
              ForEach(this.fallRecordList, 
                (item: FallRecord, index: number) => {
                  this.fallRecordItemBuilder(item, index)
                },
                (item: FallRecord, index: number) => `fall_${item.timestamp}_${index}`
              )
            }
            .width('100%')
            .padding({ left: 16, right: 16, top: 0, bottom: 16 })
          }
          .width('100%')
          .layoutWeight(1)
          .scrollBar(BarState.Off)
          .edgeEffect(EdgeEffect.Spring)
        }
      } else {
        // 久坐记录列表
        if (this.sedentaryRecordCount === 0) {
          Column() {
            Text('暂无久坐记录')
              .fontSize(16)
              .fontColor(this.themeManager.colors.tertiaryTextColor)
          }
          .width('100%')
          .layoutWeight(1)
          .justifyContent(FlexAlign.Center)
        } else {
          Scroll() {
            Column() {
              ForEach(this.sedentaryRecordList, 
                (item: SedentaryRecord, index: number) => {
                  this.sedentaryRecordItemBuilder(item, index)
                },
                (item: SedentaryRecord, index: number) => `sedentary_${item.timestamp}_${index}`
              )
            }
            .width('100%')
            .padding({ left: 16, right: 16, top: 0, bottom: 16 })
          }
          .width('100%')
          .layoutWeight(1)
          .scrollBar(BarState.Off)
          .edgeEffect(EdgeEffect.Spring)
        }
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}