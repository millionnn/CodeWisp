# CodeWisp 架构说明

> **说明：** 标注为「最终架构 / 未来架构」的内容描述目标形态，**当前尚未全部实现**，请勿误认为已全部落地。

## 当前已实现

### V0.1：对话 CLI + LLM Client

```
用户 → CLI → LLM Client → LLM API → CLI
```

| 模块 | 职责 |
|------|------|
| `backend/app/cli/` | 终端输入输出 |
| `backend/app/llm/` | Conversation、LLM Client、`LLMResponse` 领域对象、领域异常 |
| `backend/app/main.py` | 组装配置与 CLI |

`LLMClient.chat()` 返回领域对象 `LLMResponse`（`content` / `tool_calls` / `finish_reason` / `raw_response`），SDK 的 `choices[0].message` 不向外传播。当前 CLI 只使用 `.text`；`tool_calls` 已可解析但**不会自动执行**（留给 V0.3 Agent Loop）。

### V0.2：Tool System

```
Tool 定义
  ↓
ToolRegistry（注册 / 查找）
  ↓
ToolExecutor（按名称 + 参数执行）
  ↓
ToolResult（success / output / error / metadata）
```

| 模块 | 职责 |
|------|------|
| `backend/app/tools/base.py` | Tool 抽象（name / description / parameters / execute） |
| `backend/app/tools/result.py` | 统一 `ToolResult` |
| `backend/app/tools/registry.py` | 注册表 |
| `backend/app/tools/executor.py` | 统一执行与参数校验 |
| `backend/app/tools/builtin/` | 内置工具：`calculator`、`get_current_time` |

**边界（刻意为之）：**

- Tool System **不**依赖 CLI / LLM / FastAPI / React
- V0.2 **不**实现 Agent Loop，也 **不**让 LLM 自动调用工具
- 编码类工具（读文件、写文件、Shell 等）属于 **V0.4**
- 人工验证入口：`python -m backend.app.tools`（不经 LLM）

`ToolResult.metadata` 含 `tool_name`、`arguments`、`duration_ms`，为未来 V0.8 Trace UI 预留结构，当前无 Event Bus / WebSocket。

## 设计原则（已生效）

**Agent 核心与 UI 解耦**

```
当前：  CLI  →  LLM Client
        （独立）ToolExecutor → Registry → Tool

未来：  CLI / Web → Agent Runtime → LLM + Tool System
```

## 最终架构 / 未来架构

```
┌─────────────────────────────────────────────────────────┐
│  Web IDE (React)  │  CLI                                  │
└─────────┬─────────┴──────────┬────────────────────────────┘
          │                    │
          ▼                    ▼
   后端 API (HTTP/WS)      直接调用
          │
          ▼
┌─────────────────────────────────────┐
│           Agent Runtime (V0.3+)     │
│  规划 · 循环 · 上下文 · 安全          │
│  Trace                              │
└─────────────────┬───────────────────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
     LLM API   Tool System   （V0.4 编码工具）
```

## 版本职责划分

| 版本 | 做什么 | 不做什么 |
|------|--------|----------|
| V0.1 | CLI + LLM + 对话历史 | 工具 |
| V0.2 | Tool / Registry / Executor / Result | Agent Loop、自动 Tool Calling |
| V0.3 | Agent Loop：LLM ↔ Tool Call ↔ Observation | 完整 Coding Tools |
| V0.4 | read/write/search/shell 等编码工具 | — |

## 配置项

| 变量 | 含义 | 当前默认 |
|------|------|----------|
| `LLM_API_KEY` | API 密钥（必填，禁止入库） | — |
| `LLM_BASE_URL` | OpenAI 兼容接口地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |
