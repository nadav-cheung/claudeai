# 第 4 章：Structured Outputs（结构化输出）

> **本章目标**：掌握 Anthropic 结构化输出（Structured Outputs）的协议层机制。读完本章后，你将理解 Constrained Decoding 的底层原理，能够使用 `output_config` 参数精确约束 Claude 的输出格式，并掌握 Schema 设计的最佳实践。

---

## 4.1 概念全景

### 大模型输出的可控性悖论

大语言模型的核心能力——根据上下文生成自然语言——同时也是其最大的不可靠性来源。对于"总结这篇文档"这类开放式任务，自由文本输出是理想的。但对于以下场景，自由文本输出直接变成了工程灾难：

- **数据提取管道**：从非结构化文本中提取实体。如果模型返回"姓名是张三"，你还需要写正则表达式解析——而正则表达式面对自然语言的多样性极其脆弱。
- **API 返回值**：将 Claude 作为微服务的推理引擎。下游代码期望的是一个可靠的 `{"sentiment": "positive", "score": 0.87}` 对象，而不是 "我认为这条评论是正面的"。
- **多 Agent 协作**：Agent A 将输出传递给 Agent B。如果两个 Agent 之间没有结构化的契约，Agent B 会在解析上游输出上消耗大量 Token，且容易出错。
- **前端渲染**：UI 组件需要特定结构的数据来驱动渲染。没有结构化输出，你需要在前后端之间增加一个不可靠的格式转换层。

### 结构化输出的演化史：从 Regex 到 Constrained Decoding

在深入 Anthropic 的实现之前，理解这一领域的技术演化有助于你把握 Structured Outputs 在整个 AI 工程生态中的历史定位。

**第一代：基于正则的后解析（2019-2022）**

早期的解决方式是"先让模型自由生成，然后用正则表达式从生成结果中提取"。例如，定义一个 Prompt 让模型返回 JSON，然后用 `re.search(r'\{.*\}', response, re.DOTALL)` 从响应中捞出 JSON 部分。

这种方法的问题数不胜数：一是正则表达式对不完整 JSON（缺少闭合括号、嵌套引号转义不完整）几乎没有容错能力；二是每次修复正则的成本都大于其收益；三是团队最终都会在解析层积累大量技术债务。

**第二代：基于重试的验证循环（2022-2023）**

OpenAI 引入 Function Calling（2023年6月）和 JSON Mode（2023年11月）标志着结构化输出的第二代。核心思路是"生成后验证"——模型尽量生成合法的 JSON，如果解析失败则重试。

重试机制虽然提高了可靠性，但带来了根本性的效率问题：
- 每次重试消耗额外的 Token（包括输入的重复消费）。
- 重试次数不确定，导致延迟的尾部分布（tail latency）不可预测。
- 模型仍然可能输出"几乎合法但不完全合法"的结果，特别是在复杂嵌套结构下。

**第三代：Constrained Decoding（2024-至今）**

Anthropic 的 Structured Outputs 代表了第三代方案：**在 Token 生成层面实施约束，而非在生成后验证**。这一范式的核心优势在于"数学保证"——只要生成正常完成，输出在语法层面 100% 符合 Schema，无需重试，无需正则解析。

### 两种实现路径：Prompt Engineering vs Constrained Decoding

在 Structured Outputs 特性出现之前，开发者只能依赖 Prompt Engineering 来获得结构化的输出：

```
请在回答时严格遵循以下 JSON 格式,不要添加任何其他文字:
{
  "name": "姓名",
  "age": 数字,
  "email": "邮箱地址"
}
```

这种方法的根本问题在于：**Prompt 是建议，不是约束**。模型的输出始终存在概率性的偏差：

1. **格式漂移**：模型可能在 JSON 前后添加 "这是结果：" 之类的引导语。
2. **类型错误**：`"age": "三十岁"` 而不是 `"age": 30`。
3. **结构变异**：模型可能输出 `{"person": {"name": "..."}}` 而不是预期的扁平结构。
4. **截断不完整**：如果生成被 `max_tokens` 截断，输出的 JSON 可能缺少闭合括号。
5. **长尾失败**：即使 Prompt 在 100 次测试中 99 次有效，那 1 次失败在生产环境中可能意味着整个管道的崩溃。

Anthropic 的 Structured Outputs 从根本上改变了这一局面：**约束不是在 Prompt 层面施加的，而是在 Token 生成层面实施的**。

### Constrained Decoding 的核心思路

Constrained Decoding（约束解码）的核心思想是：**在每个 Token 生成步骤中，模型只允许从那些能够形成合法 Schema 输出的 Token 候选集中选择**。

这类似于一个"语法编译器"的工作方式：

1. 你提供一个 JSON Schema（数据结构的声明式描述）。
2. API 服务端将这个 Schema 编译为一个有限状态自动机（Finite State Automaton）或上下文无关文法（Context-Free Grammar）。
3. 在每个解码步骤中，自动机定义了"哪些 Token 是当前状态下合法延续"。
4. 不合法的 Token 的 logit 值被设为 -inf（logit masking），确保它们永远不会被采样。

结果是：**模型输出的每一个字符在生成时都经过了 Schema 验证**。你的 Prompt 可以专注于告诉模型"提取什么"，而不需要教它"如何格式化"。

### Constrained Decoding 与其他厂商方案的技术对比

虽然本章聚焦于 Anthropic 的实现，但了解其在更大生态中的位置有助于架构决策。

OpenAI 的 Structured Outputs（2024年8月发布）采用了类似但独立的路径。两者的核心差异在于：

- **Schema 支持范围**：OpenAI 支持 `$ref` 和 `definitions` 引用，允许更模块化的 Schema 组织。但 Anthropic 的全内联 Schema 避免了引用解析的隐式依赖和潜在的循环引用问题。
- **strict 模式**：OpenAI 使用 `strict: true` 开关控制约束等级；Anthropic 使用分层级的 `effort` 参数，提供更精细的控制。
- **流式支持**：OpenAI 在 Structured Outputs 中支持流式；Anthropic 当前要求非流式模式。这一差异影响实时性敏感的应用（如聊天界面的打字机效果）。
- **模型覆盖**：Anthropic 的 Structured Outputs 从 Claude 3.5 Sonnet 开始原生支持（无需额外配置），而早期 Claude 模型需要通过 Tool Use 间接实现。

