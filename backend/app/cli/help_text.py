"""CodeWisp 帮助文案。"""

HELP_TEXT = """\
[bold cyan]CodeWisp Commands[/]

[bold]Session[/]
  [cyan]/new[/] [title] [--provider-id P] [--model-id M]
                       Create a new session
  [cyan]/new --model[/] <id>    Create session with model (unique id)
  [cyan]/sessions[/]            List sessions
  [cyan]/use[/]                 Interactive session picker (↑↓ Enter)
  [cyan]/use[/] <id>            Switch session
  [cyan]/session[/]             Show current session
  [cyan]/history[/]             Show conversation history
  [cyan]/delete[/]              Interactive delete picker (↑↓ Enter)
  [cyan]/delete[/] <id>         Delete a session (/rm)

[bold]Model[/]
  [cyan]/providers[/]           List available providers
  [cyan]/models[/]              List available models
  [cyan]/model[/]               Interactive model picker (↑↓ Enter)
  [cyan]/model[/] <id>          Switch model (unique model_id)
  [cyan]/model[/] <provider> <model>
                       Switch provider + model

[bold]Changes[/]
  [cyan]/git[/]                 Git repository status
  [cyan]/git status[/]          Show branch and working tree
  [cyan]/git diff[/] [path]     Show Git diff
  [cyan]/git log[/] [limit]     Show recent commits
  [cyan]/git branch[/]          List branches
  [cyan]/git commit[/] <msg>    Commit (asks permission)
  [cyan]/diff[/]                Diff latest run (Rich +/−)
  [cyan]/diff[/] step <id>      Diff one AgentStep
  [cyan]/diff[/] run <id>       Diff one AgentRun
  [cyan]/revert[/]              Pick step/run then revert (asks permission)
  [cyan]/revert[/] step <id>    Revert one AgentStep
  [cyan]/revert[/] run <id>     Revert one AgentRun

[bold]Context[/]
  [cyan]/context[/]             Hierarchical context budget breakdown
  [cyan]/context status[/]      Same as /context
  [cyan]/context compact[/]     Manual compaction + checkpoint
  [cyan]/context memory[/]      List durable memories
  [cyan]/plan[/]                Show current Plan (✓ ● ○ ✗)
  [cyan]/plan show[/]           Same as /plan
  [cyan]/plan refresh[/]        Rebuild plan via Planner
  [dim]During agent runs, Plan updates live from plan_* events; Tool Trace stays separate.[/]

[bold]Memory[/]
  [cyan]/memory[/]              Memory help
  [cyan]/memory search[/] <q>   Hybrid semantic + keyword search
  [cyan]/memory index[/]        Index workspace (incremental)
  [cyan]/memory rebuild[/]      Rebuild semantic index
  [cyan]/memory stats[/]        Index statistics

[bold]Runtime[/]
  [cyan]/status[/]              Show current runtime status

[bold]General[/]
  [cyan]/help[/]                Show help
  [cyan]/exit[/]                Exit CodeWisp

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
