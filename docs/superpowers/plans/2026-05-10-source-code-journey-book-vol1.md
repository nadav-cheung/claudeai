# 《跟着消息走》卷一：消息的旅程 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成卷一的全部 12 章内容，形成一本编程新手能跟着读下来的叙事体源码分析书。

**Architecture:** 每章遵循「场景钩子 → 叙事段落 → 源码片段 → 生活类比 → TS 概念引入 → 下一站预告」的结构。每章先研究源码，再写内容，最后验证源码引用准确性。

**Tech Stack:** Markdown 书写，引用 TypeScript 源码（Bun 运行时）

**Spec:** `docs/superpowers/specs/2026-05-10-source-code-journey-book-design.md`

---

## File Structure

```
teaching/v2/
├── README.md                           ← 全书入口（卷一阶段只写卷一简介）
└── 卷一-消息的旅程/
    ├── 第01章-你和AI的第一次对话.md
    ├── 第02章-回车键之后发生了什么.md
    ├── 第03章-消息被装进信封.md
    ├── 第04章-信封飞向远方.md
    ├── 第05章-文字一个字一个字地回来.md
    ├── 第06章-AI说要执行一条命令.md
    ├── 第07章-命令真的被执行了.md
    ├── 第08章-你确定吗.md
    ├── 第09章-结果回到AI手中.md
    ├── 第10章-对话越来越长.md
    ├── 第11章-屏幕上的每一帧.md
    └── 第12章-你的第一次追踪.md
```

---

### Task 0: 创建目录结构和 README

**Files:**
- Create: `teaching/v2/README.md`
- Create: `teaching/v2/卷一-消息的旅程/` (directory)

- [ ] **Step 1: 创建目录**

```bash
mkdir -p teaching/v2/卷一-消息的旅程
```

- [ ] **Step 2: 写 README.md**

创建 `teaching/v2/README.md`，内容：

```markdown
# 跟着消息走：Claude Code 源码的旅程

> 从你按下回车的那一刻起，你的消息将穿越一个完整的系统。
> 本书带你跟着它走完这段旅程。

## 关于本书

一本以《网络是怎么连接的》风格写的源码分析书。不按模块组织，
而是跟着一条消息穿越 Claude Code 的每一层。

## 四卷结构

| 卷 | 书名 | 读完你能做什么 |
|---|------|-------------|
| 卷一 | 消息的旅程 | 追踪请求流程、定位 bug、修小问题 |
| 卷二 | 引擎室的秘密 | 理解设计模式、读懂任意模块 |
| 卷三 | 造物主的工坊 | 独立添加新功能模块 |
| 卷四 | 架构师的棋盘 | 参与架构讨论、理解设计权衡 |

## 阅读前提

- 你会用终端（命令行）
- 你写过代码（任何语言都行）
- 你不需要懂 TypeScript

## 开始阅读

👉 [卷一：消息的旅程](./卷一-消息的旅程/第01章-你和AI的第一次对话.md)
```

- [ ] **Step 3: Commit**

```bash
git add teaching/v2/
git commit -m "book(v2): scaffold directory structure and README"
```

---

### Task 1: 第01章 — 你和 AI 的第一次对话

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第01章-你和AI的第一次对话.md`

**源码研究：** 无（本章不涉及具体源码，是全书的序章）

**章节内容规格：**

- **场景钩子**："你刚刚在终端里输入了一行字。这行字即将展开一段旅程。"
- **本章做什么**：
  1. 什么是 Claude Code（用类比：一个住在你终端里的 AI 助手）
  2. 安装和第一次运行（简要步骤）
  3. 你输入"帮我修个 bug"，AI 回答了。但这中间发生了什么？
  4. 为什么要读源码（类比：知道汽车引擎怎么工作，开车更有底气）
  5. 什么是"源码"（给编程新手解释：源码就是程序的图纸）
  6. 这本书怎么读（叙事旅程的风格说明）
- **不引入 TS 概念**（本章纯叙事）
- **生活类比**：源码 = 房子的蓝图，AI 助手 = 一个能操作电脑的助手
- **结尾钩子**："在下一章，我们会跟着你按下回车后的那零点几秒，看看你的消息去了哪里。"
- **篇幅**：2500-3000 字（序章略短）

- [ ] **Step 1: 写章节初稿**

写 `teaching/v2/卷一-消息的旅程/第01章-你和AI的第一次对话.md`，按上述规格写完整章节内容。

- [ ] **Step 2: 审校**

检查：
- 没有假设读者了解 TypeScript
- 没有假设读者了解 CLI 开发
- 生活类比恰当
- 结尾钩子引向第 02 章

- [ ] **Step 3: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第01章-你和AI的第一次对话.md
git commit -m "book(v2): write chapter 01 - first conversation"
```

