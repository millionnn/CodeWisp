"""CLI 帮助文案。"""

HELP_TEXT = """\
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