理解这些差异的价值不在于"谁更好"，而在于选择与你的性能目标、Schema 复杂度和架构约束最匹配的方案。

### 本章学习成果

完成本章的学习和编码练习后，你将能够：

1. 理解 Constrained Decoding 的底层原理（grammar compilation、logit masking）及其与 Prompt-based JSON 的本质区别。
2. 掌握 Anthropic `output_config` 参数的完整协议规范，包括 `format`、`schema` 和 `effort` 字段。
3. 在自己的代码中实现不依赖 SDK 的 Structured Outputs 客户端，直接通过 HTTP 层使用 `output_config` 参数。
4. 设计高效、可靠的 JSON Schema，避免常见的 Schema 设计陷阱，并在不同场景下选择合适的结构化输出策略（Structured Outputs vs Tool Use）。

---

## 4.2 协议规范逐层拆解

### 4.2.1 Constrained Decoding 的底层原理

Constrained Decoding 不是 Anthropic 独有的概念——它在学术界和工业界有深厚的理论基础。理解其原理有助于你评估这个特性的能力边界和适用场景。

**背景：自回归解码的数学框架**

在标准的自回归语言模型中，给定上文序列 \( x_{<t} \)，第 t 个位置的 Token 生成遵循条件概率分布：

\[ P(x_t | x_{<t}) = \text{softmax}(W \cdot h_t) \]

其中 \( h_t \) 是模型在位置 t 的隐藏状态，\( W \) 是输出投影矩阵。采样过程从整个词汇表 \( V \) 上选择一个 Token（通常经过 temperature scaling 和 top-p/top-k 过滤）。

Constrained Decoding 在这一框架中插入了一个关键步骤：**在 softmax（或采样）之前，根据外部约束掩码部分 Token 的概率**。

**阶段一：Schema 到语法的编译**

你提供的 JSON Schema 不是直接传递给模型。首先，它被编译为一个确定性的语法规则集。以以下 Schema 为例：

```json
{
  "type": "object",
  "properties": {
    "name": {"type": "string"},
    "age": {"type": "integer"}
  },
  "required": ["name", "age"]
}
```

编译过程将其转化为一个有限状态自动机（FSA），大致包含以下状态：

```
STATE_0: 必须输出 '{'
STATE_1: 必须输出 '"name"'
STATE_2: 必须输出 ':'
STATE_3: 可以输出任意字符串（JSON string 合法字符集）
STATE_4: 必须输出 ','
STATE_5: 必须输出 '"age"'
STATE_6: 必须输出 ':'
STATE_7: 可以输出数字字符（0-9，可选负号）
STATE_8: 必须输出 '}'
STATE_9: 终止状态（EOS token 合法）
```

实际上，自动机的结构远比这个简化模型复杂，需要处理可选字段、嵌套对象、数组、enum 约束、$ref 引用等等。但对于理解原理，这个简化模型已经足够。

**编译过程中的关键决策**

Schema 编译不仅仅是一个机械的翻译过程，它涉及多个需要权衡的决策：

1. **属性顺序**：JSON Schema 规范中 `properties` 是一个无序映射，但自动机必须确定属性的输出顺序。Anthropic 的实现按照 Schema 中 `properties` 的定义顺序输出，这为 Prompt 设计提供了有用的确定性。

2. **可选字段处理**：对于不在 `required` 中的字段，自动机在每个可选字段处引入分支状态。分支越多，自动机的复杂度越高。这就是为什么拥有大量可选字段的 Schema 可能导致性能下降。

3. **递归和引用展开**：由于 Anthropic 不支持 `$ref`，所有嵌套结构必须在编译时完全内联展开。深层嵌套的结构在编译后的自动机中表现为更深的状态路径。

4. **enum 优化**：`enum` 约束被编译为精确的 Token 序列匹配器——自动机只在枚举值之间选择。这使得 `enum` 是最高效的约束类型之一。

**阶段二：Logit Masking 的数学定义**

在正常的自回归解码中，语言模型在每一步计算所有可能 Token 的概率分布（logits），然后从中采样。Constrained Decoding 在这个概率分布上施加一个掩码（mask）：

```python
# 伪代码：Constrained Decoding 的每一步
def constrained_sample(logits, current_state, automaton):
    # 获取当前状态下所有合法的 Token
    allowed_tokens = automaton.allowed_tokens(current_state)

    # 将非法 Token 的 logit 设为 -inf（概率为 0）
    for token_id in range(vocab_size):
        if token_id not in allowed_tokens:
            logits[token_id] = -float("inf")

    # 在约束后的分布上采样
    next_token = sample(logits)

    # 更新自动机状态
    automaton.advance(next_token)
    return next_token
```

**合法 Token 集的计算**

`automaton.allowed_tokens(current_state)` 的计算是 Constrained Decoding 的核心性能瓶颈。对于给定的自动机状态，需要确定词汇表中的每个 Token（通常 100K-200K 个 Token）是否是当前状态的合法延续。

这是一个非平凡的问题，因为：
- 一个 Token 可能包含多个字符（BPE tokenization），例如 `"name"` 可能是一个单独的 Token。
- 自动机状态是按字符定义的，但模型输出的是 Token。
- 需要判断一个 Token 的所有可能解码路径中，是否至少有一条能通过自动机。

高效的实现使用预处理过的"Token 到字符前缀"映射表和增量自动机遍历算法，将每个解码步骤的合法性检查复杂度从 O(|V| * L) 降低到 O(|V|)，其中 L 是 Token 长度。

**Logit Masking 对采样分布的副作用**

将某些 Token 的 logit 设为 -inf 不仅移除了这些 Token，还改变了剩余 Token 的相对概率分布。这是因为 softmax 函数的归一化特性：

\[ \text{softmax}(x_i) = \frac{e^{x_i}}{\sum_j e^{x_j}} \]

当分母中的某些 \( e^{x_j} \) 被设为 0 后，剩余 Token 的概率会被重新分配。这可能导致某些"合法但不自然"的 Token 获得异常高的概率——模型在受约束的情况下可能输出在语义上显得生硬或不自然的内容。

