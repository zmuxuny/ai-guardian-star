import { AppStorageV2 } from '@kit.ArkUI';

@Entry
@Component
struct Index {
  //pathStack : NavPathStack = new NavPathStack();
  pathStack : NavPathStack = AppStorageV2.connect(NavPathStack,'navStack',()=>new NavPathStack())!;

  build() {
    Navigation(this.pathStack){
    }.onAppear(() => {
      this.pathStack.replacePathByName("Login", null, false);//控制跳转
    })
    .hideNavBar(true)//不会把自己放在控制跳转的对象里面->点返回的时候不会回到这个导航页
  }
}