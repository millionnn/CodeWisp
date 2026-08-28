# CodeWisp 需求说明

## 2.1 用户需求

用户面对一个已有的软件项目，希望直接用自然语言提出任务，例如：

- 帮我修复这个 Python 项目中的所有测试错误。
- 给这个项目增加一个 CSV 文件分析功能。
- 帮我找到登录失败的原因并修复它。

用户不需要手动告诉 Agent：

- 先打开哪个文件
- 再运行什么命令
- 再修改什么代码

而是由 Agent 自主决定。

## 三、核心功能需求

最终需求分为 8 个功能模块。

### FR-1：任务理解

用户输入自然语言任务，例如：

> Fix all bugs in this project and make all tests pass.

Agent 对任务进行分析，形成类似结构：

| 字段 | 示例 |
|------|------|
| Goal | 修复项目中的 Bug |
| Constraints | 保持现有接口 |
| Expected Result | 所有测试通过 |

### FR-2：任务规划

复杂任务不能直接开始乱改。Agent 可以先生成计划，例如：

```text
Plan
1. Inspect repository structure
2. Identify relevant modules
3. Run existing tests
4. Analyze failures
5. Modify source code
6. Run tests again
7. Fix remaining issues
8. Verify final result
```

### FR-3：代码仓库探索

Agent 必须能够自主了解项目。

核心工具：

- `list_files()`
- `read_file()`
- `search_code()`
- `find_files()`

示例流程：

1. 调用 `list_files(".")`，发现：

   ```text
   src/
   tests/
   README.md
   requirements.txt
   ```

2. 调用 `search_code("login")`，定位：

   ```text
   src/auth.py
   src/api/user.py
   tests/test_auth.py
   ```

### FR-4：代码修改

至少支持：

- `write_file()`
- `edit_file()`
- `apply_patch()`

特别推荐使用 **edit / patch**，而不是每次重写整个文件。

这样更符合真正 Coding Agent 的工作方式，也更容易展示修改前后的差异。

### FR-5：命令执行

Agent 能够执行：

```text
run_command("pytest")
run_command("python main.py")
```

然后获得 Observation，例如：

```text
FAILED tests/test_login.py
AssertionError:
expected True
got False
```

### FR-6：自主错误修复

这是最终项目最核心的高级能力之一：

```text
修改
 ↓
执行
 ↓
失败
 ↓
分析
 ↓
再次修改
 ↓
执行
 ↓
成功
```

即：**Self-Correction Loop**。

### FR-7：任务终止与验证

不能让 Agent 无限运行。最终需要设计终止状态，例如：

- Success
- Failure
- Max Steps
- Repeated Error
- No Progress
- Critical Error

逻辑示意：

```text
if tests_passed:
    SUCCESS
elif step_count > max_steps:
    STOP
elif repeated_error:
    STOP
else:
    CONTINUE
```

### FR-8：安全执行

Agent 能执行 Shell 是非常危险的，因此增加安全检查：

```text
Tool Call
    ↓
Safety Check
    ↓
┌───────────────┐
│ Risk Analysis │
└───────────────┘
   ↓       ↓
 Safe     Dangerous
   ↓          ↓
Execute    Block/Confirm
```

例如：

- `pytest` → 自动执行
- `rm -rf ...` → `HIGH RISK`，Execution blocked

## 四、非功能需求

这部分很重要，面试时评委很可能提问。

### 4.1 可解释性

Agent 每一步都能看到：

- Reasoning
- Tool
- Arguments
- Observation

最终形成 **Execution Trace**。

### 4.2 可扩展性

未来可以很容易增加：

- Git Tool
- Web Search Tool
- LSP Tool
- Database Tool
- Docker Tool

而不用修改 Agent Core。因此设计：

```text
Tool Interface
       ↓
Tool Registry
       ↓
Tool Executor
```

### 4.3 鲁棒性

需要处理：

- API 错误
- Tool 参数错误
- 文件不存在
- 命令执行失败
- 超时
- LLM 返回非法格式
- Agent 无限循环

### 4.4 安全性

至少保证：

- 工作目录隔离
- Shell 命令风险控制
- 禁止访问 workspace 外部敏感文件
- 高风险操作拦截
- 执行超时
