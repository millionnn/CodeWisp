"""Credential 抽象：Phase 1 仅支持环境变量 / .env。

禁止将 api_key 写入 Session / Provider / Model / SQLite。
未来可替换为其它 CredentialSource，而不改 Domain。
"""
#llm身份信息，如api key等
from __future__ import annotations

import os
from typing import Protocol

from backend.app.llm.errors import ConfigError


#凭据来源
class CredentialSource(Protocol):
    """可替换的凭据来源（Phase 1：环境变量）。"""

    def get_api_key(self) -> str:
        """返回非空 API Key；缺失时抛出 ConfigError。"""


#目前phase1从环境变量读
class EnvCredentialSource:
    """从环境变量读取 API Key（由 dotenv / 进程环境注入）。"""

    def __init__(self, env_var: str = "LLM_API_KEY") -> None:
        name = (env_var or "").strip()
        if not name:
            raise ConfigError("credential env_var 不能为空")
        self._env_var = name

    @property
    def env_var(self) -> str:
        return self._env_var

    def get_api_key(self) -> str:
        api_key = (os.getenv(self._env_var) or "").strip()
        if not api_key:
            raise ConfigError(
                f"未设置 {self._env_var}。"
                "请复制 .env.example 为 .env 并填入你的 API Key。"
            )
        return api_key
