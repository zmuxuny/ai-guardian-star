# 人脸姓名录入页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将个人页“人脸信息”的旧弹窗替换为“姓名填写 → 应用内人脸取景”的两步采集页。

**Architecture:** 新增纯 ArkTS 姓名/步骤模块和 `FaceEnrollment` 导航页；个人页只负责跳转。第二步使用 CameraKit + XComponent 实时预览，白色离屏混合遮罩只露出椭圆人脸区域，拍摄 JPEG 仅在内存中交给现有上传接口。

**Tech Stack:** HarmonyOS ArkTS、Navigation router map、Hypium、CameraKit、XComponent

**Spec:** `docs/superpowers/specs/2026-11-03-face-vector-enrollment-design.md`

## Global Constraints

- 姓名必填，并拒绝全空格、超过 64 字符、路径字符和控制字符。
- 页面继承 `Profile`、`MyAddress` 的顶部返回结构、背景、圆角、颜色与深色模式。
- 底部主按钮高度至少 44vp；姓名无效或正在处理时不可提交。
- 照片不写 App 临时文件；CameraKit 回调复制到内存后直接交给上传接口。
- 本次实现应用内取景和遮罩，不实现三照片预览确认、实时头姿接线、活体或向量协议。

## Review Focus

- 纯空白姓名不能启用拍摄，并显示可恢复的就地提示。
- 64 字符边界可接受，65 字符必须拒绝。
- `/`、`\\`、NUL 和其他控制字符不能进入服务端路径。
- 相机退出或页面消失时释放 Session、Input 和 Output。
- 键盘显示时姓名字段保持在可滚动内容中，返回键优先收起输入焦点。

---

### Task 1: 姓名校验规则

**Files:**
- Create: `entry/src/main/ets/face/FaceEnrollmentName.ets`
- Modify: `entry/src/test/LocalUnit.test.ets`

**Interfaces:**
- Produces: `validateFaceEnrollmentName(value: string): FaceEnrollmentNameValidation`
- Produces: `normalizeFaceEnrollmentName(value: string): string`

- [ ] **Step 1: Write the failing test** covering valid trimmed input, whitespace-only, 64/65 character boundary, path characters, and control characters.
- [ ] **Step 2: Run the local unit build and verify it fails because the module does not exist.**
- [ ] **Step 3: Implement the validator with server-compatible limits and user-facing recovery messages.**
- [ ] **Step 4: Run the local unit build and verify it passes.**

### Task 2: 独立录入页与导航

**Files:**
- Create: `entry/src/main/ets/pages/FaceEnrollment.ets`
- Modify: `entry/src/main/ets/pages/person.ets`
- Modify: `entry/src/main/resources/base/profile/route_map.json`

**Interfaces:**
- Consumes: `validateFaceEnrollmentName` and `normalizeFaceEnrollmentName` from Task 1.
- Produces: route `FaceEnrollment` via `FaceEnrollmentBuilder()`.

- [ ] **Step 1: Add a navigation/interaction acceptance test that opens the route and verifies invalid names cannot start capture.**
- [ ] **Step 2: Run it and verify the old dialog path fails the acceptance expectation.**
- [ ] **Step 3: Add the new page, route registration, and `pushPathByName('FaceEnrollment', null)` entry behavior.**
- [x] **Step 4: Replace CameraPicker with CameraKit preview, white oval mask, and in-memory capture.**
- [x] **Step 5: Build the release HAP and run the focused unit tests.**

### Task 3: 真机验收与协作记录

**Files:**
- Modify: `docs/修改记录/协作/STATUS-codex.md`
- Modify: `docs/修改记录/协作/TASKS.md`

**Interfaces:**
- Consumes: signed installable HAP and the already connected single device.

- [ ] **Step 1: Confirm the device is connected and install the newest signed HAP.**
- [ ] **Step 2: Verify “人脸信息” opens the independent page, invalid name blocks capture, and a valid name enables “开始拍摄”.**
- [ ] **Step 3: Record build/device evidence and remaining unimplemented Phase 0/Phase 1 items.**
