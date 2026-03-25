/**
 * person.ets — 个人中心页面
 * 显示用户信息、统计数据和系统设置
 */
import { ThemeManager, ThemeMode } from '../common/ThemeManager';
import { MqttManager } from './MqttManager';
import { promptAction } from '@kit.ArkUI';
import { DatabaseHelper, HealthEvent, FREE_RETENTION_DAYS, STORAGE_KEY_RETENTION, UserInfo } from '../database/DatabaseHelper';
import { preferences } from '@kit.ArkData';
import { common } from '@kit.AbilityKit';
import { STORAGE_KEY_LOGGED_IN_USER } from './Login';

@Builder
export function personBuilder(): void {
  NavDestination() { person() }.hideTitleBar(true)
}

@Component
export struct person {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State userName: string = '超级管理员';
  @State userPhone: string = '';  // 用户手机号
  @State userId: string = 'ID: 69175890';
  @State useDays: number = 128;
  @State totalAlertCount: number = 0;
  @StorageLink(STORAGE_KEY_RETENTION) retentionDays: number = FREE_RETENTION_DAYS;
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;
  // 各菜单行按压状态
  @State pressedRow: string = '';
  // 退出登录按钮缩放
  @State logoutScale: number = 1.0;
  // 导航路径栈
  pathStack: NavPathStack = new NavPathStack();

  aboutToAppear(): void {
    this.loadUserInfo();
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
    const mask = '*'.repeat(maskLength);
    return prefix + mask + suffix;
  }

  /** 加载用户信息 */
  private loadUserInfo(): void {
    const currentUser = AppStorage.get<string>('loggedInUsername') ?? '';
    const db = DatabaseHelper.getInstance();

    console.log(`[person]: 开始加载用户信息，currentUser=${currentUser}`);

    // 从数据库加载当前用户信息（昵称、注册天数）
    db.queryUserByUsername(currentUser)
      .then((user: UserInfo | null) => {
        if (user) {
          this.userName = user.username;
          // 加密手机号
          if (user.phone && user.phone.trim() !== '') {
            this.userPhone = this.encryptPhone(user.phone);
            console.log(`[person]: 手机号已加密：${this.userPhone}`);
          } else {
            // 如果没有手机号，使用用户名作为标识
            this.userPhone = this.userName;
            console.log(`[person]: 无手机号，使用用户名：${this.userPhone}`);
          }
          const msPerDay = 24 * 60 * 60 * 1000;
          this.useDays = Math.max(1, Math.floor((Date.now() - user.createTime) / msPerDay));
          console.log(`[person]: 用户信息加载成功 user=${user.username}, phone=${this.userPhone}, useDays=${this.useDays}`);
        } else {
          console.warn(`[person]: 未找到用户信息 user=${currentUser}`);
        }
      })
      .catch((err: Error) => {
        console.error(`[person]: 查询用户失败 ${err.message}`);
      });

    // 从数据库加载当前用户的累计预警次数
    db.queryHealthEvents('fall', currentUser)
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
    Column() {
      Column() {
        Image($r('app.media.ic_user'))
          .width('50%').aspectRatio(1).objectFit(ImageFit.Contain)
      }
      .width('22%').aspectRatio(1)
      .borderRadius(999)
      .clip(true)
      .backgroundColor('rgba(255,255,255,0.2)')
      .border({ width: 2, color: 'rgba(255,255,255,0.6)' })
      .justifyContent(FlexAlign.Center)
      .alignItems(HorizontalAlign.Center)
      .onClick((): void => this.safePush("AvatarEdit"))

      Text(this.userName)
        .fontSize(22)
        .fontWeight(FontWeight.Bold)
        .fontColor('#ffffff')
        .margin({ top: '4%' })
      Text(this.userPhone ? `📱 ${this.userPhone}` : this.userId)
        .fontSize(13)
        .fontColor('#CCFFFFFF')
        .margin({ top: '2%' })
    }
    .width('100%').padding({ top: this.topSafeHeight + 24, bottom: 20 })
    .linearGradient({ direction: GradientDirection.Bottom,
      colors: [['#1e40af', 0.0], ['#3b82f6', 0.5], ['#60a5fa', 1.0]] })
    .borderRadius({ bottomLeft: '6%', bottomRight: '6%' })
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
  }

