// import { LoginWithHuaweiIDButton, loginComponentManager } from "@kit.AccountKit"; // 华为一键登录暂不可用
// import { BusinessError } from "@kit.BasicServicesKit";
import { ThemeManager } from "../common/ThemeManager";
import { DatabaseHelper, UserInfo } from "../database/DatabaseHelper";
import { UserManager } from "../common/UserManager";
import { CloudService, CloudUser } from "../common/CloudService";
import { AiPermissionService } from '../common/AiPermissionService';
import { AvatarSyncService } from "../common/AvatarSyncService";
import { preferences } from "@kit.ArkData";
import { common } from "@kit.AbilityKit";
import { STORE_KEY_LOGGED_IN_USER, STORE_KEY_NICKNAME, STORE_KEY_AVATAR, STORE_KEY_AI_ENABLED, STORE_KEY_AI_ACCESS_LEVEL, PREF_NAME_AUTH, PREF_KEY_LAST_NICKNAME } from '../config';
import { showToast } from '../common/UiFeedback';
import { careIconTint } from '../common/CarePalette';

// 与 docs/ui-demo/login.html 同一套深绿玻璃配色，不随系统深浅色切换
const L_BASE = '#052A1F';
const L_ON2 = '#D6FFFFFF';
const L_INK = '#10231C';
const L_SOLID = '#0A5C43';
const L_ERR = '#FFB4A6';
const L_HINT = '#FFD0C6';
const L_LINE = '#2EFFFFFF';

@Extend(Text)
function fieldLabel() {
  .fontSize(13)
  .fontColor(L_ON2)
  .margin({ left: 4, bottom: 6 })
  .alignSelf(ItemAlign.Start)
}

@Extend(Text)
function segItem(on: boolean) {
  .layoutWeight(1)
  .height(40)
  .borderRadius(12)
  .textAlign(TextAlign.Center)
  .fontSize(15)
  .fontWeight(FontWeight.Medium)
  .fontColor(on ? L_INK : L_ON2)
  .backgroundColor(on ? Color.White : Color.Transparent)
}

@Extend(Row)
function glassBox() {
  .width('100%')
  .height(54)
  .borderRadius(18)
  .padding({ left: 16, right: 6 })
  .backgroundColor('#33000000')
  .alignItems(VerticalAlign.Center)
}

