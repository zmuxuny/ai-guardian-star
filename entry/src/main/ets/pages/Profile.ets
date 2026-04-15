/**
 * Profile.ets — 个人资料编辑页
 * 合并了头像编辑 + 昵称编辑，支持从相册选图、深色模式适配、保存至数据库
 */
import { ThemeManager } from '../common/ThemeManager';
import { DatabaseHelper, UserInfo } from '../database/DatabaseHelper';
import { UserManager } from '../common/UserManager';
import { promptAction } from '@kit.ArkUI';
import { common, abilityAccessCtrl } from '@kit.AbilityKit';
import { photoAccessHelper } from '@kit.MediaLibraryKit';
import fs from '@ohos.file.fs';

@Builder
export function ProfileBuilder() {
  Profile();
}

@Component
export struct Profile {
  pathStack: NavPathStack = new NavPathStack();
  @State themeManager: ThemeManager = ThemeManager.getInstance();

  // ── 表单状态 ──────────────────────────────────────────────
  @State nickname: string = '';
  @State avatarPath: string = '';        // 沙箱内头像文件路径，空则显示默认图标
  @State originalNickname: string = '';  // 用于判断是否有改动
  @State originalAvatarPath: string = '';
  @State isLoading: boolean = false;
  @State isSaving: boolean = false;

  // ── 动画状态 ──────────────────────────────────────────────
  @State avatarScale: number = 1.0;
  @State saveBtnScale: number = 1.0;
  @State nicknameError: string = '';

  private currentUser: string = '';

  aboutToAppear(): void {
    this.currentUser = UserManager.getInstance().getCurrentUsername();
    this.loadProfile();
  }

  /** 从数据库加载当前用户资料 */
  private loadProfile(): void {
    this.isLoading = true;
    DatabaseHelper.getInstance().queryUserByUsername(this.currentUser)
      .then((user: UserInfo | null) => {
        this.isLoading = false;
        if (user) {
          // 昵称：优先 DB，其次 AppStorage
          const storedNick = AppStorage.get<string>('loggedInNickname') ?? '';
          this.nickname = (user.nickname && user.nickname.trim() !== '')
            ? user.nickname
            : (storedNick !== '' ? storedNick : this.currentUser);
          this.avatarPath = user.avatarPath ?? '';
          this.originalNickname = this.nickname;
          this.originalAvatarPath = this.avatarPath;
        }
      })
      .catch(() => { this.isLoading = false; });
  }

  /** 校验昵称 */
  private validateNickname(): string {
    const v = this.nickname.trim();
    if (v.length < 2) return '昵称至少 2 个字';
    if (v.length > 12) return '昵称最多 12 个字';
    return '';
  }

  /** 申请相册权限 + 调起图片选择器 */
  private async pickAvatar(): Promise<void> {
    const context = getContext(this) as common.UIAbilityContext;

    // 运行时申请相册权限（API 20 正确权限名）
    const atManager = abilityAccessCtrl.createAtManager();
    const grant = await atManager.requestPermissionsFromUser(
      context, ['ohos.permission.READ_IMAGEVIDEO']
    );
    if (grant.authResults[0] !== 0) {
      promptAction.showToast({ message: '需要相册权限，请在设置中开启' });
      return;
    }

    // 直接调起 PhotoViewPicker，不需要 getAssets
    const picker = new photoAccessHelper.PhotoViewPicker();
    const selectOptions = new photoAccessHelper.PhotoSelectOptions();
    selectOptions.MIMEType = photoAccessHelper.PhotoViewMIMETypes.IMAGE_TYPE;
    selectOptions.maxSelectNumber = 1;

    try {
      const pickerResult = await picker.select(selectOptions);
      if (!pickerResult || pickerResult.photoUris.length === 0) return;
      const sourceUri = pickerResult.photoUris[0];
      await this.copyAvatarToSandbox(context, sourceUri);
    } catch (e) {
      console.error('[Profile]: 选图失败', JSON.stringify(e));
      promptAction.showToast({ message: '选取图片失败，请重试' });
    }
  }

  /** 把选中的图片复制到应用沙箱，更新 avatarPath */
  private async copyAvatarToSandbox(
    context: common.UIAbilityContext,
    sourceUri: string
  ): Promise<void> {
    try {
      const avatarDir = context.filesDir + '/avatars';
      try { fs.mkdirSync(avatarDir); } catch (_e) {}

      const destPath = avatarDir + '/avatar_' + this.currentUser + '.jpg';
      // PhotoViewPicker 返回的是 file:// URI，直接用 fs.copyFile 的 URI 重载
      await fs.copyFile(sourceUri, destPath);
      // 触发 UI 刷新——先清空再赋值，强制 Image 组件重新加载
      this.avatarPath = '';
      setTimeout(() => { this.avatarPath = destPath; }, 50);
    } catch (e) {
      console.error('[Profile]: 复制头像失败', JSON.stringify(e));
      promptAction.showToast({ message: '处理图片失败，请重试' });
    }
  }

