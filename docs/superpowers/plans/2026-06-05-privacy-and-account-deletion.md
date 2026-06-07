# 隐私协议弹窗 + 账号注销 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 首次启动显示隐私协议弹窗（同意/退出），person 页加注销账号（密码验证 + 云端优先删除）。

**Architecture:** 5 文件顺序改动；Index.ets 加 CustomDialog 在 checkAutoLogin 前拦截；person.ets 加第二个 CustomDialog；CloudService 加 deleteUser；后端加 /api/deleteUser。密码比对走本地明文比较（现有系统密码存明文，字段名 passwordHash 但值未哈希）。

**Tech Stack:** HarmonyOS ArkTS, @kit.ArkData (Preferences), @kit.AbilityKit (Want for URL), @ohos.net.http, Flask/SQLite

---

## 文件改动一览

| 文件 | 类型 | 改动 |
|---|---|---|
| `entry/src/main/ets/config.ets` | Modify | 新增 2 个常量 |
| `wenxin_proxy.py` | Modify | 新增 `/api/deleteUser` 端点 |
| `entry/src/main/ets/common/CloudService.ets` | Modify | 新增 `deleteUser()` 方法 |
| `entry/src/main/ets/pages/Index.ets` | Modify | 新增 `PrivacyDialog` + 启动检查 |
| `entry/src/main/ets/pages/person.ets` | Modify | 新增 `DeleteAccountDialog` + 注销按钮 |

---

## Task 1: config.ets — 新增隐私相关常量

**Files:**
- Modify: `entry/src/main/ets/config.ets`

- [ ] **Step 1: 在 Preferences 区末尾追加两个常量**

在 `PREF_KEY_LAST_NICKNAME` 之后添加：

```ts
export const PREF_KEY_PRIVACY_ACCEPTED = 'privacyAccepted';
export const PRIVACY_POLICY_URL =
  'https://agreement-drcn.hispace.dbankcloud.cn/index.html?lang=zh&agreementId=1944894729334323712';
```

- [ ] **Step 2: Commit**

```bash
git add entry/src/main/ets/config.ets
git commit -m "feat: config 新增隐私政策 URL 和 Preferences key"
```

---

## Task 2: wenxin_proxy.py — 新增 /api/deleteUser 端点

**Files:**
- Modify: `wenxin_proxy.py`

- [ ] **Step 1: 在 api_login 函数之后（约第 130 行之后）插入新端点**

找到 `@app.route('/api/login'` 对应的函数结尾，紧跟插入：

```python
@app.route('/api/deleteUser', methods=['POST'])
def api_delete_user():
    d = request.get_json(force=True) or {}
    username = (d.get('username') or '').strip()
    if not username:
        return jsonify({"success": False, "message": "参数缺失"}), 400
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT username FROM t_user WHERE username=? OR phone=? OR email=?",
            (username, username, username)
        ).fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "message": "账号不存在"})
        conn.execute("DELETE FROM t_user WHERE username=?", (row['username'],))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "账号已注销"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
```

- [ ] **Step 2: 手动验证（服务器上执行）**

```bash
# 重启后端
pkill -f wenxin_proxy && nohup python3 wenxin_proxy.py > /var/log/wenxin_proxy.log 2>&1 &

# 测试接口（用一个测试账号）
curl -X POST http://localhost:8899/api/deleteUser \
  -H 'Content-Type: application/json' \
  -d '{"username":"test_user"}'
# 期望: {"success": false, "message": "账号不存在"} 或 {"success": true, ...}
```

- [ ] **Step 3: Commit**

```bash
git add wenxin_proxy.py
git commit -m "feat: 后端新增 /api/deleteUser 端点"
```

---

## Task 3: CloudService.ets — 新增 deleteUser() 方法

**Files:**
- Modify: `entry/src/main/ets/common/CloudService.ets`

- [ ] **Step 1: 在 CloudService 类末尾的 changePassword 方法之后添加**

