# CodeWisp 架构说明

> **说明：** 标注为「最终架构 / 未来架构」的内容描述目标形态，**当前尚未全部实现**，请勿误认为已全部落地。

## 当前实现（最小可运行 CLI）

数据流：

```
用户 → CLI → LLM Client → LLM API → CLI
```

| 模块 | 职责 |
|------|------|
| `backend/app/cli/` | 终端输入输出（横幅、提示符、打印回复） |
| `backend/app/llm/messages.py` | `Message` 与内存中的 `Conversation` |
| `backend/app/llm/client.py` | OpenAI 兼容的 Chat Completions 客户端 |
| `backend/app/llm/errors.py` | 面向用户的领域异常 |
| `backend/app/main.py` | 组装配置、客户端与 CLI |

当前刻意未实现：工具调用、Agent 循环、自我纠错、文件读写、Shell、规划与上下文压缩、HTTP/WebSocket API、Web UI / Monaco / Diff、安全层等。

## 设计原则（已生效）

**Agent 核心与 UI 解耦**

- CLI 依赖 `LLMClient`，反向不成立。
- 未来 Web UI 经后端 API 调用同一套核心；CLI 保持为薄适配层。

```
当前：  CLI  →  LLM Client
未来：  CLI  →  Agent Runtime
        Web  →  Backend API  →  Agent Runtime
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
│           Agent Runtime             │
│  规划 · 循环 · 上下文 · 安全          │
│  工具注册表 · 执行轨迹 Trace          │
└─────────────────┬───────────────────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
     LLM API   文件工具   Shell 工具
```

上图中超出「当前实现」的部分均为规划，尚未交付。

## 配置项

| 变量 | 含义 | 当前默认 |
|------|------|----------|
| `LLM_API_KEY` | API 密钥（必填，来自环境变量 / `.env`，禁止入库） | — |
| `LLM_BASE_URL` | OpenAI 兼容接口地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |

## 版本演进（参考）

| 版本 | 重点 |
|------|------|
| V0.1 | CLI + LLM Client + 对话历史 |
| V0.2 | 工具系统 |
| V0.3 | Agent 循环 |
| V0.4 | 编码类工具 |
| V0.5 | 自我纠错 |
| V0.6 | Agent 后端 API |
| V0.7 | Web UI MVP |
| V0.8 | Agent Trace UI |
| V0.9 | 代码编辑器 + Diff |
| V1.0 | 规划 + 上下文 |
| V1.1 | 安全与健壮性 |
| V1.2 | 最终打磨 |
