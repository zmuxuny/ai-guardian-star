# HarmonyOS SDK 20 数据库修复说明

**修复日期：** 2026-03-24  
**SDK 版本：** API 20 (HarmonyOS 6.0.0)  
**修复内容：** 数据库加载逻辑、代码规范修正

---

## 🔧 修复内容

### 1. DatabaseDiagnostic.ets（新建）

**文件路径：** `entry/src/main/ets/pages/DatabaseDiagnostic.ets`

**修复内容：**
- ✅ 导入 `relationalStore` 模块
- ✅ 使用 `db.getRdbStore()` 公开方法访问数据库
- ✅ 修复 `ResultSet` 关闭逻辑（使用 `if (resultSet !== undefined)` 检查）
- ✅ 移除 `async/await` 改为 `.then/.catch` 链式调用
- ✅ 所有回调使用箭头函数

**SDK 20 规范要点：**
```typescript
// ❌ 错误：访问私有方法
const store = db['getStore']()

// ✅ 正确：使用公开方法
const store = db.getRdbStore()

// ❌ 错误：可选链关闭
resultSet?.close()

// ✅ 正确：显式检查关闭
if (resultSet !== undefined) {
  resultSet.close()
}
```

---

### 2. DatabaseHelper.ets

**文件路径：** `entry/src/main/ets/database/DatabaseHelper.ets`

**新增方法：**
```typescript
/** 【公开方法】获取 RdbStore 实例（用于诊断工具等高级操作） */
public getRdbStore(): relationalStore.RdbStore {
  if (!this.store) {
    throw new Error('DatabaseHelper 未初始化，请先调用 init(context)');
  }
  return this.store;
}
```

**修复内容：**
- ✅ `insertHealthEvent()` 确保 `username` 不为空
- ✅ `queryHealthEvents()` 优化查询逻辑
- ✅ 新增 `queryAllHealthEventsForDebug()` 诊断方法

---

### 3. person.ets

**文件路径：** `entry/src/main/ets/pages/person.ets`

**修复内容：**
- ✅ `pathStack` 类型从 `NavPathStack | undefined` 改为 `NavPathStack`
- ✅ `pathStack` 直接初始化为 `new NavPathStack()`
- ✅ `safePush()` 方法移除 `if (this.pathStack)` 检查
- ✅ `aboutToAppear()` 提取为 `loadUserInfo()` 方法
- ✅ 所有回调使用箭头函数

**SDK 20 规范要点：**
```typescript
// ❌ 错误：pathStack 可能为 undefined
pathStack: NavPathStack | undefined = undefined;

private safePush(pageName: string): void {
  if (this.pathStack) this.pathStack.pushPathByName(pageName, null);
}

// ✅ 正确：pathStack 始终有值
pathStack: NavPathStack = new NavPathStack();

private safePush(pageName: string): void {
  this.pathStack.pushPathByName(pageName, null);
}
```

---

### 4. HealthHistory.ets

**文件路径：** `entry/src/main/ets/pages/HealthHistory.ets`

**修复内容：**
- ✅ 导入 `promptAction` 模块
- ✅ `@Builder` 函数添加 `(): void` 返回类型
- ✅ `LoadingProgress` 使用 `Column` 包裹
- ✅ 所有回调使用箭头函数
- ✅ 添加详细注释

**SDK 20 规范要点：**
```typescript
// ❌ 错误：@Builder 函数没有返回类型
@Builder
export function HealthHistoryBuilder() { ... }

// ✅ 正确：添加返回类型
@Builder
export function HealthHistoryBuilder(): void { ... }

// ❌ 错误：LoadingProgress 单独使用
LoadingProgress().width(48).height(48)

// ✅ 正确：使用 Column 包裹
Column() {
  LoadingProgress()
    .width(48)
    .height(48)
}
.width('100%')
.margin({ top: '25%' })
```

---

### 5. MqttManager.ets

**文件路径：** `entry/src/main/ets/pages/MqttManager.ets`

**修复内容：**
- ✅ 新增 `getCurrentUsername()` 统一方法
- ✅ 默认值从 `''` 改为 `'default_user'`
- ✅ 添加详细日志输出

```typescript
/** 获取当前登录用户名（统一入口，保证一致性） */
private getCurrentUsername(): string {
  return AppStorage.get<string>('loggedInUsername') ?? 'default_user';
}
```

---

### 6. Login.ets

**文件路径：** `entry/src/main/ets/pages/Login.ets`

**修复内容：**
- ✅ Logo 区域添加 `LongPressGesture` 进入诊断工具
- ✅ `pathStack` 已正确定义为 `NavPathStack = new NavPathStack()`

**使用方法：**
```typescript
// 长按 Logo 进入数据库诊断工具
.gesture(
  LongPressGesture()
    .onAction(() => {
      promptAction.showToast({ message: '正在打开诊断工具...', duration: 1000 });
      this.pathStack.pushPathByName('DatabaseDiagnostic', null);
    })
)
```

