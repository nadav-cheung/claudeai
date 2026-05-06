# A02 - UI 渲染代码详解

> **本文档目标**：深入解析 Claude Code Ink 终端 UI 渲染系统的核心代码，包括自定义 Reconciler、Yoga 布局、渲染管线等。

---

## 1. 渲染入口：createRoot()

**文件**：`src/ink/root.ts:30-80`

**功能**：创建 Ink 渲染根节点。

```typescript
// src/ink/root.ts:30
export async function createRoot(
  options: RenderOptions = {}
): Promise<Root> {
  // 1. 创建 React Reconciler
  const reconciler = createReconciler({
    appendChild,
    removeChild,
    insertBefore,
    createInstance,
    createTextInstance,
    commitUpdate,
    // ...
  })

  // 2. 创建容器
  const container = createContainer()

  // 3. 创建根节点
  const root = reconciler.createRoot(container)

  // 4. 返回 Root 接口
  return {
    render: (node: ReactNode) => {
      // 包裹 ThemeProvider
      const themedNode = createElement(ThemeProvider, null, node)
      reconciler.update(themedNode, root)
    },
    unmount: () => reconciler.destroy(root),
  }
}
```

---

## 2. 自定义 Reconciler

**文件**：`src/ink/reconciler.ts:50-150`

**功能**：创建 React 到终端的自定义渲染器。

```typescript
// src/ink/reconciler.ts:50
function createReconciler(config: ReconcilerConfig) {
  return reconciler({
    appendChild(parent, child) {
      appendChildNode(parent, child)
    },

    removeChild(parent, child) {
      removeChildNode(parent, child)
    },

    insertBefore(parent, child, before) {
      insertBeforeNode(parent, child, before)
    },

    createInstance(type, props) {
      return createNode(type, props)
    },

    createTextInstance(text) {
      return createTextNode(text)
    },

    commitUpdate(node, oldProps, newProps) {
      if (node.nodeName === 'text') {
        updateTextContent(node, newProps)
      } else {
        updateNodeAttributes(node, oldProps, newProps)
      }
    },
  })
}
```

---

## 3. 虚拟 DOM 节点

**文件**：`src/ink/dom.ts:30-100`

**功能**：定义终端专用的 DOM 节点类型。

```typescript
// src/ink/dom.ts:30
export interface DOMElement {
  nodeName: ElementNames  // 'box' | 'text' | 'root'
  attributes: DOMNodeAttribute
  style: Styles
  yogaNode: Yoga.YogaNode  // Yoga 布局节点
  childNodes: (DOMElement | TextNode)[]
  // ...
}

export interface TextNode {
  nodeName: '#text'
  textContent: string
  yogaNode: Yoga.YogaNode
  style: TextStyles
}

export function createNode(
  type: string,
  props: NodeProps
): DOMElement {
  const yogaNode = Yoga.NodeBuilder.create()

  return {
    nodeName: type,
    attributes: {},
    style: parseStyle(props.style || {}),
    yogaNode,
    childNodes: [],
  }
}
```

---

## 4. Yoga 布局

**文件**：`src/ink/dom.ts:100-150`

**功能**：将 CSS 样式映射到 Yoga 布局属性。

```typescript
// src/ink/dom.ts:100
function setStyle(node: DOMElement, style: Styles): void {
  const yogaNode = node.yogaNode

  // Flexbox 方向
  if (style.flexDirection === 'row') {
    yogaNode.setFlexDirection(Yoga.FLEX_DIRECTION_ROW)
  } else if (style.flexDirection === 'column') {
    yogaNode.setFlexDirection(Yoga.FLEX_DIRECTION_COLUMN)
  }

  // 对齐
  if (style.justifyContent === 'center') {
    yogaNode.setJustifyContent(Yoga.JUSTIFY_CENTER)
  } else if (style.justifyContent === 'space-between') {
    yogaNode.setJustifyContent(Yoga.JUSTIFY_SPACE_BETWEEN)
  }

  // 边距和内边距
  yogaNode.setPadding(Yoga.EDGE_TOP, style.paddingTop || 0)
  yogaNode.setPadding(Yoga.EDGE_BOTTOM, style.paddingBottom || 0)
  // ...

  // 宽高
  if (style.width) {
    yogaNode.setWidth(Yoga.parseMetric(style.width))
  }
  if (style.height) {
    yogaNode.setHeight(Yoga.parseMetric(style.height))
  }

  // Flex
  if (style.flex) {
    yogaNode.setFlex(style.flex)
  }
}
```

---

## 5. 渲染到终端

**文件**：`src/ink/renderer.ts:50-120`

**功能**：将布局后的 DOM 树渲染为 ANSI 字符串。

```typescript
// src/ink/renderer.ts:50
export function renderToOutput(
  root: DOMElement,
  terminalWidth: number,
  terminalHeight: number
): string {
  // 1. 计算 Yoga 布局
  root.yogaNode.calculateLayout(
    terminalWidth,
    terminalHeight,
    Yoga.DIRECTION_LTR
  )

  // 2. 递归渲染节点
  const output = renderNode(root, { x: 0, y: 0 })

  return output
}

function renderNode(
  node: DOMElement | TextNode,
  position: Position
): string {
  if (node.nodeName === '#text') {
    // 文本节点直接返回内容
    return renderText(node)
  }

  // 获取节点布局信息
  const layout = node.yogaNode.getLayout()
  const { width, height } = layout

  // 渲染子节点
  let output = ''
  for (const child of node.childNodes) {
    output += renderNode(child, {
      x: position.x + layout.left,
      y: position.y + layout.top,
    })
  }

  // 如果有背景色，渲染背景
  if (node.style.backgroundColor) {
    output = renderBackground(node, layout) + output
  }

  return output
}
```

---

## 6. 终端 I/O

**文件**：`src/ink/termio/termio.ts:30-80`

**功能**：管理终端输入输出的底层操作。

```typescript
// src/ink/termio/termio.ts:30
export class TermIO {
  private originalStty?: SttyState

  // 启用原始模式（用于捕获按键）
  enableRawMode(): void {
    this.originalStty = tty.setRawMode()
  }

  // 恢复终端状态
  disableRawMode(): void {
    if (this.originalStty) {
      tty.restore(this.originalStty)
    }
  }

  // 读取单个按键
  readKey(): KeyEvent {
    const buffer = Buffer.alloc(10)
    const bytesRead = fs.readSync(STDIN_FD, buffer, 0, 10)
    return parseKeyEvent(buffer.slice(0, bytesRead))
  }

  // 写入输出
  write(output: string): void {
    process.stdout.write(ansiProcessor.process(output))
  }
}
```

---

## 7. 关键源码文件索引

| 文件 | 关键函数/类 | 说明 |
|------|-----------|------|
| `src/ink/root.ts` | `createRoot()` | 创建渲染根 |
| `src/ink/reconciler.ts` | `createReconciler()` | 自定义 Reconciler |
| `src/ink/dom.ts` | `DOMElement`, `createNode()` | 虚拟 DOM |
| `src/ink/dom.ts` | `setStyle()` | Yoga 布局映射 |
| `src/ink/renderer.ts` | `renderToOutput()` | 渲染为 ANSI |
| `src/ink/renderer.ts` | `renderNode()` | 节点渲染 |
| `src/ink/termio/termio.ts` | `TermIO` | 终端 I/O |
| `src/ink/termio/dec.ts` | DEC modes | DEC 私有模式 |
| `src/components/design-system/` | `ThemedBox`, `ThemedText` | 主题组件 |
