---
title: "第03章：React在终端里奔跑"
description: "深度剖析 Ink 如何让 React 在终端中运行：Fiber 协调器的适配、渲染管线的五个阶段、组件树从 App 到 REPL 的完整链路，以及状态变化如何驱动终端屏幕更新。"
tags: [react, ink, reconciler, fiber, yoga, terminal, rendering, jsx, component-tree, dom]
date: 2026-05-10
---

# 第03章：React在终端里奔跑

你打开 Claude Code，终端里出现了一个精致的界面：底部是输入框，上面是消息列表，中间穿插着工具调用的动画。这一切看起来很流畅，像一个原生的桌面应用。

但你心里清楚——这是一个终端程序。终端能做的事情有限：在指定位置显示字符、改变颜色、移动光标。它没有 CSS，没有浏览器引擎，没有 DOM。那么，React 怎么能在一个没有浏览器的地方跑起来？

上一章我们看到了程序启动的入口。这一章，我们要深入一个更底层的问题：Claude Code 用了什么机制，让 React 这个"网页框架"变成了"终端框架"？它怎么把一棵 React 组件树翻译成终端屏幕上的字符？

---

## 这是什么

用一个类比来理解。

想象你在写一份中文文档。你可以手动排版——一个字一个字地数，决定每个字在第几行第几列。这当然能行，但一旦要修改内容（加一句话、删一个段落），你就得重新数所有的字。这太痛苦了。

所以你用了一个排版软件，比如 Word。你只需要说"标题用二号字，正文用小四号，首行缩进两格"，软件帮你计算每一个字的精确位置。你修改内容，排版自动更新。

React 就是这个"排版软件"。你告诉它你想要什么界面（通过 JSX），它帮你计算每一个元素的精确位置和内容。你改了数据，界面自动更新。

但 React 原本是为浏览器设计的——它的"排版结果"是 DOM 节点，它的"输出设备"是浏览器窗口。在终端里，没有 DOM，也没有浏览器窗口。

Ink 就是那个"翻译层"。它做了一件精妙的事：替换了 React 的输出后端。React 仍然负责"你想显示什么"，但 Ink 告诉 React："别把结果画到浏览器里了，画到终端里。"

这就像把一个打印机的驱动换掉了——Word 还是那个 Word，排版逻辑没变，但输出从 A4 纸变成了热敏小票纸。

---

## 打开源码

打开 `src/ink/` 目录。你会看到五十多个文件，但核心的渲染管线只涉及几个关键文件：

```
src/ink.ts                  -- 入口门面（85行），封装 Ink 的 render 和 createRoot
src/ink/
  reconciler.ts             -- Fiber 协调器适配（512行）
  root.ts                   -- 创建渲染根（184行）
  renderer.ts               -- DOM 节点 -> 屏幕缓冲区（178行）
  render-node-to-output.ts  -- 逐节点绘制（~1800行，最重的文件）
  ink.tsx                   -- Ink 主类，调度渲染循环（~900行）
  frame.ts                  -- 帧数据结构，双缓冲定义
  output.ts                 -- 输出缓冲区管理
  screen.ts                 -- 屏幕缓冲区（每个字符一格的二维数组）
  layout/
    engine.ts               -- 布局引擎入口，委托给 Yoga
  components/
    Box.tsx                 -- 终端里的矩形区域
    Text.tsx                -- 终端里的文字
    ScrollBox.tsx           -- 可滚动的区域
    Button.tsx              -- 可交互的按钮
  hooks/
    use-input.ts            -- 键盘输入 hook
    use-stdin.ts            -- 标准输入流 hook
```

这些文件构成了一条完整的渲染管线。我们从最外面的入口开始，一步步走到终端屏幕。

---

## 它怎么工作

### 第一站：入口门面 `src/ink.ts`

只有 85 行，但它是整个终端渲染系统的门面。所有外部代码想画 UI，都要经过这个文件。

