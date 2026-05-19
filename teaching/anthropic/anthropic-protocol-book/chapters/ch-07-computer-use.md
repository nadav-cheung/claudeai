# 第 7 章：Computer Use —— 桌面控制协议

> **本章目标**：理解 Computer Use 作为独立协议的设计哲学，掌握截图捕获、鼠标操作、键盘输入的全部动作规范，能够构建完整的 Agent Loop 驱动 Claude 控制桌面环境。完成本章后，你将拥有一个不依赖特定桌面环境的、可测试的 Computer Use 客户端，以及驱动 Claude 自主完成 GUI 任务的编排引擎。

---

## 7.1 概念全景

### 7.1.1 Computer Use 在 Anthropic 生态中的定位

Computer Use 是 Anthropic 提供的一项 Beta 功能，它允许 Claude 像人类一样"看见"屏幕并"操作"键盘鼠标。但 Computer Use 不是什么神秘的端到端机器人——它是一种工具协议（Tool Protocol），与第 3 章讨论的 Tool Use 共享完全相同的底层机制：Claude 返回 `tool_use` 内容块，客户端执行操作并将 `tool_result` 返回。

Computer Use 的独特之处在于：它是一个**无 schema 工具（schema-less tool）**。与其他工具不同，你不需要（也不能）自定义 Computer Use 的输入 schema——actions 的结构已经内置在 Claude 模型中。你只需声明工具的 `type`、`name` 和显示器参数，Claude 就知道该发送什么。

**Computer Use 在生态中的三层位置：**

```
第 1 层：Anthropic Messages API（基础设施，第 1 章）
  └─ 第 2 层：Tool Use 协议（第 3 章）
       └─ 第 3 层：Computer Use 工具（本章）
            ├── Screenshot Capture（截图捕获）
            ├── Mouse Control（鼠标控制）
            ├── Keyboard Input（键盘输入）
            └── Agent Loop（代理循环）
```

Computer Use 本身就是一个普通的 `tool_use`——它与自定义工具、bash 工具、text_editor 工具处于同一抽象层级。这意味着：

- **你可以把 Computer Use 和自定义工具混用**：比如"去网站上提取表格，然后调用我的数据分析工具"。
- **你可以把 Computer Use 和 bash/edit 配用**：这是 Anthropic 推荐的三工具组合（computer + bash + text_editor），构成了完整的桌面自动化环境。
- **Agent Loop 是通用的**：驱动 Computer Use 的循环模式同样适用于任何 Tool Use 场景。

### 7.1.2 核心使用场景

| 场景 | 描述 | 适用性 |
|------|------|--------|
| **Web 自动化** | 在真实浏览器中导航、填充表单、提取数据 | 高（最佳场景） |
| **GUI 代理** | 操作桌面应用（Office, 文件管理器, 配置面板） | 中（依赖应用兼容性） |
| **RPA（机器人流程自动化）** | 跨应用的工作流自动化 | 中（需要 prompt 工程） |
| **自动化测试** | E2E 测试、UI 回归测试、验证部署 | 高（无需测试框架适配） |
| **数据采集** | 从无法提供 API 的网站提取信息 | 中（坐标定位有误差） |
| **辅助功能** | 帮助残障用户操作计算机 | 低（延迟较高） |

**Computer Use 不应该用于**：
- 需要完美精度座标定位的场景（考虑直接使用 API 或 Playwright）
- 需要低延迟的实时交互（当前延迟约为秒级）
- 涉及敏感账户或数据而无人类监督的场景
- 社交媒体账户创建或内容发布（违反 Anthropic 使用政策）

### 7.1.3 本章学习成果

完成本章的学习和编码练习后，你将能够：

1. 理解 Computer Use 协议的完整规范，包括所有动作类型、参数约束和坐标系统。
2. 实现一个可测试的 Computer Use 客户端，独立于特定桌面环境。
3. 构建 Agent Loop 编排引擎，驱动 Claude 与桌面环境的多轮交互。
4. 正确处理坐标缩放、错误恢复和安全边界。

---

## 7.2 协议规范

### 7.2.1 工具声明（Tool Declaration）

Computer Use 是第一个 Anthropic 自定义的 schema-less 工具。你传给 Messages API 的 `tools` 数组中的声明只包含元信息，不包含 `input_schema`：

**Python SDK 用法（计算机使用工具 + bash + 编辑器三件套）：**

```python
tools = [
    {
        "type": "computer_20251124",
        "name": "computer",
        "display_width_px": 1024,
        "display_height_px": 768,
        "display_number": 1,
    },
    {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
    {"type": "bash_20250124", "name": "bash"},
]
```

