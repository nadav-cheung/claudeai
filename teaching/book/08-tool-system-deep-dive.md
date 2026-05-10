# 08 - 工具系统

> **本章目标**：深入理解 Claude Code 的工具系统——从 Tool 接口、工具注册、到具体工具的实现。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/Tool.ts` - 工具接口定义
- `src/tools.ts` - 工具注册表
- `src/tools/FileReadTool/` - 文件读取工具
- `src/tools/BashTool/` - Shell 执行工具

### 1.2 本章与 Mini-Claude 的关系

| Mini-Claude | Claude Code |
|-------------|-------------|
| `src/tools/tool.ts` (简单接口) | `src/Tool.ts` (完整接口) |
| `src/tools/registry.ts` | `src/tools.ts` |
| `src/tools/FileReadTool.ts` | `src/tools/FileReadTool/` |
| `src/tools/ShellTool.ts` | `src/tools/BashTool/` |

---

## 2. Tool 接口详解

### 2.1 Claude Code 的完整 Tool 接口

```typescript
// src/Tool.ts (简化)
export interface Tool<Input, Output, Context extends ToolContext = ToolContext> {
  // === 身份 ===
  readonly name: string;
  aliases?: string[];
  searchHint?: string;

  // === 描述（AI 用于决定何时调用）===
  description: string;
  categories?: ToolCategory[];

  // === 参数 Schema（JSON Schema 格式）===
  input_schema: {
    type: 'object';
    properties: Record<string, SchemaProperty>;
    required?: string[];
  };

  // === 执行 ===
  execute(args: Input, context: Context): Promise<ToolResult<Output>>;

  // === 可选钩子 ===
  preprocess?: (args: Input, context: Context) => Input | Promise<Input>;
  postprocess?: (result: ToolResult<Output>, context: Context) => ToolResult<Output>;
}

interface SchemaProperty {
  type: 'string' | 'number' | 'boolean' | 'object' | 'array';
  description?: string;
  default?: unknown;
  enum?: unknown[];
}
```

### 2.2 Mini-Claude 的简化接口

```typescript
// Mini-Claude 的简化版
interface Tool {
  name: string;
  description: string;
  parameters: Parameter[];
  execute(params: Record<string, unknown>): Promise<ToolResult>;
}
```

### 2.3 对比总结

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| 参数定义 | 简单数组 | JSON Schema |
| 类型安全 | any | 泛型 `<Input, Output>` |
| 预处理 | 无 | preprocess 钩子 |
| 后处理 | 无 | postprocess 钩子 |
| 描述分类 | 无 | categories |
| 搜索提示 | 无 | searchHint |

---

## 3. 工具注册表

### 3.1 Claude Code 的 getAllBaseTools

```typescript
// src/tools.ts (简化)
export function getAllBaseTools(): Tool[] {
  const tools: Tool[] = [];

  // 核心工具（默认加载）
  tools.push(new AgentTool());
  tools.push(new TaskOutputTool());
  tools.push(new BashTool());
  tools.push(new ExitPlanModeTool());
  tools.push(new FileReadTool());
  tools.push(new FileEditTool());
  tools.push(new FileWriteTool());
  tools.push(new WebFetchTool());
  // ... 更多工具

  // 条件加载（Feature Flags）
  if (feature('WEB_BROWSER_TOOL')) {
    tools.push(new WebBrowserTool());
  }

  if (feature('TODO_V2')) {
    tools.push(new TaskCreateTool());
    tools.push(new TaskGetTool());
    tools.push(new TaskUpdateTool());
    tools.push(new TaskListTool());
  }

  // MCP 工具（动态加载）
  const mcpTools = await loadMcpTools();
  tools.push(...mcpTools);

  return tools;
}
```

### 3.2 Mini-Claude 的硬编码注册

```typescript
// Mini-Claude: 构造函数里硬编码注册
class ToolRegistry {
  constructor() {
    this.register(new FileReadTool());
    this.register(new FileWriteTool());
    this.register(new ShellTool());
  }
}
```

---

## 4. 具体工具实现

### 4.1 FileReadTool

Claude Code 的文件读取工具比 Mini-Claude 复杂得多：

```typescript
// Claude Code 的 FileReadTool (简化)
export class FileReadTool implements Tool<string, string> {
  name = 'Read';
  description = '读取文件内容...';

