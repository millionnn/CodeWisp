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
AgentLoop
  ↓
ToolExecutor
  ↓
list_files / glob / read_file / search_code
  ↓
Workspace（路径边界 + 只读 IO）
```

### V0.4-B：Safe Code Modification（当前）

```
AgentLoop
  ↓
ToolExecutor
  ↓
edit_file / write_file
  ↓
Workspace.replace_text / write_text
  ↓
resolve_path + atomic write
```

| 模块 | 职责 |
|------|------|
| `backend/app/workspace/` | `Workspace`：路径边界 + list/glob/read/search + write_text/replace_text |
| `backend/app/tools/builtin/workspace/` | 一工具一文件：只读四工具 + `edit_file` / `write_file` |
| `backend/app/agent/` | AgentLoop（无工具特判） |
| `backend/app/tools/` | Tool System |
| `backend/app/cli/` | UI |

**工具目录规划（与能力分类对齐）：**

```text
backend/app/tools/builtin/
├── workspace/       # 已实现：list/glob/read/search + edit_file/write_file
│                    # 预留：patch（若需要更细粒度补丁）
├── execution/       # 预留：run_command, git（V0.4-C）
└── intelligence/    # 预留：LSP, ...
```

**路径边界：** `Path.resolve()` + `relative_to(workspace_root)`，拒绝 `..` 穿越与 workspace 外绝对路径；写入同样复用，禁止 Tool 直接 `open()`。

**确定性编辑（edit_file）：** `old_text` 精确计数；仅当 `actual == expected_replacements` 时替换并原子写回；否则结构化失败，不猜测。

**原子写入：** 同目录临时文件 → `os.replace`，避免半截截断。

**write_file：** 默认 `overwrite=false`；缺失父目录时自动创建（仍受边界约束）。

**Workspace 语义（重要）：**

- `Workspace` = Agent **服务的目标仓库**（用户打开的项目），不是 CodeWisp 源码树。
- 根目录解析挂点：`resolve_workspace_root()`  
  优先级：显式参数（CLI `--workspace` / 未来 Web Session）→ 环境变量 `CODEWISP_WORKSPACE` → `cwd`。
- 未来 Web UI：每个 Session 绑定自己的 `workspace_root`，注入 `Workspace`，无需改 AgentLoop。

**本阶段明确未实现（V0.4-C 及以后）：** `run_command` / shell / git / patch / LSP / self-correction。

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
LLM API  +  Tool System（只读 + 安全写入已落地；Shell / git 后续）
```

## 配置项

| 变量 | 含义 | 默认 |
|------|------|------|
| `LLM_API_KEY` | API 密钥（禁止入库） | — |
| `LLM_BASE_URL` | OpenAI 兼容地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
