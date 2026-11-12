import { CareStatusBadge } from '../components/CareStatusBadge';
/**
 * AiChat.ets - AI Health Assistant Page
 * Tab sub-component, no @Entry decorator
 */

import { WenxinService, ChatMessage } from '../common/WenxinService';
import { ThemeManager } from '../common/ThemeManager';
import { GradientHeader, PAGE_HORIZONTAL_GUTTER, PAGE_TITLE_SIZE } from '../components/GradientHeader';
import { STORE_KEY_AI_ACCESS_LEVEL, STORE_KEY_AI_POLICY_READY, STORE_KEY_AI_POLICY_STAMP } from '../config';
import { getWindowSizeClass } from '../common/ResponsiveLayout';
import { CarePalette, carePalette, careIconTint } from '../common/CarePalette';
import { MqttManager } from './MqttManager';

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
  onOpenHome: () => void = () => {};
  onTabScroll: (delta: number, state: ScrollState) => void = () => {};
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State mqtt: MqttManager = MqttManager.getInstance();
  @State messages: BubbleMsg[] = [];
  @State inputText: string = '';
  @State isRequesting: boolean = false;
  @State dotPhase: number = 0;
  @StorageLink(STORE_KEY_AI_ACCESS_LEVEL) aiAccessLevel: string = 'privacy';
  @StorageProp(STORE_KEY_AI_POLICY_STAMP) @Watch('onPolicyChanged') policyStamp: string = '';
  @StorageProp(STORE_KEY_AI_POLICY_READY) @Watch('onPolicyReadinessChanged') policyReady: boolean = false;
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;
  // 当前视口宽度，用于快捷提问在大屏折行铺开
  @State viewportWidth: number = 360;

  private scroller: Scroller = new Scroller();
  private msgIdCounter: number = 0;
  private dotTimer: number = -1;
  private requestGeneration: number = 0;

  private onPolicyChanged(): void {
    this.requestGeneration++;
    this.stopDotAnimation();
    this.messages = [];
    this.inputText = '';
    this.isRequesting = false;
    this.pushAssistantMsg('AI 权限已更新，之前的对话已清空。请重新提问。');
  }

  private onPolicyReadinessChanged(): void {
    if (!this.policyReady) this.onPolicyChanged();
  }

  aboutToAppear(): void {
    const accessText = this.aiAccessLevel === 'full' ? '完整监护状态'
      : this.aiAccessLevel === 'basic' ? '基础健康问答' : '脱敏统计摘要';
    this.pushAssistantMsg(
      '你好！我是智护星 AI 健康助手 👋\n\n' +
      `当前模式：${accessText}，` +
      '可以帮你分析健康风险、解答护理疑问。\n\n问题和最近对话会交给云端 AI。常见手机号、身份证号和邮箱会自动隐藏；请勿输入姓名或住址。切换权限会清空对话。'
    );
  }

  aboutToDisappear(): void {
    this.requestGeneration++;
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
    if (!trimmed || this.isRequesting || !this.policyReady) return;
    const generation = ++this.requestGeneration;

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
      console.error('[AiChat] sendMessage failed');
    }
    if (generation !== this.requestGeneration) return;
    this.replaceLoadingMsg(loadingId, reply);
    this.stopDotAnimation();
    this.isRequesting = false;
    this.scrollToBottom();
  }

  private palette(): CarePalette {
    return carePalette(this.mqtt.isFallDetected, this.mqtt.isSedentaryDetected, this.mqtt.deviceOnline);
  }

  @Builder
  GradientHeader(): void {
    GradientHeader({ useHomeStyle: true }) {
      Column() {
        Row() {
          Text('AI 健康助手').fontSize(PAGE_TITLE_SIZE).fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.colors.primaryTextColor)
          Blank()
          CareStatusBadge({ onOpenHome: this.onOpenHome })
        }.width('100%')
        Row({ space: 8 }) {
          Image($r('app.media.ic_shield_blue')).width(18).height(18).supportSvg2(true)
            .colorFilter(careIconTint(this.themeManager.isDarkMode ? '#FFFFFF' : this.palette().solid))
          Text('云端 AI 权限：').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor)
          Text(this.aiAccessLevel === 'full' ? '深度照护'
            : this.aiAccessLevel === 'basic' ? '基础问答' : '隐私保护')
            .fontSize(13).fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.isDarkMode ? '#FFFFFF' : this.palette().solid)
        }
        .width('100%').height(44).padding({ left: 14, right: 14 }).margin({ top: 12 })
        .borderRadius(22).backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .shadow({ radius: 20, offsetY: 10, color: '#1A10231C' })
      }
      .width('100%')
      .padding({ left: PAGE_HORIZONTAL_GUTTER, right: PAGE_HORIZONTAL_GUTTER, top: 16, bottom: 8 })
    }
  }

  @Builder
  LoadingDots(): void {
    Column({ space: 4 }) {
      Text('正在整理建议…')
        .fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
      Row({ space: 5 }) {
        ForEach([0, 1, 2], (i: number) => {
          Text(' ').width(7).height(7)
            .backgroundColor(this.themeManager.isDarkMode ? '#93c5fd' : '#0A5C43').borderRadius(4)
            .scale({ x: this.dotPhase === i ? 1.4 : 1.0, y: this.dotPhase === i ? 1.4 : 1.0 })
            .animation({ duration: 350, curve: Curve.EaseInOut })
        })
      }
    }.padding({ left: 4, right: 4, top: 4, bottom: 4 })
  }

  @Builder
  MessageBubble(msg: BubbleMsg): void {
    Row() {
      if (msg.role === 'user') {
        Blank()
        Text(msg.content)
          .fontSize(16).fontColor('#ffffff').lineHeight(24).fontWeight(FontWeight.Medium)
          .padding({ left: 16, right: 16, top: 12, bottom: 12 })
          .backgroundColor(this.palette().solid)
          .borderRadius({ topLeft: 22, topRight: 8, bottomLeft: 22, bottomRight: 22 })
          .constraintSize({ maxWidth: '72%' })
      } else {
        Column() {
          if (msg.isLoading) {
            this.LoadingDots()
          } else {
            Text('AI生成内容')
              .fontSize(11)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .alignSelf(ItemAlign.Start)
              .margin({ bottom: 4 })
            Text(msg.content)
              .fontSize(16)
              .fontColor(this.themeManager.colors.primaryTextColor)
              .lineHeight(25)
          }
        }
        .padding({ left: 16, right: 16, top: 12, bottom: 14 })
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .borderRadius({ topLeft: 8, topRight: 22, bottomLeft: 22, bottomRight: 22 })
        .shadow({ radius: 24, offsetY: 12, color: this.themeManager.isDarkMode ? '#40000000' : '#1A10231C' })
        .constraintSize({ maxWidth: '80%' })
        Blank()
      }
    }
    .width('100%').padding({ left: '5%', right: '5%', top: 6, bottom: 6 })
  }

  @Builder
  QuickChip(q: string): void {
    Text(q)
      .fontSize(14).fontColor(this.themeManager.colors.primaryTextColor)
      .padding({ left: 16, right: 16, top: 10, bottom: 10 })
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .borderRadius(99).shadow({ radius: 12, offsetY: 6, color: '#1410231C' })
      .onClick((): void => {
        if (!this.isRequesting) this.sendMessage(q);
      })
  }

  @Builder
  QuickQuestions(): void {
    Column() {
      Text('快捷提问').fontSize(12)
        .fontColor(this.themeManager.colors.secondaryTextColor)
        .margin({ left: 18, bottom: 8 }).alignSelf(ItemAlign.Start)
      if (getWindowSizeClass(this.viewportWidth) === 'compact') {
        // 手机宽度放不下，横向滑动
        Scroll(new Scroller()) {
          Row({ space: 10 }) {
            ForEach(QUICK_QUESTIONS, (q: string) => {
              this.QuickChip(q)
            })
          }.padding({ left: 18, right: 18, top: 2, bottom: 10 })
        }.scrollable(ScrollDirection.Horizontal).scrollBar(BarState.Off)
      } else {
        // 大屏直接折行铺开，不留半截被截断的提问
        Flex({ wrap: FlexWrap.Wrap, justifyContent: FlexAlign.Start }) {
          ForEach(QUICK_QUESTIONS, (q: string) => {
            Row() { this.QuickChip(q) }.margin({ right: 10, bottom: 8 })
          })
        }.width('100%').padding({ left: 18, right: 18 })
      }
    }
    .width('100%').constraintSize({ maxWidth: 640 })
    .margin({ bottom: 6 })
  }

  @Builder
  AiDisclaimer(): void {
    Row({ space: 4 }) {
      Text('AI').fontSize(10).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.secondaryTextColor)
      Text('内容由 AI 生成，仅供参考，不替代专业医疗诊断')
        .fontSize(11)
        .fontColor(this.themeManager.colors.secondaryTextColor)
    }
    .width('100%')
    .justifyContent(FlexAlign.Center)
    .padding({ top: 4, bottom: 6 })
  }

  @Builder
  InputBar(): void {
    Row({ space: 12 }) {
      TextInput({ text: this.inputText, placeholder: '问点什么…' })
        .maxLength(2000)
        .layoutWeight(1).height(50).fontSize(16)
        .backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .borderRadius(25).padding({ left: 18, right: 18 })
        .caretColor(this.palette().solid)
        .shadow({ radius: 16, offsetY: 8, color: '#1410231C' })
        .placeholderColor(this.themeManager.colors.secondaryTextColor)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .onChange((val: string): void => { this.inputText = val; })
        .onSubmit((): void => { this.sendMessage(this.inputText); })
        .enabled(!this.isRequesting && this.policyReady)
      Stack() {
        if (this.isRequesting) {
          LoadingProgress().width(22).height(22).color('#ffffff')
        } else {
          Text('↑').fontSize(20).fontColor('#ffffff').fontWeight(FontWeight.Bold)
        }
      }
      .width(50).height(50)
      .backgroundColor(this.palette().solid)
      .opacity(this.inputText.trim().length > 0 && !this.isRequesting ? 1 : 0.5)
      .borderRadius(25).animation({ duration: 200, curve: Curve.EaseOut })
      .onClick((): void => { this.sendMessage(this.inputText); })
    }
    .width('100%').constraintSize({ maxWidth: 640 })
    .padding({ left: 16, right: 16, top: 8, bottom: 16 })
  }

  build() {
    Column() {
      this.GradientHeader()
      Scroll(this.scroller) {
        Column({ space: 0 }) {
          ForEach(this.messages, (msg: BubbleMsg) => {
            this.MessageBubble(msg)
          }, (msg: BubbleMsg) => `${msg.id}_${msg.isLoading ? 'L' : msg.content.length}`)
          Column().height(16)
        }.width('100%').constraintSize({ maxWidth: 640 }).padding({ top: 12 })
      }
      .layoutWeight(1).scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
      .onDidScroll((_x: number, y: number, state: ScrollState): void => { this.onTabScroll(y, state); })
      this.QuickQuestions()
      this.AiDisclaimer()
      this.InputBar()
    }
    .width('100%').height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
    .onAreaChange((_oldValue: Area, newValue: Area): void => {
      const width = Number(newValue.width);
      if (width > 0) this.viewportWidth = width;
    })
  }
}
