"""LLMResponse / ToolCall 领域对象测试。"""

from backend.app.llm.response import LLMResponse, ToolCall


def test_llm_response_text_helpers() -> None:
    response = LLMResponse(content="hello", finish_reason="stop")
    assert response.text == "hello"
    assert response.has_tool_calls is False


def test_llm_response_with_tool_calls() -> None:
    tc = ToolCall(id="1", name="calculator", arguments={"expression": "1+1"})
    response = LLMResponse(content=None, tool_calls=(tc,), finish_reason="tool_calls")
    assert response.text == ""
    assert response.has_tool_calls is True
    assert response.tool_calls[0].name == "calculator"
