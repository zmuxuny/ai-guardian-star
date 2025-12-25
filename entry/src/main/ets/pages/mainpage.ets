import { MqttManager } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';
// 【关键修正 1】导入 webview 模块
import webview from '@ohos.web.webview';
import display from '@ohos.display';
import { AudioTransferManager } from '../common/AudioTransferManager';
import { abilityAccessCtrl, Permissions } from '@kit.AbilityKit';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';

@Entry
@Component
export struct mainPage {
  @State selectedView: string = '正面视角';
  private volumeLevel: number = 50;
  @State videoUrl: string = 'http://192.168.5.118:5000/video_feed';

  // 使用可观察对象，确保 UI 随 MQTT 状态联动
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  
  // 本地状态变量,用于确保 UI 及时刷新
  @State isConnected: boolean = false;
  @State latestMessage: string = '正在初始化...';
  @State isFallDetected: boolean = false; // 本地摔倒状态
  @State isSedentaryDetected: boolean = false; // 本地久坐状态
  private updateTimer: number = -1;
  
  // 屏幕方向状态
  @State isPortrait: boolean = true; // true=竖屏，false=横屏

  // 【关键修正 2】将 WebController 更改为 WebviewController
  private webController: webview.WebviewController = new webview.WebviewController();

  // 用一个状态变量控制按钮样式
  @State isTalking: boolean = false;
  // 获取管理类实例
  private audioManager = AudioTransferManager.getInstance();
  // 用来请求权限的上下文
  private context = getContext(this) as common.UIAbilityContext;

  aboutToAppear() {
    // 页面出现时进行连接与订阅
    this.mqttManager.connectAndSubscribe();
    console.info('[mqtt] mainpage MQTT 初始化并尝试连接');
    
    // 检测初始屏幕方向
    this.updateOrientation();
    
    // 立即同步一次状态
    this.syncState();
    
    // 启动定时器，定期同步 MQTT 状态到本地状态
    // 使用较短的间隔确保摔倒状态能及时刷新
    this.startStateSync();
  }
  
  // 更新屏幕方向
  private updateOrientation() {
    try {
      // 通过窗口宽高比判断横竖屏
      const defaultDisplay = display.getDefaultDisplaySync();
      const windowWidth = px2vp(defaultDisplay.width);
      const windowHeight = px2vp(defaultDisplay.height);
      this.isPortrait = windowHeight > windowWidth;
      console.log(`[mainpage]:屏幕方向 isPortrait=${this.isPortrait}, width=${windowWidth}, height=${windowHeight}`);
    } catch (e) {
      console.error(`[mainpage]:获取屏幕方向失败: ${e}`);
      this.isPortrait = true; // 默认竖屏
    }
  }
  
  aboutToDisappear() {
    // 清理定时器
    if (this.updateTimer !== -1) {
      clearInterval(this.updateTimer);
      this.updateTimer = -1;
    }
  }
  
  // 同步状态方法
  private syncState() {
    let stateChanged: boolean = false;
    
    if (this.isConnected !== this.mqttManager.isConnected) {
      console.log(`[mainpage]:连接状态变化 ${this.isConnected} -> ${this.mqttManager.isConnected}`);
      this.isConnected = this.mqttManager.isConnected;
      stateChanged = true;
    }
    
    if (this.latestMessage !== this.mqttManager.latestMessage) {
      console.log(`[mainpage]:消息变化 "${this.latestMessage}" -> "${this.mqttManager.latestMessage}"`);
      this.latestMessage = this.mqttManager.latestMessage;
      stateChanged = true;
    }
    
    if (this.isFallDetected !== this.mqttManager.isFallDetected) {
      console.log(`[mainpage]:🔴 摔倒状态变化 ${this.isFallDetected} -> ${this.mqttManager.isFallDetected}`);
      this.isFallDetected = this.mqttManager.isFallDetected;
      stateChanged = true;
    }
    
    if (this.isSedentaryDetected !== this.mqttManager.isSedentaryDetected) {
      console.log(`[mainpage]:🟡 久坐状态变化 ${this.isSedentaryDetected} -> ${this.mqttManager.isSedentaryDetected}`);
      this.isSedentaryDetected = this.mqttManager.isSedentaryDetected;
      stateChanged = true;
    }
    
    if (stateChanged) {
      console.log(`[mainpage]:状态已更新 isConnected=${this.isConnected}, isFallDetected=${this.isFallDetected}, isSedentaryDetected=${this.isSedentaryDetected}, message=${this.latestMessage.substring(0, 30)}...`);
    }
  }
  
  // 启动状态同步定时器
  private startStateSync() {
    // 每 100ms 检查一次状态变化，确保摔倒状态能及时刷新到 UI
    // 使用较短的间隔确保状态变化能快速反映
    this.updateTimer = setInterval(() => {
      this.syncState();
    }, 100) as number;
  }

  // 视频流组件
  @Builder
  VideoArea() {
    Column() {
      Stack() {
        Web({ src: this.videoUrl, controller: this.webController })
          .width('100%')
          .aspectRatio(16 / 9)
          .border({ radius: 8, color: this.themeManager.colors.borderColor, width: 1 })
      }
      .width('100%')
      .padding(10)
    }
    .justifyContent(FlexAlign.Center)
  }
  