---

### Task 2: 第02章 — 回车键之后发生了什么

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第02章-回车键之后发生了什么.md`

**源码研究（必须先读）：**
- `src/main.tsx` L585-700（`main()` 函数入口和初始化）
- `src/main.tsx` L884-960（`run()` 函数，Commander 命令树）
- `src/replLauncher.tsx`（全文 22 行）
- `src/screens/REPL.tsx` L526-620（REPL 组件 props 和主函数签名）

**章节内容规格：**

- **场景钩子**："你的手指按下了回车键。在屏幕上，这只是换了一行。但在程序内部，一场接力赛刚刚开始。"
- **叙事线**：
  1. 回车键触发的事件 → REPL 组件捕获输入
  2. 程序的入口：main.tsx 的 main() 函数（解释"入口"的概念）
  3. 初始化做了什么（简述：加载配置、解析参数、启动 REPL）
  4. REPL 是什么（Read-Eval-Print Loop，类比：你和 AI 轮流说话的桌子）
  5. 你的消息被放进了变量里（解释"变量"和"字符串"）
- **引入 TS 概念**：
  - `function`：一段有名字的代码块（类比：菜谱）
  - `async/await`：等待某事完成（类比：等外卖）
  - `import`：从别的文件拿工具来用（类比：从工具箱里拿螺丝刀）
- **代码片段**（选取 main.tsx 中的关键几行，附中文注释）：
  - `main()` 函数签名和前几行
  - `launchRepl()` 调用
- **生活类比**：main() = 大楼的正门，import = 从仓库搬工具
- **结尾钩子**："你的消息现在是一个字符串，躺在程序的内存里。但它还不是 AI 能理解的格式——它需要被装进一个信封。"
- **篇幅**：3000-4000 字

- [ ] **Step 1: 阅读源码**

读取上述文件和行号范围，理解 main() 的启动流程和 REPL 的角色。

- [ ] **Step 2: 写章节初稿**

按规格写完整章节。代码片段必须来自真实源码，标注文件路径和行号。

- [ ] **Step 3: 验证源码引用**

确认：
- main() 函数确实在 main.tsx L585
- launchRepl() 确实在 replLauncher.tsx L12
- 代码片段与源码一致

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第02章-回车键之后发生了什么.md
git commit -m "book(v2): write chapter 02 - after pressing enter"
```

---

