/**
 * Profile.ets — 个人资料编辑页
 * 支持修改：头像、昵称、手机号（验证码）、邮箱（验证码）、密码（二次确认）
 * 所有修改先写本地 RDB，再异步同步云端（失败静默降级）
 */
import { ThemeManager } from '../common/ThemeManager';
import { DatabaseHelper, UserInfo } from '../database/DatabaseHelper';
import { UserManager } from '../common/UserManager';
import { CloudService, CloudUpdateFields } from '../common/CloudService';
import { preferences } from '@kit.ArkData';
import { promptAction } from '@kit.ArkUI';
import { common, abilityAccessCtrl } from '@kit.AbilityKit';
import { photoAccessHelper } from '@kit.MediaLibraryKit';
import fs from '@ohos.file.fs';

// ── 修改手机号弹窗 ───────────────────────────────────────────
@CustomDialog
struct PhoneEditDialog {
  controller: CustomDialogController;
  themeManager: ThemeManager = ThemeManager.getInstance();
  currentPhone: string = '';
  currentUser: string = '';

  @State phone: string = '';
  @State code: string = '';
  @State countdown: number = 0;
  @State sending: boolean = false;
  @State verifying: boolean = false;
  @State errorMsg: string = '';
  private timer: number = -1;

  aboutToDisappear(): void { if (this.timer !== -1) { clearInterval(this.timer); } }

  private startCountdown(): void {
    this.countdown = 60;
    this.timer = setInterval(() => {
      this.countdown--;
      if (this.countdown <= 0) { clearInterval(this.timer); this.countdown = 0; }
    }, 1000) as number;
  }

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
        .margin({ bottom: 12 })

