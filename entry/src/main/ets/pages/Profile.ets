/**
 * Profile.ets — 个人资料编辑页
 * 支持修改：头像、名字、手机号、邮箱、密码（二次确认）
 * 修改先写本地 RDB，再异步同步云端（失败静默降级）
 * 注：验证码接口(/api/sendCode, /api/verifyCode)后端未实现，暂跳过验证直接保存
 */
import { ThemeManager } from '../common/ThemeManager';
import { DatabaseHelper, UserInfo } from '../database/DatabaseHelper';
import { GradientHeader } from '../components/GradientHeader';
import { UserManager } from '../common/UserManager';
import { STORE_KEY_PHONE, STORE_KEY_EMAIL, STORE_KEY_NICKNAME, STORE_KEY_AVATAR, PREF_NAME_AUTH, PREF_KEY_LAST_NICKNAME, PREF_KEY_LAST_USERNAME } from '../config';
import { CloudService, CloudUpdateFields } from '../common/CloudService';
import { preferences } from '@kit.ArkData';
import { promptAction } from '@kit.ArkUI';
import { common, abilityAccessCtrl } from '@kit.AbilityKit';
import { photoAccessHelper } from '@kit.MediaLibraryKit';
import { image } from '@kit.ImageKit';
import fs from '@ohos.file.fs';

// ── 修改手机号弹窗 ───────────────────────────────────────────
@CustomDialog
struct PhoneEditDialog {
  controller: CustomDialogController;
  themeManager: ThemeManager = ThemeManager.getInstance();
  currentPhone: string = '';
  cloudLookupKey: string = '';   // 当前登录态 loginId，作为云端 lookup key（不可与新值混淆）
  loadedUser: UserInfo | null = null;
  onSuccess: (newPhone: string) => void = (_v: string) => {};

  @State phone: string = '';
  @State saving: boolean = false;
  @State errorMsg: string = '';

  build() {
    Column() {
      Text('修改手机号').fontSize(18).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor).margin({ bottom: 4 })
      if (this.currentPhone) {
        Text(`当前绑定：${this.maskPhone(this.currentPhone)}`).fontSize(12)
          .fontColor(this.themeManager.colors.secondaryTextColor).margin({ bottom: 16 })
      } else {
        Text('当前未绑定手机号').fontSize(12)
          .fontColor(this.themeManager.colors.tertiaryTextColor).margin({ bottom: 16 })
      }

      Text('新手机号').fontSize(12).fontWeight(FontWeight.Medium)
        .fontColor(this.themeManager.colors.secondaryTextColor)
        .alignSelf(ItemAlign.Start).margin({ bottom: 6 })
      TextInput({ placeholder: '请输入新手机号', text: this.phone })
        .type(InputType.PhoneNumber).maxLength(11).fontSize(14)
        .backgroundColor(this.themeManager.isDarkMode ? '#0f172a' : '#f8fafc')
        .fontColor(this.themeManager.colors.primaryTextColor)
        .border({ width: 1.5, color: this.themeManager.isDarkMode ? '#334155' : '#e2e8f0' })
        .borderRadius(12).height(44).width('100%')
        .onChange((v: string) => { this.phone = v; this.errorMsg = ''; })
        .margin({ bottom: 16 })

      if (this.errorMsg) {
        Text(this.errorMsg).fontSize(11).fontColor('#ef4444').alignSelf(ItemAlign.Start).margin({ bottom: 8 })
      }

      Row({ space: 12 }) {
        Button('取消').layoutWeight(1).height(44).type(ButtonType.Normal)
          .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9')
          .fontColor(this.themeManager.colors.secondaryTextColor).fontSize(14).borderRadius(12)
          .onClick(() => { this.controller.close(); })
        Button('确认修改').layoutWeight(1).height(44).type(ButtonType.Normal)
          .enabled(!this.saving)
          .linearGradient({ direction: GradientDirection.Right,
            colors: [[this.saving ? '#94a3b8' : '#1e40af', 0.0], [this.saving ? '#94a3b8' : '#3b82f6', 1.0]] })
          .fontColor(Color.White).fontSize(14).borderRadius(12)
          .onClick(async () => {
            const newPhone = this.phone.trim();
            if (!/^1[3-9]\d{9}$/.test(newPhone)) { this.errorMsg = '请输入正确的手机号'; return; }
            if (newPhone === this.currentPhone) { this.errorMsg = '新手机号与当前一致'; return; }
            const user = this.loadedUser;
            if (!user || user.id === undefined) { this.errorMsg = '用户信息异常'; return; }
            this.saving = true;
            try {
              // 1) 先同步云端（用旧 lookup key 定位）。云端失败就不动本地，避免双端漂移。
              const fields = new CloudUpdateFields();
              fields.username = this.cloudLookupKey;
              fields.phone = newPhone;
              const cloudR = await CloudService.getInstance().updateUser(fields);
              if (!cloudR.success) {
                this.errorMsg = cloudR.message === '网络不可用'
                  ? '网络不可用，请检查后重试' : '云端同步失败：' + cloudR.message;
                this.saving = false;
                return;
              }
              // 2) 云端成功，再写本地 + AppStorage
              user.phone = newPhone;
              await DatabaseHelper.getInstance().updateUser(user);
              AppStorage.setOrCreate<string>(STORE_KEY_PHONE, newPhone);
              promptAction.showToast({ message: '手机号修改成功' });
              this.onSuccess(newPhone);
              this.controller.close();
            } catch (e) {
              this.errorMsg = '保存失败，请重试';
              console.error('[PhoneEditDialog]: ' + JSON.stringify(e));
            }
            this.saving = false;
          })
      }.width('100%')
    }
    .width('100%').padding({ left: 24, right: 24, top: 28, bottom: 24 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius(20)
  }

  private maskPhone(phone: string): string {
    if (!phone || phone.length < 7) return phone;
    return phone.substring(0, 3) + '****' + phone.substring(phone.length - 4);
  }
}

// ── 修改邮箱弹窗 ───────────────────────────────────────────
@CustomDialog
struct EmailEditDialog {
  controller: CustomDialogController;
  themeManager: ThemeManager = ThemeManager.getInstance();
  currentEmail: string = '';
  cloudLookupKey: string = '';   // 当前登录态 loginId，作为云端 lookup key
  loadedUser: UserInfo | null = null;
  onSuccess: (newEmail: string) => void = (_v: string) => {};

