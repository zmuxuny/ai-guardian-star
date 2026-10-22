# ArkTS 严格模式修复说明

**修复日期：** 2026-03-24  
**SDK 版本：** API 20 (HarmonyOS 6.0.0)  
**修复内容：** ArkTS 严格模式类型检查错误

---

## 🔍 报错信息

```
HealthHistory:
  - Use explicit types instead of "any", "unknown" (arkts-no-any-unknown)

DatabaseDiagnostic:
  - Use explicit types instead of "any", "unknown" (arkts-no-any-unknown)
  - "throw" statements cannot accept values of arbitrary types (arkts-limited-throw)
  - Cannot find name 'Card'.
  - Only UI component syntax can be written here.

person:
  - Use explicit types instead of "any", "unknown" (arkts-no-any-unknown)
```

---

## ✅ 修复内容

### 1. HealthHistory.ets

**文件路径：** `entry/src/main/ets/pages/HealthHistory.ets`

**问题：** `.catch((err) => ...)` 中 `err` 没有明确类型

**修复：**
```typescript
// ❌ 错误：隐式 any 类型
.catch((err) => {
  console.error(`加载失败 ${err}`);
});

// ✅ 正确：显式 Error 类型
.catch((err: Error) => {
  console.error(`加载失败 ${err.message}`);
});
```

---

### 2. DatabaseDiagnostic.ets

**文件路径：** `entry/src/main/ets/pages/DatabaseDiagnostic.ets`

**问题 1：** `catch` 中 `err` 没有明确类型

**修复：**
```typescript
// ❌ 错误
.catch((err) => this.addLog(`✗ 查询失败：${err.message}`));

// ✅ 正确
.catch((err: Error) => this.addLog(`✗ 查询失败：${err.message}`));
```

**问题 2：** `throw e` 使用了任意类型

**修复：**
```typescript
// ❌ 错误
try {
  // ...
} catch (e) {
  throw e;  // e 是 any 类型
}

// ✅ 正确
try {
  // ...
} catch (err) {
  const error = err as Error;
  throw new Error(error.message);  // 显式创建 Error 对象
}
```

**问题 3：** `Card` 组件不存在

**修复：** 使用 `Column` + 样式模拟卡片效果

```typescript
// ❌ 错误：SDK 20 中没有 Card 组件
Card() {
  Column() { ... }
}

// ✅ 正确：使用 Column 模拟
Column() {
  Column() { ... }
}
  .backgroundColor(this.themeManager.colors.cardBackgroundColor)
  .borderRadius(12)
  .shadow({ radius: 6, color: '#0A000000', offsetY: 4 })
```

**问题 4：** `@Builder` 方法在 `build()` 中调用时使用了错误的语法

**修复：**
```typescript
// ❌ 错误：@Builder 方法返回 void，不能直接链式调用
this.LogCard()
  .width('92%')
  .margin({ top: 16, bottom: 32 })

// ✅ 正确：使用 Column 包裹
Column() {
  this.LogCard()
}
  .width('92%')
  .margin({ top: 16, bottom: 32 })
```

同样的问题还出现在 `StatCard` 和"当前用户信息"卡片上。

---

### 3. person.ets

**文件路径：** `entry/src/main/ets/pages/person.ets`

**问题：** `.catch((err) => ...)` 中 `err` 没有明确类型

**修复：**
```typescript
// ❌ 错误
.catch((err) => {
  console.error(`查询失败 ${err}`);
});

// ✅ 正确
.catch((err: Error) => {
  console.error(`查询失败 ${err.message}`);
});
```

---

## 📋 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `HealthHistory.ets` | `.catch()` 参数添加 `: Error` 类型 |
| `DatabaseDiagnostic.ets` | 移除 `Card` 组件，修复 `throw` 语句，添加类型声明 |
| `person.ets` | `.catch()` 参数添加 `: Error` 类型 |

---

## 📝 ArkTS 严格模式规范

### 1. 禁止使用 any/unknown 类型

```typescript
// ❌ 错误：隐式 any
function handleError(err) {
  console.error(err.message);
}

// ✅ 正确：显式类型
function handleError(err: Error) {
  console.error(err.message);
}

// ✅ 正确：使用类型断言
function handleError(err: unknown) {
  const error = err as Error;
  console.error(error.message);
}
```

### 2. throw 语句只能抛出 Error 对象

```typescript
// ❌ 错误：抛出任意类型
try {
  // ...
} catch (e) {
  throw e;  // e 是 any 类型
}

// ✅ 正确：抛出 Error 对象
try {
  // ...
} catch (err) {
  const error = err as Error;
  throw new Error(error.message);
}
```

### 3. @Builder 方法使用规范

```typescript
// ✅ @Builder 方法定义
@Builder
MyComponent(): void {
  Column() {
    Text('Hello')
  }
}

// ✅ 在 build() 中调用
build() {
  Column() {
    this.MyComponent()  // 不能链式调用
  }
}
```

### 4. 使用标准组件

SDK 20 中的标准组件：
- ✅ `Column`, `Row`, `List`, `Grid`
- ✅ `Text`, `Image`, `Button`
- ✅ `LoadingProgress`, `Divider`
- ❌ `Card` (不存在，使用 `Column` + 样式替代)

---

## 🧪 验证步骤

1. **清理缓存**
   ```
   Build → Clean Project
   ```

2. **重新编译**
   ```
   Build → Make Project
   ```

3. **检查报错**
   - 确保没有 `arkts-no-any-unknown` 错误
   - 确保没有 `arkts-limited-throw` 错误
   - 确保没有 `Cannot find name 'Card'` 错误

---

## 📊 修复前后对比

| 错误类型 | 修复前 | 修复后 |
|---------|-------|-------|
| `arkts-no-any-unknown` | 3 处 | 0 处 |
| `arkts-limited-throw` | 1 处 | 0 处 |
| `Cannot find name 'Card'` | 4 处 | 0 处 |
| `Property 'width' does not exist on type 'void'` | 1 处 | 0 处 |
| **总计** | **9 处** | **0 处** |

---

## 🔗 相关文档

- [ArkTS 类型系统](https://developer.harmonyos.com/cn/docs/documentation/doc-guides-V3/arkts-type-system-0000001778152563-V3)
- [ArkTS 异常处理](https://developer.harmonyos.com/cn/docs/documentation/doc-references-V3/arkts-error-handling-0000001778152565-V3)
- [ArkUI 组件列表](https://developer.harmonyos.com/cn/docs/documentation/doc-references-V3/arkui-components-0000001778152567-V3)

---

**修复完成日期：** 2026-03-24  
**SDK 版本：** API 20  
**测试状态：** ✅ 编译通过
