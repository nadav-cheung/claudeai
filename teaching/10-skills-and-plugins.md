# 10 - Skills 与插件系统

> **本章目标**：理解 Claude Code 的 Skill（技能）和 Plugin（插件）系统。学完本章后，你将清楚：
>
> 1. Skill 的定义格式（文件系统、内建、MCP、Plugin 四种来源）
> 2. Skill 的加载、去重、动态发现和条件激活机制
> 3. SkillTool 如何调用 Skill（inline vs fork 两种执行模式）
> 4. Plugin 的生命周期（安装、启用/禁用、更新、卸载）
> 5. Plugin 如何通过 hook 系统注入行为
> 6. Marketplace（插件市场）的发现与协调机制

---

## 核心概念

### Skill vs Plugin 的区别

| 维度 | Skill（技能） | Plugin（插件） |
|------|--------------|---------------|
| 形式 | Markdown 文件（SKILL.md）或 TypeScript 注册 | 一个目录，含 plugin.json + skills/ + hooks/ |
| 来源 | 文件系统、内建、MCP、Plugin | Marketplace 安装、本地目录、内建 |
| 执行 | SkillTool 调用，展开为 prompt 注入对话 | 通过 Skill 暴露功能；通过 Hook 注入行为 |
| 可见性 | 在 system-reminder 中列出 | 在 /plugin UI 中管理 |
| 用户交互 | `/skill-name` 斜杠命令 | `/plugin` 管理界面 |

### Skill 的四种来源

```
1. bundled  - 编译进 CLI 二进制，所有用户可用
2. skills   - 文件系统中的 .claude/skills/skill-name/SKILL.md
3. mcp      - MCP 服务器动态提供的技能
4. plugin   - 通过 Plugin 安装提供的技能
```

### Command 类型定义

Skill 在代码中统一表示为 `Command` 对象，关键字段：

```typescript
// src/types/command.ts (概念模型)
type Command = {
  type: 'prompt'           // 所有 skill 都是 prompt 类型
  name: string             // 技能名称，如 "commit"
  description: string      // 简短描述
  whenToUse?: string       // 模型用于匹配的详细描述
  source: string           // 'bundled' | 'plugin' | 'userSettings' | ...
  loadedFrom: LoadedFrom   // 'bundled' | 'skills' | 'mcp' | 'plugin' | ...
  allowedTools: string[]   // 技能允许使用的工具列表
  context?: 'fork'         // 如果设置，则在子 agent 中执行
  model?: string           // 模型覆盖
  effort?: EffortValue     // 努力级别覆盖
  hooks?: HooksSettings    // 技能附带的 hook
  paths?: string[]         // 条件激活的路径模式
  getPromptForCommand(args, ctx) => Promise<ContentBlockParam[]>
}
```

---

## 源码导览

### 关键目录结构

```
src/skills/
  bundledSkills.ts           # BundledSkillDefinition 类型和注册 API
  loadSkillsDir.ts           # 文件系统 skill 加载（核心，~1080 行）
  mcpSkillBuilders.ts        # MCP skill 构建器的注册表
  bundled/
    index.ts                 # initBundledSkills() - 启动时注册所有内建 skill
    remember.ts              # /remember - 记忆审查
    simplify.ts              # /simplify - 代码审查
    updateConfig.ts          # /update-config - 配置修改
    keybindings.ts           # /keybindings-help
    verify.ts                # /verify
    batch.ts                 # /batch
    debug.ts                 # /debug
    stuck.ts                 # /stuck
    skillify.ts              # /skillify
    loop.ts                  # /loop (feature flag)
    claudeApi.ts             # /claude-api (feature flag)
    scheduleRemoteAgents.ts  # /schedule-remote-agents (feature flag)
    claudeInChrome.ts        # /claude-in-chrome (条件启用)

src/tools/SkillTool/
  SkillTool.ts               # SkillTool 工具定义（~1100 行）
  prompt.ts                  # Skill 列表的 prompt 生成和预算管理
  constants.ts               # SKILL_TOOL_NAME = 'Skill'

src/plugins/
  builtinPlugins.ts          # 内建 Plugin 注册表
  bundled/index.ts           # initBuiltinPlugins()

src/services/plugins/
  PluginInstallationManager.ts  # 后台安装协调
  pluginOperations.ts           # install/uninstall/enable/disable/update
  pluginCliCommands.ts          # CLI 命令入口

src/utils/plugins/
  loadPluginHooks.ts            # Plugin hook 加载和热重载
  validatePlugin.ts             # Plugin 验证
  installedPluginsManager.ts    # 磁盘上的安装记录
  officialMarketplace.ts        # 官方 Marketplace
  dependencyResolver.ts         # 依赖解析
  pluginPolicy.ts               # 策略控制
  pluginVersioning.ts           # 版本管理
  refresh.ts                    # 刷新活跃 Plugin

src/components/skills/
  SkillsMenu.tsx                # Skill 列表 UI
```