  @State email: string = '';
  @State saving: boolean = false;
  @State errorMsg: string = '';

  build() {
    Column() {
      Text('修改邮箱').fontSize(18).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor).margin({ bottom: 4 })
      if (this.currentEmail) {
        Text(`当前绑定：${this.currentEmail}`).fontSize(12)
          .fontColor(this.themeManager.colors.secondaryTextColor).margin({ bottom: 16 })
      } else {
        Text('当前未绑定邮箱').fontSize(12)
          .fontColor(this.themeManager.colors.tertiaryTextColor).margin({ bottom: 16 })
      }

      Text('新邮箱地址').fontSize(12).fontWeight(FontWeight.Medium)
        .fontColor(this.themeManager.colors.secondaryTextColor)
        .alignSelf(ItemAlign.Start).margin({ bottom: 6 })
      TextInput({ placeholder: '请输入新邮箱', text: this.email })
        .type(InputType.Email).fontSize(14)
        .backgroundColor(this.themeManager.isDarkMode ? '#0f172a' : '#f8fafc')
        .fontColor(this.themeManager.colors.primaryTextColor)
        .border({ width: 1.5, color: this.themeManager.isDarkMode ? '#334155' : '#e2e8f0' })
        .borderRadius(12).height(44).width('100%')
        .onChange((v: string) => { this.email = v; this.errorMsg = ''; })
        .margin({ bottom: 16 })

      if (this.errorMsg) {
        Text(this.errorMsg).fontSize(11).fontColor('#ef4444').alignSelf(ItemAlign.Start).margin({ bottom: 8 })
      }

      Row({ space: 12 }) {
        Button('取消').layoutWeight(1).height(44).type(ButtonType.Normal)
          .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9')
          .fontColor(this.themeManager.colors.secondaryTextColor).fontSize(14).borderRadius(12)
          .onClick(() => { this.controller.close(); })
        Button('确认修改').layoutWeight(1).height(44).type(ButtonType.Normal)
          .enabled(!this.saving)
          .linearGradient({ direction: GradientDirection.Right,
            colors: [[this.saving ? '#94a3b8' : '#1e40af', 0.0], [this.saving ? '#94a3b8' : '#3b82f6', 1.0]] })
          .fontColor(Color.White).fontSize(14).borderRadius(12)
          .onClick(async () => {
            const newEmail = this.email.trim();
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newEmail)) { this.errorMsg = '请输入正确的邮箱'; return; }
            if (newEmail === this.currentEmail) { this.errorMsg = '新邮箱与当前一致'; return; }
            const user = this.loadedUser;
            if (!user || user.id === undefined) { this.errorMsg = '用户信息异常'; return; }
            this.saving = true;
            try {
              // 1) 先同步云端（用旧 lookup key 定位），失败不动本地
              const fields = new CloudUpdateFields();
              fields.username = this.cloudLookupKey;
              fields.email = newEmail;
              const cloudR = await CloudService.getInstance().updateUser(fields);
              if (!cloudR.success) {
                this.errorMsg = cloudR.message === '网络不可用'
                  ? '网络不可用，请检查后重试' : '云端同步失败：' + cloudR.message;
                this.saving = false;
                return;
              }
              // 2) 云端成功，再写本地 + AppStorage
              user.email = newEmail;
              await DatabaseHelper.getInstance().updateUser(user);
              AppStorage.setOrCreate<string>(STORE_KEY_EMAIL, newEmail);
              promptAction.showToast({ message: '邮箱修改成功' });
              this.onSuccess(newEmail);
              this.controller.close();
            } catch (e) {
              this.errorMsg = '保存失败，请重试';
              console.error('[EmailEditDialog]: ' + JSON.stringify(e));
            }
            this.saving = false;
          })
      }.width('100%')
    }
    .width('100%').padding({ left: 24, right: 24, top: 28, bottom: 24 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius(20)
  }
}