```ts
interface DeleteUserRequest {
  username: string;
}

// 在 CloudService 类内：
/** 注销账号 — 从云端永久删除用户记录 */
async deleteUser(username: string): Promise<CloudResult> {
  const body: DeleteUserRequest = { username: username };
  return postJson('/api/deleteUser', body);
}
```

注意：`interface DeleteUserRequest` 放在类**外**（文件顶层），`deleteUser` 方法放在类**内** `changePassword` 之后。

- [ ] **Step 2: Commit**

```bash
git add entry/src/main/ets/common/CloudService.ets
git commit -m "feat: CloudService 新增 deleteUser 方法"
```

---

## Task 4: Index.ets — 隐私协议弹窗

**Files:**
- Modify: `entry/src/main/ets/pages/Index.ets`

- [ ] **Step 1: 在文件顶部 import 区补充缺失的导入**

在现有 import 末尾添加：

```ts
import { Want } from '@kit.AbilityKit';
import { PREF_KEY_PRIVACY_ACCEPTED, PRIVACY_POLICY_URL } from '../config';
```

- [ ] **Step 2: 在 `@Entry @Component struct Index` 之前插入 PrivacyDialog**

```ts
@CustomDialog
struct PrivacyDialog {
  controller: CustomDialogController;
  onAgree: () => void = () => {};
  onDisagree: () => void = () => {};

  build() {
    Column({ space: 0 }) {
      Text('隐私政策与用户协议')
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor('#1e293b')
        .margin({ top: 24, bottom: 16 })
        .textAlign(TextAlign.Center)
        .width('100%')

      Scroll() {
        Column({ space: 8 }) {
          Text('智护星（Guardian Star）非常重视您的隐私保护。使用本应用前，请阅读以下说明：')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
          Text('• 账号信息（手机号 / 邮箱）：用于身份识别和跨设备登录')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
          Text('• 健康监测数据（摔倒 / 久坐事件）：存储于本机及您的云端账号，仅用于监护服务')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
          Text('• 摄像头（人脸录入，可选）：照片仅上传至您自己的开发板，不经过第三方服务器')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
          Text('数据不会向任何第三方共享或出售。')
            .fontSize(13)
            .fontColor('#475569')
            .lineHeight(20)
            .margin({ top: 4 })
          Text('查看完整隐私政策 →')
            .fontSize(13)
            .fontColor('#3b82f6')
            .decoration({ type: TextDecorationType.Underline, color: '#3b82f6' })
            .margin({ top: 4 })
            .onClick(() => {
              const ctx = getContext(this) as common.UIAbilityContext;
              const want: Want = {
                action: 'ohos.want.action.viewData',
                entities: ['entity.system.browsable'],
                uri: PRIVACY_POLICY_URL,
              };
              ctx.startAbility(want).catch((e: Error) => {
                console.warn('[PrivacyDialog]: 打开隐私政策链接失败', e.message);
              });
            })
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)
      }
      .height(200)
      .width('100%')
      .padding({ left: 20, right: 20 })

      Row({ space: 12 }) {
        Button('不同意', { type: ButtonType.Normal })
          .layoutWeight(1)
          .height(44)
          .backgroundColor('#f1f5f9')
          .fontColor('#64748b')
          .borderRadius(10)
          .onClick(() => { this.onDisagree(); })
        Button('同意并继续', { type: ButtonType.Normal })
          .layoutWeight(1)
          .height(44)
          .backgroundColor('#3b82f6')
          .fontColor('#ffffff')
          .borderRadius(10)
          .onClick(() => { this.onAgree(); })
      }
      .width('100%')
      .padding({ left: 20, right: 20, top: 16, bottom: 24 })
    }
    .width('100%')
    .backgroundColor('#ffffff')
    .borderRadius(16)
  }
}
```

