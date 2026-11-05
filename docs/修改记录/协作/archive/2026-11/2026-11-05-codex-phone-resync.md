# 手机重同步归档

## 2026-11-05 · codex · T-20261105-06 · 已完成

> 分支：`wip/codex-20261105-zy-app-sync@cd7e6f7`；将与模拟器一致的最新 zy 签名 HAP 覆盖同步到 USB 手机，安装和启动成功。
> 下一步：用户在手机登录后从个人/人脸信息检查新流程；相机授权、姿态采集、上传与真实设备链路尚未验收。

- 手机 MIA-AL00/nova 14 Pro（API 26），明确使用 USB 目标；未操作模拟器，未卸载或清数据。
- HAP SHA-256 `553D7101112155E483F4E8C6B3948DED130E097491ED6DD90C2E36D238936B59`，24,686,693 B；源码和包未变，复用此前成功构建，不重复构建或测试。
- 覆盖安装返回 install bundle successfully；EntryAbility 返回 start ability successfully，当前可达登录页，进程存在，按进程读取日志无 FATAL/JS_ERROR/Unhandled 标记。
- 本地布局 `.tmp/phone-validation-20261105/resync-layout.json` 被忽略；未截取个人资料，未登录、授权相机/麦克风或上传数据。
- 保留现有四处本机改动；仅本地协作记录提交，未 push 或部署服务器/开发板。
