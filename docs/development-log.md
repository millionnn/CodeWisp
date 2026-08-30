# 开发日志

## V0.6

**日期：** 2026-08-30

### 目标

Session、Conversation Persistence、Agent Run/Step 身份、SQLite、Backend API；CLI 与 API 共用 Agent Core。为 V0.7 Provider/Model 与 V0.9 Snapshot/Undo 预留稳定 ID 与模型身份字段。

### 已完成

- Domain 序列化 round-trip（Message / ToolCall / AgentRun / AgentStep / Session）
- SqliteStore + migration v1；Session / Conversation / AgentRun Repositories
- AgentService：Loop 外持久化；Session Resume；per-session 锁
- FastAPI：Session CRUD + GET/POST messages
- CLI：经 AgentService；`/sessions` `/use` `/history` 等；ASCII Banner
- 集成与 API 测试；文档更新
- **未做** Multi-Provider Runtime、Snapshot/Undo、Web UI、Context Compression

### 设计决策

1. **AgentLoop 不知 SQLite** — Persistence 在 AgentService 投影。
2. **Run 冗余 provider/model** — 审计「当时用的模型」，不绑可变 Session 配置。
3. **不建 snapshots 表** — 仅保证 `step_id` / `tool_call_id` 稳定唯一。
4. **CLI 与 API 同一条编排路径** — 禁止第二套 Agent Loop。

### 测试结果

`pytest`：**251 passed**（含 V0.1–V0.5 regression + V0.6）。

### 后续（需确认后再做）

V0.7 Provider / Model Registry；V0.8 Web UI / Trace；V0.9 Diff / Snapshot。

---

## V0.5

**日期：** 2026-08-30

### 目标

Self-Correction / Autonomous Repair：在有限预算内，让 Agent 依据 Observation 自主决定继续工具调用或结束，完成「发现 → 定位 → 修改 → 验证」闭环。

### 已完成

- 复用既有多轮 AgentLoop（不重写、无语言特判）
- `termination_reason`；`PERMISSION_REQUIRED` 硬停（不自动授权）
- 默认 `max_steps=15`；CLI `--max-steps`
- System prompt：Observation 驱动迭代 / 验证后停止 / 遇授权则停（不写死工具顺序）
- 集成测试：简单修复、需 search、多轮修复、预算耗尽、修复中 ASK
- 文档更新

### 设计决策

1. **Self-Correction = Loop 的自然能力** — 不是独立 Repair Engine。
2. **预算复用 max_steps** — 不另造 repair_iteration 计数器。
3. **ASK 框架硬停** — 安全优先于「让模型自己停」。
4. **无 pytest 专用解析器 / if exit_code 重试** — 保持语言无关。

### 测试结果

`pytest`：**192 passed**（含 V0.1–V0.4-C 回归 + V0.5）。

### 后续（需确认后再做）

Planning / 项目探测 / Context Compression / 交互式 Permission UI 等。

---

## V0.4-C

**日期：** 2026-08-30

### 目标

Language-Agnostic Controlled Command Execution：在 Workspace 内安全、受控地执行开发命令。

### 已完成

- `backend/app/execution/`：`ExecutionRequest` / `ExecutionResult` / `ExecutionService` / `CommandPolicy` / `PermissionRequired`
- 工具：`run_command`（Policy → Service → ToolResult）
- ALLOW / ASK / DENY；ASK 不启动 subprocess
- 安全：`shell=False`、cwd 边界、timeout、输出截断
- Agent 集成测试；文档更新
- **未做** Self-Correction / 交互式 Permission UI / 项目语言探测（已移交 V0.5）

### 设计决策

1. **Execution 与 Tool / Agent 分层** — Service 不依赖 AgentLoop。
2. **策略显式三态** — 为未来 Web 授权留 `permission_required` 接口。
3. **默认拒绝未知命令** — allowlist 常见开发工具，而非开放任意二进制。
4. **不做自动重试修复** — 失败作为 Observation，留给 V0.5。

### 测试结果

`pytest`：**186 passed**（V0.1–V0.4-B 回归 + V0.4-C Phase 2/3）。

### 后续（需确认后再做）

**V0.5 Self-Correction** —— 已在上方完成。

---

## V0.4-B

**日期：** 2026-08-29

### 目标

Safe Code Modification：让 Agent 能在 Workspace 内**精确、安全、可验证**地修改代码。

### 已完成

- `Workspace.write_text` / `replace_text`：共享原子写入（临时文件 + `os.replace`）
- 工具：`edit_file`（`path` / `old_text` / `new_text` / `expected_replacements`）、`write_file`（`path` / `content` / `overwrite`，默认 false）
- 确定性编辑：匹配次数必须等于预期，否则结构化失败、不落盘
- 缺失父目录：写入时自动创建（边界仍经 `resolve_path`）
- 注册进默认 Registry；AgentLoop 无工具特判
- 测试：Workspace 写入、Tool、Agent 集成（read → edit → read 验证；write → read）

### 设计决策

1. **禁止整文件重生成作为默认编辑** — `edit_file` 只做精确子串替换。
2. **不猜测** — `actual != expected_replacements` 一律失败。
3. **写入统一走 Workspace** — Tool 不直接 `open()`。
4. **默认不覆盖** — `write_file` 的 `overwrite=false`，降低误删风险。
5. **不做 Shell / git / self-correction** — 严格停在 V0.4-B。

### 测试结果

`pytest`：**137 passed**（含 V0.1–V0.4-A 回归 + V0.4-B）。

### 后续（需确认后再做）

**V0.4-C**：受控命令执行 —— 已在上方完成。

---

## V0.4-A

**日期：** 2026-08-29

### 目标

引入 Workspace 与只读 Coding Tools，让 Agent 第一次能理解真实代码仓库。

### 已完成

- `Workspace`：`root` / `resolve_path` / `list` / `glob` / `read` / `search`
- 工具：`list_files`、`glob`、`read_file`、`search_code`（构造函数注入 Workspace）
- 路径边界：`resolve()` + `relative_to`，拒绝穿越
- 注册进默认 Registry；AgentLoop 无特判
- 临时目录单测 + Agent 集成测试（glob → read_file → final answer）

### 设计决策

1. **Coding Tools 不各自做路径逻辑** — 统一走 Workspace，避免边界漏洞不一致。
2. **不默认整库递归 list** — `max_depth` 默认 1，降低噪声与成本。
3. **glob 与 search_code 分离** — 找文件 vs 找内容。
4. **不做写入/Shell** — 严格停在 V0.4-A。
6. **System prompt 与工具解耦** — Agent 只保留角色与全局约束；具体何时用哪个工具写在各 Tool 的 description / schema 中，由 `list_schemas()` 交给模型。
7. **Workspace = 目标仓库** — 通过 `resolve_workspace_root()` 挂点解析（`--workspace` / `CODEWISP_WORKSPACE` / cwd），与 CodeWisp 源码目录解耦，便于日后 Web Session 注入。

### 测试结果

`pytest`：**105 passed**（含 V0.1–V0.3 回归 + V0.4-A）。

### 后续（需确认后再做）

**V0.4-B**：写入类工具（edit/write 等）——已在上方完成。

---

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
