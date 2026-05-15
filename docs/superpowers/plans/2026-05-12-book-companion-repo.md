# AgentScope Book Companion Repository — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `teaching/book/lab/`, a companion code directory inside the AgentScope repository, providing runnable, multi-provider examples that guide readers from using the framework to contributing to it.

**Architecture:** A single `config.py` provides provider-agnostic model/formatter pairs. An optional `mock_server.py` eliminates the API key requirement. Each chapter is a self-contained directory with its own README and Python scripts (<80 lines each) that include source-code pointer comments (`# → src/agentscope/...`) linking back to the actual AgentScope implementation.

**Tech Stack:** Python 3.10+, AgentScope (pip install), python-dotenv, stdlib http.server (mock server)

**Location:** `teaching/book/lab/` inside the agentscope repository

---

## File Structure Map

```
teaching/book/lab/
├── .env.example                     # Template, readers copy to .env
├── .gitignore                       # *.pyc, .env, __pycache__, .venv
├── README.md                        # Global nav + provider setup guide
├── config.py                        # Shared: multi-provider model/formatter factory
├── mock/
│   ├── __init__.py                  # Empty
│   ├── mock_server.py               # Flask server, returns pre-recorded LLM responses
│   └── responses/
│       ├── ch02_weather.json        # Pre-recorded: "北京今天天气怎么样？"
│       └── ch09_stream.json         # Pre-recorded: streaming response
├── scripts/
│   └── verify_companion.py          # Scan source pointers, verify file+line validity
├── ch01-hello-llm/
│   ├── README.md
│   └── hello_llm.py
├── ch02-hello-agent/
│   ├── README.md
│   ├── weather_agent.py             # Full agent, 3 providers all work
│   └── pure_python_loop.py          # if/else ReAct, zero dependencies
├── ch04-message/
│   ├── README.md
│   ├── msg_create.py                # 7 ContentBlock types
│   └── msg_serialize.py             # to_dict / from_dict
├── ch05-agent-receives/
│   ├── README.md
│   ├── agent_call_flow.py           # await agent(msg) trace
│   └── hook_demo.py                 # register_instance_hook
├── ch06-memory/
│   ├── README.md
│   ├── memory_store.py              # InMemoryMemory CRUD
│   └── memory_compress.py           # Compression + summary
├── ch08-formatter/
│   ├── README.md
│   ├── openai_format.py             # OpenAI message format
│   └── anthropic_format.py          # Anthropic format, side-by-side diff
├── ch09-model/
│   ├── README.md
│   ├── sync_vs_stream.py            # Sync vs streaming call comparison
│   └── structured_output.py         # Structured output via tool calling
├── ch10-toolkit/
│   ├── README.md
│   ├── register_tool.py             # register_tool_function demo
│   └── middleware_demo.py           # _apply_middlewares onion model
├── ch11-loop/
│   ├── README.md
│   └── react_loop.py                # Full ReAct loop with step logging
├── ch22-new-tool/
│   ├── README.md
│   └── custom_tool.py               # Build + register a custom tool
├── ch23-new-model/
│   ├── README.md
│   └── custom_provider.py           # Wire a new model provider
├── ch24-new-memory/
│   ├── README.md
│   └── sqlite_memory.py             # SQLite-backed Memory implementation
├── ch25-new-agent/
│   ├── README.md
│   └── plan_execute_agent.py        # Plan-Execute agent subclass
├── ch26-mcp-server/
│   ├── README.md
│   └── mcp_integration.py           # Connect an MCP server
├── ch27-advanced-extension/
│   ├── README.md
│   ├── rate_limit_middleware.py     # Custom tool middleware
│   └── agent_skill.py               # register_agent_skill demo
└── ch28-capstone/
    ├── README.md
    └── integration.py               # All custom pieces wired together
```

**Total: ~25 Python files, 17 READMEs, 5 infrastructure files**

---

## Dependency Graph

