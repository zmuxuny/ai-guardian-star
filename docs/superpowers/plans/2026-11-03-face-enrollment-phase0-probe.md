# 人脸录入 Phase 0 技术探针实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不接入正式上传、不持久化用户照片的前提下，证明严格头姿、动作活体同人绑定、自定义三路相机和开发板独立头姿复验可行，并冻结 Phase 1 所需接口与模型。

**Architecture:** App 探针使用 Camera Kit 的显示 PreviewOutput、分析 PreviewOutput 和 PhotoOutput，所有帧先规范化为竖直、未镜像的 RGBA_8888 PixelMap，再交给 Core Vision Kit。纯规则层负责角度、质量、提示优先级和 500 ms/5 帧稳定窗；Vision Kit 负责动作活体，Core Vision `faceComparator` 绑定活体与最终照片。开发板用独立的可替换 `FacePoseEstimator` 适配器评测候选 6DRepNet ONNX→OM 模型；Phase 0 只输出 go/no-go 报告，不改云端协议、数据库和正式登记服务。

**Tech Stack:** ArkTS / HarmonyOS API 24、Camera Kit、Image Kit、Core Vision Kit、Vision Kit、Hypium/Node 离线测试、Python 3、OpenCV、Ascend ACL/CANN、SQLite（仅现状检查，不改 schema）。

**Spec:** `docs/superpowers/specs/2026-11-03-face-vector-enrollment-design.md`

## Global Constraints

- 所有终端命令使用 PowerShell 7；HarmonyOS 构建只使用 `DEVECO_BUILD.md` 固定的 DevEco Node、OHPM、Hvigor 和 Java。
- 执行前用 `using-git-worktrees` 创建独立 worktree，分支名 `wip/codex-20261103-face-vector-enrollment`；不得覆盖当前工作区未提交改动。
- 不修改、合并或推送 `zy`；未经用户另行授权不 push、不部署生产服务器或正式开发板服务。
- 每个逻辑任务只做本地提交，提交信息使用完整中文并追加 `AI-Agent: codex`；显式 `git add <files>`，禁止 `git add -A`。
- 目标与兼容 SDK 固定为 `6.1.1(24)`；必须在至少两台目标手机真机验证，模拟器和构建成功不能代替设备验收。
- 角度规则固定：正脸 `-15°～15°`、左脸 `≤-25°`、右脸 `≥25°`、pitch `-20°～20°`、roll `-15°～15°`；不得擅自增加侧脸最大 yaw。
- 放行条件固定：连续至少 500 ms、至少 5 个不同帧、最大样本间隔 300 ms、点击时最后结果新鲜度不超过 300 ms；任何条件失败立即禁用。
- 必须同时通过单人脸、完整度、清晰度、遮挡和动作活体同人绑定；不得只凭角度放行。
- 前置预览可以镜像，检测与最终 JPEG 必须是竖直、未镜像、无 EXIF 方向依赖的规范图。
- 不把探针照片写入仓库、系统相册、云端、日志或数据库；临时测试数据只允许存在于 App 私有 cache 或显式临时目录，任务结束必须验证删除。
- 模型权重、HAP、日志、人脸图、密钥和设备凭据不得提交；只记录模型来源、许可证、SHA-256、输入输出和转换命令。

## Review Focus

- 前摄镜像、90°/270°旋转或相机 ID 变化时，物理左转仍必须映射为负 yaw，未知标定必须拒绝录入；Task 2 的转换测试和 Task 7 的双机验收固定此行为。
- 分析结果乱序、延迟、重复 frameId、切后台或相机会话重建时，稳定窗必须清零，旧结果不能重新启用拍摄；Task 1 和 Task 3 覆盖。
- 活体通过后换人、使用照片或比较服务超时必须拒绝，且 `mPixelMap` 在成功、失败和退出路径都释放；Task 5 覆盖。
- 目标前摄不支持“显示预览＋分析预览＋拍照”或活体释放后 camera busy 时必须给出明确 UNSUPPORTED/RETRYABLE 结果，不能静默退回 CameraPicker；Task 4 和 Task 5 覆盖。
- App 与板端在 `±15°/±25°` 边界发生模型分歧时必须判定 Phase 0 未通过，不允许用 App 元数据覆盖板端结果；Task 6 和 Task 7 覆盖。

---

## 文件结构

### App 探针

