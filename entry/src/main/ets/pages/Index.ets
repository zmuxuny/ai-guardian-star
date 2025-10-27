
@Entry
@Component
struct Index {
  pathStack : NavPathStack = new NavPathStack();

  build() {
    Navigation(this.pathStack){
    }.onAppear(() => {
      this.pathStack.pushPathByName("Login", null, false);//控制跳转
    })
    .hideNavBar(true)//不会把自己放在控制跳转的对象里面->点返回的时候不会回到这个导航页
  }
}