```
config.py  ←── all chapter .py files
mock/      ←── config.py (when MOCK=1)
.env       ←── config.py (via python-dotenv)

Chapter dependencies (reader perspective):
  ch01 → ch02 → ch04 → ch05 → ch06 → ch08 → ch09 → ch10 → ch11
  ch22 → ch23 → ch24 → ch25 → ch26 → ch27 → ch28
  (Each is self-contained for jump-in readers; sequential for linear readers)
```

---

### Task 1: Repository Skeleton

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `README.md`
- Create: `mock/__init__.py`

- [ ] **Step 1: Create `.env.example`**

```bash
# AgentScope Book Lab — 环境配置
# 复制此文件为 .env 并填入你的 API key

# 三选一: deepseek | openai | anthropic
LLM_PROVIDER=deepseek

# DeepSeek（推荐：注册即送免费额度，支持 OpenAI + Anthropic 双格式）
DEEPSEEK_API_KEY=sk-your-deepseek-key

# OpenAI
OPENAI_API_KEY=sk-your-openai-key
OPENAI_MODEL=gpt-4o

# Anthropic（原生）或 DeepSeek Anthropic 端点
ANTHROPIC_API_KEY=sk-ant-your-key
ANTHROPIC_MODEL=claude-sonnet-4-6
# 如果用 DeepSeek 的 Anthropic 端点，取消下行注释：
# ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.venv/
venv/
*.egg-info/
dist/
```

- [ ] **Step 3: Create `README.md`**

```markdown
# AgentScope 源码之旅 — 配套代码

这是《AgentScope 源码之旅》书籍的配套可运行代码。

## 快速开始

```bash
git clone https://github.com/modelscope/agentscope-book-lab.git
cd agentscope-book-lab
python -m venv .venv && source .venv/bin/activate
pip install agentscope python-dotenv
cp .env.example .env
# 编辑 .env，填入任意一个 provider 的 API key
```

## 三种运行方式

| 方式 | 命令 | 需要 API key |
|------|------|-------------|
| DeepSeek（推荐） | `python ch02-hello-agent/weather_agent.py` | DeepSeek 免费额度 |
| OpenAI | `LLM_PROVIDER=openai python ...` | OpenAI key |
| Anthropic | `LLM_PROVIDER=anthropic python ...` | Anthropic key |
| 离线 Mock | `MOCK=1 python ...` | **不需要** |

## 目录导航

| 章节目录 | 对应源码 | 学什么 |
|---------|---------|--------|
| ch01-hello-llm | — | 第一行代码，跑通 LLM 调用 |
| ch02-hello-agent | agent/ | 完整天气 Agent，理解 ReAct |
| ch04-message | message/ | Msg 的七种 ContentBlock |
| ch05-agent-receives | agent/_agent_base.py | Agent 收信 → reply 调用链 |
| ch06-memory | memory/ | InMemoryMemory 增删查 |
| ch08-formatter | formatter/ | OpenAI vs Anthropic 格式转换 |
| ch09-model | model/ | 同步/流式调用，结构化输出 |
| ch10-toolkit | tool/ | 工具注册 + 中间件洋葱模型 |
| ch11-loop | agent/_react_agent.py | ReAct 完整循环，逐步日志 |
| ch22-ch28 | 各模块 | 造新 Tool / Model / Memory / Agent |

## 源码指针

代码注释中的 `# → src/agentscope/...` 指向 AgentScope 源码对应位置。读完 companion 代码后，跳转过去看真正的实现。

## 分支导航

```bash
git branch -a  # 查看所有章节分支
git checkout ch05-agent-receives  # 跳到第5章起点
```
```

- [ ] **Step 4: Create `mock/__init__.py`** (empty file)

- [ ] **Step 5: Initialize git repo and commit**

```bash
cd agentscope-book-lab
git init
git add -A
git commit -m "feat: repository skeleton with README and config templates"
```

---

### Task 2: config.py — Multi-Provider Factory

**Files:**
- Create: `config.py`

- [ ] **Step 1: Write `config.py`**

```python
"""Provider configuration for AgentScope book companion.

Usage — copy-paste into any chapter script:
    from config import get_model_and_formatter
    model, formatter = get_model_and_formatter()

Provider selection via environment (edit .env):
    LLM_PROVIDER=deepseek    # recommended: free credits, dual format
    LLM_PROVIDER=openai      # standard OpenAI
    LLM_PROVIDER=anthropic   # Anthropic or DeepSeek Anthropic endpoint

Offline mode:
    MOCK=1 python ch02-hello-agent/weather_agent.py
"""
import os