**关键约定：**
- `name` 必须是 `"computer"`——这是 Anthropic 硬编码的约定。
- `display_width_px` 和 `display_height_px` 告诉 Claude 你的显示分辨率。Claude 返回的座标在这个空间内。
- 不需要 `input_schema`——Claude 已经内置了对 Computer Use 动作的理解。

**工具版本对照：**

| 版本 | `type` 值 | Beta Header | 可用模型 |
|------|-----------|-------------|----------|
| 2024-10-22 | `computer_20241022` | `computer-use-2025-01-24` | (已弃用) |
| 2025-01-24 | `computer_20250124` | `computer-use-2025-01-24` | Opus 4.1, Sonnet 4, Opus 4 |
| 2025-11-24 | `computer_20251124` | `computer-use-2025-11-24` | Opus 4.7, Opus 4.6, Sonnet 4.6, Opus 4.5 |

**Beta Header 是强制的**。没有它，API 会拒绝带有 Computer Use 工具的请求：
```http
anthropic-beta: computer-use-2025-11-24
```

### 7.2.2 动作全集（Actions Reference）

Computer Use 的动作按功能分为六组。下表列出 `computer_20250124` 和 `computer_20251124` 支持的全部动作：

**表 7-1：Computer Use 全部动作**

| 动作 | 必需参数 | 可选参数 | 引入版本 |
|------|----------|----------|----------|
| `screenshot` | *(无)* | — | 所有版本 |
| `left_click` | `coordinate: [x, y]` | `text`（修饰键） | 所有版本 |
| `right_click` | `coordinate: [x, y]` | `text` | `20250124` |
| `middle_click` | `coordinate: [x, y]` | `text` | 所有版本 |
| `double_click` | `coordinate: [x, y]` | `text` | `20250124` |
| `triple_click` | `coordinate: [x, y]` | `text` | `20250124` |
| `left_click_drag` | `coordinate: [x, y]` | — | 所有版本 |
| `left_mouse_down` | *(无)* | — | `20250124` |
| `left_mouse_up` | *(无)* | — | `20250124` |
| `mouse_move` | `coordinate: [x, y]` | — | 所有版本 |
| `type` | `text: string` | — | 所有版本 |
| `key` | `text: string` | — | 所有版本 |
| `hold_key` | `text: string` | `duration: number` | `20250124` |
| `scroll` | `scroll_direction`, `scroll_amount` | `coordinate`, `text` | `20250124` |
| `wait` | *(无)* | `duration: number` | `20250124` |
| `cursor_position` | *(无)* | — | 所有版本 |
| `zoom` | `region: [x1, y1, x2, y2]` | — | `20251124` |

**表 7-2：修饰键（Modifier Keys）**

在 click 和 scroll 动作中，可以通过 `text` 参数传递修饰键实现组合操作：

| 修饰键 | 对应键名 | 典型用途 |
|--------|----------|----------|
| `shift` | Shift | 范围选择（Shift+点击） |
| `ctrl` | Control | 多选（Windows/Linux） |
| `alt` | Alt | 替代操作 |
| `super` | Command/Windows | 多选（macOS） |

示例——按住 Shift 点击进行范围选择：
```json
{"action": "left_click", "coordinate": [500, 300], "text": "shift"}
```

示例——按住 Ctrl 滚动进行水平滚动：
```json
{"action": "scroll", "coordinate": [500, 400], "scroll_direction": "down", "scroll_amount": 3, "text": "ctrl"}
```

### 7.2.3 截图捕获与图像处理

**截图动作**是最简单的 Computer Use 动作——不需要任何参数：

```json
{"action": "screenshot"}
```