---

## 📋 修改文件清单

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `DatabaseDiagnostic.ets` | 新建 | 数据库诊断工具 |
| `DatabaseHelper.ets` | 修改 | 新增 `getRdbStore()` 公开方法 |
| `person.ets` | 修改 | pathStack 初始化修复 |
| `HealthHistory.ets` | 修改 | LoadingProgress 修复 |
| `MqttManager.ets` | 修改 | 用户名获取统一化 |
| `Login.ets` | 修改 | 添加诊断工具入口 |

---

## 🧪 测试步骤

### 1. 编译项目

```bash
# DevEco Studio
File → Project Structure → SDK Management
确认 API 20 已安装

Build → Make Project
```

### 2. 登录账号

1. 打开 App
2. 输入账号密码
3. 点击登录

### 3. 连接板子测试

1. 确保 MQTT 连接正常
2. 模拟摔倒/久坐事件
3. 观察控制台日志

### 4. 查看数据库

**方法一：诊断工具**
1. 返回登录页
2. **长按 Logo**（智护星图标）
3. 进入数据库诊断工具
4. 查看实时数据

**方法二：IDE 查看**
1. DevEco Studio → Device File Explorer
2. 连接设备
3. 导航到：
   ```
   /data/storage/el2/base/dependencies_cache/GuardianStar.db
   ```

---

## 📝 SDK 20 代码规范要点

### 1. 类型声明

```typescript
// ✅ 必须声明返回类型
@Builder
export function HealthHistoryBuilder(): void { ... }

// ✅ 必须声明变量类型
@State fallRecords: FallRecord[] = [];
```

### 2. 异步处理

```typescript
// ✅ 推荐使用 .then/.catch 链式调用
db.queryHealthEvents('fall', currentUser)
  .then((events: HealthEvent[]) => {
    this.fallRecords = events.map(...);
  })
  .catch((err) => {
    console.error(`加载失败 ${err}`);
  });

// ⚠️ async/await 需要正确处理异常
private async loadData(): Promise<void> {
  try {
    const events = await db.queryHealthEvents('fall', currentUser);
    this.fallRecords = events.map(...);
  } catch (err) {
    console.error(`加载失败 ${err}`);
  }
}
```

### 3. 资源释放

```typescript
// ✅ ResultSet 必须显式关闭
let resultSet: relationalStore.ResultSet | undefined = undefined;
try {
  resultSet = await store.query(predicates, columns);
  // 处理数据
} catch (e) {
  throw e;
} finally {
  if (resultSet !== undefined) {
    resultSet.close();
  }
}
```

### 4. 导航栈

```typescript
// ✅ pathStack 必须初始化
pathStack: NavPathStack = new NavPathStack();

// ✅ 在 onReady 中赋值
.onReady((ctx: NavDestinationContext) => {
  this.pathStack = ctx.pathStack;
})
```

---

## 🔍 常见问题排查

### Q1: 编译报错 "Module '@kit.ArkData' has no exported member 'relationalStore'"

**解决方法：**
检查 `oh-package.json5` 依赖：
```json5
{
  "dependencies": {
    "@ohos/mqtt": "2.0.18"
  }
}
```

确保 `build-profile.json5` 中 `targetSdkVersion` 为 `6.0.0(20)`

---

### Q2: 运行时报错 "DatabaseHelper 未初始化"

**解决方法：**
检查 `EntryAbility.ets` 中是否调用初始化：
```typescript
// EntryAbility.ets onWindowStageCreate()
DatabaseHelper.getInstance().init(this.context)
  .then(() => {
    hilog.info(DOMAIN, TAG, 'DatabaseHelper initialized');
  });
```

---

### Q3: 诊断工具打不开

**解决方法：**
1. 检查 `Login.ets` 中 `pathStack` 是否正确
2. 检查 `DatabaseDiagnostic.ets` 是否导入所有依赖
3. 查看控制台路由错误日志

---

### Q4: 数据库文件看不到

**解决方法：**
1. 确保设备已连接
2. DevEco Studio → Device File Explorer
3. 刷新文件列表
4. 如果还是没有，在诊断工具中执行一次查询操作

---

## 📊 日志关键字

| 日志前缀 | 含义 |
|---------|------|
| `[mqtt]:✅` | MQTT 记录添加成功（内存） |
| `[mqtt]:📦` | ArkDB 写入成功 |
| `[mqtt]:❌` | ArkDB 写入失败 |
| `[person]:` | 个人页面数据加载 |
| `[HealthHistory]:` | 历史记录页数据加载 |
| `DatabaseHelper` | 数据库核心操作 |

---

**修复完成日期：** 2026-03-24  
**SDK 版本：** API 20  
**测试状态：** 待测试
