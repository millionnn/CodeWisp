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

进入交互后输入自然语言问题即可对话；输入 `/exit` 或 `/quit` 退出。

运行测试（可选）：

```bash
pytest
```

## 特色功能说明

CodeWisp 是从零实现的编程智能体（Coding Agent）：面向自然语言编程任务，目标能力包括探索代码仓库、读写与修改代码、执行本地命令与测试，并根据结果迭代修复。实现上不封装 Claude Code / Codex 等现成产品，也不使用 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen、CrewAI 等 Agent 框架；对话历史、工具定义与本地执行、模型输出解析、循环终止与错误处理等关键逻辑自行编写。模型侧使用厂商官方或 OpenAI 兼容 API（当前默认对接 DeepSeek），凭据仅通过环境变量 / 未入库配置提供。

当前仓库已具备可运行的命令行对话入口、可复用的 LLM 客户端，以及基础多轮对话历史管理；后续将继续完善工具系统、Agent 循环、编码工具与 Web IDE 等能力。

## 其它说明

- API Key 等凭据不得出现在仓库、README 或演示视频中。
- 开发过程文档见 `docs/`（架构说明、开发日志）。
- 鼓励使用 AI 辅助开发，但设计决策由作者负责，面试将围绕「为何这样运转」进行答辩。