执行后，你需要将截图编码为 base64 PNG 或 JPEG，放入 `tool_result` 返回给 Claude：

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01A09q90qw90lq917835lq9",
  "content": [
    {"type": "text", "text": "Screenshot captured."},
    {
      "type": "image",
      "source": {
        "type": "base64",
        "media_type": "image/png",
        "data": "iVBORw0KGgoAAAANSUhEUgAA..."
      }
    }
  ]
}
```

**图像大小限制**。Anthropic API 对图像有自动缩放限制：

| 限制维度 | 最大值 | 说明 |
|----------|--------|------|
| 长边最大像素 | 1568 px (早期模型) / 2576 px (Opus 4.7) | 超过则按比例缩小 |
| 总像素数 | ~1.15 百万像素 | 超过则按面积缩小 |

**表 7-3：推荐分辨率**

| 标签 | 分辨率 | 纵横比 | 适用场景 |
|------|--------|--------|----------|
| XGA | 1024x768 | 4:3 | 通用桌面任务 |
| WXGA | 1280x800 | 16:10 | Web 应用 |
| FWXGA | 1366x768 | ~16:9 | Web 应用 |
| FHD | 1920x1080 | 16:9 | 最大推荐分辨率 |

对于绝大多数使用场景，1024x768 或 1280x800 是分辨率的最佳平衡点——足够让 Claude 看清 UI 元素，又在 API 的尺寸限制之内。

### 7.2.4 坐标系统与缩放

Claude 返回的座标在**下采样后的图像空间**中，而不是你的真实屏幕空间。这是 Computer Use 中最容易出错的环节。

**完整流程：**

```
真实屏幕 (1512×982)
    │
    ├─ 比例因子 = min(1.0, 1568/1512, sqrt(1.15M / (1512×982)))
    │            = min(1.0, 1.037, 0.881)
    │            ≈ 0.881
    │
    ├─ 缩放截图 (1332×865)  ──发送给──→  Claude API
    │                                        │
    │                              Claude 返回座标 (例如 [400, 300])
    │                                        │
    ├─ 反向缩放 ←────────────────────────────┘
    │   screen_x = 400 / 0.881 ≈ 454
    │   screen_y = 300 / 0.881 ≈ 341
    │
    └─ 真实座标 (454, 341)
```

**表 7-4：座标缩放算法**

| 步骤 | 公式 | 方向 |
|------|------|------|
| 1. 计算比例因子 | `min(1.0, 1568/max(W,H), sqrt(1.15M / (W×H)))` | 真 → API |
| 2. 缩放截图 | `new_W = round(W × factor)`, `new_H = round(H × factor)` | 真 → API |
| 3. 发送给 Claude | — | — |
| 4. Claude 返回座标 | `(X_api, Y_api)` | API 空间 |
| 5. 还原座标 | `X_real = round(X_api / factor)`, `Y_real = round(Y_api / factor)` | API → 真 |

**Opus 4.7 例外**：Claude Opus 4.7 支持高达 2576 像素的长边，其座标与图像像素 1:1 对应，无需坐标缩放。

### 7.2.5 鼠标操作详解

**表 7-5：鼠标动作对比**

| 动作 | 需要座标 | 产生效果 | 使用建议 |
|------|----------|----------|----------|
| `mouse_move` | 是 | 移动光标至 (x, y) | 配合后续点击使用 |
| `left_click` | 是 | 在 (x, y) 单击 | 最常用 |
| `left_mouse_down` | 否 | 在当前光标位置按下左键 | 配合 `left_mouse_up` 实现拖拽 |
| `left_mouse_up` | 否 | 释放左键 | 配合 `left_mouse_down` |
| `left_click_drag` | 是 | 从当前位置拖拽至 (x, y) | 拖拽操作 |
| `double_click` | 是 | 在 (x, y) 双击 | 打开文件/文件夹 |
| `triple_click` | 是 | 在 (x, y) 三击 | 选中整行文本 |
| `right_click` | 是 | 右键菜单 | 上下文菜单 |
| `middle_click` | 是 | 中键点击 | 浏览器：在新标签打开链接 |

**关于 `mouse_move` + `left_click` 与 `left_click` 的区别：**

- 当直接的 `left_click` 动作包含 `coordinate` 时，Claude 的意图是先移动光标再点击。
- 当使用 `left_mouse_down` + `mouse_move` + `left_mouse_up` 三段式时，实现的是精细拖拽控制。
- 实际实现中，`left_click` 带 coordinate 应该被翻译为 `mousemove + click`，而 `left_mouse_down` 只做按下。

### 7.2.6 键盘操作详解

**表 7-6：键盘操作对比**

| 动作 | 参数 | 效果 | 使用场景 |
|------|------|------|----------|
| `type` | `text: string` | 逐字符键入文本 | 填充表单、输入搜索词 |
| `key` | `text: string` | 按下组合键 | 快捷键（Ctrl+S, Alt+Tab） |
| `hold_key` | `text: string`, `duration: number` | 按住键一段时间 | 长按修饰键 |

**`type` vs `key` 的关键区别：**

- `type` 是逐字符输入，模拟人类打字。它会触发每个按键的 keydown/keyup 事件，适合文本输入。
- `key` 是一次性按下组合键，适合快捷键。例如 `"ctrl+s"` 会同时按下 Ctrl 和 S。

**常见键名参考：**

| 键名 | 对应按键 | 键名 | 对应按键 |
|------|----------|------|----------|
| `Return` | Enter | `Tab` | Tab |
| `Escape` | Esc | `BackSpace` | Backspace |
| `Delete` | Delete | `space` | 空格 |
| `Up/Down/Left/Right` | 方向键 | `Home/End` | Home/End |
| `Page_Up/Page_Down` | 翻页键 | `F1`-`F12` | 功能键 |
| `ctrl` | Control | `alt` | Alt |
| `shift` | Shift | `super` | Cmd/Win |

### 7.2.7 滚动操作

滚动操作是 `computer_20250124` 引入的增强动作，减少了实现拖拽滚动条的复杂性：

```json
{"action": "scroll", "coordinate": [500, 400], "scroll_direction": "down", "scroll_amount": 3}
```

**表 7-7：滚动方向**

| 方向 | 效果 | 对应滚轮方向 |
|------|------|-------------|
| `up` | 内容向下移动，看到上方内容 | 滚轮向下 |
| `down` | 内容向上移动，看到下方内容 | 滚轮向上 |
| `left` | 内容向右移动 | — |
| `right` | 内容向左移动 | — |

`scroll_amount` 表示滚动的"单位"，1 个单位通常对应滚轮的一个刻度。在应用中滚动没有效果时，可以尝试键盘替代方案（如 Page Down）。

### 7.2.8 等待与缩放

**`wait`** 让 Claude 可以在动作之间暂停。某些 UI 需要时间响应（如页面加载、动画过渡）：
```json
{"action": "wait", "duration": 1.5}
```

**`zoom`**（`computer_20251124` 专属）让 Claude 可以放大查看屏幕的特定区域。在工具定义中需要设置 `enable_zoom: true`：
```json
{"action": "zoom", "region": [100, 200, 400, 350]}
```
`region` 的四个数字分别是：`[左上角x, 左上角y, 右下角x, 右下角y]`。

### 7.2.9 Beta 状态与行为差异

Computer Use 目前是 **Beta** 状态。以下是 Beta 带来的具体影响：

**表 7-8：Beta 行为特征**

| 方面 | 当前状态 | 影响 |
|------|----------|------|
| 系统提示开销 | 额外 466-499 tokens | 每次请求的输入 token 基数增加 |
| 工具定义开销 | 735 tokens（Claude 4.x） | 在工具列表中添加 Computer Use 的成本 |
| 图像定价 | 标准 Vision 定价 | 截图作为图像计费 |
| 模型可用性 | 需要特定模型 + Beta 头 | 不能随意换模型 |
| ZDR 支持 | 支持 | 数据不会在 Anthropic 端持久存储 |
| 座标精度 | 可能出错或幻觉 | 需验证、Extended Thinking 可辅助 |

**Beta 版本升级路径：**

```
computer_20241022  ──(已弃用)──→  computer_20250124
                                     │
                ┌────────────────────┘
                ▼
        computer_20251124 (当前推荐)
          ├── 新增 zoom 动作
          ├── Opus 4.7 支持 2576px 长边
          └── 需要 "computer-use-2025-11-24" beta 头