`effort` 参数在底层的作用之一就是控制模型在约束条件下进行多少次额外的内部推理，以找到既合法又自然的 Token 选择。

**阶段三：增量解析与流式挑战**

对于流式（streaming）场景，自动机需要增量地处理到来的 Token，在流式过程中持续验证。Anthropic API 目前要求 Structured Outputs 使用非流式模式（`stream: false`），因为完整 Schema 验证需要整个输出的上下文。

这背后的技术原因是多方面的：
- 在生成前几个 Token 时，自动机尚无法确定整个输出的结构（例如，模型可能选择不输出某个可选字段）。
- 某些 JSON Schema 约束（如 `additionalProperties: false`）需要等到整个对象生成完成后才能验证。
- 流式场景下的 Logit Masking 错误恢复更复杂——如果自动机进入了错误状态，回退代价极高。

**约束的代价与限制**

Constrained Decoding 并非零成本：

1. **计算开销**：每个解码步骤都需要查询自动机，确定合法 Token 集。对于复杂 Schema（深层嵌套、大量可选字段），这个查询的复杂度可能不可忽略。实测表明，使用 `effort: "max"` 的复杂 Schema 可能导致每个 Token 的生成延迟增加 20-50%。

2. **质量影响**：限制 Token 候选集会改变模型的采样分布。对于某些创造性的输出任务（如文案撰写），Constrained Decoding 可能导致输出"生硬"或"不自然"。这不是 API 的问题，而是约束本身的固有特性——你不可能既严格限制搜索空间，又保留完全的创造性。

3. **Schema 复杂度限制**：过于复杂的 Schema（深层嵌套、大量 `enum` 值、递归结构）可能导致自动机状态爆炸，超出 API 的处理能力。如果你发现 API 返回 Schema 验证错误或超时，降低 Schema 复杂度（减少嵌套层级、合并可选字段）通常是有效的解决方案。

4. **温度参数的相互作用**：当 `temperature` 设置较高时，模型有更强的倾向探索"不太可能但合法"的 Token 路径，这在与 Logit Masking 结合时可能导致模型反复选择相似的合法 Token 序列，产生重复内容。建议在 Structured Outputs 场景下使用较低的 `temperature`（0.0-0.3）。

### 4.2.2 从 Logit Masking 到工程实践：关键推论

理解 Logit Masking 的数学原理后，以下是几个直接指导工程实践的关键推论：

**推论一：JSON 字符串值的内容不受 Schema 约束**

这是最容易被误解的一点。Schema 的 `"type": "string"` 只保证输出的字段值是一个合法的 JSON 字符串——即被双引号包裹、内部转义正确。Schema **不约束**字符串的语义内容。

例如，对于 `{"name": {"type": "string"}}`，模型可以输出 `"name": "张三"`，也可以输出 `"name": "根据上下文无法确定人物姓名"`。两者在 JSON Schema 层面都是合法的字符串。

因此，在你的应用层代码中始终对字符串字段进行业务验证，不能假设 Schema 能保证内容的业务正确性。

**推论二：Logit Masking 在不同 Tokenizer 下的行为差异**

不同模型使用不同的 BPE Tokenizer。一个对模型 A 来说是单 Token 的字符串（如 `"name"`），对模型 B 可能被拆分为 `"` + `name` + `"` 三个 Token。这会影响 Constrained Decoding 的效率——单 Token 匹配比多 Token 匹配更快、更可靠。

这是一个重要的实践考量：如果你发现某个 Schema 在特定模型上表现不佳（频繁截断、输出质量差），可能是 Tokenizer 差异导致的。尝试调整 Schema 的字段名长度或嵌套结构，使其与目标模型的 Tokenizer 模式更匹配。

**推论三：概率分布重归一化的"赢家通吃"效应**

当 Logit Masking 移除了大量候选 Token 后，剩余 Token 的相对概率被放大。这可能导致模型的输出偏向"最安全的选项"——例如在使用 `enum` 时，模型可能过度选择 enum 列表的第一个值。

缓解策略：在 Prompt 中明确要求模型"仔细考虑所有可能的选项"，并避免在 `enum` 中将高频选项放在列表开头。

**推论四：自动机状态爆炸的实际影响**

对于包含 N 个可选字段（不在 `required` 中）的 Schema，自动机在最坏情况下需要追踪 \( 2^N \) 种可能的字段组合状态。当 N 超过 10-15 时，即使在 `effort: "max"` 下，API 也可能因编译超时而拒绝 Schema。

这是 Anthropic 不支持 `anyOf`/`oneOf`/`allOf` 的根本原因——这些组合关键字同样会导致状态空间的组合爆炸。如果你的应用确实需要多态输出（例如，根据输入类型返回不同的对象形状），推荐的解决方案是：
1. 使用 `enum` 字段作为类型判别器（discriminator）。
2. 在应用层根据判别器字段的值进行进一步的解析。
3. 或者，将复杂任务拆分为多个 API 调用，每个调用使用不同的 Schema。

### 4.2.3 JSON Schema 约束语法

Anthropic Structured Outputs 支持的 JSON Schema 是 JSON Schema Draft 2020-12 的一个**子集**。不是所有 JSON Schema 特性都被支持——这是由 Constrained Decoding 的底层实现决定的。

**支持的类型和关键字**

| 类别 | 支持的关键字 | 说明 |
|------|------------|------|
| 类型定义 | `type` | 必须为 `"object"`（顶层）、`"string"`、`"integer"`、`"number"`、`"boolean"`、`"array"`、`"null"` |
| 字符串约束 | `enum`、`minLength`、`maxLength`、`pattern` | `pattern` 支持 ECMAScript 正则 |
| 数字约束 | `multipleOf`、`minimum`、`maximum`、`exclusiveMinimum`、`exclusiveMaximum` | 仅对 `integer` 和 `number` 有效 |
| 数组约束 | `items`、`minItems`、`maxItems`、`uniqueItems` | `items` 仅支持单 Schema（不支持 tuple validation） |
| 对象约束 | `properties`、`required`、`additionalProperties` | `additionalProperties` 默认为 `true` |
| 组合 | `enum`（顶层对象） | 不支持 `anyOf`、`oneOf`、`allOf`、`not` |
| 引用 | 不支持 | `$ref`、`$defs`、`definitions` 均不可用 |
| 条件 | 不支持 | `if`/`then`/`else` 不可用 |