  /** 保存到数据库 */
  private async saveProfile(): Promise<void> {
    const err = this.validateNickname();
    if (err !== '') {
      this.nicknameError = err;
      return;
    }
    this.nicknameError = '';
    this.isSaving = true;

    const db = DatabaseHelper.getInstance();
    try {
      const user = await db.queryUserByUsername(this.currentUser);
      if (!user || user.id === undefined) throw new Error('用户不存在');

      user.nickname = this.nickname.trim();
      user.avatarPath = this.avatarPath;
      await db.updateUser(user);

      // 同步更新 AppStorage，让个人页即时刷新
      AppStorage.setOrCreate<string>('loggedInNickname', this.nickname.trim());
      AppStorage.setOrCreate<string>('loggedInAvatarPath', this.avatarPath);

      this.isSaving = false;
      this.originalNickname = this.nickname.trim();
      this.originalAvatarPath = this.avatarPath;

      promptAction.showToast({ message: '保存成功 ✓', duration: 1500 });
      setTimeout(() => { this.pathStack.pop(); }, 800);
    } catch (e) {
      this.isSaving = false;
      console.error('[Profile]: 保存失败', JSON.stringify(e));
      promptAction.showToast({ message: '保存失败，请重试' });
    }
  }

  /** 是否有未保存的改动 */
  private get hasChanged(): boolean {
    return this.nickname.trim() !== this.originalNickname ||
      this.avatarPath !== this.originalAvatarPath;
  }


