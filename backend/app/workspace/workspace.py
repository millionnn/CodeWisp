"""Workspace：Agent 所服务的「目标仓库」的安全 FS 门面。

重要语义：
- Workspace.root = 用户打开/绑定的那个项目目录（target project），不是 CodeWisp 自身源码树。
- CodeWisp 仓库根只是宿主程序所在位置；用本仓库自测时，只是把目标目录临时指到这里。
- list / glob / read / search / write_text / replace_text 都对该目标根目录操作，并统一做路径边界检查。

Coding Tools 应通过本模块访问目标仓库，禁止各自重复实现路径校验或直接 open()。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

from backend.app.workspace.errors import PathOutsideWorkspaceError, WorkspaceIOError

# 遍历时默认跳过的目录名
DEFAULT_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        ".idea",
        ".vscode",
        "dist",
        "build",
        ".tox",
        ".eggs",
    }
)

DEFAULT_MAX_READ_BYTES = 100_000 # 最大读取字节数
DEFAULT_MAX_SEARCH_RESULTS = 50 # 最大搜索结果数
DEFAULT_MAX_GLOB_RESULTS = 200 # 最大 glob 结果数
DEFAULT_MAX_LIST_ENTRIES = 500 # 最大列表条目数


class Workspace:
    """目标项目工作区：以 root 为边界的安全 FS 视图（可注入，非全局单例）。

    V0.4-A：只读 list/glob/read/search。
    V0.4-B：write_text / replace_text（原子写入 + 确定性替换）。
    """

    def __init__(self, root: str | Path) -> None:
        resolved = Path(root).expanduser().resolve()
        if not resolved.exists():
            raise WorkspaceIOError(f"workspace 根目录不存在：{resolved}")
        if not resolved.is_dir():
            raise WorkspaceIOError(f"workspace 根目录不是文件夹：{resolved}")
        self._root = resolved

    @property
    def root(self) -> Path:
        return self._root

# 将用户路径解析为绝对路径，并确保位于 workspace 内
    def resolve_path(self, user_path: str | Path | None = None) -> Path:
        """将用户路径解析为绝对路径，并确保位于 workspace 内。

        使用 Path.resolve()（跟随符号链接），再用 is_relative_to 做边界检查，
        避免简单 startswith 被绕过。
        """
        raw = "." if user_path is None or str(user_path).strip() == "" else str(user_path)
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = self._root / candidate
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            raise WorkspaceIOError(f"无法解析路径：{raw}（{exc}）") from exc

        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise PathOutsideWorkspaceError(
                f"路径超出 workspace 边界：{raw} → {resolved}"
            ) from exc
        return resolved

# 将路径转换为相对路径，如果转换失败则返回原始路径
    def relative_to_root(self, path: Path) -> str:
        """返回相对 workspace root 的 POSIX 风格路径。"""
        return path.resolve().relative_to(self._root).as_posix()

# 列目录，默认只看一层，可加深；跳过 .git、node_modules 等
    def list(
        self,
        path: str | Path = ".",
        *,
        max_depth: int = 1,
        max_entries: int = DEFAULT_MAX_LIST_ENTRIES,
    ) -> list[dict[str, Any]]:
        """列出目录条目（默认仅一层，不整库递归）。"""
        if max_depth < 1:
            raise WorkspaceIOError("max_depth 必须 >= 1")

        target = self.resolve_path(path)
        if not target.exists():
            raise WorkspaceIOError(f"路径不存在：{self._safe_rel(target)}")
        if not target.is_dir():
            raise WorkspaceIOError(f"不是目录：{self._safe_rel(target)}")

        entries: list[dict[str, Any]] = []

        def walk(current: Path, depth: int) -> None:
            if len(entries) >= max_entries or depth > max_depth:
                return
            try:
                children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            except OSError as exc:
                raise WorkspaceIOError(f"无法列出目录：{exc}") from exc

            for child in children:
                if child.name in DEFAULT_SKIP_DIRS:
                    continue
                try:
                    resolved = child.resolve()
                    resolved.relative_to(self._root)
                except (OSError, ValueError):
                    continue

                if resolved.is_dir():
                    entries.append({"path": self.relative_to_root(resolved), "type": "directory"})
                    if depth < max_depth:
                        walk(resolved, depth + 1)
                elif resolved.is_file():
                    entries.append({"path": self.relative_to_root(resolved), "type": "file"})

                if len(entries) >= max_entries:
                    return

        walk(target, 1)
        return entries

    # 辅助方法，将路径转换为相对路径，如果转换失败则返回原始路径
    def _safe_rel(self, path: Path) -> str:
        try:
            return self.relative_to_root(path)
        except ValueError:
            return str(path)

# 按模式找文件，如 **/*.py、**/*.ts（不限语言）
    def glob(
        self,
        pattern: str,
        *,
        path: str | Path = ".",
        max_results: int = DEFAULT_MAX_GLOB_RESULTS,
    ) -> list[str]:
        """按 glob 模式查找文件（相对 workspace 或指定子目录）。"""
        text = (pattern or "").strip()
        if not text:
            raise WorkspaceIOError("glob pattern 不能为空。")

        base = self.resolve_path(path)
        if not base.exists():
            raise WorkspaceIOError(f"路径不存在：{self.relative_to_root(base)}")
        if not base.is_dir():
            raise WorkspaceIOError(f"不是目录：{self.relative_to_root(base)}")

        matches: list[str] = []
        # Path.glob 支持 **；过滤到仅文件且仍在边界内
        for found in base.glob(text):
            try:
                resolved = found.resolve()
                resolved.relative_to(self._root)
            except (OSError, ValueError):
                continue
            if not resolved.is_file():
                continue
            # 跳过位于 skip dirs 下的匹配
            if any(part in DEFAULT_SKIP_DIRS for part in resolved.parts):
                continue
            matches.append(self.relative_to_root(resolved))
            if len(matches) >= max_results:
                break
        return sorted(matches)

# 读 UTF-8 文本；可按行；二进制/过大文件会报错
    def read(
        self,
        path: str | Path,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
        max_bytes: int = DEFAULT_MAX_READ_BYTES,
    ) -> dict[str, Any]:
        """读取文本文件；支持行范围。二进制/超大文件返回结构化错误。"""
        target = self.resolve_path(path)
        if not target.exists():
            raise WorkspaceIOError(f"文件不存在：{path}")
        if not target.is_file():
            raise WorkspaceIOError(f"不是文件：{self.relative_to_root(target)}")

        size = target.stat().st_size
        if start_line is None and end_line is None and size > max_bytes:
            raise WorkspaceIOError(
                f"文件过大（{size} bytes > {max_bytes}）。"
                "请使用 start_line/end_line 分段读取。"
            )

        raw = target.read_bytes()
        if b"\x00" in raw[:8192]:
            raise WorkspaceIOError(f"拒绝读取二进制文件：{self.relative_to_root(target)}")

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceIOError(
                f"无法以 UTF-8 解码：{self.relative_to_root(target)}"
            ) from exc

        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        s = 1 if start_line is None else start_line
        e = total_lines if end_line is None else end_line
        if s < 1 or e < 1 or s > e:
            raise WorkspaceIOError("非法的行范围：要求 start_line/end_line >= 1 且 start <= end。")
        if s > total_lines:
            raise WorkspaceIOError(f"start_line 超出文件行数（共 {total_lines} 行）。")

        e = min(e, total_lines)
        sliced = lines[s - 1 : e]
        content = "".join(sliced)
        # 行范围结果仍受 max_bytes 约束
        truncated = False
        if len(content.encode("utf-8")) > max_bytes:
            # 按字节截断（尽量保持 UTF-8）
            encoded = content.encode("utf-8")[:max_bytes]
            content = encoded.decode("utf-8", errors="ignore")
            truncated = True

        return {
            "path": self.relative_to_root(target),
            "content": content,
            "start_line": s,
            "end_line": e,
            "total_lines": total_lines,
            "truncated": truncated,
        }

#在文本文件里按子串搜内容，返回文件、行号、那一行
    def search(
        self,
        query: str,
        *,
        path: str | Path = ".",
        max_results: int = DEFAULT_MAX_SEARCH_RESULTS,
    ) -> list[dict[str, Any]]:
        """在文本文件中搜索 query，返回 file/line/match。"""
        q = query if query is not None else ""
        if q == "":
            raise WorkspaceIOError("search query 不能为空。")

        base = self.resolve_path(path)
        if not base.exists():
            raise WorkspaceIOError(f"路径不存在：{path}")

        hits: list[dict[str, Any]] = []
        files = self._iter_text_files(base)
        for file_path in files:
            try:
                raw = file_path.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:8192]:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            for idx, line in enumerate(text.splitlines(), start=1):
                if q in line:
                    hits.append(
                        {
                            "file": self.relative_to_root(file_path),
                            "line": idx,
                            "match": line.rstrip("\n\r"),
                        }
                    )
                    if len(hits) >= max_results:
                        return hits
        return hits

    def write_text(
        self,
        path: str | Path,
        content: str,
        *,
        overwrite: bool = False,
        create_parents: bool = True,
    ) -> dict[str, Any]:
        """写入 UTF-8 文本文件（原子替换）。

        语义：
        - 文件不存在 → 创建（可选自动创建父目录，默认开启）
        - 文件存在且 overwrite=False → 拒绝
        - 文件存在且 overwrite=True → 覆盖
        """
        if not isinstance(content, str):
            raise WorkspaceIOError("content 必须为字符串（UTF-8 文本）。")

        target = self.resolve_path(path)
        created = not target.exists()
        overwritten = False

        if target.exists():
            if target.is_dir():
                raise WorkspaceIOError(f"目标是目录，无法写入文件：{self._safe_rel(target)}")
            if not overwrite:
                raise WorkspaceIOError(
                    f"文件已存在且 overwrite=false：{self.relative_to_root(target)}"
                )
            overwritten = True
            created = False

        self._ensure_parent_dir(target, create_parents=create_parents)
        self._atomic_write_text(target, content)

        return {
            "path": self.relative_to_root(target),
            "created": created,
            "overwritten": overwritten,
            "bytes_written": len(content.encode("utf-8")),
        }

    def replace_text(
        self,
        path: str | Path,
        old_text: str,
        new_text: str,
        *,
        expected_replacements: int = 1,
    ) -> dict[str, Any]:
        """对已有 UTF-8 文本文件做确定性子串替换，再原子写回。

        仅当 old_text 的实际出现次数恰好等于 expected_replacements 时才修改；
        不猜测、不模糊匹配。
        """
        if not isinstance(old_text, str) or old_text == "":
            raise WorkspaceIOError("old_text 不能为空。")
        if not isinstance(new_text, str):
            raise WorkspaceIOError("new_text 必须为字符串。")
        try:
            expected = int(expected_replacements)
        except (TypeError, ValueError) as exc:
            raise WorkspaceIOError("expected_replacements 必须为整数。") from exc
        if expected < 1:
            raise WorkspaceIOError("expected_replacements 必须 >= 1。")

        target = self.resolve_path(path)
        if not target.exists():
            raise WorkspaceIOError(f"文件不存在：{path}")
        if not target.is_file():
            raise WorkspaceIOError(f"不是文件：{self.relative_to_root(target)}")

        text = self._read_utf8_text(target)
        actual = text.count(old_text)
        if actual != expected:
            raise WorkspaceIOError(
                f"替换次数不匹配：expected_replacements={expected}, actual={actual}。"
                "拒绝修改（确定性编辑：不允许猜测意图）。"
            )

        updated = text.replace(old_text, new_text)
        self._atomic_write_text(target, updated)

        return {
            "path": self.relative_to_root(target),
            "replacements": actual,
        }

    def _read_utf8_text(self, target: Path) -> str:
        """读取目标文件为 UTF-8 文本；二进制或解码失败则结构化报错。"""
        try:
            raw = target.read_bytes()
        except OSError as exc:
            raise WorkspaceIOError(f"无法读取文件：{exc}") from exc
        if b"\x00" in raw[:8192]:
            raise WorkspaceIOError(f"拒绝作为文本修改二进制文件：{self.relative_to_root(target)}")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceIOError(
                f"无法以 UTF-8 解码：{self.relative_to_root(target)}"
            ) from exc

    def _ensure_parent_dir(self, target: Path, *, create_parents: bool) -> None:
        """确保写入目标的父目录存在，且始终位于 workspace 内。"""
        parent = target.parent
        try:
            # 父路径即便尚未存在，resolve 后也必须落在边界内
            parent_resolved = parent.resolve()
            parent_resolved.relative_to(self._root)
        except ValueError as exc:
            raise PathOutsideWorkspaceError(
                f"父目录超出 workspace 边界：{parent}"
            ) from exc
        except OSError as exc:
            raise WorkspaceIOError(f"无法解析父目录：{exc}") from exc

        if parent.exists():
            if not parent.is_dir():
                raise WorkspaceIOError(f"父路径不是目录：{self._safe_rel(parent)}")
            return

        if not create_parents:
            raise WorkspaceIOError(
                f"父目录不存在且未启用自动创建：{self._safe_rel(parent)}"
            )

        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorkspaceIOError(f"无法创建父目录：{exc}") from exc

        # 创建后再校验（防止异常竞态 / 异常挂载）
        try:
            parent.resolve().relative_to(self._root)
        except ValueError as exc:
            raise PathOutsideWorkspaceError(
                f"创建后的父目录超出 workspace 边界：{parent}"
            ) from exc

    def _atomic_write_text(self, target: Path, content: str) -> None:
        """先写同目录临时文件，再 os.replace 原子替换，避免截断半成品。"""
        data = content.encode("utf-8")
        parent = target.parent
        fd: int | None = None
        tmp_path: Path | None = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=str(parent),
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "wb") as handle:
                fd = None  # 已由 fdopen 接管
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, target)
            tmp_path = None
        except OSError as exc:
            raise WorkspaceIOError(f"写入失败：{exc}") from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _iter_text_files(self, base: Path) -> Iterator[Path]:
        if base.is_file():
            yield base
            return
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_SKIP_DIRS]
            for name in sorted(filenames):
                child = Path(dirpath) / name
                try:
                    resolved = child.resolve()
                    resolved.relative_to(self._root)
                except (OSError, ValueError):
                    continue
                if resolved.is_file():
                    yield resolved