// ── 修改密码弹窗 ───────────────────────────────────────────
@CustomDialog
struct PasswordEditDialog {
  controller: CustomDialogController;
  themeManager: ThemeManager = ThemeManager.getInstance();
  loadedUser: UserInfo | null = null;
  onSuccess: () => void = () => {};

  @State oldPwd: string = '';
  @State newPwd: string = '';
  @State confirmPwd: string = '';
  @State showOldPwd: boolean = false;
  @State showNewPwd: boolean = false;
  @State showConfirmPwd: boolean = false;
  @State changing: boolean = false;
  @State errorMsg: string = '';

  build() {
    Column() {
      Text('修改密码').fontSize(18).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor).margin({ bottom: 16 })

      this.PwdRow('当前密码', this.oldPwd, this.showOldPwd, (v: string) => { this.oldPwd = v; this.errorMsg = ''; },
        () => { this.showOldPwd = !this.showOldPwd; })

      this.PwdRow('新密码', this.newPwd, this.showNewPwd, (v: string) => { this.newPwd = v; this.errorMsg = ''; },
        () => { this.showNewPwd = !this.showNewPwd; })

      this.PwdRow('确认新密码', this.confirmPwd, this.showConfirmPwd, (v: string) => { this.confirmPwd = v; this.errorMsg = ''; },
        () => { this.showConfirmPwd = !this.showConfirmPwd; })

      if (this.errorMsg) {
        Text(this.errorMsg).fontSize(11).fontColor('#ef4444').alignSelf(ItemAlign.Start).margin({ bottom: 8 })
      }

      Row({ space: 12 }) {
        Button('取消').layoutWeight(1).height(44).type(ButtonType.Normal)
          .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9')
          .fontColor(this.themeManager.colors.secondaryTextColor).fontSize(14).borderRadius(12)
          .onClick(() => { this.controller.close(); })
        Button('确认修改').layoutWeight(1).height(44).type(ButtonType.Normal)
          .enabled(!this.changing)
          .linearGradient({ direction: GradientDirection.Right,
            colors: [[this.changing ? '#94a3b8' : '#1e40af', 0.0], [this.changing ? '#94a3b8' : '#3b82f6', 1.0]] })
          .fontColor(Color.White).fontSize(14).borderRadius(12)
          .onClick(async () => {
            if (this.oldPwd.length < 4) { this.errorMsg = '当前密码至少4位'; return; }
            if (this.newPwd.length < 4) { this.errorMsg = '新密码至少4位'; return; }
            if (this.newPwd !== this.confirmPwd) { this.errorMsg = '两次输入的新密码不一致'; return; }
            if (this.newPwd === this.oldPwd) { this.errorMsg = '新密码不能与当前密码相同'; return; }
            const user = this.loadedUser;
            if (!user || user.id === undefined) { this.errorMsg = '用户信息异常'; return; }
            this.changing = true;
            try {
              const loginId = UserManager.getInstance().getCurrentUsername();
              // 1) 先本地校验旧密码
              if (user.passwordHash !== this.oldPwd) {
                // 本地不匹配，尝试云端验证（兜底本地密码丢失的 edge case）
                const fb = await CloudService.getInstance().login(loginId, this.oldPwd);
                if (!fb.success) { this.errorMsg = '当前密码不正确'; this.changing = false; return; }
              }
              // 2) 先同步云端，云端确认后再改本地，确保两端一致
              const cloudR = await CloudService.getInstance().changePassword(loginId, this.oldPwd, this.newPwd);
              if (!cloudR.success) {
                this.errorMsg = cloudR.message === '网络不可用'
                  ? '网络不可用，请检查后重试' : '云端同步失败：' + cloudR.message;
                this.changing = false;
                return;
              }
              // 3) 云端成功，再写本地
              await DatabaseHelper.getInstance().updatePasswordHash(user.id!, this.newPwd);
              user.passwordHash = this.newPwd;
              promptAction.showToast({ message: '密码修改成功' });
              this.onSuccess();
              this.controller.close();
            } catch (e) {
              this.errorMsg = '操作异常，请重试';
              console.error('[PasswordEditDialog]: ' + JSON.stringify(e));
            }
            this.changing = false;
          })
      }.width('100%')
    }
    .width('100%').padding({ left: 24, right: 24, top: 28, bottom: 24 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius(20)
  }

  @Builder
  PwdRow(label: string, value: string, show: boolean,
         onChange: (v: string) => void, onToggle: () => void): void {
    Column() {
      Text(label).fontSize(12).fontWeight(FontWeight.Medium)
        .fontColor(this.themeManager.colors.secondaryTextColor)
        .alignSelf(ItemAlign.Start).margin({ bottom: 6 })
      Row() {
        TextInput({ placeholder: `请输入${label}`, text: value })
          .type(show ? InputType.Normal : InputType.Password).fontSize(14).layoutWeight(1)
          .backgroundColor(this.themeManager.isDarkMode ? '#0f172a' : '#f8fafc')
          .fontColor(this.themeManager.colors.primaryTextColor)
          .border({ width: 1.5, color: this.themeManager.isDarkMode ? '#334155' : '#e2e8f0' })
          .borderRadius(12).height(44).padding({ left: 12, right: 0 })
          .onChange(onChange)
      }.width('100%')
    }.width('100%').margin({ bottom: 10 })
  }
}

// ── ProfileBuilder ─────────────────────────────────────────
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
  @State displayName: string = '';
  @State avatarPath: string = '';
  @State phone: string = '';
  @State email: string = '';
  @State originalDisplayName: string = '';  // 判断昵称是否改动，决定是否显示「保存」小标签
  @State isLoading: boolean = false;
  @State isSaving: boolean = false;         // 昵称保存中
  @State nameError: string = '';