### Task 3: 第03章 — 消息被装进信封

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第03章-消息被装进信封.md`

**源码研究：**
- `src/services/api/claude.ts` L588-650（`userMessageToMessageParam()`）
- `src/services/api/claude.ts` L3213-3300（`buildSystemPromptBlocks()`）
- `src/services/api/claude.ts` L3063-3100（`addCacheBreakpoints()`）

**章节内容规格：**

- **场景钩子**："你的消息'帮我修个 bug'现在是一串文字。但它不能就这样被扔给 AI——它需要被装进一个标准信封。"
- **叙事线**：
  1. AI API 需要什么格式的消息（Message 对象）
  2. 消息有角色：user（你说的）、assistant（AI 说的）、tool（工具结果）
  3. system prompt：AI 的"角色说明书"（类比：给新员工的入职手册）
  4. 消息数组：整个对话历史（类比：聊天记录）
  5. 你的消息如何被包装成 `{ role: "user", content: "帮我修个 bug" }`
- **引入 TS 概念**：
  - 类型（type）：数据的形状（类比：信封的模板）
  - 接口（interface）：一份合同（类比："我保证这个对象有这些字段"）
  - JSON：数据的通用语言（类比：国际快递单）
- **代码片段**：
  - `userMessageToMessageParam()` 的签名和关键逻辑
  - 消息类型的简化定义
- **生活类比**：消息 = 信件，role = 寄件人类型，消息数组 = 邮袋
- **结尾钩子**："信封装好了。现在它需要被寄出去——穿越网络，到达 Anthropic 的服务器。"
- **篇幅**：3000-4000 字

- [ ] **Step 1: 阅读源码**

读取 `src/services/api/claude.ts` 中消息构建相关代码。

- [ ] **Step 2: 写章节初稿**

- [ ] **Step 3: 验证源码引用**

确认 `userMessageToMessageParam()` 在 L588，函数签名和逻辑与源码一致。

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第03章-消息被装进信封.md
git commit -m "book(v2): write chapter 03 - message packaging"
```

---

### Task 4: 第04章 — 信封飞向远方

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第04章-信封飞向远方.md`

**源码研究：**
- `src/services/api/claude.ts` L709-760（`queryModelWithoutStreaming()` 和 `queryModelWithStreaming()` 签名）
- `src/services/api/withRetry.ts`（全文，重试逻辑）
- `src/services/api/claude.ts` L1-50（imports，看 Anthropic SDK 的使用）

**章节内容规格：**

- **场景钩子**："你的消息被装进了信封。现在，这个信封要穿越互联网，飞到数千公里外的服务器。"
- **叙事线**：
  1. API 是什么（类比：餐厅的窗口，你递单子进去，菜从里面出来）
  2. HTTP 请求：信封的投递方式（简述 POST、headers、auth）
  3. Anthropic SDK：一个帮你寄信的快递员（不需要自己写 HTTP）
  4. 认证：怎么证明你有权寄信（API key 的概念）
  5. 如果网络断了怎么办（简述重试机制的存在，不深入）
- **引入 TS 概念**：
  - Promise：一个"我以后给你结果"的承诺（类比：取餐号码牌）
  - try/catch：万一出错了怎么办（类比：备选方案）
- **代码片段**：
  - `queryModelWithStreaming()` 的签名
  - SDK 调用的简化形式
- **生活类比**：API = 餐厅窗口，SDK = 外卖平台，认证 = 会员卡
- **结尾钩子**："请求已经发出了。但 AI 不会一口气说完——它的回答会一个字一个字地流回来。"
- **篇幅**：3000-4000 字

- [ ] **Step 1: 阅读源码**

读取 `src/services/api/claude.ts` 的 API 调用部分和 `withRetry.ts`。

- [ ] **Step 2: 写章节初稿**

- [ ] **Step 3: 验证源码引用**

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第04章-信封飞向远方.md
git commit -m "book(v2): write chapter 04 - sending to API"
```

---

### Task 5: 第05章 — 文字一个字一个字地回来

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第05章-文字一个字一个字地回来.md`

**源码研究：**
- `src/services/api/claude.ts` L752-900（`queryModelWithStreaming()` 的流式处理核心）
- `src/services/api/claude.ts` L2898-2950（`cleanupStream()` 和 `updateUsage()`）

**章节内容规格：**

- **场景钩子**："你盯着屏幕，AI 的回答开始一个字一个字地出现。像有人在屏幕上打字。这不是魔法——这是'流式响应'。"
- **叙事线**：
  1. 为什么不一次性返回？（类比：等一整本书写完再读 vs 边写边读）
  2. SSE（Server-Sent Events）：服务器推着给你数据
  3. 每一个"字"其实是一个 token（解释 token 概念）
  4. 流式数据如何在代码中被接收（async generator）
  5. 每收到一个 token，屏幕就更新一次
- **引入 TS 概念**：
  - AsyncIterable / yield：一边生产一边消费（类比：水管里的水）
  - generator 函数 `function*`：一个能暂停的函数
- **代码片段**：
  - `queryModelWithStreaming()` 中 yield 的使用
  - 流式事件解析的简化版本
- **生活类比**：流式 = 水管，token = 水滴，一次性返回 = 水桶
- **结尾钩子**："AI 在流式回答中说了一句话。但有时候，AI 不只是说话——它说'我要执行一条命令'。"
- **篇幅**：3000-4000 字

- [ ] **Step 1: 阅读源码**

读取 `queryModelWithStreaming()` 的流式处理逻辑。

- [ ] **Step 2: 写章节初稿**

- [ ] **Step 3: 验证源码引用**

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第05章-文字一个字一个字地回来.md
git commit -m "book(v2): write chapter 05 - streaming response"
```

