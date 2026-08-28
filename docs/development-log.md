# 开发日志

## V0.2

**日期：** 2026-08-28

### 目标

建立清晰、可扩展、可测试的 Tool System，供未来 Agent Loop 调用；本版本**不**实现自动 Tool Calling。

### 已完成

- `Tool` 抽象：`name` / `description` / `parameters`(JSON Schema) / `execute`
- 统一 `ToolResult`：`success` / `output` / `error` / `metadata`
- `ToolRegistry`：注册、查找、列举、防重复
- `ToolExecutor`：名称 + 参数 → 校验 → 执行 → 结构化结果（含 `duration_ms`）
- 内置工具：`calculator`（AST 安全求值，禁止危险 eval）、`get_current_time`
- 人工验证入口：`python -m backend.app.tools`（不经 LLM）
- 新增工具相关 pytest；V0.1 原有测试保持通过

### 设计决策

1. **Tool System 与 CLI / LLM 解耦** — 未来 Web API 与 Agent Runtime 可直接复用。
2. **失败返回 ToolResult，而不是拖垮进程** — 适配未来循环中的 Observation。
3. **人工验证用独立模块入口，而非塞进对话 CLI** — 避免污染产品交互，且不依赖 API Key。
4. **calculator 使用 AST 白名单求值** — 满足题目「工具本地执行」且避免任意代码执行。
5. **不修改 LLMClient 的自动调工具行为** — V0.2 不自动执行工具。另已引入 `LLMResponse` 领域对象，将 SDK 响应形状关在 Client 内，为 V0.3 预留 `tool_calls`。

### 为什么不提前实现 Agent Loop

Agent Loop 属于 V0.3：需要「模型输出解析 → 决定是否调工具 → 写回 observation → 终止条件」。
若在 V0.2 混入，会掩盖 Tool System 本身的边界，也不利于面试分模块讲解。

### 测试结果

`pytest`：**46 passed**（含 V0.1 原 18 项 + V0.2 新增）。

### 后续

**V0.3 — Agent Loop**：在 Runtime 中组合 `LLMClient` + `ToolExecutor`，实现自动 Tool Call 与 Observation 回写。

---

## V0.1

**日期：** 2026-08-28

### 目标

实现最小可运行的 CodeWisp：多轮 LLM 命令行对话，以及可复用的 LLM 客户端与基础对话历史。

### 已完成

- 项目骨架（`backend/app/...`）
- `Message` / `Conversation`（system / user / assistant）
- OpenAI 兼容的 `LLMClient`（从环境变量读取配置，默认对接 DeepSeek）
- CLI：横幅、提示符、多轮对话、退出与空输入处理
- 缺密钥、错误配置、网络与 API 失败等领域异常
- `.env.example`、`.gitignore`、依赖与 pytest
- `README.md`、`docs/architecture.md`、本日志

### 设计决策

1. **LLM 核心与 CLI 分离** — 便于后续 Web API 复用同一客户端。
2. **仅使用官方 `openai` SDK** — 通过 DeepSeek 的 OpenAI 兼容接口调用；不引入任何 Agent 框架。
3. **对话历史采用追加式列表** — 暂不做上下文窗口管理，便于面试解释。
4. **可注入 OpenAI 客户端与 CLI I/O** — 无真实密钥、无真实终端也能单测。
5. **LLM 调用失败时回滚本轮 user 消息** — 避免未得到回复的轮次污染历史。

### Python 版本

基于 **Python 3.11.9** 开发（`requires-python >= 3.11`）。
