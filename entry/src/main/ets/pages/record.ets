import { MqttManager, FallRecord, SedentaryRecord } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';
import { GradientHeader } from '../components/GradientHeader';

// ArkTS 严格模式：联合类型不能用字符串字面量，统一用 string
interface TimelineItem {
  id: string;
  type: string;   // 'fall' | 'sedentary'
  date: string;
  time: string;
  timestamp: number;
}

// 分组结果需要显式 interface，不能用匿名对象字面量
interface DayGroupData {
  date: string;
  list: TimelineItem[];
}

@Component
export struct record {
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State currentTab: number = 0;
  @State fallRecords: FallRecord[] = [];
  @State sedentaryRecords: SedentaryRecord[] = [];
  // 处理好的分组数据，在 refreshData 里更新，build() 里直接用
  @State fallGroups: DayGroupData[] = [];
  @State sedGroups: DayGroupData[] = [];
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;

  private updateTimer: number = -1;

  aboutToAppear(): void {
    this.refreshData();
    this.updateTimer = setInterval(() => { this.refreshData(); }, 500);
  }

  aboutToDisappear(): void {
    if (this.updateTimer !== -1) { clearInterval(this.updateTimer); this.updateTimer = -1; }
  }

  private refreshData(): void {
    if (this.mqttManager) {
      this.fallRecords = [...this.mqttManager.fallRecords];
      this.sedentaryRecords = [...this.mqttManager.sedentaryRecords];
      // 预处理分组，避免在 build() 里声明局部变量
      this.fallGroups = this.groupByDate(
        this.fallRecords.map((r: FallRecord, i: number): TimelineItem => ({
          id: `fall_${i}`, type: 'fall', date: r.date, time: r.time, timestamp: i
        }))
      );
      this.sedGroups = this.groupByDate(
        this.sedentaryRecords.map((r: SedentaryRecord, i: number): TimelineItem => ({
          id: `sed_${i}`, type: 'sedentary', date: r.date, time: r.time, timestamp: i
        }))
      );
    }
  }

  private groupByDate(items: TimelineItem[]): DayGroupData[] {
    const map: Map<string, TimelineItem[]> = new Map();
    for (const item of items) {
      const existing = map.get(item.date);
      if (existing) {
        existing.push(item);
      } else {
        map.set(item.date, [item]);
      }
    }
    const result: DayGroupData[] = [];
    map.forEach((list: TimelineItem[], date: string) => {
      result.push({ date: date, list: list });
    });
    result.sort((a: DayGroupData, b: DayGroupData) => (a.date > b.date ? -1 : 1));
    return result;
  }


  @Builder
  GradientHeader(): void {
    GradientHeader() {
      Row() {
        Text('事件记录').fontSize(26).fontWeight(FontWeight.Bold).fontColor('#ffffff')
      }
      .width('100%').padding({ left: '6%', right: '6%', top: this.topSafeHeight + 16, bottom: 34 })
    }
  }

  @Builder
  StatDashboard(): void {
    Row({ space: 15 }) {
      Column() {
        Text('累计摔倒').fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
        Text(`${this.fallRecords.length}`)
          .fontSize(28).fontWeight(FontWeight.Bold).margin({ top: 8 }).fontColor('#ef4444')
      }
      .layoutWeight(1).padding({ top: 20, bottom: 20 })
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .borderRadius('10%').shadow({ radius: 12, color: '#0A000000', offsetY: 6 })

      Column() {
        Text('累计久坐').fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
        Text(`${this.sedentaryRecords.length}`)
          .fontSize(28).fontWeight(FontWeight.Bold).margin({ top: 8 }).fontColor('#f59e0b')
      }
      .layoutWeight(1).padding({ top: 20, bottom: 20 })
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .borderRadius('10%').shadow({ radius: 12, color: '#0A000000', offsetY: 6 })
    }
    .width('92%').margin({ top: '-4%' })
  }

  @Builder
  EmptyState(title: string, subTitle: string): void {
    Column() {
      Image($r('app.media.ic_shield_blue'))
        .width(100).height(100).objectFit(ImageFit.Contain).padding(22)
        .linearGradient({ direction: GradientDirection.Bottom,
          colors: [['#dbeafe', 0.0], ['#eff6ff', 1.0]] })
        .borderRadius(32).margin({ bottom: 28 })
      Text(title).fontSize(22).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
      Text(subTitle).fontSize(15).fontColor(this.themeManager.colors.secondaryTextColor)
        .margin({ top: 12 }).textAlign(TextAlign.Center).lineHeight(24)
    }
    .width('100%').margin({ top: '18%' }).padding({ left: '12%', right: '12%' })
  }