```typescript
// src/ink.ts，第14-31行
function withTheme(node: ReactNode): ReactNode {
  return createElement(ThemeProvider, null, node)
}

export async function render(
  node: ReactNode,
  options?: NodeJS.WriteStream | RenderOptions,
): Promise<Instance> {
  return inkRender(withTheme(node), options)
}

export async function createRoot(options?: RenderOptions): Promise<Root> {
  const root = await inkCreateRoot(options)
  return {
    ...root,
    render: node => root.render(withTheme(node)),
  }
}
```

`withTheme` 做的事情很简单：在你的组件树外面包一层 `ThemeProvider`。Claude Code 的所有 UI 组件都依赖主题系统来决定颜色和样式。如果每次渲染都要手动挂载 ThemeProvider，既麻烦又容易忘。所以在门面层统一处理——你的组件进来，带着主题出去。

`render` 和 `createRoot` 暴露了两种创建 UI 的方式。`render` 是一次性的：传入组件，立刻渲染，返回一个可以 `rerender` 和 `unmount` 的实例。`createRoot` 是可复用的：先创建一个空根，之后反复调用 `root.render()` 挂载不同的组件树。

注意到 `createRoot` 返回的对象把 `render` 方法包装了一下：`render: node => root.render(withTheme(node))`。这样每次调用 `root.render()` 时，主题注入都会自动发生。

### 第二站：Fiber 协调器 `src/ink/reconciler.ts`

这是整条管线中最精妙的部分。

React 本身并不知道怎么画界面。React 的核心是一个叫 Fiber 的架构——它负责维护组件树、比较新旧差异、决定哪些节点需要更新。但"怎么更新"这件事，React 留给了"宿主环境"去实现。在浏览器里，宿主环境是 DOM：React 说"创建一个节点"，浏览器就创建一个 `div`。React 说"设置样式"，浏览器就设置 `element.style.color`。

`react-reconciler` 是 React 暴露出来的一个底层 API，让你可以自定义宿主环境。Ink 用它告诉 React："当你说'创建节点'时，我不会创建 DOM 节点——我会创建一个终端节点。"

看看这个协调器是怎么定义的：