**关键限制**

1. **顶层类型必须为 `"object"`**：你不能使用 `{"type": "array"}` 作为顶层 Schema。如果需要输出数组，将其包装在对象属性中。

2. **不支持 `$ref` 和 `definitions`**：所有 Schema 必须完全内联。这意味着大型、复杂的 Schema 必须在客户端展开所有引用。这不是技术限制，而是为了确保自动机编译的确定性。

3. **不支持 `anyOf`/`oneOf`/`allOf`**：这些组合关键字会引入不确定性和状态分支，在 Constrained Decoding 中处理代价极高。对于需要多态输出的场景，考虑使用 `enum` 加条件解析，或者使用多个 API 调用分别处理不同情况。

4. **`additionalProperties` 默认为 `true`**：与严格的 JSON Schema 验证器不同，Anthropic 的实现默认允许额外属性。如果你需要严格的属性集，必须显式设置 `"additionalProperties": false`。

5. **正则表达式限制**：`pattern` 关键字使用的是受限制的正则子集（ECMAScript 语法），不支持回溯和 lookahead/lookbehind。

**Schema 示例**

一个典型的数据提取 Schema：

```json
{
  "type": "object",
  "properties": {
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "实体名称"
          },
          "type": {
            "type": "string",
            "enum": ["PERSON", "ORG", "LOCATION", "DATE", "MONEY"]
          },
          "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0
          }
        },
        "required": ["name", "type", "confidence"],
        "additionalProperties": false
      },
      "minItems": 1
    },
    "total_count": {
      "type": "integer",
      "minimum": 0
    }
  },
  "required": ["entities", "total_count"],
  "additionalProperties": false
}
```

### 4.2.4 Structured Outputs 与 Tool Use 的对比

Structured Outputs 和 Tool Use 都可以让 Claude 输出结构化的 JSON。选择哪个取决于你的具体需求。理解两者的区别有助于在设计阶段做出正确的架构决策。

| 维度 | Structured Outputs | Tool Use |
|------|-------------------|----------|
| **输出保证** | 输出在生成层面受 Schema 约束，数学上保证合法 | 输出是"尽力而为"的——Claude 被训练为生成合法 JSON，但不保证 |
| **Schema 复杂度** | 受限于 Constrained Decoding 自动机的表达能力 | 支持更复杂的嵌套和条件 Schema |
| **流式支持** | 仅支持非流式（`stream: false`） | 支持流式增量输出 |
| **交互模式** | 一次性输出：提供 Schema，获得结构化对象 | 对话式：模型输出 `tool_use`，你的代码执行工具，返回 `tool_result` |
| **Token 效率** | 输出仅包含 JSON 数据（无 `tool_use` 包装） | 输出包含 `tool_use` Content Block 的元数据（`id`、`name` 等） |
| **模型适配** | 需要模型原生支持（Claude 3.5 Sonnet 及以上） | 所有 Claude 3+ 模型均支持 |
| **适用场景** | 数据提取、API 返回值、单次结构化生成 | Agent 工作流、函数调用、需要外部系统交互的场景 |
| **Thinking 兼容** | 可以与 Extended Thinking 结合使用 | 同样支持 Extended Thinking |

**选择决策树**

```
需要一个结构化 JSON 输出？
├── 是 ──→ 需要与外部系统交互（API 调用、数据库查询）？
│           ├── 是 ──→ 使用 Tool Use
│           └── 否 ──→ 需要严格的 Schema 保证（不是"尽力而为"）？
│                      ├── 是 ──→ 使用 Structured Outputs
│                      └── 否 ──→ Tool Use 也够用，且支持流式
└── 否 ──→ 使用标准 Messages API
```

**混合使用的场景**

在实际项目中，Structured Outputs 和 Tool Use 常常结合使用：

1. 使用 Tool Use 让 Claude 决定"何时"需要获取数据（如天气、股价）。
2. 工具执行完成后，使用 Structured Outputs 将工具结果和对话上下文转换为结构化的最终回答。

这种模式在 Agent 架构中特别常见："与外部世界交互"用 Tool Use，"生成最终 API 响应"用 Structured Outputs。

### 4.2.5 `output_config` 参数协议规范

Structured Outputs 通过 `output_config` 顶层参数启用。相比旧文档中出现的 `response_format` 参数，`output_config` 是当前 API 的规范参数，提供了更丰富的配置能力。

**参数结构表**

| 参数路径 | 类型 | 必填 | 描述 |
|---------|------|------|------|
| `output_config` | `object` | 否 | 输出配置的顶层容器 |
| `output_config.format` | `object` | 是（当 `output_config` 存在时） | 输出格式描述 |
| `output_config.format.type` | `string` | 是 | 固定为 `"json_schema"` |
| `output_config.format.schema` | `object` | 是 | JSON Schema 对象（Draft 2020-12 子集） |
| `output_config.effort` | `string` | 否 | 约束执行的效力等级 |

**`effort` 参数详解**

`effort` 控制模型在遵循 Schema 约束上的"努力程度"，本质上是约束精度与输出质量之间的权衡：

| 等级 | 约束精度 | Token 消耗 | 适用场景 |
|------|---------|-----------|---------|
| `low` | 基础约束 | 最低 | 简单 Schema、高吞吐场景 |
| `medium` | 平衡（默认） | 适中 | 大多数场景的推荐值 |
| `high` | 严格约束 | 较高 | 复杂嵌套结构、要求严格的业务逻辑 |
| `xhigh` | 非常严格 | 高 | 关键任务、合规要求高的输出 |
| `max` | 最大约束 | 最高 | 容错率极低的生产关键路径 |

**重要**：即使 `effort` 设为 `max`，如果生成被 `max_tokens` 截断，输出仍可能不完整。始终为结构化输出分配足够的 `max_tokens` 预算。

