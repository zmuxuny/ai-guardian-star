# Contributing · 贡献指南

Thanks for your interest in AI Guardian Star. Please read this guide before opening a pull request.

感谢你关注并参与本项目。发起 Pull Request 前请先阅读本指南。

---

## English

### Workflow

1. Open an Issue first to describe the bug or the feature you plan to work on, so it can be discussed and scheduled.
2. Fork the repository and create a branch locally. Recommended naming: `feat/xxx`, `fix/xxx`, `docs/xxx`.
3. Open a pull request when the branch is ready. Describe the purpose of the change, the related Issue, and the test results.

### Commit conventions

- Write clear commit messages. Conventional Commits style is preferred, for example `feat: add MQTT client` or `fix: resolve crash on login`.
- Every pull request should include reasonable tests or reproduction steps.

Backend tests run with:

```bash
python -m unittest discover -v
```

CI additionally runs Python compilation checks and diff validation. HarmonyOS changes should be verified with a Release build in DevEco Studio and, where relevant, on a real device.

### Code style

- Follow the existing code style and lint rules of the module you are touching.
- Add unit tests and documentation when introducing a significant module.
- Never commit signing passwords, private keys, access keys, personal absolute paths, or production secrets.

### Other

- If a change affects licensing, third-party dependencies, or major architecture, confirm it through an Issue with the maintainers first.
- For large files (>50 MB), contact the maintainers about Git LFS or an alternative.
- Contributions are accepted under the [Apache License 2.0](LICENSE).

Security issues do **not** belong in a public Issue — see [SECURITY.md](SECURITY.md).

---

## 中文

### 贡献流程

1. 先在 Issues 中提交问题或功能请求，便于讨论与规划。
2. Fork 本仓库并在本地创建分支，分支命名建议使用 `feat/xxx`、`fix/xxx` 或 `docs/xxx`。
3. 在分支完成开发后发起 Pull Request，并在描述中写明变更目的、关联 Issue 和测试结果。

### 提交规范

- 使用清晰的提交信息，推荐 Conventional Commits 风格，例如 `feat: 添加新的 MQTT 客户端`、`fix: 修复崩溃问题`。
- 每个 PR 应包含合理的测试或复现步骤。

后端测试执行：

```bash
python -m unittest discover -v
```

CI 还会执行 Python 编译检查与 diff 校验。涉及 HarmonyOS 的改动应在 DevEco Studio 完成 Release 构建，必要时在真机验证。

### 代码风格

- 遵循所改模块已有的代码风格与 lint 规则。
- 新增重要模块时请补充对应的单元测试与文档说明。
- 签名密码、私钥、AccessKey、个人绝对路径和生产环境密钥一律不得提交。

### 其他

- 若变更涉及许可、第三方依赖或重大架构修改，请先通过 Issue 与维护者确认。
- 如需添加大文件（>50 MB），请联系维护者使用 Git LFS 或其他方案。
- 所有贡献均按 [Apache License 2.0](LICENSE) 授权。

安全问题请**不要**在公开 Issue 中提交，见 [SECURITY.md](SECURITY.md)。
