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
python -m backend.app
```

进入交互后输入自然语言任务；Agent 可自行决定是否调用工具。输入 `/exit` 或 `/quit` 退出。

示例任务：

- `计算 123 * 456`
- `计算 123 * 456，然后告诉我当前时间`

运行测试（可选）：

```bash
pytest
```

## 特色功能说明

CodeWisp 是从零实现的编程智能体（Coding Agent）：面向自然语言编程任务，目标能力包括探索代码仓库、读写与修改代码、执行本地命令与测试，并根据结果迭代修复。实现上不封装 Claude Code / Codex 等现成产品，也不使用 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen、CrewAI 等 Agent 框架；对话历史、工具定义与本地执行、模型输出解析、循环终止与错误处理等关键逻辑自行编写。模型侧使用厂商官方或 OpenAI 兼容 API（当前默认对接 DeepSeek），凭据仅通过环境变量 / 未入库配置提供。

当前已具备完整的最小 Agent Runtime：接收任务 → 调用 LLM → 识别 Tool Call → 经 ToolExecutor 执行工具 → 将 Observation 写回对话 → 多轮循环 → 在无 tool_calls 或达到最大步数时终止。内置工具目前为安全计算器与本地时间查询；读写文件、Shell 等编码工具尚未加入。

可选：单独验证工具系统（无需 API Key）：

```bash
python -m backend.app.tools list
python -m backend.app.tools run calculator '{"expression":"12 * 8 + 5"}'
```

## 其它说明

- API Key 等凭据不得出现在仓库、README 或演示视频中。
- 开发过程文档见 `docs/`（架构说明、开发日志）。
- 鼓励使用 AI 辅助开发，但设计决策由作者负责，面试将围绕「为何这样运转」进行答辩。