**完整请求示例**

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 4096,
  "system": "你是一个数据提取助手。严格按照给定的 JSON Schema 返回数据。",
  "messages": [
    {
      "role": "user",
      "content": "张三，35岁，邮箱 zhangsan@example.com，住在北京市朝阳区。"
    }
  ],
  "output_config": {
    "format": {
      "type": "json_schema",
      "schema": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "age": {"type": "integer"},
          "email": {"type": "string"},
          "address": {
            "type": "object",
            "properties": {
              "city": {"type": "string"},
              "district": {"type": "string"}
            },
            "required": ["city", "district"]
          }
        },
        "required": ["name", "age"]
      }
    },
    "effort": "high"
  }
}
```

**响应格式**

成功响应与标准 Messages API 响应格式一致，区别仅在于 `content[0].text` 的内容是符合 Schema 的 JSON 字符串。响应中**不会**有额外的字段（如 `parsed_output`）——这是 SDK 层（如 `messages.parse()`）添加的便利性封装，不是 HTTP 协议的一部分。

```json
{
  "id": "msg_01Xxxxxxxxxxxxx",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "{\"name\":\"张三\",\"age\":35,\"email\":\"zhangsan@example.com\",\"address\":{\"city\":\"北京\",\"district\":\"朝阳区\"}}"
    }
  ],
  "model": "claude-sonnet-4-20250514",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": 150, "output_tokens": 80}
}
```

注意 `content[0].text` 是原始的 JSON 字符串——你需要自行调用 `json.loads()` 或 `JSON.parse()` 解析。

### 4.2.6 确定合理的 `max_tokens` 预算

结构化输出的 `max_tokens` 设置与自由文本场景有根本的不同。在自由文本中，`max_tokens` 是一个宽松的上限。在结构化输出中，如果 Token 预算不足导致输出被截断，整个 JSON 对象会变得不可解析——这是灾难性的失败模式。

**经验公式**

对于结构化输出，推荐使用以下经验公式估算 `max_tokens`：

```
max_tokens = base_overhead + (estimated_output_chars / avg_chars_per_token) * safety_factor
```

其中：
- `base_overhead`：JSON 结构本身的语法开销（花括号、引号、逗号、字段名）。对于简单 Schema，预留 20-30 Token；对于复杂嵌套 Schema，预留 50-100 Token。
- `estimated_output_chars`：你预期模型输出的 JSON 字符串的字符总数。可以从 Schema 的 `description` 和 Prompt 中的预期推断。
- `avg_chars_per_token`：英语约 4 字符/Token，中文约 1.5-2 字符/Token，数字约 1 字符/Token。
- `safety_factor`：安全系数。对于确定性的结构化输出，使用 2.0-3.0。这个系数留出了模型可能输出额外的可选字段或更详细的描述的余地。

**实例计算**

假设你期望模型输出一个包含 3 个实体的 JSON 对象，每个实体有 4 个字段（中文字段值合计约 100 个中文字符）：

```
estimated_output_chars = 150 (100 中文字 + 50 JSON 标点/结构)
max_tokens = 50 + (150 / 1.5) * 2.5
           = 50 + 100 * 2.5
           = 300
```

对于包含 20 个实体的更复杂输出：

```
estimated_output_chars = 700
max_tokens = 80 + (700 / 1.5) * 3.0
           = 80 + 467 * 3.0
           ≈ 1480
