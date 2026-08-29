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

# 可选：限制迭代预算（每次 LLM 调用计 1 步）
python -m backend.app --workspace /path/to/your-project --max-steps 8
```

也可用环境变量（写入 `.env` 亦可）：

```bash
export CODEWISP_WORKSPACE=/path/to/your-project
python -m backend.app
```

优先级：`--workspace` > `CODEWISP_WORKSPACE` > `cwd`。  
注意：Workspace 是 Agent 要探索的项目目录，不是 CodeWisp 安装路径。在本仓库根目录启动时，相当于用 CodeWisp 自己当目标项目做自测。启动前请确保 PATH 中有目标项目所需的测试命令（例如已 `source` 含 pytest 的 venv）。

示例任务：

- `计算 123 * 456`
- `查看项目结构，找到 AgentLoop 相关代码并简要说明`
- `把某文件中的指定片段改成新内容（精确匹配）`
- `运行这个项目的测试，并告诉我结果`
- `修复这个项目的测试失败，并运行测试验证`

运行测试（可选）：

```bash
pytest
```

## 特色功能说明

CodeWisp 是从零实现的编程智能体（Coding Agent）：面向自然语言编程任务，目标能力包括探索代码仓库、读写与修改代码、执行本地命令与测试，并根据结果迭代修复。实现上不封装 Claude Code / Codex 等现成产品，也不使用 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen、CrewAI 等 Agent 框架；对话历史、工具定义与本地执行、模型输出解析、循环终止与错误处理等关键逻辑自行编写。模型侧使用厂商官方或 OpenAI 兼容 API（当前默认对接 DeepSeek），凭据仅通过环境变量 / 未入库配置提供。

### 当前能力

- **Coding Tools：** `list_files` / `glob` / `read_file` / `search_code` / `edit_file` / `write_file`
- **受控执行：** `run_command`（语言无关 Execution Layer + CommandPolicy：ALLOW / ASK / DENY）
- **Workspace 边界：** 路径解析与 cwd 隔离
- **V0.5 Self-Correction：** 在有限迭代预算内，根据 Observation 自主决定是否继续读/搜/改/跑并验证。  
  Self-Correction is **LLM-driven**；框架不硬编码 Python / pytest 专用修复策略，只提供工具、状态、预算、安全边界与终止条件（含 `permission_required` 硬停）。

### 当前不支持

Planning、项目/语言自动探测、LSP、Web UI、交互式 Permission UI、Context Compression、开放式任意 Shell。

可选：单独验证工具系统（无需 API Key）：

```bash
python -m backend.app.tools list
python -m backend.app.tools run list_files '{"path":".","max_depth":1}'
python -m backend.app.tools run run_command '{"command":"python3","args":["-c","print(1)"],"timeout":10}'
```

## 其它说明

- API Key 等凭据不得出现在仓库、README 或演示视频中。
- 开发过程文档见 `docs/`（架构说明、开发日志）。
- 鼓励使用 AI 辅助开发，但设计决策由作者负责，面试将围绕「为何这样运转」进行答辩。
