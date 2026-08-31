"""项目指令发现：AGENTS.md / CLAUDE.md（路径敏感、去重、可失效）。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

#按照当前文件路径向上找AGENTS.md或CLAUDE.md，去重、可刷新

RULE_FILENAMES: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md")

#数据结构：规则路径、内容、内容哈希
@dataclass(frozen=True)
class ProjectRule:
    """一条已发现的项目规则文件。"""

    path: str  # workspace-relative POSIX
    content: str
    content_hash: str

    @staticmethod
    def from_text(path: str, content: str) -> ProjectRule:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return ProjectRule(path=path, content=content, content_hash=digest)


@dataclass
class ProjectInstructionSet:
    """当前 Session 已注入的规则集合（按 path 去重）。"""

    rules: dict[str, ProjectRule] = field(default_factory=dict)
    loaded_hashes: dict[str, str] = field(default_factory=dict)

    def upsert(self, rule: ProjectRule) -> bool:
        """写入或刷新；返回是否发生内容变化。"""
        prev = self.loaded_hashes.get(rule.path)
        self.rules[rule.path] = rule
        self.loaded_hashes[rule.path] = rule.content_hash
        return prev != rule.content_hash

    def invalidate(self, path: str | None = None) -> None:
        if path is None:
            self.rules.clear()
            self.loaded_hashes.clear()
            return
        self.rules.pop(path, None)
        self.loaded_hashes.pop(path, None)

    def ordered(self) -> list[ProjectRule]:
        # 根规则优先，再按路径深度
        return sorted(
            self.rules.values(),
            key=lambda r: (r.path.count("/"), r.path),
        )

    def render(self) -> str:
        ordered = self.ordered()
        if not ordered:
            return ""
        parts = ["## Project Instructions"]
        for rule in ordered:
            parts.append(f"### {rule.path}")
            parts.append(rule.content.strip())
        return "\n\n".join(parts)


def discover_project_rules(
    workspace_root: Path | str,
    *,
    focus_path: str | None = None,
) -> list[ProjectRule]:
    """从 workspace 根到 focus_path 的祖先链发现 AGENTS.md / CLAUDE.md。

    同一目录优先 AGENTS.md，否则 CLAUDE.md。相同内容只保留一份路径键。
    """
    root = Path(workspace_root).resolve()
    if not root.is_dir():
        return []

    dirs = _ancestor_dirs(root, focus_path)
    found: list[ProjectRule] = []
    seen_hashes: set[str] = set()

    for directory in dirs:
        rule = _load_rule_in_dir(root, directory)
        if rule is None:
            continue
        if rule.content_hash in seen_hashes:
            continue
        seen_hashes.add(rule.content_hash)
        found.append(rule)
    return found


def _ancestor_dirs(root: Path, focus_path: str | None) -> list[Path]:
    """从根到 focus 所在目录（含根）。"""
    chain: list[Path] = [root]
    if not focus_path:
        return chain
    rel = focus_path.replace("\\", "/").strip("/")
    if not rel or ".." in rel.split("/"):
        return chain
    parent = Path(rel).parent
    parts = [] if str(parent) == "." else list(parent.parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_dir():
            chain.append(current)
    # 若 focus 本身是目录
    focus_dir = root / rel
    if focus_dir.is_dir() and focus_dir not in chain:
        chain.append(focus_dir)
    return chain


def _load_rule_in_dir(root: Path, directory: Path) -> ProjectRule | None:
    for name in RULE_FILENAMES:
        path = directory / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.strip():
            continue
        rel = path.relative_to(root).as_posix()
        return ProjectRule.from_text(rel, text)
    return None


def merge_rules(existing: ProjectInstructionSet, discovered: Iterable[ProjectRule]) -> list[str]:
    """合并新发现规则；返回发生变更的 path 列表。"""
    changed: list[str] = []
    for rule in discovered:
        if existing.upsert(rule):
            changed.append(rule.path)
    return changed