```

### 7.2.10 安全边界

Computer Use 引入了传统 API 功能不具备的风险。当 Claude 能够控制桌面环境时，以下风险需要特别关注：

**表 7-9：安全风险与缓解措施**

| 风险 | 严重性 | 缓解措施 |
|------|--------|----------|
| Prompt Injection（网页/图像中的恶意指令） | **高** | 使用专用 VM/容器；隔离敏感数据；启用 Anthropic 的 prompt-injection 分类器 |
| 敏感信息泄露（截图中包含银行信息等） | 高 | 过滤截图内容；使用虚拟化环境；限制可访问的网站白名单 |
| 意外操作（误删文件、发送消息等） | 中 | 人类确认关键决策；最小权限原则；操作日志审计 |
| 无限 Agent Loop | 中 | 设置 max_iterations；监控 API 开销 |
| 沙箱逃逸 | 低（容器化） | Docker 隔离；禁用宿主机挂载；网络隔离 |

**人类确认机制（Human Confirmation）**：Anthropic 在 Computer Use 中内置了自动的 prompt-injection 分类器。当分类器检测到截图中的潜在注入攻击时，会自动引导模型在执行操作前请求用户确认。你可以在需要时联系 Anthropic 关闭此保护——但这是不推荐的。

**最小权限原则的实现建议：**

```python
# 推荐的 Computer Use 环境配置
ENVIRONMENT = {
    "isolation": "docker",           # 容器隔离
    "privileged": False,             # 非特权模式
    "network": "allowlist_only",     # 网络白名单
    "storage": "ephemeral",          # 临时存储
    "confirm_threshold": "high",     # 高风险操作需人工确认
}
```

### 7.2.11 与标准 Tool Use 的对比

**表 7-10：Computer Use vs 标准 Tool Use**

| 维度 | 标准 Tool Use | Computer Use |
|------|---------------|--------------|
| **Schema 定义** | 用户自定义 `input_schema` | 内置 schema（不可修改） |
| **抽象层级** | 结构化数据（JSON → JSON） | GUI 交互（截图 → 动作） |
| **状态管理** | 无状态（每次调用独立） | 有状态（屏幕是共享状态） |
| **错误处理** | 返回结构化错误文本 | 坐标错误、截图失败、UI 响应超时 |
| **执行方** | 客户端代码 | 客户端 + Docker/VM 环境 |
| **Beta 要求** | 无 | 需要 Beta 头 |
| **延迟特征** | 毫秒级 | 秒级（截图传输 + 动作执行） |
| **成本模型** | 标准 token 计费 | token + Vision（截图）+ Beta 开销 |
| **最佳场景** | API 调用、数据库查询、计算 | Web 自动化、GUI 测试、桌面操作 |

**核心洞察**：Computer Use 不是标准 Tool Use 的替代品——它们是互补的。一个设计良好的 Agent 应该：

1. **优先使用结构化工具**（当有 API/接口可用时）——更快、更可靠、更便宜。
2. **退回到 Computer Use**（当只有 GUI 可用时）——最后的手段，但也是唯一的途径。

---

## 7.3 Python 实现

完整实现位于 `code/python/ch07/computer_use.py`。以下是核心组件的解析。

### 7.3.1 坐标缩放

```python
import math