---

## 数据流图

### 1. Skill 加载流程

```
启动
  │
  ├─ initBundledSkills() ──> registerBundledSkill(definition)
  │                              │
  │                              └─> bundledSkills[] (内存注册表)
  │
  ├─ getSkillDirCommands(cwd)  [memoized]
  │     │
  │     ├── loadSkillsFromSkillsDir(managedSkillsDir) ──> managed/.claude/skills/
  │     ├── loadSkillsFromSkillsDir(userSkillsDir)    ──> ~/.claude/skills/
  │     ├── loadSkillsFromSkillsDir(projectDirs)      ──> .claude/skills/
  │     ├── loadSkillsFromSkillsDir(additionalDirs)   ──> --add-dir/.claude/skills/
  │     └── loadSkillsFromCommandsDir(cwd)            ──> .claude/commands/ (legacy)
  │
  │     └─> 去重 (realpath 去符号链接)
  │     └─> 分离条件 skill (有 paths frontmatter)
  │     └─> 返回 unconditionalSkills[]
  │
  ├─ Plugin skills ──> getBuiltinPluginSkillCommands() + loadAllPlugins()
  │
  ├─ MCP skills ──> MCP 连接后通过 mcpSkillBuilders 动态注册
  │
  └─ 合并为完整 Command[] 列表 ──> 注入 system prompt
```

### 2. Skill 调用流程

```
用户输入 → 模型选择 SkillTool
  │
  ├─ validateInput() ──> 查找 Command，检查 disableModelInvocation
  │
  ├─ checkPermissions() ──> 检查 deny/allow 规则，安全属性自动放行
  │
  ├─ call()
  │     │
  │     ├── context === 'fork'?
  │     │     └─ YES: executeForkedSkill() ──> runAgent() 子 agent
  │     │
  │     └── NO (inline): processPromptSlashCommand()
  │           └─ getPromptForCommand(args, ctx)
  │               └─ 替换参数: $ARGUMENTS, ${CLAUDE_SKILL_DIR}, ${CLAUDE_SESSION_ID}
  │               └─ 执行 shell 命令: !`...` (仅限非 MCP skill)
  │               └─ 返回 ContentBlockParam[]
  │
  └─ 返回 ToolResult + contextModifier (allowedTools, model, effort)
```

### 3. Plugin 生命周期

```
安装 (installPluginOp)
  │
  ├── 在 Marketplace 中查找 Plugin
  ├── 写入 settings (声明意图)
  ├── 缓存 Plugin + 记录版本
  └── 记录到 installed_plugins_v2.json

启用/禁用 (setPluginEnabledOp)
  │
  ├── 解析 pluginId 和 scope
  ├── 检查策略 (blockedByPolicy)
  ├── 更新 settings.enabledPlugins
  └── 清除缓存

更新 (updatePluginOp)
  │
  ├── 从 Marketplace 获取最新版本
  ├── 下载到临时目录 / 使用本地路径
  ├── 计算版本哈希
  ├── 复制到版本化缓存目录
  └── 更新 installed_plugins_v2.json

卸载 (uninstallPluginOp)
  │
  ├── 从 settings 移除
  ├── 从 installed_plugins_v2.json 移除
  ├── 标记旧版本为孤儿
  ├── 删除 Plugin 选项和密钥
  └── 可选删除数据目录
```

