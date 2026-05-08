# 01 - 入口与启动流程

> **本章目标**：理解从用户执行 `claude` 命令到 REPL 界面出现的完整启动链路，包括 CLI 解析、初始化、认证、工具注册等。

---

## 1. 启动阶段总览

Claude Code 的启动分为 **5 个阶段**，总耗时约 300-500ms：

```
Phase 0: 模块加载 (main.tsx 顶部 import)     ~135ms
Phase 1: 安全预检 + CLI 参数解析              ~5ms
Phase 2: init() 初始化                        ~100ms
Phase 3: 认证 + 配置                          ~50ms
Phase 4: REPL 渲染                            ~50ms
Phase 5: 后台预取 (deferredPrefetches)         非阻塞
```

---

## 2. Phase 0: 模块加载与副作用预启动

文件：`src/main.tsx:1-209`

### 2.1 三个关键预启动副作用

```typescript
// 1. 性能埋点：标记入口时间
profileCheckpoint('main_tsx_entry');

// 2. MDM 配置预读：在 macOS/Windows 上并行执行 plutil/reg query
startMdmRawRead();

// 3. Keychain 预取：并行读取 OAuth token + API key
startKeychainPrefetch();
```

**为什么需要预启动？** 这些 I/O 操作需要 60-100ms，如果在模块加载时就开始（而非等到 `init()`），可以与后续 135ms 的 import 阶段**并行执行**，节省总启动时间。

### 2.2 大规模 import

`main.tsx` 的 import 区域有约 **200 行**，导入了：
- Commander.js（CLI 解析）
- React + Ink（UI 框架）
- 所有工具（`tools.ts`）
- 所有命令（`commands.ts`）
- 各种工具函数和服务

### 2.3 懒加载打破循环依赖

```typescript
// 模式1: 函数包装 require
const getTeamCreateTool = () =>
  require('./tools/TeamCreateTool/TeamCreateTool.js').TeamCreateTool

// 模式2: Feature flag 条件加载（需先 import { feature } from 'bun:bundle'）
const coordinatorModeModule = feature('COORDINATOR_MODE')
  ? require('./coordinator/coordinatorMode.js')
  : null
```

### 2.4 反调试检查

```typescript
// main.tsx:266
if ("external" !== 'ant' && isBeingDebugged()) {
  process.exit(1);
}
```

外部构建版本会在启动时检测调试器，如果检测到就直接退出。检查方式包括 `process.execArgv`、`NODE_OPTIONS` 和 `inspector.url()`。

---

## 3. Phase 1: CLI 参数解析

文件：`src/main.tsx:585` → `main()` 函数

### 3.1 入口函数 `main()`

```typescript
export async function main() {
  // 安全：防止 Windows PATH 劫持
  process.env.NoDefaultCurrentDirectoryInExePath = '1';

  // 初始化警告处理
  initializeWarningHandler();

  // 注册退出时的光标恢复
  process.on('exit', () => resetCursor());

  // 处理 SIGINT
  process.on('SIGINT', () => {
    if (process.argv.includes('-p') || process.argv.includes('--print')) return;
    process.exit(0);
  });
}
```

### 3.2 早期参数处理

在 `main()` 中，有几个参数需要在 Commander.js 完整解析之前就处理：

```typescript
// --settings: 提前加载设置文件（影响后续所有配置读取）
eagerLoadSettings();

// 入口点标记（用于遥测区分不同使用方式）
initializeEntrypoint(isNonInteractive);

// cc:// URL 处理（Direct Connect 功能）
// 需先 import { feature } from 'bun:bundle'
if (feature('DIRECT_CONNECT')) {
  const rawCliArgs = process.argv.slice(2);
  const ccIdx = rawCliArgs.findIndex(a => a.startsWith('cc://') || a.startsWith('cc+unix://'));
  if (ccIdx !== -1 && _pendingConnect) {
    const ccUrl = rawCliArgs[ccIdx]!;
    const { parseConnectUrl } = await import('./server/parseConnectUrl.js');
    const parsed = parseConnectUrl(ccUrl);
    _pendingConnect.url = parsed.serverUrl;
    _pendingConnect.authToken = parsed.authToken;
    // 非交互模式：重写为 internal `open` 子命令；交互模式：剥离 URL 后正常启动
  }
}
```

