/**
 * Profile.ets — 个人资料编辑页
 * 合并了头像编辑 + 昵称编辑，支持从相册选图、深色模式适配、保存至数据库
 */
import { ThemeManager } from '../common/ThemeManager';
import { DatabaseHelper, UserInfo } from '../database/DatabaseHelper';
import { UserManager } from '../common/UserManager';
import { CloudService, CloudUpdateFields } from '../common/CloudService';
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
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  pathStack: NavPathStack = new NavPathStack();
  @StorageProp("topSafeHeight") topSafeHeight: number = 48;

  // ── 表单状态 ──────────────────────────────────────────────
  @State nickname: string = '';
  @State avatarPath: string = '';        // 沙箱内头像文件路径，空则显示默认图标
  @State originalNickname: string = '';  // 用于判断是否有改动
  @State originalAvatarPath: string = '';
  @State isLoading: boolean = false;
  @State isSaving: boolean = false;
  @State hasChanged: boolean = false;    // 是否有未保存的改动

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
          this.updateChangedState();
        }
      })
      .catch(() => { this.isLoading = false; });
  }

  /** 同步更新 hasChanged 状态 */
  private updateChangedState(): void {
    this.hasChanged = this.nickname.trim() !== this.originalNickname ||
      this.avatarPath !== this.originalAvatarPath;
  }

  /** 校验昵称 */
  private validateNickname(): string {
    const v = this.nickname.trim();
    if (v.length < 1) return '昵称至少 1 个字';
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
      setTimeout(() => { this.avatarPath = destPath; this.updateChangedState(); }, 50);
    } catch (e) {
      console.error('[Profile]: 复制头像失败', JSON.stringify(e));
      promptAction.showToast({ message: '处理图片失败，请重试' });
    }
  }

  /** 保存到本地数据库，并异步同步云端 */
  private async saveProfile(): Promise<void> {
    const err = this.validateNickname();
    if (err !== '') { this.nicknameError = err; return; }
    this.nicknameError = '';
    this.isSaving = true;

    const db = DatabaseHelper.getInstance();
    try {
      const user = await db.queryUserByUsername(this.currentUser);
      if (!user || user.id === undefined) throw new Error('用户不存在');

      user.nickname = this.nickname.trim();
      user.avatarPath = this.avatarPath;
      await db.updateUser(user);

      // 同步更新内存层，个人页即时刷新
      AppStorage.setOrCreate<string>('loggedInNickname', this.nickname.trim());
      AppStorage.setOrCreate<string>('loggedInAvatarPath', this.avatarPath);

      // 同步更新 Preferences，重启后 Index 能恢复最新昵称
      try {
        const ctx = getContext(this) as common.UIAbilityContext;
        const pref = (await import('@kit.ArkData')).preferences
          .getPreferencesSync(ctx, { name: 'guardian_auth' });
        pref.putSync('lastNickname', this.nickname.trim());
        pref.flush();
      } catch (_) {}

      // 异步同步到云端，失败静默降级
      const updateFields = new CloudUpdateFields();
      updateFields.username = this.currentUser;
      updateFields.nickname = this.nickname.trim();
      updateFields.avatarPath = this.avatarPath;
      CloudService.getInstance().updateUser(updateFields).then(r => {
        console.info('[Profile]: 云端同步', r.success ? '成功' : '失败:' + r.message);
      });

      this.isSaving = false;
      this.originalNickname = this.nickname.trim();
      this.originalAvatarPath = this.avatarPath;
      this.updateChangedState();
      promptAction.showToast({ message: '保存好啦', duration: 1500 });
      // 延迟 1 秒后自动返回上一页
      setTimeout(() => {
        this.pathStack.pop();
      }, 1000);
    } catch (e) {
      this.isSaving = false;
      console.error('[Profile]: 保存失败', JSON.stringify(e));
      promptAction.showToast({ message: '保存失败，请重试' });
    }
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
              this.updateChangedState();
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
  // 已移入标题栏右侧，保留 saveProfile() 供保留，SaveButton Builder 已移除

  // ── 自定义标题栏（仿 HealthHistory，含保存按钮） ───────────
  // 使用 Stack + 全屏渐变背景 + expandSafeArea(TOP) 实现沉浸式状态栏
  @Builder
  GradientHeader(): void {
    Stack({ alignContent: Alignment.Top }) {
      // 层1：渐变背景（高度覆盖标题栏 + 头像区域，通过 expandSafeArea 延伸到状态栏）
      Column()
        .width("100%")
        .height(this.topSafeHeight + 100)
        .linearGradient({
          direction: GradientDirection.Bottom,
          colors: [
            ["#1e40af", 0.0],
            ["#3b82f6", 0.5],
            ["#60a5fa", 1.0],
          ],
        })
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
        .borderRadius({ bottomLeft: "6%", bottomRight: "6%" })

      // 层2：标题栏内容区
      Row() {
        Image($r("app.media.ic_chevron_right"))
          .width(36)
          .height(36)
          .objectFit(ImageFit.Contain)
          .padding(8)
          .backgroundColor("#33FFFFFF")
          .borderRadius(100)
          .rotate({ angle: 180 })
          .onClick((): void => {
            if (this.hasChanged) {
              // 逻辑统一放 onBackPressed，这里直接 pop 触发回调
              this.pathStack.pop();
            } else {
              this.pathStack.pop();
            }
          })
        Text("个人资料")
          .fontSize(22)
          .fontWeight(FontWeight.Bold)
          .fontColor("#ffffff")
          .margin({ left: "5%" })
          .layoutWeight(1)
        Text("保存")
          .fontSize(15)
          .fontColor("#ffffff")
          .padding({ left: 14, right: 14, top: 6, bottom: 6 })
          .backgroundColor("#33FFFFFF")
          .borderRadius(20)
          .onClick((): void => {
            if (!this.hasChanged) {
              promptAction.showToast({ message: '你还没有进行修改' });
            } else {
              this.saveProfile();
            }
          })
      }
      .width("100%")
      .padding({ left: "4%", right: "4%", top: this.topSafeHeight})
    }
    .width("100%")
    // Stack 自身不需要 borderRadius —— 内层 Column 全宽，"外圆弧"由子层容器过渡或由下层 Column 控制
  }

  build() {
    NavDestination() {
      Column() {
        this.GradientHeader()

        // 内容区域：去掉 Scroll，改为静态 Column，不可滑动
        Column() {
          // 头像区域
          this.AvatarSection()

          // 表单区域
          Column() {
            // 小标题（顶部间距调小，使整体内容上移，避免与渐变背景底部产生大段空白）
            Text('基本信息')
              .fontSize(12)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .alignSelf(ItemAlign.Start)
              .margin({ left: '4%', bottom: 10, top: 8 })

            this.FormSection()

            // 提示文字
            Text('昵称将显示在个人主页和消息通知中')
              .fontSize(11)
              .fontColor(this.themeManager.colors.tertiaryTextColor)
              .width('92%')
              .textAlign(TextAlign.Start)
              .margin({ top: 8, bottom: 32 })

            // 底部留白
            Column().height(40)
          }
          .width('100%')
          .alignItems(HorizontalAlign.Center)
        }
        .width('100%')
        .layoutWeight(1)
        .backgroundColor(this.themeManager.colors.backgroundColor)
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
      }
      .width('100%')
      .height('100%')
    }
    .hideTitleBar(true)
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .onBackPressed(() => {
      if (this.hasChanged) {
        AlertDialog.show({
          title: '提示',
          message: '有未保存的修改，是否保存？',
          primaryButton: {
            value: '不保存',
            action: () => {
              this.pathStack.pop();
            }
          },
          secondaryButton: {
            value: '保存',
            action: () => { this.saveProfile(); }
          },
          cancel: () => {},
          alignment: DialogAlignment.Center,
        });
        return true; // 拦截系统返回
      }
      return false; // 放行系统返回
    })
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }
}
