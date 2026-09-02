Git 仓库
https://github.com/millionnn/CodeWisp.git

如何运行
Python 3.11+；OpenAI 兼容 API（DeepSeek 或硅基流动）。密钥只写入未入库的 .env，不要出现在本文件或视频里。

  git clone https://github.com/millionnn/CodeWisp.git
  cd CodeWisp
  python3 -m venv .venv && source .venv/bin/activate
  pip install -e ".[dev]"
  cp .env.example .env
  # 编辑 .env：LLM_API_KEY、LLM_BASE_URL、LLM_MODEL

在任意目标项目目录执行 codewisp（Workspace 默认是当前目录，不是 CodeWisp 源码树）。
开发调试：python -m backend.app
HTTP 接口：codewisp-api
无密钥可先验证工具系统：python -m backend.app.tools list
自测：pytest

特色
CodeWisp 是我从零实现的编程智能体：能探索仓库、改代码、跑测试，并按失败结果继续修。不封装 Claude Code / Codex 等产品，也不使用 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen、CrewAI。题目点名的关键逻辑——对话历史与上下文、工具定义与本地执行、模型输出解析、循环终止、错误处理——全部自行编写。模型只负责决策；文件、命令、Git、LSP、MCP 都在本机。

我没有把「更强」做成更长的 Prompt 或 Loop 里的 if git / if lsp。Git、LSP、MCP、工作区快照都是独立领域服务，对 Agent 只暴露为 Tool，失败则以 Observation 写回。这是本项目希望被追问的主线。

1. 自我纠错是循环本身。无独立 Repair Engine，也不为 pytest 写死重试；有 tool_calls 就执行，失败则再决策，预算是 max_steps。
2. 权限三态 ALLOW / ASK / DENY。危险命令与 git commit 需确认；用户拒绝后 Agent 带着结果继续，而不是崩溃退出。
3. Git 与 Snapshot 正交。/git 理解分支与工作区；/diff /revert 只回滚本轮 Agent 写盘。编码任务默认不自动提交。
4. LSP 增强、可降级。有 Pyright 时用诊断辅助修复；没有则退回搜索与测试，语言服务器不是单点故障。
5. 分层上下文与会话。规则、计划、记忆、Git/LSP 元数据按预算装配；SQLite 持久化，进程重启可续跑。CLI 与 FastAPI 共用同一套 AgentService。

其它
终止状态包括完成、步数耗尽、等待授权、失败，避免无限转。测试覆盖 Loop、权限、Git、LSP 等，不依赖真实 Language Server。设计过程见 docs/。使用过 AI 辅助开发，但边界划分与取舍由我负责，面试可按「为什么这样运转」提问。
