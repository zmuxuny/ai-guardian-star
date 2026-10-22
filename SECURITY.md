# Security Policy · 安全报告

## English

### Reporting a vulnerability

Please do **not** disclose a suspected vulnerability in a public Issue.

**Preferred:** report privately through a GitHub Security Advisory.

1. Go to the repository `Security` → `Advisories` → `New draft security advisory`.
2. Describe the vulnerability, its impact, and the steps to reproduce it.
3. Once submitted, the report is visible only to the repository maintainers.

**Fallback:** open an Issue with `[SECURITY]` in the title. It will be moved to a private discussion immediately, so keep sensitive details out of the initial text.

### What to expect

Reports are acknowledged within three business days. A security update is published once a fix is available. Vulnerabilities in third-party dependencies are tracked upstream in parallel.

### Supported versions

The latest published release and the `main` branch receive security fixes. Older prereleases do not.

### Secrets and configuration

Cloud credentials (API tokens, access keys, admin passwords, Flask secret key) are injected through server environment variables only. They must never be embedded in the application or committed to the repository. If a credential is exposed, rotate it before filing the report.

---

## 中文

### 漏洞报告

如果你发现本项目存在安全漏洞，请**不要**在公开 Issue 中披露。

**推荐方式：** 使用 GitHub Security Advisory 私下报告。

1. 进入仓库 `Security` → `Advisories` → `New draft security advisory`。
2. 填写漏洞描述、影响范围和复现步骤。
3. 提交后仅仓库维护者可见。

**备用方式：** 通过 Issue 标题标注 `[SECURITY]`，我们会立即转为私有讨论；首次提交时请不要写入敏感细节。

### 处理时效

我们会在收到报告后 3 个工作日内确认，并在修复后发布安全更新。涉及第三方依赖的漏洞将同步跟进上游。

### 支持范围

最新已发布版本与 `main` 分支提供安全修复，更早的预发布版本不再维护。

### 密钥与配置

云端凭据（API Token、AccessKey、管理密码、Flask Secret Key）只通过服务器环境变量注入，不得写入 App 或提交到仓库。若凭据已经泄露，请先轮换再提交报告。
