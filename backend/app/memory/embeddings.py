"""EmbeddingProvider 抽象：不写死具体厂商。"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def batch_embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """确定性本地 embedding（测试/离线默认）。

    将文本哈希展开为固定维伪向量并 L2 归一化；无外部 API。
    """

    def __init__(self, *, dimensions: int = 64, model_name: str = "hash-embed-v1") -> None:
        if dimensions < 8:
            raise ValueError("dimensions 必须 >= 8")
        self._dim = dimensions
        self._name = model_name

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def dimensions(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        raw = (text or "").encode("utf-8")
        digest = hashlib.sha256(raw).digest()
        # 扩展到所需字节
        buf = digest
        while len(buf) < self._dim * 4:
            buf += hashlib.sha256(buf).digest()
        vals: list[float] = []
        for i in range(self._dim):
            chunk = buf[i * 4 : i * 4 + 4]
            # 有符号归一到 [-1, 1]
            n = struct.unpack(">I", chunk)[0]
            vals.append((n / 0xFFFFFFFF) * 2.0 - 1.0)
        # 混入 token 级特征：提高短文本可区分度
        tokens = (text or "").lower().split()
        for i, tok in enumerate(tokens[: self._dim]):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
            vals[i % self._dim] += ((h % 1000) / 1000.0) * 0.15
        return _l2_normalize(vals)

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class FailingEmbeddingProvider:
    """测试用：始终失败。"""

    def __init__(self, message: str = "embedding unavailable") -> None:
        self._message = message

    @property
    def model_name(self) -> str:
        return "failing"

    @property
    def dimensions(self) -> int:
        return 8

    def embed(self, text: str) -> list[float]:
        raise RuntimeError(self._message)

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError(self._message)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _l2_normalize(vals: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vals))
    if norm == 0:
        return vals
    return [v / norm for v in vals]


def default_embedding_provider() -> EmbeddingProvider:
    """默认本地确定性 provider；不读取 API key。"""
    return HashEmbeddingProvider()
