"""tools 人工验证入口测试（不调用 LLM）。"""

from __future__ import annotations

import json

from backend.app.tools.__main__ import main


def test_tools_cli_list(capsys) -> None:
    code = main(["list"])
    captured = capsys.readouterr()
    assert code == 0
    assert "calculator" in captured.out
    assert "get_current_time" in captured.out


def test_tools_cli_run_calculator(capsys) -> None:
    code = main(["run", "calculator", json.dumps({"expression": "12 * 8 + 5"})])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["success"] is True
    assert payload["output"] == 101


def test_tools_cli_unknown_tool(capsys) -> None:
    code = main(["run", "missing", "{}"])
    captured = capsys.readouterr()
    assert code == 2
    payload = json.loads(captured.out)
    assert payload["success"] is False
