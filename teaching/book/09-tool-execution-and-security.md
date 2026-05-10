# 09 - 工具执行与安全

> **本章目标**：深入理解 Claude Code 如何安全地执行工具，包括权限检查、危险命令检测、输出截断等安全机制。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/services/tools/toolExecution.ts` - 工具执行引擎
- `src/tools/BashTool/` - Shell 执行工具

### 1.2 本章与 Mini-Claude 的关系

| Mini-Claude | Claude Code |
|-------------|-------------|
| 直接 `exec()` | 沙箱 + 权限检查 |
| 无超时控制 | 超时 + 资源限制 |
| 无危险检测 | 命令黑名单 |

---

## 2. 安全执行模型

### 2.1 Mini-Claude 的简单执行

```typescript
// Mini-Claude: 直接执行，无安全防护
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

async function execute(command: string) {
  // 任何命令都能执行 - 有安全风险
  const { stdout } = await execAsync(command);
  return stdout;
}
```

### 2.2 Claude Code 的多层防护

```
┌─────────────────────────────────────────────────────┐
│                 Claude Code 安全模型                  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  1. 工具级别权限检查                                 │
│     └── 用户是否允许此工具？                          │
│                                                     │
│  2. 参数级别验证                                    │
│     └── Schema 校验 + 白名单                         │
│                                                     │
│  3. 执行时危险命令检测                               │
│     └── rm -rf, 管道注入, ; 分号注入                 │
│                                                     │
│  4. 资源限制                                        │
│     └── 超时、内存、输出大小                          │
│                                                     │
│  5. 沙箱隔离（可选）                                 │
│     └── Docker / gVisor                            │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 3. 权限检查机制

### 3.1 Claude Code 的权限钩子

```typescript
// services/tools/toolExecution.ts (简化)
export async function executeTool(
  toolName: string,
  args: unknown,
  context: ToolContext
): Promise<ToolResult> {
  // 1. 获取工具定义
  const tool = tools.get(toolName);
  if (!tool) {
    return { success: false, error: `Unknown tool: ${toolName}` };
  }

  // 2. 权限检查
  const canUse = await context.checkPermission(toolName);
  if (!canUse) {
    return {
      success: false,
      error: `Permission denied for tool: ${toolName}`,
      requiresApproval: true,
    };
  }

  // 3. 执行
  return await tool.execute(args, context);
}
```

### 3.2 权限配置

```typescript
// 用户可以在项目中配置工具权限
interface ProjectPermissions {
  allow: string[];        // 允许的工具
  deny: string[];        // 拒绝的工具
  confirm: string[];     // 需要确认的工具
  autoApprove: boolean;  // 自动批准信任的命令
}

// .claude/settings.json
{
  "permissions": {
    "allow": ["Read", "WebFetch"],
    "confirm": ["Bash", "Write"],
    "deny": ["Edit"]
  }
}
```

---

## 4. 危险命令检测

### 4.1 Claude Code 的安全模式匹配

Claude Code 使用**正则表达式**来检测危险命令模式：

```typescript
// BashTool 的危险命令检测（简化示例）
const DANGEROUS_PATTERNS = [
  // 递归删除根目录
  /^rm\s+-rf\s+\//,
  // 格式化磁盘
  /^mkfs/,
  // 直接写入设备
  /^dd\s+if=/,
  // 修改所有权限
  /^chmod\s+-R\s+777/,
  // Fork 炸弹
  /:\s*\{\s*:\s*\|/,
];

function isDangerous(command: string): string[] {
  return DANGEROUS_PATTERNS
    .filter(pattern => pattern.test(command))
    .map(pattern => pattern.toString());
}
```

### 4.2 Mini-Claude 的简单实现

```typescript
// Mini-Claude: 简单的危险命令黑名单
class ShellTool {
  private blacklist = ['rm -rf', ':(){:|:&};:'];

  async execute(params) {
    const command = params.command;

    // 简单的字符串包含检查
    for (const dangerous of this.blacklist) {
      if (command.includes(dangerous)) {
        return {
          success: false,
          error: `危险命令: ${dangerous}`
        };
      }
    }

    // 执行命令
    const result = await execAsync(command);
    return { success: true, result: result.stdout };
  }
}
```

### 4.3 对比

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| 检测方式 | 字符串包含 | 正则匹配 |
| 覆盖范围 | 有限 | 更全面 |
| 误报率 | 可能较高 | 更精确 |

---

## 5. 资源限制

### 5.1 超时控制

Claude Code 对所有工具执行都有超时控制：

```typescript
// Claude Code 的超时控制
async function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number
): Promise<T> {
  let timeoutId: NodeJS.Timeout;

  const timeout = new Promise<T>((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error('Execution timeout')), timeoutMs);
  });

  try {
    return await Promise.race([promise, timeout]);
  } finally {
    clearTimeout(timeoutId!);
  }
}

// 默认超时：30秒
const DEFAULT_TIMEOUT = 30000;
```

### 5.2 输出截断

