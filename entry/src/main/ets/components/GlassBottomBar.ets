import { careIconTint } from '../common/CarePalette';
import { curves } from '@kit.ArkUI';
import { reduceMotion, softTap } from '../common/UiFeedback';

export const GLASS_TAB_CLEARANCE: number = 88;

export interface GlassTabItem {
  label: string;
  icon: Resource;
  activeIcon: Resource;
}

/** ArkUI adaptation of the floating rail and moving selection in Jianyuanxi/GlassTabBar. */
@Component
export struct GlassBottomBar {
  @Prop items: GlassTabItem[] = [];
  @Prop selected: number = 0;
  @Prop viewportWidth: number = 360;
  @Prop compact: boolean = false;
  @Prop darkSurface: boolean = false;
  @Prop accent: string = '#0A5C43';
  @Prop tint: string = '#DDF4E9';

  @State touchSlot: number = -1;
  @State lift: number = 0;
  onSelect: (slot: number) => void = () => {};
  private dragging: boolean = false;
  private lastDragCell: number = -1;
  private dragOrigin: number = 0;

  private barWidth(): number {
    const full = Math.min(480, this.viewportWidth - 40);
    return this.compact ? Math.min(full, Math.max(this.items.length * 48, this.viewportWidth - 128)) : full;
  }

  private barHeight(): number {
    return this.compact ? 50 : 64;
  }

  private cellWidth(): number {
    return this.barWidth() / Math.max(1, this.items.length);
  }

  private pillWidth(): number {
    return this.cellWidth() * (1 + 0.26 * this.lift) - 8 * (1 - this.lift);
  }

  private pillHeight(): number {
    return this.barHeight() - 8 + 18 * this.lift;
  }

  private pillX(): number {
    const slot = this.touchSlot >= 0 ? this.touchSlot : this.selected;
    return (slot + 0.5) * this.cellWidth() - this.pillWidth() / 2;
  }

  private trackPress(event: TouchEvent, slot: number): void {
    if (this.dragging || reduceMotion()) return;
    if (event.type === TouchType.Down && event.touches.length === 1) {
      this.getUIContext().animateTo({ duration: 170, curve: Curve.FastOutSlowIn }, () => {
        this.touchSlot = slot;
        this.lift = 1;
      });
    } else if (event.type === TouchType.Up || event.type === TouchType.Cancel) {
      this.settle();
    }
  }

  private dragPosition(offset: number): number {
    return Math.max(0, Math.min(this.items.length - 1, this.dragOrigin + offset / this.cellWidth()));
  }

  private startDrag(event: GestureEvent): void {
    const finger = event.fingerList[0];
    if (finger === undefined) return;
    this.dragging = true;
    this.dragOrigin = (finger.localX - event.offsetX) / this.cellWidth() - 0.5;
    this.touchSlot = this.dragPosition(event.offsetX);
    this.lastDragCell = Math.round(this.touchSlot);
    this.lift = reduceMotion() ? 0 : 1;
  }

  private settle(slot?: number): void {
    this.dragging = false;
    const reset = (): void => {
      if (slot !== undefined && slot < this.items.length) this.onSelect(slot);
      this.touchSlot = -1;
      this.lift = 0;
    };
    if (reduceMotion()) reset();
    else this.getUIContext().animateTo({ curve: curves.springMotion(0.35, 0.78) }, reset);
  }

  // 中性透明液态玻璃：深色背景上用白字，浅色阅读页上用深字，不随状态染色
  private glyphColor(active: boolean): string {
    if (this.darkSurface) return active ? '#FFFFFF' : '#CCFFFFFF';
    return active ? '#10231C' : '#8010231C';
  }

  private barTint(): string {
    // 低遮罩 + 轻模糊：能透出底下的内容，而不是一块磨砂白板
    return this.darkSurface ? '#0AFFFFFF' : '#33FFFFFF';
  }

  @Builder
  glyph(item: GlassTabItem, accent: boolean): void {
    Column({ space: 3 }) {
      Image(accent ? item.activeIcon : item.icon)
        .width(24).height(24).objectFit(ImageFit.Contain).supportSvg2(true).colorFilter(careIconTint(this.glyphColor(accent)))
        .draggable(false)
      if (!this.compact) {
        Text(item.label)
          .fontSize(11).fontWeight(FontWeight.Medium).maxLines(1)
          .fontColor(this.glyphColor(accent))
      }
    }.width('100%').height('100%').justifyContent(FlexAlign.Center)
  }

