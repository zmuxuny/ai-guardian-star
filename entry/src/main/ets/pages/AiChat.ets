/**
 * AiChat.ets - AI Health Assistant Page
 * Tab sub-component, no @Entry decorator
 */

import { WenxinService, ChatMessage } from '../common/WenxinService';
import { ThemeManager } from '../common/ThemeManager';
import { MqttManager } from './MqttManager';
import { GradientHeader } from '../components/GradientHeader';

const QUICK_QUESTIONS: string[] = [
  '老人最近状态怎么样？',
  '摔倒后有哪些注意事项？',
  '久坐对老人有什么危害？',
  '如何预防老人摔倒？',
];

interface BubbleMsg {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  isLoading: boolean;
  timestamp: number;
}

@Component
export struct AiChat {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State messages: BubbleMsg[] = [];
  @State inputText: string = '';
  @State isRequesting: boolean = false;
  @State dotPhase: number = 0;
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;

  private scroller: Scroller = new Scroller();
  private msgIdCounter: number = 0;
  private dotTimer: number = -1;

  aboutToAppear(): void {
    this.pushAssistantMsg(
      '你好！我是智护星 AI 健康助手 👋\n\n' +
      '我已接入监护数据（仅统计摘要），' +
      '可以帮你分析健康风险、解答护理疑问。'
    );
  }

  aboutToDisappear(): void {
    if (this.dotTimer !== -1) {
      clearInterval(this.dotTimer);
      this.dotTimer = -1;
    }
  }

  private nextId(): number { return ++this.msgIdCounter; }

  private pushMsg(msg: BubbleMsg): void {
    this.messages = [...this.messages, msg];
  }

  private pushAssistantMsg(content: string): void {
    this.pushMsg({
      id: this.nextId(), role: 'assistant',
      content, isLoading: false, timestamp: Date.now()
    });
    this.scrollToBottom();
  }

  private replaceLoadingMsg(loadingId: number, reply: string): void {
    const filtered = this.messages.filter(m => m.id !== loadingId);
    const replyMsg: BubbleMsg = {
      id: loadingId,
      role: 'assistant',
      content: reply,
      isLoading: false,
      timestamp: Date.now()
    };
    this.messages = [];
    this.messages = [...filtered, replyMsg];
  }

  private scrollToBottom(): void {
    setTimeout(() => { this.scroller.scrollEdge(Edge.Bottom); }, 100);
  }

  private startDotAnimation(): void {
    this.dotPhase = 0;
    if (this.dotTimer !== -1) clearInterval(this.dotTimer);
    this.dotTimer = setInterval(() => { this.dotPhase = (this.dotPhase + 1) % 3; }, 400);
  }

  private stopDotAnimation(): void {
    if (this.dotTimer !== -1) { clearInterval(this.dotTimer); this.dotTimer = -1; }
  }

  private buildHistory(): ChatMessage[] {
    return this.messages
      .filter(m => !m.isLoading && m.content.length > 0)
      .slice(-20)
      .map(m => ({ role: m.role, content: m.content } as ChatMessage));
  }

