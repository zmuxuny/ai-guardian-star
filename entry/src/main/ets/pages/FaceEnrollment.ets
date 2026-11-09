import { abilityAccessCtrl, common } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { image } from '@kit.ImageKit';
import camera from '@ohos.multimedia.camera';
import display from '@ohos.display';
import { facePreviewCoverRect } from '../face/FacePreviewGeometry';
import { CloudService } from '../common/CloudService';
import { ThemeManager } from '../common/ThemeManager';
import { showToast } from '../common/UiFeedback';
import {
  validateFaceEnrollmentName,
} from '../face/FaceEnrollmentName';
import {
  advanceFaceEnrollmentFromName,
  FaceEnrollmentStep,
} from '../face/FaceEnrollmentFlow';
import {
  PAGE_TITLE_SIZE,
  SURFACE_PADDING,
  SURFACE_RADIUS,
} from '../components/GradientHeader';

@Builder
export function FaceEnrollmentBuilder(): void {
  FaceEnrollment();
}

@Component
export struct FaceEnrollment {
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;
  @State name: string = '';
  @State nameError: string = '';
  @State step: FaceEnrollmentStep = 'name';
  @State busy: boolean = false;
  @State cameraReady: boolean = false;
  @State cameraMessage: string = '正在启动相机…';
  @State capturedPreview?: image.PixelMap = undefined;
  @State inputFocused: boolean = false;
  @State guideWidth: number = 260;
  @State guideHeight: number = 340;
  private previewWidth: number = 0;
  private previewHeight: number = 0;
  private previewProfile?: camera.Profile;
  private previewConfigured: boolean = false;
  pathStack: NavPathStack = new NavPathStack();
  private xController: XComponentController = new XComponentController();
  private cameraInput?: camera.CameraInput;
  private previewOutput?: camera.PreviewOutput;
  private photoOutput?: camera.PhotoOutput;
  private photoSession?: camera.PhotoSession;
  private capturedBytes?: ArrayBuffer;
  private capturedSource?: image.ImageSource;

  private updatePreviewGeometry(): void {
    if (!this.previewConfigured || this.previewOutput === undefined || this.previewProfile === undefined ||
      this.previewWidth <= 0 || this.previewHeight <= 0) return;
    const rotation = this.previewOutput.getPreviewRotation(display.getDefaultDisplaySync().rotation * 90);
    this.previewOutput.setPreviewRotation(rotation, true);
    this.xController.setXComponentSurfaceRect(facePreviewCoverRect(
      this.previewWidth, this.previewHeight,
      this.previewProfile.size.width, this.previewProfile.size.height, rotation));
  }

  private finishInput(): void {
    this.getUIContext().getFocusController().clearFocus();
  }

  private canContinue(): boolean {
    return !this.busy && validateFaceEnrollmentName(this.name).isValid;
  }

  private async continueToCapture(): Promise<void> {
    if (this.busy) return;
    const transition = advanceFaceEnrollmentFromName(this.name);
    if (transition.step === 'name') {
      this.nameError = transition.message;
      return;
    }
    this.name = transition.normalizedName;
    this.nameError = '';
    this.finishInput();
    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    try {
      const atManager = abilityAccessCtrl.createAtManager();
      const grantResult = await atManager.requestPermissionsFromUser(context, ['ohos.permission.CAMERA']);
      if (grantResult.authResults[0] !== 0) {
        showToast(this.getUIContext(), { message: '需要相机权限才能采集人脸，请在系统设置中开启' });
        return;
      }
      this.step = 'capture';
      this.cameraMessage = '正在启动相机…';
    } catch (error) {
      console.error(`[FaceEnrollment] request camera permission failed: ${JSON.stringify(error)}`);
      showToast(this.getUIContext(), { message: '相机权限申请失败，请稍后重试' });
    }
  }

