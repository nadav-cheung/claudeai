# 第 28 章：终章——集成实战

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

本章把 ch22-ch26 造的扩展集成在一起，跑通端到端流程。

---

## 集成目标

把以下扩展组合成一个完整的工作流：

1. **GitHubIssueTool**（ch22）：创建 Issue
2. **`/metrics` 命令**（ch23）：查看会话统计
3. **MCP 文件搜索**（ch24）：搜索代码
4. **简洁输出样式**（ch25）：控制回复格式
5. **敏感信息检查 Hook**（ch26）：保护密钥

---

## 端到端场景

```
用户：搜索代码中所有 TODO 注释，为每个 TODO 创建 GitHub Issue

Claude 的执行流程：
1. 调用 MCP search_files 工具搜索 "TODO"
2. 分析搜索结果，提取每个 TODO 的上下文
3. 对每个 TODO：
   a. 调用 GitHubIssueTool 创建 Issue（Hook 检查无敏感信息）
   b. 记录创建结果
4. 用简洁样式汇报结果

用户：/metrics
  → 显示工具调用统计
```

---

## 集成检查清单

### 1. 工具注册

```typescript
// src/tools.ts
import { GitHubIssueTool } from './tools/GitHubIssueTool/GitHubIssueTool.js'

export function getAllBaseTools(): Tools {
  return [
    // ... 内置工具
    GitHubIssueTool,       // ch22
    // MCP 工具由 assembleToolPool 自动合并  // ch24
  ]
}
```

### 2. 命令注册

```typescript
// src/commands.ts
import metricsCommand from './commands/metrics/index.js'

const COMMANDS = memoize(() => [
  // ... 现有命令
  metricsCommand,          // ch23
])
```

### 3. MCP 配置

```json
// .claude/settings.json
{
  "mcpServers": {
    "my-search": {
      "command": "npx",
      "args": ["-y", "@my-org/mcp-file-search"]
    }
  }
}
```

### 4. Hook 配置

```json
// .claude/settings.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [{
          "type": "command",
          "command": "node .claude/hooks/check-secrets.mjs"
        }]
      }
    ]
  }
}
```

### 5. 输出样式

```markdown
// CLAUDE.md
## 输出风格
- 回复控制在 3-5 句话
- 不解释做了什么——直接做
- 使用项目符号
```

---

## 集成测试

```bash
# 启动 Claude Code
claude

# 测试 1：MCP 搜索
> 搜索包含 "useEffect" 的文件

# 测试 2：创建 Issue
> 创建一个 issue，标题是"修复 useEffect 依赖警告"

# 测试 3：Hook 拦截
> 把 API key 写入 config.yml
# 期望：Hook 阻止，显示敏感信息警告

# 测试 4：统计
> /metrics
# 期望：显示工具调用次数和 token 使用量

# 测试 5：输出样式
> 解释 React useEffect 的清理函数
# 期望：简洁的 3-5 句回复
```

---

## 验证清单

| 检查项 | 通过？ |
|--------|-------|
| GitHubIssueTool 出现在工具列表 | ☐ |
| `/metrics` 命令可执行 | ☐ |
| MCP 服务器连接成功 | ☐ |
| Hook 在 Write 前触发 | ☐ |
| Hook 能阻止敏感信息写入 | ☐ |
| 输出样式影响回复格式 | ☐ |
| 多个扩展互不冲突 | ☐ |

---

## 常见集成问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 工具不出现 | 未在 getAllBaseTools 注册 | 检查 tools.ts |
| 命令不识别 | 未在 COMMANDS 数组 | 检查 commands.ts |
| MCP 连接失败 | 命令路径错误 | 检查 settings.json |
| Hook 不触发 | matcher 不匹配 | 检查 matcher 字段 |
| 样式不生效 | CLAUDE.md 未加载 | 检查文件位置 |

---

## 过渡桥：从建造到反思

卷三到此结束。你已经亲手造了 5 种扩展：

- **Tool**：GitHubIssueTool——Zod schema + buildTool + 注册
- **Command**：`/metrics`——local 类型 + 命令逻辑
- **MCP Client**：文件搜索——配置式接入
- **Output Style**：简洁模式——CLAUDE.md 指令
- **Hook**：敏感信息检查——stdin/stdout JSON 协议

建造过程中你一定产生了很多疑问：

- **为什么用 React 渲染终端，而不是直接写 ANSI？** （ch29）
- **为什么用 Zod 而不是 JSON Schema 验证工具输入？** （ch30）
- **为什么核心循环是一个巨大的 `async function*`？** （ch31）
- **为什么权限系统这么复杂？简单布尔检查不够吗？** （ch32）
- **为什么要自定义 Ink fork？** （ch33）
- **为什么工具执行是流式的？等模型说完再执行不行吗？** （ch34）
- **为什么用文件（CLAUDE.md）做配置，不用数据库？** （ch35）
- **这个架构的全景和边界在哪里？** （ch36）

卷四回答这些问题。每章围绕一个设计决策——源码中的证据、被否决的替代方案、今天的好处和麻烦、横向对比其他工具。

**卷三 → 卷四映射表**：

| 卷三你造了 | 产生的疑问 | 卷四回答 |
|-----------|----------|---------|
| 工具的 React UI | 为什么用 React 渲染终端？ | ch29 为什么用 Ink |
| Zod schema | 为什么用 Zod？ | ch30 为什么用 Zod |
| 整个扩展的集成 | 为什么 query.ts 是一个大函数？ | ch31 为什么大 query |
| 权限检查 | 为什么分层？ | ch32 为什么分层权限 |
| 工具的终端显示 | 为什么自定义 Ink fork？ | ch33 为什么自定义 fork |
| 工具的流式执行 | 为什么流式？ | ch34 为什么流式 |
| CLAUDE.md 配置 | 为什么用文件？ | ch35 为什么文件配置 |
| 全部 | 架构全景 | ch36 全景与边界 |

---

## 检查点

- **集成流程**：注册 → 配置 → 测试 → 验证
- **注册点**：tools.ts（工具）、commands.ts（命令）、settings.json（MCP/Hook/样式）
- **验证清单**：7 项检查确保所有扩展正常工作
- **常见问题**：未注册、路径错误、matcher 不匹配
- **过渡桥**：从"怎么造"到"为什么这样设计"——卷四回答设计决策问题
