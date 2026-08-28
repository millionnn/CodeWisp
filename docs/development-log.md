# 开发日志

## V0.3

**日期：** 2026-08-28

### 目标

建立自主 Agent Loop：将 V0.1 的 LLM Client 与 V0.2 的 Tool System 连接为最小完整的 Agent Runtime。

### 已完成

- `AgentLoop.run(task)`：传 tools schema → 解析 tool_calls → ToolExecutor → Observation 回写 → 循环
- `AgentState` / `AgentStatus`：IDLE / RUNNING / COMPLETED / FAILED / MAX_STEPS
- 轻量 `AgentEvent`（无 Event Bus）
- Conversation 扩展：`tool` 角色与 assistant `tool_calls`
- `LLMClient.chat(..., tools=)`；`LLMResponse` / `ToolCall`（含 parse_error）
- CLI 改为调用 AgentLoop；可展示工具轨迹
- 仍仅内置 `calculator` / `get_current_time`（无 Coding Tools）

### 设计决策

1. **AgentLoop 不放在 CLI** — CLI 可被 Web UI 替换；编排逻辑必须可复用。
2. **ToolExecutor 不放进 LLMClient** — 保持 Model I/O 与本地执行分离，符合题目「自行实现循环与工具执行」。
3. **需要 max_steps** — 防止模型反复 tool_call 导致无限循环。
4. **ToolResult 必须写回 Conversation** — 否则模型看不到 observation，无法形成多步推理。
5. **工具失败作为 observation** — 让模型自行决定是否重试/改口，而不是进程崩溃。

### 测试结果

`pytest`：**66 passed**（含 V0.1 / V0.2 回归 + V0.3 新增）。

### 后续

**V0.4 — Coding Tools**：在现有 Tool 抽象上注册 read/write/shell 等，AgentLoop 无需重写。

---

## V0.2

**日期：** 2026-08-28

### 目标

建立清晰、可扩展、可测试的 Tool System，供未来 Agent Loop 调用；本版本**不**实现自动 Tool Calling。

### 已完成

- `Tool` / `ToolResult` / `ToolRegistry` / `ToolExecutor`
- 内置 `calculator`、`get_current_time`
- `python -m backend.app.tools` 人工验证入口
- 引入 `LLMResponse` 领域对象（为 V0.3 预留 tool_calls）

### 设计决策

1. Tool System 与 CLI / LLM 解耦
2. 失败返回 ToolResult，不拖垮上层
3. calculator 使用 AST 白名单求值
4. schema 对齐 OpenAI function calling 形态

---

## V0.1

**日期：** 2026-08-28

### 目标

最小可运行 LLM CLI + 对话历史。

### 设计决策

LLM 核心与 CLI 分离；仅用官方 `openai` SDK；追加式历史；可注入 mock。