```

**实践建议**

1. 在开发阶段使用较大的 `max_tokens`（如 4096），观察实际输出大小。
2. 在监控中跟踪实际 `usage.output_tokens` 的分布。
3. 将生产环境的 `max_tokens` 设置为 P99 输出大小的 1.5-2 倍。
4. 对于 Schema 中包含开放式数组（没有 `maxItems`）的场景，始终设置 `max_tokens` 同时作为 `maxItems` 的补充约束——Token 限制可以防止数组无限制增长。

### 4.2.7 协议层对比：`output_config` vs 旧版 `response_format`

如果你查阅较早的 Anthropic API 文档或博客文章，可能会看到 `response_format` 参数。以下是两个参数的对比：

| 维度 | `output_config`（当前） | `response_format`（旧版/特定上下文） |
|------|------------------------|-----------------------------------|
| **状态** | 当前生产 API 的规范参数 | 已文档化的旧参数，部分代理/网关仍在使用 |
| **结构** | `{"format": {"type": "json_schema", "schema": ...}}` | `{"type": "json_schema", "json_schema": {"name": "...", "schema": ...}}` |
| **effort 支持** | 支持 | 不支持 |
| **Schema 命名** | Schema 不需要 `name` 字段 | Schema 需要 `name` 字段 |
| **官方推荐** | 推荐使用 | 逐步弃用中 |

如果你从使用 `response_format` 的旧代码迁移，主要变化是：

1. 将 `response_format` 替换为 `output_config.format`。
2. 移除 Schema 的 `name` 字段（如果不需要）。
3. 根据需求添加 `effort` 参数。

### 4.2.8 典型应用场景

**场景一：非结构化文本的实体提取**

从客户邮件、法律合同、医疗记录中提取结构化实体。传统方法需要训练 NER 模型（需要标注数据、模型训练、部署维护的完整链条）或手写正则表达式（需要领域专家逐模式编写、脆弱且难以维护）。

使用 Structured Outputs 的优势在于：
- **零标注数据**：只需要一个 JSON Schema 和一个描述性的 Prompt。
- **上下文理解**：Claude 可以利用上下文消歧——区分"苹果公司"和"苹果水果"，这是传统 NER 模型难以做到的。
- **灵活 Schema**：添加新的实体类型只需修改 Schema，不需要重新训练模型。

在实际项目中，建议将 Claude 的提取结果与确定性规则结合：Claude 负责理解和消歧，确定性规则负责时间解析、数字格式标准化等精确计算。

**场景二：多 Agent 系统的信息传递**

在多 Agent 架构中，上游 Agent 的分析结果需要被下游 Agent 可靠地消费。这是 Agent 系统中最常见的失败点——Agent A 输出了一段包含推理过程、总结和数据的混合文本，Agent B 需要从中提取自己关心的信息。

使用 Structured Outputs 作为 Agent 间的合约（contract）：
1. 每个 Agent 的"输出接口"由一个 JSON Schema 定义。
2. Agent A 使用 Structured Outputs 将其分析结果输出为结构化数据。
3. Agent B 在 Prompt 中接收结构化的上游数据，而非自由文本。
4. 系统编排器可以验证每一步的 Schema 合规性。

这种模式显著降低了多 Agent 系统的调试难度——当某个 Agent 的输出导致下游问题时，你可以精确地知道是哪个字段、哪个值导致了问题，而不需要在自由文本中大海捞针。

**场景三：作为微服务的 AI 推理层**

将 Claude 包装为内部微服务，为其他服务提供自然语言理解能力。例如：
- 内部搜索服务的 Query Understanding 模块。
- 客服工单系统的意图分类和字段填充。
- 内容审核管道的结构化告警输出。

在这种模式下，JSON Schema 就是你的"API 契约"。下游服务通过 Schema 定义预期的响应格式，如同调用任何其他结构化 API。核心优势在于下游服务开发者不需要理解 LLM 或 Prompt Engineering——他们只需要定义 Schema，由 AI 平台团队维护 Prompt 和模型选择。

**场景四：文档解析与分类**

从 PDF、扫描件中提取结构化信息。结合 Claude 的视觉能力（multimodal），可以直接从文档图像中提取表格、表单数据，并以结构化 JSON 输出。

对于发票、收据、合同等标准化文档，你可以定义高度精确的 Schema（具体到每个字段的类型和约束），实现接近 OCR+结构化解析的精度，同时保持了 LLM 的语义理解能力（处理格式变化、手写注释等）。

**场景五：代码生成（结构化版本）**

生成符合特定接口的代码片段或配置文件。Schema 可以描述目标代码的结构（类名、方法签名、参数类型），Claude 的生成被保证符合这个结构。这在以下场景中特别有用：
- CI/CD 管道中自动生成 Terraform/Pulumi 配置。
- 从 OpenAPI 规范生成 API 客户端的框架。
- 生成符合公司模板的项目结构文件。

**场景六：结构化推理链（Chain-of-Thought with Structure）**

这是一个进阶模式：让模型在内部进行推理，但将推理结果输出为结构化格式。例如，对于一个复杂的分析任务，你可以设计以下 Schema：

```json
{
  "type": "object",
  "properties": {
    "premises": {
      "type": "array",
      "items": {"type": "string"},
      "description": "从输入中识别的关键前提"
    },
    "reasoning_steps": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "step": {"type": "integer"},
          "thought": {"type": "string"},
          "conclusion": {"type": "string"}
        },
        "required": ["step", "thought", "conclusion"]
      }
    },
    "final_answer": {"type": "string"}
  },
  "required": ["premises", "reasoning_steps", "final_answer"]
}
```

这让你在获得结构化推理链的同时，也能程序化地验证推理的每个步骤。

---

## 4.3 Python 实现

本节实现的完整代码文件位于 `code/python/ch04/structured_output.py` 和 `code/python/ch04/test_structured_output.py`。

### 设计决策

1. **无 SDK 依赖**：`StructuredOutputClient` 直接构建 `output_config` 参数并通过 HTTP 层发送，不依赖 Anthropic 官方 SDK 的 `messages.parse()` 方法。这让你理解协议层的每个细节。

2. **组合而非继承**：`StructuredOutputClient` 通过构造函数接收 Ch01 的 `AnthropicClient` 实例（或任何实现 `post(**kwargs) -> dict` 接口的对象）。这种设计遵循"组合优于继承"原则，也让测试变得更加简单。

3. **两阶段 JSON 解析**：`_parse_json_response()` 函数处理模型可能不完美遵循约束的情况——它尝试纯 JSON 解析、markdown fence 提取和括号定位三种策略，确保在模型偶尔添加外围文本时仍能正确提取数据。

4. **`create()` vs `extract()` 的分工**：
   - `create()` 是低层 API，直接映射到 `output_config` 协议参数，给予完全的控制权。
   - `extract()` 是高层便利方法，自动构建提取 Prompt 并解析响应中的 JSON，适合数据提取场景。

### 代码结构

```python
class StructuredOutputClient:
    def __init__(self, client): ...        # 注入兼容的客户端
    def create(...) -> dict: ...            # 协议层：output_config
    def extract(...) -> dict: ...           # 便利层：自动构建提取 Prompt
```

---

## 4.4 Node.js 实现

本节实现的完整代码文件位于 `code/node/ch04/StructuredOutputClient.ts` 和 `code/node/ch04/structured_output.test.ts`。

Node.js 实现与 Python 版本在功能上完全等价。使用的是严格的 TypeScript，接口定义明确，不使用 `any`。

### 设计决策

1. **`ClientLike` 接口**：定义了底层客户端需要满足的最小契约 (`post(params) -> Promise<object>`)，使 `StructuredOutputClient` 可以包装任何兼容的 HTTP 客户端，不限于 Ch01 的 `AnthropicClient`。

2. **结构化参数类型**：`CreateParams` 和 `ExtractParams` 接口提供了强类型的参数验证，避免运行时因拼写错误导致的协议错误。

3. **与 Python 版保持一致的 JSON 解析**：`parseJsonResponse()` 实现了与 Python `_parse_json_response()` 相同的三级回退策略。

---

## 4.5 最佳实践

### 4.5.1 Schema 设计模式

**模式一：使用 `description` 引导模型**

JSON Schema 的 `description` 关键字不仅用于文档，在 Structured Outputs 中也作为模型的"字段级提示"：

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["approve", "reject", "escalate"],
      "description": "审批决定：approve=批准, reject=拒绝, escalate=升级到上级"
    }
  }
}
```

与 Prompt 中的描述相比，Schema 中的 `description` 直接作用于字段级约束上下文，通常能获得更准确的枚举值选择。

**模式二：用 `additionalProperties: false` 防止幻觉字段**

在没有显式设置的情况下，API 默认允许模型输出 Schema 中未定义的属性。对于严格要求输出结构的场景，始终在顶层对象和嵌套对象上设置 `"additionalProperties": false`。

**模式三：避免过深的嵌套**

每增加一层嵌套，自动机的状态空间就呈指数增长。实测表明：
- 2-3 层嵌套：几乎无性能影响。
- 4-5 层嵌套：可能需要更高的 `effort` 级别。
- 6+ 层嵌套：可能出现 Schema 编译超时。

如果需要深层嵌套，考虑：
- 将嵌套结构展平为扁平属性（使用命名约定如 `address_city`、`address_district`）。
- 拆分为多次 API 调用，分别获取不同层级的数据。

