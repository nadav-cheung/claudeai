# 15 - Skills 与插件系统

> **本章目标**：深入理解 Claude Code 的 Skills 系统——内置技能如何定义，以及如何构建可扩展的插件系统。

---

## 1. 准备工作

### 1.1 阅读源码

**必读**：
- `src/skills/` - Skills 实现
- `src/tools/SkillTool/` - Skill 调用工具

### 1.2 本章与 Mini-Claude 的关系

| Mini-Claude | Claude Code |
|-------------|-------------|
| 无 Skills | 内置 Skills |
| 无插件系统 | 完整插件 API |

---

## 2. 什么是 Skill？

### 2.1 Skill 的定义

Skill 是一个**可复用的提示模板**，包含：
- 名称和描述
- 使用示例
- System Prompt 片段
- 可用的工具集

```text
Skill 示例：/review
┌─────────────────────────────────────────────────┐
│                                                 │
│  名称: code-review                              │
│  描述: 帮你审查代码质量问题                       │
│                                                 │
│  System Prompt:                                 │
│  "你是一个专业的代码审查员..."                    │
│                                                 │
│  可用工具: [Read, Grep, Bash]                   │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 2.2 Skill vs Tool

| 方面 | Tool | Skill |
|------|------|-------|
| 本质 | 执行操作 | 提供提示 |
| 触发 | AI 决定 | 用户斜杠命令 |
| 范围 | 单一操作 | 复杂行为 |
| 定制 | 参数 | 整个 Prompt |

---

## 3. Claude Code 的内置 Skills

### 3.1 Skill 定义格式

```typescript
// skills/definitions/review.ts (简化)
export const codeReviewSkill: Skill = {
  name: 'review',
  description: '审查代码质量问题',
  aliases: ['code-review', 'cr'],

  // 这个 Skill 激活时添加到 system prompt
  systemPrompt: `你是一个专业的代码审查员。

当审查代码时，请关注：
1. 代码可读性
2. 潜在 bug
3. 性能问题
4. 安全漏洞
5. 最佳实践

审查结果请按以下格式输出：
- 问题描述
- 严重程度（高/中/低）
- 建议修复方式`,

  // 这个 Skill 可以使用的工具
  allowedTools: ['Read', 'Grep', 'Glob'],

  // 使用示例
  examples: [
    '/review',
    '/review --focus security',
  ],
};
```

### 3.2 Skill 加载

```typescript
// skills/index.ts (简化)
export function loadSkills(): Skill[] {
  const skills: Skill[] = [];

  // 加载内置 Skills
  skills.push(codeReviewSkill);
  skills.push(testGenerationSkill);
  skills.push(documentationSkill);
  skills.push(refactorSkill);

  // 从配置文件加载自定义 Skills
  const customSkills = loadCustomSkills();
  skills.push(...customSkills);

  return skills;
}
```

---

## 4. SkillTool

### 4.1 用户调用 Skill

用户通过斜杠命令使用 Skill：

```
/review
  │
  ▼
SkillTool 被调用
  │
  ▼
Skill 被激活
  │
  ▼
System Prompt 被更新
  │
  ▼
AI 获得 Skill 的能力
```

### 4.2 SkillTool 实现

```typescript
// tools/SkillTool/ (简化)
export class SkillTool implements Tool {
  name = 'Skill';
  description = '激活一个 Skill 来增强 AI 的能力';

  input_schema = {
    type: 'object',
    properties: {
      skill_name: {
        type: 'string',
        description: '要激活的 Skill 名称',
        enum: skillNames, // 动态从可用 Skills 中获取
      },
    },
    required: ['skill_name'],
  };

  async execute(args: { skill_name: string }, context: ToolContext) {
    const skill = skills.get(args.skill_name);

    if (!skill) {
      return {
        success: false,
        error: `Skill not found: ${args.skill_name}`,
      };
    }

    // 激活 Skill：更新 context
    context.activateSkill(skill);

    return {
      success: true,
      result: `已激活 Skill: ${skill.name}\n\n${skill.description}`,
    };
  }
}
```

---

## 5. 插件系统

### 5.1 Claude Code 的插件 API

```typescript
// 插件接口定义
interface ClaudeCodePlugin {
  name: string;
  version: string;