- Create `entry/src/main/ets/face/FaceProbeTypes.ets`：共享 pose、质量、门禁状态和错误码类型。
- Create `entry/src/main/ets/face/FacePoseGate.ets`：纯规则状态机，不依赖 ArkUI 或相机。
- Create `entry/src/main/ets/face/FaceFrameTransform.ets`：规范图方向和头姿标定转换。
- Create `entry/src/main/ets/face/FaceProbeMetrics.ets`：P50/P95/P99、掉帧和重置原因聚合，只输出非图像 JSON。
- Create `entry/src/main/ets/face/FaceVisionAnalyzer.ets`：Core Vision 检测器适配器与 latest-frame 管线。
- Create `entry/src/main/ets/face/FaceCameraProbeController.ets`：三路 CameraSession 生命周期和静态拍照。
- Create `entry/src/main/ets/face/FaceLivenessProbe.ets`：动作活体、同人比较和 PixelMap 释放。
- Create `entry/src/main/ets/pages/FaceEnrollmentProbe.ets`：Phase 0 真机探针页，不调用正式上传。
- Modify `entry/src/main/resources/base/profile/route_map.json`：登记 `FaceEnrollmentProbe`。
- Modify `entry/src/main/ets/pages/person.ets`：仅在 WIP 探针分支把“人脸信息”入口导向探针页；Phase 1 替换，不进入正式分支。
- Create `tests/face-pose-gate.test.cjs`、`tests/face-probe-pipeline.test.cjs`：使用 DevEco TypeScript 编译器运行纯 ArkTS 逻辑离线测试。

### 开发板模型探针

- Create `src/guardian_face_pose.py`：可替换板端头姿估计器接口；Phase 0 不接入正式登记路径。
- Create `tools/face_pose_probe/benchmark.py`：读取临时 JSONL 清单，对最终 JPEG 运行板端估计并输出非图像指标。
- Create `tests/test_face_pose_probe.py`：使用假模型固定角度换算、阈值和统计行为。
- Modify `MODEL_ASSETS.md`：仅在候选通过后记录来源、MIT 许可证、SHA-256、输入输出、CANN/ATC 和目标 SoC；不提交权重。
- Create `docs/face-pose-probe-decision.md`：记录两台手机、板端模型和最终 go/no-go 结论。

---

### Task 1: 严格头姿门禁状态机

**Files:**
- Create: `entry/src/main/ets/face/FaceProbeTypes.ets`
- Create: `entry/src/main/ets/face/FacePoseGate.ets`
- Create: `tests/face-pose-gate.test.cjs`

**Interfaces:**
- Consumes: 无。
- Produces: `PoseKind = 'front' | 'left' | 'right'`；`PoseGateSample`；`PoseGateState`；`FacePoseGate.accept(sample: PoseGateSample): PoseGateState`；`FacePoseGate.reset(reason: GateResetReason): void`。

- [ ] **Step 1: 写失败测试固定角度边界和提示优先级**

