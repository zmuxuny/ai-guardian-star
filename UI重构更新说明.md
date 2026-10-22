# UI 全面重构更新说明

## 📅 修改日期
2026 年 3 月 18 日

## 🎯 修改目标
1. 全面美化三个页面 UI，统一蓝色渐变风格
2. 将所有页面内图标从 SvgIcon 组件替换为 Image 组件加载 SVG 资源文件
3. 修复图标大小、位置、背景色块等渲染异常问题
4. 修复记录页统计卡空白、个人页数据卡过高等布局问题
5. 为通话按钮添加点击缩放动画和通话中变红效果

---

## 📝 修改内容

### 1. **底部导航图标方案（Layout.ets）**

**文件路径**: `entry/src/main/ets/pages/Layout.ets`

**问题根因**: 原方案用 `Image + fillColor` 试图染色 SVG 的 stroke，但 `fillColor` 只能修改 SVG 的 `fill` 属性，对 `stroke` 无效，导致图标颜色无法跟随激活状态切换。

**解决方案**: 为每个 Tab 做激活/非激活两套 SVG 文件，颜色直接烘焙进 SVG 的 `stroke` 属性，Image 原样显示。

新增文件（位于 `entry/src/main/resources/base/media/`）：

| 文件名 | 颜色 | 用途 |
|--------|------|------|
| `tab_home_active.svg` | `#2563eb` 蓝色 | 主页激活 |
| `tab_home_inactive.svg` | `#94a3b8` 灰色 | 主页未激活 |
| `tab_record_active.svg` | `#2563eb` 蓝色 | 记录激活 |
| `tab_record_inactive.svg` | `#94a3b8` 灰色 | 记录未激活 |
| `tab_person_active.svg` | `#2563eb` 蓝色 | 个人激活 |
| `tab_person_inactive.svg` | `#94a3b8` 灰色 | 个人未激活 |

```typescript
// 根据 currentIndex 切换资源，Image 直接显示
private getTabIconResource(index: number): Resource {
  const active = this.currentIndex === index;
  switch (index) {
    case 0: return active ? $r("app.media.tab_home_active") : $r("app.media.tab_home_inactive");
    case 1: return active ? $r("app.media.tab_record_active") : $r("app.media.tab_record_inactive");
    case 2: return active ? $r("app.media.tab_person_active") : $r("app.media.tab_person_inactive");
  }
}
```

---

### 2. **页面内图标资源文件（media 目录）**

彻底放弃 SvgIcon 组件，改用 Image 加载独立 SVG 文件。颜色在文件中烘焙，命名规则：`ic_用途_颜色.svg`。

新增 16 个图标文件：

| 文件名 | 颜色 | 使用位置 |
|--------|------|---------|
| `ic_camera_off.svg` | `#64748b` 灰 | 主页视频区摄像头未连接 |
| `ic_alert_white.svg` | `#ffffff` 白 | 主页视频区离线角标 |
| `ic_link_off_red.svg` | `#ef4444` 红 | 主页设备状态卡离线图标 |
| `ic_shield_blue.svg` | `#2563eb` 蓝 | 主页监测卡 / 记录页空状态 |
| `ic_shield_green.svg` | `#10b981` 绿 | 主页设备状态卡在线图标 |
| `ic_shield_gray.svg` | `#64748b` 灰 | 个人页系统偏好图标 |
| `ic_phone_white.svg` | `#ffffff` 白 | 主页通话按钮 |
| `ic_phone_orange.svg` | `#f59e0b` 橙 | 个人页紧急联系人菜单 |
| `ic_refresh_white.svg` | `#ffffff` 白 | 记录页 Header 刷新按钮 |
| `ic_refresh_gray.svg` | `#64748b` 灰 | 个人页清理缓存菜单 |
| `ic_chevron_right.svg` | `#cbd5e1` 浅灰 | 各页面菜单行右箭头 |
| `ic_user_white.svg` | `#ffffff` 白 | 个人页头像区人物图标 |
| `ic_user_edit_blue.svg` | `#2563eb` 蓝 | 个人页个人资料菜单 |
| `ic_map_pin_green.svg` | `#10b981` 绿 | 个人页常用地址菜单 |
| `ic_alert_red.svg` | `#ef4444` 红 | 记录页摔倒记录列表项 |
| `ic_list_blue.svg` | `#2563eb` 蓝 | 记录页久坐记录列表项 |

---

### 3. **图标背景色块 padding 修复（三个页面）**

**问题根因**: `padding('22%')` 在 ArkTS 中是相对于组件自身宽度的百分比，图标容器越大 padding 越大，导致背景色块异常撑大，图标本身反而缩成一个点。

**修复方案**: 全部改为固定 `padding(8)` 或 `padding(9)`。

