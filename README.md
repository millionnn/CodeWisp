# CodeWisp

> **A CLI-first autonomous coding agent built from scratch for real software engineering tasks.**

CodeWisp 是一个从零实现的自主编程智能体（Coding Agent）。它通过大语言模型驱动本地工具，在真实代码仓库中完成**代码理解、任务规划、代码修改、命令执行、测试验证、自主纠错、代码诊断与版本管理**。

CodeWisp 不依赖 LangChain、LlamaIndex、AutoGen、CrewAI 等 Agent 框架，而是自行实现 Agent Runtime、Tool System、Context Management、Permission、Persistence、Snapshot、Git 与 LSP 等核心能力。

核心工作闭环：

```text
User Task
   │
   ▼
Context / Plan
   │
   ▼
LLM Reasoning
   │
   ▼
Tool Execution
   │
   ├── Read / Search
   ├── Edit / Write
   ├── Run Command
   ├── LSP Diagnostics
   └── Git
   │
   ▼
Observation
   │
   ▼
Self-Correction
   │
   ▼
Verification
   │
   ▼
Diff / Revert / Commit
```

---

## ✨ Features

### 🤖 Autonomous Coding

CodeWisp 支持多轮 **LLM → Tool → Observation** 执行循环。

Agent 可以自主：

* 理解用户编程任务
* 浏览和搜索代码
* 读取项目文件
* 修改代码
* 创建文件
* 执行测试和命令
* 根据执行结果继续推理
* 修复之前产生的问题

因此它不是一次性的代码生成器，而是一个能够持续执行任务的 Coding Agent。

---

### 🔄 Self-Correction

CodeWisp 将工具执行结果重新反馈给 Agent。

例如：

```text
修改代码
   ↓
运行测试
   ↓
测试失败
   ↓
分析错误
   ↓
定位相关代码
   ↓
再次修改
   ↓
重新测试
   ↓
测试通过
```

Agent 不需要预先写死具体的修复路径，而是根据测试结果和环境反馈动态决定下一步行动。

---

### 🧠 Context / Plan / Memory

CodeWisp 提供分层 Context 管理机制，将不同来源的信息按照任务相关性组织：

```text
System Instructions
       ↓
Project Rules
       ↓
Task / Plan
       ↓
Memory
       ↓
Retrieved Code
       ↓
Workspace State
       ↓
Recent Messages
       ↓
Tool Observations
```

同时支持：

* Project Rules
* Task State
* Plan / Plan Steps
* Memory
* Context Budget
* Context Compression
* Workspace Context
* Conversation Persistence

Agent 可以在有限上下文预算下优先保留与当前任务相关的信息。

---

### 🔐 Permission System

CodeWisp 将 Agent 操作划分为三级权限：

```text
ALLOW ──► 直接执行
ASK   ──► 请求用户确认
DENY  ──► 阻止执行
```

例如：

* 读取文件：ALLOW
* 普通测试命令：ALLOW
* 修改代码：根据策略处理
* Git Commit：ASK
* 危险 Git 操作：DENY

权限判断与具体交互 Handler 解耦，因此 CLI、API 等不同运行环境可以使用不同的权限处理方式。

---

### 📸 Snapshot / Diff / Revert

CodeWisp 不依赖 Git 来追踪 Agent 的修改，而是维护独立的 Workspace Change Management。

可以记录：

```text
Run
 ├── Step 1
 │    └── file changes
 ├── Step 2
 │    └── file changes
 └── Step 3
      └── file changes
```

支持：

* Snapshot
* File Diff
* Step-level Change Tracking
* Run-level Change Tracking
* Revert

因此即使 Agent 连续修改多个文件，也可以将一次完整任务产生的修改整体回滚。

---

### 🌿 Git-Aware Workflow

CodeWisp 提供独立的 Git Domain Service 与 Git Tools。

Agent 可以感知：

* Repository Root
* Current Branch
* Working Tree Status
* Modified / Staged / Untracked Files
* Recent Commits
* Ahead / Behind Status

支持：

```text
/git status
/git diff
/git log
/git branch
/git commit
```

Commit 不会被 Agent 静默执行，而是先生成 **Commit Preview**，再经过 Permission Handler 请求用户确认。

---

### 🧩 LSP-Aware Coding Intelligence

CodeWisp 将 LSP 能力作为 Coding Agent 的代码智能层。

当前支持：

* Diagnostics
* Symbols
* Definition
* References
* Hover
* Language / Server Status

其中 Diagnostics 可以直接进入 Agent 的上下文：

```text
Code Modification
       ↓
LSP Diagnostics
       ↓
Agent observes errors
       ↓
Reasoning
       ↓
Code Repair
       ↓
Diagnostics again
```

当前以 Python + Pyright 为主要实践，并在 LSP 不可用时进行 graceful degradation。

---

## 🏗️ Architecture

CodeWisp 采用模块化分层设计。