MAX_LONG_EDGE = 1568
MAX_TOTAL_PIXELS = 1_150_000


def get_scale_factor(width: int, height: int) -> float:
    """计算符合 API 限制的缩放因子。"""
    long_edge = max(width, height)
    total_pixels = width * height
    long_edge_scale = MAX_LONG_EDGE / long_edge
    total_pixels_scale = math.sqrt(MAX_TOTAL_PIXELS / total_pixels)
    return min(1.0, long_edge_scale, total_pixels_scale)


def scale_coordinates_up(x: int, y: int, scale: float) -> tuple[int, int]:
    """将 API 空间的座标还原到屏幕空间。"""
    return round(x / scale), round(y / scale)
```

关键点：
- 同时约束长边和总像素数，取最严格的限制。
- `scale_coordinates_up` 是 Claude 返回座标后必须执行的步骤。
- 对于 Opus 4.7，如果 display 不超过 2576px，`get_scale_factor` 返回 1.0，无需转换。

### 7.3.2 动作验证器

```python
class ActionValidator:
    """纯逻辑参数验证——无副作用，可独立单元测试。"""
    
    def validate(self, action: str, params: dict) -> tuple[bool, str | None]:
        if action == "screenshot":
            return True, None
        if action in ("left_click", "right_click", ...):
            coord = params.get("coordinate")
            if coord is None:
                return False, "Missing 'coordinate'"
            x, y = coord
            if not (0 <= x < self.display_width):
                return False, f"X coordinate {x} out of bounds"
            # ... 验证 y
        # ... 覆盖 17 种动作
```

验证器的设计原则：
- **零副作用**——只做检查，不执行任何操作。
- **覆盖所有动作**——包括 `zoom`（20251124 新增）。
- **明确错误信息**——便于格式化 `tool_result` 中的 `is_error: true`。

### 7.3.3 ComputerUseClient

```python
class ComputerUseClient:
    def __init__(self, *, display_width_px=1024, display_height_px=768, ...):
        self._scale = get_scale_factor(display_width_px, display_height_px)
        # 可插拔的回调——生产环境中替换为真实 I/O
        self._screenshot_cb: Callable | None = None
        self._mouse_cb: Callable | None = None
        self._keyboard_cb: Callable | None = None
    
    def on_screenshot(self, cb: Callable) -> None: ...
    def on_mouse(self, cb: Callable) -> None: ...
    def on_keyboard(self, cb: Callable) -> None: ...
    
    def execute_action(self, **params) -> ToolActionResult:
        action = params.get("action")
        valid, err = self._validator.validate(action, params)
        if not valid:
            return ToolActionResult(success=False, error=err)
        return self._dispatch(action, params)
