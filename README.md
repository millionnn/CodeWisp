# CodeWisp

## Git 仓库地址

https://github.com/millionnn/CodeWisp.git

## 如何运行

环境要求：Python 3.11+；DeepSeek API Key（或其它 OpenAI 兼容接口）。

### 一次性安装（推荐）

```bash
git clone https://github.com/millionnn/CodeWisp.git
cd CodeWisp
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

编辑 `.env`，填入密钥（勿提交到仓库）：

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

CLI 命令：`/sessions` `/session` `/new [title]` `/use <id>` `/delete <id>`（`/rm`）`/history` `/exit`。
普通输入经 **AgentService → AgentLoop** 执行并持久化。

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

### 当前能力（V0.6）

- **Coding Tools：** `list_files` / `glob` / `read_file` / `search_code` / `edit_file` / `write_file`
- **受控执行：** `run_command`（ALLOW / ASK / DENY）
- **Self-Correction：** Observation 驱动有限迭代（LLM-driven，无语言特判）
- **Session + SQLite 持久化：** Conversation / AgentRun / AgentStep / ToolCall；进程重启可恢复
- **Provider / Model Identity：** Session 与 AgentRun 记录 `provider_id` / `model_id`（V0.6 仅身份，不做多 Provider Runtime）
- **Backend API + CLI** 共用 `AgentService → AgentLoop`

### 当前不支持

完整 Multi-Provider Runtime、Model Registry、Web UI、Snapshot / Diff / Undo、Context Compression、交互式 Permission UI、Planning、LSP。

可选：单独验证工具系统（无需 API Key）：

```bash
python -m backend.app.tools list
python -m backend.app.tools run list_files '{"path":".","max_depth":1}'
```

## 其它说明

- API Key 等凭据不得出现在仓库、README、Session 表或演示视频中。
- 开发过程文档见 `docs/`（架构说明、开发日志）。
- 鼓励使用 AI 辅助开发，但设计决策由作者负责，面试将围绕「为何这样运转」进行答辩。
