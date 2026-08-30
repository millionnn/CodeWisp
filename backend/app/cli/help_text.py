"""CodeWisp 帮助文案。"""

HELP_TEXT = """\
[bold cyan]CodeWisp Commands[/]

[bold]Session[/]
  [cyan]/new[/] [title] [--provider-id P] [--model-id M]
                       Create a new session
  [cyan]/new --model[/] <id>    Create session with model (unique id)
  [cyan]/sessions[/]            List sessions
  [cyan]/use[/] <id>            Switch session
  [cyan]/session[/]             Show current session
  [cyan]/history[/]             Show conversation history
  [cyan]/delete[/] <id>         Delete a session (/rm)

[bold]Model[/]
  [cyan]/providers[/]           List available providers
  [cyan]/models[/]              List available models
  [cyan]/model[/]               Show current model
  [cyan]/model[/] <id>          Switch model (unique model_id)
  [cyan]/model[/] <provider> <model>
                       Switch provider + model

[bold]Runtime[/]
  [cyan]/status[/]              Show current runtime status

[bold]General[/]
  [cyan]/help[/]                Show help
  [cyan]/exit[/]                Exit CodeWisp

[dim]Theme: CODEWISP_THEME=default|mono · NO_COLOR=1 disables color[/]
"""

HELP_TEXT_PLAIN = """\
CodeWisp Commands

Session:
  /new [title] [--provider-id P] [--model-id M]
                       Create a new session
  /new --model <id>    Create session with model (unique id)
  /sessions            List sessions
  /use <id>            Switch session
  /session             Show current session
  /history             Show conversation history
  /delete <id>         Delete a session (/rm)

Model:
  /providers           List available providers
  /models              List available models
  /model               Show current model
  /model <id>          Switch model (unique model_id)
  /model <provider> <model>
                       Switch provider + model

Runtime:
  /status              Show current runtime status

General:
  /help                Show help
  /exit                Exit CodeWisp
"""
