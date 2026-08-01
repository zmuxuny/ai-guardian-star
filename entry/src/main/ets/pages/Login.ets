// import { LoginWithHuaweiIDButton, loginComponentManager } from "@kit.AccountKit"; // 华为一键登录暂不可用
// import { BusinessError } from "@kit.BasicServicesKit";
import { ThemeManager } from "../common/ThemeManager";
import { DatabaseHelper, UserInfo } from "../database/DatabaseHelper";
import { UserManager } from "../common/UserManager";
import { CloudService, CloudUser } from "../common/CloudService";
import { preferences } from "@kit.ArkData";
import { common } from "@kit.AbilityKit";
import { promptAction } from "@kit.ArkUI";
import fs from '@ohos.file.fs';
import { util } from '@kit.ArkTS';
import { STORE_KEY_LOGGED_IN_USER, STORE_KEY_NICKNAME, STORE_KEY_AVATAR, STORE_KEY_AI_ENABLED, STORE_KEY_AI_ACCESS_LEVEL, PREF_NAME_AUTH, PREF_KEY_LAST_NICKNAME } from '../config';

@Builder
export function LoginBuilder() {
  Login();
}

@Preview
@Component
struct Login {
  pathStack: NavPathStack = new NavPathStack();
  @State username: string = "";
  @State password: string = "";
  @State isLoading: boolean = false;
  @State showPassword: boolean = false;
  @State loginBtnScale: number = 1.0;
  @State inputMode: number = 0;
  @State usernameError: string = "";
  @State rememberMe: boolean = false;
  @State registerMode: boolean = false;
  @State confirmPassword: string = "";
  @State verifyCode: string = "";
  @State challengeId: string = "";
  @State challengePhone: string = "";
  @State canSendCode: boolean = true;
  @State isSendingCode: boolean = false;
  @State themeManager: ThemeManager = ThemeManager.getInstance();

  /** 校验当前输入格式，返回错误信息（空字符串=通过） */
  private validateUsername(): string {
    const v = this.username.trim();
    if (v === "") return "";
    if (this.inputMode === 0) {
      // 手机号：11位数字，1开头
      return /^1[3-9]\d{9}$/.test(v) ? "" : "请输入正确的手机号";
    } else {
      // 邮箱：基本格式校验
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? "" : "请输入正确的邮箱地址";
    }
  }

