import { ThemeManager } from '../common/ThemeManager';
import { UserManager } from '../common/UserManager';
import { AddressService, SavedAddress, AddressDraft, AddressIdentity, AddressResult } from '../common/AddressService';
import { GradientHeader, ICON_FRAME_SIZE, PAGE_HORIZONTAL_GUTTER, PAGE_TITLE_SIZE, SURFACE_RADIUS } from '../components/GradientHeader';
import { showToast, showDialog } from '../common/UiFeedback';

@Builder
export function MyAddressBuilder(): void { MyAddress(); }

@Component
export struct MyAddress {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;
  pathStack: NavPathStack = new NavPathStack();
  @State addresses: SavedAddress[] = [];
  @State loading: boolean = true;
  @State busy: boolean = false;
  @State editing: boolean = false;
  @State offline: boolean = false;
  @State loadError: string = '';
  @State formError: string = '';
  @State detail: string = '';
  @State makeDefault: boolean = false;
  private originalDraft: string = '';
  private currentUser: string = '';
  private disposed: boolean = false;
  private requestVersion: number = 0;
  private inputFocused: boolean = false;

  private finishInput(): void { this.getUIContext().getFocusController().clearFocus(); }

  aboutToAppear(): void {
    this.disposed = false;
    this.currentUser = UserManager.getInstance().getCurrentUsername();
    this.loadAddresses();
  }
  aboutToDisappear(): void { this.disposed = true; this.requestVersion++; }

  private active(): boolean {
    return !this.disposed && this.currentUser !== '' &&
      UserManager.getInstance().getCurrentUsername() === this.currentUser;
  }

  private async loadAddresses(): Promise<void> {
    if (this.busy) return;
    const version = ++this.requestVersion;
    this.loading = true;
    this.loadError = '';
    try {
      const cached = await AddressService.cached(this.currentUser);
      if (!this.active() || version !== this.requestVersion) return;
      if (cached !== null) this.addresses = cached;
      const result = await AddressService.list();
      if (!this.active() || version !== this.requestVersion) return;
      this.addresses = result.addresses;
      this.offline = false;
      const cachedOk = await AddressService.cache(this.currentUser, result);
      if (!cachedOk && this.active()) showToast(this.getUIContext(), { message: '云端已读取，本机离线副本暂未更新' });
    } catch (error) {
      if (!this.active() || version !== this.requestVersion) return;
      this.offline = true;
      this.loadError = (error as Error).message || '地址加载失败，请重试';
    } finally {
      if (this.active() && version === this.requestVersion) this.loading = false;
    }
  }

  private draftKey(): string {
    return JSON.stringify([this.detail, this.makeDefault]);
  }

  private beginAdd(): void {
    if (this.busy || this.offline) return;
    this.detail = '';
    this.makeDefault = this.addresses.length === 0;
    this.formError = '';
    this.originalDraft = this.draftKey();
    this.editing = true;
  }

  private async leaveEdit(): Promise<void> {
    if (this.busy) return;
    if (this.originalDraft !== this.draftKey()) {
      const choice = await showDialog(this.getUIContext(), {
        title: '放弃未保存的修改？', message: '本次填写的内容还没有保存。',
        buttons: [{ text: '继续填写', color: '#2563eb' },
          { text: '放弃修改', color: this.themeManager.colors.secondaryTextColor }],
      });
      if (choice === undefined || choice.index !== 1) return;
    }
    this.editing = false;
    this.formError = '';
  }

  private draft(): AddressDraft | undefined {
    const detail = this.detail.trim();
    if (detail.length < 5 || detail.length > 300) { this.formError = '请填写5至300字的详细地址'; return undefined; }
    // Keep the existing API contract; name/coordinates are no longer user inputs.
    const existing = this.addresses.find((address: SavedAddress): boolean => address.detail.trim() === detail);
    const value: AddressDraft = { label: existing?.label || '常用住处', detail,
      latitude: existing?.latitude ?? null, longitude: existing?.longitude ?? null,
      isDefault: this.makeDefault || (existing?.isDefault ?? false) };
    if (existing !== undefined) { value.id = existing.id; value.version = existing.version; }
    return value;
  }

