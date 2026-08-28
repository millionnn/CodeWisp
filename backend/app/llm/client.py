"""OpenAI 兼容的 LLM 客户端（不依赖任何 Agent 框架）。

从环境变量读取配置：
  LLM_API_KEY   — 必填（例如 DeepSeek API Key）
  LLM_BASE_URL  — 可选，默认 DeepSeek 兼容接口
  LLM_MODEL     — 可选，默认 deepseek-chat

本模块是可复用的「LLM 核心」，供 CLI（以及未来的 Web API）调用。
不得向 stdout 打印，也不得依赖 CLI I/O。

对外返回领域对象 LLMResponse，不向上层传播 SDK 的 choices/message 结构。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, OpenAI

from backend.app.llm.errors import ConfigError, LLMNetworkError, LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall


# DeepSeek 提供 OpenAI 兼容的 Chat Completions 接口。
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


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
        # client 可注入，便于测试时 mock，无需真实网络。
        self._client = client or OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    def chat(self, conversation: Conversation) -> LLMResponse:
        """发送完整对话历史，返回领域侧 LLMResponse。"""
        if len(conversation) == 0:
            raise ConfigError("对话为空，无法向 LLM 发送请求。")

        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=conversation.to_api_messages(),  # type: ignore[arg-type]
            )
        except AuthenticationError as exc:
            raise LLMRequestError(
                "LLM 鉴权失败，请检查 LLM_API_KEY 是否有效。"
            ) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMNetworkError(
                "无法连接 LLM API，请检查网络与 LLM_BASE_URL。"
            ) from exc
        except APIError as exc:
            raise LLMRequestError(f"LLM API 请求失败：{exc.message}") from exc
        except Exception as exc:  # noqa: BLE001 — 边界：将未知 SDK 错误映射为领域异常
            raise LLMRequestError(f"LLM 客户端发生未预期错误：{exc}") from exc

        return self._to_domain_response(response)

    @staticmethod
    def _to_domain_response(response: Any) -> LLMResponse:
        """将厂商 SDK 响应映射为 LLMResponse（SDK 细节止步于此）。"""
        try:
            choice = response.choices[0]
            message = choice.message
            content = message.content
            finish_reason = getattr(choice, "finish_reason", None)
            raw_tool_calls = getattr(message, "tool_calls", None) or []
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMRequestError("LLM 返回了无法解析的响应结构。") from exc

        tool_calls = tuple(
            ToolCall(
                id=str(getattr(tc, "id", "") or ""),
                name=str(getattr(getattr(tc, "function", None), "name", "") or ""),
                arguments=_parse_tool_arguments(
                    getattr(getattr(tc, "function", None), "arguments", None)
                ),
            )
            for tc in raw_tool_calls
        )

        # 纯文本模式下仍要求有内容；若未来带 tool_calls，允许 content 为空。
        if (content is None or content == "") and not tool_calls:
            raise LLMRequestError("LLM 返回了空内容。")

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw_response=response,
        )


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    """解析 tool call 的 arguments（通常是 JSON 字符串）。"""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
