# 第 33 章：为什么自定义 Ink Fork

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

---

## 决策回顾

Claude Code 不是用 npm 的 `ink` 包——而是在 `src/ink/` 目录下维护了一个完整的自定义 fork。

源码证据：
- `src/ink/ink.tsx`——~1500 行的核心类（原版 Ink 的 `src/ink.tsx` 约 300 行）
- `src/ink/reconciler.ts`——513 行的自定义 reconciler
- `src/ink/screen.ts`——自定义 Screen 缓冲 + 三个池化结构
- `src/ink/log-update.ts`——自定义差异引擎
- `src/ink/optimizer.ts`——补丁优化器
- `src/ink/render-node-to-output.ts`——blit 优化

原版 Ink 没有的特性：
1. **ScrollBox**：虚拟滚动——长对话必需
2. **双缓冲差异引擎**：前后帧交换 + 单元格级 diff
3. **Blit 优化**：不变子树直接复制
4. **池化内存**：CharPool / StylePool / HyperlinkPool
5. **选择高亮**：后处理通道修改 Screen 缓冲
6. **损伤追踪**：只在 damage 区域内比较

---

## 被否方案

### 方案 A：使用原版 Ink + 贡献上游

```typescript
// 被 否 决 的 方 案
import { render, Box, Text } from 'ink'
```

**问题**：
- 原版 Ink 的渲染性能不够——每帧全屏重绘
- 缺少 ScrollBox——长对话无法使用
- 贡献上游的 PR 审核周期长——产品需求等不及

### 方案 B：从零开始写终端渲染

```typescript
// 被 否 决 的 方 案
function renderToTerminal(component: Component) {
  // 直接操作 ANSI 转义序列
}
```

**问题**：放弃 React 组件模型——回到方案 A 的问题。

### 方案 C：使用其他终端 UI 框架（blessed、terminal-kit）

**问题**：这些框架不支持 React——丧失声明式 UI 的好处。

---

## 后果分析

### 好处

1. **渲染性能**：blit + 差异引擎 + 池化内存 → 流式输出时无卡顿
2. **功能完整**：ScrollBox、选择、搜索高亮等复杂 UI
3. **自由修改**：不受上游发布周期约束
4. **终端兼容性**：可以针对特定终端做优化

### 麻烦

1. **维护成本**：需要跟进 React 版本更新、Yoga 更新
2. **社区隔离**：不能直接使用 npm Ink 生态的组件
3. **调试困难**：自定义 reconciler 的 bug 需要深入理解 React 内部机制
4. **代码量**：`src/ink/` 目录约 5000+ 行——显著增加代码库大小

---

## 横向对比

| 工具 | 终端渲染方案 | 自定义程度 |
|------|------------|----------|
| **Claude Code** | 自定义 Ink fork | 高——reconciler + diff engine 重写 |
| **Aider** | prompt_toolkit (Python) | 低——使用标准库 |
| **Warp** | Metal/GPU 渲染 | 极高——完全自研 |
| **npm Ink** | 原版 Ink | 无——直接使用 |

---

## 你的判断

1. 自定义 fork 的维护成本是否可以通过贡献上游来减少？
2. 如果 React 推出重大版本更新（如新的并发特性），自定义 reconciler 的迁移成本有多大？
3. 未来是否有更好的终端 UI 框架出现，使得自定义 fork 不再必要？

---

**设计原则标签**：能力放大——minimal scaffolding + maximal harness。保留 React 组件模型（脚手架），重写渲染引擎（利用最大化）。