  build() {
    NavDestination() {
      // ── Stack 层叠：渐变背景 + 表单卡片叠加，形成圆弧衔接 ──
      Stack({ alignContent: Alignment.Top }) {
        // 层1：渐变背景铺满全屏（含状态栏和底部安全区）
        Column()
          .width("100%")
          .height("100%")
          .linearGradient({
            direction: GradientDirection.Bottom,
            colors: [
              ["#0f2878", 0.0],
              ["#1e40af", 0.05],
              ["#2563eb", 0.2],
              ["#60a5fa", 0.35],
              ["#bfdbfe", 1.0],
            ],
          })
          .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])

        // 层2：整体内容列（Logo区 + 表单卡片）
        Column() {
          // ── Logo + 标语区 ─────────────────────────────────
          Column() {
            Column() {
              Image($r("app.media.logo"))
                .width(64)
                .height(64)
                .objectFit(ImageFit.Contain)
            }
            .width(88)
            .height(88)
            .borderRadius(44)
            .clip(true)
            .backgroundColor("rgba(255,255,255,0.15)")
            .border({ width: 2, color: "rgba(255,255,255,0.35)" })
            .justifyContent(FlexAlign.Center)
            .alignItems(HorizontalAlign.Center)
            .margin({ bottom: 14 })
            .gesture(
              LongPressGesture().onAction(() => {
                // 长按 Logo 进入数据库诊断工具
                promptAction.showToast({ message: "正在打开诊断工具...", duration: 1000 });
                this.pathStack.pushPathByName("DatabaseDiagnostic", null);
              }),
            )
            Text("智护星")
              .fontSize(24)
              .fontWeight(FontWeight.Bold)
              .fontColor("#ffffff")
              .margin({ bottom: 6 })
            Text("关怀我们的过去，保障我们的未来")
              .fontSize(12)
              .fontColor("rgba(255,255,255,0.78)")
              .textAlign(TextAlign.Center)
          }
          .width("100%")
          .height("38%")
          .justifyContent(FlexAlign.Center)
          .alignItems(HorizontalAlign.Center)

          // ── 表单卡片：顶部大圆角覆盖渐变，产生圆弧衔接 ──────
          Scroll() {
            Column() {
            Text(this.registerMode ? "注册账号" : "登录账号")
              .fontSize(18)
              .fontWeight(FontWeight.Bold)
              .fontColor(this.themeManager.colors.primaryTextColor)
              .alignSelf(ItemAlign.Start)
              .margin({ bottom: 4 })
            Text(this.registerMode
              ? "使用手机号验证码创建账号"
              : this.inputMode === 0 ? "使用手机号登录" : "邮箱仅支持已有账号登录")
              .fontSize(12)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .alignSelf(ItemAlign.Start)
              .margin({ bottom: 24 })

            // ── 手机号 / 邮箱 切换选项 ───────────────────────────
            if (!this.registerMode) {
            Row() {
              // 手机号 Tab
              Column() {
                Text("手机号")
                  .fontSize(14)
                  .fontWeight(this.inputMode === 0 ? FontWeight.Bold : FontWeight.Normal)
                  .fontColor(
                    this.inputMode === 0
                      ? this.themeManager.colors.primaryTextColor
                      : this.themeManager.colors.secondaryTextColor,
                  )
                // 选中指示线
                Column()
                  .width(this.inputMode === 0 ? "60%" : 0)
                  .height(2)
                  .backgroundColor("#3b82f6")
                  .borderRadius(1)
                  .animation({ duration: 200, curve: Curve.EaseOut })
                  .margin({ top: 4 })
              }
              .layoutWeight(1)
              .alignItems(HorizontalAlign.Center)
              .padding({ bottom: 4 })
              .onClick((): void => {
                this.inputMode = 0;
                this.username = "";
                this.usernameError = "";
              })

              // 邮箱 Tab
              Column() {
                Text("邮箱（已有账号）")
                  .fontSize(14)
                  .fontWeight(this.inputMode === 1 ? FontWeight.Bold : FontWeight.Normal)
                  .fontColor(
                    this.inputMode === 1
                      ? this.themeManager.colors.primaryTextColor
                      : this.themeManager.colors.secondaryTextColor,
                  )
                Column()
                  .width(this.inputMode === 1 ? "60%" : 0)
                  .height(2)
                  .backgroundColor("#3b82f6")
                  .borderRadius(1)
                  .animation({ duration: 200, curve: Curve.EaseOut })
                  .margin({ top: 4 })
              }
              .layoutWeight(1)
              .alignItems(HorizontalAlign.Center)
              .padding({ bottom: 4 })
              .onClick((): void => {
                this.inputMode = 1;
                this.username = "";
                this.usernameError = "";
              })
            }
            .width("100%")
            .margin({ bottom: 12 })
            .border({ width: { bottom: 1 }, color: this.themeManager.colors.separatorColor })
            }

            // 输入框 + 右侧状态图标
            Row() {
              TextInput({
                placeholder: this.inputMode === 0 ? "请输入手机号" : "请输入邮箱地址",
                text: this.username,
              })
                .onChange((v: string) => {
                  this.username = v;
                  this.usernameError = this.validateUsername();
                  if (v.trim() !== this.challengePhone) {
                    this.challengeId = "";
                  }
                })
                .layoutWeight(1)
                .fontSize(14)
                .type(this.inputMode === 0 ? InputType.PhoneNumber : InputType.Email)
                .backgroundColor(Color.Transparent)
                .placeholderColor(this.themeManager.colors.tertiaryTextColor)
                .fontColor(this.themeManager.colors.primaryTextColor)
                .border({ width: 0 })
                .padding({ left: 12, right: 4 })

              // 右侧校验状态图标
              if (this.username.trim().length > 0) {
                Text(this.usernameError === "" ? "✓" : "✕")
                  .fontSize(16)
                  .fontWeight(FontWeight.Bold)
                  .fontColor(this.usernameError === "" ? "#10b981" : "#ef4444")
                  .margin({ right: 12 })
                  .animation({ duration: 150, curve: Curve.EaseOut });
              }
            }
            .width("100%")
            .alignItems(VerticalAlign.Center)
            .backgroundColor(this.themeManager.isDarkMode ? "#0f172a" : "#f8fafc")
            .border({
              width: 1.5,
              color:
                this.username.trim().length === 0
                  ? this.themeManager.isDarkMode
                    ? "#334155"
                    : "#e2e8f0"
                  : this.usernameError === ""
                    ? "#10b981"
                    : "#ef4444",
            })
            .borderRadius(12)
            .margin({ bottom: this.usernameError !== "" ? 4 : 14 })

            // 格式错误提示文字
            if (this.usernameError !== "") {
              Text(this.usernameError)
                .fontSize(11)
                .fontColor("#ef4444")
                .alignSelf(ItemAlign.Start)
                .margin({ bottom: 10 })
                .animation({ duration: 150, curve: Curve.EaseOut });
            }

            // 密码输入框（无左图标，只右侧眼睛切换）
            Text("密码")
              .fontSize(12)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .alignSelf(ItemAlign.Start)
              .margin({ bottom: 6 })
            Row() {
              TextInput({
                placeholder: this.registerMode ? "请输入密码（至少8位）" : "请输入密码（至少4位）",
                text: this.password
              })
                .onChange((v: string) => {
                  this.password = v;
                })
                .layoutWeight(1)
                .fontSize(14)
                .type(this.showPassword ? InputType.Normal : InputType.Password)
                .backgroundColor(Color.Transparent)
                .placeholderColor(this.themeManager.colors.tertiaryTextColor)
                .fontColor(this.themeManager.colors.primaryTextColor)
                .border({ width: 0 })
                .padding({ left: 12, right: 0 })
            }
            .width("100%")
            .alignItems(VerticalAlign.Center)
            .backgroundColor(this.themeManager.isDarkMode ? "#0f172a" : "#f8fafc")
            .border({ width: 1.5, color: this.themeManager.isDarkMode ? "#334155" : "#e2e8f0" })
            .borderRadius(12)
            .margin({ bottom: 8 })

            if (this.registerMode) {
              Text("确认密码")
                .fontSize(12)
                .fontWeight(FontWeight.Medium)
                .fontColor(this.themeManager.colors.secondaryTextColor)
                .alignSelf(ItemAlign.Start)
                .margin({ bottom: 6, top: 6 })
              TextInput({ placeholder: "请再次输入密码", text: this.confirmPassword })
                .onChange((v: string) => {
                  this.confirmPassword = v;
                })
                .width("100%")
                .height(48)
                .fontSize(14)
                .type(this.showPassword ? InputType.Normal : InputType.Password)
                .backgroundColor(this.themeManager.isDarkMode ? "#0f172a" : "#f8fafc")
                .placeholderColor(this.themeManager.colors.tertiaryTextColor)
                .fontColor(this.themeManager.colors.primaryTextColor)
                .border({ width: 1.5, color: this.themeManager.isDarkMode ? "#334155" : "#e2e8f0" })
                .borderRadius(12)
                .padding({ left: 12, right: 12 })
                .margin({ bottom: 14 })

              Text("短信验证码")
                .fontSize(12)
                .fontWeight(FontWeight.Medium)
                .fontColor(this.themeManager.colors.secondaryTextColor)
                .alignSelf(ItemAlign.Start)
                .margin({ bottom: 6 })
              Row({ space: 8 }) {
                TextInput({ placeholder: "请输入验证码", text: this.verifyCode })
                  .onChange((v: string) => {
                    this.verifyCode = v;
                  })
                  .layoutWeight(1)
                  .height(48)
                  .fontSize(14)
                  .type(InputType.Number)
                  .backgroundColor(this.themeManager.isDarkMode ? "#0f172a" : "#f8fafc")
                  .placeholderColor(this.themeManager.colors.tertiaryTextColor)
                  .fontColor(this.themeManager.colors.primaryTextColor)
                  .border({ width: 1.5, color: this.themeManager.isDarkMode ? "#334155" : "#e2e8f0" })
                  .borderRadius(12)
                  .padding({ left: 12, right: 12 })
                Button(this.isSendingCode ? "发送中" : this.canSendCode ? "获取验证码" : "60 秒后重试")
                  .height(48)
                  .fontSize(12)
                  .fontColor(Color.White)
                  .backgroundColor("#3b82f6")
                  .borderRadius(12)
                  .enabled(this.canSendCode && !this.isSendingCode)
                  .onClick(() => {
                    this.handleSendCode();
                  })
              }
              .width("100%")
              .margin({ bottom: 14 })
            }

            Row({ space: 6 }) {
              Checkbox({ name: 'rememberMe', group: 'loginOptions' })
                .select(this.rememberMe)
                .selectedColor('#3b82f6')
                .width(20)
                .height(20)
                .onChange((value: boolean) => {
                  this.rememberMe = value;
                })
              Text('记住我')
                .fontSize(12)
                .fontColor(this.themeManager.colors.secondaryTextColor)
              Blank()
              if (!this.registerMode) {
                Text("忘记密码？")
                  .fontSize(12)
                  .fontColor("#3b82f6")
                  .fontWeight(FontWeight.Medium)
                  .onClick(() => {
                    AlertDialog.show({
                      title: "忘记密码",
                      message: "请联系管理员重置密码，或使用华为账号登录后重新绑定。",
                      primaryButton: { value: "知道了", action: () => {} },
                      alignment: DialogAlignment.Center,
                    });
                  })
              }
            }
            .width('100%')
            .margin({ bottom: 24 })

            // 登录按钮（带缩放动画）
            Button(this.isLoading
              ? this.registerMode ? "注册中..." : "登录中..."
              : this.registerMode ? "注册并登录" : "登录")
              .onClick(() => {
                this.loginBtnScale = 0.95;
                setTimeout(() => {
                  this.loginBtnScale = 1.0;
                }, 150);
                if (this.registerMode) {
                  this.handleRegister();
                } else {
                  this.handleLogin();
                }
              })
              .width("100%")
              .height(50)
              .fontSize(16)
              .fontWeight(FontWeight.Medium)
              .fontColor(Color.White)
              .linearGradient({
                direction: GradientDirection.Right,
                colors: this.isLoading
                  ? [
                      ["#94a3b8", 0.0],
                      ["#94a3b8", 1.0],
                    ]
                  : [
                      ["#1e40af", 0.0],
                      ["#3b82f6", 1.0],
                    ],
              })
              .borderRadius(100)
              .margin({ bottom: 20 })
              .enabled(!this.isLoading)
              .scale({ x: this.loginBtnScale, y: this.loginBtnScale })
              .animation({ duration: 120, curve: Curve.EaseInOut })

            Text(this.registerMode ? "已有账号？返回登录" : "注册新账号")
              .fontSize(12)
              .fontColor("#3b82f6")
              .margin({ bottom: 12 })
              .onClick(() => {
                this.registerMode = !this.registerMode;
                this.inputMode = 0;
                this.password = "";
                this.confirmPassword = "";
                this.verifyCode = "";
                this.challengeId = "";
                this.challengePhone = "";
                this.usernameError = this.validateUsername();
              })

            /* 华为一键登录暂时不可用
            Row() {
              Divider()
                .layoutWeight(1)
                .color(this.themeManager.colors.separatorColor)
                .strokeWidth(1)
              Text(" 其他登录方式 ")
                .fontSize(11)
                .fontColor(this.themeManager.colors.secondaryTextColor)
              Divider()
                .layoutWeight(1)
                .color(this.themeManager.colors.separatorColor)
                .strokeWidth(1)
            }
            .width("100%")
            .margin({ bottom: 16 })

            LoginWithHuaweiIDButton({
              params: {
                style: loginComponentManager.Style.BUTTON_RED,
                borderRadius: 100,
              },
              controller:
                new loginComponentManager.LoginWithHuaweiIDButtonController().onClickLoginWithHuaweiIDButton(
                  (error, response) => {
                    if (error) {
                      let msg = "登录失败";
                      if (error.code === 100004) msg = "环境不支持，请检查HMS Core";
                      if (error.code === 6003) msg = "证书指纹校验失败";
                      this.showAlert(msg);
                      return;
                    }
                    if (response) {
                      this.handleHuaweiLogin(response);
                    }
                  },
                ),
            })
              .width("100%")
              .height(50)
            */
            }
            .width("100%")
            .padding({ left: 24, right: 24, top: 28, bottom: 32 })
            .backgroundColor(this.themeManager.colors.cardBackgroundColor)
          }
          .layoutWeight(1)
          .width("100%")
          .backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .borderRadius({ topLeft: 24, topRight: 24, bottomLeft: 0, bottomRight: 0 })
          .constraintSize({ minHeight: "62%" })
          .scrollBar(BarState.Off)
          .edgeEffect(EdgeEffect.Spring)
          .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
        }
        // 外层 Column：占满全屏
        .width("100%")
        .height("100%")
      }
      // Stack 铺满全屏，背景深蓝防止安全区透白
      .width("100%")
      .height("100%")
      .backgroundColor("#0f2878")
    }
    //.expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])

    .hideTitleBar(true)
    .backgroundColor("#0f2878")
    // NavDestination 背景也设深蓝，彻底消除白边
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    });
  }

  // ── 核心登录逻辑 ──────────────────────────────────────────
  private async handleLogin(): Promise<void> {
    const uname = this.username.trim();
    const pwd = this.password.trim();
    if (uname === "") {
      this.showAlert("请输入账号");
      return;
    }

    // 格式校验
    const fmtErr = this.validateUsername();
    if (fmtErr !== "") {
      this.usernameError = fmtErr;
      this.showAlert(fmtErr);
      return;
    }

    if (pwd === "") {
      this.showAlert("请输入密码");
      return;
    }
    if (pwd.length < 4) {
      this.showAlert("密码至少4位");
      return;
    }

    this.isLoading = true;
    try {
      const db = DatabaseHelper.getInstance();
      const existing = await db.queryUserByIdentifier(uname);
      const result = await CloudService.getInstance().login(uname, pwd, this.rememberMe);
      if (!result.success || !result.user) {
        if (existing && result.message === '账号不存在') {
          this.showAlert('检测到本机旧账号，不能再使用本地密码登录。请使用手机号完成账号迁移。');
        } else {
          this.showAlert(result.message || '登录失败');
        }
        return;
      }

      await this.completeCloudLogin(uname, result.user, existing, "欢迎回来");
    } catch (_e) {
      CloudService.getInstance().clearSession();
      this.showAlert('登录失败，请重试');
    } finally {
      this.isLoading = false;
    }
  }

  private async handleSendCode(): Promise<void> {
    const phone = this.username.trim();
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      this.usernameError = "请输入正确的手机号";
      this.showAlert(this.usernameError);
      return;
    }
    this.isSendingCode = true;
    try {
      const result = await CloudService.getInstance().sendRegistrationCode(phone);
      if (!result.success || !result.challengeId) {
        this.showAlert(result.message || "验证码发送失败");
        return;
      }
      this.challengeId = result.challengeId;
      this.challengePhone = phone;
      this.canSendCode = false;
      promptAction.showToast({ message: "验证码已发送，5 分钟内有效", duration: 1800 });
      setTimeout(() => {
        this.canSendCode = true;
      }, 60000);
    } catch (_e) {
      this.showAlert("验证码发送失败，请稍后重试");
    } finally {
      this.isSendingCode = false;
    }
  }

  private async handleRegister(): Promise<void> {
    const phone = this.username.trim();
    const pwd = this.password.trim();
    const code = this.verifyCode.trim();
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      this.usernameError = "请输入正确的手机号";
      this.showAlert(this.usernameError);
      return;
    }
    if (pwd.length < 8) {
      this.showAlert("密码至少 8 位");
      return;
    }
    if (pwd !== this.confirmPassword.trim()) {
      this.showAlert("两次输入的密码不一致");
      return;
    }
    if (!/^\d{4,8}$/.test(code)) {
      this.showAlert("请输入正确的短信验证码");
      return;
    }
    if (this.challengeId === "" || this.challengePhone !== phone) {
      this.showAlert("请先获取当前手机号的验证码");
      return;
    }

    this.isLoading = true;
    try {
      const result = await CloudService.getInstance().register(
        phone, pwd, code, this.challengeId, this.rememberMe
      );
      if (!result.success || !result.user) {
        this.showAlert(result.message || "注册失败");
        return;
      }
      const existing = await DatabaseHelper.getInstance().queryUserByIdentifier(phone);
      await this.completeCloudLogin(phone, result.user, existing, "注册成功");
    } catch (_e) {
      CloudService.getInstance().clearSession();
      this.showAlert("注册失败，请重试");
    } finally {
      this.isLoading = false;
    }
  }

  private async completeCloudLogin(loginId: string, cloudUser: CloudUser,
    localUser: UserInfo | null, greeting: string): Promise<void> {
    const db = DatabaseHelper.getInstance();
    const displayName = cloudUser.nickname || cloudUser.username || loginId;
    if (localUser && localUser.id !== undefined) {
      localUser.username = displayName;
      localUser.phone = cloudUser.phone || (this.inputMode === 0 ? loginId : "");
      localUser.email = cloudUser.email || (this.inputMode === 1 ? loginId : "");
      localUser.address = cloudUser.address;
      await db.updateUser(localUser);
      await db.updatePasswordHash(localUser.id, "");
    } else {
      await db.insertUser({
        username: displayName,
        phone: cloudUser.phone || (this.inputMode === 0 ? loginId : ""),
        email: cloudUser.email || (this.inputMode === 1 ? loginId : ""),
        passwordHash: "",
        avatarPath: '',
        address: cloudUser.address,
        createTime: cloudUser.createTime,
      });
    }
    if ((cloudUser.avatarVersion || 0) > 0) {
      const storedUser = await db.queryUserByIdentifier(loginId);
      if (storedUser) await this.restoreCloudAvatar(storedUser);
    }
    promptAction.showToast({ message: `${greeting}，${displayName}`, duration: 1500 });
    await this.saveLoginAndJump(loginId, displayName);
  }

  private async restoreCloudAvatar(user: UserInfo): Promise<void> {
    const result = await CloudService.getInstance().downloadAvatar();
    if (!result.success || !result.imageBase64) return;
    let file: fs.File | undefined;
    try {
      const context = getContext(this) as common.UIAbilityContext;
      const avatarDir = context.filesDir + '/avatars';
      try { fs.mkdirSync(avatarDir); } catch (_e) {}
      const bytes = new util.Base64Helper().decodeSync(result.imageBase64);
      const path = avatarDir + '/cloud_avatar_' + Date.now() + '.jpg';
      file = fs.openSync(path, fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
      fs.writeSync(file.fd, bytes.buffer);
      fs.closeSync(file);
      file = undefined;
      const oldPath = user.avatarPath || '';
      user.avatarPath = path;
      await DatabaseHelper.getInstance().updateUser(user);
      AppStorage.setOrCreate<string>(STORE_KEY_AVATAR, path);
      if (oldPath.startsWith(avatarDir + '/') && oldPath !== path) {
        try { fs.unlinkSync(oldPath); } catch (_e) {}
      }
    } catch (e) {
      console.warn('[Login]: 云端头像恢复失败 ' + JSON.stringify(e));
    } finally {
      if (file !== undefined) { try { fs.closeSync(file); } catch (_e) {} }
    }
  }

  private async saveLoginAndJump(loginId: string, displayName: string = ""): Promise<void> {
    UserManager.getInstance().setCurrentUsername(loginId);
    AppStorage.setOrCreate<string>(STORE_KEY_LOGGED_IN_USER, loginId);
    AppStorage.setOrCreate<string>(STORE_KEY_NICKNAME, displayName || loginId);
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME_AUTH };
      const pref = preferences.getPreferencesSync(ctx, options);
      pref.putSync(PREF_KEY_LAST_NICKNAME, displayName || loginId);
      pref.flush();
    } catch (e) {
      console.warn("[Login]: Preferences 写入失败 " + JSON.stringify(e));
    }
    const aiEnabled = await DatabaseHelper.getInstance().loadSetting(loginId, STORE_KEY_AI_ENABLED);
    const savedAccessLevel = await DatabaseHelper.getInstance().loadSetting(loginId, STORE_KEY_AI_ACCESS_LEVEL);
    const aiAccessLevel = savedAccessLevel === 'full' || savedAccessLevel === 'basic'
      ? savedAccessLevel : 'privacy';
    AppStorage.setOrCreate<boolean>(STORE_KEY_AI_ENABLED, aiEnabled !== 'false');
    AppStorage.setOrCreate<string>(STORE_KEY_AI_ACCESS_LEVEL, aiAccessLevel);
    this.pathStack.replacePathByName("Layout", {}, false);
  }

  private showAlert(message: string): void {
    AlertDialog.show({
      title: "提示",
      message: message,
      alignment: DialogAlignment.Center,
      primaryButton: { value: "确定", action: () => {} },
      gridCount: 6,
      autoCancel: true,
    });
  }

}
