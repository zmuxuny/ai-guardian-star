import { mainpage } from "./mainpage"
import { record } from "./record"

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
  tabData:TabClass[]=[
    {text:'主页',icon:$r('app.media.mainpage')},
    {text:'记录',icon:$r('app.media.record')}
  ]

  @Builder tabBuilder(item:TabClass,index:number){
    Column({space:5}){
      Image(item.icon)
        .width(24)
        .fillColor(this.currentIndex === index ? Color.Blue:Color.Black)
      Text(item.text)
        .fontSize(14)
        .fontColor(this.currentIndex === index ? Color.Blue:Color.Black)
    }
  }

  build() {
    NavDestination(){
      Tabs({barPosition:BarPosition.End}){
        ForEach(this.tabData,(item:TabClass,index:number)=>{
          TabContent(){
            if(this.currentIndex===0){
              mainpage()
            }
            else if(this.currentIndex===1) {
              record()
            }
          }
          .tabBar(this.tabBuilder(item,index))
          .backgroundColor('#fff')
          .expandSafeArea([SafeAreaType.SYSTEM],[SafeAreaEdge.TOP,SafeAreaEdge.BOTTOM])
        })
      }
      .onChange((index:number)=>{
        this.currentIndex=index
      })
      .backgroundColor('#D3D3D3')
      .expandSafeArea([SafeAreaType.SYSTEM],[SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
      .onReady((context: NavDestinationContext) => {
        this.pathStack = context.pathStack;
      })
  }
}