  // ── 动画 ──────────────────────────────────────────────────
  @State avatarScale: number = 1.0;

  private currentUser: string = '';
  private loadedUser: UserInfo | null = null;

  // ── Dialog 控制器（每次打开时重建以传递最新状态）─────────────────
  private phoneDialogController: CustomDialogController = new CustomDialogController({
    builder: PhoneEditDialog({ currentPhone: '', loadedUser: null }),
    alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
  });

  private emailDialogController: CustomDialogController = new CustomDialogController({
    builder: EmailEditDialog({ currentEmail: '', loadedUser: null }),
    alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
  });

  private pwdDialogController: CustomDialogController = new CustomDialogController({
    builder: PasswordEditDialog({ loadedUser: null }),
    alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
  });

  aboutToAppear(): void {
    this.currentUser = UserManager.getInstance().getCurrentUsername();
    this.loadProfile();
  }

  // ── 数据加载 ──────────────────────────────────────────────
  private async loadProfile(): Promise<void> {
    this.isLoading = true;
    const db = DatabaseHelper.getInstance();
    try {
      let user = await db.queryUserByIdentifier(this.currentUser);
      if (!user) {
        // loginId 可能已变（如修改了手机号），用昵称兜底查一次
        const nickname = AppStorage.get<string>(STORE_KEY_NICKNAME) ?? '';
        if (nickname) user = await db.queryUserByUsername(nickname);
      }
      this.isLoading = false;
      if (user) {
        this.loadedUser = user;
        this.displayName = user.username || '';
        this.avatarPath = user.avatarPath ?? '';
        this.phone = user.phone ?? '';
        this.email = user.email ?? '';
        this.originalDisplayName = this.displayName;
      }
    } catch (_e) {
      this.isLoading = false;
    }
  }

  private validateName(): string {
    const v = this.displayName.trim();
    if (v.length < 1) return '名字不能为空';
    if (v.length > 12) return '名字最多 12 个字';
    return '';
  }

  // ── 打开弹窗（每次重建 controller 以传入最新字段） ───────────
  private openPhoneDialog(): void {
    if (!this.loadedUser) { promptAction.showToast({ message: '用户信息未加载，请稍后再试' }); return; }
    this.phoneDialogController = new CustomDialogController({
      builder: PhoneEditDialog({
        currentPhone: this.phone,
        cloudLookupKey: this.currentUser,
        loadedUser: this.loadedUser,
        onSuccess: (newPhone: string) => {
          this.phone = newPhone;
          if (this.loadedUser) this.loadedUser.phone = newPhone;
          // 若当前 loginId 是手机号，同步更新，避免下次 loadProfile 找不到用户
          if (/^1[3-9]\d{9}$/.test(this.currentUser)) {
            this.currentUser = newPhone;
            UserManager.getInstance().setCurrentUsername(newPhone);
            const ctx = getContext(this) as common.UIAbilityContext;
            try {
              const pref = preferences.getPreferencesSync(ctx, { name: PREF_NAME_AUTH });
              pref.putSync(PREF_KEY_LAST_USERNAME, newPhone);
              pref.flush();
            } catch (_e) {}
          }
        },
      }),
      alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
    });
    this.phoneDialogController.open();
  }

