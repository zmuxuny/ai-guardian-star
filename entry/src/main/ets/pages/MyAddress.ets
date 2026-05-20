/**
 * MyAddress.ets — 地址编辑页
 * 从数据库加载当前用户地址，可编辑，保存到本地 RDB + 云端同步
 */
import { ThemeManager } from '../common/ThemeManager';
import { DatabaseHelper, UserInfo } from '../database/DatabaseHelper';
import { UserManager } from '../common/UserManager';
import { CloudService, CloudUpdateFields } from '../common/CloudService';
import { GradientHeader } from '../components/GradientHeader';
import { promptAction } from '@kit.ArkUI';

@Builder
export function MyAddressBuilder() {
  MyAddress();
}

@Component
export struct MyAddress {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  pathStack: NavPathStack = new NavPathStack();
  @StorageProp("topSafeHeight") topSafeHeight: number = 48;

  @State address: string = '';
  @State originalAddress: string = '';
  @State isLoading: boolean = true;
  @State isSaving: boolean = false;
  @State isEditing: boolean = false;   // 是否处于编辑态（展示卡片 ↔ 编辑表单）

  private currentUser: string = '';
  private loadedUser: UserInfo | null = null;

  aboutToAppear(): void {
    this.currentUser = UserManager.getInstance().getCurrentUsername();
    this.loadAddress();
  }

  private loadAddress(): void {
    this.isLoading = true;
    const db = DatabaseHelper.getInstance();
    db.queryUserByIdentifier(this.currentUser)
      .then((user: UserInfo | null) => {
        this.isLoading = false;
        if (user) {
          this.loadedUser = user;
          this.address = user.address ?? '';
          this.originalAddress = this.address;
        }
      })
      .catch(() => { this.isLoading = false; });
  }

  private maskPhone(phone: string): string {
    if (!phone || phone.length < 7) return phone;
    return phone.substring(0, 3) + '****' + phone.substring(phone.length - 4);
  }

  private enterEdit(): void {
    this.address = this.originalAddress;
    this.isEditing = true;
  }

  private cancelEdit(): void {
    this.address = this.originalAddress;
    this.isEditing = false;
  }

  // 保存：云端优先（成功后再写本地），避免本地/云端分叉；不退页，停在卡片视图
  private async saveAddress(): Promise<void> {
    const newAddr = this.address.trim();
    if (newAddr === '') { promptAction.showToast({ message: '请输入地址' }); return; }
    const user = this.loadedUser;
    if (!user || user.id === undefined) {
      promptAction.showToast({ message: '用户信息未加载，请返回重试' });
      return;
    }
    this.isSaving = true;
    try {
      // 1) 先同步云端
      const fields = new CloudUpdateFields();
      fields.username = this.currentUser;
      fields.address = newAddr;
      const cloudR = await CloudService.getInstance().updateUser(fields);
      if (!cloudR.success) {
        promptAction.showToast({ message: cloudR.message === '网络不可用' ? '网络不可用，请检查后重试' : '云端同步失败：' + cloudR.message });
        this.isSaving = false;
        return;
      }
      // 2) 云端成功，再写本地
      user.address = newAddr;
      await DatabaseHelper.getInstance().updateUser(user);
      this.originalAddress = newAddr;
      this.isEditing = false;
      promptAction.showToast({ message: '地址已保存', duration: 1500 });
    } catch (e) {
      console.error('[MyAddress]: 保存失败', JSON.stringify(e));
      promptAction.showToast({ message: '保存失败，请重试' });
    }
    this.isSaving = false;
  }

  @Builder
  GradientHeader(): void {
    GradientHeader() {
      Row() {
        Image($r("app.media.ic_chevron_right")).width(36).height(36)
          .objectFit(ImageFit.Contain).padding(8)
          .backgroundColor("#33FFFFFF").borderRadius(100).rotate({ angle: 180 })
          .onClick((): void => { this.pathStack.pop(); })
        Text("我的地址").fontSize(22).fontWeight(FontWeight.Bold).fontColor("#ffffff")
          .margin({ left: "5%" }).layoutWeight(1)
      }
      .width("100%").padding({ left: "4%", right: "4%", top: this.topSafeHeight })
    }
  }