  @Builder
  selection(): void {
    Stack({ alignContent: Alignment.TopStart }) {
      Column()
        .width('100%').height('100%')
        .borderRadius(999)
        .backgroundColor(this.darkSurface ? '#3DFFFFFF' : '#CCFFFFFF')
        .linearGradient({
          direction: GradientDirection.Bottom,
          colors: [['#33FFFFFF', 0], ['#08FFFFFF', 1]],
        })
        .border({ width: 1, color: this.darkSurface ? '#66FFFFFF' : '#FFFFFFFF' })
      // Clip the accent layer to the moving lens so partially covered icons keep their position.
      Row() {
        ForEach(this.items, (item: GlassTabItem) => {
          Column() { this.glyph(item, true) }
            .width(this.cellWidth()).height('100%')
        }, (item: GlassTabItem): string => item.label)
      }
      .width(this.barWidth()).height(this.barHeight())
      .position({ x: -this.pillX(), y: (this.pillHeight() - this.barHeight()) / 2 })
    }
    .width(this.pillWidth()).height(this.pillHeight())
    .borderRadius(999).clip(true)
    .position({ x: this.pillX(), y: (this.barHeight() - this.pillHeight()) / 2 })
    .shadow({ radius: 4 + 8 * this.lift, offsetY: 1 + 3 * this.lift, color: '#290F172A' })
    .hitTestBehavior(HitTestMode.None)
    .accessibilityLevel('no-hide-descendants')
  }

  build() {
    Stack({ alignContent: Alignment.TopStart }) {
      Column()
        .width('100%').height('100%')
        .borderRadius(999)
        .backgroundEffect({
          radius: 4,
          saturation: 1.4,
          brightness: 1.0,
          color: this.barTint(),
        })
        .linearGradient({
          direction: GradientDirection.Bottom,
          colors: [['#14FFFFFF', 0], ['#00FFFFFF', 0.4], ['#00000000', 1]],
        })
        .border({ width: 1, color: this.darkSurface ? '#40FFFFFF' : '#99FFFFFF' })
        .shadow({ radius: 24, offsetY: 10, color: this.darkSurface ? '#64000000' : '#4010231C' })
        .scale({ x: 1 + 0.03 * this.lift, y: 1 + 0.02 * this.lift })
        .hitTestBehavior(HitTestMode.None)
      Row() {
        ForEach(this.items, (item: GlassTabItem, slot: number) => {
          Button({ type: ButtonType.Normal, stateEffect: false }) {
            this.glyph(item, false)
          }
          .width(this.cellWidth()).height('100%').padding(0)
          .borderRadius(999).backgroundColor(Color.Transparent)
          .id(`glass-tab-${slot}`)
          .accessibilityText(item.label).accessibilitySelected(this.selected === slot)
          .onTouch((event: TouchEvent): void => { this.trackPress(event, slot); })
          .onClick((): void => {
            // Accessibility and keyboard activation also use the existing tab selection.
            if (!this.dragging) {
              if (this.selected !== slot) softTap();
              this.settle(slot);
            }
          })
        }, (item: GlassTabItem): string => item.label)
      }.width('100%').height('100%')
      this.selection()
    }
    .width(this.barWidth()).height(this.barHeight())
    .parallelGesture(
      PanGesture({ fingers: 1, direction: PanDirection.Horizontal, distance: 6 })
        .onActionStart((event: GestureEvent): void => { this.startDrag(event); })
        .onActionUpdate((event: GestureEvent): void => {
          if (this.dragging) {
            this.touchSlot = this.dragPosition(event.offsetX);
            const cell = Math.round(this.touchSlot);
            if (cell !== this.lastDragCell) {
              this.lastDragCell = cell;
              softTap();
            }
          }
        })
        .onActionEnd((event: GestureEvent): void => {
          if (this.dragging) this.settle(Math.round(this.dragPosition(event.offsetX)));
        })
        .onActionCancel((): void => { if (this.dragging) this.settle(); })
    )
  }
}