在 `tests/face-pose-gate.test.cjs` 断言：正脸 `-15/15` 通过而 `-15.01/15.01` 拒绝；左脸 `-25` 通过、`-24.99` 拒绝；右脸 `25` 通过、`24.99` 拒绝；pitch 与 roll 边界包含端点。再断言原因优先级为 `face_count → liveness → completeness → clarity → roll → pitch → yaw`，对应中文提示与设计稿一致。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$DevEco = 'C:\Program Files\Huawei\DevEco Studio'
$env:GUARDIAN_TYPESCRIPT_PATH = Join-Path $DevEco 'tools\hvigor\hvigor\node_modules\typescript'
& (Join-Path $DevEco 'tools\node\node.exe') --test .\tests\face-pose-gate.test.cjs
```

Expected: FAIL，提示 `FacePoseGate.ets` 或导出类型不存在。

- [ ] **Step 3: 实现门禁类型与单帧规则**

`PoseGateSample` 必须包含 `frameId/capturedAtMs/receivedAtMs/pose/yaw/pitch/roll/singleFace/livenessMatched/complete/clear`。`FacePoseGate` 只消费布尔质量结果，不自行推理图片；所有阈值使用 Global Constraints 的固定值。

- [ ] **Step 4: 写失败测试固定稳定窗与重置**

增加测试：5 个不同 frameId 横跨至少 500 ms 才允许；重复 frameId 不计数；样本间隔或结果新鲜度超过 300 ms、质量瞬时失败、`reset('background'|'camera_restart'|'orientation_change')` 后必须从 0 重新累计；乱序时间戳拒绝且不能倒推 stableSince。

- [ ] **Step 5: 实现稳定窗并运行测试**

Run: Task 1 Step 2 的同一命令。

Expected: 全部 PASS，且测试输出包含角度边界、提示优先级、稳定窗、乱序和重置用例。

- [ ] **Step 6: 本地提交**

```powershell
git add entry/src/main/ets/face/FaceProbeTypes.ets entry/src/main/ets/face/FacePoseGate.ets tests/face-pose-gate.test.cjs
git commit -m "实现：固定人脸录入严格头姿门禁`n`nAI-Agent: codex"
```

### Task 2: 规范图转换、标定和非图像指标

**Files:**
- Create: `entry/src/main/ets/face/FaceFrameTransform.ets`
- Create: `entry/src/main/ets/face/FaceProbeMetrics.ets`
- Create: `tests/face-probe-pipeline.test.cjs`

**Interfaces:**
- Consumes: `PoseGateSample` from Task 1。
- Produces: `FrameTransformSpec`；`PoseCalibrationKey`；`normalizePose(raw: RawPose, calibration: PoseCalibration): CanonicalPose`；`FaceProbeMetrics.record(frame: ProbeFrameMetric): void`；`FaceProbeMetrics.snapshot(): ProbeMetricsSnapshot`。

- [ ] **Step 1: 写失败测试固定标定键和角度变换**

断言标定键必须包含 `deviceModel/systemVersion/cameraId/sensorOrientation/detectorVersion/preprocessVersion`；`yawSign/pitchSign/rollSign` 只接受 `-1|1`；零点偏移在符号变换后应用；缺失键或非有限角返回 `CALIBRATION_MISSING/INVALID_POSE`，不能给默认方向。

- [ ] **Step 2: 写失败测试固定指标统计**

以确定数组断言 P50/P95/P99、处理帧数、丢弃帧数、重置原因计数；快照只包含数值、设备/版本和错误码，不包含 PixelMap、文件路径、JPEG 字节或姓名。

- [ ] **Step 3: 运行测试确认失败**

Run: Task 1 Step 2 的命令，把测试文件改为 `tests/face-probe-pipeline.test.cjs`。

Expected: FAIL，提示转换或指标模块不存在。

- [ ] **Step 4: 实现转换与指标模块**

像素规范化顺序固定为：根据传感器/显示旋转纠正 → 去前摄镜像 → 输出竖直 RGBA_8888 → 再运行检测器；EXIF 只作为输入信息，输出 PixelMap/JPEG 不保留方向依赖。`FaceProbeMetrics` 使用有界数组，最多保留最近 600 个耗时样本。

- [ ] **Step 5: 运行 Task 1 与 Task 2 测试**

Expected: 两个 Node 测试文件全部 PASS。

- [ ] **Step 6: 本地提交**

```powershell
git add entry/src/main/ets/face/FaceFrameTransform.ets entry/src/main/ets/face/FaceProbeMetrics.ets tests/face-probe-pipeline.test.cjs
git commit -m "实现：增加人脸探针规范图与指标规则`n`nAI-Agent: codex"
```

### Task 3: Core Vision latest-frame 分析管线

**Files:**
- Create: `entry/src/main/ets/face/FaceVisionAnalyzer.ets`
- Modify: `tests/face-probe-pipeline.test.cjs`

**Interfaces:**
- Consumes: `FrameTransformSpec` and `FaceProbeMetrics` from Task 2；Huawei `faceDetector`。
- Produces: `FaceDetectorPort.init(): Promise<void>`；`FaceDetectorPort.detect(pixelMap: image.PixelMap): Promise<FaceAnalysis>`；`FaceDetectorPort.release(): Promise<void>`；`LatestFrameAnalyzer.offer(frame: AnalysisFrame): Promise<AnalysisOutcome>`。

- [ ] **Step 1: 写失败测试固定 latest-frame 行为**

通过假 `FaceDetectorPort` 断言：一次只推理一帧；忙时不排队并记录 `droppedBusy`；会话 token 改变或页面销毁后，迟到结果返回 `STALE_SESSION` 且不能送入 `FacePoseGate`；每个输入 PixelMap 恰好释放一次。

- [ ] **Step 2: 运行测试确认失败**

Expected: FAIL，提示 `LatestFrameAnalyzer` 不存在。

- [ ] **Step 3: 实现 Core Vision 适配器**

初始化 `faceDetector.init({ faceBlock: true })`；只接受 RGBA_8888 规范 PixelMap；映射 `Face.pose`、`probability`、`block`、`rect` 和五点。完整度初判为恰好一张脸、遮挡为 `UNBLOCKED`、五点存在且几何有限；不伪造逐关键点置信度。

- [ ] **Step 4: 将转换、检测、门禁全链路耗时写入指标**

耗时起点使用帧采集单调时间，分别记录 `normalizeMs/detectMs/gateMs/endToEndMs`；P95 通过标准为小于选定分析周期，初始分析周期 200 ms。

- [ ] **Step 5: 运行离线测试与 Release 编译**

Run: 两个 Node 测试文件；再按 `DEVECO_BUILD.md` 执行 Release `assembleHap --no-daemon`。

Expected: 测试 PASS；Hvigor 输出 `BUILD SUCCESSFUL` 且能找到非零 HAP。此结果只证明编译，不证明真机可用。

- [ ] **Step 6: 本地提交**

```powershell
git add entry/src/main/ets/face/FaceVisionAnalyzer.ets tests/face-probe-pipeline.test.cjs
git commit -m "实现：接入人脸头姿最新帧分析管线`n`nAI-Agent: codex"
```

### Task 4: 自定义三路相机探针页

**Files:**
- Create: `entry/src/main/ets/face/FaceCameraProbeController.ets`
- Create: `entry/src/main/ets/pages/FaceEnrollmentProbe.ets`
- Modify: `entry/src/main/resources/base/profile/route_map.json`
- Modify: `entry/src/main/ets/pages/person.ets`
- Modify: `tests/face-probe-pipeline.test.cjs`

**Interfaces:**
- Consumes: `LatestFrameAnalyzer` from Task 3 and `FacePoseGate` from Task 1。
- Produces: `FaceCameraProbeController.start(displaySurfaceId: string): Promise<CameraProbeCapability>`；`captureCanonicalJpeg(): Promise<CapturedProbePhoto>`；`stop(reason: CameraStopReason): Promise<void>`。

- [ ] **Step 1: 写失败测试固定 CameraSession 状态机**

通过假 camera port 断言：顺序为查询前摄 capability → 创建 display PreviewOutput → 创建 ImageReceiver PreviewOutput → 创建 PhotoOutput → `canAddOutput` → `commitConfig` → start；任一路不支持返回 `UNSUPPORTED_OUTPUT_COMBINATION`，不得回退 CameraPicker；stop/后台/方向变化会停止会话并重置门禁。

- [ ] **Step 2: 运行测试确认失败**

Expected: FAIL，提示相机控制器不存在。

- [ ] **Step 3: 实现三路相机控制器**

分析 ImageReceiver 每次只 `readLatestImage`，无论成功失败都释放 Image；PhotoOutput 的最终文件必须经过规范化、JPEG 重编码和重新解码后，再做静态分析。探针页只显示角度、当前提示、稳定帧数、P50/P95/P99、capability 和错误码，不显示/保存调试帧。

- [ ] **Step 4: 注册探针路由和 WIP 入口**

新增 `FaceEnrollmentProbe` 路由；在 WIP 分支把 `person.ets` 的“人脸信息”点击改为 `pushPathByName('FaceEnrollmentProbe', null)`，保留旧 `takePhotoAndSendToBoard` 代码不删除，便于 Phase 0 回退与差异审查。

- [ ] **Step 5: 构建并在两台目标手机验证相机组合**

每台手机记录设备型号、系统版本、cameraId、传感器方向、三路 profile、`canAddOutput` 和 `commitConfig` 结果。验收：预览连续、分析角度更新、PhotoOutput 成功、后台/返回后相机释放；任何设备不支持则停止后续完整实现并形成替代设计，不静默降级。

- [ ] **Step 6: 本地提交**

显式暂存上述四个源码/路由文件和测试，提交信息：`实现：增加严格头姿三路相机技术探针`，尾行 `AI-Agent: codex`。

### Task 5: 动作活体与最终照片同人绑定

**Files:**
- Create: `entry/src/main/ets/face/FaceLivenessProbe.ets`
- Modify: `entry/src/main/ets/pages/FaceEnrollmentProbe.ets`
- Modify: `tests/face-probe-pipeline.test.cjs`

**Interfaces:**
- Consumes: final canonical JPEG/PixelMap from Task 4；Huawei `interactiveLiveness` and `faceComparator`。
- Produces: `FaceLivenessProbe.start(): Promise<LivenessReference>`；`compare(candidate: image.PixelMap): Promise<IdentityMatch>`；`release(): Promise<void>`。

- [ ] **Step 1: 写失败测试固定资源释放和换人拒绝**

假端口断言：使用 `THREE_ACTION + BACK_MODE`；没有 `mPixelMap`、取消、超时、`isSamePerson=false`、比较异常全部拒绝；成功、失败、页面退出三条路径都恰好释放活体 PixelMap、候选 PixelMap 和 comparator；活体通过后 camera busy 只有限重试，不无限循环。

- [ ] **Step 2: 运行测试确认失败**

Expected: FAIL，提示 `FaceLivenessProbe` 不存在。

- [ ] **Step 3: 实现活体和比较适配器**

调用 `interactiveLiveness.startLivenessDetection(config, callback)`；只把 `mPixelMap` 保存在当前会话内存。初始化 `faceComparator`，将每张最终 JPEG 重新解码后的 PixelMap 与活体 PixelMap 比较；只接受 `isSamePerson=true`，相似度仅记录为非图像指标，不自行覆盖系统判定。

- [ ] **Step 4: 真机验证活体后相机重开与换人场景**

两台手机分别验证：三动作通过、取消、超时、活体后重开自定义相机、同一人通过、换人拒绝。日志只含结果码、耗时和相似度，不含照片、姓名或可还原数据。

- [ ] **Step 5: 运行测试、构建并本地提交**

Expected: Node 测试 PASS，Release HAP 构建成功；提交信息 `实现：绑定动作活体与最终人脸照片`，尾行 `AI-Agent: codex`。

### Task 6: 开发板 6DRepNet 候选模型与独立复验探针

**Files:**
- Create: `src/guardian_face_pose.py`
- Create: `tools/face_pose_probe/benchmark.py`
- Create: `tests/test_face_pose_probe.py`
- Modify: `MODEL_ASSETS.md`

**Interfaces:**
- Consumes: 临时 JSONL 清单，每行只引用临时图片路径、App 规范角和期望 pose 类别；候选模型优先采用官方 6DRepNet `RepVGG-B1g2`、224×224、MIT 许可证，模型文件不进入 Git。
- Produces: `PoseAngles`；`FacePoseEstimator.estimate(bgr_face: np.ndarray) -> PoseAngles`；benchmark JSON：模型 ID、SHA-256、P50/P95/P99、三轴误差和门禁混淆矩阵。

- [ ] **Step 1: 写失败测试固定板端接口和判定**

使用假估计器断言：非有限输出、维度错误、模型 ID 不匹配拒绝；角度规则与 App 完全一致；benchmark 不读取/输出姓名，不复制图片，报告只含路径哈希或样本 ID。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_face_pose_probe -v`