  private async startCamera(surfaceId: string): Promise<void> {
    if (surfaceId === '' || this.cameraReady) return;
    try {
      const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
      const cameraManager = camera.getCameraManager(context);
      const cameras = cameraManager.getSupportedCameras();
      let frontCamera: camera.CameraDevice | undefined = undefined;
      for (let index = 0; index < cameras.length; index++) {
        if (cameras[index].cameraPosition === camera.CameraPosition.CAMERA_POSITION_FRONT) {
          frontCamera = cameras[index];
          break;
        }
      }
      if (frontCamera === undefined) throw new Error('未检测到前置摄像头');
      const capability = cameraManager.getSupportedOutputCapability(frontCamera, camera.SceneMode.NORMAL_PHOTO);
      if (capability.previewProfiles.length === 0 || capability.photoProfiles.length === 0) {
        throw new Error('摄像头不支持拍照输出');
      }

      // Keep preview and photo on the same aspect ratio to avoid a framing jump.
      this.previewProfile = capability.previewProfiles[0];
      let photoProfile = capability.photoProfiles[0];
      const previewRatio = this.previewProfile.size.width / this.previewProfile.size.height;
      for (const candidate of capability.photoProfiles) {
        if (Math.abs(candidate.size.width / candidate.size.height - previewRatio) <
          Math.abs(photoProfile.size.width / photoProfile.size.height - previewRatio)) {
          photoProfile = candidate;
        }
      }
      this.cameraInput = cameraManager.createCameraInput(frontCamera);
      await this.cameraInput.open();
      this.previewOutput = cameraManager.createPreviewOutput(this.previewProfile, surfaceId);
      this.photoOutput = cameraManager.createPhotoOutput(photoProfile);
      this.photoOutput.on('photoAvailable', (error: BusinessError, photo: camera.Photo): void => {
        this.handlePhotoAvailable(error, photo);
      });
      this.photoSession = cameraManager.createSession<camera.PhotoSession>(camera.SceneMode.NORMAL_PHOTO);
      this.photoSession.beginConfig();
      if (!this.photoSession.canAddInput(this.cameraInput)) throw new Error('无法连接前置摄像头');
      this.photoSession.addInput(this.cameraInput);
      if (!this.photoSession.canAddOutput(this.previewOutput)) throw new Error('无法创建相机预览');
      this.photoSession.addOutput(this.previewOutput);
      if (!this.photoSession.canAddOutput(this.photoOutput)) throw new Error('无法创建拍照输出');
      this.photoSession.addOutput(this.photoOutput);
      await this.photoSession.commitConfig();
      this.previewConfigured = true;
      this.updatePreviewGeometry();
      await this.photoSession.start();
      this.cameraReady = true;
      this.cameraMessage = '';
    } catch (error) {
      console.error(`[FaceEnrollment] start camera failed: ${JSON.stringify(error)}`);
      this.cameraMessage = '相机启动失败，请返回后重试';
      await this.releaseCamera();
    }
  }

  private handlePhotoAvailable(error: BusinessError, photo: camera.Photo): void {
    if (error) {
      console.error(`[FaceEnrollment] photo unavailable: ${JSON.stringify(error)}`);
      this.busy = false;
      showToast(this.getUIContext(), { message: '拍摄失败，请重试' });
      return;
    }
    this.prepareCapturedPhoto(photo);
  }

  private async prepareCapturedPhoto(photo: camera.Photo): Promise<void> {
    try {
      const component = await photo.main.getComponent(image.ComponentType.JPEG);
      const photoBytes = component.byteBuffer.slice(0);
      await photo.release();
      if (photoBytes.byteLength === 0) throw new Error('照片数据为空');
      if (photoBytes.byteLength > 8 * 1024 * 1024) {
        showToast(this.getUIContext(), { message: '照片不能超过 8 MiB' });
        this.busy = false;
        return;
      }
      this.capturedSource = image.createImageSource(photoBytes);
      this.capturedPreview = await this.capturedSource.createPixelMap();
      this.capturedBytes = photoBytes;
      this.busy = false;
      await this.releaseCamera();
    } catch (error) {
      try {
        await photo.release();
      } catch (_releaseError) {
      }
      console.error(`[FaceEnrollment] prepare captured photo failed: ${JSON.stringify(error)}`);
      this.busy = false;
      showToast(this.getUIContext(), { message: '照片处理失败，请重试' });
    }
  }

  private async confirmUpload(): Promise<void> {
    if (this.capturedBytes === undefined || this.busy) return;
    this.busy = true;
    try {
      showToast(this.getUIContext(), { message: '正在上传人脸信息…' });
      const result = await CloudService.getInstance().enrollFace(this.name, this.capturedBytes);
      if (!result.success) {
        showToast(this.getUIContext(), { message: result.message || '人脸录入失败，请重试' });
        this.busy = false;
        return;
      }
      showToast(this.getUIContext(), { message: '人脸录入成功！开发板已更新识别库' });
      await this.clearCapturedPhoto();
      this.pathStack.pop();
    } catch (error) {
      console.error(`[FaceEnrollment] upload confirmed photo failed: ${JSON.stringify(error)}`);
      this.busy = false;
      showToast(this.getUIContext(), { message: '操作失败，请重试' });
    }
  }

