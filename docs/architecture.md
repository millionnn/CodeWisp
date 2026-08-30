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

### V0.6：Session、持久化与 Backend API（当前）

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

**本阶段明确未实现：** Multi-Provider Runtime、Snapshot / Undo / Diff、Web UI、Context Compression、交互式 Permission UI。

## 终止条件

| 状态 | 含义 |
|------|------|
| `COMPLETED` | 无 tool_calls，产出最终回答 |
| `MAX_STEPS` | 迭代预算耗尽 |
| `PERMISSION_REQUIRED` | ASK / permission_required，硬停 |
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