  input_schema = {
    type: 'object',
    properties: {
      file_path: {
        type: 'string',
        description: '要读取的文件路径',
      },
      offset: {
        type: 'number',
        description: '字节偏移量',
      },
      limit: {
        type: 'number',
        description: '最大读取字节数',
      },
    },
    required: ['file_path'],
  };

  async execute(
    args: { file_path: string; offset?: number; limit?: number },
    context: ToolContext
  ): Promise<ToolResult<string>> {
    // 1. 权限检查
    if (!context.canRead(args.file_path)) {
      return { success: false, error: 'Permission denied' };
    }

    // 2. 路径规范化
    const resolvedPath = path.resolve(context.cwd, args.file_path);

    // 3. 读取文件（支持大文件截断）
    const content = await fs.readFile(resolvedPath, 'utf-8');

    // 4. 截断大文件
    if (args.limit && content.length > args.limit) {
      return {
        success: true,
        result: content.slice(args.offset || 0, args.limit) + '\n... (truncated)',
        truncated: true,
      };
    }

    return { success: true, result: content };
  }
}
```

### 4.2 BashTool 的安全执行

```typescript
// Claude Code 的 BashTool (简化)
export class BashTool implements Tool<string, string> {
  name = 'Bash';
  description = '执行 Shell 命令';

  async execute(
    command: string,
    context: ToolContext
  ): Promise<ToolResult<string>> {
    // 1. 危险命令检查
    const dangerous = this.detectDangerousCommands(command);
    if (dangerous.length > 0) {
      return {
        success: false,
        error: `危险命令: ${dangerous.join(', ')}`,
      };
    }

    // 2. 超时控制
    const result = await withTimeout(
      execAsync(command, { cwd: context.cwd, timeout: 30000 }),
      30000
    );

    // 3. 输出截断
    if (result.stdout.length > MAX_OUTPUT_LENGTH) {
      return {
        success: true,
        result: result.stdout.slice(0, MAX_OUTPUT_LENGTH) + '\n... (output truncated)',
        truncated: true,
      };
    }

    return { success: true, result: result.stdout + result.stderr };
  }

  private detectDangerousCommands(command: string): string[] {
    const dangerous = ['rm -rf', ':(){:|:&};:', 'dd if='];
    return dangerous.filter(d => command.includes(d));
  }
}
```

---

## 5. 工具执行流程

### 5.1 完整流程

```
用户消息
    │
    ▼
API 调用（携带工具 Schema）
    │
    ▼
AI 返回 tool_use
    │
    ▼
工具执行引擎 (toolExecution.ts)
    │
    ├── 1. 查找工具
    ├── 2. 权限检查
    ├── 3. 参数校验
    ├── 4. 预处理
    ├── 5. 执行
    ├── 6. 后处理
    └── 7. 返回结果
    │
    ▼
API 继续推理（或直接返回文本）
```

### 5.2 工具执行引擎

```typescript
// services/tools/toolExecution.ts (简化)
export async function executeTool(
  toolName: string,
  args: unknown,
  context: ToolContext
): Promise<ToolResult> {
  // 1. 查找工具
  const tool = tools.get(toolName);
  if (!tool) {
    return { success: false, error: `Unknown tool: ${toolName}` };
  }

  // 2. 权限检查
  if (!context.canUse(tool)) {
    return { success: false, error: 'Permission denied' };
  }

  // 3. 参数校验（JSON Schema）
  const validation = validateArgs(args, tool.input_schema);
  if (!validation.valid) {
    return { success: false, error: `Invalid args: ${validation.error}` };
  }

  // 4. 预处理
  const processedArgs = tool.preprocess
    ? await tool.preprocess(args, context)
    : args;

  // 5. 执行
  const result = await tool.execute(processedArgs, context);

  // 6. 后处理
  const finalResult = tool.postprocess
    ? await tool.postprocess(result, context)
    : result;

  return finalResult;
}
```

---

## 6. 实战练习

### 6.1 练习：实现一个 GrepTool

**目标**：为 Mini-Claude 添加一个 GrepTool（文本搜索）

**答案要点**：
```typescript
class GrepTool implements Tool {
  name = 'grep';
  description = '在文件中搜索匹配的文本';

  input_schema = {
    type: 'object',
    properties: {
      pattern: { type: 'string', description: '搜索模式(正则)' },
      file_path: { type: 'string', description: '文件路径' },
    },
    required: ['pattern', 'file_path'],
  };