```typescript
// src/ink/reconciler.ts，第224-260行
const reconciler = createReconciler<
  ElementNames,    // 节点类型：'ink-box', 'ink-text', 'ink-root'...
  Props,
  DOMElement,      // 宿主节点类型
  DOMElement,
  TextNode,        // 文本节点类型
  DOMElement,
  unknown,
  unknown,
  DOMElement,
  HostContext,
  null,
  NodeJS.Timeout,
  -1,
  null
>({
  getRootHostContext: () => ({ isInsideText: false }),
  createInstance(originalType, newProps, _root, hostContext) {
    if (hostContext.isInsideText && originalType === 'ink-box') {
      throw new Error(`<Box> can't be nested inside <Text> component`)
    }
    const type = originalType === 'ink-text' && hostContext.isInsideText
      ? 'ink-virtual-text'
      : originalType
    const node = createNode(type)
    for (const [key, value] of Object.entries(newProps)) {
      applyProp(node, key, value)
    }
    return node
  },
  createTextInstance(text, _root, hostContext) {
    if (!hostContext.isInsideText) {
      throw new Error(
        `Text string "${text}" must be rendered inside <Text> component`,
      )
    }
    return createTextNode(text)
  },
  // ...更多回调
})
```

`createReconciler` 接收一个巨大的配置对象。每个字段都是一个回调函数，React 在不同阶段会调用它们。关键几个：

**`createInstance`**——React 说"我要创建一个元素节点"。Ink 就创建一个 `DOMElement` 对象（不是浏览器 DOM，而是 Ink 自己的轻量节点）。节点类型被映射为 Ink 的内部类型：`<Box>` 变成 `ink-box`，`<Text>` 变成 `ink-text`。还有一个有趣的规则：`<Text>` 嵌套在 `<Text>` 里面时，内层的会被标记为 `ink-virtual-text`（虚拟文本节点），因为它不需要单独的布局计算。

**`createTextInstance`**——React 说"我要创建一个纯文本节点"。Ink 就创建一个 `TextNode`。注意那个校验：裸文本必须放在 `<Text>` 里面，否则直接报错。这是 Ink 的设计约束——终端里没有"默认的文本渲染方式"，你必须明确声明文本的样式容器。

**`commitUpdate`**——React 说"这个节点的属性变了"。Ink 就 diff 新旧 props，只更新变化的部分。如果 `style` 变了，就重新应用到 Yoga 节点上：

```typescript
// src/ink/reconciler.ts，第426-459行
commitUpdate(node, _type, oldProps, newProps) {
  const props = diff(oldProps, newProps)
  const style = diff(oldProps['style'], newProps['style'])
  if (props) {
    for (const [key, value] of Object.entries(props)) {
      if (key === 'style') {
        setStyle(node, value as Styles)
        continue
      }
      if (key === 'textStyles') {
        setTextStyles(node, value as TextStyles)
        continue
      }
      setAttribute(node, key, value as DOMNodeAttribute)
    }
  }
  if (style && node.yogaNode) {
    applyStyles(node.yogaNode, style, newProps['style'] as Styles)
  }
},
```

还有一个特别重要的回调：`resetAfterCommit`。React 每次提交完更新后都会调用它。Ink 在这里触发 Yoga 布局计算和渲染调度：

```typescript
// src/ink/reconciler.ts，第247-315行（简化）
resetAfterCommit(rootNode) {
  // 计算布局
  if (typeof rootNode.onComputeLayout === 'function') {
    rootNode.onComputeLayout()
  }
  // 触发渲染
  rootNode.onRender?.()
}
```

这个 `onComputeLayout` 和 `onRender` 是 Ink 主类在构造时挂上去的。它们构成了渲染管线的后半段。

### 第三站：DOM 节点模型 `src/ink/dom.ts`

Ink 的 `DOMElement` 不是浏览器的 DOM，而是一个轻量的 JavaScript 对象。它模拟了浏览器 DOM 的核心概念，但目标是终端：

```typescript
// src/ink/dom.ts，第31-91行（简化）
export type DOMElement = {
  nodeName: ElementNames      // 'ink-box', 'ink-text', 'ink-root'...
  attributes: Record<string, DOMNodeAttribute>
  childNodes: DOMNode[]
  yogaNode?: LayoutNode       // Yoga 布局节点
  style: Styles
  dirty: boolean              // 是否需要重新渲染
  scrollTop?: number          // 滚动位置
  focusManager?: FocusManager // 焦点管理器
  // ...更多终端特有的属性
}
```

注意 `yogaNode` 字段。每个 Ink 节点都关联一个 Yoga 布局节点——Yoga 是 Facebook 开发的 Flexbox 布局引擎，用 C++ 编写，通过 WASM 绑定到 JavaScript。你在 JSX 里写的 `flexDirection="column"`、`paddingLeft={2}` 这些样式属性，最终都会被应用到这个 Yoga 节点上。

`dirty` 字段是性能优化的关键。当某个节点的内容变了，它会被标记为 dirty。渲染时只需要处理 dirty 节点及其祖先，跳过未变化的部分。这和浏览器渲染中的"重排"（reflow）概念完全一致。

### 第四站：组件树从 App 到 REPL

了解了底层机制，现在看看实际的组件树长什么样。

最外层是 `App` 组件：

```typescript
// src/components/App.tsx，第19-55行（编译后，还原为原始结构）
export function App({
  getFpsMetrics,
  stats,
  initialState,
  children,
}: Props) {
  return (
    <FpsMetricsProvider getFpsMetrics={getFpsMetrics}>
      <StatsProvider store={stats}>
        <AppStateProvider
          initialState={initialState}
          onChangeAppState={onChangeAppState}
        >
          {children}
        </AppStateProvider>
      </StatsProvider>
    </FpsMetricsProvider>
  )
}
```

三层 Provider 嵌套。`AppStateProvider` 管理全局状态（你的对话、工具权限、输入模式等），`StatsProvider` 管理统计信息（token 使用量、API 调用次数），`FpsMetricsProvider` 管理帧率监控。这三层 Provider 不直接渲染任何可见内容——它们的工作是让所有子组件都能通过 React 的 context 机制访问这些数据。

在 `App` 里面，真正的界面是 `REPL` 组件。`REPL` 的 props 非常丰富：

```typescript
// src/screens/REPL.tsx，第526-570行
export type Props = {
  commands: Command[];
  debug: boolean;
  initialTools: Tool[];
  initialMessages?: MessageType[];
  pendingHookMessages?: Promise<HookResultMessage[]>;
  systemPrompt?: string;
  onBeforeQuery?: (input: string, newMessages: MessageType[]) => Promise<boolean>;
  onTurnComplete?: (messages: MessageType[]) => void | Promise<void>;
  disabled?: boolean;
  thinkingConfig: ThinkingConfig;
  // ...还有更多
};
```

每一个 prop 都是一条信息通道。`commands` 是可用命令列表，`initialMessages` 是初始对话历史，`systemPrompt` 是系统提示词，`onTurnComplete` 是一轮对话结束的回调。

`REPL` 的返回值是一棵巨大的组件树，核心结构是这样的：

```
AlternateScreen                -- 终端备用屏幕（全屏模式）
  KeybindingSetup              -- 键盘快捷键注册
  GlobalKeybindingHandlers     -- 全局按键处理
  FullscreenLayout             -- 全屏布局容器
    scrollable=
      Messages                 -- 消息列表
        UserTextMessage        -- 用户消息
        AssistantMessage       -- AI 回复
        ToolUseMessage         -- 工具调用展示
      SpinnerWithVerb          -- 加载动画
    bottom=
      PromptInput              -- 输入框
      PermissionStickyFooter   -- 权限提示
