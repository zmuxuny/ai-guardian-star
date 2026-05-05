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
  @State hasChanged: boolean = false;

  private currentUser: string = '';

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
          this.address = user.address ?? '';
          this.originalAddress = this.address;
        }
      })
      .catch(() => { this.isLoading = false; });
  }

  private updateChangedState(): void {
    this.hasChanged = this.address.trim() !== this.originalAddress;
  }

  private async saveAddress(): Promise<void> {
    this.isSaving = true;
    const db = DatabaseHelper.getInstance();
    try {
      const user = await db.queryUserByIdentifier(this.currentUser);
      if (!user || user.id === undefined) {
        promptAction.showToast({ message: '用户信息异常' });
        this.isSaving = false;
        return;
      }
      user.address = this.address.trim();
      await db.updateUser(user);
      // 云端同步（失败静默降级）
      const fields = new CloudUpdateFields();
      fields.username = this.currentUser;
      fields.address = this.address.trim();
      CloudService.getInstance().updateUser(fields).then(r => {
        console.info('[MyAddress]: 云端同步', r.success ? '成功' : '失败:' + r.message);
      });
      this.originalAddress = this.address.trim();
      this.updateChangedState();
      promptAction.showToast({ message: '保存好啦', duration: 1500 });
      setTimeout(() => { this.pathStack.pop(); }, 1000);
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
        Text("保存").fontSize(15).fontColor("#ffffff")
          .padding({ left: 14, right: 14, top: 6, bottom: 6 })
          .backgroundColor("#33FFFFFF").borderRadius(20)
          .opacity(this.hasChanged ? 1 : 0.5)
          .onClick((): void => {
            if (!this.hasChanged) { promptAction.showToast({ message: '你还没有进行修改' }); }
            else { this.saveAddress(); }
          })
      }
      .width("100%").padding({ left: "4%", right: "4%", top: this.topSafeHeight })
    }
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
            } else {
              Text('家庭地址').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
                .alignSelf(ItemAlign.Start).margin({ left: '4%', bottom: 10, top: 20 })
              Column() {
                TextArea({ placeholder: '请输入详细地址，如省/市/区/街道/门牌号', text: this.address })
                  .fontSize(15).fontColor(this.themeManager.colors.primaryTextColor)
                  .placeholderColor(this.themeManager.colors.tertiaryTextColor)
                  .backgroundColor(this.themeManager.colors.cardBackgroundColor)
                  .border({ width: 1.5, color: this.themeManager.isDarkMode ? '#334155' : '#e2e8f0' })
                  .borderRadius(12).padding(16).height(140).width('100%')
                  .onChange((v: string) => { this.address = v; this.updateChangedState(); })
              }
              .width('92%')
              Text('用于紧急情况时提供位置信息').fontSize(11)
                .fontColor(this.themeManager.colors.tertiaryTextColor)
                .width('92%').textAlign(TextAlign.Start).margin({ top: 8 })
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
      if (this.hasChanged) {
        AlertDialog.show({
          title: '提示', message: '有未保存的修改，是否保存？',
          primaryButton: { value: '不保存', action: () => { this.pathStack.pop(); } },
          secondaryButton: { value: '保存', action: () => { this.saveAddress(); } },
          cancel: () => {}, alignment: DialogAlignment.Center,
        });
        return true;
      }
      return false;
    })
    .onReady((context: NavDestinationContext) => { this.pathStack = context.pathStack; })
  }
}
