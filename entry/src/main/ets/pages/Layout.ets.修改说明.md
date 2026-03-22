# Layout.ets 修改记录 - 改用 Image 组件

## 📅 修改日期
2026 年 3 月 17 日

## 🎯 修改目标
将底部导航栏从 `SvgIcon` 组件改用 `Image` 组件加载 SVG 图片资源。

---

## 📝 修改内容

### 修改前（SvgIcon 组件）
```typescript
import { SvgIcon } from '../common/Icons';

@Builder
tabBuilder(index: number): void {
  Column() {
    SvgIcon({
      name: this.tabData[index].icon,
      color: this.currentIndex === index ? '#2563eb' : '#94a3b8',
      sizeType: 'nav'
    })
    // ...
  }
}
```

### 修改后（Image 组件）
```typescript
@Builder
tabBuilder(index: number): void {
  Column() {
    Image(this.getTabIconResource(index))
      .width(40)
      .height(40)
      .fillColor(this.currentIndex === index ? '#2563eb' : '#94a3b8')
    // ...
  }
}

// 获取 Tab 图标资源
private getTabIconResource(index: number): Resource {
  switch (index) {
    case 0: return $r('app.media.home');    // 主页
    case 1: return $r('app.media.record');   // 记录
    case 2: return $r('app.media.person');   // 个人
    default: return $r('app.media.home');
  }
}
```

---

## 📊 对比

| 方面 | SvgIcon | Image |
|------|---------|-------|
| 代码量 | 较多（需维护路径） | 简洁（引用资源） |
| 图标尺寸 | 40px (基准) | 40px (固定) |
| 颜色切换 | ✅ 支持动态 | ✅ 支持 fillColor |
| 视觉效果 | 线条渲染 | SVG 图片，更饱满 |
| 维护性 | 需维护路径数据 | 直接替换图片文件 |

---

## 📁 备份文件
- `Layout.ets.bak` - SvgIcon 版本备份

---

## ✅ 使用资源
- `home.svg` - 主页图标
- `record.svg` - 记录图标
- `person.svg` - 个人图标