---

### Task 6: 第06章 — AI 说要执行一条命令

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第06章-AI说要执行一条命令.md`

**源码研究：**
- `src/services/tools/toolExecution.ts` L1-50（imports，看 tool_use 类型）
- `src/services/tools/toolExecution.ts` L337-450（`runToolUse()` 的前半段：解析 tool_use 块）
- `src/Tool.ts` L1-60（Tool 类型定义的开头）

**章节内容规格：**

- **场景钩子**："AI 的回答不是普通的文字。在流式数据中，出现了一个特殊的标记：`tool_use`。AI 想执行一条命令。"
- **叙事线**：
  1. 模型的回答不只是文字——还可能是"动作请求"
  2. tool_use 块的结构：工具名 + 输入参数
  3. 如何从流式响应中识别出 tool_use（type guard）
  4. 工具分发：根据名字找到对应的工具
  5. "工具"是什么概念（类比：AI 是大脑，工具是手）
- **引入 TS 概念**：
  - 联合类型（union type）：一个值可能是 A 也可能是 B（类比：快递可能是信件也可能是包裹）
  - type guard：判断"这是 A 还是 B"（类比：看快递单上的类型标记）
  - 字符串字面量类型：不只是一个 string，而是特定的 string
- **代码片段**：
  - tool_use 事件的结构示例
  - `runToolUse()` 接收 tool_use 块的入口代码
- **生活类比**：tool_use = 大脑给手下达的指令，工具名 = 指令类型
- **结尾钩子**："AI 说它要执行一条 Bash 命令。但这条命令会怎么被执行？谁来做这件事？"
- **篇幅**：3000-4000 字

- [ ] **Step 1: 阅读源码**

读取 toolExecution.ts 的 tool_use 解析逻辑。

- [ ] **Step 2: 写章节初稿**

- [ ] **Step 3: 验证源码引用**

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第06章-AI说要执行一条命令.md
git commit -m "book(v2): write chapter 06 - tool_use detection"
```

---

### Task 7: 第07章 — 命令真的被执行了

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第07章-命令真的被执行了.md`

**源码研究：**
- `src/tools/BashTool/BashTool.tsx` L420-550（BashTool 定义和 execute 入口）
- `src/tools/BashTool/BashTool.tsx` L264-320（BashToolInput 类型定义）
- `src/tools/BashTool/prompt.ts` 前 30 行（BashTool 的 prompt 描述）

**章节内容规格：**

- **场景钩子**："AI 决定要执行 `git status`。这不是一个模拟——这条命令会在你的电脑上真实地运行。"
- **叙事线**：
  1. BashTool：Claude Code 的"双手"（类比：工具箱里的扳手）
  2. 输入：`{ command: "git status" }`（Zod 验证输入格式）
  3. 子进程：程序如何在你的电脑上运行命令（child_process）
  4. 输出：stdout 和 stderr 被捕获（类比：命令的"嘴"和"错误喇叭"）
  5. 超时和中断：如果命令跑太久怎么办
- **引入 TS 概念**：
  - child_process：让程序执行另一个程序（类比：你让别人帮你跑腿）
  - Buffer：二进制数据的容器（类比：水桶）
  - 泛型 `<Input, Output>`：一个模具，可以放不同的材料
- **代码片段**：
  - BashToolInput 类型定义
  - execute 函数的简化版本
- **生活类比**：子进程 = 你叫别人帮你做事，stdout = 那个人告诉你结果
- **结尾钩子**："等一下——在命令被执行之前，有一道关卡。程序会问你：'你确定要让 AI 执行这条命令吗？'"
- **篇幅**：3500-4500 字

- [ ] **Step 1: 阅读源码**

读取 BashTool 的核心实现代码。

- [ ] **Step 2: 写章节初稿**

- [ ] **Step 3: 验证源码引用**

确认 BashTool 定义在 BashTool.tsx L420，BashToolInput 在 L264。

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第07章-命令真的被执行了.md
git commit -m "book(v2): write chapter 07 - command execution"
```