  // 信息面板组件
  @Builder
  InfoPanel() {
    Column() {
      // 设备连接状态
      Row() {
        Image($r(this.isConnected ?'app.media.link':'app.media.notlink'))
          .width(20)
          .height(20)
          .margin({ right: 8 })
          .fillColor(this.themeManager.isDarkMode ? Color.White : Color.Black)
        Text(this.isConnected ? '已连接' : '未连接')
          .fontSize(16)
          .fontColor(this.themeManager.colors.primaryTextColor)
        Blank()
        Circle({ width: 10, height: 10 })
          .fill(this.isConnected ? Color.Green : Color.Red)
      }
      .width('100%')
      .padding(12)
      .backgroundColor(this.themeManager.isDarkMode ? '#3A3A3C' : '#F8F8F8')
      .borderRadius(10)
      .margin({ bottom: 16 })
      
      // MQTT 消息显示区
      Text(this.latestMessage)
        .fontSize(18)
        .textAlign(TextAlign.Center)
        .width('100%')
        .backgroundColor(this.isFallDetected ? 
          (this.themeManager.isDarkMode ? '#4D1F1F' : '#FFE0E0') : 
          (this.isSedentaryDetected ?
            (this.themeManager.isDarkMode ? '#4D4D1F' : '#FFF8DC') :
            (this.themeManager.isDarkMode ? '#1F2D4D' : '#E6F7FF')))
        .fontColor(this.isFallDetected ? 
          this.themeManager.colors.dangerButtonColor : 
          (this.isSedentaryDetected ?
            (this.themeManager.isDarkMode ? '#FFD700' : '#FF8C00') :
            this.themeManager.colors.primaryTextColor))
        .padding(12)
        .borderRadius(10)
        .margin({ bottom: 16 })
      
      // 音量控制
      Row() {
        Image($r('app.media.yinliang2'))
          .width(24)
          .height(24)
          .margin({ right: 8 })
          .fillColor(this.themeManager.isDarkMode ? Color.White : Color.Black)
        Slider({
          value: this.volumeLevel,
          min: 0,
          max: 100
        })
          .onChange((value: number) => {
            this.volumeLevel = value;
          })
          .layoutWeight(1)
          .width(150)
          .margin({ left: 8 })
          .showTips(false)
      }
      .width('100%')
      .height(50)
      .padding(12)
      .backgroundColor(this.themeManager.isDarkMode ? '#3A3A3C' : '#F8F8F8')
      .borderRadius(20)
    }
    .width('100%')
    .padding({ left: 16, right: 16 })
  }

  build() {
    Column() {
      // 标题栏
      Text('智能居家监护')
        .fontSize(20)
        .fontWeight(FontWeight.Bold)
        .width('100%')
        .margin({ left: 20, top: 20, bottom: 20 })
        .fontColor(this.themeManager.colors.primaryTextColor)
        .alignSelf(ItemAlign.Start)

      // 根据横竖屏切换布局
      if (this.isPortrait) {
        // 竖屏：上下布局
        Scroll() {
          Column() {
            this.VideoArea()
            this.InfoPanel()
          }
          .width('100%')
        }
        .width('100%')
        .layoutWeight(1)
        .scrollBar(BarState.Off)
        .edgeEffect(EdgeEffect.Spring)
      } else {
        // 横屏：左右布局
        Row() {
          // 左侧视频区域
          Column() {
            this.VideoArea()
          }
          .layoutWeight(1)
          
          // 右侧信息面板
          Scroll() {
            this.InfoPanel()
          }
          .width('40%')
          .scrollBar(BarState.Off)
          .edgeEffect(EdgeEffect.Spring)
        }
        .width('100%')
        .layoutWeight(1)
      }
      Button({type: ButtonType.Circle}) // 动态改变文字
      //this.isTalking ? '挂断' : '开始通话'
      {
        Column() {
          Text('        ')
          Image(this.isTalking ? $r('app.media.offcall'):$r('app.media.oncall'))
            .width(24)
            .height(24)
            .fillColor(this.isTalking ? Color.Black:Color.White)
            .margin({ bottom: 8 })
          Text(this.isTalking ? '挂断':'通话')
            .textAlign(TextAlign.Center)
            .fontSize(16)
            .fontColor(Color.White)
        }
        .width('100%')
        .height('100%')
      }
        .width(150)
        .height(50)
        .width(90)
        .height(90)
        .borderRadius(60)
        .margin({bottom:50})
        .backgroundColor(this.isTalking ? Color.Red : Color.Blue) // 动态改变颜色
        .onClick(async () => {
          if (this.isTalking) {
            // 挂断逻辑不变
            await this.audioManager.stopCall();
            this.isTalking = false;
          } else {
            // --- 新增：申请权限逻辑 ---
            const atManager = abilityAccessCtrl.createAtManager();
            try {
              // 向用户弹窗请求麦克风权限
              const result = await atManager.requestPermissionsFromUser(this.context, ['ohos.permission.MICROPHONE']);

              // 检查用户是否点击了“允许”
              if (result.authResults[0] === 0) {
                // 用户允许了，开始通话
                console.info('权限已获取，启动通话');
                await this.audioManager.startCall();
                this.isTalking = true;
              } else {
                console.warn('用户拒绝了麦克风权限');
                // 这里可以弹个窗提示用户去设置里开启
              }
            } catch (err) {
              console.error('申请权限失败:', JSON.stringify(err));
            }
          }
        })
    }
    .width('100%')
    .height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}