  async execute(args: { pattern: string; file_path: string }) {
    const content = await fs.readFile(args.file_path, 'utf-8');
    const regex = new RegExp(args.pattern, 'g');
    const matches = content.match(regex) || [];
    return { success: true, result: `找到 ${matches.length} 个匹配` };
  }
}
```

### 6.2 练习：添加工具调用日志

**目标**：在 Mini-Claude 中添加工具执行的详细日志

**答案要点**：
```typescript
async function executeWithLogging(tool: Tool, args: Record<string, unknown>) {
  console.log(chalk.blue(`\n🔧 工具: ${tool.name}`));
  console.log(chalk.gray(`参数: ${JSON.stringify(args)}`));

  const startTime = Date.now();
  const result = await tool.execute(args);
  const duration = Date.now() - startTime;

  if (result.success) {
    console.log(chalk.green(`✓ 成功 (${duration}ms)`));
  } else {
    console.log(chalk.red(`✗ 失败 (${duration}ms): ${result.error}`));
  }

  return result;
}
```

---

## 7. 与我们的小项目对比

### 7.1 工具接口对比

| 方面 | Mini-Claude (Chapter 02) | Claude Code |
|------|-------------------------|-------------|
| 接口定义 | 简单 `name/description/parameters/execute` | 完整 `Tool<T>` 泛型接口 |
| 参数定义 | 简单数组 `Parameter[]` | JSON Schema 格式 |
| 类型安全 | `any` 类型 | 泛型 `<Input, Output, Context>` |
| 预处理 | 无 | `preprocess` 钩子 |
| 后处理 | 无 | `postprocess` 钩子 |
| 工具分类 | 无 | `categories` 数组 |
| 搜索提示 | 无 | `searchHint` 字段 |

### 7.2 工具注册对比

```
Mini-Claude 工具注册:
┌─────────────────────────────────────┐
│    tools/registry.ts (简单注册表)    │
├─────────────────────────────────────┤
│ - 硬编码工具列表                     │
│ - getTools() 返回所有工具            │
│ - 无动态加载                         │
└─────────────────────────────────────┘

Claude Code 工具注册:
┌─────────────────────────────────────┐
│         src/tools.ts                 │
├─────────────────────────────────────┤
│ - getAllBaseTools() 聚合所有工具     │
│ - Feature Flags 条件编译             │
│ - MCP 服务器动态注册                 │
│ - 工具别名系统                       │
└─────────────────────────────────────┘
```

### 7.3 关键差异总结

| 差异点 | Mini-Claude | Claude Code | 为什么重要 |
|--------|-------------|-------------|------------|
| 参数校验 | 运行时 any | JSON Schema 编译时 | 类型安全、文档自动生成 |
| 工具扩展 | 修改源码 | preprocess/postprocess | 无需修改工具本身 |
| 注册方式 | 硬编码 | 动态聚合 | 支持插件和 MCP 扩展 |
| 工具发现 | 全部加载 | 按需加载 | 性能优化 |

### 7.4 扩展练习

**问题**：如何在 Mini-Claude 中添加工具别名功能？

**提示**：
1. 在工具接口中添加 `aliases?: string[]`
2. 在注册表里建立别名 → 原名的映射
3. 查找工具时同时搜别名

**答案要点**：
```typescript
interface Tool {
  name: string;
  aliases?: string[];
  // ...
}

// 注册时建立别名索引
const aliasMap = new Map<string, string>();
for (const tool of tools) {
  for (const alias of tool.aliases || []) {
    aliasMap.set(alias, tool.name);
  }
}

// 查找工具时
function findTool(name: string): Tool | undefined {
  return tools.find(t => t.name === name || aliasMap.get(name) === t.name);
}
```

---

## 8. 总结

| 概念 | 理解 |
|------|------|
| Tool 接口设计 | ✓ |
| JSON Schema 参数校验 | ✓ |
| 工具注册表 | ✓ |
| 工具执行引擎 | ✓ |
| 安全检查 | ✓ |

---

## 下一篇

👉 [09 - 工具执行与安全](../04-tool-execution.md) —— 深入理解工具如何被安全地执行

`★ Insight ─────────────────────────────────────`
Claude Code 的工具系统设计展示了几个重要原则：**1) 接口一致性**——不管什么工具，都实现相同的 Tool 接口。**2) 组合优于继承**——通过 pre/postprocess 钩子增强工具，而非修改基类。**3) 安全第一**——所有工具都有权限检查和危险命令检测。**4) 失败友好**——工具执行失败不影响整个对话，AI 可以换一种方式尝试。
`─────────────────────────────────────────────────`