  /** 单条磁贴：isFall 直接传进来，避免 Builder 内声明 const */
  @Builder
  TimelineCard(item: TimelineItem, isFall: boolean): void {
    Column() {
      Stack({ alignContent: Alignment.BottomEnd }) {
        // 占位背景
        Column()
          .width('100%').height('100%').borderRadius(12)
          .linearGradient({ direction: GradientDirection.Bottom,
            colors: isFall
              ? [['#1e1515', 0.0], ['#3d1515', 0.6], ['#2d0a0a', 1.0]]
              : [['#151a1e', 0.0], ['#1a2d15', 0.6], ['#0a2010', 1.0]] })
        // 中央图标
        Column() {
          Text(isFall ? '⚠️' : '🪑').fontSize(28)
          Text(isFall ? '跌倒事件' : '久坐提醒').fontSize(11)
            .fontColor(isFall ? '#fca5a5' : '#fcd34d').margin({ top: 4 })
        }.justifyContent(FlexAlign.Center)
        // 右下角时间角标
        Row() {
          Text(item.time).fontSize(11).fontColor('#ffffff').fontWeight(FontWeight.Medium)
        }
        .padding({ left: 8, right: 8, top: 3, bottom: 3 })
        .backgroundColor('rgba(0,0,0,0.55)')
        .borderRadius(100).margin({ right: 8, bottom: 8 })
      }
      .width('100%').height(110).borderRadius(12).clip(true)
      .border({ width: 1.5, color: isFall ? '#7f1d1d44' : '#7c390044' })
    }
    .width('46%').padding(6)
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .borderRadius(14).shadow({ radius: 10, color: '#0000001A', offsetY: 4 })
  }

  @Builder
  DayGroup(group: DayGroupData, isFall: boolean): void {
    Column({ space: 0 }) {
      Row() {
        Column().width(3).height(14).backgroundColor('#3b82f6').borderRadius(2).margin({ right: 8 })
        Text(group.date).fontSize(13).fontWeight(FontWeight.Bold)
          .fontColor(this.themeManager.colors.primaryTextColor)
      }
      .width('100%').padding({ left: 2, top: 16, bottom: 10 })

      Flex({ wrap: FlexWrap.Wrap, justifyContent: FlexAlign.Start }) {
        ForEach(group.list, (item: TimelineItem) => {
          Row() { this.TimelineCard(item, isFall) }.margin({ right: '4%', bottom: 12 })
        })
      }.width('100%')
    }
  }


  build() {
    Column() {
      this.GradientHeader()
      this.StatDashboard()

      Row() {
        Text('摔倒记录').fontSize(15)
          .fontWeight(this.currentTab === 0 ? FontWeight.Bold : FontWeight.Normal)
          .fontColor(this.currentTab === 0 ? '#2563eb' : this.themeManager.colors.secondaryTextColor)
          .layoutWeight(1).textAlign(TextAlign.Center).padding({ bottom: '3%' })
          .border({ width: { bottom: this.currentTab === 0 ? 3 : 0 }, color: '#2563eb' })
          .onClick((): void => { this.currentTab = 0 })
        Text('久坐记录').fontSize(15)
          .fontWeight(this.currentTab === 1 ? FontWeight.Bold : FontWeight.Normal)
          .fontColor(this.currentTab === 1 ? '#2563eb' : this.themeManager.colors.secondaryTextColor)
          .layoutWeight(1).textAlign(TextAlign.Center).padding({ bottom: '3%' })
          .border({ width: { bottom: this.currentTab === 1 ? 3 : 0 }, color: '#2563eb' })
          .onClick((): void => { this.currentTab = 1 })
      }
      .width('100%').padding({ left: '8%', right: '8%', top: '5%', bottom: 0 })

      Scroll() {
        Column() {
          if (this.currentTab === 0) {
            if (this.fallRecords.length === 0) {
              this.EmptyState('暂无摔倒告警', '一切正常，老人安全受到监护')
            } else {
              ForEach(this.fallGroups, (group: DayGroupData) => {
                this.DayGroup(group, true)
              })
            }
          } else {
            if (this.sedentaryRecords.length === 0) {
              this.EmptyState('健康状态良好', '近日未检测到长时间久坐行为')
            } else {
              ForEach(this.sedGroups, (group: DayGroupData) => {
                this.DayGroup(group, false)
              })
            }
          }
          Column().height(24)
        }.width('100%').padding({ left: '4%', right: '4%', top: '3%' })
      }
      .layoutWeight(1).width('100%')
      .edgeEffect(EdgeEffect.Spring).scrollBar(BarState.Off)
    }
    .width('100%').height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .alignItems(HorizontalAlign.Center)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}