  private async clearCapturedPhoto(): Promise<void> {
    this.capturedBytes = undefined;
    try {
      if (this.capturedPreview !== undefined) await this.capturedPreview.release();
    } catch (_error) {
    }
    try {
      if (this.capturedSource !== undefined) await this.capturedSource.release();
    } catch (_error) {
    }
    this.capturedPreview = undefined;
    this.capturedSource = undefined;
  }

  private async retakePhoto(): Promise<void> {
    if (this.busy) return;
    await this.clearCapturedPhoto();
    this.cameraMessage = '正在启动相机…';
    await this.startCamera(this.xController.getXComponentSurfaceId());
  }

  private async capturePhoto(): Promise<void> {
    if (!this.cameraReady || this.photoOutput === undefined || this.busy) return;
    this.busy = true;
    try {
      const rotation = this.photoOutput.getPhotoRotation(display.getDefaultDisplaySync().rotation * 90);
      await this.photoOutput.capture({ rotation });
    } catch (error) {
      console.error(`[FaceEnrollment] capture failed: ${JSON.stringify(error)}`);
      this.busy = false;
      showToast(this.getUIContext(), { message: '拍摄失败，请重试' });
    }
  }

  private async releaseCamera(): Promise<void> {
    this.cameraReady = false;
    this.previewConfigured = false;
    try { if (this.photoSession !== undefined) await this.photoSession.stop(); } catch (_error) {}
    try { if (this.photoSession !== undefined) await this.photoSession.release(); } catch (_error) {}
    try { if (this.previewOutput !== undefined) await this.previewOutput.release(); } catch (_error) {}
    try { if (this.photoOutput !== undefined) await this.photoOutput.release(); } catch (_error) {}
    try { if (this.cameraInput !== undefined) await this.cameraInput.close(); } catch (_error) {}
    this.photoSession = undefined;
    this.previewOutput = undefined;
    this.previewProfile = undefined;
    this.photoOutput = undefined;
    this.cameraInput = undefined;
  }

  private async goBack(): Promise<void> {
    if (this.busy) return;
    if (this.step === 'capture') {
      await this.releaseCamera();
      await this.clearCapturedPhoto();
      this.step = 'name';
      return;
    }
    this.pathStack.pop();
  }

  aboutToDisappear(): void {
    this.releaseCamera();
    this.clearCapturedPhoto();
  }

  @Builder
  PageHeader(): void {
    Row({ space: 12 }) {
      Button({ type: ButtonType.Normal }) {
        Image(this.themeManager.isDarkMode ? $r('app.media.ic_camera_back') : $r('app.media.ic_nav_back_dark'))
          .width(20).height(20).objectFit(ImageFit.Contain)
      }
      .width(44).height(44).padding(0).borderRadius(SURFACE_RADIUS)
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .accessibilityText('返回').enabled(!this.busy)
      .onClick((): void => { this.goBack(); })
      Text('人脸数据采集')
        .fontSize(PAGE_TITLE_SIZE).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .layoutWeight(1)
    }
    .width('100%').constraintSize({ maxWidth: 640 })
    .padding({
      left: SURFACE_PADDING,
      right: SURFACE_PADDING,
      top: this.topSafeHeight + 8,
      bottom: 12,
    })
  }

