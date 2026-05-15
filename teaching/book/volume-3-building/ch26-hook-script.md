# 第 26 章：造一个 Hook 脚本

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

本章创建一个 PreToolUse Hook——在文件写入前检查是否包含敏感信息。

---

## 目标

```
Claude 尝试调用 Write tool 写入 config.yml
  → Hook 脚本检查内容
  → 发现包含 API_KEY
  → 返回 deny，阻止写入
```

---

## Hook 协议

Hook 通过 stdin/stdout 通信：

```
Claude Code → stdin → Hook 脚本 → stdout → Claude Code

stdin: JSON 格式的 Hook 输入
stdout: JSON 格式的 Hook 结果
```

### Hook 输入格式（PreToolUse）

```json
{
  "session_id": "abc-123",
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/project/config.yml",
    "content": "api_key: sk-abc123..."
  }
}
```

### Hook 输出格式

```json
// 允许执行
{ "decision": "allow" }

// 阻止执行
{ "decision": "deny", "reason": "Contains API key" }

// 修改输入
{ "decision": "allow", "updatedInput": { "content": "[REDACTED]" } }
```

---

## 实现：敏感信息检查 Hook

### Bash 脚本版本

```bash
#!/bin/bash
# .claude/hooks/check-secrets.sh

# 从 stdin 读取 JSON 输入
INPUT=$(cat)

# 提取工具名和输入
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name')
TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input')

# 只检查写入操作
if [ "$TOOL_NAME" != "Write" ] && [ "$TOOL_NAME" != "Edit" ]; then
  echo '{"decision": "allow"}'
  exit 0
fi

# 提取内容
CONTENT=$(echo "$TOOL_INPUT" | jq -r '.content // .new_string // empty')

# 检查敏感模式
PATTERNS=(
  'sk-[a-zA-Z0-9]{20,}'           # OpenAI API key
  'AIza[a-zA-Z0-9_-]{35}'         # Google API key
  'ghp_[a-zA-Z0-9]{36}'           # GitHub PAT
  'AKIA[A-Z0-9]{16}'              # AWS access key
  '-----BEGIN PRIVATE KEY-----'   # Private key
)

for pattern in "${PATTERNS[@]}"; do
  if echo "$CONTENT" | grep -qE "$pattern"; then
    echo "{\"decision\": \"deny\", \"reason\": \"Content contains sensitive data matching pattern: $pattern\"}"
    exit 0
  fi
done

# 通过检查
echo '{"decision": "allow"}'
```

### Node.js 脚本版本

```javascript
// .claude/hooks/check-secrets.mjs

import { createInterface } from 'readline'

const rl = createInterface({ input: process.stdin })
let input = ''

rl.on('line', (line) => { input += line })
rl.on('close', () => {
  const data = JSON.parse(input)

  // 只检查写入工具
  if (!['Write', 'Edit'].includes(data.tool_name)) {
    console.log(JSON.stringify({ decision: 'allow' }))
    return
  }

  const content = data.tool_input?.content
    ?? data.tool_input?.new_string
    ?? ''

  const patterns = [
    { name: 'OpenAI key', re: /sk-[a-zA-Z0-9]{20,}/ },
    { name: 'Google key', re: /AIza[a-zA-Z0-9_-]{35}/ },
    { name: 'GitHub PAT', re: /ghp_[a-zA-Z0-9]{36}/ },
    { name: 'AWS key', re: /AKIA[A-Z0-9]{16}/ },
    { name: 'Private key', re: /-----BEGIN PRIVATE KEY-----/ },
  ]

  for (const { name, re } of patterns) {
    if (re.test(content)) {
      console.log(JSON.stringify({
        decision: 'deny',
        reason: `Content contains ${name}`,
      }))
      return
    }
  }

  console.log(JSON.stringify({ decision: 'allow' }))
})
```

---

## 配置 Hook

```json
// .claude/settings.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [{
          "type": "command",
          "command": "node .claude/hooks/check-secrets.mjs",
          "timeout": 5000
        }]
      },
      {
        "matcher": "Edit",
        "hooks": [{
          "type": "command",
          "command": "node .claude/hooks/check-secrets.mjs",
          "timeout": 5000
        }]
      }
    ]
  }
}
```

---

## 测试

```bash
# 直接测试 Hook 脚本
echo '{"tool_name":"Write","tool_input":{"content":"api_key: sk-abc123def456ghi789jkl012mno345"}}' | \
  node .claude/hooks/check-secrets.mjs

# 期望输出：{"decision": "deny", "reason": "Content contains OpenAI key"}

# 安全内容测试
echo '{"tool_name":"Write","tool_input":{"content":"console.log(\"hello\")"}}' | \
  node .claude/hooks/check-secrets.mjs

# 期望输出：{"decision": "allow"}
```

---

## 高级：HTTP Hook

如果检查逻辑需要外部服务：

```json
{
  "type": "http",
  "url": "https://security-api.example.com/check",
  "headers": {
    "Authorization": "Bearer $SECURITY_API_KEY"
  },
  "timeout": 3000
}
```

Hook 输入自动 POST 到 URL，响应作为 Hook 结果。

---

## 检查点

- **Hook 协议**：stdin JSON → 脚本处理 → stdout JSON
- **PreToolUse Hook**：`decision: allow/deny`，可修改 `tool_input`
- **敏感信息检查**：正则匹配 API key、私钥等模式
- **配置位置**：`.claude/settings.json` 的 `hooks` 字段
- **执行类型**：command（Shell）、http（Webhook）、prompt（LLM）、agent（子代理）

**下一章**：第 27 章深入高级扩展——任务系统与子代理架构。
