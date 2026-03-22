import display from "@ohos.display";

// 图标尺寸类型定义 - 用于不同场景的图标大小
export type IconSizeType = "nav" | "list" | "card" | "empty" | "header" | "custom";

// 屏幕适配系数限制（最小 85%，最大 115%）
const MIN_SCALE = 0.85;
const MAX_SCALE = 1.15;
const BASE_SCREEN_WIDTH = 360; // 基准屏幕宽度
@Component
export struct SvgIcon {
  @Prop name: string;
  @Prop color: ResourceColor = "#000000";
  @Prop iconSize: number = 24;
  @Prop strokeWidth: number = 2.2; // 从 1.8 调大到 2.2，图标线条更饱满
  @Prop sizeType: IconSizeType = "custom";

  // 获取屏幕宽度
  private getScreenWidth(): number {
    try {
      const d = display.getDefaultDisplaySync();
      if (d && d.width) {
        return d.width;
      }
    } catch (e) {
      console.warn("[SvgIcon]: 获取屏幕宽度失败", e);
    }
    return BASE_SCREEN_WIDTH;
  }

  // 根据屏幕宽度计算自适应尺寸
  private getAdaptiveSize(): number {
    if (this.sizeType === "custom") {
      return this.iconSize;
    }
    // 使用 switch 语句避免索引访问
    let baseSize: number;
    switch (this.sizeType) {
      case "nav":
        baseSize = 40; // 底部导航图标 - 从 32 调大到 40，更醒目
        break;
      case "list":
        baseSize = 34; // 列表项图标 - 从 26 调大到 34，与文字更协调
        break;
      case "card":
        baseSize = 40; // 卡片状态图标 - 从 32 调大到 40，保持醒目
        break;
      case "empty":
        baseSize = 72; // 空状态大图标 - 从 56 调大到 72，视觉中心
        break;
      case "header":
        baseSize = 48; // 页面标题旁图标 - 从 36 调大到 48
        break;
      default:
        baseSize = 24;
        break;
    }
    const screenWidth = this.getScreenWidth();
    const scaleFactor = screenWidth / BASE_SCREEN_WIDTH;
    const clampedFactor = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scaleFactor));
    return Math.round(baseSize * clampedFactor);
  }

  // 获取 SVG 路径数据 - 使用 switch 语句避免索引访问
  private getPath(): string {
    switch (this.name) {
      case "home":
        return "M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10";
      case "list":
        return "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01";
      case "user":
        return "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 7a4 4 0 1 0 0-8 4 4 0 0 0 0 8z";
      case "shield-check":
        return "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z M9 12l2 2 4-4";
      case "camera-off":
        return "M1 1l22 22M21 21H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3m3-3h6l2 3h4a2 2 0 0 1 2 2v9.34m-16 0A5 5 0 0 0 12 17a5 5 0 0 0 3.41-1.34";
      case "alert-triangle":
        return "M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4M12 17h.01";
      case "link-off":
        return "M9 15a5 5 0 0 0 7.07.06l3-3a5 5 0 0 0-7.07-7.07L10.37 6.6 M15 9a5 5 0 0 0-7.07-.06L4.93 11.94a5 5 0 0 0 7.07 7.07L13.63 17.4 M1 1l22 22";
      case "phone":
        return "M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z";
      case "map-pin":
        return "M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z M12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6z";
      case "user-pen":
        return "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 7a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z";
      case "refresh-cw":
        return "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15";
      case "chevron-right":
        return "M9 18l6-6-6-6";
      default:
        return "";
    }
  }

  build() {
    Stack() {
      Path()
        .commands(this.getPath())
        .stroke(this.color as string)
        .strokeWidth(this.strokeWidth)
        .strokeLineCap(LineCapStyle.Round)
        .strokeLineJoin(LineJoinStyle.Round)
        .fill(Color.Transparent)
        .antiAlias(true)
    }
    .width(this.getAdaptiveSize())
    .height(this.getAdaptiveSize());
  }
}