  // 插件初始化
  init?(options: PluginOptions): Promise<void>;

  // 注册工具
  tools?: Tool[];

  // 注册 Skills
  skills?: Skill[];

  // 注册命令
  commands?: Command[];

  // 生命周期钩子
  hooks?: {
    onMessage?: (message: Message) => Message | void;
    onToolResult?: (result: ToolResult) => ToolResult | void;
    onComplete?: () => void;
  };
}
```

### 5.2 插件加载

```typescript
// pluginManager.ts (简化)
class PluginManager {
  private plugins: Map<string, ClaudeCodePlugin> = new Map();

  async loadPlugin(config: PluginConfig): Promise<void> {
    // 1. 导入插件模块
    const module = await import(config.path);

    // 2. 创建插件实例
    const plugin = module.default || module;

    // 3. 初始化
    if (plugin.init) {
      await plugin.init({ config });
    }

    // 4. 注册组件
    if (plugin.tools) {
      for (const tool of plugin.tools) {
        toolRegistry.register(tool);
      }
    }

    if (plugin.skills) {
      for (const skill of plugin.skills) {
        skillRegistry.register(skill);
      }
    }

    this.plugins.set(plugin.name, plugin);
  }
}
```

---

## 6. Mini-Claude 的简单插件

### 6.1 插件接口

```typescript
// Mini-Claude: 简单的插件接口
interface MiniClaudePlugin {
  name: string;
  version: string;

  // 初始化
  initialize?(): Promise<void>;

  // 工具
  tools?: Tool[];

  // 命令
  commands?: {
    name: string;
    execute: (args: string[]) => Promise<string>;
  }[];
}
```

### 6.2 插件加载

```typescript
// Mini-Claude: 插件管理器
class PluginManager {
  private plugins: MiniClaudePlugin[] = [];

  async load(pluginPath: string): Promise<void> {
    const plugin = await import(pluginPath);

    if (plugin.initialize) {
      await plugin.initialize();
    }

    // 注册工具
    if (plugin.tools) {
      for (const tool of plugin.tools) {
        registry.register(tool);
      }
    }

    // 注册命令
    if (plugin.commands) {
      for (const cmd of plugin.commands) {
        program.command(cmd.name).action(cmd.execute);
      }
    }

    this.plugins.push(plugin);
  }
}
```

---

## 7. 实战练习

### 7.1 练习：创建一个 Skill

**目标**：为 Mini-Claude 创建一个 `explain` Skill

**答案要点**：
```typescript
// Mini-Claude Skill 示例
const explainSkill: Skill = {
  name: 'explain',
  description: '详细解释代码或概念',

  systemPrompt: `当你被要求解释代码时：
1. 先说明整体功能
2. 逐部分解释实现
3. 说明关键的代码片段
4. 如果有更好的实现方式，请提出`,

  allowedTools: ['Read'],
};

registry.registerSkill(explainSkill);
```

---

## 8. 总结

| 方面 | Mini-Claude | Claude Code |
|------|-------------|-------------|
| Skill 系统 | 无 | 完整 |
| 插件系统 | 简单 | 完整 API |
| Skill 激活 | 无 | 动态更新 Prompt |
| 工具扩展 | 硬编码 | 插件 |
| 生命周期钩子 | 无 | 有 |

---

## 下一篇

👉 [16 - API通信与远程](../11-api-and-remote.md) —— 深入理解 Claude Code 的网络通信

`★ Insight ─────────────────────────────────────`
Skill 系统的本质是**Prompt 模板化**——把常用的 Prompt 模式提取成可复用的组件。这比每次都写完整的 Prompt 高效得多，而且保证了一致性。插件系统则更进一步，允许第三方扩展 Claude Code 的能力，这和 VS Code 的插件生态很相似。
`─────────────────────────────────────────────────`