- [ ] **Step 3: 在 `struct Index` 内添加 controller 字段和 showPrivacyDialog 方法**

在 `pathStack: NavPathStack = new NavPathStack();` 之后添加：

```ts
  private privacyDialogController: CustomDialogController = new CustomDialogController({
    builder: PrivacyDialog({
      onAgree: () => {
        this.privacyDialogController.close();
        this.savePrivacyAccepted();
        this.checkAutoLogin();
      },
      onDisagree: () => {
        this.privacyDialogController.close();
        const ctx = getContext(this) as common.UIAbilityContext;
        ctx.terminateSelf();
      },
    }),
    autoCancel: false,
    alignment: DialogAlignment.Center,
    customStyle: false,
    cornerRadius: 16,
    width: '88%',
  });

  private savePrivacyAccepted(): void {
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME_AUTH };
      const pref = preferences.getPreferencesSync(ctx, options);
      pref.putSync(PREF_KEY_PRIVACY_ACCEPTED, true);
      pref.flushSync();
    } catch (e) {
      console.warn('[Index]: 保存隐私协议状态失败', JSON.stringify(e));
    }
  }
```

- [ ] **Step 4: 修改 build() 中 onAppear 的调用逻辑**

将：
```ts
    }).onAppear(() => {
      this.checkAutoLogin();
    })
```

改为：
```ts
    }).onAppear(() => {
      this.checkPrivacyThenLogin();
    })
```

- [ ] **Step 5: 在 checkAutoLogin 之前插入 checkPrivacyThenLogin 方法**

```ts
  private checkPrivacyThenLogin(): void {
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const options: preferences.Options = { name: PREF_NAME_AUTH };
      const pref = preferences.getPreferencesSync(ctx, options);
      const accepted = pref.getSync(PREF_KEY_PRIVACY_ACCEPTED, false) as boolean;
      if (!accepted) {
        this.privacyDialogController.open();
        return;
      }
    } catch (e) {
      console.warn('[Index]: 读取隐私协议状态失败', JSON.stringify(e));
    }
    this.checkAutoLogin();
  }
```

- [ ] **Step 6: Commit**

```bash
git add entry/src/main/ets/pages/Index.ets
git commit -m "feat: 首次启动隐私协议弹窗 — 同意继续/不同意退出"
```

---

## Task 5: person.ets — 注销账号按钮 + DeleteAccountDialog

**Files:**
- Modify: `entry/src/main/ets/pages/person.ets`

- [ ] **Step 1: 在 import 区补充缺失的导入**

在现有 import 末尾添加（若还没有）：

```ts
import { CloudService } from '../common/CloudService';
import { PREF_KEY_PRIVACY_ACCEPTED, PREF_KEY_LAST_USERNAME } from '../config';
```

注：`CloudService` 可能已导入，检查后按需添加。

- [ ] **Step 2: 在 `struct person` 开头的 @State 区添加两个字段**

在 `@State logoutScale: number = 1.0;` 之后添加：

```ts
  @State deleteInputPassword: string = '';
  @State isDeleting: boolean = false;
```

- [ ] **Step 3: 在 `struct person` 内（pathStack 声明之后）添加 deleteAccountDialogController**

```ts
  private deleteAccountDialogController: CustomDialogController = new CustomDialogController({
    builder: DeleteAccountDialog({
      inputPassword: this.deleteInputPassword,
      isDeleting: this.isDeleting,
      onPasswordChange: (v: string) => { this.deleteInputPassword = v; },
      onConfirm: () => { this.executeDeleteAccount(); },
      onCancel: () => {
        this.deleteInputPassword = '';
        this.deleteAccountDialogController.close();
      },
    }),
    autoCancel: false,
    alignment: DialogAlignment.Center,
    customStyle: false,
    cornerRadius: 16,
    width: '88%',
  });
```

- [ ] **Step 4: 在 takePhotoAndSendToBoard 方法之前插入 DeleteAccountDialog 组件和 executeDeleteAccount 方法**

