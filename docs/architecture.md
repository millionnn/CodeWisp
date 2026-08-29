# CodeWisp 架构说明

> **说明：** 标注为「最终架构 / 未来架构」的内容描述目标形态，**当前尚未全部实现**。

## 版本演进（已实现）

### V0.1：对话 CLI + LLM Client

```
用户 → CLI → LLM Client → LLM API → CLI
```

### V0.2：Tool System

```
Tool → ToolRegistry → ToolExecutor → ToolResult
```

### V0.3：Agent Loop

```
User → AgentLoop → LLM (+ tools schema)
                 → ToolExecutor → ToolResult → Observation → LLM …
```

### V0.4-A / V0.4-B：Workspace 只读 + 安全写入

```
list/glob/read/search / edit_file/write_file → Workspace
```

### V0.4-C：Controlled Command Execution

```text
run_command → CommandPolicy (ALLOW|ASK|DENY) → ExecutionService → ExecutionResult
```

### V0.5：Self-Correction / Bounded Autonomous Repair（当前）

Self-Correction **不是**独立的 Python 修复器，而是现有 Agent Loop 基于 Observation 的有限自主迭代：

```text
                 ┌─────────────────────┐
                 │      AgentLoop      │
                 └──────────┬──────────┘
                            │
                            ▼
                          LLM
                            │
                     Tool Call
                            │
                            ▼
                         Tool
                            │
                            ▼
                      Observation
                            │
                            └─────────────┐
                                          │
                                          ▼
                                         LLM
                                          │
                               ┌──────────┴──────────┐
                               │                     │
                            Continue               Finish
                               │
                               ▼
                         Another Tool
```

框架提供：

- 工具与 Observation 回写
- 迭代预算（`max_steps`，默认 15）
- `termination_reason`：`completed` / `max_steps` / `permission_required` / `failed`
- `PERMISSION_REQUIRED`：ASK 时硬停，绝不自动 ALLOW

框架**不**提供：写死的「pytest 失败 → edit_file」策略。

| 模块 | 职责 |
|------|------|
| `backend/app/agent/` | AgentLoop / State / Event（工具无关） |
| `backend/app/workspace/` | 路径边界与读写 |
| `backend/app/execution/` | 语言无关命令执行 + Policy |
| `backend/app/tools/` | Tool System + Coding / Execution 工具 |

**工具目录：**

```text
backend/app/tools/builtin/
├── workspace/       # list/glob/read/search + edit/write
├── execution/       # run_command
└── intelligence/    # 预留：LSP, ...
```

**本阶段明确未实现：** Planning、Project Detection、LSP、Web UI、交互式 Permission、Context Compression。

## 终止条件

| 状态 | 含义 |
|------|------|
| `COMPLETED` | 无 tool_calls，产出最终回答 |
| `MAX_STEPS` | 迭代预算耗尽 |
| `PERMISSION_REQUIRED` | 工具返回 ASK / permission_required，硬停 |
| `FAILED` | 不可恢复错误 |

## 最终架构 / 未来架构

```
CLI / Web UI
    ↓
Agent Runtime（Loop · Planning · Context · Safety · Trace）
    ↓
LLM API  +  Tool System（只读 + 写入 + 受控执行 + 有限 Self-Correction）
```

## 配置项

| 变量 / 参数 | 含义 | 默认 |
|------|------|------|
| `LLM_API_KEY` | API 密钥（禁止入库） | — |
| `LLM_BASE_URL` | OpenAI 兼容地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `CODEWISP_WORKSPACE` | 目标仓库根 | cwd |
| `--max-steps` | 迭代预算 | AgentLoop 默认 15 |
