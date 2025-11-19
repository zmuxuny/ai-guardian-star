import { MqttManager, FallRecord } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';

@Component
export struct record{
  // 使用MqttManager获取摔倒检测数据
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  // 添加本地状态用于强制 UI 刷新
  @State recordCount: number = 0;
  @State recordList: FallRecord[] = [];
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
    const currentCount = this.mqttManager.fallRecords.length;
    if (this.recordCount !== currentCount) {
      console.log(`[record]:检测到记录数变化 ${this.recordCount} -> ${currentCount}`);
      this.recordCount = currentCount;
      // 创建新数组触发响应式更新
      this.recordList = [...this.mqttManager.fallRecords];
      console.log(`[record]:UI 已同步，当前显示 ${this.recordList.length} 条记录`);
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

  build() {
    Column() {
      // 页面标题
      Text('摔倒记录')
        .fontSize(20)
        .width('100%')
        .fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .margin({ top: 20, bottom: 20, left: 20 })
        .alignSelf(ItemAlign.Start)
      
      // 总摔倒次数显示
      Row() {
        Text('总摔倒次数：')
          .fontSize(16)
          .fontColor(this.themeManager.colors.secondaryTextColor)
        
        Text(`${this.recordCount}`)
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor(this.themeManager.colors.dangerButtonColor)
      }
      .width('100%')
      .padding({ left: 20, right: 20, top: 12, bottom: 12 })
      .margin({ bottom: 16 })
      .alignItems(VerticalAlign.Center)
      
      // 摔倒记录列表 - 使用Scroll组件
      if (this.recordCount === 0) {
        // 没有记录时显示提示
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
            ForEach(this.recordList, 
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
    }
    .width('100%')
    .height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}