      Row({ space: 10 }) {
        TextInput({ placeholder: '验证码', text: this.code })
          .type(InputType.Number).maxLength(6).fontSize(14)
          .backgroundColor(this.themeManager.isDarkMode ? '#0f172a' : '#f8fafc')
          .fontColor(this.themeManager.colors.primaryTextColor)
          .border({ width: 1.5, color: this.themeManager.isDarkMode ? '#334155' : '#e2e8f0' })
          .borderRadius(12).height(44).layoutWeight(1)
          .onChange((v: string) => { this.code = v; })
        Button(this.countdown > 0 ? `${this.countdown}s` : this.sending ? '发送中…' : '获取验证码')
          .fontSize(12).height(44).width(100)
          .fontColor(this.countdown > 0 ? '#94a3b8' : '#ffffff')
          .backgroundColor(this.countdown > 0
            ? (this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9')
            : '#3b82f6')
          .enabled(this.countdown === 0 && !this.sending && this.phone.trim().length === 11)
          .onClick(async () => {
            if (!/^1[3-9]\d{9}$/.test(this.phone.trim())) {
              this.errorMsg = '请输入正确的手机号'; return;
            }
            this.sending = true;
            const r = await CloudService.getInstance().sendVerificationCode(this.phone.trim(), 'phone', this.currentUser);
            this.sending = false;
            if (r.success) { this.startCountdown(); promptAction.showToast({ message: '验证码已发送' }); }
            else { this.errorMsg = r.message || '发送失败，请重试'; }
          })
      }.width('100%').margin({ bottom: 8 })

      if (this.errorMsg) {
        Text(this.errorMsg).fontSize(11).fontColor('#ef4444').alignSelf(ItemAlign.Start).margin({ bottom: 8 })
      }

      Row({ space: 12 }) {
        Button('取消').layoutWeight(1).height(44).type(ButtonType.Normal)
          .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9')
          .fontColor(this.themeManager.colors.secondaryTextColor).fontSize(14).borderRadius(12)
          .onClick(() => { this.controller.close(); })
        Button('确认修改').layoutWeight(1).height(44).type(ButtonType.Normal)
          .enabled(!this.verifying)
          .linearGradient({ direction: GradientDirection.Right,
            colors: [[this.verifying ? '#94a3b8' : '#1e40af', 0.0], [this.verifying ? '#94a3b8' : '#3b82f6', 1.0]] })
          .fontColor(Color.White).fontSize(14).borderRadius(12)
          .onClick(async () => {
            if (!/^1[3-9]\d{9}$/.test(this.phone.trim())) { this.errorMsg = '请输入正确的手机号'; return; }
            if (this.code.trim().length !== 6) { this.errorMsg = '请输入6位验证码'; return; }
            this.verifying = true;
            const r = await CloudService.getInstance().verifyCode(this.phone.trim(), this.code.trim(), this.currentUser);
            if (r.success) {
              const db = DatabaseHelper.getInstance();
              const user = await db.queryUserByUsername(this.currentUser);
              if (user && user.id !== undefined) {
                user.phone = this.phone.trim();
                await db.updateUser(user);
                AppStorage.setOrCreate<string>('loggedInPhone', user.phone);
                const fields = new CloudUpdateFields();
                fields.username = this.currentUser; fields.phone = this.phone.trim();
                CloudService.getInstance().updateUser(fields).then(() => {});
              }
              promptAction.showToast({ message: '手机号修改成功' });
              this.controller.close();
            } else {
              this.errorMsg = r.message || '验证失败';
            }
            this.verifying = false;
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
  currentUser: string = '';

  @State email: string = '';
  @State code: string = '';
  @State countdown: number = 0;
  @State sending: boolean = false;
  @State verifying: boolean = false;
  @State errorMsg: string = '';
  private timer: number = -1;

  aboutToDisappear(): void { if (this.timer !== -1) { clearInterval(this.timer); } }

  private startCountdown(): void {
    this.countdown = 60;
    this.timer = setInterval(() => {
      this.countdown--;
      if (this.countdown <= 0) { clearInterval(this.timer); this.countdown = 0; }
    }, 1000) as number;
  }

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
        .margin({ bottom: 12 })

      Row({ space: 10 }) {
        TextInput({ placeholder: '验证码', text: this.code })
          .type(InputType.Number).maxLength(6).fontSize(14)
          .backgroundColor(this.themeManager.isDarkMode ? '#0f172a' : '#f8fafc')
          .fontColor(this.themeManager.colors.primaryTextColor)
          .border({ width: 1.5, color: this.themeManager.isDarkMode ? '#334155' : '#e2e8f0' })
          .borderRadius(12).height(44).layoutWeight(1)
          .onChange((v: string) => { this.code = v; })
        Button(this.countdown > 0 ? `${this.countdown}s` : this.sending ? '发送中…' : '获取验证码')
          .fontSize(12).height(44).width(100)
          .fontColor(this.countdown > 0 ? '#94a3b8' : '#ffffff')
          .backgroundColor(this.countdown > 0
            ? (this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9')
            : '#3b82f6')
          .enabled(this.countdown === 0 && !this.sending && this.email.trim().length > 0)
          .onClick(async () => {
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email.trim())) {
              this.errorMsg = '请输入正确的邮箱地址'; return;
            }
            this.sending = true;
            const r = await CloudService.getInstance().sendVerificationCode(this.email.trim(), 'email', this.currentUser);
            this.sending = false;
            if (r.success) { this.startCountdown(); promptAction.showToast({ message: '验证码已发送至邮箱' }); }
            else { this.errorMsg = r.message || '发送失败，请重试'; }
          })
      }.width('100%').margin({ bottom: 8 })

      if (this.errorMsg) {
        Text(this.errorMsg).fontSize(11).fontColor('#ef4444').alignSelf(ItemAlign.Start).margin({ bottom: 8 })
      }

      Row({ space: 12 }) {
        Button('取消').layoutWeight(1).height(44).type(ButtonType.Normal)
          .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9')
          .fontColor(this.themeManager.colors.secondaryTextColor).fontSize(14).borderRadius(12)
          .onClick(() => { this.controller.close(); })
        Button('确认修改').layoutWeight(1).height(44).type(ButtonType.Normal)
          .enabled(!this.verifying)
          .linearGradient({ direction: GradientDirection.Right,
            colors: [[this.verifying ? '#94a3b8' : '#1e40af', 0.0], [this.verifying ? '#94a3b8' : '#3b82f6', 1.0]] })
          .fontColor(Color.White).fontSize(14).borderRadius(12)
          .onClick(async () => {
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email.trim())) { this.errorMsg = '请输入正确的邮箱'; return; }
            if (this.code.trim().length !== 6) { this.errorMsg = '请输入6位验证码'; return; }
            this.verifying = true;
            const r = await CloudService.getInstance().verifyCode(this.email.trim(), this.code.trim(), this.currentUser);
            if (r.success) {
              const db = DatabaseHelper.getInstance();
              const user = await db.queryUserByUsername(this.currentUser);
              if (user && user.id !== undefined) {
                user.email = this.email.trim();
                await db.updateUser(user);
                AppStorage.setOrCreate<string>('loggedInEmail', user.email);
                const fields = new CloudUpdateFields();
                fields.username = this.currentUser; fields.email = this.email.trim();
                CloudService.getInstance().updateUser(fields).then(() => {});
              }
              promptAction.showToast({ message: '邮箱修改成功' });
              this.controller.close();
            } else {
              this.errorMsg = r.message || '验证失败';
            }
            this.verifying = false;
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
  currentUser: string = '';

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
            this.changing = true;
            const db = DatabaseHelper.getInstance();
            try {
              const user = await db.queryUserByUsername(this.currentUser);
              if (!user || user.id === undefined) { this.errorMsg = '用户信息异常'; this.changing = false; return; }
              // 先本地校验旧密码
              if (user.passwordHash !== this.oldPwd) {
                // 本地不匹配，尝试云端验证
                const cloud = CloudService.getInstance();
                const fb = await cloud.login(this.currentUser, this.oldPwd);
                if (!fb.success) { this.errorMsg = '当前密码不正确'; this.changing = false; return; }
              }
              // 云端改密码
              const r = await CloudService.getInstance().changePassword(this.currentUser, this.oldPwd, this.newPwd);
              if (r.success) {
                await db.updatePasswordHash(user.id!, this.newPwd);
                promptAction.showToast({ message: '密码修改成功' });
                this.controller.close();
              } else {
                this.errorMsg = r.message || '修改失败，请重试';
              }
            } catch (e) {
              this.errorMsg = '操作异常，请重试';
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
        Text(show ? '🙈' : '👁').fontSize(16).width(36).textAlign(TextAlign.Center)
          .onClick(onToggle)
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
  @State originalDisplayName: string = '';
  @State originalAvatarPath: string = '';
  @State originalPhone: string = '';
  @State originalEmail: string = '';
  @State isLoading: boolean = false;
  @State isSaving: boolean = false;
  @State hasChanged: boolean = false;
  @State nameError: string = '';

  // ── 动画 ──────────────────────────────────────────────────
  @State avatarScale: number = 1.0;

  private currentUser: string = '';

  // ── Dialog 控制器（每次打开时重建以传递最新状态）─────────────────
  private phoneDialogController: CustomDialogController = new CustomDialogController({
    builder: PhoneEditDialog({ currentPhone: '', currentUser: '' }),
    alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
  });

  private emailDialogController: CustomDialogController = new CustomDialogController({
    builder: EmailEditDialog({ currentEmail: '', currentUser: '' }),
    alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
  });

  private pwdDialogController: CustomDialogController = new CustomDialogController({
    builder: PasswordEditDialog({ currentUser: '' }),
    alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
  });

  aboutToAppear(): void {
    this.currentUser = UserManager.getInstance().getCurrentUsername();
    this.loadProfile();
  }

  // ── 数据加载 ──────────────────────────────────────────────
  private loadProfile(): void {
    this.isLoading = true;
    const db = DatabaseHelper.getInstance();
    db.queryUserByIdentifier(this.currentUser)
      .then((user: UserInfo | null) => {
        this.isLoading = false;
        if (user) {
          this.displayName = user.username || '';
          this.avatarPath = user.avatarPath ?? '';
          this.phone = user.phone ?? '';
          this.email = user.email ?? '';
          this.originalDisplayName = this.displayName;
          this.originalAvatarPath = this.avatarPath;
          this.originalPhone = this.phone;
          this.originalEmail = this.email;
          this.updateChangedState();
        }
      })
      .catch(() => { this.isLoading = false; });
  }

  private updateChangedState(): void {
    this.hasChanged = this.displayName.trim() !== this.originalDisplayName ||
      this.avatarPath !== this.originalAvatarPath;
  }

  private validateName(): string {
    const v = this.displayName.trim();
    if (v.length < 1) return '名字不能为空';
    if (v.length > 12) return '名字最多 12 个字';
    return '';
  }

  // ── 打开弹窗（每次重建 controller 以传入最新字段） ───────────
  private openPhoneDialog(): void {
    this.phoneDialogController = new CustomDialogController({
      builder: PhoneEditDialog({ currentPhone: this.phone, currentUser: this.currentUser }),
      alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
    });
    this.phoneDialogController.open();
  }

  private openEmailDialog(): void {
    this.emailDialogController = new CustomDialogController({
      builder: EmailEditDialog({ currentEmail: this.email, currentUser: this.currentUser }),
      alignment: DialogAlignment.Center, cornerRadius: 20, maskColor: 'rgba(0,0,0,0.5)',
    });
    this.emailDialogController.open();
  }

  private openPwdDialog(): void {
    this.pwdDialogController = new CustomDialogController({
      builder: PasswordEditDialog({ currentUser: this.currentUser }),
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
      await this.copyAvatarToSandbox(context, pickerResult.photoUris[0]);
    } catch (e) {
      console.error('[Profile]: 选图失败', JSON.stringify(e));
      promptAction.showToast({ message: '选取图片失败，请重试' });
    }
  }

  private async copyAvatarToSandbox(context: common.UIAbilityContext, sourceUri: string): Promise<void> {
    try {
      const avatarDir = context.filesDir + '/avatars';
      try { fs.mkdirSync(avatarDir); } catch (_e) {}
      const destPath = avatarDir + '/avatar_' + this.currentUser + '.jpg';
      await fs.copyFile(sourceUri, destPath);
      this.avatarPath = '';
      setTimeout(() => { this.avatarPath = destPath; this.updateChangedState(); }, 50);
    } catch (e) {
      console.error('[Profile]: 复制头像失败', JSON.stringify(e));
      promptAction.showToast({ message: '处理图片失败，请重试' });
    }
  }

  // ── 保存昵称/头像 ─────────────────────────────────────────
  private async saveProfile(): Promise<void> {
    const err = this.validateName();
    if (err !== '') { this.nameError = err; return; }
    this.nameError = '';
    this.isSaving = true;
    const db = DatabaseHelper.getInstance();
    try {
      const user = await db.queryUserByIdentifier(this.currentUser);
      if (!user || user.id === undefined) throw new Error('用户不存在');
      user.username = this.displayName.trim();
      user.avatarPath = this.avatarPath;
      if (this.phone) user.phone = this.phone;
      if (this.email) user.email = this.email;
      await db.updateUser(user);
      AppStorage.setOrCreate<string>('loggedInNickname', this.displayName.trim());
      AppStorage.setOrCreate<string>('loggedInAvatarPath', this.avatarPath);
      try {
        const ctx = getContext(this) as common.UIAbilityContext;
        const pref = preferences.getPreferencesSync(ctx, { name: 'guardian_auth' });
        pref.putSync('lastNickname', this.displayName.trim());
        pref.flush();
      } catch (_) {}
      const fields = new CloudUpdateFields();
      fields.username = this.displayName.trim();
      fields.avatarPath = this.avatarPath;
      CloudService.getInstance().updateUser(fields).then(r => {
        console.info('[Profile]: 云端同步', r.success ? '成功' : '失败:' + r.message);
      });
      this.isSaving = false;
      this.originalDisplayName = this.displayName.trim();
      this.originalAvatarPath = this.avatarPath;
      this.updateChangedState();
      promptAction.showToast({ message: '保存好啦', duration: 1500 });
      setTimeout(() => { this.pathStack.pop(); }, 1000);
    } catch (e) {
      this.isSaving = false;
      console.error('[Profile]: 保存失败', JSON.stringify(e));
      promptAction.showToast({ message: '保存失败，请重试' });
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
            .onChange((v: string) => { this.displayName = v; this.nameError = this.validateName(); this.updateChangedState(); })
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

  // ── 账号行 ────────────────────────────────────────────────
  @Builder
  AccountRow(): void {
    Row() {
      Text('账号').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).width(56)
      Text(this.currentUser).fontSize(15).fontColor(this.themeManager.colors.tertiaryTextColor).layoutWeight(1)
      Text('不可修改').fontSize(11).fontColor(this.themeManager.colors.tertiaryTextColor)
        .padding({ left: 8, right: 8, top: 3, bottom: 3 })
        .backgroundColor(this.themeManager.isDarkMode ? '#1e293b' : '#f1f5f9').borderRadius(6)
    }
    .width('100%').padding({ left: 16, right: 8, top: 14, bottom: 14 }).alignItems(VerticalAlign.Center)
  }

  // ── 标题栏 ────────────────────────────────────────────────
  @Builder
  GradientHeader(): void {
    Stack({ alignContent: Alignment.Top }) {
      Column()
        .width("100%").height(this.topSafeHeight + 100)
        .linearGradient({ direction: GradientDirection.Bottom,
          colors: [["#1e40af", 0.0], ["#3b82f6", 0.5], ["#60a5fa", 1.0]] })
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
        .borderRadius({ bottomLeft: "6%", bottomRight: "6%" })
      Row() {
        Image($r("app.media.ic_chevron_right")).width(36).height(36)
          .objectFit(ImageFit.Contain).padding(8)
          .backgroundColor("#33FFFFFF").borderRadius(100).rotate({ angle: 180 })
          .onClick((): void => { this.pathStack.pop(); })
        Text("个人资料").fontSize(22).fontWeight(FontWeight.Bold).fontColor("#ffffff")
          .margin({ left: "5%" }).layoutWeight(1)
        Text("保存").fontSize(15).fontColor("#ffffff")
          .padding({ left: 14, right: 14, top: 6, bottom: 6 })
          .backgroundColor("#33FFFFFF").borderRadius(20)
          .onClick((): void => {
            if (!this.hasChanged) { promptAction.showToast({ message: '你还没有进行修改' }); }
            else { this.saveProfile(); }
          })
      }
      .width("100%").padding({ left: "4%", right: "4%", top: this.topSafeHeight })
    }.width("100%")
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
Column() { this.AccountRow() }
                .width('92%').margin({ top: 12 }).backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius(14)

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
    .onBackPressed(() => {
      if (this.hasChanged) {
        AlertDialog.show({
          title: '提示', message: '有未保存的修改，是否保存？',
          primaryButton: { value: '不保存', action: () => { this.pathStack.pop(); } },
          secondaryButton: { value: '保存', action: () => { this.saveProfile(); } },
          cancel: () => {}, alignment: DialogAlignment.Center,
        });
        return true;
      }
      return false;
    })
    .onReady((context: NavDestinationContext) => { this.pathStack = context.pathStack; })
  }
}
