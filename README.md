# CodeWisp

## Git 仓库地址

https://github.com/millionnn/CodeWisp.git

## 如何运行

环境要求：Python 3.11+；DeepSeek / 硅基流动等 **OpenAI 兼容** API Key。

### 一次性安装（推荐）

```bash
git clone https://github.com/millionnn/CodeWisp.git
cd CodeWisp
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

编辑 `.env`。若使用**硅基流动 + Qwen**：

```
LLM_API_KEY=你的硅基流动密钥
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen3.5-4B
```

启动后可用：

```bash
codewisp --provider-id siliconflow --model-id Qwen/Qwen3.5-4B
# 或进入后：/model siliconflow Qwen/Qwen3.5-4B
```

也可单独配置 `SILICONFLOW_API_KEY`（可选 `SILICONFLOW_BASE_URL`），与 DeepSeek 的 `LLM_*` 并存。

DeepSeek 示例：

```
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

也可把同一份配置放到 `~/.codewisp/.env`，这样不依赖当前目录。

### 日常用法：任意项目目录直接启动

一次性把 CLI 挂到用户 PATH（之后**不必**再 `source` venv）：

```bash
cd /Users/wangyiran/Desktop/CodeWisp   # 或你的 CodeWisp 克隆路径
./scripts/install_cli.sh
source ~/.zshrc
```

然后在**任意**需要 Agent 的项目里：

```bash
cd /path/to/your-project
codewisp
```

Workspace 默认 = 当前目录。API：

```bash
codewisp-api
```

常用可选参数：

```bash
codewisp --title "My Session" --max-steps 15
codewisp --session ses_xxx          # 续跑已有 Session
codewisp -w /other/project          # 显式指定 Workspace（覆盖 cwd）
codewisp --db ~/.codewisp/demo.db   # 可选：指定 SQLite 路径
```

CLI 命令：`/help` `/sessions` `/session` `/new` `/use` `/history` `/providers` `/models` `/model` `/status` `/delete` `/exit`。
普通输入经 **AgentService → ModelResolver → AgentLoop** 执行并持久化；工具轨迹由 AgentEvent 展示。

Workspace 解析优先级：`--workspace` / `-w` > `CODEWISP_WORKSPACE` > **cwd**。  
注意：Workspace 是 Agent 要操作的项目，不是 CodeWisp 源码目录。

开发调试仍可用：`cd CodeWisp && source .venv/bin/activate && python -m backend.app`。

### Backend API

```bash
codewisp-api
# 默认 http://127.0.0.1:8000 ；文档 /docs
```

主要接口：

```http
POST   /api/sessions
GET    /api/sessions
GET    /api/sessions/{id}
PATCH  /api/sessions/{id}
DELETE /api/sessions/{id}
GET    /api/sessions/{id}/messages
POST   /api/sessions/{id}/messages
```

示例任务：

- `计算 123 * 456`
- `查看项目结构，找到 AgentLoop 相关代码并简要说明`
- `运行这个项目的测试，并告诉我结果`
- `修复这个项目的测试失败，并运行测试验证`

运行自动化测试：

```bash
pytest
```

## 特色功能说明

CodeWisp 是从零实现的编程智能体（Coding Agent）：面向自然语言编程任务，目标能力包括探索代码仓库、读写与修改代码、执行本地命令与测试，并根据结果迭代修复。实现上不封装 Claude Code / Codex 等现成产品，也不使用 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen、CrewAI 等 Agent 框架；对话历史、工具定义与本地执行、模型输出解析、循环终止与错误处理等关键逻辑自行编写。模型侧使用厂商官方或 OpenAI 兼容 API（当前默认对接 DeepSeek），凭据仅通过环境变量 / 未入库配置提供。

### 当前能力（V0.6 + V0.7 Phase 1–3）

- **Coding Tools：** `list_files` / `glob` / `read_file` / `search_code` / `edit_file` / `write_file`
- **受控执行：** `run_command`（ALLOW / ASK / DENY）
- **Self-Correction：** Observation 驱动有限迭代（LLM-driven，无语言特判）
- **Session + SQLite 持久化：** Conversation / AgentRun / AgentStep / ToolCall；进程重启可恢复
- **Provider / Model Domain + Registry（Phase 1）**
- **ModelResolver + Session Runtime（Phase 2）**
- **CLI Model / Provider UX + AgentEvent 轨迹（Phase 3）：** `/providers` `/models` `/model` `/status` `/help`；工具调用可视化；PermissionRequired 展示
- **Backend API + CLI** 共用 `AgentService`（CLI 不直连 SQLite / 不自建 Loop）

### 当前不支持

交互式 Permission UI（Allow/Deny）、Web UI、Streaming / SSE / WebSocket、Snapshot / Diff / Undo、Context Compression、Planning、LSP。

可选：单独验证工具系统（无需 API Key）：

```bash
python -m backend.app.tools list
python -m backend.app.tools run list_files '{"path":".","max_depth":1}'
```

## 其它说明

- API Key 等凭据不得出现在仓库、README、Session 表或演示视频中。
- 开发过程文档见 `docs/`（架构说明、开发日志）。
- 鼓励使用 AI 辅助开发，但设计决策由作者负责，面试将围绕「为何这样运转」进行答辩。