  @Builder
  NameForm(): void {
    Column({ space: 18 }) {
      Column({ space: 6 }) {
        Text('填写人脸用户姓名')
          .fontSize(20).fontWeight(FontWeight.Bold)
          .fontColor(this.themeManager.colors.primaryTextColor)
          .width('100%')
        Text('请填写需要采集人脸的用户姓名。')
          .fontSize(13).lineHeight(20)
          .fontColor(this.themeManager.colors.secondaryTextColor)
          .width('100%')
      }.width('100%').alignItems(HorizontalAlign.Start)

      Column({ space: 8 }) {
        Text('姓名')
          .fontSize(14).fontWeight(FontWeight.Medium)
          .fontColor(this.themeManager.colors.primaryTextColor)
          .width('100%')
        TextInput({ placeholder: '请输入姓名，例如：张三', text: this.name })
          .height(52).width('100%').fontSize(16).maxLength(64)
          .fontColor(this.themeManager.colors.primaryTextColor)
          .placeholderColor(this.themeManager.colors.secondaryTextColor)
          .backgroundColor(this.themeManager.colors.secondaryBackgroundColor)
          .borderRadius(12)
          .border({
            width: this.nameError === '' ? 1 : 1.5,
            color: this.nameError === ''
              ? this.themeManager.colors.borderColor
              : this.themeManager.colors.dangerTextColor,
          })
          .padding({ left: 14, right: 14 })
          .enabled(!this.busy)
          .accessibilityText('人脸用户姓名')
          .onFocus((): void => { this.inputFocused = true; })
          .onBlur((): void => { this.inputFocused = false; })
          .onChange((value: string): void => {
            this.name = value;
            const validation = validateFaceEnrollmentName(value);
            this.nameError = value.length === 0 || validation.isValid ? '' : validation.message;
          })
        if (this.nameError !== '') {
          Text(this.nameError)
            .fontSize(12).fontColor(this.themeManager.colors.dangerTextColor)
            .width('100%').accessibilityText('姓名错误：' + this.nameError)
        } else {
          Text('最多64个字符，不能包含 / 或 \\ 等路径符号')
            .fontSize(12).fontColor(this.themeManager.colors.tertiaryTextColor)
            .width('100%')
        }
      }.width('100%').alignItems(HorizontalAlign.Start)

      Row({ space: 10 }) {
        Image($r('app.media.ic_shield_blue')).width(24).height(24).objectFit(ImageFit.Contain)
        Text('拍摄照片仅在本次采集过程中临时处理，完成或退出后释放。')
          .fontSize(12).lineHeight(18).fontColor(this.themeManager.colors.secondaryTextColor)
          .layoutWeight(1)
      }
      .width('100%').padding(12)
      .backgroundColor(this.themeManager.colors.secondaryBackgroundColor)
      .borderRadius(12)
    }
    .width('100%').padding(SURFACE_PADDING)
    .backgroundColor(this.themeManager.colors.cardBackgroundColor)
    .borderRadius(SURFACE_RADIUS)
    .alignItems(HorizontalAlign.Start)
  }

  @Builder
  CaptureGuide(): void {
    Column({ space: 6 }) {
      Text(this.capturedPreview === undefined ? '请将面部完整置于取景框内' : '请确认人脸照片')
        .fontSize(20).fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
      Text(this.capturedPreview === undefined
        ? '保持正脸、光线充足，并摘下口罩或其他遮挡物'
        : '照片清晰且面部完整后，再点击确定上传')
        .fontSize(13).lineHeight(20)
        .fontColor(this.themeManager.colors.secondaryTextColor)
    }
    .width('100%').alignItems(HorizontalAlign.Center)
    .padding({ left: 20, right: 20, top: 18, bottom: 14 })
  }

  @Builder
  FacePreview(): void {
    Stack({ alignContent: Alignment.Center }) {
      XComponent({ id: 'face_capture_surface', type: XComponentType.SURFACE, controller: this.xController })
        .width('100%').height('100%')
        .onLoad((): void => {
          this.xController.setXComponentSurfaceRotation({ lock: true });
          this.startCamera(this.xController.getXComponentSurfaceId());
        })
        .onAreaChange((_oldArea: Area, area: Area): void => {
          const width = Number(area.width);
          const height = Number(area.height);
          this.previewWidth = this.getUIContext().vp2px(width);
          this.previewHeight = this.getUIContext().vp2px(height);
          const guideScale = Math.max(0, Math.min(1, (width - 32) / 260, (height - 24) / 340));
          this.guideWidth = 260 * guideScale;
          this.guideHeight = 340 * guideScale;
          try {
            this.updatePreviewGeometry();
          } catch (error) {
            console.error(`[FaceEnrollment] resize preview failed: ${JSON.stringify(error)}`);
            this.cameraMessage = '预览调整失败，请返回后重试';
            this.releaseCamera();
          }
        })
        .onDestroy((): void => { this.releaseCamera(); })
      if (this.capturedPreview !== undefined) {
        Image(this.capturedPreview)
          .width('100%').height('100%').objectFit(ImageFit.Cover)
      }
      Stack({ alignContent: Alignment.Center }) {
        Rect().width('100%').height('100%').fill('#FFFFFF')
        Ellipse().width(this.guideWidth).height(this.guideHeight).fill('#000000').blendMode(BlendMode.DST_OUT)
      }
      .width('100%').height('100%')
      .blendMode(BlendMode.SRC_OVER, BlendApplyType.OFFSCREEN)
      Ellipse().width(this.guideWidth).height(this.guideHeight).fill(Color.Transparent)
        .stroke('#2563EB').strokeWidth(3)
      if (!this.cameraReady && this.capturedPreview === undefined) {
        Column({ space: 10 }) {
          LoadingProgress().width(30).height(30).color('#2563EB')
          Text(this.cameraMessage).fontSize(13)
            .fontColor(this.themeManager.colors.secondaryTextColor)
        }
      }
    }
    .width('100%').layoutWeight(1).clip(true).backgroundColor('#FFFFFF')
  }

  @Builder
  BottomActions(): void {
    Row({ space: 12 }) {
      if (this.step === 'name') {
        Button('返回', { type: ButtonType.Normal })
          .layoutWeight(1).height(50).fontSize(16).fontWeight(FontWeight.Medium)
          .fontColor(this.themeManager.colors.linkTextColor).borderRadius(SURFACE_RADIUS)
          .backgroundColor(this.themeManager.colors.cardBackgroundColor).enabled(!this.busy)
          .onClick((): void => { this.goBack(); })
      } else {
        Button(this.capturedPreview === undefined ? '返回上一步' : '重拍', { type: ButtonType.Normal })
          .layoutWeight(1).height(50).fontSize(16).fontWeight(FontWeight.Medium)
          .fontColor(this.themeManager.colors.linkTextColor).borderRadius(SURFACE_RADIUS)
          .backgroundColor(this.themeManager.colors.cardBackgroundColor).enabled(!this.busy)
          .onClick((): void => {
            if (this.capturedPreview === undefined) this.goBack(); else this.retakePhoto();
          })
      }
      if (this.step === 'name') {
        Button('继续', { type: ButtonType.Normal })
          .layoutWeight(1).height(50).fontSize(16).fontWeight(FontWeight.Medium)
          .fontColor('#FFFFFF').borderRadius(SURFACE_RADIUS)
          .backgroundColor(this.canContinue() ? this.themeManager.colors.primaryButtonColor : '#64748B')
          .enabled(this.canContinue())
          .accessibilityText(this.canContinue() ? '继续采集人脸' : '请先填写有效姓名')
          .onClick((): void => { this.continueToCapture(); })
      } else {
        Button(this.capturedPreview === undefined ? (this.busy ? '处理中…' : '拍摄')
          : (this.busy ? '上传中…' : '确定上传'), { type: ButtonType.Normal })
          .layoutWeight(1).height(50).fontSize(16).fontWeight(FontWeight.Medium)
          .fontColor('#FFFFFF').borderRadius(SURFACE_RADIUS)
          .backgroundColor((this.cameraReady || this.capturedPreview !== undefined) && !this.busy
            ? this.themeManager.colors.primaryButtonColor : '#64748B')
          .enabled((this.cameraReady || this.capturedPreview !== undefined) && !this.busy)
          .accessibilityText(this.capturedPreview === undefined ? '拍摄人脸照片' : '确认并上传人脸照片')
          .onClick((): void => {
            if (this.capturedPreview === undefined) this.capturePhoto(); else this.confirmUpload();
          })
      }
    }
    .width('100%').constraintSize({ maxWidth: 640 })
    .padding({ left: SURFACE_PADDING, right: SURFACE_PADDING, top: 12, bottom: 20 })
  }

  build() {
    NavDestination() {
      Column() {
        this.PageHeader()
        if (this.step === 'name') {
          Scroll() {
            Column() {
              this.NameForm()
            }
            .width('100%').constraintSize({ maxWidth: 640 })
            .padding({ left: SURFACE_PADDING, right: SURFACE_PADDING, top: 8, bottom: 24 })
          }
          .layoutWeight(1).width('100%').align(Alignment.Top)
          .scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
        } else {
          Column() {
            Column() {
              this.CaptureGuide()
              this.FacePreview()
            }
            .width('100%').layoutWeight(1)
            .backgroundColor(this.themeManager.colors.cardBackgroundColor)
            .borderRadius(SURFACE_RADIUS).clip(true)
          }
          .layoutWeight(1).width('100%').constraintSize({ maxWidth: 640 })
          .padding({ left: SURFACE_PADDING, right: SURFACE_PADDING, top: 8 })
        }
        this.BottomActions()
      }
      .width('100%').height('100%')
      .backgroundColor(this.themeManager.colors.backgroundColor)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .hideTitleBar(true)
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .onBackPressed((): boolean => {
      if (this.inputFocused) {
        this.finishInput();
        return true;
      }
      if (this.busy) return true;
      if (this.step === 'capture') {
        this.goBack();
        return true;
      }
      return false;
    })
    .onReady((context: NavDestinationContext): void => { this.pathStack = context.pathStack; })
  }
}
