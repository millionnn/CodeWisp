# 开发日志

## V1.3 MCP Tool Integration

**日期：** 2026-09-01

### 目标

让 CodeWisp 通过 MCP 动态发现、注册并调用外部工具，同时保持 AgentLoop / Permission / Context / Git / LSP / Snapshot 架构不被破坏。

### 已完成

- `backend/app/mcp/`：models / errors / config / transport / client / manager / adapter / policy / registry / context / service / demo_server
- ToolRegistry：`unregister` / `register_or_replace`；MCP 工具 ID：`mcp.<server>.<tool>`
- Permission：read ALLOW / write ASK / dangerous DENY；复用 PermissionHandler
- Context：`MCPContextProvider`（metadata-first）
- AgentService：run 前 sync MCP tools；失败不阻断 Agent
- CLI：`/mcp servers|tools|connect|disconnect|reload`
- API：`/api/sessions/{id}/mcp/*` 与 `/api/mcp/*`（需 `session_id`）
- Demo：`codewisp-demo-mcp`（stdio，离线）
- 测试：config/policy/client/adapter/agent/api；stdio demo roundtrip

### 设计决策

1. AgentLoop 无 `if mcp_` 特判；MCP 最终表现为普通 Tool
2. 配置在文件系统，不在 SQLite 存 secret
3. 自研最小 stdio JSON-RPC 客户端（与 LSP 风格一致）；不依赖 MCP SDK 版本抖动
4. Resource / Prompt / OAuth / 全 transport → Future

详见 [v1.3-mcp-report.md](./v1.3-mcp-report.md)

---

## V1.2 LSP-Aware Coding Intelligence

**日期：** 2026-09-01

### 目标

让 Agent 具备代码语义感知（diagnostics / symbols / definition / references / hover），
在不改 AgentLoop 编排语义的前提下，用 LSP Observation 增强 Self-Correction。

### 已完成

- `backend/app/lsp/`：Detector / Client Protocol / Manager / Service / Policy / Context
- Adapters：Fake（测试）/ PyrightCli（真实 diagnostics）/ Unavailable（降级）
- Tools：`lsp_diagnostics` / `lsp_definition` / `lsp_references` / `lsp_symbols` / `lsp_hover`
- ContextManager：LSP metadata 注入；edit 后 refresh
- AgentService + API：`/api/sessions/{id}/lsp/*`
- CLI：`/lsp status|diagnostics|symbols|definition|references|hover`
- 测试：8 模块 29 cases；全量 **495 passed**

### 设计决策

1. AgentLoop 不含 LSP 特判；不硬编码 edit→diagnostics 循环
2. LSP 只读 ALLOW；不可用时结构化失败，Agent 继续
3. 不自动安装语言服务器；测试不依赖真实 Pyright
4. 不新增 LSP 数据库；与 Git / Snapshot 正交

详见 [v1.2-lsp-report.md](./v1.2-lsp-report.md)

---

## V1.1 Git-Aware Coding Workflow

**日期：** 2026-09-01

### 目标

让 Agent 理解 Git 工作区状态，形成自然 coding workflow（status → inspect → edit → test → diff → optional commit），Git 作为独立 Domain Service，与 Snapshot/Revert 正交。

### 已完成

- `backend/app/git/`：GitDetector / GitRepository / GitPolicy / GitService / GitContextProvider
- Git Tools：`git_status` / `git_diff` / `git_log` / `git_branch` / `git_commit`
- ContextManager：Git metadata 注入 Workspace Context（不含完整 diff）
- AgentService + API：`/api/sessions/{id}/git/*`
- CLI：`/git status|diff|log|branch|commit`
- 测试：9 模块 46 cases；全量 **466 passed**

### 设计决策

1. AgentLoop 不含 Git 特判；Tool → GitService → GitRepository
2. GitPolicy 结构化 ALLOW/ASK/DENY；commit 走 CommitPreview + PermissionHandler
3. Coding task ≠ auto commit；仅用户明确要求才 git_commit
4. Snapshot/Revert 负责 Agent 写文件回滚；Git 负责版本控制
5. 不新增 Git DB 表

详见 [v1.1-git-report.md](./v1.1-git-report.md)

---

## V1.0+ Semantic Memory & Intelligent Context

**日期：** 2026-08-31

### 目标

在不重写 AgentLoop 的前提下，把 V1.0 启发式 Context/Memory/Plan 升级为：LLM Planner（旁路）、Persistent Memory + Provenance、Semantic Code Index、Hybrid Retrieval、Memory-aware Context Assembly。

### 已完成

- `backend/app/memory/`：EmbeddingProvider（默认 Hash）、结构感知 chunking、SemanticIndex、HybridRetriever、LLM/启发式 MemoryExtractor、MemoryService
- `backend/app/planning/`：PlannerService + JSON parser；不修改 Workspace
- migration `004_semantic_memory.sql`：semantic_documents/chunks、task_summaries、memory 扩展列
- ContextManager：Retrieved Context 注入；revert 后 index/memory 失效
- CLI：`/memory *`、`/plan refresh`；API：`/api/sessions/{id}/memories|plans|context`
- 测试：`tests/test_semantic_v10plus.py`；全量 **394 passed**

### 设计决策

1. Planner / Memory 是旁路服务，不进 AgentLoop，不绕过 Permission
2. 与 ScriptedLLM 隔离：主对话队列不可被旁路 `chat()` 抢占
3. 向量存 SQLite JSON + 本地 cosine；默认 HashEmbedding（无 API key）
4. Embedding 只用于 code/docs/rules/memory/task summary，不用 Session/Run 元数据

### 后续

可选：真实 embedding provider 插件、独立 planning model、更细的 decay。

