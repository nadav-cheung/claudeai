# 19 - 向 Claude Code 贡献代码

> **本章目标**：学会如何向 Claude Code 开源项目贡献代码，了解 GitHub 工作流和提交流范。

---

## 1. 准备工作

### 1.1 Fork 仓库

```bash
# 1. 在 GitHub 上 Fork claude-code 仓库
# https://github.com/anthropics/claude-code

# 2. 克隆你的 Fork
git clone https://github.com/YOUR_USERNAME/claude-code.git
cd claude-code

# 3. 添加上游仓库
git remote add upstream https://github.com/anthropics/claude-code.git

# 4. 验证
git remote -v
# origin    https://github.com/YOUR_USERNAME/claude-code.git (fetch)
# origin    https://github.com/YOUR_USERNAME/claude-code.git (push)
# upstream  https://github.com/anthropics/claude-code.git (fetch)
# upstream  https://github.com/anthropics/claude-code.git (push)
```

### 1.2 保持同步

```bash
# 1. 切换到 main 分支
git checkout main

# 2. 拉取上游更新
git fetch upstream
git merge upstream/main

# 3. 推送更新到你的 Fork
git push origin main
```

---

## 2. 开发流程

### 2.1 创建功能分支

```bash
# 基于最新的 main 创建分支
git checkout -b feature/add-new-tool

# 分支命名规范
# feature/xxx - 新功能
# fix/xxx - Bug 修复
# docs/xxx - 文档更新
# refactor/xxx - 重构
```

### 2.2 开发步骤

```
1. 在本地开发
   │
2. 频繁提交（每完成一个小功能就提交）
   │
3. 写清晰的提交信息
   │
4. 测试你的修改
   │
5. Push 到你的 Fork
   │
6. 在 GitHub 上创建 Pull Request
```

---

## 3. 提交信息规范

### 3.1 格式

```
<type>: <简短描述>

[可选的详细描述]

[可选的 Footer]
```

### 3.2 Type 类型

| Type | 用途 | 示例 |
|------|------|------|
| feat | 新功能 | `feat: 添加 TodoWriteTool` |
| fix | Bug 修复 | `fix: 修复权限检查 bug` |
| docs | 文档 | `docs: 更新 README` |
| style | 代码格式 | `style: 格式化代码` |
| refactor | 重构 | `refactor: 简化工具注册` |
| test | 测试 | `test: 添加工具测试` |
| chore | 构建 | `chore: 更新依赖` |

### 3.3 示例

```
feat: 添加 Git MCP 服务器支持

实现了对 Git MCP 服务器的完整支持，包括：
- ListBranchesTool
- CreateBranchTool
- CommitTool

Closes #123
```

---

## 4. Pull Request 流程

### 4.1 创建 PR

```bash
# 1. Push 到你的 Fork
git push origin feature/add-new-tool

# 2. 在 GitHub 上创建 PR
# 或者使用 GitHub CLI
gh pr create --title "feat: 添加新工具" --body "
## 描述
添加了一个新工具...

## 测试
- [ ] 测试了工具执行
- [ ] 测试了错误处理
"
```

### 4.2 PR 描述模板

```markdown
## Summary
<!-- 简短描述修改内容 -->

## Test plan
<!-- 如何测试这个修改 -->

## Checklist
- [ ] 代码符合项目规范
- [ ] 添加了测试（如有需要）
- [ ] 更新了文档（如有需要）
- [ ] 所有测试通过

## Screenshots (如有 UI 修改)
<!-- UI 截图 -->
```

---

## 5. 代码审查

### 5.1 审查要点

**代码审查时关注**：
1. **功能正确性** - 代码是否做了它应该做的？
2. **边界情况** - 错误处理是否完善？
3. **性能** - 有没有性能问题？
4. **可读性** - 代码是否清晰易懂？
5. **测试** - 是否有足够的测试？

### 5.2 常见反馈

```
// 反馈类型
[nitpick] - 小建议，非阻塞
[suggestion] - 建议改进
[question] - 需要澄清
[issue] - 阻塞性问题，需要修复
[praise] - 好的做法！
```

---

## 6. 贡献类型

### 6.1 文档贡献

```markdown
# 文档修改不需要太多流程

# 1. 直接在 GitHub 上编辑
# 2. 或克隆后修改
git checkout -b docs/fix-typo
# 修改后提交
git push origin docs/fix-typo
```

### 6.2 代码贡献

```markdown
# 需要更多测试和验证

# 1. 确保代码符合项目风格
# 2. 添加测试
# 3. 运行所有测试
npm test

# 4. 提交并创建 PR
```

### 6.3 Bug 修复

```markdown
# 修复 Bug 时

# 1. 描述问题
# 2. 描述解决方案
# 3. 添加测试防止回归
# 4. 引用相关 Issue
Closes #123
```

---

## 7. 实战练习

### 7.1 练习：修复一个文档错误

**任务**：在 GitHub 上找到 README 的一个错误并修复

**步骤**：
1. Fork 仓库
2. 创建一个 `docs/fix-xxx` 分支
3. 修复错误
4. 提交并创建 PR

### 7.2 练习：添加一个测试

**任务**：为 Mini-Claude 添加测试

**步骤**：
1. 创建测试文件
2. 运行测试确保通过
3. 提交并创建 PR

---

## 8. 总结

| 步骤 | 命令 |
|------|------|
| Fork | GitHub 页面操作 |
| 克隆 | `git clone` |
| 创建分支 | `git checkout -b` |
| 提交 | `git commit` |
| 推送 | `git push` |
| 创建 PR | `gh pr create` |

---

## 下一篇

👉 [20 - 构建你的第一个插件](20-building-first-plugin.md) —— 实战：构建一个真实的插件

`★ Insight ─────────────────────────────────────`
开源贡献不只是写代码，还包括**代码审查**。当你提交 PR 时，保持开放心态接受反馈；当别人提交 PR 时，积极提供建设性的意见。好的开源社区是双向的——每个人都在帮助每个人变得更好。
`─────────────────────────────────────────────────`
