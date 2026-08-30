# CodeWisp 架构说明

> **说明：** 标注为「最终架构 / 未来架构」的内容描述目标形态，**当前尚未全部实现**。

## 版本演进（已实现）

### V0.1 – V0.5（摘要）

```text
V0.1 CLI + LLM Client
V0.2 Tool System
V0.3 Agent Loop
V0.4-A/B Workspace 只读 + 安全写入
V0.4-C Controlled Command Execution
V0.5 Self-Correction（Observation 驱动有限迭代）
```

### V0.6：Session、持久化与 Backend API

```text
CLI / FastAPI
      ↓
AgentService
      ↓
SessionService → Repositories → SqliteStore
      ↓
AgentLoop → Tools → Workspace / Execution
```

核心能力：

- **Session**：绑定 `workspace` + `provider_id` + `model_id`
- **Conversation Persistence**：完整 User / Assistant / ToolCall / Observation
- **AgentRun / AgentStep**：稳定 ID，为未来 Snapshot / Undo 预留关联
- **CLI 与 API 共用 Agent Core**（无第二套 Loop）
- **Schema migration**（SQLite v1）

```text
Session
  └── AgentRun (provider/model 快照)
        └── AgentStep
              ├── ToolCall
              └── Observation (tool message)
```

| 模块 | 职责 |
|------|------|
| `backend/app/agent/` | AgentLoop / State / Event（不知 SQLite） |
| `backend/app/session/` | Session / AgentRun / AgentStep 领域 + SessionService |
| `backend/app/services/` | AgentService（编排 + 持久化投影） |
| `backend/app/persistence/` | SqliteStore / migration / Repositories |
| `backend/app/api/` | FastAPI Session / Message API |
| `backend/app/cli/` | CLI → AgentService |
| `backend/app/workspace/` / `execution/` / `tools/` | 既有安全边界与工具 |

### V0.7 Phase 1：Provider / Model Domain + Registry

建立 Provider / Model 领域与内存 Registry（身份目录）。

### V0.7 Phase 2：ModelResolver + Session Runtime Integration

```text
Session.provider_id + model_id
        ↓
ModelResolver
        ↓
Provider / Model（Registry）
        ↓
LLMConfig + EnvCredentialSource
        ↓
LLMClient（OpenAI-compatible）
        ↓
AgentLoop(llm=...)
```

### V0.7 Phase 3：CLI Model / Provider UX + Interface Boundary

### V0.8：Interactive Permission + Live Agent Event（当前）

```text
CommandPolicy (ALLOW / ASK / DENY)
      ↓ ASK
PermissionHandler → ALLOW / DENY
      ↓
ExecutionService / Observation → AgentLoop 继续

AgentLoop
      ↓ AgentEvent
EventSink → CLI 实时 Trace / 未来 SSE
```

核心能力：

- **Interactive Permission**：ASK 经 `PermissionHandler`（`CliPermissionHandler` / `BrokerPermissionHandler`），不再无 Handler 时硬停；有 Handler 时 ALLOW 执行 / DENY 写 observation 并继续
- **EventSink**：`AgentLoop` / `AgentService` 运行时 `emit`；CLI `CliEventSink` 实时渲染；`event_sink=None` 时与 V0.7 兼容
- **Run 状态**：`WAITING_PERMISSION`（等待授权时投影到 AgentRun）
- **FastAPI**：`/api/providers` `/api/models`、pending/decide Permission、`POST .../messages` 返回 `events`

| 模块 | 职责 |
|------|------|
| `backend/app/permissions/` | PermissionRequest / Decision / Handler / Broker |
| `backend/app/agent/event_sink.py` | EventSink 抽象（Null / Recording / Composite） |
| `backend/app/cli/event_sink.py` | CLI 实时 Trace |

```text
CLI / Future Web UI
        ↓
   AgentService / SessionService
        ↓
   ModelResolver + AgentLoop
        ↓
   AgentEvent → CLI Trace Renderer
                 （未来：SSE / WebSocket）
```

CLI 命令：`/help` `/providers` `/models` `/model` `/status` 等；模型切换经 `AgentService.switch_session_model` → Registry `lookup` → Session 持久化；**不**在 CLI 内实现 Loop / Resolver 业务副本。

#### Interface Boundary for Future Web UI

```text
CLI                          Web UI
 │                             │
 │  直接调 Service             │  HTTP
 ▼                             ▼
AgentService ◄──────────── FastAPI
 │
 ├─ SessionService
 ├─ ModelResolver
 └─ AgentLoop → AgentEvent / Tools / Workspace
         │
         ▼
    Persistence (SQLite)
```

共享：`SessionService`、`AgentService`、`ModelResolver`、Tool System、`AgentEvent`、Persistence。

已有 API：`GET/POST /api/sessions`、`GET/POST .../messages` 等。  
未来可增加（**本阶段未实现**）：`GET /api/sessions/{id}/events` 或 `GET /api/runs/{id}/events`（SSE/WebSocket 消费同一套 AgentEvent）。

**禁止：** CLI → localhost HTTP → FastAPI 绕一圈；CLI 不得直连 SQLite Repository。

路线图：

```text
V0.6  Session stores provider/model identity
V0.7 Phase 1  Provider / Model domain + registry
V0.7 Phase 2  Runtime resolution (ModelResolver)
V0.7 Phase 3  CLI Model / Provider UX + AgentEvent trace
V0.8  Interactive Permission + Live EventSink  ← 当前
V0.9  Web UI / SSE / Snapshot（未实现）
```

## 终止条件

| 状态 | 含义 |
|------|------|
| `COMPLETED` | 无 tool_calls，产出最终回答 |
| `MAX_STEPS` | 迭代预算耗尽 |
| `PERMISSION_REQUIRED` | 无 PermissionHandler 时 ASK 硬停（V0.7 兼容） |
| `WAITING_PERMISSION` | 有 Handler 时等待用户 ALLOW/DENY（运行中投影） |
| `FAILED` | 不可恢复错误 |

## 最终架构 / 未来架构

```text
                         CodeWisp
                            │
                     Agent Runtime
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
      Session             Model              Tools
        │             (V0.7 Provider)           │
        └───────────────┬───────────────────────┘
                        │
                    Agent Run → Steps → ToolCall
                        │
                   Workspace → (V0.9 Snapshot / Diff / Undo)
```

## 配置项

| 变量 / 参数 | 含义 | 默认 |
|------|------|------|
| `LLM_API_KEY` | API 密钥（禁止入库） | — |
| `LLM_BASE_URL` | OpenAI 兼容地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `CODEWISP_WORKSPACE` | 目标仓库根 | cwd |
| `CODEWISP_DB` | SQLite 路径 | `~/.codewisp/codewisp.db` |
| `--max-steps` | 迭代预算 | 15 |
| `--session` | 续跑 Session ID | 新建 |
| `--provider-id` / `--model-id` | Session 模型身份（仅记录） | deepseek / LLM_MODEL |
