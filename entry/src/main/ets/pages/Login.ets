import { authentication, LoginWithHuaweiIDButton, loginComponentManager } from "@kit.AccountKit";
import { BusinessError } from "@kit.BasicServicesKit";
import { ThemeManager } from "../common/ThemeManager";
import { DatabaseHelper, UserInfo } from "../database/DatabaseHelper";
import { UserManager } from "../common/UserManager";
import { preferences } from "@kit.ArkData";
import { common } from "@kit.AbilityKit";
import { promptAction } from "@kit.ArkUI";

export const STORAGE_KEY_LOGGED_IN_USER = "loggedInUsername";
const PREF_NAME = "guardian_auth";
const PREF_KEY_USERNAME = "lastUsername";

interface LoginResult {
  name: string;
  isNew: boolean;
}

// ── 注册验证弹框 ──────────────────────────────────────────
@CustomDialog
struct VerifyDialog {
  controller!: CustomDialogController;
  themeManager: ThemeManager = ThemeManager.getInstance();
  onCancel: () => void = () => {};
  onConfirm: () => void = () => {};

  @State code: string = "";
  @State countdown: number = 0;
  @State hasSent: boolean = false;
  private timer: number = -1;

  private startCountdown(): void {
    this.countdown = 60;
    this.hasSent = true;
    this.timer = setInterval(() => {
      this.countdown--;
      if (this.countdown <= 0) {
        clearInterval(this.timer);
        this.countdown = 0;
      }
    }, 1000) as number;
  }

  aboutToDisappear(): void {
    if (this.timer !== -1) clearInterval(this.timer);
  }