Expected: FAIL，提示 `guardian_face_pose` 或 benchmark 接口不存在。

- [ ] **Step 3: 实现可替换估计器和 benchmark**

实现预处理、模型输出到 yaw/pitch/roll 的转换与模型指纹；正式 `src/ascend_board_server.py`、`FaceLibrary` 和数据库路径保持不变。候选权重下载到工作区外临时目录，先核验官方仓库 MIT 许可证和 SHA-256。

- [ ] **Step 4: 在目标板查询并记录转换环境**

只读记录 `npu-smi info`、`atc --version`、目标 SoC 和 ACL 输入输出支持；按实际环境把 ONNX 转为 OM。转换命令、CANN/ATC 版本、输入输出 shape/dtype 和模型 SHA 写入 `MODEL_ASSETS.md`，不写设备凭据或权重。

- [ ] **Step 5: 运行公共标注集与跨端最终 JPEG benchmark**

公共标注集放工作区外临时目录；跨端样本使用 App 最终规范 JPEG，通过显式临时目录传到板端，禁止经过云端/服务器，运行后立即删除并用目录清单验证为空。通过门槛：公共集 yaw/pitch/roll MAE 各不高于 5°；板端单图 P95 不高于 500 ms；App 与板端三轴中位绝对差不高于 5°、P95 不高于 10°；门禁标签一致率至少 95%，且已标记不合格样本不得被板端错误放行。

