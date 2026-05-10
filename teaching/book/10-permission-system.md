# 10 - 权限系统

> **本章目标**：深入理解 Claude Code 的权限模型，包括基于项目的权限配置、工具使用审批流程、用户确认机制。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/hooks/useCanUseTool.ts` - 权限检查钩子
- `src/tools/permissions.ts` - 权限配置

### 1.2 本章与 Mini-Claude 的关系

Mini-Claude 目前**没有**权限系统 —— 这是它和 Claude Code 最大的安全差距之一。

---

## 2. 为什么需要权限系统？

### 2.1 风险场景

Claude Code 可以执行任意命令，这意味着：

```text
用户让 Claude 帮忙"优化性能"
        │
        ▼
Claude 决定执行: rm -rf node_modules/
        │
        ▼
灾难发生！
```

### 2.2 权限系统的作用

```text
┌─────────────────────────────────────────────────────┐
│                 权限系统的作用                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  1. 控制谁能做什么                                    │
│     └── 只有经过批准的工具才能执行                     │
│                                                     │
│  2. 防止误操作                                      │
│     └── 危险操作需要用户明确确认                       │
│                                                     │
│  3. 审计追踪                                       │
│     └── 记录谁在什么时候使用了什么工具                 │
│                                                     │
│  4. 多用户支持                                      │
│     └── 不同用户有不同权限级别                         │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 3. Claude Code 的权限模型

### 3.1 权限级别

```typescript
// 工具权限级别
enum PermissionLevel {
  DENY = 'deny',           // 明确拒绝
  ASK = 'ask',             // 每次询问
  CONFIRM = 'confirm',     // 确认后执行
  ALLOW = 'allow',         // 直接允许
}

// 用户权限配置
interface UserPermissions {
  tools: Record<string, PermissionLevel>;
  autoApprove: boolean;
  autoApproveModels: boolean;
}
```

### 3.2 权限检查流程

```
工具执行请求
    │
    ├── 1. 检查全局权限配置
    │
    ├── 2. 检查工具特定权限
    │
    ├── 3. 判断是否需要用户确认
    │
    ├── 4. 如果需要确认，显示提示
    │
    └── 5. 用户确认后执行
```

### 3.3 useCanUseTool 钩子

```typescript
// hooks/useCanUseTool.ts (简化)
export function useCanUseTool() {
  const [permissions, setPermissions] = useState<UserPermissions>();

  // 检查工具权限
  function canUseTool(toolName: string): boolean {
    const level = permissions.tools[toolName];

    switch (level) {
      case 'allow':
        return true;

      case 'deny':
        return false;

      case 'ask':
      case 'confirm':
        return false; // 需要用户确认

      default:
        // 默认策略：危险工具需要确认
        return isSafeTool(toolName);
    }
  }

  // 请求用户确认
  async function requestConfirmation(toolName: string): Promise<boolean> {
    // 显示确认对话框
    return await showConfirmDialog({
      title: '工具执行确认',
      message: `允许执行工具 ${toolName} 吗？`,
      details: getToolDescription(toolName),
    });
  }

  return { canUseTool, requestConfirmation };
}
```

---

## 4. 权限配置方式

### 4.1 项目级配置

```json
// .claude/permissions.json
{
  "version": 1,
  "tools": {
    "Bash": {
      "level": "confirm",
      "autoApproveSeconds": 300
    },
    "Write": {
      "level": "confirm"
    },
    "Read": {
      "level": "allow"
    },
    "WebFetch": {
      "level": "allow"
    }
  },
  "autoApprove": false
}
```

### 4.2 交互式权限授予

当 Claude Code 遇到未授权的工具时：

```
┌─────────────────────────────────────────────────┐
│  🔒 工具执行需要授权                              │
├─────────────────────────────────────────────────┤
│                                                 │
│  工具: Bash                                     │
│  命令: npm install                              │
│                                                 │
│  [ ] 允许本次执行                                │
│  [ ] 允许所有 Bash 命令（5分钟内）               │
│  [ ] 永久允许 Bash 工具                          │
│                                                 │
│           [取消]        [允许]                   │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 5. Mini-Claude 的权限实现

### 5.1 简单的权限装饰器

```typescript
// Mini-Claude: 添加基础权限检查
function withPermission(
  tool: Tool,
  requiredLevel: 'allow' | 'confirm' = 'confirm'
) {
  return {
    ...tool,
    async execute(params: Record<string, unknown>, context: ToolContext) {
      // 检查权限
      const hasPermission = await checkPermission(tool.name, requiredLevel);

      if (!hasPermission) {
        return {
          success: false,
          error: `Permission denied for tool: ${tool.name}`,
          requiresApproval: true,
        };
      }

      return await tool.execute(params, context);
    },
  };
}

// 使用
const safeBashTool = withPermission(new BashTool(), 'confirm');
```

### 5.2 配置驱动的权限

```typescript
// Mini-Claude: 基于配置的权限
class PermissionManager {
  private config: Record<string, string> = {};

  async loadConfig() {
    const configPath = path.join(process.cwd(), '.mini-claude-permissions.json');
    try {
      const content = await fs.readFile(configPath, 'utf-8');
      this.config = JSON.parse(content);
    } catch {
      // 使用默认配置
      this.config = {
        'shell': 'confirm',
        'read': 'allow',
        'write': 'confirm',
      };
    }
  }

  canUse(toolName: string): { allowed: boolean; requiresConfirm: boolean } {
    const level = this.config[toolName] || 'deny';

    return {
      allowed: level !== 'deny',
      requiresConfirm: level === 'confirm',
    };
  }
}
```

---

## 6. 实战练习

### 6.1 练习：实现权限确认

**目标**：为 Mini-Claude 添加交互式权限确认

**答案要点**：
```typescript
async function executeWithConfirmation(
  tool: Tool,
  params: Record<string, unknown>
): Promise<ToolResult> {
  const { allowed, requiresConfirm } = permissionManager.canUse(tool.name);

  if (!allowed) {
    return {
      success: false,
      error: `Tool ${tool.name} is not allowed`,
    };
  }

  if (requiresConfirm) {
    const { confirmed } = await inquirer.prompt([
      {
        type: 'confirm',
        name: 'confirmed',
        message: `Allow tool "${tool.name}" to execute?`,
        default: false,
      },
    ]);

    if (!confirmed) {
      return { success: false, error: 'Permission denied by user' };
    }
  }

  return await tool.execute(params);
}
```

---

## 7. 总结

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| 权限级别 | 无 | 完整（allow/confirm/ask/deny） |
| 配置方式 | 无 | JSON 配置文件 |
| 用户确认 | 无 | 交互式确认 |
| 审计日志 | 无 | 完整日志 |
| 自动过期 | 无 | 有（时间限制） |

---

## 下一篇

👉 [11 - 上下文管理与压缩](../06-context-and-compact.md) —— 深入理解消息如何被压缩

`★ Insight ─────────────────────────────────────`
权限系统的核心是**最小权限原则**——默认拒绝，只在明确授权时才允许。这和 TypeScript 的类型系统很像：默认类型不兼容，只有明确声明后才允许操作。Claude Code 的权限系统让用户可以精细控制 AI 能做什么、不能做什么，既保证了便利性又确保了安全。
`─────────────────────────────────────────────────`
