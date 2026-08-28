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

与 UI / LLM 解耦；内置 `calculator`、`get_current_time`。

### V0.3：Agent Loop（当前）

```
User
  ↓
AgentLoop
  ↓
LLMClient (+ tools schema) → LLMResponse
  ↓
有 tool_calls？
  ├─ 否 → Final Answer → COMPLETED
  └─ 是 → ToolExecutor → ToolResult
            ↓
         Observation 写回 Conversation
            ↓
         再次调用 LLM …（直至终止 / max_steps）
```

| 模块 | 职责 |
|------|------|
| `backend/app/agent/loop.py` | Agent 编排：LLM ↔ Tool ↔ Observation |
| `backend/app/agent/state.py` | `AgentState` / `AgentStatus` |
| `backend/app/agent/events.py` | 轻量事件（无 Event Bus，供未来 Trace） |
| `backend/app/llm/` | Conversation（含 tool）、LLMClient、LLMResponse |
| `backend/app/tools/` | Tool System（V0.2） |
| `backend/app/cli/` | 仅 UI：输入任务、展示结果与工具轨迹 |

**边界：**

- LLMClient **只**做 Model I/O，不执行工具
- ToolExecutor **不知道** LLM
- CLI **不**实现 while tool_calls
- Coding Tools（读文件 / Shell 等）属于 **V0.4**

## 终止条件

| 状态 | 含义 |
|------|------|
| `COMPLETED` | 模型未再返回 tool_calls，产出最终回答 |
| `MAX_STEPS` | 达到 `max_steps`（默认 10） |
| `FAILED` | 不可恢复错误（如 LLM 请求失败） |

工具执行失败 → 作为 observation 回写，**不**直接崩溃 Agent。

## 最终架构 / 未来架构

```
CLI / Web UI
    ↓
Agent Runtime（Loop · Planning · Context · Safety · Trace）
    ↓
LLM API  +  Tool System（含 V0.4 Coding Tools）
```

## 配置项

| 变量 | 含义 | 默认 |
|------|------|------|
| `LLM_API_KEY` | API 密钥（禁止入库） | — |
| `LLM_BASE_URL` | OpenAI 兼容地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