@Extend(TextInput)
function glassInput() {
  .layoutWeight(1)
  .height('100%')
  .fontSize(17)
  .fontColor(Color.White)
  .placeholderColor('#9EFFFFFF')
  .placeholderFont({ size: 17 })
  .caretColor(Color.White)
  .backgroundColor(Color.Transparent)
  .borderRadius(0)
  .padding(0)
}

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
  /** 忘记密码模式：手机号 + 短信验证码 + 新密码 */
  @State resetMode: boolean = false;
  @State confirmPassword: string = "";
  @State verifyCode: string = "";
  @State challengeId: string = "";
  @State challengePhone: string = "";
  @State canSendCode: boolean = true;
  @State isSendingCode: boolean = false;
  /** 重置流程：验证码是否已通过服务端校验，未通过时新密码输入框保持禁用 */
  @State codeVerified: boolean = false;
  @State isVerifyingCode: boolean = false;
  @State codeError: string = "";
  /** 当前聚焦的输入框，用来画白色聚焦描边 */
  @State focusField: string = "";
  @State viewHeight: number = 0;

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

  /** 重置流程未通过短信验证时，新密码相关输入框保持禁用 */
  private passwordFieldEnabled(): boolean {
    return !this.resetMode || this.codeVerified;
  }

  /** 输入框描边：出错浅红、聚焦白色、平时一圈细白线 */
  private boxBorder(field: string, error: boolean): BorderOptions {
    if (error) return { width: 2, color: L_ERR };
    if (this.focusField === field) return { width: 2, color: Color.White };
    return { width: 1, color: L_LINE };
  }

  private leaveField(field: string): void {
    if (this.focusField === field) this.focusField = "";
  }

  private switchInputMode(mode: number): void {
    if (this.inputMode === mode) return;
    this.getUIContext().animateTo({ duration: 250, curve: Curve.FastOutSlowIn }, () => {
      this.inputMode = mode;
    });
    this.username = "";
    this.usernameError = "";
  }

  private titleText(): string {
    return this.resetMode ? "重置密码" : this.registerMode ? "注册账号" : "智护星";
  }

  private subtitleText(): string {
    return this.resetMode
      ? "验证注册手机号后设置新密码"
      : this.registerMode ? "使用手机号验证码创建账号" : "关怀我们的过去，保障我们的未来";
  }

  @Builder
  Ambient(): void {
    // 每层都要各自延伸进安全区，否则状态栏和底部横条处会露出一条更暗的底色
    Stack() {
      Column().width("100%").height("100%").backgroundColor(L_BASE)
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
      Column().width("100%").height("100%")
        .radialGradient({ center: ["92%", "14%"], radius: 260, colors: [["#8017B07C", 0], ["#0017B07C", 1]] })
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
      Column().width("100%").height("100%")
        .radialGradient({ center: ["4%", "44%"], radius: 280, colors: [["#800B7A54", 0], ["#000B7A54", 1]] })
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
      Column().width("100%").height("100%")
        .radialGradient({ center: ["62%", "100%"], radius: 240, colors: [["#3D7BE0B8", 0], ["#007BE0B8", 1]] })
        .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .width("100%")
    .height("100%")
    .hitTestBehavior(HitTestMode.None)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }

  @Builder
  Brand(): void {
    Column() {
      // 同心圆标记：只在登录态显示；注册/重置表单更长，省出高度让整张卡一屏放下
      if (!this.registerMode && !this.resetMode) {
      Stack() {
        Circle({ width: 58, height: 58 }).fill(Color.Transparent).stroke(Color.White).strokeOpacity(0.35).strokeWidth(2.5)
        Circle({ width: 39, height: 39 }).fill(Color.Transparent).stroke(Color.White).strokeOpacity(0.7).strokeWidth(2.5)
        Circle({ width: 18, height: 18 }).fill(Color.White)
      }
      .width(64)
      .height(64)
      .accessibilityLevel("no")
      .margin({ bottom: 22 })
      }

      Text(this.titleText())
        .fontSize(56)
        .fontWeight(FontWeight.Bold)
        .fontColor(Color.White)
        .letterSpacing(-1)
        .lineHeight(60)
        .textShadow({ radius: 40, offsetY: 18, color: "#40000000" })
      Text(this.subtitleText())
        .fontSize(16)
        .fontColor(L_ON2)
        .margin({ top: 12 })
        .constraintSize({ maxWidth: 280 })
    }
    .width("100%")
    .alignItems(HorizontalAlign.Start)
    .padding({ left: 24, right: 24, top: this.registerMode || this.resetMode ? 28 : 72, bottom: 24 })
  }

  @Builder
  ModeSwitch(): void {
    Row({ space: 4 }) {
      Text("手机号")
        .segItem(this.inputMode === 0)
        .accessibilitySelected(this.inputMode === 0)
        .onClick((): void => { this.switchInputMode(0); })
      Text("邮箱（已有账号）")
        .segItem(this.inputMode === 1)
        .accessibilitySelected(this.inputMode === 1)
        .onClick((): void => { this.switchInputMode(1); })
    }
    .width("100%")
    .padding(4)
    .borderRadius(16)
    .backgroundColor("#38000000")
  }

  @Builder
  UserField(): void {
    Column() {
      Text(this.inputMode === 0 ? "手机号" : "邮箱").fieldLabel()
      Row() {
        if (this.inputMode === 0) {
          Text("+86")
            .fontSize(17)
            .fontColor(L_ON2)
            .padding({ right: 10 })
            .margin({ right: 10 })
            .border({ width: { right: 1 }, color: "#38FFFFFF" })
        }
        TextInput({
          placeholder: this.inputMode === 0 ? "请输入手机号" : "请输入邮箱地址",
          text: this.username,
        })
          .glassInput()
          .type(this.inputMode === 0 ? InputType.PhoneNumber : InputType.Email)
          .onFocus((): void => { this.focusField = "user"; })
          .onBlur((): void => { this.leaveField("user"); })
          .onChange((v: string) => {
            this.username = v;
            this.usernameError = this.validateUsername();
            if (v.trim() !== this.challengePhone) {
              // 换了号码，之前那条验证码会话作废
              this.challengeId = "";
              this.codeVerified = false;
              this.codeError = "";
            }
          })
      }
      .glassBox()
      .border(this.boxBorder("user", this.usernameError !== ""))

      if (this.usernameError !== "") {
        Row({ space: 6 }) {
          Image($r("app.media.login_alert")).width(16).height(16).colorFilter(careIconTint(L_HINT))
          Text(this.usernameError).fontSize(13).fontColor(L_HINT)
        }
        .margin({ top: 6, left: 4 })
        .alignSelf(ItemAlign.Start)
      }
    }
    .width("100%")
    .margin({ top: this.registerMode || this.resetMode ? 0 : 12 })
  }

  @Builder
  VerifyCodeField(): void {
    Column() {
      Text("短信验证码").fieldLabel()
      Row({ space: 8 }) {
        TextInput({ placeholder: "6 位验证码", text: this.verifyCode })
          .glassInput()
          .type(InputType.Number)
          .onFocus((): void => { this.focusField = "code"; })
          .onBlur((): void => { this.leaveField("code"); })
          .onChange((v: string) => {
            this.onVerifyCodeChange(v);
          })
        // 重置流程的校验状态
        if (this.resetMode && this.verifyCode.trim() !== "") {
          if (this.isVerifyingCode) {
            LoadingProgress().width(20).height(20).color(Color.White)
          } else if (this.codeVerified) {
            Image($r("app.media.login_check")).width(20).height(20).colorFilter(careIconTint("#7BE0B8"))
              .accessibilityText("验证码已通过")
          }
        }
        Button(this.isSendingCode ? "发送中" : this.canSendCode ? "获取验证码" : "60 秒后重试")
          .height(42)
          .padding({ left: 14, right: 14 })
          .borderRadius(14)
          .fontSize(14)
          .fontWeight(FontWeight.Medium)
          .fontColor(Color.White)
          .backgroundColor("#2EFFFFFF")
          .enabled(this.canSendCode && !this.isSendingCode)
          .opacity(this.canSendCode && !this.isSendingCode ? 1 : 0.6)
          .onClick(() => {
            this.handleSendCode();
          })
      }
      .glassBox()
      .border(this.boxBorder("code", this.codeError !== ""))

      if (this.codeError !== "") {
        Row({ space: 6 }) {
          Image($r("app.media.login_alert")).width(16).height(16).colorFilter(careIconTint(L_HINT))
          Text(this.codeError).fontSize(13).fontColor(L_HINT)
        }
        .margin({ top: 6, left: 4 })
        .alignSelf(ItemAlign.Start)
      }
    }
    .width("100%")
    .margin({ top: 12 })
  }

  @Builder
  PasswordField(): void {
    Column() {
      Text(this.resetMode ? "新密码" : "密码").fieldLabel()
      Row() {
        TextInput({
          placeholder: this.resetMode && !this.codeVerified ? "请先通过短信验证" : "至少 4 位",
          text: this.password,
        })
          .glassInput()
          .type(this.showPassword ? InputType.Normal : InputType.Password)
          .showPasswordIcon(false)
          .enabled(this.passwordFieldEnabled())
          .onFocus((): void => { this.focusField = "pw"; })
          .onBlur((): void => { this.leaveField("pw"); })
          .onChange((v: string) => {
            this.password = v;
          })
        Button({ type: ButtonType.Circle, stateEffect: true }) {
          Image(this.showPassword ? $r("app.media.login_eye") : $r("app.media.login_eye_off"))
            .width(22).height(22).opacity(0.84)
        }
        .width(44)
        .height(44)
        .backgroundColor(Color.Transparent)
        .enabled(this.passwordFieldEnabled())
        .accessibilityText(this.showPassword ? "隐藏密码" : "显示密码")
        .onClick((): void => { this.showPassword = !this.showPassword; })
      }
      .glassBox()
      .border(this.boxBorder("pw", false))
    }
    .width("100%")
    .margin({ top: 12 })
    .opacity(this.passwordFieldEnabled() ? 1 : 0.5)
  }

  @Builder
  ConfirmField(): void {
    Column() {
      Text(this.resetMode ? "确认新密码" : "确认密码").fieldLabel()
      Row() {
        TextInput({
          placeholder: this.resetMode ? "请再次输入新密码" : "请再次输入密码",
          text: this.confirmPassword,
        })
          .glassInput()
          .type(this.showPassword ? InputType.Normal : InputType.Password)
          .showPasswordIcon(false)
          .enabled(this.passwordFieldEnabled())
          .onFocus((): void => { this.focusField = "pw2"; })
          .onBlur((): void => { this.leaveField("pw2"); })
          .onChange((v: string) => {
            this.confirmPassword = v;
          })
      }
      .glassBox()
      .border(this.boxBorder("pw2", false))
    }
    .width("100%")
    .margin({ top: 12 })
    .opacity(this.passwordFieldEnabled() ? 1 : 0.5)
  }

  @Builder
  OptionsRow(): void {
    Row() {
      Row({ space: 8 }) {
        Checkbox({ name: "rememberMe", group: "loginOptions" })
          .select(this.rememberMe)
          .shape(CheckBoxShape.ROUNDED_SQUARE)
          .selectedColor(Color.White)
          .unselectedColor("#B3FFFFFF")
          .mark({ strokeColor: L_SOLID, size: 14, strokeWidth: 2 })
          .width(22)
          .height(22)
          .margin(0)
          .onChange((value: boolean) => {
            this.rememberMe = value;
          })
        Text("记住我").fontSize(15).fontColor(Color.White)
      }
      .height(44)
      .onClick((): void => { this.rememberMe = !this.rememberMe; })

      Blank()
      if (!this.registerMode) {
        Text("忘记密码？")
          .fontSize(15)
          .fontWeight(FontWeight.Medium)
          .fontColor(Color.White)
          .height(44)
          .onClick(() => { this.enterResetMode(); })
      }
    }
    .width("100%")
    .margin({ top: 10 })
  }

  @Builder
  FormCard(): void {
    Column() {
      if (!this.registerMode && !this.resetMode) {
        this.ModeSwitch()
      }
      this.UserField()
      // 重置流程先验手机号：验证码通过前，下面的新密码输入框保持禁用
      if (this.resetMode) {
        this.VerifyCodeField()
      }
      this.PasswordField()
      if (this.registerMode || this.resetMode) {
        this.ConfirmField()
      }
      if (this.registerMode) {
        this.VerifyCodeField()
      }
      if (!this.resetMode) {
        this.OptionsRow()
      }

      Button(this.isLoading
        ? this.resetMode ? "提交中..." : this.registerMode ? "注册中..." : "登录中..."
        : this.resetMode ? "重置密码" : this.registerMode ? "注册并登录" : "登录")
        .onClick(() => {
          this.loginBtnScale = 0.96;
          setTimeout(() => {
            this.loginBtnScale = 1.0;
          }, 150);
          if (this.resetMode) {
            this.handleResetPassword();
          } else if (this.registerMode) {
            this.handleRegister();
          } else {
            this.handleLogin();
          }
        })
        .width("100%")
        .height(56)
        .borderRadius(28)
        .backgroundColor(Color.White)
        .fontColor(L_SOLID)
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .shadow({ radius: 20, offsetY: 10, color: "#59000000" })
        .margin({ top: this.resetMode ? 16 : 6 })
        .enabled(!this.isLoading)
        .opacity(this.isLoading ? 0.75 : 1)
        .scale({ x: this.loginBtnScale, y: this.loginBtnScale })
        .animation({ duration: 120, curve: Curve.EaseInOut })

      Text() {
        Span(this.resetMode || this.registerMode ? "已有账号？" : "还没有账号？").fontColor(L_ON2)
        Span(this.resetMode || this.registerMode ? "返回登录" : "注册").fontColor(Color.White).fontWeight(FontWeight.Bold)
      }
      .fontSize(15)
      .height(44)
      .padding({ left: 16, right: 16 })
      .margin({ top: 6 })
      .onClick(() => {
        if (this.resetMode) {
          this.resetMode = false;
        } else {
          this.registerMode = !this.registerMode;
        }
        this.clearFormState();
      })
    }
    .width("100%")
    .constraintSize({ maxWidth: 560 })
    .padding({ left: 16, right: 16, top: 18, bottom: 16 })
    .borderRadius(28)
    .backgroundEffect({ radius: 22, saturation: 1.7, color: "#21FFFFFF" })
    .border({ width: 1, color: "#2EFFFFFF" })
    .shadow({ radius: 30, offsetY: 16, color: "#59000000" })
  }

  build() {
    NavDestination() {
      Stack({ alignContent: Alignment.Top }) {
        this.Ambient()
        // 上半屏品牌大字，表单整块玻璃卡贴底；内容少时卡片沉底，键盘弹起可滚动
        Scroll() {
          Column() {
            this.Brand()
            Column() {
              this.FormCard()
            }
            .width("100%")
            .alignItems(HorizontalAlign.Center)
            .padding({ left: 16, right: 16, bottom: 18 })
          }
          .width("100%")
          .constraintSize({ minHeight: this.viewHeight })
          .justifyContent(FlexAlign.SpaceBetween)
        }
        .width("100%")
        .height("100%")
        .scrollBar(BarState.Off)
        .edgeEffect(EdgeEffect.Spring)
        .onAreaChange((_old: Area, area: Area): void => {
          this.viewHeight = Number(area.height);
        })
      }
      .width("100%")
      .height("100%")
      .backgroundColor(L_BASE)
    }
    .hideTitleBar(true)
    .backgroundColor(L_BASE)
    // 深色底：状态栏和导航条用白色图标
    .onShown((): void => { ThemeManager.getInstance().updateSystemUI(true); })
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

  /** 切换模式时清掉表单残留，避免验证码会话串到另一个流程 */
  private clearFormState(): void {
    this.inputMode = 0;
    this.password = "";
    this.confirmPassword = "";
    this.verifyCode = "";
    this.challengeId = "";
    this.challengePhone = "";
    this.codeVerified = false;
    this.codeError = "";
    this.usernameError = this.validateUsername();
  }

  /** 重置流程下验证码填满 6 位就自动送去服务端校验 */
  private onVerifyCodeChange(v: string): void {
    this.verifyCode = v;
    if (!this.resetMode) return;
    this.codeVerified = false;
    this.codeError = "";
    const code = v.trim();
    if (/^\d{6}$/.test(code) && !this.isVerifyingCode) {
      this.verifyResetCode(code);
    }
  }

  private async verifyResetCode(code: string): Promise<void> {
    const phone = this.username.trim();
    if (this.challengeId === "" || this.challengePhone !== phone) {
      this.codeError = "请先获取当前手机号的验证码";
      return;
    }
    this.isVerifyingCode = true;
    try {
      const result = await CloudService.getInstance()
        .verifyPasswordResetCode(phone, code, this.challengeId);
      if (result.success) {
        this.codeVerified = true;
        this.codeError = "";
      } else {
        this.codeVerified = false;
        this.codeError = result.message || "验证码错误";
      }
    } catch (_e) {
      this.codeVerified = false;
      this.codeError = "验证失败，请稍后重试";
    } finally {
      this.isVerifyingCode = false;
    }
  }

  private enterResetMode(): void {
    this.resetMode = true;
    this.registerMode = false;
    this.clearFormState();
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
      const cloud = CloudService.getInstance();
      // 重置流程要求手机号已注册，注册流程要求未注册，服务端各自判重后返回提示
      const result = this.resetMode
        ? await cloud.sendPasswordResetCode(phone)
        : await cloud.sendRegistrationCode(phone);
      if (!result.success || !result.challengeId) {
        this.showAlert(result.message || "验证码发送失败");
        return;
      }
      this.challengeId = result.challengeId;
      this.challengePhone = phone;
      this.verifyCode = "";
      this.codeVerified = false;
      this.codeError = "";
      this.canSendCode = false;
      showToast(this.getUIContext(), { message: "验证码已发送，5 分钟内有效", duration: 1800 });
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
    if (pwd.length < 4) {
      this.showAlert("密码至少 4 位");
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

  /** 忘记密码：校验短信验证码后设置新密码，成功后回到登录页 */
  private async handleResetPassword(): Promise<void> {
    const phone = this.username.trim();
    const pwd = this.password.trim();
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      this.usernameError = "请输入正确的手机号";
      this.showAlert(this.usernameError);
      return;
    }
    if (this.challengeId === "" || this.challengePhone !== phone) {
      this.showAlert("请先获取当前手机号的验证码");
      return;
    }
    if (!this.codeVerified) {
      this.showAlert("请先通过短信验证码验证手机号");
      return;
    }
    if (pwd.length < 4) {
      this.showAlert("新密码至少 4 位");
      return;
    }
    if (pwd !== this.confirmPassword.trim()) {
      this.showAlert("两次输入的密码不一致");
      return;
    }

    this.isLoading = true;
    try {
      const result = await CloudService.getInstance()
        .resetPassword(phone, pwd, this.challengeId);
      if (!result.success) {
        this.showAlert(result.message || "密码重置失败");
        return;
      }
      // 服务端已清掉该账号全部会话，本地也要清干净，避免旧凭据残留
      await CloudService.getInstance().clearPersistedSession();
      CloudService.getInstance().clearSession();
      this.resetMode = false;
      this.clearFormState();
      this.username = phone;
      this.usernameError = "";
      showToast(this.getUIContext(), { message: "密码已重置，请用新密码登录", duration: 2000 });
    } catch (_e) {
      this.showAlert("密码重置失败，请稍后重试");
    } finally {
      this.isLoading = false;
    }
  }

  private async completeCloudLogin(loginId: string, cloudUser: CloudUser,
    localUser: UserInfo | null, greeting: string): Promise<void> {
    const db = DatabaseHelper.getInstance();
    const displayName = cloudUser.nickname || cloudUser.username || loginId;
    let syncedUser: UserInfo;
    if (localUser && localUser.id !== undefined) {
      localUser.username = displayName;
      localUser.phone = cloudUser.phone || (this.inputMode === 0 ? loginId : "");
      localUser.email = cloudUser.email || (this.inputMode === 1 ? loginId : "");
      localUser.address = cloudUser.address;
      await db.updateUser(localUser);
      await db.updatePasswordHash(localUser.id, "");
      syncedUser = localUser;
    } else {
      syncedUser = {
        username: displayName,
        phone: cloudUser.phone || (this.inputMode === 0 ? loginId : ""),
        email: cloudUser.email || (this.inputMode === 1 ? loginId : ""),
        passwordHash: "",
        avatarPath: '',
        address: cloudUser.address,
        createTime: cloudUser.createTime,
      };
      syncedUser.id = await db.insertUser(syncedUser);
    }
    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    await AvatarSyncService.sync(context, loginId, syncedUser);
    showToast(this.getUIContext(), { message: `${greeting}，${displayName}`, duration: 1500 });
    await this.saveLoginAndJump(loginId, displayName);
  }

  private async saveLoginAndJump(loginId: string, displayName: string = ""): Promise<void> {
    UserManager.getInstance().setCurrentUsername(loginId);
    AppStorage.setOrCreate<string>(STORE_KEY_LOGGED_IN_USER, loginId);
    AppStorage.setOrCreate<string>(STORE_KEY_NICKNAME, displayName || loginId);
    try {
      const ctx = this.getUIContext().getHostContext() as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME_AUTH };
      const pref = preferences.getPreferencesSync(ctx, options);
      pref.putSync(PREF_KEY_LAST_NICKNAME, displayName || loginId);
      pref.flush();
    } catch (e) {
      console.warn("[Login]: Preferences 写入失败 " + JSON.stringify(e));
    }
    await AiPermissionService.getInstance().sync();
    this.pathStack.replacePathByName("Layout", {}, false);
  }

  private showAlert(message: string): void {
    this.getUIContext().showAlertDialog({
      title: "提示",
      message: message,
      alignment: DialogAlignment.Center,
      primaryButton: { value: "确定", action: () => {} },
      gridCount: 6,
      autoCancel: true,
    });
  }

}