  private async apply(action: string, body: Object, message: string): Promise<void> {
    if (this.busy || !this.active()) return;
    this.busy = true;
    this.formError = '';
    try {
      const result = await AddressService.request(action, body);
      if (!this.active()) return;
      this.addresses = result.addresses;
      this.editing = false;
      this.offline = false;
      this.loadError = '';
      const cached = await AddressService.cache(this.currentUser, result);
      if (this.active()) showToast(this.getUIContext(), {
        message: cached ? message : `${message}（云端成功，本机离线副本暂未更新）`,
      });
    } catch (error) {
      if (!this.active()) return;
      const message = (error as Error).message || '地址操作失败，请重试';
      if (this.editing) this.formError = message;
      else showToast(this.getUIContext(), { message: message });
    } finally { if (this.active()) this.busy = false; }
  }

  private async save(): Promise<void> {
    if (this.busy) return;
    this.finishInput();
    const draft = this.draft();
    if (draft !== undefined) await this.apply('save', draft, '住处已保存');
  }

  private setDefault(address: SavedAddress): void {
    const identity: AddressIdentity = { id: address.id, version: address.version };
    this.apply('default', identity, '默认地址已更新');
  }

  @Builder
  PageHeader(): void {
    GradientHeader({ contentMaxWidth: 640 }) {
      Row() {
        Image($r('app.media.ic_chevron_right')).width(ICON_FRAME_SIZE).height(ICON_FRAME_SIZE).padding(9)
          .objectFit(ImageFit.Contain).backgroundColor('#33FFFFFF').borderRadius(20).rotate({ angle: 180 })
          .accessibilityText('返回').onClick((): void => {
            if (this.editing) this.leaveEdit(); else if (!this.busy) this.pathStack.pop();
          })
        Text('常用地址').fontSize(PAGE_TITLE_SIZE).fontWeight(FontWeight.Bold).fontColor('#ffffff')
          .margin({ left: 12 }).layoutWeight(1)
        Button(this.editing ? this.busy ? '保存中…' : '保存' : this.loading ? '读取中' : '刷新', { type: ButtonType.Normal })
          .height(44).fontSize(14).fontColor('#ffffff').backgroundColor('#1e40af').borderRadius(12)
          .enabled(!this.busy && !this.loading && (!this.editing || !this.offline))
          .accessibilityText(this.editing ? '保存详细地址' : '刷新常用地址')
          .onClick((): void => { if (this.editing) this.save(); else this.loadAddresses(); })
      }.width('100%')
        .padding({ left: PAGE_HORIZONTAL_GUTTER, right: PAGE_HORIZONTAL_GUTTER, top: this.topSafeHeight + 8, bottom: 12 })
    }
  }

  @Builder
  AddressCard(address: SavedAddress): void {
    Column({ space: 12 }) {
      Row({ space: 10 }) {
        Image($r('app.media.ic_map_pin_green')).width(28).height(28).objectFit(ImageFit.Contain)
        Text(address.detail).fontSize(16).fontWeight(FontWeight.Medium).lineHeight(24)
          .fontColor(this.themeManager.colors.primaryTextColor).layoutWeight(1)
        if (address.isDefault) {
          Text('默认住处').fontSize(12).fontColor(this.themeManager.colors.linkTextColor).padding({ left: 8, right: 8, top: 4, bottom: 4 })
            .backgroundColor(this.themeManager.isDarkMode ? '#17315a' : '#dbeafe').borderRadius(6)
        }
      }.width('100%')
      if (!address.isDefault) {
          Button('设为默认', { type: ButtonType.Normal }).height(44).fontSize(14).width('100%')
            .backgroundColor(this.themeManager.colors.secondaryBackgroundColor).fontColor(this.themeManager.colors.linkTextColor)
            .borderRadius(10).onClick((): void => { this.setDefault(address); })
            .enabled(!this.busy && !this.offline)
      }
    }.alignItems(HorizontalAlign.Start).width('100%').padding(16).borderRadius(SURFACE_RADIUS)
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .border({ width: 1, color: this.themeManager.colors.borderColor })
  }