| 位置 | 修改前 | 修改后 |
|------|--------|--------|
| 状态卡图标 | `width('12%') + padding('20%')` | `width(28) + padding(8)` |
| 刷新按钮 | `width('9%') + padding('22%')` | `width(36) + padding(9)` |
| 菜单图标 | `width('11%') + padding('22%')` | `width(36) + padding(8)` |
| 空状态图标 | `width('22%') + padding('20%')` | `width(48) + padding(12)` |
| 记录列表图标 | `width('11%') + padding('22%')` | `width(36) + padding(8)` |

---

### 4. **个人页头像图标修复（person.ets）**

**问题**: Stack 容器 `width('22%')`，图标 `width('11%')` 是相对于屏幕宽度的 11%，而非 Stack 容器的 50%，导致图标极小。

**修复**: 改为 `width('50%')`，相对于 Stack 容器自身宽度，图标正好填充圆形头像的一半。

```typescript
// 修改前
Image($r('app.media.ic_user_white')).width('11%').aspectRatio(1)

// 修改后
Image($r('app.media.ic_user_white')).width('50%').aspectRatio(1)
```

---

### 5. **记录页统计卡空白修复（record.ets）**

**问题**: `StatDashboard` 被额外的 `Column` 包裹，负 margin `top: '-4%'` 被父 Column 吞掉，无法叠出到 Header 上，导致 Header 和统计卡之间出现大片空白。

**修复**: 去掉外层 Column 包裹，`StatDashboard()` 直接跟在 `GradientHeader()` 后调用，`margin({ top: -24 })` 固定值正常生效。

---

### 6. **个人页数据卡过高修复（person.ets）**

**问题**: 数据卡 `padding: { top: '5%', bottom: '5%' }` 在高 dpi 屏幕上实际像素很大，把卡片撑得过高，数字 28fp 换行显示。

**修复**: 改为固定 `padding({ top: 20, bottom: 20 })`，不随屏幕密度缩放。

---

### 7. **通话按钮三大升级（mainpage.ets）**

**文件路径**: `entry/src/main/ets/pages/mainpage.ets`

#### ① 去除白色背景
原来通话按钮套在一个有 `backgroundColor('#f0f4ff')` 的 Column 里，两侧出现白色色块。现改为直接居于页面底部，无父容器背景色。

#### ② 点击缩放动画
新增 `@State btnScale: number = 1.0`，点击时缩小到 0.93，150ms 后回弹到 1.0，配合 `.animation({ duration: 150 })` 实现弹性效果。

```typescript
@State btnScale: number = 1.0;

// 按钮上
.scale({ x: this.btnScale, y: this.btnScale })
.animation({ duration: 150, curve: Curve.EaseInOut })

// onClick 中
this.btnScale = 0.93;
setTimeout(() => { this.btnScale = 1.0; }, 150);
```

#### ③ 通话中变红
`isTalking` 为 `true` 时，渐变色和阴影颜色同步切换为红色系。

```typescript
.linearGradient({
  direction: GradientDirection.Left,
  colors: this.isTalking
    ? [['#dc2626', 0.0], ['#ef4444', 1.0]]   // 通话中：红色
    : [['#1e40af', 0.0], ['#3b82f6', 1.0]]   // 待机：蓝色
})
.shadow({ radius: 16, color: this.isTalking ? '#ef444440' : '#3b82f640', offsetY: 8 })
```

---

## 🔄 修改文件清单

| 文件 | 修改类型 | 主要变动 |
|------|---------|---------|
| `Layout.ets` | 图标方案重构 | SvgIcon → Image 双套资源方案 |
| `mainpage.ets` | 全面重写 | 图标换 Image、通话按钮动画/变色/去背景 |
| `record.ets` | 重写+修复 | 图标换 Image、统计卡负 margin 修复 |
| `person.ets` | 重写+修复 | 图标换 Image、头像图标比例修复、数据卡 padding 修复 |
| `Icons.ets` | 简化 | 回退为纯 Shape 渲染，移除 sizeType 自适应逻辑 |
| `media/tab_*.svg` | 新增 6 个 | 底部导航激活/非激活双套图标 |
| `media/ic_*.svg` | 新增 16 个 | 页面内所有功能图标 |

---

## ⚠️ 注意事项

1. **图标颜色与状态绑定**: 因为颜色烘焙在 SVG 文件里，若后续需要深色模式支持，需要为每个图标再做一套深色版本的 SVG 文件，或改回 SvgIcon 动态染色方案
2. **padding 使用固定值**: 图标背景的 padding 统一使用固定像素值（8/9/12），不使用百分比，避免在不同尺寸容器内异常撑大
3. **通话按钮动画**: `setTimeout` 实现回弹，如遇到页面切换导致定时器未清除的问题，可在 `aboutToDisappear` 中清理