  // ── 地址卡片（仿京东收货地址：联系人 + 电话 + 地址 + 默认/家庭标签）──
  @Builder
  AddressCard(): void {
    Column() {
      Row() {
        // 左侧定位图标
        Column() {
          Image($r("app.media.ic_map_pin_green")).width(22).height(22).objectFit(ImageFit.Contain)
        }
        .width(40).height(40).borderRadius(20)
        .backgroundColor(this.themeManager.isDarkMode ? '#14302a' : '#f0fdf4')
        .justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
        .margin({ right: 12 })

        Column() {
          // 联系人 + 电话
          Row() {
            Text((this.loadedUser && this.loadedUser.username) ? this.loadedUser.username : '家庭住址')
              .fontSize(16).fontWeight(FontWeight.Bold)
              .fontColor(this.themeManager.colors.primaryTextColor)
            if (this.loadedUser && this.loadedUser.phone) {
              Text(this.maskPhone(this.loadedUser.phone))
                .fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor)
                .margin({ left: 10 })
            }
          }.width('100%')

          // 标签 + 地址
          Row() {
            Text('默认').fontSize(10).fontColor('#ffffff')
              .padding({ left: 6, right: 6, top: 2, bottom: 2 })
              .backgroundColor('#3b82f6').borderRadius(4).margin({ right: 6 })
            Text('家庭').fontSize(10).fontColor('#10b981')
              .padding({ left: 6, right: 6, top: 2, bottom: 2 })
              .border({ width: 1, color: '#10b981' }).borderRadius(4)
          }.width('100%').margin({ top: 8 })

          Text(this.originalAddress)
            .fontSize(14).fontColor(this.themeManager.colors.primaryTextColor)
            .lineHeight(20).margin({ top: 8 }).width('100%')
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)

        // 编辑笔
        Text('✎').fontSize(16).fontColor('#3b82f6').padding(8)
          .onClick(() => { this.enterEdit(); })
      }
      .width('100%').alignItems(VerticalAlign.Top)
    }
    .width('92%').padding(16).margin({ top: 16 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius(14)
    .shadow({ radius: 8, color: '#0000000F', offsetY: 4 })
    // 左侧高亮色条，呼应京东默认地址的强调样式
    .border({ width: { left: 3 }, color: '#3b82f6' })
  }

  // ── 空状态 ──
  @Builder
  EmptyState(): void {
    Column() {
      Column() {
        Image($r("app.media.ic_map_pin_green")).width(40).height(40).objectFit(ImageFit.Contain)
      }
      .width(80).height(80).borderRadius(40)
      .backgroundColor(this.themeManager.isDarkMode ? '#14302a' : '#f0fdf4')
      .justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center).margin({ top: 60 })

      Text('还没有添加家庭地址').fontSize(15).fontWeight(FontWeight.Medium)
        .fontColor(this.themeManager.colors.primaryTextColor).margin({ top: 20 })
      Text('用于紧急情况时快速定位').fontSize(12)
        .fontColor(this.themeManager.colors.tertiaryTextColor).margin({ top: 6 })

      Button('添加家庭地址').height(46).width('70%').type(ButtonType.Capsule)
        .fontSize(15).fontColor('#ffffff').margin({ top: 28 })
        .linearGradient({ direction: GradientDirection.Right, colors: [['#1e40af', 0.0], ['#3b82f6', 1.0]] })
        .onClick(() => { this.enterEdit(); })
    }
    .width('100%').alignItems(HorizontalAlign.Center)
  }

  // ── 编辑表单 ──
  @Builder
  EditForm(): void {
    Column() {
      Text('家庭地址').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
        .alignSelf(ItemAlign.Start).margin({ left: '4%', bottom: 10, top: 20 })
      Column() {
        TextArea({ placeholder: '请输入详细地址，如省/市/区/街道/门牌号', text: this.address })
          .fontSize(15).fontColor(this.themeManager.colors.primaryTextColor)
          .placeholderColor(this.themeManager.colors.tertiaryTextColor)
          .backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .border({ width: 1.5, color: this.themeManager.isDarkMode ? '#334155' : '#e2e8f0' })
          .borderRadius(12).padding(16).height(140).width('100%')
          .onChange((v: string) => { this.address = v; })
      }.width('92%')
      Text('用于紧急情况时提供位置信息').fontSize(11)
        .fontColor(this.themeManager.colors.tertiaryTextColor)
        .width('92%').textAlign(TextAlign.Start).margin({ top: 8 })

      Row({ space: 12 }) {
        // 已有地址时才显示取消（空状态首次添加不需要）
        if (this.originalAddress !== '') {
          Button('取消').layoutWeight(1).height(46).type(ButtonType.Capsule)
            .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9')
            .fontColor(this.themeManager.colors.secondaryTextColor).fontSize(15)
            .onClick(() => { this.cancelEdit(); })
        }
        Button(this.isSaving ? '保存中…' : '保存').layoutWeight(1).height(46).type(ButtonType.Capsule)
          .enabled(!this.isSaving)
          .linearGradient({ direction: GradientDirection.Right,
            colors: [[this.isSaving ? '#94a3b8' : '#1e40af', 0.0], [this.isSaving ? '#94a3b8' : '#3b82f6', 1.0]] })
          .fontColor('#ffffff').fontSize(15)
          .onClick(() => { this.saveAddress(); })
      }.width('92%').margin({ top: 24 })
    }
    .width('100%').alignItems(HorizontalAlign.Center)
  }

  build() {
    NavDestination() {
      Column() {
        this.GradientHeader()
        Scroll() {
          Column() {
            if (this.isLoading) {
              Column() { LoadingProgress().width(36).height(36) }
                .width('100%').height(200).justifyContent(FlexAlign.Center)
            } else if (this.isEditing) {
              this.EditForm()
            } else if (this.originalAddress !== '') {
              this.AddressCard()
            } else {
              this.EmptyState()
            }
            Column().height(40)
          }
          .width('100%').alignItems(HorizontalAlign.Center)
        }
        .layoutWeight(1).scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring).width('100%')
      }
      .width('100%').height('100%')
    }
    .hideTitleBar(true)
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .onBackPressed(() => {
      // 编辑态且有改动 → 退回卡片视图而非直接退页
      if (this.isEditing && this.address.trim() !== this.originalAddress) {
        this.cancelEdit();
        return true;
      }
      return false;
    })
    .onReady((context: NavDestinationContext) => { this.pathStack = context.pathStack; })
  }
}
