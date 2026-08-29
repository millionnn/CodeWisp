# CodeWisp

## Git 仓库地址

https://github.com/millionnn/CodeWisp.git

## 如何运行

环境要求：Python 3.11+；DeepSeek API Key（或其它 OpenAI 兼容接口）。

```bash
git clone https://github.com/millionnn/CodeWisp.git
cd CodeWisp
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，填入密钥（勿把密钥提交到仓库）：

```
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

启动：

```bash
# 默认：以当前工作目录为「目标仓库」(Workspace)
cd /path/to/your-project
python -m backend.app

# 或显式指定目标仓库（推荐，语义最清晰）
python -m backend.app --workspace /path/to/your-project
```

也可用环境变量（写入 `.env` 亦可）：

```bash
export CODEWISP_WORKSPACE=/path/to/your-project
python -m backend.app
```

优先级：`--workspace` > `CODEWISP_WORKSPACE` > `cwd`。  
注意：Workspace 是 Agent 要探索的项目目录，不是 CodeWisp 安装路径。在本仓库根目录启动时，相当于用 CodeWisp 自己当目标项目做自测。

示例任务：

- `计算 123 * 456`
- `计算 123 * 456，然后告诉我当前时间`
- `查看项目结构，找到 AgentLoop 相关代码并简要说明`

运行测试（可选）：

```bash
pytest
```

## 特色功能说明

CodeWisp 是从零实现的编程智能体（Coding Agent）：面向自然语言编程任务，目标能力包括探索代码仓库、读写与修改代码、执行本地命令与测试，并根据结果迭代修复。实现上不封装 Claude Code / Codex 等现成产品，也不使用 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen、CrewAI 等 Agent 框架；对话历史、工具定义与本地执行、模型输出解析、循环终止与错误处理等关键逻辑自行编写。模型侧使用厂商官方或 OpenAI 兼容 API（当前默认对接 DeepSeek），凭据仅通过环境变量 / 未入库配置提供。

当前已具备最小 Agent Runtime，以及面向仓库的**只读**探索能力：`list_files` / `glob` / `read_file` / `search_code`（经 Workspace 路径边界保护）。Agent 可自主列出结构、按模式找文件、搜索并阅读代码；**尚不能**修改文件或执行 Shell。

可选：单独验证工具系统（无需 API Key）：

```bash
python -m backend.app.tools list
python -m backend.app.tools run list_files '{"path":".","max_depth":1}'
python -m backend.app.tools run glob '{"pattern":"**/loop.py"}'
```

## 其它说明

- API Key 等凭据不得出现在仓库、README 或演示视频中。
- 开发过程文档见 `docs/`（架构说明、开发日志）。
- 鼓励使用 AI 辅助开发，但设计决策由作者负责，面试将围绕「为何这样运转」进行答辩。