---

### Task 8: 第08章 — 你确定吗

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第08章-你确定吗.md`

**源码研究：**
- `src/utils/permissions/permissions.ts` L473-550（`hasPermissionsToUseTool()` 入口）
- `src/utils/permissions/permissions.ts` L137-200（`createPermissionRequestMessage()`）
- `src/utils/permissions/PermissionMode.ts`（全文 141 行，权限模式定义）

**章节内容规格：**

- **场景钩子**："AI 要在你的电脑上执行命令。但程序停了下来，问你：'你确定吗？'这个停顿不是多余的——它是你的安全网。"
- **叙事线**：
  1. 为什么需要权限系统（类比：你不希望别人随便用你的电脑）
  2. 三种权限状态：allow（允许）、deny（拒绝）、ask（问你）
  3. 权限模式：plan（谨慎）、auto（自动但有限制）、yolo（放手干）
  4. 一条命令如何被分类为"安全"或"危险"
  5. 用户确认对话框的机制
- **引入 TS 概念**：
  - 枚举（enum）或联合字符串类型：有限的选项列表
  - 模式匹配：根据类型走不同的路
- **代码片段**：
  - PermissionMode 的类型定义
  - `hasPermissionsToUseTool()` 的简化流程
- **生活类比**：权限 = 门卫，allow = 门卫认识你直接放行，ask = 门卫要你出示证件，deny = 门卫拦住你
- **结尾钩子**："权限检查通过了（或者你点了确认）。命令执行完毕，结果需要被送回给 AI。"
- **篇幅**：3000-4000 字

- [ ] **Step 1: 阅读源码**

读取权限系统的核心流程。

- [ ] **Step 2: 写章节初稿**

- [ ] **Step 3: 验证源码引用**

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第08章-你确定吗.md
git commit -m "book(v2): write chapter 08 - permission system"
```

---

### Task 9: 第09章 — 结果回到 AI 手中

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第09章-结果回到AI手中.md`

**源码研究：**
- `src/services/tools/toolExecution.ts` L450-600（`runToolUse()` 后半段：组装 tool_result）
- `src/services/tools/toolExecution.ts` L599-700（`checkPermissionsAndCallTool()`）

**章节内容规格：**

- **场景钩子**："命令执行完了。结果——可能是一段输出，也可能是报错——现在需要被送回给 AI。"
- **叙事线**：
  1. 工具执行的结果（tool_result）如何被组装
  2. result 被追加到消息数组中，角色是 "tool"
  3. 整个消息数组（用户问题 + AI 回答 + 工具调用 + 工具结果）再次被发送给 API
  4. AI 看到结果后继续回答——这就是"对话循环"
  5. 多轮工具调用：AI 可能再次要求执行命令
- **引入 TS 概念**：
  - 消息循环 / while 循环：重复做某事直到条件满足
  - 数组的 push 操作：往列表里加东西
- **代码片段**：
  - tool_result 的结构
  - 对话循环的简化伪代码
- **生活类比**：tool_result = 你给 AI 的回信，对话循环 = 你和 AI 轮流写信
- **结尾钩子**："对话在继续。但随着工具调用越来越多，对话变得很长。AI 的记忆力是有限的……"
- **篇幅**：3000-4000 字

- [ ] **Step 1: 阅读源码**

读取 tool_result 组装和对话循环逻辑。

- [ ] **Step 2: 写章节初稿**

- [ ] **Step 3: 验证源码引用**

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第09章-结果回到AI手中.md
git commit -m "book(v2): write chapter 09 - tool result and conversation loop"
```