```

从 `App` 到 `REPL`，再到 `Messages`、`PromptInput`，整棵组件树可能有上百层嵌套。但每一层都只关心自己的职责——`PromptInput` 不关心消息列表怎么渲染，`Messages` 不关心输入框怎么处理按键。React 的组件化设计让这个庞大的系统变得可以理解。

### 第五站：渲染管线

当状态变化时，整条管线是怎么运转的？让我们追踪一次完整的渲染过程。

**阶段一：React 协调（reconcile）**

某个 state 变了（比如 AI 开始回复，一条新消息被添加到列表中）。React 的 Fiber 调度器开始工作，从组件树根部向下遍历，找出所有受影响的组件。对于每个受影响的组件，React 调用它的渲染函数，得到新的 JSX 输出，然后和新旧两棵树做 diff。

这个过程调用 `reconciler.ts` 里定义的那些回调：`createInstance`、`commitUpdate`、`appendChild` 等等。最终，React 把变更提交到 Ink 的 DOM 节点上。

**阶段二：Yoga 布局计算（layout）**

React 提交完成后，`resetAfterCommit` 被触发，调用 `onComputeLayout`。这执行 Yoga 的布局计算：

```typescript
// src/ink/ink.tsx，第239-258行（简化）
this.rootNode.onComputeLayout = () => {
  if (this.rootNode.yogaNode) {
    this.rootNode.yogaNode.setWidth(this.terminalColumns);
    this.rootNode.yogaNode.calculateLayout(this.terminalColumns);
  }
};
```

Yoga 从根节点开始，递归地计算每个节点的位置和尺寸。你在 JSX 里写的 `flexDirection="column"` 被 Yoga 解释为纵向排列，`flexGrow={1}` 被解释为占满剩余空间。计算完成后，每个节点都有了 `x`、`y`、`width`、`height`——就像 CSS 布局完成后每个元素都有了确定的位置。

**阶段三：绘制到屏幕缓冲区（paint）**

布局完成后，`renderer.ts` 开始工作。它遍历布局好的节点树，把每个节点"画"到一块内存缓冲区上。这个缓冲区是一个二维数组，每个格子存储一个字符及其样式（颜色、是否粗体、是否下划线等）。

```typescript
// src/ink/renderer.ts，第31-37行
export default function createRenderer(
  node: DOMElement,
  stylePool: StylePool,
): Renderer {
  let output: Output | undefined
  return options => {
    // ...校验 yoga 节点有效性...
    const width = Math.floor(node.yogaNode.getComputedWidth())
    const height = Math.floor(node.yogaNode.getComputedHeight())
    // ...
    renderNodeToOutput(node, output, { prevScreen })
    return { screen: output.get(), cursor, viewport }
  }
}
```

`renderNodeToOutput` 是真正干重活的地方（~1800 行）。它递归遍历每个节点，根据节点类型（Box、Text、Link 等）把字符写入缓冲区的正确位置。它还处理边框绘制、文本换行、颜色应用等细节。

**阶段四：差异对比（diff）**

有了新的屏幕缓冲区后，Ink 把它和上一帧的缓冲区做对比，找出哪些格子变了。这个对比由 `LogUpdate` 类完成，它逐行逐列比较新旧缓冲区，生成一系列"补丁"（patches）：

```typescript
// src/ink/frame.ts，第73-94行
export type Patch =
  | { type: 'stdout'; content: string }
  | { type: 'clear'; count: number }
  | { type: 'cursorMove'; x: number; y: number }
  | { type: 'styleStr'; str: string }
  // ...