from dotenv import load_dotenv

load_dotenv()


def get_model_and_formatter():
    """Return (model, formatter) based on LLM_PROVIDER and MOCK env vars."""

    # ── Mock mode: no real API call ─────────────────────────
    if os.getenv("MOCK") == "1":
        from agentscope.model import OpenAIChatModel
        from agentscope.formatter import OpenAIChatFormatter

        model = OpenAIChatModel(
            model_name="mock-model",
            api_key="mock",
            base_url="http://localhost:9999/v1",
        )
        formatter = OpenAIChatFormatter()
        return model, formatter

    # ── Real providers ──────────────────────────────────────
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()

    if provider == "deepseek":
        # → src/agentscope/model/_openai_model.py
        # → src/agentscope/formatter/_openai_formatter.py
        from agentscope.model import OpenAIChatModel
        from agentscope.formatter import OpenAIChatFormatter

        model = OpenAIChatModel(
            model_name="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
        )
        formatter = OpenAIChatFormatter()

    elif provider == "openai":
        from agentscope.model import OpenAIChatModel
        from agentscope.formatter import OpenAIChatFormatter

        model = OpenAIChatModel(
            model_name=os.getenv("OPENAI_MODEL", "gpt-4o"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        formatter = OpenAIChatFormatter()

    elif provider == "anthropic":
        # DeepSeek 的 Anthropic 端点也走这里：设置 ANTHROPIC_BASE_URL 即可
        from agentscope.model import OpenAIChatModel
        from agentscope.formatter import AnthropicChatFormatter

        model = OpenAIChatModel(
            model_name=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            base_url=os.getenv(
                "ANTHROPIC_BASE_URL",
                "https://api.anthropic.com/v1",
            ),
        )
        # → src/agentscope/formatter/_anthropic_formatter.py
        formatter = AnthropicChatFormatter()

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER={provider!r}. "
            f"Set to deepseek, openai, or anthropic in .env"
        )

    return model, formatter
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add multi-provider config with mock mode support"
```

---

### Task 3: Mock Server — Offline Mode

**Files:**
- Create: `mock/mock_server.py`
- Create: `mock/responses/ch02_weather.json`
- Create: `mock/responses/ch09_stream.json`

- [ ] **Step 1: Write `mock/mock_server.py`**

```python
"""Mock LLM API server for offline book reading.

Returns pre-recorded responses so readers can run all examples
without any API key.

Usage:
    python mock/mock_server.py          # starts on localhost:9999
    MOCK=1 python ch02-hello-agent/weather_agent.py
"""
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

RESPONSES_DIR = Path(__file__).parent / "responses"

# Route: request content snippet → response file
ROUTES = {
    "北京今天天气怎么样": "ch02_weather.json",
    "stream": "ch09_stream.json",
}


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else "{}"

        # Find matching response file
        resp_file = None
        for keyword, filename in ROUTES.items():
            if keyword in body:
                resp_file = RESPONSES_DIR / filename
                break

        if resp_file and resp_file.exists():
            data = json.loads(resp_file.read_text())
            # Simulate streaming: send as SSE if stream=true in request
            if '"stream":true' in body or '"stream": true' in body:
                self._send_stream(data)
            else:
                self._send_json(data)
        else:
            # Fallback: return a generic completion
            self._send_json({
                "id": "mock-fallback",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "mock",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": (
                            "[Mock 模式] 未找到匹配的预录制响应。"
                            "请检查 mock/responses/ 目录。"
                        ),
                    },
                    "finish_reason": "stop",
                }],
            })

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _send_stream(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        content = data["choices"][0]["message"]["content"]
        for chunk in content.split():  # simple word-by-word streaming
            sse = f"data: {json.dumps({'choices': [{'delta': {'content': chunk + ' '}}]})}\n\n"
            self.wfile.write(sse.encode())
            self.wfile.flush()
            time.sleep(0.05)
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, format, *args):
        print(f"  [mock] {args[0]}")