```text
┌─────────────────────────────────────────┐
│                  CLI                    │
└───────────────────┬─────────────────────┘
                    │
┌───────────────────▼─────────────────────┐
│              AgentService               │
│        Session / Run / Workspace        │
└───────────────────┬─────────────────────┘
                    │
┌───────────────────▼─────────────────────┐
│               Agent Core                │
│                                         │
│  Context → Plan → AgentLoop → Events   │
└───────────┬───────────────┬─────────────┘
            │               │
     ┌──────▼──────┐ ┌──────▼──────────┐
     │ Tool System │ │ Permission      │
     │ Registry    │ │ Policy/Handler  │
     │ Executor    │ └─────────────────┘
     └──────┬──────┘
            │
   ┌────────┼────────┬────────┬─────────┐
   ▼        ▼        ▼        ▼         ▼
 File     Shell     LSP      Git      Change
 Tools    Tools     Tools    Tools    Tracking
                                     
┌─────────────────────────────────────────┐
│              Persistence                │
│       SQLite / Session / Run / Step     │
└─────────────────────────────────────────┘
```

核心设计原则：

* **AgentLoop 负责 Agent 决策循环，不负责业务持久化**
* **Tool 通过 Registry / Executor 统一管理**
* **Permission 与 Tool Execution 解耦**
* **Git、LSP、Snapshot 等能力作为独立 Domain Service**
* **CLI 与 FastAPI 共用 AgentService 和 Agent Core**
* **Conversation History 与 Workspace History 分离**
* **外部能力不可用时尽可能 graceful degradation**

---

## 🧱 Core Modules

```text
backend/app/
├── agent/          # Agent Loop / State / Events
├── tools/          # Tool / Registry / Executor
├── llm/            # LLM Client / Messages / Responses
├── context/        # Context / Plan / Memory
├── session/        # Session / Conversation
├── persistence/    # SQLite / Repository / Migration
├── permission/     # Permission Policy / Handler
├── changes/        # Snapshot / Diff / Revert
├── git/            # Git Domain Service / Git Tools
├── lsp/            # LSP Adapter / Diagnostics / Symbols
├── api/            # FastAPI Backend
└── cli/            # CLI Interface
```

---

## 🚀 Quick Start

### 1. Clone

```bash
git clone https://github.com/millionnn/CodeWisp.git
cd CodeWisp
```

### 2. Create Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install

```bash
pip install -e ".[dev]"
```

### 4. Configure LLM

```bash
cp .env.example .env
```

编辑 `.env`：

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=your_base_url
LLM_MODEL=your_model
```

### 5. Start CodeWisp

进入任意需要修改的代码仓库：

```bash
cd /path/to/your/project
codewisp
```

启动后可以使用：

```text
/help
/model
/context
/plan
/diff
/revert
/git
/lsp
```

---

## 🧪 Example

例如给 CodeWisp 一个真实的代码修复任务：

```text
Fix the failing tests in this project.
Do not modify the tests.
```

Agent 可以自主完成：

```text
Inspect project
      ↓
Understand failing tests
      ↓
Locate relevant implementation
      ↓
Edit source files
      ↓
Run tests
      ↓
Observe failure
      ↓
Analyze the new failure
      ↓
Perform another repair
      ↓
Run tests again
      ↓
LSP diagnostics
      ↓
Show diff
```

最终用户可以通过：

```text
/diff
```

检查 Agent 修改的代码，并通过：

```text
/revert
```

回滚本次任务产生的修改。

如果需要提交代码：

```text
/git status
/git diff
/git commit
```

Commit 前 CodeWisp 会展示 Commit Preview 并请求用户确认。

---

## 📊 Testing

CodeWisp 持续采用单元测试与回归测试验证核心模块，包括：

* Agent Loop
* Tool System
* Session
* Persistence
* Permission
* Context
* Snapshot / Diff / Revert
* Git
* LSP
* API

当前项目已完成 V0.1–V1.2 的持续迭代。

---

## 🛣️ Development Roadmap

```text
V0.1  Agent CLI
  ↓
V0.2  Tool System
  ↓
V0.3  Agent Loop
  ↓
V0.4  Coding Tools
  ↓
V0.5  Self-Correction
  ↓
V0.6  Session & Backend
  ↓
V0.7  Provider / Model
  ↓
V0.8  Permission & Live Runtime
  ↓
V0.9  Snapshot / Diff / Revert
  ↓
V1.0  Context / Plan / Memory
  ↓
V1.1  Git-Aware Workflow
  ↓
V1.2  LSP-Aware Coding Intelligence
```

---

## 🎯 Design Goal

CodeWisp 的目标不是简单地让 LLM “生成更多代码”，而是让模型真正进入软件工程执行环境：

> **Understand → Plan → Act → Observe → Repair → Verify → Review**

通过自主实现 Agent Runtime、Tool Execution、Context Management、Permission、Change Tracking、Git 和 LSP 等基础设施，CodeWisp 尝试构建一个能够在真实代码仓库中**执行任务、处理失败、验证结果并管理代码变更**的 Coding Agent。

---