**DeleteAccountDialog（放在 `struct person` 之前，与 PrivacyDialog 风格一致）：**

```ts
@CustomDialog
struct DeleteAccountDialog {
  controller: CustomDialogController;
  @Link inputPassword: string;
  @Link isDeleting: boolean;
  onPasswordChange: (v: string) => void = () => {};
  onConfirm: () => void = () => {};
  onCancel: () => void = () => {};

  build() {
    Column({ space: 0 }) {
      Text('验证身份')
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor('#1e293b')
        .margin({ top: 24, bottom: 8 })
        .textAlign(TextAlign.Center)
        .width('100%')
      Text('注销账号将永久删除所有数据，请输入当前密码确认')
        .fontSize(13)
        .fontColor('#64748b')
        .textAlign(TextAlign.Center)
        .padding({ left: 20, right: 20 })
        .margin({ bottom: 16 })
      TextInput({ placeholder: '请输入当前密码', text: this.inputPassword })
        .type(InputType.Password)
        .width('100%')
        .padding({ left: 20, right: 20 })
        .margin({ bottom: 20 })
        .onChange((v: string) => { this.onPasswordChange(v); })
      Row({ space: 12 }) {
        Button('取消', { type: ButtonType.Normal })
          .layoutWeight(1)
          .height(44)
          .backgroundColor('#f1f5f9')
          .fontColor('#64748b')
          .borderRadius(10)
          .enabled(!this.isDeleting)
          .onClick(() => { this.onCancel(); })
        Button(this.isDeleting ? '注销中...' : '确认注销', { type: ButtonType.Normal })
          .layoutWeight(1)
          .height(44)
          .backgroundColor('#ef4444')
          .fontColor('#ffffff')
          .borderRadius(10)
          .enabled(!this.isDeleting)
          .onClick(() => { this.onConfirm(); })
      }
      .width('100%')
      .padding({ left: 20, right: 20, bottom: 24 })
    }
    .width('100%')
    .backgroundColor('#ffffff')
    .borderRadius(16)
  }
}
```

**executeDeleteAccount 方法（放在 `struct person` 内，aboutToAppear 之前）：**

```ts
  private async executeDeleteAccount(): Promise<void> {
    const currentUser = UserManager.getInstance().getCurrentUsername();
    const db = DatabaseHelper.getInstance();

    // 1. 本地查用户，获取密码
    let user: UserInfo | null = null;
    try {
      user = await db.queryUserByIdentifier(currentUser);
    } catch (e) {
      promptAction.showToast({ message: '查询用户失败，请重试' });
      return;
    }
    if (!user) {
      promptAction.showToast({ message: '用户信息不存在' });
      return;
    }

    // 2. 密码验证（明文比对，与现有登录逻辑一致）
    if (this.deleteInputPassword.trim() !== user.passwordHash) {
      promptAction.showToast({ message: '密码错误，请重新输入' });
      return;
    }

    // 3. 云端删除（优先，失败则中止）
    this.isDeleting = true;
    try {
      const cloud = CloudService.getInstance();
      const result = await cloud.deleteUser(currentUser);
      if (!result.success) {
        this.isDeleting = false;
        promptAction.showToast({ message: '服务器拒绝注销，请稍后重试或联系客服' });
        return;
      }
    } catch (e) {
      this.isDeleting = false;
      promptAction.showToast({ message: '网络不可用，请检查网络后重试' });
      return;
    }

    // 4. 云端成功 → 本地清除
    try {
      await db.deleteUserByUsername(user.username);
    } catch (e) {
      console.error('[person]: 本地删除失败', JSON.stringify(e));
    }

    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const opts: preferences.Options = { name: PREF_NAME_AUTH };
      const pref = preferences.getPreferencesSync(ctx, opts);
      pref.deleteSync(PREF_KEY_LAST_USERNAME);
      pref.deleteSync(PREF_KEY_LAST_NICKNAME);
      pref.deleteSync(PREF_KEY_PRIVACY_ACCEPTED);
      pref.flushSync();
    } catch (e) {
      console.warn('[person]: 清除 Preferences 失败', JSON.stringify(e));
    }

    AppStorage.setOrCreate<string>(STORAGE_KEY_LOGGED_IN_USER, '');
    AppStorage.setOrCreate<string>(STORE_KEY_NICKNAME, '');
    AppStorage.setOrCreate<string>(STORE_KEY_AVATAR, '');
    UserManager.getInstance().clearCurrentUsername();

    this.isDeleting = false;
    this.deleteInputPassword = '';
    this.deleteAccountDialogController.close();

    if (this.pathStack) {
      this.pathStack.clear();
      this.pathStack.pushPathByName('Login', null);
    }
  }
```