  private async sendMessage(text: string): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed || this.isRequesting) return;

    this.inputText = '';
    this.isRequesting = true;

    this.pushMsg({
      id: this.nextId(), role: 'user',
      content: trimmed, isLoading: false, timestamp: Date.now()
    });
    this.scrollToBottom();

    const loadingId = this.nextId();
    this.pushMsg({
      id: loadingId, role: 'assistant',
      content: '', isLoading: true, timestamp: Date.now()
    });
    this.startDotAnimation();
    this.scrollToBottom();

    const history = this.buildHistory().slice(0, -1);

    let reply = '';
    try {
      reply = await WenxinService.getInstance().chat(trimmed, history);
    } catch (e) {
      reply = '请求出现异常，请稍后重试';
      console.error('[AiChat] sendMessage error:', JSON.stringify(e));
    }

    this.replaceLoadingMsg(loadingId, reply);
    this.stopDotAnimation();
    this.isRequesting = false;
    this.scrollToBottom();
  }

  @Builder
  GradientHeader(): void {
    GradientHeader() {
      Row() {
        Text('AI 健康助手')
          .fontSize(26).fontWeight(FontWeight.Bold).fontColor('#ffffff')
        Blank()
        Row({ space: 6 }) {
          Circle({ width: 8, height: 8 }).fill('#4ade80')
          Text('AI 在线').fontSize(12).fontColor('#E0F2FE')
        }
        .padding({ left: 10, right: 10, top: 6, bottom: 6 })
        .backgroundColor('#33FFFFFF').borderRadius(100)
      }
      .width('100%')
      .padding({ left: '6%', right: '6%', top: this.topSafeHeight + 16, bottom: 34 })
    }
  }

  @Builder
  HealthOverview(): void {
    Row({ space: 15 }) {
      Column() {
        Text('摔倒告警').fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
        Text(`${this.mqttManager.fallRecords.length}`)
          .fontSize(28).fontWeight(FontWeight.Bold).margin({ top: 8 }).fontColor('#ef4444')
      }
      .layoutWeight(1).padding({ top: 20, bottom: 20 })
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .borderRadius('10%').shadow({ radius: 12, color: '#0A000000', offsetY: 6 })

      Column() {
        Text('久坐提醒').fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
        Text(`${this.mqttManager.sedentaryRecords.length}`)
          .fontSize(28).fontWeight(FontWeight.Bold).margin({ top: 8 }).fontColor('#f59e0b')
      }
      .layoutWeight(1).padding({ top: 20, bottom: 20 })
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .borderRadius('10%').shadow({ radius: 12, color: '#0A000000', offsetY: 6 })
    }
    .width('92%').margin({ top: '-4%' })
  }

  @Builder
  LoadingDots(): void {
    Row({ space: 5 }) {
      ForEach([0, 1, 2], (i: number) => {
        Circle({ width: 8, height: 8 })
          .fill('#93c5fd')
          .scale({ x: this.dotPhase === i ? 1.4 : 1.0, y: this.dotPhase === i ? 1.4 : 1.0 })
          .animation({ duration: 350, curve: Curve.EaseInOut })
      })
    }.padding({ left: 4, right: 4, top: 6, bottom: 6 })
  }

  @Builder
  MessageBubble(msg: BubbleMsg): void {
    Row() {
      if (msg.role === 'user') {
        Blank()
        Text(msg.content)
          .fontSize(15).fontColor('#ffffff').lineHeight(22)
          .padding({ left: 14, right: 14, top: 10, bottom: 10 })
          .backgroundColor('#2563eb')
          .borderRadius({ topLeft: 16, topRight: 4, bottomLeft: 16, bottomRight: 16 })
          .constraintSize({ maxWidth: '72%' })
      } else {
        Text('🤖')
          .fontSize(20).width(36).height(36)
          .textAlign(TextAlign.Center).lineHeight(36)
          .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
          .borderRadius(18).margin({ right: 10 }).flexShrink(0)
        Column() {
          if (msg.isLoading) {
            this.LoadingDots()
          } else {
            Text(msg.content)
              .fontSize(15)
              .fontColor(this.themeManager.colors.primaryTextColor)
              .lineHeight(22)
          }
        }
        .padding({ left: 14, right: 14, top: 10, bottom: 10 })
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .borderRadius({ topLeft: 4, topRight: 16, bottomLeft: 16, bottomRight: 16 })
        .shadow({ radius: 6, color: '#08000000', offsetY: 2 })
        .constraintSize({ maxWidth: '72%' })
        Blank()
      }
    }
    .width('100%').padding({ left: '5%', right: '5%', top: 6, bottom: 6 })
  }

  @Builder
  QuickQuestions(): void {
    Column() {
      Text('快捷提问').fontSize(12)
        .fontColor(this.themeManager.colors.secondaryTextColor)
        .margin({ left: '5%', bottom: 8 }).alignSelf(ItemAlign.Start)
      Scroll(new Scroller()) {
        Row({ space: 10 }) {
          ForEach(QUICK_QUESTIONS, (q: string) => {
            Text(q)
              .fontSize(13).fontColor('#2563eb')
              .padding({ left: 14, right: 14, top: 8, bottom: 8 })
              .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
              .borderRadius(20).border({ width: 1, color: '#93c5fd' })
              .onClick((): void => {
                if (!this.isRequesting) this.sendMessage(q);
              })
          })
        }.padding({ left: '5%', right: '5%' })
      }.scrollable(ScrollDirection.Horizontal).scrollBar(BarState.Off)
    }.margin({ bottom: 6 })
  }

  @Builder
  AiDisclaimer(): void {
    Row({ space: 4 }) {
      Text('✨').fontSize(10)
      Text('内容由 AI 生成，仅供参考，请勿替代专业建议')
        .fontSize(10)
        .fontColor(this.themeManager.colors.tertiaryTextColor)
    }
    .width('100%')
    .justifyContent(FlexAlign.Center)
    .padding({ top: 4, bottom: 6 })
  }

  @Builder
  InputBar(): void {
    Row({ space: 12 }) {
      TextInput({ text: this.inputText, placeholder: '问点什么…' })
        .layoutWeight(1).height(46).fontSize(15)
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .borderRadius(23).padding({ left: 16, right: 16 })
        .border({ width: 1.5, color: this.isRequesting ? '#93c5fd' : '#e2e8f0' })
        .placeholderColor(this.themeManager.colors.secondaryTextColor)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .onChange((val: string): void => { this.inputText = val; })
        .onSubmit((): void => { this.sendMessage(this.inputText); })
        .enabled(!this.isRequesting)
      Stack() {
        if (this.isRequesting) {
          LoadingProgress().width(22).height(22).color('#ffffff')
        } else {
          Text('↑').fontSize(20).fontColor('#ffffff').fontWeight(FontWeight.Bold)
        }
      }
      .width(46).height(46)
      .backgroundColor(this.inputText.trim().length > 0 && !this.isRequesting ? '#2563eb' : '#93c5fd')
      .borderRadius(23).animation({ duration: 200, curve: Curve.EaseOut })
      .onClick((): void => { this.sendMessage(this.inputText); })
    }
    .width('100%').padding({ left: '5%', right: '5%', top: 10, bottom: 16 })
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .shadow({ radius: 10, color: '#12000000', offsetY: -3 })
  }

  build() {
    Column() {
      this.GradientHeader()
      this.HealthOverview()
      Scroll(this.scroller) {
        Column({ space: 0 }) {
          ForEach(this.messages, (msg: BubbleMsg) => {
            this.MessageBubble(msg)
          }, (msg: BubbleMsg) => `${msg.id}_${msg.isLoading ? 'L' : msg.content.length}`)
          Column().height(16)
        }.width('100%').padding({ top: 12 })
      }
      .layoutWeight(1).scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
      this.QuickQuestions()
      this.AiDisclaimer()
      this.InputBar()
    }
    .width('100%').height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
  }
}