```

设计要点：
- **回调注入模式**——`on_screenshot`、`on_mouse`、`on_keyboard` 让你可以将真实的截图/鼠标/键盘操作注入客户端，而不修改核心逻辑。
- **无外部依赖**——不 import anthropic SDK、不 import X11 库。你的测试环境不需要显示器。
- **`auto_scale` 开关**——可以关闭坐标自动缩放，用于测试或 Opus 4.7 场景。

### 7.3.4 Agent Loop

```python
class AgentLoop:
    def run(self, messages, *, system=None) -> AgentLoopResult:
        tools = [self._client.build_tool_schema()]
        iterations = 0
        while iterations < self._config.max_iterations:
            iterations += 1
            response = self._api_call(messages=messages, tools=tools, ...)
            messages.append({"role": "assistant", "content": response["content"]})
            
            tool_results = []
            for block in response["content"]:
                if block["type"] == "tool_use":
                    result = self._client.execute_action(**block["input"])
                    tool_results.append(
                        ComputerUseClient.format_tool_result(result, block["id"])
                    )
                elif block["type"] == "text":
                    final_text = block["text"]
            
            if not tool_results:  # Claude 只返回了文本——任务完成
                return AgentLoopResult(completed=True, ...)
            
            messages.append({"role": "user", "content": tool_results})
        
        return AgentLoopResult(completed=False, ...)  # 达到最大迭代次数
```

Agent Loop 的关键特征：
- **迭代上限**——防止无限制的 API 调用（参考实现使用 `max_iterations=10`）。
- **多工具并行**——一个 assistant 消息中可以包含多个 `tool_use` 块，一次循环全部执行。
- **完成检测**——当 Claude 不再请求任何工具时，循环终止。

---

## 7.4 Node.js 实现

完整实现位于 `code/node/ch07/ComputerUseClient.ts`。API 设计与 Python 版本一致。

### 7.4.1 核心类型

```typescript
type Action =
  | "screenshot" | "left_click" | "right_click" | "middle_click"
  | "double_click" | "triple_click" | "left_click_drag"
  | "left_mouse_down" | "left_mouse_up" | "mouse_move"
  | "type" | "key" | "hold_key" | "scroll" | "wait"
  | "cursor_position" | "zoom";

interface ScreenshotResult {
  readonly base64Image: string;
  readonly mediaType: string;
  readonly width: number;
  readonly height: number;
}

interface ToolActionResult {
  readonly success: boolean;
  readonly output: string | null;
  readonly error: string | null;
  readonly screenshot: ScreenshotResult | null;
}
```

### 7.4.2 回调注册

```typescript
export class ComputerUseClient {
  onScreenshot(cb: ScreenshotCallback): void { this._screenshotCb = cb; }
  onMouse(cb: MouseCallback): void { this._mouseCb = cb; }
  onKeyboard(cb: KeyboardCallback): void { this._keyboardCb = cb; }
}
```

### 7.4.3 Agent Loop（异步版）

```typescript
export class AgentLoop {
  async run(messages, options = {}): Promise<AgentLoopResult> {
    const tools = [this._client.buildToolSchema()];
    while (iterations < this._config.maxIterations) {
      const response = await this._apiCall!({ messages, tools, ... });
      messages.push({ role: "assistant", content: response.content });

      const toolResults: ToolResultContentBlock[] = [];
      for (const block of response.content) {
        if (block.type === "tool_use") {
          const result = await this._client.executeAction(block.input);
          toolResults.push(ComputerUseClient.formatToolResult(result, block.id));
        }
      }
      if (!toolResults.length) return { completed: true, ... };
      messages.push({ role: "user", content: toolResults });
    }
    return { completed: false, ... };
  }
}
```

Node.js 版本的 Agent Loop 全部使用 `async/await`，适合 Node.js 22+ 的异步运行时。与 Python 版本的关键差异：
- `ScreenshotCallback` 可以是同步或异步的（`ScreenshotResult | Promise<ScreenshotResult>`）。
- 回调参数使用结构化接口（`MouseActionParams`、`KeyboardActionParams`）而非 `**kwargs`。

---

## 7.5 最佳实践

### 7.5.1 截图分析循环模式

不要依赖一次截图就完成整个任务。推荐使用 Anthropic 官方建议的"截图——评估——重试"模式：

```
1. 执行动作前截图
2. 执行动作
3. 等待（0.5-2 秒）
4. 执行动作后截图
5. 让 Claude 比较两张截图
6. 如果目标未达成 → 重试
7. 如果达成 → 继续下一步
```

在 system prompt 中提示 Claude：

```
After each step, take a screenshot and carefully evaluate if you have 
achieved the right outcome. Explicitly show your thinking: "I have 
evaluated step X..." If not correct, try again. Only when you confirm 
a step was executed correctly should you move on to the next one.
```

### 7.5.2 坐标归一化

**永远不要假设 Claude 返回的座标可以直接使用。** 采用以下流程：

```python
def execute_click_from_claude(x: int, y: int, scale: float):
    """将 Claude 的座标转换为屏幕座标并执行点击。"""
    if scale < 1.0:
        screen_x = round(x / scale)
        screen_y = round(y / scale)
    else:
        screen_x, screen_y = x, y
    
    # 边界检查
    if not (0 <= screen_x < SCREEN_WIDTH and 0 <= screen_y < SCREEN_HEIGHT):
        raise ValueError(f"Scaled coordinates ({screen_x}, {screen_y}) out of bounds")
    
    perform_real_click(screen_x, screen_y)