### 3.3 Commander.js 命令定义

```typescript
const program = new CommanderCommand()
  .name('claude')
  .description('...')
  .option('-p, --print', '非交互模式，打印后退出')
  .option('--model <model>', '指定模型')
  .option('--resume [sessionId]', '恢复会话')
  .option('--allowedTools <tools>', '允许的工具列表')
  .option('--disallowedTools <tools>', '禁止的工具列表')
  // ... 更多选项
```

---

## 4. Phase 2: init() 初始化

文件：`src/entrypoints/init.ts`

`init()` 是一个 `memoize` 包装的异步函数，确保只执行一次。核心步骤：

```
init()
  ├── enableConfigs()              ← 验证并启用配置系统
  ├── applySafeConfigEnvironmentVariables()  ← 应用安全环境变量
  ├── applyExtraCACertsFromConfig() ← TLS 证书配置
  ├── setupGracefulShutdown()      ← 优雅退出注册
  ├── 初始化1P事件日志 (异步)       ← OpenTelemetry 日志
  ├── populateOAuthAccountInfoIfNeeded() ← OAuth 信息预填充
  ├── initJetBrainsDetection()     ← IDE 检测
  ├── detectCurrentRepository()    ← Git 仓库检测
  ├── initializeRemoteManagedSettingsLoadingPromise() ← 远程设置
  ├── initializePolicyLimitsLoadingPromise() ← 策略限制
  ├── recordFirstStartTime()       ← 记录首次启动时间
  ├── configureGlobalMTLS()        ← mTLS 配置
  ├── configureGlobalAgents()      ← HTTP 代理配置
  ├── preconnectAnthropicApi()     ← API 预连接 (TCP+TLS)
  ├── setShellIfWindows()          ← Windows git-bash 设置
  └── registerCleanup()            ← 注册清理回调
```

### 4.1 关键优化：API 预连接

```typescript
// init.ts:159
preconnectAnthropicApi()
```

在 init 阶段就预热到 Anthropic API 的 TCP+TLS 连接，约 100-200ms。当用户开始对话时，连接已经建立好，减少了首次请求延迟。

### 4.2 遥测初始化（信任后）

```typescript
// init.ts:247
initializeTelemetryAfterTrust()
```

遥测系统只在用户通过信任对话框后才初始化。对于远程设置用户，会先等待设置加载完成再初始化。

---

## 5. Phase 3: 认证与配置

### 5.1 数据迁移

```typescript
// main.tsx:326
runMigrations()
```

每次启动检查 `migrationVersion`，执行必要的设置迁移。当前版本是 11，包含：
- 自动更新设置迁移
- 绕过权限设置迁移
- MCP 服务器配置迁移
- 模型名称迁移（如 sonnet-1m → sonnet-4.5）

### 5.2 认证流程

```
认证检查
  ├── 检查 API Key (环境变量 / Keychain)
  ├── 检查 OAuth Token
  ├── 检查 Bedrock/Vertex 配置
  └── 未认证 → 显示登录对话框
```

### 5.3 GrowthBook 初始化

```typescript
initializeGrowthBook()
```

加载 A/B 测试和功能开关配置，决定哪些功能对当前用户可用。

---

## 6. Phase 4: REPL 渲染

### 6.1 启动路径选择

```
main()
  ├── -p / --print → query.ts (非交互)
  ├── --resume → 恢复会话
  ├── cc:// URL → Direct Connect
  ├── ssh:// → SSH 远程会话
  └── (默认) → launchRepl() (交互式 REPL)
```

### 6.2 launchRepl()

文件：`src/replLauncher.tsx`

```typescript
export async function launchRepl(root, appProps, replProps, renderAndRun) {
  const { App } = await import('./components/App.js')
  const { REPL } = await import('./screens/REPL.js')

  await renderAndRun(root,
    <App {...appProps}>
      <REPL {...replProps} />
    </App>
  )
}
```

