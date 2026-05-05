/**
 * person.ets — 个人中心页面
 * 显示用户信息、统计数据和系统设置
 */
import { ThemeManager, ThemeMode } from "../common/ThemeManager";
import { MqttManager } from "./MqttManager";
import { GradientHeader } from '../components/GradientHeader';
import { StatDashboard } from '../components/StatDashboard';
import { MenuRow } from '../components/MenuRow';
import { promptAction } from "@kit.ArkUI";
import {
  DatabaseHelper,
  HealthEvent,
  FREE_RETENTION_DAYS,
  STORAGE_KEY_RETENTION,
  UserInfo,
} from "../database/DatabaseHelper";
import { preferences } from "@kit.ArkData";
import { common, abilityAccessCtrl } from "@kit.AbilityKit";
import { UserManager } from "../common/UserManager";
import { STORAGE_KEY_LOGGED_IN_USER } from "./Login";
import cameraPicker from "@ohos.multimedia.cameraPicker";
import camera from "@ohos.multimedia.camera";
import fs from "@ohos.file.fs";
import http from "@ohos.net.http";
import { BOARD_UPLOAD_URL, STORE_KEY_NICKNAME, STORE_KEY_AVATAR, PREF_NAME_AUTH, PREF_KEY_LAST_NICKNAME } from '../config';
import { fileUri } from "@kit.CoreFileKit";
@Builder
export function personBuilder(): void {
  NavDestination() {
    person()
  }.hideTitleBar(true);
}
@Component
export struct person {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State userName: string = "";
  @StorageProp(STORE_KEY_NICKNAME) userNickname: string = "";
  @StorageProp(STORE_KEY_AVATAR) userAvatarPath: string = "";
  @State useDays: number = 128;
  @State totalAlertCount: number = 0;
  @StorageLink(STORAGE_KEY_RETENTION) retentionDays: number = FREE_RETENTION_DAYS;
  @StorageProp("topSafeHeight") topSafeHeight: number = 48;
  // 各菜单行按压状态
  @State pressedRow: string = "";
  // 退出登录按钮缩放
  @State logoutScale: number = 1.0;
  // 导航路径栈
  pathStack: NavPathStack = new NavPathStack();