  build() {
    Column() {
      Text("身份验证")
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .margin({ bottom: 20 })
      Row({ space: 10 }) {
        TextInput({ placeholder: "请输入验证码", text: this.code })
          .onChange((v: string) => {
            this.code = v;
          })
          .layoutWeight(1)
          .fontSize(14)
          .type(InputType.Number)
          .backgroundColor(this.themeManager.isDarkMode ? "#0f172a" : "#f8fafc")
          .fontColor(this.themeManager.colors.primaryTextColor)
          .placeholderColor(this.themeManager.colors.tertiaryTextColor)
          .border({ width: 1.5, color: this.themeManager.isDarkMode ? "#334155" : "#e2e8f0" })
          .borderRadius(12)
        Button(this.countdown > 0 ? `${this.countdown}s` : this.hasSent ? "重新发送" : "发送")
          .fontSize(12)
          .fontColor(this.countdown > 0 ? "#94a3b8" : "#3b82f6")
          .backgroundColor(
            this.countdown > 0
              ? this.themeManager.isDarkMode
                ? "#1e293b"
                : "#f1f5f9"
              : this.themeManager.isDarkMode
                ? "#1e3a5f"
                : "#eff6ff",
          )
          .border({
            width: 1,
            color:
              this.countdown > 0
                ? this.themeManager.isDarkMode
                  ? "#334155"
                  : "#e2e8f0"
                : "#bfdbfe",
          })
          .borderRadius(12)
          .height(40)
          .width(90)
          .type(ButtonType.Normal)
          .enabled(this.countdown === 0)
          .onClick(() => {
            this.startCountdown();
          })
      }
      .width("100%")
      .margin({ bottom: 16 })
      Text("测试阶段：直接点击确认即可进入")
        .fontSize(11)
        .fontColor(this.themeManager.colors.tertiaryTextColor)
        .textAlign(TextAlign.Center)
        .margin({ bottom: 24 })
      Row({ space: 12 }) {
        Button("取消")
          .layoutWeight(1)
          .height(44)
          .type(ButtonType.Normal)
          .backgroundColor(this.themeManager.isDarkMode ? "#1e293b" : "#f1f5f9")
          .fontColor(this.themeManager.colors.secondaryTextColor)
          .fontSize(14)
          .borderRadius(12)
          .onClick(() => {
            this.controller.close();
            this.onCancel();
          })
        Button("确认")
          .layoutWeight(1)
          .height(44)
          .type(ButtonType.Normal)
          .linearGradient({
            direction: GradientDirection.Right,
            colors: [
              ["#1e40af", 0.0],
              ["#3b82f6", 1.0],
            ],
          })
          .fontColor(Color.White)
          .fontSize(14)
          .borderRadius(12)
          .onClick(() => {
            this.controller.close();
            this.onConfirm();
          })
      }.width("100%")
    }
    .width("100%")
    .padding({ left: 24, right: 24, top: 28, bottom: 24 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .borderRadius(20);
  }
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
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  private pendingRegisterName: string = "";

  // ✅ CustomDialogController 必须作为成员变量声明，不能在方法里 new
  private verifyDialogController: CustomDialogController = new CustomDialogController({
    builder: VerifyDialog({
      themeManager: ThemeManager.getInstance(),
      onCancel: () => {}, // 占位，实际在 showVerifyDialog 里通过重新赋值更新
      onConfirm: () => {},
    }),
    alignment: DialogAlignment.Center,
    cornerRadius: 20,
    maskColor: "rgba(0,0,0,0.5)",
  });

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
          Column() {
            Text("登录账号")
              .fontSize(18)
              .fontWeight(FontWeight.Bold)
              .fontColor(this.themeManager.colors.primaryTextColor)
              .alignSelf(ItemAlign.Start)
              .margin({ bottom: 4 })
            Text("未注册将自动创建新账号")
              .fontSize(12)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .alignSelf(ItemAlign.Start)
              .margin({ bottom: 24 })

            // ── 手机号 / 邮箱 切换选项 ───────────────────────────
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
                Text("邮箱")
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

            // 输入框 + 右侧状态图标
            Row() {
              TextInput({
                placeholder: this.inputMode === 0 ? "请输入手机号" : "请输入邮箱地址",
                text: this.username,
              })
                .onChange((v: string) => {
                  this.username = v;
                  this.usernameError = this.validateUsername();
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
              TextInput({ placeholder: "请输入密码（至少4位）", text: this.password })
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

            // 忘记密码
            Text("忘记密码？")
              .fontSize(12)
              .fontColor("#3b82f6")
              .fontWeight(FontWeight.Medium)
              .alignSelf(ItemAlign.End)
              .margin({ bottom: 24 })
              .onClick(() => {
                AlertDialog.show({
                  title: "忘记密码",
                  message: "请联系管理员重置密码，或使用华为账号登录后重新绑定。",
                  primaryButton: { value: "知道了", action: () => {} },
                  alignment: DialogAlignment.Center,
                });
              })

            // 登录/注册按钮（带缩放动画）
            Button(this.isLoading ? "处理中..." : "登录 / 注册")
              .onClick(() => {
                this.loginBtnScale = 0.95;
                setTimeout(() => {
                  this.loginBtnScale = 1.0;
                }, 150);
                this.handleLogin();
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

            // 分割线
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

            // 华为官方登录按钮
            LoginWithHuaweiIDButton({
              params: {
                style: loginComponentManager.Style.BUTTON_RED,
                borderRadius: 100,
              },
              controller:
                new loginComponentManager.LoginWithHuaweiIDButtonController().onClickLoginWithHuaweiIDButton(
                  (error: BusinessError, response: loginComponentManager.HuaweiIDCredential) => {
                    if (error) {
                      let msg = "登录失败";
                      if (error.code === 100004) msg = "环境不支持，请检查HMS Core";
                      if (error.code === 6003) msg = "证书指纹校验失败";
                      this.showAlert(msg);
                      return;
                    }
                    if (response) {
                      try {
                        const data = (response as authentication.LoginWithHuaweiIDResponse).data;
                        if (data) this.saveLoginAndJump("HW_" + data.openID.substring(0, 8));
                      } catch (e) {
                        console.error("[Login]: 华为登录解析异常 " + JSON.stringify(e));
                      }
                    }
                  },
                ),
            })
              .width("100%")
              .height(50)
          }
          .layoutWeight(3)
          .width("100%")
          .padding({ left: 24, right: 24, top: 28, bottom: 32 })
          .backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .borderRadius({ topLeft: 24, topRight: 24, bottomLeft: 0, bottomRight: 0 })
          .layoutWeight(1)
          // 撑满剩余空间到屏幕底部
          .constraintSize({ minHeight: "62%" })
          // 保底高度，防止内容少时底部露白
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
  private handleLogin(): void {
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
    const db = DatabaseHelper.getInstance();

    db.queryUserByUsername(uname)
      .then((existing: UserInfo | null) => {
        if (existing === null) {
          // 新账号：先写库，再弹验证框
          return db
            .insertUser({
              username: uname,
              phone: this.inputMode === 0 ? uname : "", // 如果是手机号登录，保存手机号
              passwordHash: pwd,
              createTime: Date.now(),
            })
            .then(() => {
              const r: LoginResult = { name: uname, isNew: true };
              return r;
            });
        } else {
          if (existing.passwordHash !== pwd) {
            this.isLoading = false;
            this.showAlert("密码不正确");
            return Promise.reject("wrong_password");
          }
          const r: LoginResult = { name: uname, isNew: false };
          return Promise.resolve(r);
        }
      })
      .then((result: LoginResult) => {
        this.isLoading = false;
        if (result.isNew) {
          // 新用户：弹出验证码弹框
          this.showVerifyDialog(result.name);
        } else {
          // 老用户：底部 Toast 后自动跳转
          promptAction.showToast({ message: `欢迎回来，${result.name}`, duration: 1500 });
          setTimeout(() => {
            this.saveLoginAndJump(result.name);
          }, 800);
        }
      })
      .catch((e: string | Error) => {
        this.isLoading = false;
        if (e !== "wrong_password") this.showAlert("登录失败，请重试");
      });
  }

  /** 弹出注册验证弹框 */
  private showVerifyDialog(username: string): void {
    this.pendingRegisterName = username;
    // 每次弹出时重建 controller，绑定最新的 username 和回调
    this.verifyDialogController = new CustomDialogController({
      builder: VerifyDialog({
        themeManager: this.themeManager,
        onCancel: () => {
          // 取消：仅关闭弹框，留在登录页
        },
        onConfirm: () => {
          // 确认：Toast 提示后直接进入主界面
          promptAction.showToast({ message: `🎉 注册成功，欢迎加入守护星！`, duration: 1500 });
          setTimeout(() => {
            this.saveLoginAndJump(username);
          }, 600);
        },
      }),
      alignment: DialogAlignment.Center,
      cornerRadius: 20,
      maskColor: "rgba(0,0,0,0.5)",
    });
    this.verifyDialogController.open();
  }

  private saveLoginAndJump(username: string): void {
    UserManager.getInstance().setCurrentUsername(username);
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME };
      const pref = preferences.getPreferencesSync(ctx, options);
      pref.putSync(PREF_KEY_USERNAME, username);
      pref.flush();
    } catch (e) {
      console.warn("[Login]: Preferences 写入失败 " + JSON.stringify(e));
    }
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