### 6.3 React 组件树

```
<App>                              ← Context 根
  ├── FpsMetricsProvider           ← FPS 监控
  ├── StatsProvider                ← 统计数据
  ├── AppStateProvider             ← 应用状态
  │   ├── MailboxProvider          ← Agent 间通信
  │   └── VoiceProvider            ← 语音模式
  │       └── <REPL>               ← 主屏幕
  │           ├── PromptInput      ← 输入框
  │           ├── MessageList      ← 消息列表
  │           ├── PermissionReq    ← 权限对话框
  │           └── Spinner          ← 加载状态
```

---

## 7. Phase 5: 后台预取

```typescript
// main.tsx:388
startDeferredPrefetches()
```

REPL 首次渲染后触发的非阻塞预取：
- `initUser()` — 用户信息
- `getUserContext()` — 用户上下文
- `getSystemContext()` — 系统上下文（git status 等）
- `getRelevantTips()` — 提示信息
- `countFilesRoundedRg()` — 文件计数
- `initializeAnalyticsGates()` — 分析初始化
- `settingsChangeDetector.initialize()` — 设置变更监听
- `skillChangeDetector.initialize()` — 技能变更监听

**设计意图**：这些操作需要数百毫秒，但用户在首次渲染后还在"看界面"和"准备输入"，所以可以隐藏在这段时间内。

---

## 8. 启动流程完整时序图

```
Time    0ms ─── 100ms ─── 200ms ─── 300ms ─── 400ms ─── 500ms
       │          │          │          │          │          │
Phase0 ├─imports──────────────┤                              │
       │ ┌MDM预读────────────┐│                              │
       │ ┌Keychain预取──────┐ │                              │
       │                                          │          │
Phase1 │ ──安全检查─┤                             │          │
       │ ──CLI解析──┤                             │          │
       │                                          │          │
Phase2 │                    ├────init()──────────┤           │
       │                    │ ┌API预连接──────┐  │           │
       │                    │                  │  │           │
Phase3 │                                       ├─认证─┤     │
       │                                       ├配置──┤     │
       │                                                    │
Phase4 │                                              ├REPL─┤
       │                                                    │
Phase5 │                                               ┌预取(后台)─→
```

---

## 9. 关键代码

### 9.1 main() 函数核心

```typescript
// src/main.tsx:585
export async function main() {
  // 1. 安全：防止 Windows PATH 劫持
  process.env.NoDefaultCurrentDirectoryInExePath = '1'

  // 2. 初始化警告处理
  initializeWarningHandler()

  // 3. 处理 SIGINT
  process.on('SIGINT', () => {
    if (process.argv.includes('-p')) return
    process.exit(0)
  })

  // 4. 早期参数处理
  eagerLoadSettings()
  initializeEntrypoint(isNonInteractive)

  // 5. cc:// URL 处理（Direct Connect：远程连接到另一个 Claude Code 实例）
  if (feature('DIRECT_CONNECT')) {
    const rawCliArgs = process.argv.slice(2);
    const ccIdx = rawCliArgs.findIndex(a => a.startsWith('cc://') || a.startsWith('cc+unix://'));
    if (ccIdx !== -1 && _pendingConnect) {
      const ccUrl = rawCliArgs[ccIdx]!;
      const { parseConnectUrl } = await import('./server/parseConnectUrl.js');
      const parsed = parseConnectUrl(ccUrl);
      _pendingConnect.url = parsed.serverUrl;
      _pendingConnect.authToken = parsed.authToken;
      _pendingConnect.dangerouslySkipPermissions = rawCliArgs.includes('--dangerously-skip-permissions');
      if (rawCliArgs.includes('-p') || rawCliArgs.includes('--print')) {
        // headless 模式：重写为 internal `open` 子命令
        const stripped = rawCliArgs.filter((_, i) => i !== ccIdx);
        const dspIdx = stripped.indexOf('--dangerously-skip-permissions');
        if (dspIdx !== -1) stripped.splice(dspIdx, 1);
        process.argv = [process.argv[0]!, process.argv[1]!, 'open', ccUrl, ...stripped];
      } else {
        // 交互模式：剥离 URL 和 --dangerously-skip-permissions，继续正常启动
        const stripped = rawCliArgs.filter((_, i) => i !== ccIdx);
        const dspIdx = stripped.indexOf('--dangerously-skip-permissions');
        if (dspIdx !== -1) stripped.splice(dspIdx, 1);
        process.argv = [process.argv[0]!, process.argv[1]!, ...stripped];
      }
    }
  }

  // 6. 构建并执行 CLI
  const program = buildCLIProgram()
  await program.parseAsync(process.argv)
}
```