- [ ] **Step 5: 在 build() 中"退出登录"按钮之后、"智护星 v1.0.0"文字之前插入注销按钮**

在 `}).onAppear(() => {` 附近找到退出登录按钮结束的 `})` （约第 630 行），之后插入：

```ts
          Button('注销账号', { type: ButtonType.Normal })
            .width('80%')
            .height(40)
            .constraintSize({ minHeight: 36 })
            .margin({ top: '2%', bottom: '2%' })
            .backgroundColor('transparent')
            .fontColor('#dc2626')
            .fontSize(14)
            .onClick(() => {
              promptAction.showDialog({
                title: '注销账号',
                message: '此操作将永久删除您在本设备和云端的所有数据，且无法恢复。确定要继续吗？',
                buttons: [
                  { text: '取消', color: '#64748b' },
                  { text: '继续注销', color: '#ef4444' },
                ],
              }).then((res) => {
                if (res.index === 1) {
                  this.deleteInputPassword = '';
                  this.deleteAccountDialogController.open();
                }
              });
            })
```

- [ ] **Step 6: 顺带修复 person.ets 退出登录中的硬编码 key（已知风险）**

在退出登录逻辑里找到：
```ts
pref.deleteSync("lastUsername");
```
改为：
```ts
pref.deleteSync(PREF_KEY_LAST_USERNAME);
```

- [ ] **Step 7: Commit**

```bash
git add entry/src/main/ets/pages/person.ets entry/src/main/ets/common/CloudService.ets
git commit -m "feat: 账号注销 — 密码验证+云端优先删除+本地清除"
```

---

## Task 6: 推送 + 人工验收

- [ ] **Step 1: 推送所有提交**

```bash
git push origin feature/jyx-home
```

- [ ] **Step 2: 隐私弹窗验证**

1. 清除 App 数据（设置 → 应用 → 智护星 → 清除数据）或卸载重装
2. 启动 App → 应检查到 `privacyAccepted` 未设置 → 弹出隐私协议弹窗
3. 点"查看完整隐私政策" → 应跳转浏览器打开 AGC 链接
4. 点"不同意" → App 应退出
5. 重新打开 App → 弹窗再次出现
6. 点"同意并继续" → 正常进入登录或主页
7. 再次重启 App → 弹窗不再出现

- [ ] **Step 3: 账号注销验证**

1. 登录任意测试账号
2. 进入"我的"页面 → 应看到"注销账号"按钮（红色，位于"退出登录"下方）
3. 点击 → 应弹出警告弹窗
4. 点"继续注销" → 应弹出密码验证弹窗
5. 输入**错误**密码 → 应显示"密码错误"toast，弹窗保持
6. 输入**正确**密码 → 应显示"注销中..." → 成功后跳转登录页
7. 验证云端：`curl http://服务器:8899/api/login -d '{"username":"...","passwordHash":"..."}'` → 应返回"账号不存在"
8. 重启 App → 隐私弹窗应重新出现（privacyAccepted 已被清除）
