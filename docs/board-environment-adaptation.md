# 现有板端Python3.9与平铺部署适配

目标：复用已运行的Python3.9.2、CANN7.0.0、模型、平铺目录、start.sh和systemd服务；不升级原Conda、OpenCV、NumPy、FastAPI或音视频组件。适配完成后默认关闭关怀，不授权live，也不等于此前六步验收全部通过。

## 改动与证据边界

- `sedentary_care.Config` 两个PEP604注解改为Optional[time]，默认值、计时、静默和提醒规则不改。
- `run_shadow_scenarios` 改用open(newline=...)导出，兼容3.9且保持UTF-8/换行协议。
- 新增 `tools/care_flat_release.py`，不改变原严格src布局安装器。打包时以2499d1d进行三方合并：设备入口+已验证的新功能入口，冲突或丢失必要函数就拒绝。设备现有video_feed时间戳与采集时间戳增强必须保留。
- 平铺包固定16文件：11个新增关怀模块、4个邻近migrations/local_care SQL、1个合并入口。只有入口可替换既有文件，其他模块必须原本不存在。6个原辅助依赖逐个对照基线指纹，漂移拒绝覆盖；不包含SDK、模型、start.sh、原服务unit、私有配置或数据库。
- 安装与回退必须停止服务、同一设备单进程串行执行；不支持并发安装/回退。安装器本身不启停服务、不设置模式、不迁移/降级数据。
- 首先完成全量检查和私有备份，再写不可重写的回退清单；按随机nonce独占创建临时文件、写入同步后原子替换，入口最后安装。写入中断也能依据已保存清单清理本次不完整临时文件。
- 回退先把旧入口恢复到随机临时文件，指纹核对/同步后原子替换，再移除本次新增文件；回退中断可重试。部署后有独立改动时拒绝覆盖。数据库永不由此工具回滚或删除。

设备专项验证使用原解释器及现有生产依赖，HTTPX等仅供TestClient使用的纯Python包放在私有staging/test-deps，通过该测试进程的PYTHONPATH加载，没有pip install进原Conda。此目录不写入服务环境。专项输入全部为模拟；FAKE NOT VIDEO仍然不构成真实MP4播放证据。

## 操作顺序

1. 私有备份原入口、代码、配置和SQLite一致性快照，核对可读性/指纹。先记录原解释器、SDK、模型与启动脚本，不修改它们。
2. 从设备取实际入口到本机被忽略的私有目录，审查与基线差异；不要把设备入口或含其内容的包提交公开仓库。
3. 在已提交、干净的源码工作区运行：

```powershell
python tools/care_flat_release.py pack --device-entry .tmp/private-device-entry.py --bundle .tmp/care-flat.zip
```

4. 将包及 `tools/care_flat_release.py`、其复用的 `tools/care_release.py` 放到设备私有staging目录；不覆盖原工具目录。用原服务解释器先在隔离临时应用目录演练check/apply/rollback，再对真实APP_ROOT只做check。
5. 以下命令在板端执行，BOARD_PYTHON/APP_ROOT/STAGING/BACKUP由设备私有部署记录提供，不能误指向新环境或云端：

```sh
"$BOARD_PYTHON" "$STAGING/tools/care_flat_release.py" check --bundle "$STAGING/care-flat.zip" --app-root "$APP_ROOT"
systemctl stop guardian-board.service
"$BOARD_PYTHON" "$STAGING/tools/care_flat_release.py" apply --bundle "$STAGING/care-flat.zip" --app-root "$APP_ROOT" --backup "$BACKUP"
systemctl start guardian-board.service
```

任何安装错误都保持服务停止；如已产生有效backup.json，用下一节回退，再启动旧服务。不能失败后仍无条件启动半安装版本。
6. 不设置AI_GUARDIAN_CARE_CONFIG，保持默认off；复核原解释器、模型、start.sh、unit和配置指纹；确认服务、摄像头、推理与实时画面恢复。新care接口在off下未注册是预期，不能据此判API故障。
7. 只有第1步部署准入通过，才能继续原验收清单第2步；shadow需要后续受控私有配置，不能因这次模拟测试通过直接启用live。第3–6步仍按顺序门禁。

## 回退

```sh
systemctl stop guardian-board.service
"$BOARD_PYTHON" "$STAGING/tools/care_flat_release.py" rollback --app-root "$APP_ROOT" --backup "$BACKUP"
systemctl start guardian-board.service
```

恢复目标是本次安装前的设备原始字节（包含独立视频增强），不是用仓库2499d1d整文件覆盖。备份清单必须保留；安装或回退中断后使用同一份备份重试，不创建第二份覆盖它。仅在服务停止且没有其他写入者时操作。回退后复验摄像头、原模型推理、画面时间戳、录像/对讲相关接口和配置；这次仅隔离演练不自动代表正式第6步已通过。

## 一键回归

本机原验证环境执行 `python -m unittest discover -v`；新增9项 `test_board_environment` 覆盖合并保留、指纹/包篡改、已有模块拒写、安装中断/部分写入、回退中断重试、数据库保留及导入。板端原解释器在私有隔离目录运行：

```sh
PYTHONPATH="$STAGING/test-deps" "$BOARD_PYTHON" -m unittest test_board_environment.PythonCompatibilityTests test_sedentary_care test_local_care_store test_shadow_mode test_region_aggregation test_shadow_scenarios test_weekly_report test_care_delivery -v
```

本轮101项原解释器专项已通过；部署后实测记录另记在协作STATUS/验收续记中，不改写第一次失败的历史记录。
