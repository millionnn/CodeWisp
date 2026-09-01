"""LSP detector tests."""

from __future__ import annotations

from pathlib import Path

from backend.app.lsp.detector import LanguageServerDetector
from backend.app.lsp.models import LspServerStatus


def test_python_language_detected(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x=1\n", encoding="utf-8")
    lang = LanguageServerDetector.detect_language(tmp_path)
    assert lang == "python"


def test_typescript_language_detected(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text(" consoles.log(1)\n", encoding="utf-8")
    lang = LanguageServerDetector.detect_language(tmp_path)
    assert lang == "typescript"


def test_unsupported_workspace(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("hi\n", encoding="utf-8")
    detection = LanguageServerDetector.detect(tmp_path)
    assert detection.status is LspServerStatus.UNSUPPORTED
    assert detection.language is None


def test_python_unavailable_without_server(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    monkeypatch.setattr(
        "backend.app.lsp.detector.shutil.which",
        lambda _name: None,
    )
    detection = LanguageServerDetector.detect(tmp_path)
    assert detection.language == "python"
    assert detection.status is LspServerStatus.UNAVAILABLE


def test_language_for_path() -> None:
    assert LanguageServerDetector.language_for_path("foo.py") == "python"
    assert LanguageServerDetector.language_for_path("a.tsx") == "typescript"
    assert LanguageServerDetector.language_for_path("Main.java") == "java"
    assert LanguageServerDetector.language_for_path("lib.rs") == "rust"
    assert LanguageServerDetector.language_for_path("x.md") is None