```

### 7.5.3 错误恢复策略

**表 7-11：常见错误与恢复策略**

| 错误 | 原因 | 恢复方式 |
|------|------|----------|
| 座标超出边界 | 缩放计算错误 | 检查 `scale_factor`；记录日志；返回 `is_error: true` |
| 截图失败 | 显示器锁定或不可用 | 返回错误描述；让 Claude 决定是否重试 |
| 点击无响应 | UI 元素未正确加载 | 增加 `wait` 延迟；使用键盘快捷键替代 |
| 滚动无效 | 某些应用不响应 X11 滚动事件 | 使用 `Page_Down` 键盘快捷键 |
| Prompt Injection 警告 | 分类器检测到恶意内容 | 实施人类确认机制；不要盲目执行 |

**格式化错误 `tool_result` 示例：**

```python
{
    "type": "tool_result",
    "tool_use_id": block_id,
    "content": [
        {"type": "text", "text": "Error: Coordinates (1200, 900) are outside display bounds (1024x768)."}
    ],
    "is_error": True
}
```

### 7.5.4 图像管理优化

长时间 Agent Loop 中，截图会积累大量的 token 消耗。参考实现中的策略：

1. **仅保留最近 N 张截图**（如 `only_n_most_recent_images=3`）。
2. **使用 Prompt Caching**（`prompt-caching-2024-07-31` beta），缓存系统提示和早期对话，使后续截图只产生增量成本。
3. **压缩截图**——JPEG 质量 80% 通常足够 Claude 理解 UI，且比 PNG 小很多。

```python
# 压缩截图示例
from io import BytesIO
from PIL import Image

def compress_screenshot(image_bytes: bytes, quality: int = 80) -> bytes:
    img = Image.open(BytesIO(image_bytes))
    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()
```

### 7.5.5 安全清单

在生产中部署 Computer Use 前，确认清单中的每项：

- [ ] 使用专用 VM 或 Docker 容器运行 Computer Use 环境。
- [ ] 不要给 Claude 访问敏感账户、密码或支付信息的权限。
- [ ] 限制可访问的网站域名为白名单。
- [ ] 实施人工确认机制：涉及金融交易、Cookie 接受、服务条款同意的操作需要人类批准。
- [ ] 设置 Agent Loop 的 `max_iterations` 上限（建议 ≤ 10）。
- [ ] 记录所有动作和截图用于事后审计。
- [ ] 监控 API 使用量——截图可能快速积累 token 成本。
- [ ] 告知最终用户相关风险并获取同意。

### 7.5.6 Prompt 工程建议

Claude 的 Computer Use 能力很大程度上取决于 prompt 的质量：

1. **任务分解**：与其说"处理我的邮件"，不如说"打开 Firefox，导航到 gmail.com，查看未读邮件"。
2. **键盘优先**：如果 UI 元素（如下拉菜单、滚动条）难以通过鼠标操作，提示 Claude 使用键盘快捷键。
3. **提供凭据**：使用 `<robot_credentials>` XML 标签提供登录凭据（但仅在已评估注入风险后）。
4. **多会话验证**：对于跨会话的 Agent，在每个会话开始时进行端到端验证——代码级审查无法捕捉浏览器级回归。

---

## 7.6 自测题

### 问题 1：协议理解

Computer Use 的 `screenshot` 动作和 `mouse_move` 动作中，哪个需要 `coordinate` 参数？哪些动作是 `computer_20250124` 相对于 `computer_20241022` 新增的？

<details>
<summary>参考答案</summary>

- `screenshot` **不需要** `coordinate` 参数；`mouse_move` **需要** `coordinate: [x, y]`。
- `computer_20250124` 新增动作：`right_click`、`double_click`、`triple_click`、`left_mouse_down`、`left_mouse_up`、`scroll`、`hold_key`、`wait`。

</details>

### 问题 2：坐标缩放

你的屏幕分辨率是 2560x1440。截图发送给 Claude 后，Claude 返回点击座标 `(600, 400)`。请问：
1. 缩放因子是多少？（保留 3 位小数）
2. 真实屏幕座标是多少？

<details>
<summary>参考答案</summary>

1. `scale = min(1.0, 1568/2560, sqrt(1_150_000 / (2560×1440))) = min(1.0, 0.6125, 0.5585) ≈ 0.559`
2. `screen_x = round(600 / 0.559) ≈ 1073`，`screen_y = round(400 / 0.559) ≈ 716`

所以真实座标是 **(1073, 716)**。

</details>

### 问题 3：Agent Loop 实现（编程题）

补全以下 Agent Loop 代码中的 `TODO` 部分：

```python
from computer_use import ComputerUseClient, AgentLoop, AgentLoopConfig