### 9.2 init() 初始化

```typescript
// src/entrypoints/init.ts:100
const init = memoize(async function init(): Promise<void> {
  // 1. 配置系统
  await enableConfigs()
  applySafeConfigEnvironmentVariables()
  applyExtraCACertsFromConfig()

  // 2. 优雅退出
  setupGracefulShutdown()

  // 3. API 预连接（关键优化）
  await preconnectAnthropicApi()

  // 4. Git 仓库检测
  await detectCurrentRepository()

  // 5. 远程设置加载
  initializeRemoteManagedSettingsLoadingPromise()
  initializePolicyLimitsLoadingPromise()
})
```

### 9.3 REPL 启动

```typescript
// src/replLauncher.tsx:50
export async function launchRepl(root, appProps, replProps, renderAndRun) {
  // 动态导入（代码分割）
  const { App } = await import('./components/App.js')
  const { REPL } = await import('./screens/REPL.js')

  // 构建组件树
  const appElement = (
    <App {...appProps}>
      <FpsMetricsProvider>
        <StatsProvider>
          <AppStateProvider>
            <MailboxProvider>
              <VoiceProvider>
                <REPL {...replProps} />
              </VoiceProvider>
            </MailboxProvider>
          </AppStateProvider>
        </StatsProvider>
      </FpsMetricsProvider>
    </App>
  )

  await renderAndRun(root, appElement)
}
```

### 9.4 后台预取

```typescript
// src/main.tsx:388
function startDeferredPrefetches(): void {
  // REPL 渲染后触发，用户看到界面后"隐藏"执行
  initUser()                    // 用户信息
  getUserContext()              // 用户上下文
  getSystemContext()            // git status 等
  getRelevantTips()              // 提示信息
  countFilesRoundedRg()         // 文件计数
  initializeAnalyticsGates()     // 分析初始化
  settingsChangeDetector.initialize()  // 设置监听
}
```

---

## 10. 关键文件索引

| 文件 | 作用 |
|------|------|
| `src/main.tsx` | 入口，CLI 解析，启动编排 |
| `src/entrypoints/init.ts` | 初始化逻辑（memoize） |
| `src/bootstrap/state.ts` | 全局状态单例 |
| `src/replLauncher.tsx` | REPL 启动 |
| `src/components/App.tsx` | React Context 根 |
| `src/screens/REPL.tsx` | 主交互屏幕 |
| `src/interactiveHelpers.tsx` | 交互辅助（渲染、错误处理） |
| `src/utils/startupProfiler.ts` | 启动性能分析 |
| `src/utils/config.ts` | 配置管理 |
| `src/utils/secureStorage/keychainPrefetch.ts` | Keychain 预取 |

---

## 练习

1. **追踪启动时间**：搜索 `profileCheckpoint` 调用，列出所有埋点位置
2. **理解 Feature Flag**：搜索 `feature('XXX')` 模式（需先 import { feature } from 'bun:bundle'），列出所有条件加载的模块
3. **追踪 CLI 参数**：在 `main.tsx` 中找到 Commander.js 的 `.option()` 调用，列出所有支持的参数
4. **理解迁移系统**：阅读 `src/migrations/` 目录，理解数据迁移的工作方式

---

## 下一篇

👉 [02-ink-terminal-ui.md](./02-ink-terminal-ui.md) — 终端 UI 框架 (Ink) 的实现细节