---

## V0.8 Interactive Permission + Live Agent Event

**日期：** 2026-08-30

### 目标

把 CodeWisp 从「可运行 Coding Agent」提升为具有实时交互能力的 Runtime：Interactive Permission + Live EventSink；为未来 Web UI / SSE 保留接口边界。不实现 Web UI / Diff / Snapshot。

### 已完成

- Permission domain：`PermissionRequest` / `PermissionDecision` / `PermissionHandler` / `CliPermissionHandler` / `PendingPermissionBroker`
- ASK → Handler → ALLOW 执行 / DENY observation；Policy DENY 仍不询问；无 Handler 保持 V0.7 硬停
- EventSink：`AgentEventSink` + CLI 实时 Trace；`AgentService.run(..., event_sink=, permission_handler=)`
- AgentRun `waiting_permission` 投影（由 AgentService 更新，Handler 不写库）
- FastAPI：providers/models、permissions pending/decide、messages 响应含 `events`
- 测试：permission domain / CLI / integration / event_sink / API

### 设计决策

1. Policy 只决定「要不要问」；Handler 只决定「用户允不允许」
2. AgentLoop 不 `input()`，不知 CLI/Web
3. EventSink 是 runtime delivery，不新增 events 表
4. CLI 与 API 共用 AgentService，CLI 不经 localhost HTTP

### 测试结果

`pytest`：**324 passed**（V0.7 基线 297 + V0.8 新增）

### 后续

V0.9 建议：Web UI Foundation、SSE EventSink、异步 Permission 体验优化。

---

## V0.7 Phase 3

**日期：** 2026-08-30

### 目标

CLI Model / Provider UX + Interface Boundary：把 Session / Provider / Model / AgentEvent 以可操作 CLI 呈现；CLI 仅作 Interface Layer。

### 已完成

- 命令：`/help` `/providers` `/models` `/model` `/status`；增强 `/session` `/sessions` `/new --provider-id/--model-id/--model`
- 模型切换：`AgentService.switch_session_model` + `ModelResolver.lookup`（先校验再写 Session）
- AgentEvent 轨迹渲染（`cli/trace.py`）：工具起止、Self-Correction 提示、PermissionRequired、Run 摘要
- Loop 最小增量：`permission_required` 事件（不改编排语义）
- 文档：Future Web UI Interface Boundary
- 测试：`test_cli_model_ux.py` 等

### 设计决策

1. CLI → Service only；不直连 Repository / SQLite
2. 模型校验用 `lookup`（不强制当场建 Client / 不要求 key 只为切模型）
3. 凭据状态展示 `registered` / `configured`，不伪造 API 可用
4. 不引入 rich/textual；纯文本轨迹
5. 不实现交互 Permission UI / Streaming

### 测试结果

`pytest`：**297 passed**

### 后续

V0.7 Phase 4 Web UI Foundation；V0.8 Permission UI / Streaming。

---

## V0.7 Phase 2

**日期：** 2026-08-30

### 目标

ModelResolver + Session Runtime Integration：Session 的 provider/model 身份真正决定本次 Agent 使用的 LLM。

### 已完成

- `ModelResolver` / `ResolvedModel`：查 Registry → 组装 `LLMConfig` → `LLMClient`
- `AgentService` 接入 `model_resolver`；每次 run 按 Session resolve 后注入 AgentLoop
- AgentRun 快照本次实际 provider/model；Session 事后变更不改写旧 Run
- 结构化错误码：`UNKNOWN_PROVIDER` / `UNKNOWN_MODEL` / `MODEL_PROVIDER_MISMATCH` / `PROVIDER_CONFIGURATION_ERROR` / `MODEL_CONFIGURATION_ERROR`
- CLI / API 默认使用 `ModelResolver.create_default()`；测试仍可用固定 `llm=`
- 测试：`test_model_resolver` / `test_agent_service_model_resolution`

### 设计决策

1. **Resolution 在 AgentService**，AgentLoop 只收现成 `llm`
2. **OpenAI-compatible 适配表**（base_url / api_key 环境变量）留在 Resolver，禁止进 Loop
3. **凭据仍仅环境变量**，不入库
4. **兼容** `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`；openai 可选用 `OPENAI_*`

### 测试结果

`pytest`：**291 passed**（含 V0.1–V0.6 + Phase 1 + Phase 2）。

**日期：** 2026-08-30

### 目标

Provider / Model Domain + Registry：稳定、可测试的身份目录，为 Phase 2 ModelResolver 做准备。不实现 Session → LLM 自动切换。

### 已完成

- `Provider` / `Model` 领域对象（无凭据字段）
- `ProviderRegistry` / `ModelRegistry`（内存、防重复、结构化错误）
- 默认目录：`deepseek` / `deepseek-chat` 与 `LLMConfig` 默认单一来源对齐；另含 `openai` 身份条目
- `EnvCredentialSource` + `openai_compatible` Runtime 边界（复用既有 LLMClient，不推翻）
- 测试：`test_provider` / `test_model` / `test_provider_registry` / `test_model_registry`
- 文档明确 Phase 1 vs Phase 2

### 设计决策

1. **Registry 不依赖 SQLite / FastAPI / AgentLoop**
2. **AgentLoop 仍只收 `llm=`** — 禁止 provider-specific 分支
3. **凭据仅环境变量** — Domain / Session / DB 不存 key
4. **默认值不复制第二套** — `DEFAULT_MODEL_ID = LLMConfig.DEFAULT_MODEL`

### 测试结果

见 Phase 1 完成报告（`pytest`：**277 passed**）。

### 后续

V0.7 Phase 2 — ModelResolver + Session Runtime Integration。

---

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
