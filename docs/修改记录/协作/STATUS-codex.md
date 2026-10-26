# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

## 2026-10-26 20:17 · codex · T-20261026-02 · 待验证

> 分支：`wip/deepseek-20261026-recording-day-lazy` @ `0b3da26` · 基于：`zy@920b038`
> 下一步：在兼容云端部署后做模拟器按日展开、下载和七天边界端到端验收；验收前不合入 `zy`。

### 目标

修复评审发现的日期窗口越界和云端/本地回退状态码不一致，保持七天滚动留存语义。

### 改动

- `board_recording_bridge.py` — 事件严格限制在请求日窗口；合法但已过期窗口返回空快照。
- `recording_api.py` — 本地回退按请求窗口、留存窗口与 `asOf` 的交集过滤。
- `tests/test_continuous_board_bridge.py` — 增加跨日、未来、过期及 query/media × board/local 状态码回归测试。

### 验证

- `python -m unittest tests.test_continuous_board_bridge -v`：27/27 通过。
- `python -m py_compile board_recording_bridge.py recording_api.py`：通过。
- release HAP：BUILD SUCCESSFUL；24,377,390 字节；SHA-256 `D6E15541…1EC83`；未签名。
- 模拟器：未签名 HAP 安装成功，冷启动进入前台；未连接兼容云端做下载验收。

### 未验证 / 风险

- 未部署云端、未重启服务；未用兼容后端完成模拟器/真机界面与下载验收。
- App 刷新保留旧日期缓存的行为属于非阻塞项，后续端到端验收时复核。

### 回滚

- 仅回退 Codex 两次修复：依次 `git revert 0b3da26 a6c2561`。

## 2026-10-25 15:18 · codex · T-20261025-10 · 已完成

> 分支：`zy` @ `9c4fef1` · 生产源码：SHA-256 `77b2dde…91ddc`
> 下一步：T-20261025-11 由未登记人员出镜，验证稳定显示陌生人且不误认成 `Hjb`/`zy`。

### 目标

为已确认身份 `zy` 安全追加一张不同方向照片，不降低阈值，不污染 `Hjb` 图库。

### 改动

- 板端图库 — `zy` 从 1 张增为 2 张；`Hjb` 未改，照片、数据库和凭据未入 Git。
- `docs/修改记录/2026-10-25-人脸图库多尺度特征优化.md` — 记录备份、候选分数、登记结果和未完成验收。

### 验证

- 补样前备份：`/root/ai_guardian-backups/20261025T064504Z-zy-second-photo-pre`。
- 正式 NPU 复核：`zy=0.545848`、`Hjb=0.083506`、间隔 `0.462342`；接口返回 `ready`、`photo_count=2`。
- 本地人脸识别、策略、质量/超时、登记回归：58 项通过。
- 服务 `active`、`NRestarts=0`、摄像头在线，实时约 5.7～6.8 fps。
- 移开手机后连续约 40 秒采样 20 次，20/20 均为 `known:zy`，分数 `0.555967～0.605150`。

### 未验证 / 风险

- 严重低头或手机遮住鼻嘴和一只眼时仍为 `stranger`；未把遮挡图写入图库。
- 没有真实未登记人员出镜；T-20261025-11 仍待验证，不能声称陌生人不误认已经完成真机验收。

### 回滚

- 数据回退使用上述板端备份；恢复会覆盖后续登记，必须再次获得用户明确要求。