```

每个 patch 代表一个最小化的终端操作：写一段文字、清几行、移动光标、切换样式。如果一帧里只有一行文字变了，diff 的结果就只有一个 patch——只更新那一行。

**阶段五：输出到终端（draw）**

最后，补丁被序列化为 ANSI 转义序列，通过 `stdout.write()` 发送到终端：

```typescript
// src/ink/ink.tsx，第735-737行
const tWrite = performance.now();
writeDiffToTerminal(this.terminal, optimized, this.altScreenActive && !SYNC_OUTPUT_SUPPORTED);
const writeMs = performance.now() - tWrite;
```

终端收到这些转义序列后，把它们解释为渲染指令：移动光标到某个位置、设置文字颜色、显示一段文字。用户就看到了更新后的界面。

### 状态变化驱动重渲染

上面描述的五个阶段，每一次状态变化都会触发。但 Ink 做了大量优化，避免不必要的重渲染：

1. **脏标记（dirty flag）**：只有实际变化的节点才会被重新绘制。如果一个 `<Text>` 的内容没变，它就会被跳过。
2. **双缓冲（double buffering）**：Ink 维护两个帧缓冲区——`frontFrame`（当前显示的）和 `backFrame`（下一帧正在绘制的）。绘制完成后交换，避免用户看到半成品。
3. **差异输出**：只发送变化的行到终端，而不是每帧都重绘整个屏幕。
4. **节流（throttle）**：渲染被限制在 `FRAME_INTERVAL_MS`（约 4ms）一帧，防止快速连续的状态变化导致过度渲染。
5. **Yoga 缓存**：Yoga 会缓存布局计算结果。如果某个子树的尺寸没变，就跳过它的重新计算。

### Ink 的基础原语

了解管线后，看看 Ink 提供了哪些基础组件供上层使用。

**`<Box>`**——终端里的矩形区域。它是最基础的布局容器，支持 Flexbox 属性（`flexDirection`、`flexGrow`、`padding` 等）。所有的布局都是通过嵌套 Box 实现的。

**`<Text>`**——终端里的文字。它支持颜色（`color="green"`）、粗体（`bold`）、斜体（`italic`）、下划线（`underline`）等样式。所有裸文本都必须放在 `<Text>` 里面——前面看到协调器里有校验。

**`useInput`**——键盘输入 hook。它把终端的 stdin（标准输入）包装成 React 友好的接口：

```typescript
// src/ink/hooks/use-input.ts，第42-92行（简化）
const useInput = (inputHandler: Handler, options: Options = {}) => {
  const { setRawMode, internal_exitOnCtrlC, internal_eventEmitter } = useStdin()

  useLayoutEffect(() => {
    if (options.isActive === false) return
    setRawMode(true)
    return () => { setRawMode(false) }
  }, [options.isActive, setRawMode])

  useEffect(() => {
    internal_eventEmitter?.on('input', handleData)
    return () => { internal_eventEmitter?.removeListener('input', handleData) }
  }, [internal_eventEmitter, handleData])
}
```

它做了两件事：开启终端的 raw mode（让终端把每个按键都立即上报，而不是等用户按回车），然后注册一个事件监听器接收按键事件。当用户按了 Ctrl+C 时，默认行为是退出程序；可以通过 `exitOnCtrlC: false` 覆盖。

**`useStdin`**——最底层的输入 hook。它暴露了 stdin 流本身，让组件可以直接读取输入。大多数情况下你不需要直接用它——`useInput` 是更高级的封装。

**`<ScrollBox>`**——可滚动的区域。终端没有原生的滚动条，Ink 自己实现了虚拟滚动：只渲染可见区域内的组件，通过 `scrollTop` 属性控制"窗口"的位置。Claude Code 的消息列表就是用 ScrollBox 实现的——它只渲染你当前看到的那几条消息，而不是把所有消息都渲染出来。

---

## 对比：如果用 Java

在 Java 世界里，要做终端 UI，传统选择是 Java Swing 或 JavaFX。它们的渲染管线和 Ink 有异曲同工之处：

```
Java Swing 的渲染管线：
  组件树 (JFrame -> JPanel -> JButton)
    -> 布局管理器 (LayoutManager: 计算每个组件的 x, y, width, height)
    -> paint(Graphics g) (逐组件绘制)
    -> 屏幕缓冲区
    -> 操作系统窗口