---

### Task 10: 第10章 — 对话越来越长

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第10章-对话越来越长.md`

**源码研究：**
- `src/services/compact/autoCompact.ts` L72-160（`getAutoCompactThreshold()` 和 `shouldAutoCompact()`）
- `src/services/compact/compact.ts` L387-450（`compactConversation()` 入口）
- `src/services/compact/compact.ts` L330-387（`buildPostCompactMessages()` 简化）

**章节内容规格：**

- **场景钩子**："你的对话已经很长了。用户消息、AI 回答、工具调用、工具结果……加起来可能有好几万字。但 AI 的'记忆'是有限的。"
- **叙事线**：
  1. 上下文窗口：AI 一次能"看到"多少字（类比：一块白板，写满了就得擦）
  2. 当消息快要超出窗口时，系统自动触发"压缩"
  3. 压缩做了什么：把旧对话总结成一段摘要（类比：把一本书缩写成一段话）
  4. 压缩后的消息数组变短了，但关键信息被保留
  5. 什么时候触发压缩（阈值判断）
- **引入 TS 概念**：
  - 数组长度和阈值判断：`if (length > threshold)`
  - 条件逻辑：根据条件做不同的事
- **代码片段**：
  - `shouldAutoCompact()` 的简化逻辑
  - 压缩前后的消息数组对比（伪代码）
- **生活类比**：上下文窗口 = 一块白板，压缩 = 把旧笔记缩写成摘要
- **结尾钩子**："消息在系统内部流转了这么久，但你还什么都看不到。你的屏幕上发生了什么？"
- **篇幅**：3000-4000 字

- [ ] **Step 1: 阅读源码**

读取压缩系统的触发和执行逻辑。

- [ ] **Step 2: 写章节初稿**

- [ ] **Step 3: 验证源码引用**

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第10章-对话越来越长.md
git commit -m "book(v2): write chapter 10 - context compression"
```

---

### Task 11: 第11章 — 屏幕上的每一帧

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第11章-屏幕上的每一帧.md`

**源码研究：**
- `src/ink.ts`（全文 85 行）
- `src/components/App.tsx`（全文 55 行）
- `src/screens/REPL.tsx` L526-650（REPL 组件的开头和渲染结构）
- `src/ink/` 目录结构（列出文件看 Ink 适配层的范围）

**章节内容规格：**

- **场景钩子**："你的终端上出现了 AI 的回答、工具调用的动画、权限确认的对话框。这些东西是怎么被画在终端上的？"
- **叙事线**：
  1. 终端不只是黑底白字——它可以显示颜色、进度条、动画
  2. React：一个"画 UI"的框架（通常用在网页上，这里用在了终端）
  3. Ink = React for CLI（把 React 的能力搬到了终端）
  4. 组件：UI 的积木块（类比：乐高的每个零件）
  5. 状态变化时，屏幕自动更新（React 的核心思想）
  6. 从 App → REPL → 具体的消息渲染组件
- **引入 TS 概念**：
  - JSX：用类似 HTML 的语法写 UI（`<Box><Text>你好</Text></Box>`）
  - 组件（component）：一个返回 UI 的函数
  - props：组件的参数（类比：函数的参数）
- **代码片段**：
  - App 组件的简化代码
  - REPL 组件的渲染结构（简化）
- **生活类比**：React = 画师，组件 = 画稿模板，状态 = 模特的变化
- **结尾钩子**："现在你知道一条消息从头到尾经历了什么。是时候打开源码，亲手追踪一次了。"
- **篇幅**：3500-4500 字

- [ ] **Step 1: 阅读源码**

读取 Ink 适配层、App 组件和 REPL 组件。

- [ ] **Step 2: 写章节初稿**

- [ ] **Step 3: 验证源码引用**

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第11章-屏幕上的每一帧.md
git commit -m "book(v2): write chapter 11 - terminal UI rendering"
```

