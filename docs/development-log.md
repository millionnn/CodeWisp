# 开发日志

## V0.1

**日期：** 2026-08-28

### 目标

实现最小可运行的 CodeWisp：多轮 LLM 命令行对话，以及可复用的 LLM 客户端与基础对话历史。

### 已完成

- 项目骨架（`backend/app/...`）
- `Message` / `Conversation`（system / user / assistant）
- OpenAI 兼容的 `LLMClient`（从环境变量读取配置，默认对接 DeepSeek）
- CLI：横幅、提示符、多轮对话、退出与空输入处理
- 缺密钥、错误配置、网络与 API 失败等领域异常
- `.env.example`、`.gitignore`、依赖与 pytest
- `README.md`、`docs/architecture.md`、本日志

### 设计决策

1. **LLM 核心与 CLI 分离** — 便于后续 Web API 复用同一客户端。
2. **仅使用官方 `openai` SDK** — 通过 DeepSeek 的 OpenAI 兼容接口调用；不引入任何 Agent 框架。
3. **对话历史采用追加式列表** — 暂不做上下文窗口管理，便于面试解释。
4. **可注入 OpenAI 客户端与 CLI I/O** — 无真实密钥、无真实终端也能单测。
5. **LLM 调用失败时回滚本轮 user 消息** — 避免未得到回复的轮次污染历史。

### Python 版本

基于 **Python 3.11.9** 开发（`requires-python >= 3.11`）。

### 后续

**V0.2 — 工具系统**

在现有模块上扩展，而非推倒重写：

- 新增 `backend/app/tools/`（工具协议 + 注册表）
- 在合适时机扩展消息 / API 载荷以支持 tool calling
- 继续以 `LLMClient.chat` 作为模型 I/O 边界；工具在本地由后续 Agent Runtime 执行

V0.1 阶段不实现工具。
