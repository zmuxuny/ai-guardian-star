# 隐私协议弹窗 + 账号注销 设计文档

Date: 2026-06-05  
Scope: Index.ets, person.ets, wenxin_proxy.py

---

## 1. 隐私协议弹窗

### 触发条件
`Index.ets` 启动时，`checkAutoLogin()` **之前**检查 Preferences：
- key: `privacyAccepted`（store: `guardian_auth`，与现有 `PREF_NAME_AUTH` 共用）
- 未设置或为 false → 弹窗
- 已接受 → 直接走原有 `checkAutoLogin()` 流程，行为不变

### UI — CustomDialog（非 showDialog，需支持点击链接）
```
┌─────────────────────────────┐
│  隐私政策与用户协议            │
├─────────────────────────────┤
│ 智护星（Guardian Star）非常重视│
│ 您的隐私保护。本应用会收集：    │
│ • 账号信息（手机号/邮箱）      │
│ • 健康监测数据（摔倒/久坐事件） │
│ • 设备摄像头（人脸录入，可选）  │
│                              │
│ 数据仅用于提供监护服务，不会    │
│ 向第三方共享。                 │
│                              │
│ [查看完整隐私政策 →]  ← 蓝色可点击│
├─────────────────────────────┤
│  [不同意]        [同意并继续] │
└─────────────────────────────┘
```

### 行为
- **同意并继续**：`pref.putSync('privacyAccepted', true)` + `pref.flushSync()` → `checkAutoLogin()`
- **不同意**：`context.terminateSelf()` 退出 App
- **查看完整隐私政策**：`context.openLink(PRIVACY_POLICY_URL)`（AGC 托管链接）

### 常量（加入 config.ets）
```ts
export const PRIVACY_POLICY_URL =
  'https://agreement-drcn.hispace.dbankcloud.cn/index.html?lang=zh&agreementId=1944894729334323712';
export const PREF_KEY_PRIVACY_ACCEPTED = 'privacyAccepted';
```

---

## 2. 账号注销

### 入口
`person.ets`"退出登录"按钮下方，独立红色文字按钮"注销账号"。

### 三步流程

**Step 1 — 警告弹窗**（`showDialog`）
```
标题: 注销账号
内容: 此操作将永久删除您在本设备和云端的所有数据，且无法恢复。确定要继续吗？
按钮: [取消]  [继续注销]
```

**Step 2 — 密码验证弹窗**（`CustomDialog` + TextInput）
```
标题: 请输入当前密码以确认
输入框: 密码（obscureText）
按钮: [取消]  [确认注销]
```
- 本地哈希比对：`sha256(inputPassword) === user.passwordHash`
- 不匹配 → `showToast('密码错误')` + 弹窗保持打开
- 匹配 → Step 3

**Step 3 — 执行删除**（async，云端优先，失败则中止）
1. `POST /api/deleteUser`（body: `{username: loginId}`）→ 云端删除
   - 网络不可达 → toast "网络不可用，请检查网络后重试"，**中止，不动本地**
   - 服务端返回非 success → toast "服务器拒绝注销，请稍后重试或联系客服"，**中止，不动本地**
2. 云端成功后才执行本地清除：
   - `db.deleteUserByUsername(username)`
   - 清 Preferences（`lastUsername`, `lastNickname`, `privacyAccepted`）
   - 清 AppStorage（`loggedInUsername`, `loggedInNickname`, `loggedInAvatarPath`）
   - `UserManager.getInstance().clearCurrentUsername()`
3. `pathStack.clear()` → `pushPathByName('Login', null)`

**原则：云端与本地保持一致，任何一步失败均中止并提示，不留半删除状态。**

### 后端新增端点 — wenxin_proxy.py
```
POST /api/deleteUser
Body: { "username": "<loginId>" }
逻辑: 柔性 lookup (username OR phone OR email) → DELETE FROM t_user WHERE username=?
返回: {"success": true/false, "message": "..."}
```

---

## 3. 文件改动范围

| 文件 | 改动 |
|---|---|
| `config.ets` | 新增 `PRIVACY_POLICY_URL`, `PREF_KEY_PRIVACY_ACCEPTED` |
| `Index.ets` | 新增 `PrivacyDialog` CustomDialog + 启动检查逻辑 |
| `person.ets` | 新增"注销账号"按钮 + `DeleteAccountDialog` CustomDialog |
| `wenxin_proxy.py` | 新增 `POST /api/deleteUser` 端点 |

---

## 4. 不在范围内
- 隐私政策内容本身（已在 AGC 托管）
- 数据导出功能
- 找回账号功能
