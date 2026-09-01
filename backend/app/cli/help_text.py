"""CodeWisp 帮助文案。"""

HELP_TEXT = """\
[bold #2dd4bf]✦ CodeWisp Commands[/]

[bold #e2e8f0]Session[/]
  [bold #67e8f9]/new[/] [title] [--provider-id P] [--model-id M]
                       Create a new session
  [bold #67e8f9]/new --model[/] <id>    Create session with model (unique id)
  [bold #67e8f9]/sessions[/]            List sessions
  [bold #67e8f9]/use[/]                 Interactive session picker (↑↓ Enter)
  [bold #67e8f9]/use[/] <id>            Switch session
  [bold #67e8f9]/session[/]             Show current session
  [bold #67e8f9]/history[/]             Show conversation history
  [bold #67e8f9]/delete[/]              Interactive delete picker (↑↓ Enter)
  [bold #67e8f9]/delete[/] <id>         Delete a session (/rm)

[bold #e2e8f0]Model[/]
  [bold #67e8f9]/providers[/]           List available providers
  [bold #67e8f9]/models[/]              List available models
  [bold #67e8f9]/model[/]               Interactive model picker (↑↓ Enter)
  [bold #67e8f9]/model[/] <id>          Switch model (unique model_id)
  [bold #67e8f9]/model[/] <provider> <model>
                       Switch provider + model

[bold #e2e8f0]Changes[/]
  [bold #67e8f9]/git[/]                 Git repository status
  [bold #67e8f9]/git status[/]          Show branch and working tree
  [bold #67e8f9]/git diff[/] [path]     Show Git diff
  [bold #67e8f9]/git log[/] [limit]     Show recent commits
  [bold #67e8f9]/git branch[/]          List branches
  [bold #67e8f9]/git commit[/] <msg>    Commit (asks permission)
  [bold #67e8f9]/diff[/]                Diff latest run (Rich +/−)
  [bold #67e8f9]/diff[/] step <id>      Diff one AgentStep
  [bold #67e8f9]/diff[/] run <id>       Diff one AgentRun
  [bold #67e8f9]/revert[/]              Pick step/run then revert (asks permission)
  [bold #67e8f9]/revert[/] step <id>    Revert one AgentStep
  [bold #67e8f9]/revert[/] run <id>     Revert one AgentRun

[bold #e2e8f0]Context[/]
  [bold #67e8f9]/context[/]             Hierarchical context budget breakdown
  [bold #67e8f9]/context status[/]      Same as /context
  [bold #67e8f9]/context compact[/]     Manual compaction + checkpoint
  [bold #67e8f9]/context memory[/]      List durable memories
  [bold #67e8f9]/plan[/]                Show current Plan (✓ ● ○ ✗)
  [bold #67e8f9]/plan show[/]           Same as /plan
  [bold #67e8f9]/plan refresh[/]        Rebuild plan via Planner
  [dim]During agent runs, Plan updates live from plan_* events; Tool Trace stays separate.[/]

[bold #e2e8f0]Code Intelligence[/]
  [bold #67e8f9]/lsp[/]                 LSP status
  [bold #67e8f9]/lsp status[/]          Language server availability
  [bold #67e8f9]/lsp diagnostics[/] [path]
                       Show diagnostics
  [bold #67e8f9]/lsp symbols[/] <path>  Document symbols
  [bold #67e8f9]/lsp definition[/] <path> <line> <char>
  [bold #67e8f9]/lsp references[/] <path> <line> <char>

[bold #e2e8f0]MCP[/]
  [bold #67e8f9]/mcp[/]                 MCP servers status
  [bold #67e8f9]/mcp servers[/]         List configured MCP servers
  [bold #67e8f9]/mcp tools[/]           List discovered MCP tools
  [bold #67e8f9]/mcp connect[/] <id>    Connect a server
  [bold #67e8f9]/mcp disconnect[/] <id> Disconnect a server
  [bold #67e8f9]/mcp reload[/]          Reload config and reconnect

[bold #e2e8f0]Memory[/]
  [bold #67e8f9]/memory[/]              Memory help
  [bold #67e8f9]/memory search[/] <q>   Hybrid semantic + keyword search
  [bold #67e8f9]/memory index[/]        Index workspace (incremental)
  [bold #67e8f9]/memory rebuild[/]      Rebuild semantic index
  [bold #67e8f9]/memory stats[/]        Index statistics

[bold #e2e8f0]Runtime[/]
  [bold #67e8f9]/status[/]              Show current runtime status

[bold #e2e8f0]General[/]
  [bold #67e8f9]/help[/]                Show help
  [bold #67e8f9]/exit[/]                Exit CodeWisp

[dim]Theme: CODEWISP_THEME=default|mono · NO_COLOR=1 disables color[/]
[dim]Input: ↑↓←→ + Enter to select · Backspace works with CJK[/]
"""

HELP_TEXT_PLAIN = """\
CodeWisp Commands

Session:
  /new [title] [--provider-id P --model-id M]
                       Create a new session
  /new --model <id>    Create session with model (unique id)
  /sessions            List sessions
  /use                 Interactive session picker (↑↓ Enter)
  /use <id>            Switch session
  /session             Show current session
  /history             Show conversation history
  /delete              Interactive delete picker (↑↓ Enter)
  /delete <id>         Delete a session (/rm)

Model:
  /providers           List available providers
  /models              List available models
  /model               Interactive model picker (↑↓ Enter)
  /model <id>          Switch model (unique model_id)
  /model <provider> <model>
                       Switch provider + model

Changes:
  /diff                Diff latest run (Rich +/−)
  /diff step <id>      Diff one AgentStep
  /diff run <id>       Diff one AgentRun
  /revert              Pick step/run then revert (asks permission)
  /revert step <id>    Revert one AgentStep
  /revert run <id>     Revert one AgentRun

Context:
  /context             Hierarchical context budget breakdown
  /context status      Same as /context
  /context compact     Manual compaction + checkpoint
  /context memory      List durable memories
  /plan                Show current Plan (✓ ● ○ ✗)
  /plan show           Same as /plan
  /plan refresh        Rebuild plan via Planner
  During agent runs, Plan updates live from plan_* events; Tool Trace stays separate.

MCP:
  /mcp                 MCP servers status
  /mcp servers         List configured MCP servers
  /mcp tools           List discovered MCP tools
  /mcp connect <id>    Connect a server
  /mcp disconnect <id> Disconnect a server
  /mcp reload          Reload config and reconnect

Memory:
  /memory              Memory help
  /memory search <q>   Hybrid semantic + keyword search
  /memory index        Index workspace (incremental)
  /memory rebuild      Rebuild semantic index
  /memory stats        Index statistics

Runtime:
  /status              Show current runtime status

General:
  /help                Show help
  /exit                Exit CodeWisp
"""