  private async takePhotoAndSendToBoard(context: common.UIAbilityContext): Promise<void> {
    // ── Step 0: 运行时动态申请相机权限 ────────────────────────────────────
    // module.json5 里的静态声明只是"告知系统该应用需要此权限"，
    // HarmonyOS NEXT 上还必须在运行时主动弹窗请求，才能真正拿到授权。
    const atManager = abilityAccessCtrl.createAtManager();
    const grantResult = await atManager.requestPermissionsFromUser(
      context, ['ohos.permission.CAMERA']
    );
    // authResults[0] === 0 表示已授权；非 0（如 -1）表示用户拒绝
    if (grantResult.authResults[0] !== 0) {
      promptAction.showToast({ message: '需要相机权限才能录入人脸，请在系统设置中开启' });
      console.warn('[person]: 相机权限被拒绝，authResult=' + grantResult.authResults[0]);
      return;
    }
    // ─────────────────────────────────────────────────────────────────────

    // 在应用沙箱 cacheDir 预先创建临时文件，并通过 saveUri 告知系统相机直接写入此处
    // 这样 resultUri 返回的就是可直接读取的沙箱 file:// 路径，无需额外拷贝
    const sandboxPath = context.cacheDir + '/face_upload_temp.jpg';
    let httpRequest = http.createHttp();

    try {
      // Step 1: 在沙箱预创建目标文件，供 saveUri 使用
      // CREATE | WRITE_ONLY 确保文件存在且为空
      let tempFile = fs.openSync(sandboxPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
      fs.closeSync(tempFile);

      // Step 2: 将沙箱路径转为 file:// URI 格式传给 saveUri
      const sandboxUri = fileUri.getUriFromPath(sandboxPath);

      // Step 3: 调起前置相机拍照，saveUri 指定相机把照片直接写入沙箱文件
      let pickerProfile: cameraPicker.PickerProfile = {
        cameraPosition: camera.CameraPosition.CAMERA_POSITION_FRONT,
        saveUri: sandboxUri,
      };
      let pickerResult = await cameraPicker.pick(
        context,
        [cameraPicker.PickerMediaType.PHOTO],
        pickerProfile,
      );

      // resultCode 非 0 或 URI 为空 = 用户取消，静默退出
      if (pickerResult.resultCode !== 0 || pickerResult.resultUri === '') {
        console.log('[person]: 用户取消拍照');
        httpRequest.destroy();
        return;
      }

      // Step 4: 直接读取沙箱文件（saveUri 已保证照片落地于此）
      let file = fs.openSync(sandboxPath, fs.OpenMode.READ_ONLY);
      let fileStat = fs.statSync(file.fd);
      if (fileStat.size === 0) {
        fs.closeSync(file);
        throw new Error('照片文件为空，拍照可能未成功写入');
      }
      let buffer = new ArrayBuffer(fileStat.size);
      fs.readSync(file.fd, buffer);
      fs.closeSync(file);

      promptAction.showToast({ message: '正在上传人脸信息...' });

      // Step 5: POST 原始图片数据到开发板
      let response = await httpRequest.request(BOARD_UPLOAD_URL, {
        method: http.RequestMethod.POST,
        header: { 'Content-Type': 'image/jpeg' },
        extraData: buffer,
        connectTimeout: 8000,
        readTimeout: 8000,
      });

      if (response.responseCode === 200 || response.responseCode === 201) {
        promptAction.showToast({ message: '人脸信息上传成功，开发板已接收' });
      } else {
        promptAction.showToast({ message: '上传失败，状态码: ' + response.responseCode });
      }
    } catch (error) {
      console.error('[person]: 人脸录入流程出错', JSON.stringify(error));
      promptAction.showToast({ message: '操作失败，请重试' });
    } finally {
      httpRequest.destroy();
      // 阅后即焚：无论流程成败，沙箱临时文件必须销毁
      try {
        fs.unlinkSync(sandboxPath);
        console.log('[person]: 人脸临时文件已销毁');
      } catch (e) {
        // 文件不存在时忽略（Step1 之前就失败的场景）
      }
    }
  }

  aboutToAppear(): void {
    this.loadUserInfo();
    // 监听 Profile 页保存后的 AppStorage 广播，实时刷新昵称和头像
    AppStorage.setOrCreate<string>(STORE_KEY_NICKNAME, AppStorage.get<string>(STORE_KEY_NICKNAME) ?? '');
    AppStorage.setOrCreate<string>(STORE_KEY_AVATAR, AppStorage.get<string>(STORE_KEY_AVATAR) ?? '');
  }

  /** 手机号加密处理：只显示前 3 位和后 4 位，中间用 * 替代 */
  private encryptPhone(phone: string): string {
    if (!phone || phone.length < 7) {
      return phone;
    }
    // 保留前 3 位和后 4 位，中间用 * 替代
    const prefix = phone.substring(0, 3);
    const suffix = phone.substring(phone.length - 4);
    const maskLength = phone.length - 7;
    const mask = "*".repeat(maskLength);
    return prefix + mask + suffix;
  }

  /** 加载用户信息 */
  private loadUserInfo(): void {
    const currentUser = UserManager.getInstance().getCurrentUsername();
    const db = DatabaseHelper.getInstance();

    console.log(`[person]: 开始加载用户信息，currentUser=${currentUser}`);

    // 从数据库加载当前用户信息
    db.queryUserByIdentifier(currentUser)
      .then((user: UserInfo | null) => {
        if (user) {
          this.userName = user.username;
          this.userNickname = user.username;
          AppStorage.setOrCreate<string>(STORE_KEY_NICKNAME, this.userNickname);
          // 头像路径
          this.userAvatarPath = user.avatarPath ?? "";
          AppStorage.setOrCreate<string>(STORE_KEY_AVATAR, this.userAvatarPath);
          const msPerDay = 24 * 60 * 60 * 1000;
          this.useDays = Math.max(1, Math.floor((Date.now() - user.createTime) / msPerDay));
          console.log(
            `[person]: 用户信息加载成功 user=${user.username}, useDays=${this.useDays}`,
          );
        } else {
          console.warn(`[person]: 未找到用户信息 user=${currentUser}`);
        }
      })
      .catch((err: Error) => {
        console.error(`[person]: 查询用户失败 ${err.message}`);
      });

    // 从数据库加载当前用户的累计预警次数
    db.queryHealthEvents("fall", currentUser)
      .then((events: HealthEvent[]) => {
        this.totalAlertCount = events.length;
        console.log(`[person]: 摔倒事件加载成功 count=${events.length}, user=${currentUser}`);
      })
      .catch((err: Error) => {
        this.totalAlertCount = this.mqttManager.fallRecords.length;
        console.error(`[person]: 查询健康事件失败 ${err.message}`);
      });
  }

  private safePush(pageName: string): void {
    this.pathStack.pushPathByName(pageName, null);
  }

  @Builder
  GradientHeader(): void {
    GradientHeader() {
      Column() {
        if (this.userAvatarPath !== '') {
          Image(this.userAvatarPath)
            .width("22%").aspectRatio(1).borderRadius(999)
            .objectFit(ImageFit.Cover)
            .border({ width: 2.5, color: "rgba(255,255,255,0.7)" })
            .clip(true)
        } else {
          Column() {
            Image($r("app.media.ic_user")).width("50%").aspectRatio(1).objectFit(ImageFit.Contain)
          }
          .width("22%").aspectRatio(1).borderRadius(999).clip(true)
          .backgroundColor("rgba(255,255,255,0.2)")
          .border({ width: 2, color: "rgba(255,255,255,0.6)" })
          .justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
        }
        Text(this.userNickname || this.userName)
          .fontSize(22).fontWeight(FontWeight.Bold).fontColor("#ffffff").margin({ top: "4%" })
      }
      .width("100%").padding({ top: this.topSafeHeight + 8, bottom: 44 })
    }
  }

  build() {
    Column() {
      this.GradientHeader()
      Scroll() {
        Column() {
          StatDashboard({ useDays: this.useDays, totalAlertCount: this.totalAlertCount, topSafeHeight: this.topSafeHeight })
          Column() {
            Text("服务设置")
              .fontSize(12)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .margin({ left: "6%", bottom: "3%", top: "6%" })
              .alignSelf(ItemAlign.Start)
            Column() {
              MenuRow({
                imgRes: $r("app.media.ic_user_blue"),
                bgColorLight: "#eff6ff",
                bgColorDark: "#1e3a5f",
                title: "个人资料",
                subTitle: "修改头像、名字及安全联系方式",
                onClickAction: (): void => {
                  this.pathStack.pushPathByName("Profile", null);
                },
              })
              Divider()
                .margin({ left: "15%", right: "4%" })
                .color(this.themeManager.colors.separatorColor)
              MenuRow({
                imgRes: $r("app.media.ic_camera"),
                bgColorLight: "#e0f2fe",
                bgColorDark: "#0c4a6e",
                title: "人脸信息",
                subTitle: "录入人脸用于开发板识别 (阅后即焚)",
                onClickAction: (): void => {
                  this.takePhotoAndSendToBoard(getContext(this) as common.UIAbilityContext);
                },
              })
              Divider()
                .margin({ left: "15%", right: "4%" })
                .color(this.themeManager.colors.separatorColor)
              MenuRow({
                imgRes: $r("app.media.ic_map_pin_green"),
                bgColorLight: "#f0fdf4",
                bgColorDark: "#14302a",
                title: "常用地址",
                subTitle: "管理家庭地址及位置信息",
                onClickAction: (): void => this.safePush("MyAddress"),
              })
              Divider()
                .margin({ left: "15%", right: "4%" })
                .color(this.themeManager.colors.separatorColor)
              MenuRow({
                imgRes: $r("app.media.ic_phone_orange"),
                bgColorLight: "#fff7ed",
                bgColorDark: "#3d2000",
                title: "紧急联系人",
                subTitle: "危急时刻一键呼叫通知",
                onClickAction: (): void => {
                  promptAction.showToast({ message: "功能开发中" });
                },
              })
              Divider()
                .margin({ left: "15%", right: "4%" })
                .color(this.themeManager.colors.separatorColor)
              MenuRow({
                imgRes: $r("app.media.ic_list_blue"),
                bgColorLight: "#eff6ff",
                bgColorDark: "#1e3a5f",
                title: "历史记录",
                subTitle: `查看并导出近 ${this.retentionDays} 天健康事件`,
                onClickAction: (): void => this.safePush("HealthHistory"),
              })
            }
            .width("92%")
            .backgroundColor(this.themeManager.colors.cardBackgroundColor)
            .borderRadius("4%")
            .clip(true)
            .shadow({ radius: 8, color: "#0000000F", offsetY: 4 })
          }.width("100%")
          Column() {
            Text("系统偏好")
              .fontSize(12)
              .fontColor(this.themeManager.colors.secondaryTextColor)
              .margin({ left: "6%", bottom: "3%", top: "5%" })
              .alignSelf(ItemAlign.Start)
            Column() {
              Row() {
                Image(
                  this.themeManager.isDarkMode
                    ? $r("app.media.ic_shield_light")
                    : $r("app.media.ic_shield_gray"),
                )
                  .width(36)
                  .height(36)
                  .objectFit(ImageFit.Contain)
                  .padding(8)
                  .backgroundColor(this.themeManager.isDarkMode ? "#334155" : "#f1f5f9")
                  .borderRadius(10)
                  .margin({ right: "4%" })
                Text("外观模式")
                  .fontSize(15)
                  .fontWeight(FontWeight.Medium)
                  .fontColor(this.themeManager.colors.primaryTextColor)
                Blank()
                Row() {
                  Text(
                    this.themeManager.themeMode === ThemeMode.LIGHT
                      ? "浅色"
                      : this.themeManager.themeMode === ThemeMode.DARK
                        ? "深色"
                        : "跟随",
                  )
                    .fontSize(12)
                    .fontColor("#2563eb")
                    .fontWeight(FontWeight.Medium)
                }
                .padding({ left: "3%", right: "3%", top: "1.5%", bottom: "1.5%" })
                .backgroundColor(this.themeManager.isDarkMode ? "#1e3a5f" : "#eff6ff")
                .borderRadius(100)
                .onClick((): void => {
                  this.themeManager.setThemeMode(
                    ((this.themeManager.themeMode + 1) % 3) as ThemeMode,
                  );
                })
              }
              .width("100%")
              .padding({ left: "4%", right: "4%", top: "3.5%", bottom: "3.5%" })
              .constraintSize({ minHeight: 64 })
              .backgroundColor(
                this.pressedRow === "外观模式"
                  ? this.themeManager.isDarkMode
                    ? "#2a3a50"
                    : "#e8edf5"
                  : this.themeManager.colors.cardBackgroundColor,
              )
              .animation({ duration: 80, curve: Curve.EaseOut })
              .onTouch((e: TouchEvent): void => {
                if (e.type === TouchType.Down) {
                  this.pressedRow = "外观模式";
                } else if (e.type === TouchType.Up || e.type === TouchType.Cancel) {
                  setTimeout(() => {
                    this.pressedRow = "";
                  }, 150);
                }
              })
              Divider()
                .margin({ left: "15%", right: "4%" })
                .color(this.themeManager.colors.separatorColor)
              Row() {
                Image(
                  this.themeManager.isDarkMode
                    ? $r("app.media.ic_refresh_light")
                    : $r("app.media.ic_refresh_gray"),
                )
                  .width(36)
                  .height(36)
                  .objectFit(ImageFit.Contain)
                  .padding(8)
                  .backgroundColor(this.themeManager.isDarkMode ? "#334155" : "#f1f5f9")
                  .borderRadius(10)
                  .margin({ right: "4%" })
                Column() {
                  Text("清理缓存")
                    .fontSize(15)
                    .fontWeight(FontWeight.Medium)
                    .fontColor(this.themeManager.colors.primaryTextColor)
                  Text("释放存储空间，优化运行速度")
                    .fontSize(12)
                    .fontColor(this.themeManager.colors.secondaryTextColor)
                    .margin({ top: "2%" })
                }
                .alignItems(HorizontalAlign.Start)
                .layoutWeight(1)
                Image($r("app.media.ic_chevron_right"))
                  .width(16)
                  .height(16)
                  .objectFit(ImageFit.Contain)
              }
              .width("100%")
              .padding({ left: "4%", right: "4%", top: "3.5%", bottom: "3.5%" })
              .constraintSize({ minHeight: 64 })
              .backgroundColor(
                this.pressedRow === "清理缓存"
                  ? this.themeManager.isDarkMode
                    ? "#2a3a50"
                    : "#e8edf5"
                  : this.themeManager.colors.cardBackgroundColor,
              )
              .animation({ duration: 80, curve: Curve.EaseOut })
              .onTouch((e: TouchEvent): void => {
                if (e.type === TouchType.Down) {
                  this.pressedRow = "清理缓存";
                } else if (e.type === TouchType.Up || e.type === TouchType.Cancel) {
                  setTimeout(() => {
                    this.pressedRow = "";
                  }, 150);
                }
              })
              .onClick((): void => {
                this.mqttManager.clearAllCache();
                promptAction.showToast({ message: "清理完成" });
              })
              Divider()
                .margin({ left: "15%", right: "4%" })
                .color(this.themeManager.colors.separatorColor)
              // ── 数据保留天数设置行 ────────────────────────────────
              Row() {
                Image(
                  this.themeManager.isDarkMode
                    ? $r("app.media.ic_shield_light")
                    : $r("app.media.ic_shield_blue"),
                )
                  .width(36)
                  .height(36)
                  .objectFit(ImageFit.Contain)
                  .padding(8)
                  .backgroundColor(this.themeManager.isDarkMode ? "#1e3a5f" : "#eff6ff")
                  .borderRadius(10)
                  .margin({ right: "4%" })
                Column() {
                  Text("数据保留时长")
                    .fontSize(15)
                    .fontWeight(FontWeight.Medium)
                    .fontColor(this.themeManager.colors.primaryTextColor)
                  Text("视频与健康记录的保存天数")
                    .fontSize(12)
                    .fontColor(this.themeManager.colors.secondaryTextColor)
                    .margin({ top: "2%" })
                }
                .alignItems(HorizontalAlign.Start)
                .layoutWeight(1)
                // 当前天数标签
                Row() {
                  Text(`${this.retentionDays}天`)
                    .fontSize(13)
                    .fontColor("#2563eb")
                    .fontWeight(FontWeight.Medium)
                }
                .padding({ left: "3%", right: "3%", top: "1.5%", bottom: "1.5%" })
                .backgroundColor(this.themeManager.isDarkMode ? "#1e3a5f" : "#eff6ff")
                .borderRadius(100)
                .onClick((): void => {
                  // ArkTS showActionMenu 要求 ActionMenuButtonOptions[]，不支持 color 字段
                  // 改用 showDialog 实现天数选择
                  promptAction
                    .showDialog({
                      title: "数据保留时长",
                      message: "选择视频与健康记录的保存天数\n（更长时间需要开通会员）",
                      buttons: [
                        { text: "7天（免费）", color: "#2563eb" },
                        { text: "14天 👑", color: "#64748b" },
                        { text: "30天 👑", color: "#64748b" },
                        { text: "90天 👑", color: "#64748b" },
                      ],
                    })
                    .then((result) => {
                      const options = [7, 14, 30, 90];
                      const selected = options[result.index];
                      if (selected > FREE_RETENTION_DAYS) {
                        promptAction
                          .showDialog({
                            title: "👑 开通守护星会员",
                            message: `保留 ${selected} 天数据为会员专属功能。\n会员还享有：云端备份、多人协同监护等权益。`,
                            buttons: [
                              { text: "稍后再说", color: "#64748b" },
                              { text: "立即开通", color: "#2563eb" },
                            ],
                          })
                          .then((dialog) => {
                            if (dialog.index === 1) {
                              promptAction.showToast({ message: "会员功能即将上线，敬请期待！" });
                            }
                          });
                      } else {
                        DatabaseHelper.getInstance().setRetentionDays(selected);
                        this.retentionDays = selected;
                        promptAction.showToast({ message: `已设置保留 ${selected} 天` });
                      }
                    });
                })
              }
              .width("100%")
              .padding({ left: "4%", right: "4%", top: "3.5%", bottom: "3.5%" })
              .constraintSize({ minHeight: 64 })
              .backgroundColor(
                this.pressedRow === "数据保留时长"
                  ? this.themeManager.isDarkMode
                    ? "#2a3a50"
                    : "#e8edf5"
                  : this.themeManager.colors.cardBackgroundColor,
              )
              .animation({ duration: 80, curve: Curve.EaseOut })
              .onTouch((e: TouchEvent): void => {
                if (e.type === TouchType.Down) {
                  this.pressedRow = "数据保留时长";
                } else if (e.type === TouchType.Up || e.type === TouchType.Cancel) {
                  setTimeout(() => {
                    this.pressedRow = "";
                  }, 150);
                }
              })
            }
            .width("92%")
            .backgroundColor(this.themeManager.colors.cardBackgroundColor)
            .borderRadius("4%")
            .clip(true)
            .shadow({ radius: 8, color: "#0000000F", offsetY: 4 })
          }.width("100%")
          Button("退出登录", { type: ButtonType.Capsule })
            .width("80%")
            .height("6%")
            .constraintSize({ minHeight: 48 })
            .margin({ top: "10%", bottom: "6%" })
            .backgroundColor("#fee2e2")
            .fontColor("#ef4444")
            .fontWeight(FontWeight.Medium)
            .scale({ x: this.logoutScale, y: this.logoutScale })
            .animation({ duration: 120, curve: Curve.EaseInOut })
            .onClick((): void => {
              this.logoutScale = 0.95;
              setTimeout(() => {
                this.logoutScale = 1.0;
              }, 150);
              promptAction
                .showDialog({
                  title: "退出确认",
                  message: "您确定要退出当前账号吗？（这不会删除你的账号信息）",
                  buttons: [
                    { text: "取消", color: "#64748b" },
                    { text: "退出", color: "#ef4444" },
                  ],
                })
                .then((data) => {
                  if (data.index === 1 && this.pathStack) {
                    // 清除持久化登录态
                    try {
                      const ctx = getContext(this) as common.UIAbilityContext;
                      const opts: preferences.Options = { name: PREF_NAME_AUTH };
                      const pref = preferences.getPreferencesSync(ctx, opts);
                      pref.deleteSync("lastUsername");
                      pref.deleteSync(PREF_KEY_LAST_NICKNAME);
                      pref.flush();
                    } catch (e) {
                      console.warn("[person]: 清除登录态失败 " + JSON.stringify(e));
                    }
                    AppStorage.setOrCreate<string>(STORAGE_KEY_LOGGED_IN_USER, "");
                    AppStorage.setOrCreate<string>(STORE_KEY_NICKNAME, "");
                    UserManager.getInstance().clearCurrentUsername();
                    this.pathStack.clear();
                    this.pathStack.pushPathByName("Login", null);
                  }
                });
            })
          Text("守护星版本 2.0.0")
            .fontSize(12)
            .fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ bottom: "10%" })
        }
        .width("100%")
        .alignItems(HorizontalAlign.Center)
      }
      .layoutWeight(1)
      .scrollBar(BarState.Off)
      .edgeEffect(EdgeEffect.Spring)
    }
    .width("100%")
    .height("100%")
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM])
  }
}