  // ── 自定义标题栏 ─────────────────────────────────────────
  @Builder
  TitleBar(): void {
    Stack({ alignContent: Alignment.Center }) {
      Text('个人资料')
        .fontSize(17)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)

      Row() {
        Blank()
        if (this.isSaving) {
          LoadingProgress()
            .width(20).height(20).color('#3b82f6')
            .margin({ right: 16 })
        } else {
          Text('保存')
            .fontSize(16)
            .fontColor(this.hasChanged ? '#3b82f6' : this.themeManager.colors.tertiaryTextColor)
            .fontWeight(FontWeight.Medium)
            .padding({ left: 16, right: 16, top: 10, bottom: 10 })
            .enabled(this.hasChanged && !this.isSaving)
            .onClick(() => {
              this.saveBtnScale = 0.9;
              setTimeout(() => { this.saveBtnScale = 1.0; }, 120);
              this.saveProfile();
            })
            .scale({ x: this.saveBtnScale, y: this.saveBtnScale })
            .animation({ duration: 120, curve: Curve.EaseInOut })
        }
      }.width('100%')
    }
    .width('100%').height(56)
  }

  // ── 头像区域 ──────────────────────────────────────────────
  @Builder
  AvatarSection(): void {
    Column() {
      // 头像圆形区域
      Stack({ alignContent: Alignment.BottomEnd }) {
        // 头像图或默认图标
        if (this.avatarPath !== '') {
          Image(this.avatarPath)
            .width(100).height(100)
            .borderRadius(50)
            .objectFit(ImageFit.Cover)
            .border({ width: 3, color: this.themeManager.isDarkMode ? '#1e3a5f' : '#bfdbfe' })
        } else {
          Column() {
            Image($r('app.media.ic_user'))
              .width(52).height(52)
              .objectFit(ImageFit.Contain)
          }
          .width(100).height(100)
          .borderRadius(50)
          .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#dbeafe')
          .justifyContent(FlexAlign.Center)
          .alignItems(HorizontalAlign.Center)
          .border({ width: 3, color: this.themeManager.isDarkMode ? '#1e3a5f' : '#bfdbfe' })
        }

        // 右下角编辑徽章
        Column() {
          Text('✎')
            .fontSize(13)
            .fontColor('#ffffff')
        }
        .width(30).height(30)
        .borderRadius(15)
        .backgroundColor('#3b82f6')
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)
        .border({ width: 2, color: this.themeManager.colors.cardBackgroundColor })
        .offset({ x: 2, y: 2 })
      }
      .scale({ x: this.avatarScale, y: this.avatarScale })
      .animation({ duration: 150, curve: Curve.EaseInOut })
      .onClick(() => {
        this.avatarScale = 0.92;
        setTimeout(() => { this.avatarScale = 1.0; }, 150);
        this.pickAvatar();
      })

      Text('点击更换头像')
        .fontSize(13)
        .fontColor('#3b82f6')
        .margin({ top: 12 })
        .onClick(() => { this.pickAvatar(); })

      Text('支持 JPG / PNG 格式')
        .fontSize(11)
        .fontColor(this.themeManager.colors.tertiaryTextColor)
        .margin({ top: 4 })
    }
    .width('100%')
    .padding({ top: 36, bottom: 28 })
    .alignItems(HorizontalAlign.Center)
  }

  // ── 表单区域 ──────────────────────────────────────────────
  @Builder
  FormSection(): void {
    Column() {
      // 昵称行
      Column() {
        Row() {
          Text('昵称')
            .fontSize(13)
            .fontColor(this.themeManager.colors.secondaryTextColor)
            .width(60)
          TextInput({ placeholder: '请输入昵称（2-12字）', text: this.nickname })
            .layoutWeight(1)
            .fontSize(15)
            .fontColor(this.themeManager.colors.primaryTextColor)
            .placeholderColor(this.themeManager.colors.tertiaryTextColor)
            .backgroundColor(Color.Transparent)
            .border({ width: 0 })
            .padding({ left: 0, right: 8 })
            .maxLength(12)
            .onChange((v: string) => {
              this.nickname = v;
              this.nicknameError = this.validateNickname();
            })
        }
        .width('100%')
        .padding({ left: 16, right: 8, top: 14, bottom: 14 })
        .alignItems(VerticalAlign.Center)

        if (this.nicknameError !== '') {
          Text(this.nicknameError)
            .fontSize(11)
            .fontColor('#ef4444')
            .alignSelf(ItemAlign.Start)
            .padding({ left: 16, bottom: 10 })
            .animation({ duration: 150, curve: Curve.EaseOut })
        }
      }
      .width('100%')
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .borderRadius(14)

      // 账号行（只读展示）
      Row() {
        Text('账号')
          .fontSize(13)
          .fontColor(this.themeManager.colors.secondaryTextColor)
          .width(60)
        Text(this.currentUser)
          .fontSize(15)
          .fontColor(this.themeManager.colors.tertiaryTextColor)
          .layoutWeight(1)
        Text('不可修改')
          .fontSize(11)
          .fontColor(this.themeManager.colors.tertiaryTextColor)
          .padding({
            left: 8, right: 8, top: 3, bottom: 3
          })
          .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9')
          .borderRadius(6)
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 14, bottom: 14 })
      .margin({ top: 12 })
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .borderRadius(14)
    }
    .width('92%')
  }


  // ── 底部保存按钮 ──────────────────────────────────────────
  @Builder
  SaveButton(): void {
    Button(this.isSaving ? '保存中...' : '保存修改')
      .width('92%')
      .height(52)
      .fontSize(16)
      .fontWeight(FontWeight.Medium)
      .fontColor(Color.White)
      .linearGradient({
        direction: GradientDirection.Right,
        colors: this.hasChanged && !this.isSaving
          ? [['#1e40af', 0.0], ['#3b82f6', 1.0]]
          : [['#94a3b8', 0.0], ['#94a3b8', 1.0]]
      })
      .borderRadius(100)
      .enabled(this.hasChanged && !this.isSaving)
      .scale({ x: this.saveBtnScale, y: this.saveBtnScale })
      .animation({ duration: 120, curve: Curve.EaseInOut })
      .onClick(() => {
        this.saveBtnScale = 0.96;
        setTimeout(() => { this.saveBtnScale = 1.0; }, 130);
        this.saveProfile();
      })
      .shadow({
        radius: this.hasChanged ? 16 : 0,
        color: '#403b82f6',
        offsetY: 4
      })
  }

  build() {
    NavDestination() {
      Scroll() {
        Column() {
          // 头像区域：渐变背景卡片
          Column() {
            this.AvatarSection()
          }
          .width('100%')
          .linearGradient({
            direction: GradientDirection.Bottom,
            colors: this.themeManager.isDarkMode
              ? [['#0f1e3d', 0.0], ['#1a2744', 1.0]]
              : [['#eff6ff', 0.0], ['#dbeafe', 1.0]]
          })

          // 表单区域
          Column() {
            // 小标题
            Text('基本信息')
              .fontSize(12)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .alignSelf(ItemAlign.Start)
              .margin({ left: '4%', bottom: 10, top: 24 })

            this.FormSection()

            // 提示文字
            Text('昵称将显示在个人主页和消息通知中')
              .fontSize(11)
              .fontColor(this.themeManager.colors.tertiaryTextColor)
              .width('92%')
              .textAlign(TextAlign.Start)
              .margin({ top: 8, bottom: 32 })

            this.SaveButton()

            // 底部留白
            Column().height(40)
          }
          .width('100%')
          .alignItems(HorizontalAlign.Center)
        }
        .width('100%')
      }
      .width('100%')
      .height('100%')
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .scrollBar(BarState.Off)
      .edgeEffect(EdgeEffect.Spring)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
    }
    .title(this.TitleBar)
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }
}
