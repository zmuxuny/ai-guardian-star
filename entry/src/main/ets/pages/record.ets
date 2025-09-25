// 健康记录数据接口
interface HealthRecord {
  time: string;
  type: string;
  details: string[];
  isLast?: boolean;
}

@Component
export struct record{
  // 健康记录数据
  healthRecords: HealthRecord[] = [
    {
      time: '08:00',
      type: '生命体征',
      details: ['血压: 120/80', '心率: 78', '血糖: 5.6']
    },
    {
      time: '12:00',
      type: '饮食',
      details: ['午餐: 米饭, 青菜, 豆腐']
    },
    {
      time: '18:00',
      type: '用药',
      details: ['阿司匹林'],
      isLast: true
    },
    {
      time: '18:00',
      type: '用药',
      details: ['阿司匹林'],
      isLast: true
    },
    {
      time: '18:00',
      type: '用药',
      details: ['阿司匹林'],
      isLast: true
    },
    {
      time: '18:00',
      type: '用药',
      details: ['阿司匹林'],
      isLast: true
    }
  ];

  // List项构建器
  @Builder
  recordItemBuilder(item: HealthRecord, index: number) {
    Row() {
      Column() {
        Text(item.time)
          .fontSize(14)
          .fontWeight(FontWeight.Bold)
          .fontColor('#666666')
          .margin({ bottom: 4 })
        
        Text(item.type)
          .fontSize(16)
          .fontWeight(FontWeight.Bold)
          .fontColor(Color.Black)
          .margin({ bottom: 8 })
        
        ForEach(item.details, (detail: string) => {
          Text(detail)
            .fontSize(14)
            .fontColor('#666666')
            .margin({ bottom: 2 })
        })
      }
      .alignItems(HorizontalAlign.Start)
      
      Blank()
    }
    .width('100%')
    .alignItems(VerticalAlign.Top)
    .margin({ bottom: 16 })
  }

  build() {
    Column() {
      // 页面标题和搜索栏
      Column() {
        Text('健康记录')
          .fontSize(20)
          .width('100%')
          .fontWeight(FontWeight.Bold)
          .fontColor(Color.Black)
          .margin({ top: 20, bottom: 20,left: 20 })
          .alignSelf(ItemAlign.Start)
        
        // 搜索栏
        Row() {
          Stack({alignContent:Alignment.End}) {
            TextInput({ placeholder: '日期' })
              .placeholderColor('#817D83')
              .fontSize(16)
              .fontColor(Color.Black)
              .padding({ left: 16, right: 8 })
              .layoutWeight(1)

            Image($r('app.media.search'))
              .width(20)
              .fillColor(Color.Black)
              .height(20)
              //.padding({ right: 16 })
              .margin(10)
          }
        }
        .width('90%')
        .height(40)
        .backgroundColor(Color.White)
        .border({ radius: 20 })
        .alignSelf(ItemAlign.Center)
        .margin({ bottom: 20 })
      }
      .width('100%')
      .alignItems(HorizontalAlign.Center)
      
      // 用户信息区域
      Row() {
        // 用户头像
        Image($r('app.media.person'))
          .width(60)
          .fillColor(Color.Black)
        
        Column() {
          Text('张三')
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
            .margin({ bottom: 6 })
          
          Text('78岁')
            .fontSize(14)
            .fontColor('#666666')
        }
        .alignItems(HorizontalAlign.Start)
        .margin({ left: 16 })
        
        Blank()
      }
      .width('100%')
      .padding({ left: 16, right: 16 })
      .margin({ bottom: 16 })
      
      // 状态标签
      Row() {
        Text('当天状态')
          .fontSize(12)
          .fontColor(Color.Black)
          .backgroundColor('#E5E5E5')
          .padding({ left: 12, right: 12, top: 6, bottom: 6 })
          .borderRadius(12)
          .margin({ right: 8 })
        
        Text('服药正常')
          .fontSize(12)
          .fontColor(Color.Black)
          .backgroundColor('#E5E5E5')
          .padding({ left: 12, right: 12, top: 6, bottom: 6 })
          .borderRadius(12)
          .margin({ right: 8 })
        
        Text('睡眠不足')
          .fontSize(12)
          .fontColor(Color.Black)
          .backgroundColor('#E5E5E5')
          .padding({ left: 12, right: 12, top: 6, bottom: 6 })
          .borderRadius(12)
      }
      .width('100%')
      .padding({ left: 16, right: 16 })
      .margin({ bottom: 24 })
      .alignItems(VerticalAlign.Top)
      
      // 日期显示
      Text('2025.9.4')
        .fontSize(20)
        .fontWeight(FontWeight.Bold)
        .fontColor(Color.Black)
        .alignSelf(ItemAlign.Start)
        .margin({ left: 16, bottom: 20 })
      
      // 健康事件时间轴 - 使用List组件
      List() {
        ForEach(this.healthRecords, (item: HealthRecord, index: number) => {
          ListItem() {
            this.recordItemBuilder(item, index)
          }
        })
      }
      .width('100%')
      .layoutWeight(1)
      .padding({ left: 16, right: 16 })
      .divider({ 
        strokeWidth: 0,
        color: Color.Transparent 
      })
      .scrollBar(BarState.Off)
    }
    .width('100%')
    .height('100%')
    .backgroundColor(Color.White)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}