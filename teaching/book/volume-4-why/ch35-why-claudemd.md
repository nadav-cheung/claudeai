# 第 35 章：为什么 CLAUDE.md 和 MEMORY.md 是指令与记忆系统

> 源码验证日期：2026-05-15，基于 commit `0d81bb6`

---

## 决策回顾

Claude Code 用**普通文本文件**（`.md` 文件）存储用户指令和自动记忆——不是数据库，不是 JSON 配置，不是环境变量。

源码证据：
- `src/utils/claudemd.ts`——~1200 行的 CLAUDE.md 加载逻辑
- `src/memdir/memdir.ts`——自动记忆系统
- `src/context.ts:155`——`getUserContext()` memoized 加载
- 四级加载层级：Managed → User → Project → Local

---

## 被否方案

### 方案 A：数据库存储

```typescript
// 被 否 决 的 方 案
const rules = await db.query('SELECT * FROM project_rules WHERE path = ?', [cwd])
```

**问题**：
- 需要安装和管理数据库
- 版本控制困难——规则不能提交到 Git
- 跨机器同步需要额外机制
- 调试不直观——不能直接 `cat` 查看

### 方案 B：JSON/YAML 配置

```json
// 被 否 决 的 方 案
{
  "rules": [
    { "pattern": "*.ts", "action": "always-add-return-types" },
    { "pattern": "*.tsx", "action": "use-functional-components" }
  ]
}
```

**问题**：
- 表达能力有限——复杂指令难以结构化
- 用户需要学习配置语法
- 不如 Markdown 直观

### 方案 C：环境变量

```bash
# 被 否 决 的 方 案
export CLAUDE_RULE_1="Always use TypeScript strict mode"
export CLAUDE_RULE_2="Test files go in test/"
```

**问题**：长度限制、不支持多行、没有结构化格式、跨 shell 不一致。

---

## 后果分析

### 好处

1. **版本控制**：`CLAUDE.md` 可以提交到 Git——团队共享项目规则
2. **透明性**：`cat CLAUDE.md` 就能看到所有指令——没有隐藏配置
3. **灵活表达**：Markdown 支持自然语言指令、代码示例、条件规则
4. **层级覆盖**：Local 覆盖 Project 覆盖 User——个人偏好不污染团队规则
5. **`@include` 语法**：引用其他文件——避免重复
6. **条件规则**：YAML frontmatter 的 `paths` 过滤——只在相关文件生效

### 记忆系统的设计

```
MEMORY.md（自动记忆）
  → 索引文件：~150 字符的条目
  → 详细文件：独立 .md 文件
  → 限制：200 行 / 25KB
  → 跨会话持久化
```

### 麻烦

1. **加载开销**：每次查询开始时读取文件系统——缓存缓解
2. **格式不一致**：用户写法差异大——模型解析可能有歧义
3. **大小限制**：200 行 / 25KB——复杂项目的记忆可能超限
4. **无验证**：Markdown 语法错误不影响加载但可能影响模型理解

---

## 横向对比

| 工具 | 配置/记忆方式 | 特点 |
|------|-------------|------|
| **Claude Code** | CLAUDE.md + MEMORY.md | 文本文件、层级覆盖、版本控制 |
| **Cursor** | `.cursorrules` 文件 | 类似理念、单文件 |
| **GitHub Copilot** | `.github/copilot-instructions.md` | 类似理念 |
| **Aider** | `.aider.conf.yml` | YAML 配置 |

Claude Code 的创新在于**四级加载层级**和**自动记忆系统**——其他工具只有项目级配置，没有个人全局配置和自动记忆。

---

## 你的判断

1. 文本文件是否是最佳配置格式？结构化格式（如 YAML frontmatter + Markdown body）是否更好？
2. 自动记忆的 200 行限制是否合理？如何处理大型项目的复杂记忆？
3. 四级加载层级是否过于复杂？三级（User → Project → Local）是否足够？

---

**设计原则标签**：上下文适配——transparent file-based config/memory。文件即配置——版本控制、团队共享、透明调试。
