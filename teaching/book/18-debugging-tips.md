# 18 - 调试技巧与工具

> **本章目标**：掌握 Claude Code 的调试技巧，学会使用各种工具诊断和解决问题。

---

## 1. 基础调试技巧

### 1.1 console.log 的艺术

```typescript
// ❌ 无用的日志
console.log('执行工具');
console.log('调用 API');

// ✅ 有意义的日志
console.log(`[ToolExecution] 开始执行工具: ${toolName}, 参数: ${JSON.stringify(args)}`);
console.log(`[ApiClient] 发送请求到 ${url}, token 数量: ${tokenCount}`);
```

### 1.2 日志级别

```typescript
// 简单实现日志级别
enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
}

function log(level: LogLevel, message: string, data?: unknown) {
  if (level < currentLogLevel) return;

  const prefix = {
    [LogLevel.DEBUG]: '[DEBUG]',
    [LogLevel.INFO]: '[INFO]',
    [LogLevel.WARN]: '[WARN]',
    [LogLevel.ERROR]: '[ERROR]',
  }[level];

  console.log(`${prefix} ${message}`, data || '');
}

// 使用
log(LogLevel.DEBUG, '工具参数', args);
log(LogLevel.INFO, 'API 调用成功');
log(LogLevel.ERROR, '执行失败', error);
```

---

## 2. VS Code 调试

### 2.1 配置调试

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "node",
      "request": "launch",
      "name": "Debug Claude Code",
      "program": "${workspaceFolder}/src/main.tsx",
      "runtimeExecutable": "bun",
      "runtimeArgs": ["run", "src/main.tsx"],
      "args": ["--verbose"],
      "console": "integratedTerminal"
    }
  ]
}
```

### 2.2 使用断点

```
1. 在代码行号左侧点击，设置断点
2. 按 F5 启动调试
3. 程序会在断点处暂停
4. 使用调试面板查看变量值
5. F10 单步跳过
6. F11 单步进入
7. Shift+F11 跳出
```

---

## 3. 常见问题诊断

### 3.1 API 调用失败

**症状**：API 返回错误

**诊断步骤**：
```bash
# 1. 检查 API Key
echo $ANTHROPIC_API_KEY  # 确保设置正确

# 2. 测试 API 连接
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"test"}],"max_tokens":10}'

# 3. 检查响应
```

### 3.2 工具执行失败

**症状**：工具返回错误

**诊断步骤**：
```typescript
// 添加详细日志
async function executeTool(toolName: string, args: unknown) {
  console.log(`[DEBUG] 执行工具: ${toolName}`);
  console.log(`[DEBUG] 参数: ${JSON.stringify(args)}`);

  try {
    const tool = registry.get(toolName);
    if (!tool) {
      throw new Error(`工具不存在: ${toolName}`);
    }

    console.log(`[DEBUG] 找到工具: ${tool.name}`);
    console.log(`[DEBUG] 工具描述: ${tool.description}`);

    const result = await tool.execute(args);
    console.log(`[DEBUG] 执行结果: ${JSON.stringify(result)}`);

    return result;
  } catch (error) {
    console.error(`[ERROR] 执行失败:`, error);
    throw error;
  }
}
```

---

## 4. 性能分析

### 4.1 简单计时

```typescript
// 测量执行时间
async function measureTime<T>(name: string, fn: () => Promise<T>): Promise<T> {
  const start = Date.now();
  console.log(`[TIMER] ${name} 开始`);
  try {
    const result = await fn();
    const duration = Date.now() - start;
    console.log(`[TIMER] ${name} 完成，耗时: ${duration}ms`);
    return result;
  } catch (error) {
    const duration = Date.now() - start;
    console.log(`[TIMER] ${name} 失败，耗时: ${duration}ms`);
    throw error;
  }
}

// 使用
await measureTime('API 调用', () => apiClient.call(message));
await measureTime('工具执行', () => tool.execute(args));
```

### 4.2 内存分析

```typescript
// 简单内存追踪
let messageCount = 0;
let totalTokens = 0;

function trackMessage(message: Message) {
  messageCount++;
  totalTokens += estimateTokens(message.content);

  console.log(`[MEMORY] 消息 #${messageCount}, 累计 tokens: ${totalTokens}`);

  if (totalTokens > 100000) {
    console.warn('[MEMORY] Token 数量接近限制，可能需要压缩');
  }
}
```

---

## 5. 网络调试

### 5.1 查看 API 请求

```typescript
// 简单请求日志
async function fetchWithLogging(url: string, options: RequestInit) {
  console.log(`[NET] 请求: ${options.method} ${url}`);

  const start = Date.now();
  const response = await fetch(url, options);
  const duration = Date.now() - start;

  console.log(`[NET] 响应: ${response.status} (${duration}ms)`);
  console.log(`[NET] Headers: ${JSON.stringify(Object.fromEntries(response.headers.entries()))}`);

  return response;
}
```

### 5.2 cURL 转换

把 fetch 调用转换成 cURL 命令，便于调试：

```typescript
function fetchToCurl(request: Request): string {
  const headers = Object.entries(request.headers)
    .map(([k, v]) => `-H '${k}: ${v}'`)
    .join(' ');

  const body = request.body ? `-d '${JSON.stringify(request.body)}'` : '';

  return `curl -X ${request.method} ${headers} ${body} '${request.url}'`;
}
```

---

## 6. 常见错误与修复

### 6.1 权限错误

```
Error: Permission denied for tool: Bash
```

**原因**：工具未在权限白名单中

**修复**：
1. 检查 `.claude/permissions.json` 配置
2. 确认工具名称拼写正确
3. 使用 `--allow-tool Bash` 参数启动

### 6.2 Token 超限

```
Error: max_tokens exceeded
```

**原因**：上下文超过模型限制

**修复**：
1. 使用 `/compact` 命令压缩上下文
2. 使用更短的系统 Prompt
3. 减少工具定义的 Schema 详细程度

---

## 7. 总结

| 技巧 | 用途 |
|------|------|
| console.log | 快速打印值 |
| 断点调试 | 暂停执行，查看状态 |
| 日志级别 | 控制信息量 |
| 计时测量 | 定位性能问题 |
| cURL 测试 | 验证 API 调用 |

---

## 下一篇

👉 [19 - 向 Claude Code 贡献代码](19-contributing.md) —— 学习如何为开源项目做贡献

`★ Insight ─────────────────────────────────────`
调试的核心是**控制变量**——一次只改变一个因素，然后观察结果。当问题复杂时，二分查找是个好策略：分别在代码的两半添加日志，看看问题出在哪一半。这样可以把搜索范围缩小一半，效率比线性搜索高得多。
`─────────────────────────────────────────────────`
