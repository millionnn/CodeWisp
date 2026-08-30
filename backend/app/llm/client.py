"""OpenAI 兼容的 LLM 客户端（不依赖任何 Agent 框架）。

从环境变量读取配置：
  LLM_API_KEY   — 必填（例如 DeepSeek API Key）
  LLM_BASE_URL  — 可选，默认 DeepSeek 兼容接口
  LLM_MODEL     — 可选，默认 deepseek-chat

本模块是可复用的「LLM 核心」，供 CLI / AgentLoop 调用。
只负责 Model I/O，不执行工具。

V0.7：逻辑上属于 OpenAI-compatible Provider Runtime
（见 ``backend.app.providers.openai_compatible``）；
Provider/Model Registry 只描述身份，Phase 1 不按 Session 切换本客户端。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, OpenAI

from backend.app.llm.errors import ConfigError, LLMNetworkError, LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

# 无真实 stream 时（测试 Scripted 客户端）模拟推送的块大小
_FALLBACK_DELTA_CHARS = 16


@dataclass(frozen=True)
class LLMConfig:
    """已解析的 LLM 连接配置。"""

    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> LLMConfig:
        """从环境变量加载配置；非法时抛出 ConfigError。"""
        api_key = (os.getenv("LLM_API_KEY") or "").strip()
        if not api_key:
            raise ConfigError(
                "未设置 LLM_API_KEY。"
                "请复制 .env.example 为 .env 并填入你的 API Key。"
            )

        base_url = (os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL).strip()
        if not base_url:
            raise ConfigError("LLM_BASE_URL 为空，请填写有效的 API 地址。")

        model = (os.getenv("LLM_MODEL") or DEFAULT_MODEL).strip()
        if not model:
            raise ConfigError("LLM_MODEL 为空，请填写有效的模型名称。")

        return cls(api_key=api_key, base_url=base_url, model=model)


class LLMClient:
    """对 OpenAI 兼容 Chat Completions API 的薄封装。"""

    def __init__(self, config: LLMConfig | None = None, *, client: OpenAI | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self._client = client or OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """发送对话历史，可选附带 tools schema；返回 LLMResponse。"""
        if len(conversation) == 0:
            raise ConfigError("对话为空，无法向 LLM 发送请求。")

        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": conversation.to_api_messages(),
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"

        try:
            response = self._client.chat.completions.create(**request)
        except AuthenticationError as exc:
            raise LLMRequestError(
                "LLM 鉴权失败：请检查当前 Provider 对应的 API Key 是否有效"
                "（DeepSeek→LLM_API_KEY；硅基流动→SILICONFLOW_API_KEY；"
                "OpenAI→OPENAI_API_KEY）。"
            ) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMNetworkError(
                "无法连接 LLM API，请检查网络与 LLM_BASE_URL。"
            ) from exc
        except APIError as exc:
            raise LLMRequestError(f"LLM API 请求失败：{exc.message}") from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMRequestError(f"LLM 客户端发生未预期错误：{exc}") from exc

        return self._to_domain_response(response)

    def chat_stream(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
        on_text_delta: Callable[[str], None] | None = None,
        on_text_discard: Callable[[], None] | None = None,
    ) -> LLMResponse:
        """流式调用。

        - 尚未出现 tool_call 时：实时 ``on_text_delta``（真流式）
        - 一旦出现 tool_call：调用 ``on_text_discard`` 清掉已推送的推测正文
        - 无可用 SDK client 时回退 ``chat()`` + 分块重放
        """
        if len(conversation) == 0:
            raise ConfigError("对话为空，无法向 LLM 发送请求。")

        if self._client is None:
            response = self.chat(conversation, tools=tools)
            _replay_text_deltas(response, on_text_delta)
            return response

        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": conversation.to_api_messages(),
            "stream": True,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"

        try:
            stream = self._client.chat.completions.create(**request)
        except AuthenticationError as exc:
            raise LLMRequestError(
                "LLM 鉴权失败：请检查当前 Provider 对应的 API Key 是否有效"
                "（DeepSeek→LLM_API_KEY；硅基流动→SILICONFLOW_API_KEY；"
                "OpenAI→OPENAI_API_KEY）。"
            ) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMNetworkError(
                "无法连接 LLM API，请检查网络与 LLM_BASE_URL。"
            ) from exc
        except APIError as exc:
            raise LLMRequestError(f"LLM API 请求失败：{exc.message}") from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMRequestError(f"LLM 客户端发生未预期错误：{exc}") from exc

        return self._consume_stream(
            stream,
            on_text_delta=on_text_delta,
            on_text_discard=on_text_discard,
        )

    def _consume_stream(
        self,
        stream: Any,
        *,
        on_text_delta: Callable[[str], None] | None,
        on_text_discard: Callable[[], None] | None = None,
    ) -> LLMResponse:
        content_parts: list[str] = []
        tool_acc: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        saw_tool_calls = False
        emitted_text = False

        try:
            for chunk in stream:
                if not getattr(chunk, "choices", None):
                    continue
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                if delta is None:
                    continue

                raw_tools = getattr(delta, "tool_calls", None) or []
                if raw_tools:
                    if not saw_tool_calls and emitted_text and on_text_discard is not None:
                        on_text_discard()
                        emitted_text = False
                    saw_tool_calls = True
                    for tc_delta in raw_tools:
                        idx = int(getattr(tc_delta, "index", 0) or 0)
                        slot = tool_acc.setdefault(
                            idx,
                            {"id": "", "name": "", "arguments": ""},
                        )
                        if getattr(tc_delta, "id", None):
                            slot["id"] = str(tc_delta.id)
                        function = getattr(tc_delta, "function", None)
                        if function is not None:
                            if getattr(function, "name", None):
                                slot["name"] = str(function.name)
                            if getattr(function, "arguments", None):
                                slot["arguments"] += str(function.arguments)

                piece = getattr(delta, "content", None)
                if piece:
                    content_parts.append(piece)
                    # 真流式：未见 tool_call 前实时推送；出现工具后不再推正文
                    if on_text_delta is not None and not saw_tool_calls:
                        on_text_delta(piece)
                        emitted_text = True
        except LLMRequestError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LLMRequestError(f"LLM 流式响应解析失败：{exc}") from exc

        content = "".join(content_parts) if content_parts else None
        tool_calls = tuple(
            _map_tool_call_from_parts(
                tool_acc[i]["id"],
                tool_acc[i]["name"],
                tool_acc[i]["arguments"],
            )
            for i in sorted(tool_acc)
            if tool_acc[i]["name"] or tool_acc[i]["arguments"]
        )

        if (content is None or content == "") and not tool_calls:
            raise LLMRequestError("LLM 返回了空内容。")

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw_response=None,
        )

    @staticmethod
    def _to_domain_response(response: Any) -> LLMResponse:
        """将厂商 SDK 响应映射为 LLMResponse。"""
        try:
            choice = response.choices[0]
            message = choice.message
            content = message.content
            finish_reason = getattr(choice, "finish_reason", None)
            raw_tool_calls = getattr(message, "tool_calls", None) or []
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMRequestError("LLM 返回了无法解析的响应结构。") from exc

        tool_calls = tuple(_map_tool_call(tc) for tc in raw_tool_calls)

        if (content is None or content == "") and not tool_calls:
            raise LLMRequestError("LLM 返回了空内容。")

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw_response=response,
        )


def _replay_text_deltas(
    response: LLMResponse,
    on_text_delta: Callable[[str], None] | None,
) -> None:
    if on_text_delta is None or response.has_tool_calls:
        return
    text = response.text
    if not text:
        return
    size = _FALLBACK_DELTA_CHARS
    for i in range(0, len(text), size):
        on_text_delta(text[i : i + size])


def _map_tool_call_from_parts(call_id: str, name: str, arguments_raw: str) -> ToolCall:
    arguments, raw, parse_error = _parse_tool_arguments(arguments_raw or "")
    return ToolCall(
        id=call_id,
        name=name,
        arguments=arguments,
        arguments_raw=raw,
        parse_error=parse_error,
    )


def _map_tool_call(tc: Any) -> ToolCall:
    function = getattr(tc, "function", None)
    raw_args = getattr(function, "arguments", None)
    arguments, arguments_raw, parse_error = _parse_tool_arguments(raw_args)
    return ToolCall(
        id=str(getattr(tc, "id", "") or ""),
        name=str(getattr(function, "name", "") or ""),
        arguments=arguments,
        arguments_raw=arguments_raw,
        parse_error=parse_error,
    )


def _parse_tool_arguments(
    raw: Any,
) -> tuple[dict[str, Any], str | None, str | None]:
    """解析 tool call arguments，返回 (dict, raw_str, parse_error)。"""
    if raw is None or raw == "":
        return {}, None if raw is None else "", None
    if isinstance(raw, dict):
        return raw, json.dumps(raw, ensure_ascii=False), None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {}, raw, f"JSON 解析失败：{exc.msg}"
        if not isinstance(parsed, dict):
            return {}, raw, "工具参数 JSON 必须是对象。"
        return parsed, raw, None
    return {}, str(raw), "不支持的工具参数类型。"