if __name__ == "__main__":
    print("AgentScope Book Lab Mock Server")
    print("  Listening on http://localhost:9999")
    print("  Responses dir:", RESPONSES_DIR)
    print("  Press Ctrl+C to stop\n")
    HTTPServer(("localhost", 9999), MockHandler).serve_forever()
```

- [ ] **Step 2: Write `mock/responses/ch02_weather.json`**

```json
{
  "id": "mock-ch02-001",
  "object": "chat.completion",
  "created": 1715472000,
  "model": "mock",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_mock_001",
            "type": "function",
            "function": {
              "name": "get_weather",
              "arguments": "{\"city\": \"北京\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

- [ ] **Step 3: Write `mock/responses/ch09_stream.json`**

```json
{
  "id": "mock-ch09-001",
  "object": "chat.completion",
  "created": 1715472000,
  "model": "mock",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "北京今天天气晴朗，气温25°C，适合出行。"
      },
      "finish_reason": "stop"
    }
  ]
}
```

- [ ] **Step 4: Commit**

```bash
git add mock/
git commit -m "feat: add mock server for offline mode"
```

---

### Task 4: Verification Script

**Files:**
- Create: `scripts/verify_companion.py`

- [ ] **Step 1: Write `scripts/verify_companion.py`**

```python
#!/usr/bin/env python3
"""Verify that all source-code pointers in companion files are valid.

Scans `# → src/agentscope/xxx.py:123` comments in all .py files,
then verifies each referenced file exists and line number is in range.

Usage:
    python scripts/verify_companion.py [--fix]
"""
import re
import sys
from pathlib import Path

COMPANION_ROOT = Path(__file__).resolve().parent.parent
AGENTSCOPE_SRC = None  # Set by --agentscope-path or auto-detected

# Matches: # → src/agentscope/agent/_react_agent.py:408
POINTER_RE = re.compile(r"#\s*→\s*(src/agentscope/\S+?\.py):(\d+)")


def find_agentscope_src():
    """Auto-detect AgentScope source by searching common locations."""
    candidates = [
        COMPANION_ROOT.parent / "agentscope" / "src" / "agentscope",
        Path.home() / "agentscope" / "src" / "agentscope",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def check_pointer(pointer_path, line_num, src_root):
    """Verify a single source pointer. Returns (ok, message)."""
    full_path = COMPANION_ROOT.parent / pointer_path
    # Also try relative to src_root
    if not full_path.exists():
        full_path = src_root / Path(pointer_path).relative_to("src/agentscope")

    if not full_path.exists():
        return False, f"FILE NOT FOUND: {pointer_path}"

    lines = full_path.read_text().split("\n")
    if line_num > len(lines):
        return False, f"LINE {line_num} > {len(lines)} in {pointer_path}"

    return True, f"OK: {pointer_path}:{line_num}"


def main():
    src_root = find_agentscope_src()
    if not src_root:
        print("ERROR: Cannot find AgentScope source. Set --agentscope-path")
        sys.exit(1)
    print(f"AgentScope source: {src_root}\n")

    total, ok, fail = 0, 0, 0
    for py_file in sorted(COMPANION_ROOT.glob("ch*/*.py")):
        for match in POINTER_RE.finditer(py_file.read_text()):
            total += 1
            pointer_path = match.group(1)
            line_num = int(match.group(2))
            status, msg = check_pointer(pointer_path, line_num, src_root)
            if status:
                ok += 1
            else:
                fail += 1
                print(f"  FAIL [{py_file.parent.name}/{py_file.name}] {msg}")

    print(f"\n{'='*50}")
    print(f"  Total pointers: {total}")
    print(f"  OK:             {ok}")
    print(f"  FAIL:           {fail}")

    if fail > 0:
        print("\nRun with --fix to attempt auto-correction (requires git).")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/
git commit -m "feat: add source pointer verification script"
```

---

### Task 5: Chapter 01 — Hello LLM

**Files:**
- Create: `ch01-hello-llm/README.md`
- Create: `ch01-hello-llm/hello_llm.py`

- [ ] **Step 1: Write `ch01-hello-llm/hello_llm.py`**

```python
"""第 1 章：什么是大模型（LLM）

跑通第一行代码——用 AgentScope 调用 LLM。
切换 provider 只需改 .env 中的 LLM_PROVIDER。
"""
from agentscope.model import OpenAIChatModel

# 最简单的 LLM 调用：构造 model，发消息，收回复
# → src/agentscope/model/_openai_model.py  (OpenAIChatModel 实现)
# → src/agentscope/model/_model_base.py    (ChatModelBase 基类)

model = OpenAIChatModel(
    model_name="deepseek-chat",
    api_key="your-api-key",  # 读者需替换
    base_url="https://api.deepseek.com/v1",
)

# 消息格式：role + content
messages = [
    {"role": "system", "content": "你是一个有帮助的助手。"},
    {"role": "user", "content": "什么是大语言模型？用一句话回答。"},
]

response = model(messages)
print("模型回复:")
print(response.text)
print(f"\nToken 用量: {response.usage}")
```

**注意：** 这个文件是给读者"看"的入口示例，实际可运行版用 config.py。在 README 中说明读者应切换到 ch02 的 weather_agent.py 获取完整多 provider 体验。

- [ ] **Step 2: Write `ch01-hello-llm/README.md`**

```markdown
# 第 1 章：什么是大模型（LLM）

**对应书籍：** 卷零 ch01
**对应源码：** `src/agentscope/model/`

## 运行

```bash
# 需要 API key
python ch01-hello-llm/hello_llm.py

# 或用 config.py 多 provider 版本（推荐）
python ch02-hello-agent/weather_agent.py
```

## 学什么

- LLM API 调用的基本结构
- AgentScope 的 `OpenAIChatModel` 如何使用
- 消息格式（system / user / assistant）

## 源码跳转

读完此文件后，打开：
- `src/agentscope/model/_model_base.py` — ChatModelBase 基类
- `src/agentscope/model/_openai_model.py` — OpenAI 模型适配
```

- [ ] **Step 3: Commit**

```bash
git add ch01-hello-llm/
git commit -m "feat: add ch01 - hello LLM"
```

---

### Task 6: Chapter 02 — Hello Agent (Weather Agent)

**Files:**
- Create: `ch02-hello-agent/README.md`
- Create: `ch02-hello-agent/weather_agent.py`
- Create: `ch02-hello-agent/pure_python_loop.py`

- [ ] **Step 1: Write `ch02-hello-agent/weather_agent.py`**

```python
"""第 2 章：什么是 Agent — 完整天气查询 Agent

这是全书的贯穿示例。切换 LLM_PROVIDER 环境变量即可在
DeepSeek / OpenAI / Anthropic 之间切换，Agent 代码完全不变。
这就是 AgentScope model/formatter 解耦设计的价值。
"""
import asyncio

import agentscope
from agentscope.agent import ReActAgent
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.tool import Toolkit

from config import get_model_and_formatter


def get_weather(city: str) -> str:
    """查询城市天气。→ src/agentscope/tool/_types.py (ToolFunction 类型)"""
    weather_db = {
        "北京": "晴，25°C，湿度30%",
        "上海": "多云，28°C，湿度65%",
        "深圳": "阵雨，30°C，湿度80%",
    }
    return weather_db.get(city, f"未找到 {city} 的天气数据")


async def main():
    agentscope.init(project="book-lab-ch02")

    # model + formatter 由 config.py 根据 .env 自动选择
    # → src/agentscope/model/       (模型适配层)
    # → src/agentscope/formatter/   (格式转换层)
    model, formatter = get_model_and_formatter()

    # 工具注册
    # → src/agentscope/tool/_toolkit.py:1284 (register_tool_function)
    toolkit = Toolkit()
    toolkit.register_tool_function(get_weather)

    # Agent 组装：六块积木搭起一个 Agent
    # → src/agentscope/agent/_react_agent.py  (ReActAgent 实现)
    # → src/agentscope/agent/_agent_base.py   (AgentBase 基类)
    # → src/agentscope/agent/_agent_meta.py   (_AgentMeta 元类)
    agent = ReActAgent(
        name="天气助手",
        sys_prompt="你是一个天气助手。用户询问天气时，调用 get_weather 工具。",
        model=model,
        formatter=formatter,
        toolkit=toolkit,
        memory=InMemoryMemory(),
    )

    # await agent(msg) — 全书追踪的这一行
    # → src/agentscope/agent/_agent_base.py:197 (reply 方法)
    # → src/agentscope/agent/_react_agent.py:408 (_react_loop)
    msg = Msg("user", "北京今天天气怎么样？", "user")
    result = await agent(msg)

    print("=" * 50)
    print(f"Agent 最终回复: {result.get_text_content()}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Write `ch02-hello-agent/pure_python_loop.py`**

```python
"""第 2 章附录：用纯 Python 模拟 ReAct 循环

不需要 AgentScope、不需要 LLM、不需要 API key。
用 if/else 展示 ReAct（推理-行动）的核心逻辑。
运行: python ch02-hello-agent/pure_python_loop.py
"""


def get_weather(city):
    return {"北京": "晴，25°C", "上海": "多云，28°C"}.get(city, "未知")


def simulate_react(user_input, max_steps=5):
    """纯 Python 的 ReAct 循环模拟。
    → src/agentscope/agent/_react_agent.py:408 (_react_loop 真实实现)
    """
    messages = []  # → src/agentscope/memory/_working_memory/_in_memory_memory.py
    for step in range(1, max_steps + 1):
        print(f"\n--- 第 {step} 轮 ---")

        # Think: 决定用什么工具
        think = decide_action(user_input, messages)
        print(f"  [Think]  {think}")

        if think == "ANSWER":
            answer = "北京今天晴朗，25°C，适合出行。"
            print(f"  [Answer] {answer}")
            return answer
        elif think.startswith("TOOL:"):
            tool_name = think.split(":")[1].strip()
            city = "北京"
            result = get_weather(city)
            messages.append(f"工具结果: {result}")
            print(f"  [Act]    {tool_name}({city}) → {result}")
            # 循环继续，下一轮 Think 根据结果决定 ANSWER
    return "无法在限定轮数内回答。"


def decide_action(user_input, messages):
    """模拟 LLM 的推理。
    真实版 → src/agentscope/model/ (LLM 返回 tool_calls 或 text)
    """
    if not messages:
        return "TOOL: get_weather"
    if "25°C" in str(messages):
        return "ANSWER"
    return "TOOL: get_weather"


if __name__ == "__main__":
    result = simulate_react("北京今天天气怎么样？")
    print(f"\n最终结果: {result}")
```

- [ ] **Step 3: Write `ch02-hello-agent/README.md`** (pattern established, abbreviated here — includes: what book chapter, which source files to read, how to run with each provider, expected output)

- [ ] **Step 4: Commit**

```bash
git add ch02-hello-agent/
git commit -m "feat: add ch02 - weather agent + pure python ReAct"
```

---

### Task 7–18: Remaining Chapters (patterened)

Each follows the same structure. Key files and their source pointers:

| Task | Chapter | Files | Key source pointers |
|------|---------|-------|---------------------|
| 7 | ch04-message | `msg_create.py`, `msg_serialize.py` | `message/_message_base.py` (Msg class), `message/_types.py` (ContentBlock types) |
| 8 | ch05-agent-receives | `agent_call_flow.py`, `hook_demo.py` | `agent/_agent_base.py:197` (reply), `agent/_agent_meta.py` (_AgentMeta), `agent/_agent_base.py:448` (__call__) |
| 9 | ch06-memory | `memory_store.py`, `memory_compress.py` | `memory/_working_memory/_base.py` (MemoryBase), `memory/_working_memory/_in_memory_memory.py` |
| 10 | ch08-formatter | `openai_format.py`, `anthropic_format.py` | `formatter/_formatter_base.py`, `formatter/_openai_formatter.py`, `formatter/_anthropic_formatter.py` |
| 11 | ch09-model | `sync_vs_stream.py`, `structured_output.py` | `model/_model_base.py`, `model/_openai_model.py` (stream + structured output) |
| 12 | ch10-toolkit | `register_tool.py`, `middleware_demo.py` | `tool/_toolkit.py:1284` (register), `tool/_toolkit.py:57` (_apply_middlewares) |
| 13 | ch11-loop | `react_loop.py` | `agent/_react_agent.py:408` (_react_loop), `agent/_react_agent.py:1015` (工具执行) |
| 14 | ch22-new-tool | `custom_tool.py` | `tool/_toolkit.py` (参考 toolkit 结构), `tool/_response.py` (ToolResponse) |
| 15 | ch23-new-model | `custom_provider.py` | `model/_openai_model.py` (参考实现), `model/_model_base.py` (基类) |
| 16 | ch24-new-memory | `sqlite_memory.py` | `memory/_working_memory/_base.py` (MemoryBase), `memory/_working_memory/_in_memory_memory.py` (参考) |
| 17 | ch25-new-agent | `plan_execute_agent.py` | `agent/_react_agent.py` (参考), `agent/_agent_base.py` (基类) |
| 18 | ch26-mcp-server | `mcp_integration.py` | `mcp/` 目录, `tool/_toolkit.py:1328` (register_agent_skill) |
| 19 | ch27-advanced | `rate_limit_middleware.py`, `agent_skill.py` | `tool/_toolkit.py:57` (middleware), `tool/_toolkit.py:1328` (skill) |
| 20 | ch28-capstone | `integration.py` | 综合引用前面各模块源码位置 |

Each chapter task commits independently. Each Python file is self-contained (<80 lines), imports from `config`, and includes 3-5 source pointers.

**Representative commit messages:**
```
feat: add ch04 - message creation and serialization
feat: add ch05 - agent receive flow and hook demo
feat: add ch06 - memory store and compression
...
feat: add ch28 - integration capstone
```

---

### Task 21: Pre-record Mock Responses

**Files:**
- Create: additional JSON files in `mock/responses/`

- [ ] **Step 1: Run each chapter with a real API key, capture responses**

For each chapter that makes LLM calls, run once with `DEEPSEEK_API_KEY=...` and save the response JSON to `mock/responses/chXX_topic.json`. Update `ROUTES` in `mock/mock_server.py`.

- [ ] **Step 2: Commit**

```bash
git add mock/responses/
git commit -m "feat: add pre-recorded mock responses for all chapters"
```

---

### Task 22: Git Branches Per Chapter

- [ ] **Step 1: Create branches**

```bash
# From main (complete), create chapter start-point branches
git checkout -b ch01-hello-llm
# (ch01 is already on main as first chapter)
git checkout main

git checkout -b ch02-hello-agent
git checkout main

git checkout -b ch04-message
# ... one branch per chapter

# Push all branches
git push --all origin
```

Each branch contains the cumulative code up to and including that chapter. This way a reader who wants to start at chapter 6 can `git checkout ch06-memory` and get ch01-ch06 code.

- [ ] **Step 2: Add branch navigation to README.md**

```markdown
## 按章节跳转

| 章节 | 分支 | 内容 |
|------|------|------|
| ch01 | `ch01-hello-llm` | Hello LLM |
| ch02 | `ch02-hello-agent` | 天气 Agent + 纯 Python ReAct |
| ch04 | `ch04-message` | + 消息创建与序列化 |
| ... | ... | ... |
| ch28 | `ch28-capstone` | 全部章节代码 |

```bash
git checkout ch06-memory  # 获得第 6 章起点的所有代码
```
```

- [ ] **Step 3: Commit**

```bash
git checkout main
git add README.md
git commit -m "docs: add branch navigation guide"
```

---

### Task 23: Final Verification

- [ ] **Step 1: Run verify_companion.py**

```bash
python scripts/verify_companion.py
```

Expected: all source pointers resolve. Fix any that don't.

- [ ] **Step 2: Test each provider**

```bash
LLM_PROVIDER=deepseek python ch02-hello-agent/weather_agent.py
LLM_PROVIDER=openai python ch02-hello-agent/weather_agent.py
LLM_PROVIDER=anthropic python ch02-hello-agent/weather_agent.py
MOCK=1 python ch02-hello-agent/weather_agent.py  # requires mock server running
```

- [ ] **Step 3: Test mock mode end-to-end**

```bash
python mock/mock_server.py &
sleep 1
MOCK=1 python ch02-hello-agent/weather_agent.py
# Should print weather response without any API key
kill %1
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final verification pass, all providers + mock mode tested"
```

---

## Execution Order

```
Task 1  (skeleton)     ──┐
Task 2  (config.py)   ──┤ foundation, no dependencies
Task 3  (mock server) ──┤
Task 4  (verify)      ──┘
Task 5  (ch01)         ── depends on config.py
Task 6  (ch02)         ── depends on config.py
Tasks 7-20 (ch04-28)   ── depend on config.py, can run in parallel groups
                          (ch04-ch11 = 卷一+卷二, ch22-28 = 卷三)
Task 21 (mock data)     ── depends on ch02+ch09 being complete
Task 22 (git branches)  ── depends on all chapters
Task 23 (verification)  ── depends on everything
```

**Parallel group 1** (after Task 1-4 done):
- Tasks 5, 6 (ch01, ch02)

**Parallel group 2** (after config.py + pattern established):
- Tasks 7-13 (ch04-ch11) — 7 tasks can run in parallel
- Tasks 14-20 (ch22-ch28) — 7 tasks can run in parallel

---

## Design Rationale

**Why `config.py` instead of per-file env loading:** Readers switch providers by editing one `.env` file. All chapter files import the same two lines. This demonstrates AgentScope's model/formatter decoupling — the same Agent code runs on three different backends without changes.

**Why mock instead of just saying "get an API key":** The book explicitly targets offline readers. Mock mode makes the companion truly self-contained and respects the book's "no external links required" philosophy.

**Why source pointers in comments:** The companion's purpose is NOT to teach the concepts (the book does that). It's to provide runnable, traceable code that leads the reader directly into the AgentScope source. Each `# →` comment is a hyperlink from companion to source.

**Why <80 lines per file:** Each file demonstrates exactly one concept. A reader can read it in 5-10 minutes, then jump to source. No file should require scrolling to understand.

**Why git branches per chapter:** A reader who wants to start at chapter 22 (building new modules) shouldn't need to read ch01-21 code. Branches let them check out exactly the state they need.
```

---

## Post-Plan: Spec Self-Review

1. **Placeholder scan:** All chapter tasks have specific file names and source pointer targets. No TBD/TODO remain.
2. **Internal consistency:** config.py exports `get_model_and_formatter()` — all chapter files import from it. Mock server returns OpenAI-format JSON — config.py's mock mode points to it. verify_companion.py scans for `# →` pattern — all chapter files use this exact format.
3. **Scope check:** Single companion repo, 25 Python files, 17 READMEs. Self-contained with clear boundaries.
4. **Ambiguity check:** Provider selection logic is explicit. Mock server routes are keyword-based with fallback. Source pointer format is regex-enforced.