Ink 的渲染管线：
  组件树 (AlternateScreen -> FullscreenLayout -> Messages)
    -> Yoga 布局引擎 (计算每个节点的 x, y, width, height)
    -> renderNodeToOutput() (逐节点绘制)
    -> Screen 缓冲区 (二维字符数组)
    -> stdout (ANSI 转义序列)
```

结构几乎一模一样。区别在于目标设备：Swing 画到操作系统窗口（像素级精度），Ink 画到终端（字符级精度）。

Swing 的 `LayoutManager` 对应 Ink 的 Yoga 布局引擎。Swing 的 `paint(Graphics)` 对应 Ink 的 `renderNodeToOutput`。Swing 用 `repaint()` 触发重绘，Ink 用 `scheduleRender()`。两者都有脏标记、双缓冲、增量更新这些优化手段。

如果换到 Web 世界，更贴切的对比是 Spring MVC 的视图渲染：

```
Spring MVC：
  Model (数据)
    -> ViewResolver (选择模板)
    -> Template Engine (Thymeleaf/Freemarker：把数据填入模板)
    -> HTML 字符串
    -> HTTP Response -> 浏览器渲染

Ink：
  State (React state)
    -> Fiber Reconciler (diff 新旧状态)
    -> Yoga (计算布局)
    -> renderNodeToOutput (把组件树画成字符数组)
    -> LogUpdate (diff 新旧帧)
    -> ANSI 转义序列 -> 终端渲染
