---
title: 附录C — Claude Code 命令速查
description: Claude Code CLI 命令、REPL 内命令与环境变量的快速参考卡片
tags: [附录, 命令, CLI, REPL, 环境变量]
date: 2026-05-10
---

# 附录C — 命令速查

> 本附录收录 Claude Code 自身的命令与环境变量，不含通用 npm/git 内容。

---

## 1. CLI 命令

| 命令 | 说明 |
|------|------|
| `claude` | 启动交互式 REPL |
| `claude --cwd <path>` | 指定工作目录 |
| `claude --verbose` | 详细日志输出 |
| `claude --config <path>` | 指定配置文件 |
| `claude -t <Tool> -- <args>` | 直接调用单个工具 |
| `claude --list-tools` | 列出所有可用工具 |
| `claude --allow-tool <Tool>` | 允许指定工具执行 |
| `claude --mcp` | 启动内置 MCP 服务器 |
| `claude --mcp-config <path>` | 指定 MCP 配置文件 |
| `claude --list-mcp-servers` | 列出已连接的 MCP 服务器 |
| `claude --dangerously-skip-permissions` | 跳过权限检查（危险） |
| `claude --permission-mode <mode>` | 设置权限模式：`prompt` / `bypass` / `fail` / `approve` |
| `claude --export-permissions <path>` | 导出权限配置 |
| `claude --log-file <path>` | 日志输出到文件 |
| `claude --profile` | 启用性能分析 |
| `claude --heap-snapshot` | 启动时生成堆快照 |
| `claude --memory-monitor` | 监控内存使用 |

---

## 2. REPL 内命令

| 命令 | 说明 |
|------|------|
| `/exit` 或 `/quit` | 退出 REPL |
| `/help` | 查看帮助信息 |
| `/theme dark` | 切换深色主题 |
| `/theme light` | 切换浅色主题 |
| `/clear` | 清除当前对话历史 |
| `/compact` | 压缩上下文以释放 token 空间 |
| `/skills` | 列出所有已注册的 Skill |
| `/review` | 调用代码审查 Skill |
| `/docs` | 调用文档生成 Skill |
| `/refactor` | 调用重构 Skill |
| `/test` | 调用测试生成 Skill |

> 自定义 Skill 以 `/` 前缀调用，如 `/my-skill arg1 arg2`。

---

## 3. 环境变量速查

| 变量 | 说明 | 取值示例 |
|------|------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | `sk-ant-xxx...` |
| `CLAUDE_CODE_CONFIG` | 自定义配置文件路径 | `/etc/claude/config.json` |
| `CLAUDE_CODE_DATA_DIR` | 数据存储目录 | `~/.claude` |
| `LOG_LEVEL` | 日志级别 | `debug` / `info` / `warn` / `error` |
| `DEBUG` | 调试模式开关 | `true` / `false` |
| `NODE_ENV` | 运行环境标识 | `development` / `production` |
| `ENABLE_PROFILING` | 性能分析开关 | `true` / `false` |
| `HTTP_PROXY` | HTTP 代理地址 | `http://proxy:8080` |
| `HTTPS_PROXY` | HTTPS 代理地址 | `http://proxy:8080` |

---

## 4. 权限模式速查

| 模式 | 行为 |
|------|------|
| `prompt` | 每次敏感操作询问用户（默认） |
| `bypass` | 完全跳过权限检查 |
| `fail` | 无权限时直接失败，不提示 |
| `approve` | 自动批准所有请求 |

---

`★ Insight ─────────────────────────────────────`
CLI 参数覆盖环境变量，环境变量覆盖配置文件。当调试异常行为时，优先检查这三层优先级是否冲突。
`─────────────────────────────────────────────────`