**模式四：为数组设置合理的 `minItems`/`maxItems`**

未设限制的数组可能导致模型输出过长或过短的结果。`minItems` 和 `maxItems` 不仅约束输出长度，也帮助模型理解期望的输出规模。

**模式五：使用 `enum` 而非 String + Prompt 描述分类**

当字段只有固定的几种可能值时，`enum` 比在 Prompt 中描述"请选择以下选项之一：A/B/C"更可靠。`enum` 约束作用于 Token 级别，模型无法生成不在枚举中的值。

### 4.5.2 约束边界：什么 Structured Outputs 做不到

理解 Structured Outputs 的能力边界同样重要：

1. **不能保证业务正确性**：Schema 只能保证输出是合法的 JSON 结构，不能保证数据在业务上是正确的。`"age": -5` 符合 `{"type": "integer"}` 的 Schema，但年龄不可能是负数。

2. **不能替代领域验证**：Schema 定义结构，你仍然需要业务逻辑验证层来检查数据合理性。把 Schema 看作第一道防线（格式），领域验证是第二道防线（语义）。

3. **Schema 无法约束字符串内容语义**：你可以通过 `pattern` 限制邮箱格式，但无法约束"提取正确的邮箱"——如果原文中没有邮箱，模型可能编造。

4. **截断风险始终存在**：如果 `max_tokens` 不够，输出会在任意位置截断，导致 JSON 不完整。经验法则：为结构化输出分配 Prompt 中描述的预期输出大小的 2-3 倍 Token。

### 4.5.3 Schema 设计反模式

了解不应该做什么，与了解最佳实践同样重要。

**反模式一：Schema 过度精确**

```json
// 反模式：对自由文本字段使用过严的 pattern 约束
{
  "customer_feedback": {
    "type": "string",
    "pattern": "^[A-Za-z0-9 .,!?']{10,500}$"
  }
}
```

问题在于 `pattern` 约束限制了模型的"表达空间"。如果客户反馈中包含换行符、特殊字符或多语言内容，输出可能被截断或模型因找不到合法 Token 而陷入循环。

**正确做法**：对自由文本字段使用宽松的类型约束（`"type": "string"`），在应用层验证内容质量。

**反模式二：将所有字段都设为 required**

```json
// 反模式：required 中的字段在输入中没有对应的信息
{
  "required": ["name", "age", "email", "phone", "address", "company", "title"]
}
```

如果输入文本中只包含姓名和年龄，模型对于 `phone` 和 `company` 这样的必填字段只有两个选择：(1) 编造数据，或 (2) 使用空字符串。两者都不是理想行为。

**正确做法**：`required` 应该只包含输入中保证能找到的信息的字段。可能不存在的信息应设为可选字段，并在 Prompt 中指示"如果信息不存在，省略该字段"。

**反模式三：用 Schema 替代 Prompt**

有些开发者倾向于把业务逻辑全部编码到 Schema 中（如通过 `enum` 和 `description` 描述复杂的选择规则），而忽略了 Prompt 的作用。Schema 是**格式约束**，Prompt 是**内容指南**。两者各司其职：

- Schema 负责："age 字段必须是一个整数"。
- Prompt 负责："年龄应从文本中提取。如果文本中提到'大约30岁'，提取 30。如果提到'三十多岁'，提取 35。如果无法确定年龄，不要编造。"

### 4.5.4 成本效益分析

使用 Structured Outputs 的 Token 经济：

| 因素 | 影响 | 优化建议 |
|------|------|---------|
| `effort` 等级 | 更高的 effort 消耗更多推理资源，但不增加 Token 计数 | 从 `medium` 开始，仅在必要时提升 |
| Schema 复杂度 | 复杂 Schema 增加输入 Token（Schema 计入 input tokens） | 精简 Schema，移除不必要的嵌套和 description |
| 输出长度 | Structured Outputs 倾向于生成最小化的 JSON（无空格美化） | 不需要额外的 `minify` 步骤 |
| 失败重试 | 如果 Schema 不被满足，需要重新调用（消耗额外的 Token） | 设置合理的 `effort` 减少重试概率 |
| 与 Tool Use 对比 | Structured Outputs 不需要 `tool_use` 包装，通常比等效的 Tool Use 调用节省 10-20% Token | 非交互式场景优先使用 Structured Outputs |

**实际成本计算示例**

```
输入 Token（包括 Schema + Prompt）:  ~500 tokens
输出 Token（结构化 JSON）:          ~200 tokens
模型:                               Claude Sonnet 4
单次调用成本（$3/$15 per MTok）:    500*3/1M + 200*15/1M = $0.0015 + $0.003 = $0.0045

对比：Prompt-based JSON（需要3次重试才获得合法输出）:
  (500*3/1M + 200*3/1M) * 3 = $0.0135

Structured Outputs 节省约 67% 的 Token 成本，同时提供更强的可靠性保证。
```

### 4.5.5 生产环境 Schema 维护策略

在生产环境中，Schema 不是一次编写就永远不变的。业务需求演化时，Schema 也必须随之更新。以下是经过验证的维护策略：

**向后兼容的 Schema 演进**

当你的 API 消费者依赖某个 Schema 时，修改 Schema 必须向后兼容。以下修改是安全的：

- 添加新的可选字段（不在 `required` 中的新 `property`）。
- 放宽约束（移除 `pattern`、增加 `maxItems`、减小 `minimum`）。
- 添加新的 `enum` 值。

以下修改是破坏性的，需要版本化：

- 添加新的 `required` 字段。
- 收紧约束（减小 `maxItems`、增加 `minimum`）。
- 移除或重命名已有字段。
- 修改已有 `enum` 的值（移除 enum 选项）。

**Schema 版本化策略**

对于有多个消费者的 Schema，推荐使用"渐进式版本化"：

```python
# Schema 版本化示例
SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": ["1.0"]},
        "name": {"type": "string"},
        "age": {"type": "integer"}
    },
    "required": ["schema_version", "name"]
}

SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": ["2.0"]},
        "name": {"type": "string"},
        "age": {"type": "integer"},
        "email": {"type": "string"}  # V2 新增字段
    },
    "required": ["schema_version", "name", "email"]
}
```

