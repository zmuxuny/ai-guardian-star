# 个性化交付包查看前历史状态

## 2026-11-28 · codex · T-20261128-02 · fast与v5文字服务及门禁整合实测完成

- 用户要求继续上一轮下一步；分支wip/codex-20261128-fast-v5-integration，依赖PR #37；产品a275f4c、证据补全57a9f3b均先push后上传。
- 共享prepared_session/serve显式policy=v4-fast，默认v3保持；新增5回归先失败后通过、138相关回归通过；补1证据回归先失败，修复后6专项及57板端回归通过。
- 新目录两轮均备份62文件/1SQLite、核对19上传哈希；首轮功能exit0但故障决策导出缺口保留于first-run，补齐后第二轮新目录重跑exit0，不覆盖。
- 最终5评分场景符合预期；否认同句两次/2问候零模型分类，0.108秒回unclear；独立规则求助保持，弱求助4.661秒真实模型回needs_help。
- 故障另列：连接失败202后撤ready，新提醒503且不入库，已有规则求助0.024秒回传并保留；同Session/gate/worker24.036秒自动ready，恢复后真实模型3.966秒。
- 整轮rule5/model_advisory2/fallback1；warm3/probe2/class3=8客户端尝试（class含1故障），4个求助任务/无待发；独立重算与19哈希终审无阻断。
- 36资源样本，正式17/均值7.565FPS，最低可用13.576GiB；PID2259/NRestarts0、62文件/unit不变，off/相机/MQTT/JPEG正常，最终7.5及独立回读7.6FPS，模型端口关闭。
- 证据ee27da2；报告docs/local-llm/fast-v5-integration-2026-11-28.md及结构化材料；PR #38 https://github.com/zmuxuny/ai-guardian-star/pull/38，最终CI见PR。不含模型/DB/备份/真实音视频/原始生产日志，生产未部署/切默认。
- 下一步：PR #38交付zy并等待最终CI，不自动合并；真实个性化接收端/参数确认后联调，care/App/生成问候/语音/物理断电断网/窗口外求助/长稳另验。