```

都是"数据 -> 模板/组件 -> 序列化 -> 输出设备"的管线。只不过 Spring 输出 HTML 给浏览器，Ink 输出 ANSI 给终端。

有一个关键的区别值得注意：Swing 是事件驱动的——按钮点击、窗口缩放，每个事件触发一次重绘。Ink 也是事件驱动的，但它的事件源更多：键盘输入、鼠标点击、终端尺寸变化、甚至 Unix 信号（SIGCONT 恢复前台运行时也会触发重绘）。Ink 在 `ink.tsx` 构造函数里注册了所有这些事件源：

```typescript
// src/ink/ink.tsx，第226-232行
if (options.stdout.isTTY) {
  options.stdout.on('resize', this.handleResize);
  process.on('SIGCONT', this.handleResume);
}
```

终端窗口大小变了（`resize`）？重新布局、重新渲染。程序从后台恢复到前台（`SIGCONT`）？清空缓冲区、全量重绘。

---

## 你能改什么

### 初学者友好的区域

**添加一个新的 UI 组件。** 在 `src/components/` 下创建一个新的 `.tsx` 文件，导出一个函数组件，使用 `<Box>` 和 `<Text>` 来组合界面。然后在 REPL 组件里引入它。这是最安全的改法——你只是在组件树里加了一个新节点，不会影响现有的渲染管线。

比如，你想在消息列表底部加一个"今日名言"的小组件：

```tsx
function DailyQuote({ quote }: { quote: string }) {
  return (
    <Box borderStyle="round" paddingX={1} marginTop={1}>
      <Text dimColor>{quote}</Text>
    </Box>
  )
}
```

然后在 REPL 的 `scrollable` 区域里加上 `<DailyQuote quote="代码是写给人看的" />`。

**改变颜色主题。** Claude Code 的主题系统在 `src/components/design-system/` 下。颜色定义在 `color.ts` 里。你可以修改颜色值来改变整个应用的外观，比如把主色调从蓝色改成紫色。这是纯配置的改动，不涉及任何渲染逻辑。

**修改组件样式。** 找到你想修改的组件（比如 `PromptInput`），调整它的 `<Box>` 和 `<Text>` 的样式属性（`padding`、`margin`、`borderStyle`、`color` 等）。这些改动只影响布局和视觉，不会破坏渲染管线。

### 危险区域

**修改协调器（reconciler.ts）。** 这是整个渲染系统的地基。协调器定义了 React 和终端之间的"协议"。如果你改错了 `createInstance` 的行为（比如忘了处理某种节点类型），React 的 Fiber 树和 Ink 的 DOM 树就会失去同步，导致界面错乱甚至崩溃。除非你非常理解 React Fiber 的工作原理，否则不要动这个文件。

**修改渲染管线（render-node-to-output.ts）。** 这个 1800 行的文件负责把每个节点"画"到缓冲区上。它处理了大量的边界情况：双宽字符（中文占两个格子）、ANSI 转义序列的嵌套、文本换行、边框绘制。改动任何逻辑都可能导致显示错位。

**修改 Yoga 布局计算。** 布局计算发生在 `onComputeLayout` 回调里。如果修改了 Yoga 节点的宽度设置或布局调用时机，可能导致整个界面崩溃——因为所有组件的位置都依赖于正确的布局结果。

**修改 diff 算法。** `LogUpdate` 的 diff 逻辑假设了一些不变量（比如光标位置的追踪、行号的连续性）。如果改动 diff 算法，可能导致终端输出乱序或闪烁。

简单地说：在组件层（`src/components/`、`src/screens/`）改动是安全的，因为你在使用已有的基础设施。在基础设施层（`src/ink/`）改动是危险的，因为你在修改别人依赖的地基。

---

## 回顾

这一章我们拆解了 React 在终端里奔跑的完整机制：

1. **Ink 是什么**：一个 React 渲染器，把 React 的输出从浏览器 DOM 替换为终端字符。
2. **Fiber 协调器**：通过 `react-reconciler` API，Ink 自定义了 React 的"宿主环境"，让 React 创建的是 Ink DOM 节点而不是浏览器 DOM 节点。
3. **渲染管线**：状态变化 -> React 协调 -> Yoga 布局计算 -> 绘制到缓冲区 -> 差异对比 -> ANSI 转义序列输出到终端。
4. **组件树**：从 `App`（三层 Provider）到 `REPL`（全屏布局、消息列表、输入框），每个组件各司其职。
5. **基础原语**：`<Box>`、`<Text>`、`useInput`、`useStdin`、`<ScrollBox>` 构成了终端 UI 开发的基石。

这整套机制让 Claude Code 能用一个声明式框架（React）来管理终端界面，获得了自动更新、组件化、状态管理等好处，同时不需要浏览器。

终端 UI 的秘密揭开了。现在我们进入 Claude Code 最核心的系统——工具。先从工具的 DNA 开始：那个统一的 Tool 接口。

---

[上一章：主入口一切的起点](./第02章-主入口一切的起点.md) | [下一章：工具的DNA](./第04章-工具的DNA.md)
