# 第 25 章：造一个输出样式

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

本章创建一个自定义输出样式——改变 Claude 在终端中的回复格式。

---

## 输出样式系统

输出样式控制模型的回复风格。它通过 system prompt 的动态 section 注入指令：

```
getSystemPrompt()
  → getOutputStyleSection()
    → 从 settings.outputStyle 加载样式指令
    → 注入到 system prompt 的动态区
```

### 内置输出样式示例

Claude Code 有几种内置输出样式，通过 system prompt 指令控制：
- 默认样式：Markdown 格式，带代码块
- 简洁样式：更短的回复，更少的解释
- 详细样式：更全面的解释

---

## 创建自定义输出样式

### 方式 1：通过 CLAUDE.md

最简单的输出样式定制——在 CLAUDE.md 中添加指令：

```markdown
# CLAUDE.md

## 输出风格

回复时遵循以下规则：
- 每个回复以简短总结开头（一句话）
- 代码块总是包含文件路径注释
- 不要在代码块前写"这是修改后的代码"
- 使用表格对比方案时，总是包含"推荐"列
- 中文回复时，技术术语保留英文
```

### 方式 2：通过输出样式文件

创建输出样式配置文件：

```typescript
// .claude/output-styles/concise.md

# 输出样式：简洁模式

你正在简洁模式下运行。遵循以下规则：

1. 回复长度控制在 3-5 句话以内
2. 只在必要时使用代码块
3. 不解释你做了什么——直接做
4. 使用项目符号代替段落
5. 错误信息用加粗显示
```

然后在 settings.json 中启用：

```json
{
  "outputStyle": "concise"
}
```

### 方式 3：通过插件

输出样式可以作为插件组件分发：

```json
// plugin.json
{
  "name": "my-output-style",
  "version": "1.0.0",
  "outputStyles": ["styles/concise.md"]
}
```

---

## 输出样式注入点

输出样式在 system prompt 构建时注入：

```typescript
// → src/constants/prompts.ts（简化版）
// getOutputStyleSection() 从配置中读取样式指令
// 注入到 system prompt 的动态 section
systemPromptSection('output_style', () => getOutputStyleSection(settings))
```

---

## 检查点

- **输出样式系统**：通过 system prompt 的 `output_style` section 控制
- **三种方式**：CLAUDE.md 指令、样式文件、插件
- **生效时机**：每次 query 开始时加载
- **插件分发**：outputStyles 作为插件组件类型

**下一章**：第 26 章创建 PreToolUse Hook 检查脚本。
