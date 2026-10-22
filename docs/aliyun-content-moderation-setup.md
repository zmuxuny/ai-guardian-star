# 智护星低成本 AI 内容审核配置

本文采用方案一：本地急症规则、阿里云输入审核、Coze、阿里云输出审核、本地医疗输出规则。默认保持关闭；密钥、控制台规则和验收都完成后才启用。

## 一、成本与开通方式

只开按量付费，不购买资源包或 QPS。阿里云当前对 `llm_query_moderation` 和 `llm_response_moderation` 各按 15 元/万次计费；普通一轮对话调用两次，约 0.003 元，1000 轮约 3 元。只有 HTTP 200 的成功请求计费。

1. 主账号完成实名认证。
2. 打开 [内容安全增强版开通页](https://common-buy.aliyun.com/?commodityCode=lvwang_cip_public_cn)。
3. 接受按量付费协议，不购买资源包和 QPS 扩容。
4. 在费用与成本中设置月预算 10 元或 30 元，并设置 50%、80%、100% 告警。

官方价格和开通说明：[文本审核 PLUS 计费](https://help.aliyun.com/zh/document_detail/2671445.html)。

## 二、控制台规则

进入 `内容安全 / AI 安全护栏 → API 违规检测增强版 → 文本审核 → 规则配置`，分别配置：

- 大语言模型输入文字检测：`llm_query_moderation`
- 大语言模型生成文字检测：`llm_response_moderation`

首次使用保留官方默认阈值，色情、涉政、暴恐、违禁、不良、隐私、宗教、广告等检测保持开启。保存后等待 2 至 5 分钟生效。

本项目的处理规则：

- `high`：拦截。
- `medium`：当前没有人工复核队列，也拦截。
- `low`、`none`：继续处理。
- 输入审核返回 `Advice`：直接使用代答，不再调用 Coze。
- 审核服务超时或返回异常结构：关闭放行，不能把未审核内容返回客户端。

## 三、创建最小权限 RAM 用户

1. 在 RAM 控制台创建用户 `guardian-moderation-runtime`。
2. 关闭控制台登录，只允许 OpenAPI 调用。
3. 创建并绑定以下自定义策略，不使用主账号 AccessKey：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["yundun-greenweb:TextModerationPlus"],
      "Resource": "*"
    }
  ]
}
```

4. 为该用户创建 AccessKey。Secret 只显示一次，不要发到聊天、代码或 Git。
5. 在 AccessKey 网络访问策略中，只允许服务器固定公网 IPv4 `117.78.9.144`，不要使用 `0.0.0.0/0`。先确认服务器出口 IP 未变化再保存。

接口权限说明：[TextModerationPlus 授权信息](https://help.aliyun.com/zh/document_detail/2669858.html)。网络限制说明：[AccessKey 网络访问限制](https://help.aliyun.com/zh/ram/user-guide/accesskey-network-access-restriction-policy)。

## 四、服务器配置

仓库已提供官方 SDK 依赖、环境模板和 systemd drop-in。服务器首次配置：

```bash
python3 -m pip install -r /root/requirements-moderation.txt
install -d -m 700 /etc/wenxin
install -o root -g root -m 600 /root/aliyun-moderation.env.example /etc/wenxin/aliyun-moderation.env
install -d -m 755 /etc/systemd/system/wenxin.service.d
install -o root -g root -m 644 /root/aliyun-moderation.conf /etc/systemd/system/wenxin.service.d/aliyun-moderation.conf
systemctl daemon-reload
systemctl restart wenxin.service
```

编辑 `/etc/wenxin/aliyun-moderation.env`，只在服务器中填写两个密钥。首次仍保持：

```dotenv
ALIYUN_MODERATION_ENABLED=false
AI_RISK_CONTROL_READY=false
```

密钥和控制台规则完成后，先在测试环境改为 `true` 验收。全部通过后才在生产环境同时改为 `true`，再执行：

```bash
systemctl restart wenxin.service
systemctl is-active wenxin.service
curl -fsS http://127.0.0.1:8899/health
```

预期输出分别包含 `active` 和 `"status":"ok"`。若服务启动失败，立即把两项恢复为 `false` 并重启；不要删除原配置或把密钥打印到终端。

## 五、隐私与验收

医疗健康信息属于敏感个人信息。上线前需要在隐私说明中披露对话会由 Coze 和阿里云内容安全处理，并取得单独同意。服务端会在送审前遮蔽常见手机号、身份证号和邮箱；日志不得记录对话原文、风险词、AccessKey 或 Token。

至少验证：普通健康咨询、输入高/中风险、输出高/中风险、审核超时、Coze 超时、自伤求助、急症、要求自行停药或改剂量，以及日志中不存在测试身份信息。自伤或急症本地命中时不调用付费审核，直接提示联系可信任的人、120/110 和 12356。

法律依据：[个人信息保护法](https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm)。12356 说明：[国家卫健委通知](https://www.nhc.gov.cn/yzygj/c100068/202412/49a1a65386cd4be582d4702fd0926ee8.shtml)。