def my_agent_loop(user_task: str, api_key: str) -> str:
    """运行一个 Computer Use Agent Loop 直到任务完成或迭代上限。"""
    client = ComputerUseClient(display_width_px=1024, display_height_px=768)
    config = AgentLoopConfig(max_iterations=5)
    loop = AgentLoop(client, config=config)
    
    # TODO: 注册 api_call 回调
    # 提示：使用 anthropic.Anthropic() 客户端调用 beta.messages.create
    # 需要传入：model, max_tokens, messages, tools, betas
    
    # TODO: 启动 agent loop
    # 提示：调用 loop.run() 并传入初始消息
    
    # TODO: 返回最终结果
    # 提示：检查 AgentLoopResult 的 completed 和 final_text 字段
    
    return ""
```

<details>
<summary>参考答案</summary>

```python
from computer_use import ComputerUseClient, AgentLoop, AgentLoopConfig
import anthropic


def my_agent_loop(user_task: str, api_key: str) -> str:
    client = ComputerUseClient(display_width_px=1024, display_height_px=768)
    config = AgentLoopConfig(max_iterations=5)
    loop = AgentLoop(client, config=config)

    # 注册 api_call 回调
    anthropic_client = anthropic.Anthropic(api_key=api_key)

    def call_api(**kwargs):
        response = anthropic_client.beta.messages.create(**kwargs)
        return {
            "id": response.id,
            "content": [
                {
                    "type": block.type,
                    "id": getattr(block, "id", None),
                    "name": getattr(block, "name", None),
                    "input": getattr(block, "input", None),
                    "text": getattr(block, "text", None),
                }
                for block in response.content
            ],
            "stop_reason": response.stop_reason,
        }

    loop.on_api_call(call_api)

    # 启动 agent loop
    result = loop.run([
        {"role": "user", "content": user_task},
    ])

    # 返回最终结果
    if result.completed:
        return result.final_text or "Task completed (no text response)"
    return f"Task incomplete after {result.iterations} iterations"
```

</details>

### 问题 4：安全边界分析

假设你在构建一个允许用户通过自然语言描述操作桌面环境的 SaaS 产品。列出至少 4 个你必须实施的安全措施，并说明每个措施防范什么风险。

<details>
<summary>参考答案</summary>

1. **Docker 容器隔离**：每个用户会话运行在独立的 Docker 容器中，防止用户 A 的 Claude 操作影响用户 B 的桌面环境。防范跨租户攻击和意外操作扩散。

2. **网络白名单**：限制 Claude 只能访问预定义的域名列表，防止被恶意网站利用（如钓鱼页面、恶意软件下载站）或访问内部网络资源。

3. **操作审计日志**：记录所有 Computer Use 动作（截图、点击座标、键入文本）和 Claude 的推理过程。用于事后分析安全事故和合规审计。

4. **高风险操作的人类确认**：涉及用户登录、Cookie 接受、支付操作、敏感文件删除等操作时，暂停 Agent Loop 并请求人类用户确认。防范 Claude 被 prompt-injection 诱导执行不可逆操作。

5. **max_iterations 限制 + 费用告警**：设置 Agent Loop 最多 10 次迭代，并在 API 消费超过预算时自动暂停。防止无限循环导致的高额 API 账单。

6. **截图内容过滤**：在发送截图给 Claude 之前（或之后），对截图内容进行敏感信息检测（如信用卡号、密码字段）。虽然 Anthropic 提供 ZDR，但模型在推理过程中仍能看到这些信息。

</details>

---

**本章关键收获：**

- Computer Use 是 Tool Use 协议的一个特化实例——使用相同的 `tool_use`/`tool_result` 机制，但 schema 内置在模型中。
- 坐标系统是 Computer Use 中最容易出错的部分：Claude 返回的是 API 空间的座标，必须缩放回屏幕空间。
- `computer_20251124` 是当前推荐版本，新增 `zoom` 动作，并且在 Opus 4.7 上支持 2576px 长边 1:1 座标。
- 安全不是可选的——Computer Use 的风险远高于纯文本 API 调用。隔离、白名单、审计、确认机制缺一不可。
- Agent Loop 是通用模式，不限于 Computer Use——它同样驱动任何 tool_use 场景。