### 4. Plugin Hook 注入流程

```
loadPluginHooks() [memoized]
  │
  ├── loadAllPluginsCacheOnly() ──> 获取 enabled plugins
  │
  ├── for each plugin:
  │     └── convertPluginHooksToMatchers(plugin)
  │           └─ 遍历 hooksConfig 的每个 HookEvent
  │           └─ 包装为 PluginHookMatcher { matcher, hooks, pluginRoot, pluginName }
  │
  ├── clearRegisteredPluginHooks()
  ├── registerHookCallbacks(allPluginHooks)
  │
  └── setupPluginHookHotReload()
        └── 订阅 settingsChangeDetector
              └── policySettings 变化时 → 清缓存 → 重新 loadPluginHooks()
```

---

## 关键代码

### 1. Bundled Skill 注册 (src/skills/bundledSkills.ts)

`BundledSkillDefinition` 定义了内建 skill 的完整结构：

```typescript
// src/skills/bundledSkills.ts:15-41
export type BundledSkillDefinition = {
  name: string
  description: string
  aliases?: string[]
  whenToUse?: string
  argumentHint?: string
  allowedTools?: string[]
  model?: string
  disableModelInvocation?: boolean
  userInvocable?: boolean
  isEnabled?: () => boolean
  hooks?: HooksSettings
  context?: 'inline' | 'fork'
  agent?: string
  files?: Record<string, string>  // 惰性提取的参考文件
  getPromptForCommand: (args: string, context: ToolUseContext)
    => Promise<ContentBlockParam[]>
}
```

`registerBundledSkill()` 将定义转换为 `Command` 对象并推入内存注册表。如果 skill 带有 `files`，则惰性提取到临时目录（带安全写入保护 `O_NOFOLLOW | O_EXCL`）。

**内建 Skill 一览**（`src/skills/bundled/index.ts`）：

| Skill | 功能 | 用户可用 |
|-------|------|---------|
| `update-config` | 通过对话更新 `settings.json`（权限、环境变量、hook 配置） | ✅ |
| `verify` | 在终端运行 pr-review 检查，验证代码变更 | ✅ |
| `debug` | 读取 session debug log（Ant 用户）；开启 debug 日志并诊断（非 Ant） | ✅ |
| `lorem-ipsum` | 生成填充文本用于长上下文测试 | ❌ ANT-only |
| `simplify` | 审查变更代码的可复用性、质量和效率，并修复问题 | ✅ |
| `remember` | 审查 auto-memory 条目，建议晋升到 CLAUDE.md 或清理过时条目 | ✅ |
| `skillify` | 将 prompt 转化为可复用的 skill 文件 | ✅ |
| `stuck` | 调查本机 frozen/stuck/slow 会话并发布诊断报告 | ❌ ANT-only |
| `batch` | 研究并规划大规模变更，并行在 5–30 个独立 worktree agent 中执行 | ✅ |
| `keybindings-help` | 自定义键盘快捷键、绑定序列、修改 `~/.claude/keybindings.json` | ✅ |
| `dream` | KAIROS 模式下的梦生成 | KAIROS |
| `hunter` | 代码审查猎手 | REVIEW_ARTIFACT |
| `loop` | 定时循环执行任务（`/loop` 命令） | AGENT_TRIGGERS |
| `schedule-remote-agents` | 调度远程 Agent | AGENT_TRIGGERS_REMOTE |
| `claude-api` | Claude API 应用构建 | BUILDING_CLAUDE_APPS |
| `claude-in-chrome` | Chrome 中的 Claude 集成 | Chrome 扩展 |
| `run-skill-generator` | 运行 skill 生成器 | RUN_SKILL_GENERATOR |

### 2. 文件系统 Skill 加载 (src/skills/loadSkillsDir.ts)

这是 skill 加载的核心逻辑，约 1080 行。关键函数：

