# 快速澄清对照前历史状态

## 2026-11-27 · codex · T-20261127-03 · 模型预热门禁实现及真实板端验证完成

- 分支wip/codex-20261127-model-readiness，基于zy@8594dc2，独立于未合并PR #34；产品52aef7b先push后上传，V3不变。
- 新模块local_model_readiness、shared prepared_session、真实serve默认后台30秒预热+5秒探测，未就绪新提醒503不落库，重复/期限维持v5；调用失败撤ready并串行重试。
- 修复审查复现：等待追问pending仍可收明确求助；其重启应interrupted不重播。76本机/51板端回归及编译通过，复审通过。
- 两个冷模型进程/服务对象：19.220/18.895秒ready；每轮3脚本符合预期，只有模型辅助句3.937/3.866秒；共8实际尝试，规则耗时另计。
- 同一session/gate补充：只停止/重启实验模型，原worker23.905秒自动ready，后续模型辅助3.889秒；已有求助保留；7调用=warm3/probe2/class2。
- auto-01因审查指出恢复回调需重查保护/端口而主动TERM，exit1及清理保留；补guard后auto-02新目录重跑exit0，非资源保护触发；临时直连超时改既有中转，不改网络服务。
- 每轮62文件/1SQLite备份和17上传哈希核验；成功轮监控50/35样本，原PID2144/NRestarts0及62文件/单元不变，off、camera/MQTT/JPEG正常、端口关闭；生产未部署/重启。
- 产物docs/local-llm/model-readiness-2026-11-27.md及可重算合成证据；证据b917994，PR #35 https://github.com/zmuxuny/ai-guardian-star/pull/35；最终独立核验通过，CI见PR；无模型/DB/备份/图像/原始生产日志入库。
- 边界：recent ready不是永久健康保证，未观察到的外部模型重启仍可能先触发5秒兜底；旧demo保留直接后端对照，不当作serve门禁路径。
- 未验：长稳/任意输入五秒、真实个性化/care/App/语音/生成问候、物理断电断网和窗口外独立求助；既有V3理解限制保留。
- 下一步：新PR到zy、检查CI，不自行合并；之后真实模块/更多场景与长期验证另做。