---

### Task 12: 第12章 — 你的第一次追踪

**Files:**
- Create: `teaching/v2/卷一-消息的旅程/第12章-你的第一次追踪.md`

**源码研究：** 本章是实战章节，综合引用前面所有章节涉及的源码。

**章节内容规格：**

- **场景钩子**："你读完了消息的旅程。现在，你要亲手追踪一次。"
- **叙事线**：
  1. 打开源码：从 GitHub 克隆仓库或打开本地目录
  2. 设置断点：在 main.tsx 的 main() 处停下
  3. 追踪一次完整的请求：输入 → API 调用 → tool_use → 执行 → 结果 → 显示
  4. 用 console.log 在关键位置打印信息
  5. 定位一个小问题：比如"为什么这个工具没有被加载？"
  6. 实际上就是定位 bug 的过程
- **目标**：读者完成后能够独立追踪请求流程、定位 bug
- **代码片段**：
  - 断点设置的位置列表（带文件路径和行号）
  - console.log 插入的示例
- **结尾**：卷一总结 + 对卷二的预告
  - "你已经看到了消息旅途中'发生了什么'。但你还没打开引擎盖——这些系统内部是怎么设计的？"
  - 👉 卷二：引擎室的秘密

- [ ] **Step 1: 写章节初稿**

综合前面 11 章的知识，写一个实战指南。

- [ ] **Step 2: 审校**

确认：
- 断点位置的行号与源码一致
- 追踪流程覆盖了卷一所有关键节点
- 新手能照着做

- [ ] **Step 3: Commit**

```bash
git add teaching/v2/卷一-消息的旅程/第12章-你的第一次追踪.md
git commit -m "book(v2): write chapter 12 - your first trace"
```

---

### Task 13: 最终审校和章节交叉链接

**Files:**
- Modify: `teaching/v2/卷一-消息的旅程/*.md`（所有 12 章，添加交叉链接）

- [ ] **Step 1: 添加每章末尾的导航链接**

每章末尾添加：
```
---

⬅️ [上一章](./第XX章-xxx.md) | [目录](../README.md) | ➡️ [下一章](./第XX+1章-xxx.md)
```

- [ ] **Step 2: 检查所有源码引用**

对每章中的文件路径和行号做最终验证：
- `src/main.tsx` L585 — main()
- `src/replLauncher.tsx` L12 — launchRepl()
- `src/services/api/claude.ts` L588 — userMessageToMessageParam()
- `src/services/api/claude.ts` L752 — queryModelWithStreaming()
- `src/services/tools/toolExecution.ts` L337 — runToolUse()
- `src/tools/BashTool/BashTool.tsx` L420 — BashTool
- `src/utils/permissions/permissions.ts` L473 — hasPermissionsToUseTool()
- `src/services/compact/compact.ts` L387 — compactConversation()
- `src/screens/REPL.tsx` L572 — REPL()

如果行号已变（源码更新），更新引用。

- [ ] **Step 3: 全卷通读检查**

检查：
- 叙事线是否连贯（消息的旅程不中断）
- TS 概念引入是否渐进（不跳步、不提前使用未解释的概念）
- 生活类比是否恰当（不牵强）
- 每章篇幅在 3000-5000 字范围内

- [ ] **Step 4: Commit**

```bash
git add teaching/v2/
git commit -m "book(v2): volume 1 final review and cross-links"
```

---

## Self-Review

**1. Spec coverage:** 12 chapters in the spec each have a corresponding task (Tasks 1-12). Setup (Task 0) and final review (Task 13) are included. Volume-wide README is Task 0.

**2. Placeholder scan:** No TBDs or "implement later" patterns. Each task specifies exact source files, line ranges, content specs, and commit messages.

**3. Type consistency:** Not applicable (this is a content project, not a code project). The source code file paths and function names are consistent across tasks based on the research phase.
