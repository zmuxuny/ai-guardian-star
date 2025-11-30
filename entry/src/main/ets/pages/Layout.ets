import { mainPage } from "./mainpage"
import { person } from "./person"
import { record } from "./record"
import { ThemeManager, ThemeColors } from '../common/ThemeManager';

@Builder
export function LayoutBuilder(){
  Layout()
}
interface TabClass{
  text:string
  icon:ResourceStr
}

@ComponentV2
struct Layout {
  @Local currentIndex:number=0
  pathStack: NavPathStack = new NavPathStack();
  themeManager: ThemeManager = ThemeManager.getInstance();
  @Local isDarkMode: boolean = this.themeManager.isDarkMode;
  @Local colors: ThemeColors = this.themeManager.colors;
  tabData:TabClass[]=[
    {text:'主页',icon:$r('app.media.mainpage')},
    {text:'记录',icon:$r('app.media.record')},
    {text:'个人',icon:$r("app.media.person")},
  ]
  
  aboutToAppear() {
    // 定时同步主题状态
    setInterval(() => {
      if (this.isDarkMode !== this.themeManager.isDarkMode) {
        this.isDarkMode = this.themeManager.isDarkMode;
        this.colors = this.themeManager.colors;
      }
    }, 100);
  }

  @Builder tabBuilder(item:TabClass,index:number){
    Column({space:5}){
      Image(item.icon)
        .width(24)
        .fillColor(this.currentIndex === index ? this.colors.primaryButtonColor : this.colors.primaryTextColor)
      Text(item.text)
        .fontSize(14)
        .fontColor(this.currentIndex === index ? this.colors.primaryButtonColor : this.colors.primaryTextColor)
    }
  }

  build() {
    NavDestination(){
      Tabs({barPosition:BarPosition.End}){
        // Tab 0: 主页
        TabContent(){
          mainPage()
        }
        .tabBar(this.tabBuilder(this.tabData[0], 0))
        .backgroundColor(this.colors.backgroundColor)
        .expandSafeArea([SafeAreaType.SYSTEM],[SafeAreaEdge.TOP,SafeAreaEdge.BOTTOM])
        
        // Tab 1: 记录
        TabContent(){
          record()
        }
        .tabBar(this.tabBuilder(this.tabData[1], 1))
        .backgroundColor(this.colors.backgroundColor)
        .expandSafeArea([SafeAreaType.SYSTEM],[SafeAreaEdge.TOP,SafeAreaEdge.BOTTOM])
        
        // Tab 2: 个人
        TabContent(){
          Column() {
            person({ pathStack: this.pathStack })
          }
          .width('100%')
          .height('100%')
        }
        .tabBar(this.tabBuilder(this.tabData[2], 2))
        .backgroundColor(this.colors.backgroundColor)
        .expandSafeArea([SafeAreaType.SYSTEM],[SafeAreaEdge.TOP,SafeAreaEdge.BOTTOM])
      }
      .onChange((index:number)=>{
        this.currentIndex=index
      })
      .barBackgroundColor(this.colors.backgroundColor)
      .backgroundColor(this.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM],[SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
      .onReady((context: NavDestinationContext) => {
        this.pathStack = context.pathStack;
      })
  }
}