```typescript
// Claude Code 的输出大小限制
const MAX_OUTPUT_LENGTH = 100_000; // 100KB

interface TruncatedOutput {
  content: string;
  truncated: boolean;
  originalLength: number;
}

function truncateOutput(output: string): TruncatedOutput {
  if (output.length > MAX_OUTPUT_LENGTH) {
    return {
      content: output.slice(0, MAX_OUTPUT_LENGTH) + '\n... (output truncated)',
      truncated: true,
      originalLength: output.length,
    };
  }
  return {
    content: output,
    truncated: false,
    originalLength: output.length,
  };
}
```

---

## 6. 实战练习

### 6.1 练习：增强 Mini-Claude 的安全检测

**目标**：为 Mini-Claude 添加更完善的危险命令检测

**答案要点**：
```typescript
class SecureShellTool {
  // 使用正则进行更精确的匹配
  private dangerousPatterns: Array<{
    pattern: RegExp;
    message: string;
  }> = [
    { pattern: /^rm\s+-rf\s+\//, message: '禁止删除根目录' },
    { pattern: /:\s*\{.*\|.*&.*\}/, message: 'Fork炸弹检测' },
    { pattern: /\|\s*sh$/, message: '管道到shell危险' },
    { pattern: />\s*\/dev\/sda/, message: '直接写入设备' },
  ];

  validate(command: string): { valid: boolean; message?: string } {
    for (const { pattern, message } of this.dangerousPatterns) {
      if (pattern.test(command)) {
        return { valid: false, message };
      }
    }
    return { valid: true };
  }

  async execute(params) {
    const validation = this.validate(params.command);
    if (!validation.valid) {
      return { success: false, error: validation.message };
    }
    // 继续执行...
  }
}
```

---

## 7. 与我们的小项目对比

### 7.1 安全机制对比

| 方面 | Mini-Claude (Chapter 02) | Claude Code |
|------|-------------------------|-------------|
| 权限检查 | 无 | 完整权限级别系统 |
| 危险检测 | 简单字符串匹配 | 正则模式匹配 |
| 超时控制 | 无 | 任务级别超时 |
| 输出截断 | 无 | 智能截断 + 标记 |
| 沙箱隔离 | 无 | 可配置 |
| 参数校验 | 无 | Schema 校验 |

### 7.2 执行流程对比

```
Mini-Claude 执行流程:
用户输入 → AI 决定工具 → 直接执行 → 返回结果
                ↓
           无权限检查
           无超时控制

Claude Code 执行流程:
┌─────────────────────────────────────────┐
│         用户输入                          │
├─────────────────────────────────────────┤
│         AI 决定工具                       │
├─────────────────────────────────────────┤
│    useCanUseTool() 权限检查              │
│         ↓                               │
│    tool.execute() 执行                   │
│    ├── preprocess 预处理                  │
│    ├── 参数校验                          │
│    ├── 超时监控                          │
│    ├── 危险检测                          │
│    └── postprocess 后处理                │
├─────────────────────────────────────────┤
│    输出截断 + 审计日志                    │
└─────────────────────────────────────────┘
```

### 7.3 关键差异总结

| 差异点 | Mini-Claude | Claude Code | 为什么重要 |
|--------|-------------|-------------|------------|
| 权限模型 | 无 | allow/confirm/ask/deny | 用户控制 AI 能做什么 |
| 危险检测 | 简单黑名单 | 正则 + 白名单 | 更精准的检测 |
| 执行监控 | 无 | 超时 + 资源限制 | 防止恶意操作 |
| 失败处理 | 直接报错 | 格式化错误消息 | AI 能更好地恢复 |

### 7.4 扩展练习

**问题**：如何在 Mini-Claude 中添加超时控制？

**提示**：
1. 使用 `Promise.race()` 实现超时
2. 创建一个 `withTimeout` 工具封装函数
3. 超时时返回有意义的错误消息

**答案要点**：
```typescript
async function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  timeoutMsg: string
): Promise<T> {
  const timeout = new Promise<T>((_, reject) =>
    setTimeout(() => reject(new Error(timeoutMsg)), ms)
  );
  return Promise.race([promise, timeout]);
}

// 使用
async function executeWithTimeout(tool: Tool, args: Record<string, unknown>) {
  return withTimeout(
    tool.execute(args),
    30000, // 30秒超时
    `工具 ${tool.name} 执行超时`
  );
}
```

---

## 8. 总结

| 安全机制 | Mini-Claude | Claude Code |
|----------|-------------|-------------|
| 权限检查 | 无 | 完整 |
| 危险检测 | 简单字符串 | 正则模式 |
| 超时控制 | 无 | 有 |
| 输出截断 | 无 | 有 |
| 沙箱隔离 | 无 | 可选 |

---

## 下一篇

👉 [10 - 权限系统](../05-permission-system.md) —— 深入理解 Claude Code 的权限模型

`★ Insight ─────────────────────────────────────`
安全不是事后补丁，而是设计时就需要考虑的。Claude Code 的多层防护（权限、参数校验、危险检测、资源限制）形成了一个纵深防御体系。即使一层被突破，其他层也能提供保护。这种思想在任何需要处理用户输入的系统都适用。
`─────────────────────────────────────────────────`