- **`getSkillDirCommands(cwd)`** — 加载所有来源的 skill，去重，分离条件 skill
- **`loadSkillsFromSkillsDir(basePath, source)`** — 读取 `skill-name/SKILL.md` 格式
- **`loadSkillsFromCommandsDir(cwd)`** — 兼容旧版 `.claude/commands/` 格式
- **`createSkillCommand({...})`** — 将 frontmatter 解析结果转为 `Command` 对象
- **`parseSkillFrontmatterFields(frontmatter, ...)`** — 解析所有 frontmatter 字段

去重策略：使用 `realpath` 解析符号链接得到文件身份（inode 在某些文件系统不可靠），按来源优先级保留第一个。

动态发现机制：
- **`discoverSkillDirsForPaths(filePaths, cwd)`** — 从文件路径向上遍历到 cwd，查找 `.claude/skills/` 目录
- **`activateConditionalSkillsForPaths(filePaths, cwd)`** — 激活有 `paths` frontmatter 的条件 skill

### 3. Skill 列表预算管理 (src/tools/SkillTool/prompt.ts)

Skill 列表只占用上下文窗口的 1%（约 8000 字符），策略如下：

```typescript
// src/tools/SkillTool/prompt.ts:21-23
export const SKILL_BUDGET_CONTEXT_PERCENT = 0.01
export const CHARS_PER_TOKEN = 4
export const DEFAULT_CHAR_BUDGET = 8_000
```

当描述超出预算时：
1. Bundled skill 永远不被截断（完整描述保留）
2. 非 bundled skill 的描述被截断以适应剩余空间
3. 极端情况下，非 bundled skill 只显示名称

### 4. SkillTool 调用 (src/tools/SkillTool/SkillTool.ts)

SkillTool 是模型调用 skill 的唯一入口。关键执行路径：

**Inline 执行**（默认）：skill 的 prompt 内容作为 user message 注入当前对话流，通过 `processPromptSlashCommand` 处理参数替换和 shell 命令执行。

**Fork 执行**（`context: 'fork'`）：skill 在隔离的子 agent 中运行，拥有独立的 token 预算。调用 `runAgent()` 获取 `AsyncGenerator<Message>`，收集结果文本后返回。

**安全检查**：`skillHasOnlySafeProperties()` 使用白名单检查 skill 属性，只有完全安全的 skill 才自动放行，其他需要用户确认。

### 5. Plugin 安装 (src/services/plugins/pluginOperations.ts)

安装流程是"settings-first"：

```typescript
// 简化的安装流程
async function installPluginOp(plugin, scope) {
  // 1. 在已物化的 Marketplace 中查找
  const found = await searchMarketplaces(pluginName)

  // 2. 写入 settings（声明意图）
  updateSettingsForSource(source, { enabledPlugins: { [pluginId]: true } })

  // 3. 缓存 Plugin + 记录版本
  await installResolvedPlugin({ pluginId, entry, scope, ... })
}
```

Scope 层级（从具体到通用）：`local` > `project` > `user` > `managed`

### 6. Plugin Hook 系统 (src/utils/plugins/loadPluginHooks.ts)

Plugin 通过 `hooksConfig` 注入行为，支持全部 HookEvent：

```
PreToolUse, PostToolUse, PostToolUseFailure, PermissionDenied,
Notification, UserPromptSubmit, SessionStart, SessionEnd, Stop,
StopFailure, SubagentStart, SubagentStop, PreCompact, PostCompact,
PermissionRequest, Setup, TeammateIdle, TaskCreated, TaskCompleted,
Elicitation, ElicitationResult, ConfigChange, WorktreeCreate,
WorktreeRemove, InstructionsLoaded, CwdChanged, FileChanged
```

Hook 加载是原子的：先 `clearRegisteredPluginHooks()`，再 `registerHookCallbacks()`，确保旧 hook 在新 hook 注册前始终有效。

热重载：通过 `settingsChangeDetector` 监听 `policySettings` 变化，对比快照后决定是否重新加载。

---

## 练习

### 练习 1：创建自定义 Skill

**类比 Java**：Skill 类似于 Spring 的 `@Bean` 定义——声明式注册，通过名称调用。

**答案**：

创建 Skill 的步骤：