在 Prompt 中包含 `schema_version` 字段让消费者能够区分版本，并在过渡期同时支持多个版本。

### 4.5.6 监控与可观测性

在生产环境中使用 Structured Outputs，以下指标值得持续监控：

1. **Schema 合规率**：`extract()` 调用成功解析 JSON 的比例。如果低于 99.5%，需要检查 Schema 设计或 `effort` 设置。

2. **截断率**：`stop_reason == "max_tokens"` 的比例。如果超过 1%，说明 `max_tokens` 设置不足以覆盖大多数情况，需要增加预算或减少 Schema 复杂度。

3. **输出长度分布**：JSON 输出的 Token 长度分布。异常值（过长或过短）可能表明模型在某些输入上出现了异常行为。

4. **延迟分布**：Structured Outputs 调用的 P50/P95/P99 延迟。突然的延迟增加可能表明 Schema 复杂度或模型负载问题。

```python
# 简单的结构化输出监控装饰器
import time
import functools

def monitor_structured_output(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.monotonic()
        try:
            result = func(*args, **kwargs)
            elapsed = time.monotonic() - start
            # 记录成功指标
            return result
        except Exception as e:
            elapsed = time.monotonic() - start
            # 记录失败指标
            raise
    return wrapper
```

### 4.5.7 错误处理策略

当使用 Structured Outputs 时，以下错误模式值得关注：

**模式一：Schema 验证失败（API 层）**

API 会在请求阶段验证 Schema 的合法性。如果 Schema 不符合支持的子集（如使用了 `$ref`），API 返回 400 错误。

```python
# 错误处理示例
try:
    response = client.create(
        model="claude-sonnet-4-20250514",
        messages=[...],
        json_schema=my_schema,
    )
except AnthropicError as e:
    if "schema" in str(e).lower():
        # Schema 结构问题：检查是否使用了不支持的关键字
        ...
    elif e.is_retryable:
        # 临时错误：按照第 1 章的重试策略处理
        ...
```

**模式二：输出被截断**

如果 `stop_reason == "max_tokens"`，解析响应中的 JSON 将失败。在 `extract()` 方法的返回值中总是检查数据的完整性：

```python
response = client.create(...)
if response.get("stop_reason") == "max_tokens":
    # 输出被截断，JSON 可能不完整
    # 策略：增加 max_tokens 后重试，或降低 Schema 复杂度
    ...
```

**模式三：模型输出不符合 Schema（罕见但可能）**

在极低 `effort` 等级或极其复杂的 Schema 下，模型输出可能仍不完全符合要求。这就是为什么我们的 `_parse_json_response()` 提供了三级回退——它能处理大多数"模型添加了额外文字"的情况。

---

## 4.6 自测题

### 问题 1（理论）

解释 Constrained Decoding 的 Logit Masking 机制。在自回归解码的每个步骤中，Logit Masking 如何确保输出符合 JSON Schema？为什么这种方法比"生成后验证"更高效？

### 问题 2（理论）

对比 Structured Outputs 和 Tool Use 在以下三个维度上的差异，并举例说明：
- 输出格式保证机制
- 交互模式（一次性 vs 对话式）
- Token 效率

在以下场景中，你会选择哪种方案？为什么？
- (a) 从客户邮件中提取订单号、日期和金额
- (b) 构建一个能查询数据库、发送邮件的 AI 助手
- (c) 将模型输出作为 RESTful API 的响应体

### 问题 3（编码）

不参考本章的示例代码，实现一个 `extract_entities` 函数，从一段文本中提取人物和地点信息。要求：

```python
# 预期接口
def extract_entities(
    client: Any,  # 任何实现 post(**kwargs) -> dict 的对象
    model: str,
    text: str,
) -> dict:
    """从 text 中提取人物（persons）和地点（locations）列表。

    Returns:
        {"persons": ["张三", "李四"], "locations": ["北京", "上海"]}
    """
    ...
```

提示：
- 使用 `output_config` 参数启用 Structured Outputs。
- 设计合适的 JSON Schema（包含 persons 和 locations 两个数组字段）。
- 注意处理模型可能在 JSON 外添加额外文字的情况。

### 问题 4（编码）

扩展本章的 `StructuredOutputClient`，为其添加一个 `bulk_extract` 方法，支持批量数据提取。要求：

```python
# 预期接口
def bulk_extract(
    self,
    model: str,
    texts: list[str],
    json_schema: dict,
    *,
    max_concurrency: int = 3,
) -> list[dict]:
    """对 texts 中的每段文本并发调用 extract()。

    返回一个与 texts 等长的列表，每个元素是对应文本的提取结果。
    """
    ...
```

提示：
- Python 实现可使用 `concurrent.futures.ThreadPoolExecutor` 实现并发。
- Node.js 实现可使用 `Promise.all()` 配合并发限制。
- 注意错误处理——某段文本提取失败不应中断整个批量操作。
- 考虑速率限制：`max_concurrency` 参数控制同时进行的请求数量。

---

## 本章小结

本章完成了 Structured Outputs 的协议层深度剖析：

1. **概念层**：理解了 Prompt-based JSON 的不可靠性，以及 Constrained Decoding 如何通过 Grammar Compilation + Logit Masking 在 Token 生成层面保证输出符合 Schema。

2. **协议层**：掌握了 `output_config` 参数的完整规范，包括 `format.type`、`format.schema` 和 `effort` 三个层级。学习了 JSON Schema 的受支持子集及其关键限制（无 `$ref`、无 `anyOf`/`oneOf`/`allOf`、顶层必须为 object）。

3. **对比层**：深入区分了 Structured Outputs 和 Tool Use 的适用场景——前者用于"需要严格格式保证的一次性结构生成"，后者用于"需要与外部系统交互的对话式工作流"。

4. **实现层**：构建了 Python 和 Node.js 双语言的 `StructuredOutputClient`，在不依赖官方 SDK 的情况下直接使用 `output_config` 参数，并实现了健壮的 JSON 解析（三级回退策略）。

5. **实践层**：学习了 Schema 设计的五个核心模式、约束边界认知、成本效益分析和错误处理策略。

第 5 章将在此基础上深入 Prompt Caching——如何在多次调用中复用上下文以降低延迟和成本。