  private openEmailDialog(): void {
    if (!this.loadedUser) { promptAction.showToast({ message: '用户信息未加载，请稍后再试' }); return; }
    this.emailDialogController = new CustomDialogController({
      builder: EmailEditDialog({
        currentEmail: this.email,
        cloudLookupKey: this.currentUser,
        loadedUser: this.loadedUser,
        onSuccess: (newEmail: string) => {
          this.email = newEmail;
          if (this.loadedUser) this.loadedUser.email = newEmail;
          // 若当前 loginId 是邮箱，同步更新
          if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.currentUser)) {
            this.currentUser = newEmail;
            UserManager.getInstance().setCurrentUsername(newEmail);
            const ctx = getContext(this) as common.UIAbilityContext;
            try {
              const pref = preferences.getPreferencesSync(ctx, { name: PREF_NAME_AUTH });
              pref.putSync(PREF_KEY_LAST_USERNAME, newEmail);
              pref.flush();
            } catch (_e) {}
          }
        },
      }),
      alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
    });
    this.emailDialogController.open();
  }

  private openPwdDialog(): void {
    if (!this.loadedUser) { promptAction.showToast({ message: '用户信息未加载，请稍后再试' }); return; }
    this.pwdDialogController = new CustomDialogController({
      builder: PasswordEditDialog({
        loadedUser: this.loadedUser,
        onSuccess: () => {},
      }),
      alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
    });
    this.pwdDialogController.open();
  }

  // ── 头像 ──────────────────────────────────────────────────
  private async pickAvatar(): Promise<void> {
    const context = getContext(this) as common.UIAbilityContext;
    const atManager = abilityAccessCtrl.createAtManager();
    const grant = await atManager.requestPermissionsFromUser(
      context, ['ohos.permission.READ_IMAGEVIDEO']
    );
    if (grant.authResults[0] !== 0) {
      promptAction.showToast({ message: '需要相册权限，请在设置中开启' });
      return;
    }
    const picker = new photoAccessHelper.PhotoViewPicker();
    const selectOptions = new photoAccessHelper.PhotoSelectOptions();
    selectOptions.MIMEType = photoAccessHelper.PhotoViewMIMETypes.IMAGE_TYPE;
    selectOptions.maxSelectNumber = 1;
    try {
      const pickerResult = await picker.select(selectOptions);
      if (!pickerResult || pickerResult.photoUris.length === 0) return;
      await this.processAndSaveAvatar(context, pickerResult.photoUris[0]);
    } catch (e) {
      console.error('[Profile]: 选图失败', JSON.stringify(e));
      promptAction.showToast({ message: '选取图片失败，请重试' });
    }
  }

  /**
   * 处理并保存头像：
   *   1. 用 fd 打开相册 URI（真机必须先取 fd，不能直接 fs.copyFile URI）
   *   2. ImageKit 解码任意尺寸图片为 PixelMap
   *   3. 按短边居中裁成正方形，再缩放到 512×512（统一规格，控制体积）
   *   4. 重编码为 JPEG 写入沙箱（带时间戳文件名，绕过 Image 组件路径缓存）
   *   5. 尽力删除旧头像文件，避免堆积
   */
  private async processAndSaveAvatar(context: common.UIAbilityContext, sourceUri: string): Promise<void> {
    let srcFile: fs.File | undefined;
    let imageSource: image.ImageSource | undefined;
    let pixelMap: image.PixelMap | undefined;
    let packer: image.ImagePacker | undefined;
    try {
      const avatarDir = context.filesDir + '/avatars';
      try { fs.mkdirSync(avatarDir); } catch (_e) {}

      // 1) fd 打开来源 URI
      srcFile = fs.openSync(sourceUri, fs.OpenMode.READ_ONLY);
      imageSource = image.createImageSource(srcFile.fd);
      const info = await imageSource.getImageInfo();
      pixelMap = await imageSource.createPixelMap();

      // 2) 短边居中裁正方形
      const w = info.size.width;
      const h = info.size.height;
      const side = Math.min(w, h);
      const region: image.Region = {
        x: Math.max(0, Math.floor((w - side) / 2)),
        y: Math.max(0, Math.floor((h - side) / 2)),
        size: { width: side, height: side },
      };
      await pixelMap.crop(region);

      // 3) 缩放到 512×512
      const TARGET = 512;
      await pixelMap.scale(TARGET / side, TARGET / side);

      // 4) JPEG 重编码
      packer = image.createImagePacker();
      const jpegBuffer = await packer.packing(pixelMap, { format: 'image/jpeg', quality: 90 });

      // 5) 写入带时间戳的新文件，删除旧文件
      const destPath = avatarDir + '/avatar_' + this.currentUser + '_' + Date.now() + '.jpg';
      const destFile = fs.openSync(destPath, fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
      fs.writeSync(destFile.fd, jpegBuffer);
      fs.closeSync(destFile);

      const oldPath = this.avatarPath;
      this.avatarPath = destPath;
      if (oldPath && oldPath !== destPath) {
        try { fs.unlinkSync(oldPath); } catch (_e) {}
      }
      // 选完即存：立即落地本地 + 云端
      await this.saveAvatar();
    } catch (e) {
      console.error('[Profile]: 处理头像失败', JSON.stringify(e));
      promptAction.showToast({ message: '处理图片失败，请重试' });
    } finally {
      pixelMap?.release();
      packer?.release();
      imageSource?.release();
      if (srcFile !== undefined) { try { fs.closeSync(srcFile); } catch (_e) {} }
    }
  }

  // ── 保存昵称（内联即时，云端优先）─────────────────────────
  private async saveNickname(): Promise<void> {
    const err = this.validateName();
    if (err !== '') { this.nameError = err; return; }
    this.nameError = '';
    const newName = this.displayName.trim();
    if (newName === this.originalDisplayName) return; // 没改，不动
    const user = this.loadedUser;
    if (!user || user.id === undefined) { promptAction.showToast({ message: '用户信息异常' }); return; }
    this.isSaving = true;
    try {
      // 1) 先同步云端，失败不动本地。
      //    同时更新 username(PK，newUsername) 和 nickname 两列：
      //    nickname 列任何后端版本都支持，避免只依赖 PK 改名而旧后端静默忽略。
      const fields = new CloudUpdateFields();
      fields.username = this.currentUser;
      fields.newUsername = newName;
      fields.nickname = newName;
      const cloudR = await CloudService.getInstance().updateUser(fields);
      if (!cloudR.success) {
        promptAction.showToast({ message: cloudR.message === '网络不可用' ? '网络不可用，请检查后重试' : '云端同步失败：' + cloudR.message });
        this.isSaving = false;
        return;
      }
      // 2) 云端成功，再写本地 + AppStorage + Preferences
      user.username = newName;
      await DatabaseHelper.getInstance().updateUser(user);
      AppStorage.setOrCreate<string>(STORE_KEY_NICKNAME, newName);
      try {
        const ctx = getContext(this) as common.UIAbilityContext;
        const pref = preferences.getPreferencesSync(ctx, { name: PREF_NAME_AUTH });
        pref.putSync(PREF_KEY_LAST_NICKNAME, newName);
        pref.flush();
      } catch (_) {}
      this.originalDisplayName = newName;
      promptAction.showToast({ message: '名字已更新', duration: 1500 });
    } catch (e) {
      console.error('[Profile]: 昵称保存失败', JSON.stringify(e));
      promptAction.showToast({ message: '保存失败，请重试' });
    }
    this.isSaving = false;
  }

  // ── 保存头像（选完即存：本地立即落地，云端尽力同步）───────────
  private async saveAvatar(): Promise<void> {
    const user = this.loadedUser;
    if (!user || user.id === undefined) return;
    try {
      user.avatarPath = this.avatarPath;
      await DatabaseHelper.getInstance().updateUser(user);
      AppStorage.setOrCreate<string>(STORE_KEY_AVATAR, this.avatarPath);
      // 云端同步头像路径（不退页，请求可完整跑完；路径为设备本地，仅作信息留存）
      const fields = new CloudUpdateFields();
      fields.username = this.currentUser;
      fields.avatarPath = this.avatarPath;
      CloudService.getInstance().updateUser(fields).then(r => {
        console.info('[Profile]: 头像云端同步', r.success ? '成功' : '失败:' + r.message);
      });
      promptAction.showToast({ message: '头像已更新', duration: 1500 });
    } catch (e) {
      console.error('[Profile]: 头像保存失败', JSON.stringify(e));
      promptAction.showToast({ message: '头像保存失败，请重试' });
    }
  }

  // ── 头像区域 Builder ──────────────────────────────────────
  @Builder
  AvatarSection(): void {
    Column() {
      Stack({ alignContent: Alignment.BottomEnd }) {
        if (this.avatarPath !== '') {
          Image(this.avatarPath).width(100).height(100).borderRadius(50)
            .objectFit(ImageFit.Cover)
            .border({ width: 3, color: this.themeManager.isDarkMode ? '#1e3a5f' : '#bfdbfe' })
        } else {
          Column() {
            Image($r('app.media.ic_user')).width(52).height(52).objectFit(ImageFit.Contain)
          }
          .width(100).height(100).borderRadius(50)
          .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#dbeafe')
          .justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
          .border({ width: 3, color: this.themeManager.isDarkMode ? '#1e3a5f' : '#bfdbfe' })
        }
        Column() { Text('✎').fontSize(13).fontColor('#ffffff') }
        .width(30).height(30).borderRadius(15).backgroundColor('#3b82f6')
        .justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
        .border({ width: 2, color: this.themeManager.colors.cardBackgroundColor }).offset({ x: 2, y: 2 })
      }
      .scale({ x: this.avatarScale, y: this.avatarScale }).animation({ duration: 150, curve: Curve.EaseInOut })
      .onClick(() => { this.avatarScale = 0.92; setTimeout(() => { this.avatarScale = 1.0; }, 150); this.pickAvatar(); })

      Text('点击更换头像').fontSize(13).fontColor('#3b82f6').margin({ top: 12 })
        .onClick(() => { this.pickAvatar(); })
      Text('支持 JPG / PNG 格式').fontSize(11)
        .fontColor(this.themeManager.colors.tertiaryTextColor).margin({ top: 4 })
    }
    .width('100%').padding({ top: 36, bottom: 28 }).alignItems(HorizontalAlign.Center)
  }

  // ── 可编辑行 Builder（昵称/手机/邮箱通用） ─────────────────
  @Builder
  EditRow(label: string, value: string, placeholder: string, maxLen: number,
          onChange: (v: string) => void, rightText: string, rightTap: () => void,
          inputType: InputType): void {
    Row() {
      Text(label).fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).width(56)
      TextInput({ placeholder: placeholder, text: value })
        .type(inputType).maxLength(maxLen).fontSize(15).layoutWeight(1)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .placeholderColor(this.themeManager.colors.tertiaryTextColor)
        .backgroundColor(Color.Transparent).border({ width: 0 }).padding({ left: 0, right: 8 })
        .onChange(onChange)
      Text(rightText).fontSize(12).fontColor('#3b82f6').fontWeight(FontWeight.Medium)
        .padding({ left: 10, right: 10, top: 4, bottom: 4 })
        .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
        .borderRadius(100)
        .onClick(rightTap)
    }
    .width('100%').padding({ left: 16, right: 8, top: 14, bottom: 14 }).alignItems(VerticalAlign.Center)
  }

  // ── 表单区域 ──────────────────────────────────────────────
  @Builder
  FormSection(): void {
    Column() {
      // 名字行
      Column() {
        Row() {
          Text('名字').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).width(56)
          TextInput({ placeholder: '请输入你的名字（2-12字）', text: this.displayName })
            .layoutWeight(1).fontSize(15)
            .fontColor(this.themeManager.colors.primaryTextColor)
            .placeholderColor(this.themeManager.colors.tertiaryTextColor)
            .backgroundColor(Color.Transparent).border({ width: 0 }).padding({ left: 0, right: 8 })
            .maxLength(12)
            .onChange((v: string) => { this.displayName = v; this.nameError = this.validateName(); })
            .onSubmit(() => { this.saveNickname(); })
          // 改动且合法时才出现「保存」小标签，点击即云端优先保存
          if (this.displayName.trim() !== this.originalDisplayName && this.nameError === '') {
            Text(this.isSaving ? '保存中' : '保存').fontSize(12).fontColor('#3b82f6').fontWeight(FontWeight.Medium)
              .padding({ left: 10, right: 10, top: 4, bottom: 4 })
              .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
              .borderRadius(100)
              .onClick(() => { if (!this.isSaving) this.saveNickname(); })
          }
        }
        .width('100%').padding({ left: 16, right: 8, top: 14, bottom: 14 }).alignItems(VerticalAlign.Center)
        if (this.nameError !== '') {
          Text(this.nameError).fontSize(11).fontColor('#ef4444')
            .alignSelf(ItemAlign.Start).padding({ left: 16, bottom: 10 })
            .animation({ duration: 150, curve: Curve.EaseOut })
        }
      }
      .width('100%').backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius(14)
    }
    .width('92%')
  }

  // ── 安全与联系区域 ───────────────────────────────────────
  @Builder
  SecuritySection(): void {
    Column() {
      // 手机号行
      Row() {
        Text('手机号').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).width(56)
        Text(this.phone ? this.maskPhone(this.phone) : '未绑定')
          .fontSize(15).fontColor(this.phone ? this.themeManager.colors.primaryTextColor : this.themeManager.colors.tertiaryTextColor)
          .layoutWeight(1)
        Text(this.phone ? '修改' : '绑定').fontSize(12).fontColor('#3b82f6').fontWeight(FontWeight.Medium)
          .padding({ left: 10, right: 10, top: 4, bottom: 4 })
          .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
          .borderRadius(100)
          .onClick(() => { this.openPhoneDialog(); })
      }
      .width('100%').padding({ left: 16, right: 8, top: 14, bottom: 14 }).alignItems(VerticalAlign.Center)

      Divider().margin({ left: '12%', right: '4%' }).color(this.themeManager.colors.separatorColor)

      // 邮箱行
      Row() {
        Text('邮箱').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).width(56)
        Text(this.email || '未绑定')
          .fontSize(15).fontColor(this.email ? this.themeManager.colors.primaryTextColor : this.themeManager.colors.tertiaryTextColor)
          .layoutWeight(1)
        Text(this.email ? '修改' : '绑定').fontSize(12).fontColor('#3b82f6').fontWeight(FontWeight.Medium)
          .padding({ left: 10, right: 10, top: 4, bottom: 4 })
          .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
          .borderRadius(100)
          .onClick(() => { this.openEmailDialog(); })
      }
      .width('100%').padding({ left: 16, right: 8, top: 14, bottom: 14 }).alignItems(VerticalAlign.Center)

      Divider().margin({ left: '12%', right: '4%' }).color(this.themeManager.colors.separatorColor)

      // 密码行
      Row() {
        Text('密码').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).width(56)
        Text('••••••••').fontSize(15).fontColor(this.themeManager.colors.primaryTextColor).layoutWeight(1)
        Text('修改').fontSize(12).fontColor('#3b82f6').fontWeight(FontWeight.Medium)
          .padding({ left: 10, right: 10, top: 4, bottom: 4 })
          .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
          .borderRadius(100)
          .onClick(() => { this.openPwdDialog(); })
      }
      .width('100%').padding({ left: 16, right: 8, top: 14, bottom: 14 }).alignItems(VerticalAlign.Center)
    }
    .width('92%').backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius(14)
  }

  private maskPhone(phone: string): string {
    if (!phone || phone.length < 7) return phone;
    return phone.substring(0, 3) + '****' + phone.substring(phone.length - 4);
  }

  // ── 标题栏 ────────────────────────────────────────────────
  @Builder
  GradientHeader(): void {
    GradientHeader() {
      Row() {
        Image($r("app.media.ic_chevron_right")).width(36).height(36)
          .objectFit(ImageFit.Contain).padding(8)
          .backgroundColor("#33FFFFFF").borderRadius(100).rotate({ angle: 180 })
          .onClick((): void => { this.pathStack.pop(); })
        Text("个人资料").fontSize(22).fontWeight(FontWeight.Bold).fontColor("#ffffff")
          .margin({ left: "5%" }).layoutWeight(1)
      }
      .width("100%").padding({ left: "4%", right: "4%", top: this.topSafeHeight })
    }
  }

  build() {
    NavDestination() {
      Column() {
        this.GradientHeader()
        // 内容区域改为可滚动，容纳新增的安全设置区
        Scroll() {
          Column() {
            this.AvatarSection()
            Column() {
              // ── 基本信息 ──
              Text('基本信息').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
                .alignSelf(ItemAlign.Start).margin({ left: '4%', bottom: 10, top: 8 })
              Column() { this.FormSection() }.width('100%').alignItems(HorizontalAlign.Center)

              // ── 安全与联系 ──
              Text('安全与联系').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
                .alignSelf(ItemAlign.Start).margin({ left: '4%', bottom: 10, top: 24 })
              Column() { this.SecuritySection() }.width('100%').alignItems(HorizontalAlign.Center)

              Text('手机号和邮箱将用于账号安全验证和重要通知').fontSize(11)
                .fontColor(this.themeManager.colors.tertiaryTextColor)
                .width('92%').textAlign(TextAlign.Start).margin({ top: 8, bottom: 32 })

              Column().height(40)
            }
            .width('100%').alignItems(HorizontalAlign.Center)
          }.width('100%')
        }
        .layoutWeight(1).scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
        .width('100%')
      }
      .width('100%').height('100%')
    }
    .hideTitleBar(true)
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .onReady((context: NavDestinationContext) => { this.pathStack = context.pathStack; })
  }
}