1. **创建文件**：`.claude/skills/my-skill/SKILL.md`
2. **定义 frontmatter**：
```markdown
---
description: 项目结构分析
when_to_use: 当用户需要了解项目文件结构时使用
allowed-tools:
  - Bash
argument-hint: "[目录路径]"
---
```

3. **验证加载**：Skill 在启动时被 `getSkillDirCommands()` 扫描并注册

### 练习 2：追踪 Skill 调用链

**答案**：

调用链对比：

| 模式 | 路径 | Token 使用 |
|------|------|----------|
| Inline | SkillTool.call() → processPromptSlashCommand() → 注入 user message | 继承主会话预算 |
| Fork | SkillTool.call() → runAgent() → 独立上下文 | 独立预算 |

**Java 对比**：
```java
// Inline 类似方法直接调用
void inlineSkill() { /* 主线程 */ }

// Fork 类似 @Async 任务
@Async
CompletableFuture<String> forkedSkill() { /* 新线程 */ }
```

### 练习 3：理解 Plugin Hook 注入

**答案**：

Hook 注册必须是原子的原因：
- 避免新旧 hook 同时存在导致竞态
- 清空再注册确保 hook 执行顺序确定

**Java 对比**：
```java
// Spring 的拦截器注册也是原子的
InterceptorRegistry registry = getInterceptors();
registry.removeInterceptorByName(name);  // clear
registry.addInterceptor(interceptor);     // register
```

### 练习 4：条件 Skill 实验

**答案**：

条件 Skill 激活时机：
- 文件路径匹配 `paths` pattern 时激活
- 通过 `activateConditionalSkillsForPaths(filePaths, cwd)` 实现

**Java 对比**：
```java
// Spring 的 @ConditionalOnProperty
@Bean
@ConditionalOnProperty(name = "feature.skill.enabled")
public Skill mySkill() { return new MySkill(); }
```

---

### 练习 5：Plugin 热重载机制

**目标**：理解 Plugin 配置变化时如何触发热重载。

**场景**：用户修改了 `settings.json` 中的 `allowedTools` 配置，Claude Code 如何响应？

**答案**：

**热重载流程**：
```
settings.json 变化
    ↓
settingsChangeDetector 检测到变化
    ↓
发布 'policySettings' 变更事件
    ↓
loadPluginHooks() 重新加载
    ↓
Hook 配置更新完成
```

**关键代码**：
```typescript
settingsChangeDetector.subscribe(async (changes) => {
  if (changes.policySettings) {
    await loadPluginHooks()  // 重新加载
  }
})
```

**注意**：只重载 Hook 配置，不重载 Plugin 本身。

**Java 对比**：类似于 Spring 的 `@RefreshScope`，配置变化时重新创建 Bean。

---

## 练习答案速查

| 练习 | 核心答案 |
|------|---------|
| 1 | .claude/skills/name/SKILL.md 格式，frontmatter 定义元数据 |
| 2 | Inline=注入消息；Fork=独立 Agent，有独立 token 预算 |
| 3 | 原子注册避免竞态，clear + register 配对 |
| 4 | paths pattern 匹配时激活，类似 @Conditional |
| 5 | settingsChangeDetector 触发 loadPluginHooks() 重载 |

---

## Skill/Plugin vs Java Spring

| 方面 | Claude Code | Java Spring |
|------|-------------|-------------|
| 技能定义 | SKILL.md (Markdown) | @Bean 方法 |
| 技能注册 | getSkillDirCommands() | @ComponentScan |
| 条件激活 | paths frontmatter | @Conditional |
| 插件形式 | 目录 + plugin.json | JAR + spring.factories |
| Hook 注入 | loadPluginHooks() | HandlerInterceptor |
| 生命周期 | install/enable/update/uninstall | @PostConstruct/@PreDestroy |
| 预算管理 | SKILL_BUDGET_CONTEXT_PERCENT | 无等价 |

---

## 下一篇

[11-api-and-remote.md](11-api-and-remote.md) — API 通信与远程连接，包括 Anthropic API 调用流、流式响应、OAuth 认证、远程会话、Bridge 模式和多云支持。