- [ ] **Step 6: 运行单元测试并本地提交**

Expected: Python 测试 PASS；只提交源码、测试和模型元数据，不提交模型/数据。提交信息 `探针：评估开发板独立头姿复验模型`，尾行 `AI-Agent: codex`。

### Task 7: 双机持续验收与 Phase 0 决策记录

**Files:**
- Create: `docs/face-pose-probe-decision.md`
- Modify: `docs/修改记录/协作/TASKS.md`
- Modify: `docs/修改记录/协作/STATUS-codex.md`

**Interfaces:**
- Consumes: Tasks 1–6 的 App 指标、相机 capability、活体结果和板端 benchmark。
- Produces: 明确 `GO`、`GO_WITH_CHANGES` 或 `NO_GO`，以及 Phase 1 可直接引用的相机 profile、模型 ID、标定键、误差带和性能预算。

- [ ] **Step 1: 每台目标手机运行 10 分钟持续探针**

按正脸、左脸、右脸、pitch 上下、roll 倾斜、多人、遮挡、出框、模糊、过暗、过亮逐项验证。记录 P50/P95/P99、分析 fps、丢帧率、内存变化、温升和 camera error；不保存帧。

- [ ] **Step 2: 验证物理方向和严格边界**

每台手机由测试人员实际向物理左/右转头；确认规范角左负右正。围绕 `-25/-15/15/25` 采样，角度未达标或不足 500 ms/5 帧时按钮始终不可用；未知相机/标定键必须拒绝。

