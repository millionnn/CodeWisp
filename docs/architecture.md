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

### V0.4-A：Workspace + 只读 Coding Tools

```
AgentLoop → ToolExecutor → list/glob/read/search → Workspace
```

### V0.4-B：Safe Code Modification

```
AgentLoop → ToolExecutor → edit_file / write_file → Workspace
```

### V0.4-C：Controlled Command Execution（当前）

```text
                    AgentLoop
                        │
                        ▼
                   ToolExecutor
                        │
                        ▼
                  run_command
                        │
                        ▼
                ExecutionService
                        │
                 CommandPolicy
                 /      |      \
              ALLOW    ASK     DENY
                │        │       │
                ▼        │       ▼
             execute     │     reject
                         ▼
                PermissionRequired
                     （不执行）
```

| 模块 | 职责 |
|------|------|
| `backend/app/execution/` | Request / Result / Policy / Service（语言无关） |
| `backend/app/tools/builtin/execution/` | 薄 `run_command` Tool |
| `backend/app/workspace/` | 路径边界；执行 cwd 复用 `resolve_path` |
| `backend/app/agent/` | AgentLoop（无工具 / 语言特判） |
| `backend/app/tools/` | Tool System |

**工具目录：**

```text
backend/app/tools/builtin/
├── workspace/       # list/glob/read/search + edit/write
├── execution/       # run_command（V0.4-C）
└── intelligence/    # 预留：LSP, ...
```

**Execution 安全机制：**

- `shell=False`；`command` + `args` 列表，禁止 shell 拼接
- `cwd` 必须落在 Workspace 内
- 强制 timeout（默认 30s，上限 120s）
- stdout/stderr 截断（`max_output_chars`）
- Policy：`ALLOW` / `ASK` / `DENY`；ASK 返回 `permission_required`，不启动进程

**ExecutionService 与具体语言无关**——`pytest` / `mvn` / `cargo` 走同一套 Request → Policy → Service。

**本阶段明确未实现：** Self-Correction、Planning、Project Detection、LSP、Web UI、交互式 Permission、开放任意 Shell。

## 终止条件

| 状态 | 含义 |
|------|------|
| `COMPLETED` | 无 tool_calls，产出最终回答 |
| `MAX_STEPS` | 达到 `max_steps` |
| `FAILED` | 不可恢复错误 |

## 最终架构 / 未来架构

```
CLI / Web UI
    ↓
Agent Runtime（Loop · Planning · Context · Safety · Trace）
    ↓
LLM API  +  Tool System（只读 + 写入 + 受控执行已落地）
```

## 配置项

| 变量 | 含义 | 默认 |
|------|------|------|
| `LLM_API_KEY` | API 密钥（禁止入库） | — |
| `LLM_BASE_URL` | OpenAI 兼容地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `CODEWISP_WORKSPACE` | 目标仓库根（可被 `--workspace` 覆盖） | cwd |
