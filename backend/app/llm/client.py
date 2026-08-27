"""OpenAI 兼容的 LLM 客户端（不依赖任何 Agent 框架）。

从环境变量读取配置：
  LLM_API_KEY   — 必填（例如 DeepSeek API Key）
  LLM_BASE_URL  — 可选，默认 DeepSeek 兼容接口
  LLM_MODEL     — 可选，默认 deepseek-chat

本模块是可复用的「LLM 核心」，供 CLI（以及未来的 Web API）调用。
不得向 stdout 打印，也不得依赖 CLI I/O。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, OpenAI

from backend.app.llm.errors import ConfigError, LLMNetworkError, LLMRequestError
from backend.app.llm.messages import Conversation


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

    def chat(self, conversation: Conversation) -> str:
        """发送完整对话历史，返回助手文本内容。"""
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

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMRequestError("LLM 返回了无法解析的响应结构。") from exc

        if content is None or content == "":
            raise LLMRequestError("LLM 返回了空内容。")

        return content