  @Builder
  EditForm(): void {
    Column({ space: 14 }) {
      Text('保存常用地址').fontSize(19).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor).width('100%')
      if (this.formError !== '') {
        Text(this.formError).fontSize(13).fontColor(this.themeManager.colors.dangerTextColor).width('100%')
      }
      Column({ space: 7 }) {
        Text('详细地址（必填）').fontSize(14).fontColor(this.themeManager.colors.primaryTextColor)
        TextArea({ placeholder: '省 / 市 / 区 / 街道 / 小区 / 楼栋门牌', text: this.detail })
          .fontColor(this.themeManager.colors.primaryTextColor).backgroundColor(this.themeManager.colors.secondaryBackgroundColor)
          .placeholderColor(this.themeManager.colors.secondaryTextColor)
          .height(104).maxLength(300).fontSize(15).onChange((value: string): void => { this.detail = value; })
          .onFocus((): void => { this.inputFocused = true; }).onBlur((): void => { this.inputFocused = false; })
      }.width('100%').alignItems(HorizontalAlign.Start)
      Row() {
        Text('设为默认住处').fontSize(15).fontColor(this.themeManager.colors.primaryTextColor).layoutWeight(1)
        Toggle({ type: ToggleType.Switch, isOn: this.makeDefault }).selectedColor('#2563eb')
          .accessibilityText('设为默认住处').enabled(!this.busy && this.addresses.length > 0)
          .onChange((value: boolean): void => { this.makeDefault = value; })
      }.width('100%').height(48)
    }.width('100%').padding(16).alignItems(HorizontalAlign.Start).enabled(!this.busy)
      .backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius(SURFACE_RADIUS)
  }

  build() {
    NavDestination() {
      Column() {
        this.PageHeader()
        Scroll() {
          Column({ space: 14 }) {
            if (this.loading) {
              Column({ space: 12 }) {
                LoadingProgress().width(38).height(38)
                Text('正在读取常用地址').fontSize(14).fontColor(this.themeManager.colors.secondaryTextColor)
              }.width('100%').height(200).justifyContent(FlexAlign.Center)
            } else if (this.editing) {
              this.EditForm()
            } else {
              if (this.loadError !== '') {
                Text(this.addresses.length > 0 ? '离线副本 · 联网刷新后可保存和设置默认住处' : this.loadError)
                  .fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).width('100%')
              }
              if (this.addresses.length === 0) {
                Column({ space: 12 }) {
                  Image($r('app.media.ic_map_pin_green')).width(48).height(48).objectFit(ImageFit.Contain)
                  Text(this.loadError === '' ? '还没有保存常用住处' : '暂时无法读取地址').fontSize(18).fontWeight(FontWeight.Medium)
                    .fontColor(this.themeManager.colors.primaryTextColor)
                  Text(this.loadError === '' ? '填写详细地址，保存后可设为默认住处。' : '请联网后点击右上角刷新。').fontSize(13)
                    .fontColor(this.themeManager.colors.secondaryTextColor).textAlign(TextAlign.Center)
                }.width('100%').height(230).justifyContent(FlexAlign.Center)
              } else {
                Text(`已保存 ${this.addresses.length} / 20 个住处`).fontSize(13)
                  .fontColor(this.themeManager.colors.secondaryTextColor).width('100%')
                ForEach(this.addresses, (address: SavedAddress) => { this.AddressCard(address) },
                  (address: SavedAddress): string => `${address.id}-${address.version}`)
              }
              Button('添加常用住处', { type: ButtonType.Normal }).width('100%').height(50).fontSize(16)
                .backgroundColor('#2563eb').fontColor('#ffffff').borderRadius(12)
                .enabled(!this.busy && !this.offline && this.addresses.length < 20)
                .onClick((): void => { this.beginAdd(); })
            }
          }.width('100%').constraintSize({ maxWidth: 640 }).padding({ left: 16, right: 16, top: 16, bottom: 28 })
        }.layoutWeight(1).width('100%').align(Alignment.Top)
          .scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
      }.width('100%').height('100%').backgroundColor(this.themeManager.colors.cardBackgroundColor)
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }.hideTitleBar(true)
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
      .onBackPressed((): boolean => {
        if (this.inputFocused) { this.finishInput(); return true; }
        if (this.busy) return true;
        if (this.editing) { this.leaveEdit(); return true; }
        return false;
      })
      .onReady((context: NavDestinationContext): void => { this.pathStack = context.pathStack; })
  }
}
