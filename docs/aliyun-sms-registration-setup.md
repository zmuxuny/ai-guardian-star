# 阿里云短信验证码注册配置

本项目选择阿里云「号码认证服务」中的「短信认证」，不是内容安全，也不是普通「短信服务 SMS」。个人实名认证开发者可直接使用系统赠送签名和模板，无需企业营业执照；当前中国内地号码按量低用量价格约为 `0.06 元/次`，核验不收费。

代码已提供：

- `POST /api/otp/send`：发送注册验证码。
- `POST /api/register`：核验验证码、创建账号并返回登录会话。
- 本地手机号/IP 频控、5 分钟有效期、最多 5 次核验、一次性消费。
- 新注册密码至少 8 位；历史账号仍可按原规则登录。
- 服务端只保存随机挑战值的 SHA-256，不生成或保存明文验证码。

在以下配置全部完成前，生产环境必须保持 `ALIYUN_SMS_ENABLED=false`。

## 需要在阿里云完成

1. 打开[号码认证服务控制台](https://dypns.console.aliyun.com/)，开通「短信认证」。
2. 在「短信认证参数配置」中选择控制台当前提供的赠送签名。
3. 选择赠送的登录/注册模板，模板 Code 通常为 `100001`；以控制台实际显示为准。赠送签名必须搭配赠送模板。
4. 绑定测试手机号，在控制台快速测试中分别跑通发送和核验。
5. 新建仅用于短信的 RAM 用户，例如 `guardian-sms`：只启用永久 AccessKey API 访问，不启用控制台登录。
6. 给该 RAM 用户创建并授权以下最小权限策略：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dypns:SendSmsVerifyCode",
        "dypns:CheckSmsVerifyCode"
      ],
      "Resource": "*"
    }
  ]
}
```

参考：[个人开发者接入说明](https://help.aliyun.com/zh/pnvs/use-cases/sms-verify-for-individual-developers)、[发送接口与权限](https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-sendsmsverifycode)、[核验接口与权限](https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-checksmsverifycode)、[当前计费](https://help.aliyun.com/zh/pnvs/product-overview/product-pricing/)。

> 赠送签名可能调整，不要照抄旧名称。请把控制台当前显示的签名名称发给维护者。AccessKey 不要发到聊天、截图或仓库。

## 服务器配置

安装 SDK：

```bash
python3 -m pip install -r /root/caringSystem/requirements-sms.txt
```

在仓库根目录执行以下命令，安装环境文件和 systemd drop-in：

```bash
install -d -m 700 /etc/wenxin
install -m 600 deploy/aliyun-sms.env.example /etc/wenxin/aliyun-sms.env
install -d -m 755 /etc/systemd/system/wenxin.service.d
install -m 644 deploy/wenxin.service.d/aliyun-sms.conf \
  /etc/systemd/system/wenxin.service.d/aliyun-sms.conf
```

然后编辑 `/etc/wenxin/aliyun-sms.env`：

```dotenv
ALIYUN_SMS_ENABLED=false
ALIBABA_CLOUD_SMS_ACCESS_KEY_ID=<短信专用 RAM AccessKey ID>
ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET=<短信专用 RAM AccessKey Secret>
ALIYUN_SMS_SIGN_NAME=<控制台当前赠送签名>
ALIYUN_SMS_TEMPLATE_CODE=100001
ALIYUN_SMS_SCHEME_NAME=guardian-register
ALIYUN_SMS_DAILY_LIMIT=100
```

再设置权限并加载 systemd drop-in：

```bash
chmod 600 /etc/wenxin/aliyun-sms.env
systemctl daemon-reload
systemctl restart wenxin.service
systemctl is-active wenxin.service
```

先保持关闭并确认服务正常。完成阿里云控制台测试后，将 `ALIYUN_SMS_ENABLED` 改为 `true`，重启服务，再通过 App 完成一次真实注册。

## 验收标准

- 同一手机号 60 秒内重复发送被拒绝。
- 验证码 5 分钟后失效，错误 5 次后失效，成功后不能重复使用。
- 注册成功后可直接进入应用，再退出；退出后必须重新登录。
- 服务器数据库中存在新用户，但不存在明文密码或明文验证码。
- 阿里云控制台能看到对应发送记录与费用。