- [ ] **Step 3: 复核隐私与清理**

检查 App cache、系统相册、工作站临时目录、板端临时目录、云端应用目录、日志和 Git 状态；不得存在探针照片、模型权重或包含人脸数据的日志。记录只写“目录为空/发现数量”，不写文件内容。

- [ ] **Step 4: 写决策文档**

`docs/face-pose-probe-decision.md` 必须包含：设备矩阵、相机组合、Core Vision 版本、标定约定、活体/同人结果、App 性能、板端模型来源与哈希、跨端误差、隐私清理、失败项和最终结论。任一硬门槛失败时结论不得写 GO。

- [ ] **Step 5: 全量验证**

Run:

```powershell
$DevEco = 'C:\Program Files\Huawei\DevEco Studio'
$env:GUARDIAN_TYPESCRIPT_PATH = Join-Path $DevEco 'tools\hvigor\hvigor\node_modules\typescript'
& (Join-Path $DevEco 'tools\node\node.exe') --test .\tests\face-pose-gate.test.cjs .\tests\face-probe-pipeline.test.cjs
python -m unittest tests.test_face_pose_probe -v
git diff --check
```

随后按 `DEVECO_BUILD.md` 构建 Release HAP、发现产物并计算 SHA-256。Expected: 所有测试 PASS、`git diff --check` 无输出、HAP 非零且有 SHA-256；真机验收结果单独记录，不能由这些命令替代。

- [ ] **Step 6: 更新协作记录并提交 Phase 0 报告**

只更新 Codex 自己的任务行和 STATUS；显式暂存决策文档及协作文件。提交信息 `记录：完成人脸严格头姿技术探针`，尾行 `AI-Agent: codex`。不 push、不部署。

---

## Phase 0 停止条件

出现任一情况立即停止，不进入 Phase 1：

- 任一目标手机缺少 Core Vision/活体/比较 syscap，且没有经用户确认的本地替代模型。
- 任一目标手机无法稳定配置显示预览＋分析预览＋PhotoOutput，且替代 Surface 方案尚未单独确认。
- Core Vision 端到端 P95 高于分析周期，或 10 分钟测试出现不可接受的卡顿、温升、内存增长或相机泄漏。
- 活体 `mPixelMap` 无法可靠取得/释放，或换人场景能通过同人比较。
- 板端候选模型不满足许可证、转换、性能、误差或门禁一致性要求。
- 任何探针路径会把照片写入云端、服务器、数据库、日志或无法验证清理的目录。

Phase 0 得到 GO 后，再基于已冻结的 `CameraProbeCapability`、模型 ID、误差带和最终 JPEG 规范编写 Phase 1 实施计划；不在本计划里预先假设数据库/API/UI 的最终实现细节。