  @Builder
  StatDashboard(): void {
    Row() {
      Column() {
        Text(`${this.useDays}`).fontSize(28).fontWeight(FontWeight.Bold).fontColor('#1e40af')
        Text('天·已监护').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: 6 })
      }.layoutWeight(1)
      // 竖向分隔线
      Column()
        .width(1)
        .height(36)
        .backgroundColor(this.themeManager.colors.separatorColor)
      Column() {
        Text(`${this.totalAlertCount}`).fontSize(28).fontWeight(FontWeight.Bold).fontColor('#1e40af')
        Text('次·已预警').fontSize(13).fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: 6 })
      }.layoutWeight(1)
    }
    .width('88%').padding({ top: 20, bottom: 20 })
    .margin({ top: -36 })
    .backgroundColor(this.themeManager.colors.cardBackgroundColor).borderRadius('4%')
    .shadow({ radius: 12, color: '#1A3b82f6', offsetY: 6 })
  }


  @Builder
  MenuRow(imgRes: Resource, bgColorLight: string, bgColorDark: string, title: string, subTitle: string, onClickAction: () => void): void {
    Row() {
      Image(imgRes)
        .width(36).height(36).objectFit(ImageFit.Contain)
        .padding(8)
        .backgroundColor(this.themeManager.isDarkMode ? bgColorDark : bgColorLight)
        .borderRadius(10).margin({ right: '4%' })
      Column() {
        Text(title).fontSize(15).fontWeight(FontWeight.Medium)
          .fontColor(this.themeManager.colors.primaryTextColor)
        Text(subTitle).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: '2%' })
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
      Image($r('app.media.ic_chevron_right'))
        .width(16).height(16).objectFit(ImageFit.Contain)
    }
    .width('100%').padding({ left: '4%', right: '4%', top: '3.5%', bottom: '3.5%' })
    .constraintSize({ minHeight: 64 })
    // 按压时背景加深 — 参考系统设置页，浅色模式变#e8edf5（明显灰蓝），深色模式变#2a3a50
    .backgroundColor(this.pressedRow === title
      ? (this.themeManager.isDarkMode ? '#2a3a50' : '#e8edf5')
      : this.themeManager.colors.cardBackgroundColor)
    .animation({ duration: 80, curve: Curve.EaseOut })
    .gesture(
      TapGesture()
        .onAction((): void => { if (onClickAction) onClickAction(); })
    )
    .onTouch((event: TouchEvent): void => {
      if (event.type === TouchType.Down) { this.pressedRow = title; }
      else if (event.type === TouchType.Up || event.type === TouchType.Cancel) {
        setTimeout(() => { this.pressedRow = ''; }, 150);
      }
    })
  }

  build() {
    Scroll() {
      Column() {
        this.GradientHeader()
        this.StatDashboard()

        Column() {
          Text("服务设置").fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ left: '6%', bottom: '3%', top: '6%' }).alignSelf(ItemAlign.Start)
          Column() {
            this.MenuRow($r('app.media.ic_user_blue'), '#eff6ff', '#1e3a5f',
              "个人资料", "修改头像、昵称及手机号", (): void => this.safePush("NicknameEdit"))
            Divider().margin({ left: '15%', right: '4%' }).color(this.themeManager.colors.separatorColor)
            this.MenuRow($r('app.media.ic_map_pin_green'), '#f0fdf4', '#14302a',
              "常用地址", "管理家庭地址及位置信息", (): void => this.safePush("MyAddress"))
            Divider().margin({ left: '15%', right: '4%' }).color(this.themeManager.colors.separatorColor)
            this.MenuRow($r('app.media.ic_phone_orange'), '#fff7ed', '#3d2000',
              "紧急联系人", "危急时刻一键呼叫通知",
              (): void => { promptAction.showToast({ message: "功能开发中" }) })
            Divider().margin({ left: '15%', right: '4%' }).color(this.themeManager.colors.separatorColor)
            this.MenuRow($r('app.media.ic_list_blue'), '#eff6ff', '#1e3a5f',
              "历史记录", `查看并导出近 ${this.retentionDays} 天健康事件`,
              (): void => this.safePush("HealthHistory"))
          }
          .width('92%').backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .borderRadius('4%').clip(true)
          .shadow({ radius: 8, color: '#0000000F', offsetY: 4 })
        }.width('100%')

        Column() {
          Text("系统偏好").fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ left: '6%', bottom: '3%', top: '5%' }).alignSelf(ItemAlign.Start)
          Column() {
            Row() {
              Image(this.themeManager.isDarkMode ? $r('app.media.ic_shield_light') : $r('app.media.ic_shield_gray'))
                .width(36).height(36).objectFit(ImageFit.Contain)
                .padding(8)
                .backgroundColor(this.themeManager.isDarkMode ? '#334155' : '#f1f5f9')
                .borderRadius(10).margin({ right: '4%' })
              Text("外观模式").fontSize(15).fontWeight(FontWeight.Medium)
                .fontColor(this.themeManager.colors.primaryTextColor)
              Blank()
              Row() {
                Text(this.themeManager.themeMode === ThemeMode.LIGHT ? "浅色" :
                  this.themeManager.themeMode === ThemeMode.DARK ? "深色" : "跟随")
                  .fontSize(12).fontColor('#2563eb').fontWeight(FontWeight.Medium)
              }
              .padding({ left: '3%', right: '3%', top: '1.5%', bottom: '1.5%' })
              .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
              .borderRadius(100)
              .onClick((): void => {
                this.themeManager.setThemeMode(((this.themeManager.themeMode + 1) % 3) as ThemeMode);
              })
            }
            .width('100%').padding({ left: '4%', right: '4%', top: '3.5%', bottom: '3.5%' })
            .constraintSize({ minHeight: 64 })
            .backgroundColor(this.pressedRow === '外观模式'
              ? (this.themeManager.isDarkMode ? '#2a3a50' : '#e8edf5')
              : this.themeManager.colors.cardBackgroundColor)
            .animation({ duration: 80, curve: Curve.EaseOut })
            .onTouch((e: TouchEvent): void => {
              if (e.type === TouchType.Down) { this.pressedRow = '外观模式'; }
              else if (e.type === TouchType.Up || e.type === TouchType.Cancel) {
                setTimeout(() => { this.pressedRow = ''; }, 150);
              }
            })
            Divider().margin({ left: '15%', right: '4%' }).color(this.themeManager.colors.separatorColor)
            Row() {
              Image(this.themeManager.isDarkMode ? $r('app.media.ic_refresh_light') : $r('app.media.ic_refresh_gray'))
                .width(36).height(36).objectFit(ImageFit.Contain)
                .padding(8)
                .backgroundColor(this.themeManager.isDarkMode ? '#334155' : '#f1f5f9')
                .borderRadius(10).margin({ right: '4%' })
              Column() {
                Text("清理缓存").fontSize(15).fontWeight(FontWeight.Medium)
                  .fontColor(this.themeManager.colors.primaryTextColor)
                Text("释放存储空间，优化运行速度").fontSize(12)
                  .fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: '2%' })
              }.alignItems(HorizontalAlign.Start).layoutWeight(1)
              Image($r('app.media.ic_chevron_right')).width(16).height(16).objectFit(ImageFit.Contain)
            }
            .width('100%').padding({ left: '4%', right: '4%', top: '3.5%', bottom: '3.5%' })
            .constraintSize({ minHeight: 64 })
            .backgroundColor(this.pressedRow === '清理缓存'
              ? (this.themeManager.isDarkMode ? '#2a3a50' : '#e8edf5')
              : this.themeManager.colors.cardBackgroundColor)
            .animation({ duration: 80, curve: Curve.EaseOut })
            .onTouch((e: TouchEvent): void => {
              if (e.type === TouchType.Down) { this.pressedRow = '清理缓存'; }
              else if (e.type === TouchType.Up || e.type === TouchType.Cancel) {
                setTimeout(() => { this.pressedRow = ''; }, 150);
              }
            })
            .onClick((): void => {
              this.mqttManager.clearAllCache();
              promptAction.showToast({ message: "清理完成" });
            })
            Divider().margin({ left: '15%', right: '4%' }).color(this.themeManager.colors.separatorColor)
            // ── 数据保留天数设置行 ────────────────────────────────
            Row() {
              Image(this.themeManager.isDarkMode ? $r('app.media.ic_shield_light') : $r('app.media.ic_shield_blue'))
                .width(36).height(36).objectFit(ImageFit.Contain)
                .padding(8)
                .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
                .borderRadius(10).margin({ right: '4%' })
              Column() {
                Text("数据保留时长").fontSize(15).fontWeight(FontWeight.Medium)
                  .fontColor(this.themeManager.colors.primaryTextColor)
                Text("视频与健康记录的保存天数").fontSize(12)
                  .fontColor(this.themeManager.colors.secondaryTextColor).margin({ top: '2%' })
              }.alignItems(HorizontalAlign.Start).layoutWeight(1)
              // 当前天数标签
              Row() {
                Text(`${this.retentionDays}天`)
                  .fontSize(13).fontColor('#2563eb').fontWeight(FontWeight.Medium)
              }
              .padding({ left: '3%', right: '3%', top: '1.5%', bottom: '1.5%' })
              .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#eff6ff')
              .borderRadius(100)
              .onClick((): void => {
                // ArkTS showActionMenu 要求 ActionMenuButtonOptions[]，不支持 color 字段
                // 改用 showDialog 实现天数选择
                promptAction.showDialog({
                  title: '数据保留时长',
                  message: '选择视频与健康记录的保存天数\n（更长时间需要开通会员）',
                  buttons: [
                    { text: '7天（免费）', color: '#2563eb' },
                    { text: '14天 👑', color: '#64748b' },
                    { text: '30天 👑', color: '#64748b' },
                    { text: '90天 👑', color: '#64748b' }
                  ]
                }).then(result => {
                  const options = [7, 14, 30, 90];
                  const selected = options[result.index];
                  if (selected > FREE_RETENTION_DAYS) {
                    promptAction.showDialog({
                      title: '👑 开通守护星会员',
                      message: `保留 ${selected} 天数据为会员专属功能。\n会员还享有：云端备份、多人协同监护等权益。`,
                      buttons: [
                        { text: '稍后再说', color: '#64748b' },
                        { text: '立即开通', color: '#2563eb' }
                      ]
                    }).then(dialog => {
                      if (dialog.index === 1) {
                        promptAction.showToast({ message: '会员功能即将上线，敬请期待！' });
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
            .width('100%').padding({ left: '4%', right: '4%', top: '3.5%', bottom: '3.5%' })
            .constraintSize({ minHeight: 64 })
            .backgroundColor(this.pressedRow === '数据保留时长'
              ? (this.themeManager.isDarkMode ? '#2a3a50' : '#e8edf5')
              : this.themeManager.colors.cardBackgroundColor)
            .animation({ duration: 80, curve: Curve.EaseOut })
            .onTouch((e: TouchEvent): void => {
              if (e.type === TouchType.Down) { this.pressedRow = '数据保留时长'; }
              else if (e.type === TouchType.Up || e.type === TouchType.Cancel) {
                setTimeout(() => { this.pressedRow = ''; }, 150);
              }
            })
          }
          .width('92%').backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .borderRadius('4%').clip(true)
          .shadow({ radius: 8, color: '#0000000F', offsetY: 4 })
        }.width('100%')

        Button("退出登录", { type: ButtonType.Capsule })
          .width('80%').height('6%').constraintSize({ minHeight: 48 })
          .margin({ top: '10%', bottom: '6%' })
          .backgroundColor('#fee2e2').fontColor('#ef4444').fontWeight(FontWeight.Medium)
          .scale({ x: this.logoutScale, y: this.logoutScale })
          .animation({ duration: 120, curve: Curve.EaseInOut })
          .onClick((): void => {
            this.logoutScale = 0.95;
            setTimeout(() => { this.logoutScale = 1.0; }, 150);
            promptAction.showDialog({
              title: '退出确认', message: '您确定要退出当前账号吗？',
              buttons: [{ text: '取消', color: '#64748b' }, { text: '退出', color: '#ef4444' }]
            }).then(data => {
              if (data.index === 1 && this.pathStack) {
                // 清除持久化登录态
                try {
                  const ctx = getContext(this) as common.UIAbilityContext;
                  const opts: preferences.Options = { name: 'guardian_auth' };
                  const pref = preferences.getPreferencesSync(ctx, opts);
                  pref.deleteSync('lastUsername');
                  pref.flush();
                } catch (e) {
                  console.warn('[person]: 清除登录态失败 ' + JSON.stringify(e));
                }
                AppStorage.setOrCreate<string>(STORAGE_KEY_LOGGED_IN_USER, '');
                this.pathStack.clear();
                this.pathStack.pushPathByName("Login", null);
              }
            })
          })
        Text("守护星版本 2.0.0").fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor).margin({ bottom: '10%' })
      }
      .width('100%').alignItems(HorizontalAlign.Center)
    }
    .width('100%').height('100%').backgroundColor(this.themeManager.colors.backgroundColor)
    .scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}
