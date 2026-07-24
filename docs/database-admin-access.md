# 数据库可视化管理

生产服务继续使用轻量的 SQLite 数据库。项目自带 `Guardian DB Admin`，目前已在服务器启用，但 Nginx 会对公网 `/admin` 固定返回 `404`；管理页面只能通过 SSH 加密隧道访问。

## 打开管理页面

在 Windows PowerShell 执行并保持窗口打开：

```powershell
ssh -N -L 18899:127.0.0.1:8899 -p 22 root@117.78.9.144
```

然后在浏览器打开：

```text
http://127.0.0.1:18899/admin
```

管理密码保存在服务器的 `/etc/wenxin/admin.env`，不会写入仓库。需要复制密码时，另开一个 PowerShell 窗口执行：

```powershell
$adminPassword = ssh -p 22 root@117.78.9.144 "sed -n 's/^ADMIN_PASSWORD=//p' /etc/wenxin/admin.env"
$adminPassword | Set-Clipboard
```

粘贴登录后，可查询、搜索、编辑和删除用户。编辑用户名或删除用户会同时撤销该用户的服务端会话。

## 安全边界

- 不要把 `/admin` 暴露到公网，也不要开放公网 `8899`。
- 后台不显示或直接修改密码；注册用户应优先走短信验证码流程。
- 当前后台没有 MFA、RBAC 和完整审计，仅适合项目阶段的受限运维。
- SQLite 文件与管理环境文件权限均应保持 `600`。
- 如需任意 SQL 或多库管理，再考虑只监听回环地址的只读工具；当前两个业务表不值得部署 CloudBeaver。

## 连接异常

- PowerShell 窗口关闭后，SSH 隧道会一并关闭，这是正常现象。
- 本地 `18899` 被占用时，可把命令和浏览器地址中的 `18899` 同时换成其他未占用端口。
- 公网访问 `https://api.aistar.asia/admin` 返回 `404` 是预期的安全行为。
