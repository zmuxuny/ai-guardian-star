# 晚起提醒的本机 HTTP 联调

步骤 3 使用 Python 标准库，沿用 [v5 消息格式](personalization-message-format.md) 和 `schema_version: "2"`。当前演示使用模拟文字问候和预设回答。

## 重复运行

在个性化分支的仓库目录运行。

```powershell
python -m tools.personalization_http_demo
python -m unittest discover -s tests -p "test_personalization_http.py" -v
```

默认使用临时数据库。指定新的输出目录可保留模拟作息 CSV、每个场景的 `personalization.sqlite3` 和 `model.sqlite3`。

```powershell
python -m tools.personalization_http_demo --output-dir .tmp/late-wakeup-http
```

两端共用 2026-11-24 的回放时钟。演示会实际向环回 HTTP 端口发请求，按场景推进模拟时间。

| 场景 | 检查项 |
| --- | --- |
| `ok` 和 `needs_help` | 收到版本 1，待处置分别为 0 和 1 |
| 重复提醒和重复结果 | 返回 `duplicate`，问候和待处置均只登记一次 |
| 提醒和结果回执丢失 | 接收方保存后断开 HTTP 连接，发送方在 5 秒补发点重发原载荷 |
| 模型发送进程重启 | 新进程打开同一 SQLite，补发同一 `event_id`、版本和时间 |
| 结果版本乱序 | 版本 2 的求助先到，版本 1 后到，保留历史并继续以版本 2 为当前结果 |

个性化端的 `results` 表留存各版本，`help_tasks` 按事件保存一条待处置。两端的 `outbox` 表保存发件载荷、尝试次数、待重试时间和失败原因。演示保留这些记录，补发按 v5 截止时间停止。模拟模式未接入音频、真实分类模型或独立求助入口。

## 接入独立模型进程

在同一台电脑启动提供 `POST /personalization/v2/reminders` 的模型服务，让它向个性化端的 `POST /personalization/v2/results` 回传结果。下面是示例端口，双方使用同一设备 ID。

```powershell
python -m tools.personalization_http_demo peer --model-port 8766 --results-port 8765 --db personalization.sqlite3 --device-id demo-device --send-sample
```

`--send-sample` 以内置模拟提醒开启一轮，时间戳使用本机当前时间，便于和独立模型共用时钟。用同一个数据库重启个性化端时，去掉该参数即可恢复待发送记录并继续接收结果。收到结果时，终端会输出当前版本、历史和待处置数量。按 Ctrl+C 结束进程。
