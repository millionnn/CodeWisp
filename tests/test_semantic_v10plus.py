"""V1.0+ Semantic Memory / Planner 测试（全部 Fake LLM / Hash embedding）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app.context.models import PlanStepStatus
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse
from backend.app.memory.chunking import chunk_text
from backend.app.memory.embeddings import FailingEmbeddingProvider, HashEmbeddingProvider
from backend.app.memory.extractor import MemoryExtractor
from backend.app.memory.index import SemanticIndex
from backend.app.memory.prompts import parse_memory_extraction
from backend.app.memory.service import MemoryService
from backend.app.persistence.semantic_repository import SemanticIndexRepository
from backend.app.persistence.store import SqliteStore
from backend.app.planning.parser import parse_plan_json
from backend.app.planning.service import PlannerService
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._queue = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": conversation.to_api_messages(), "tools": tools})
        if not self._queue:
            from backend.app.llm.errors import LLMRequestError

            raise LLMRequestError("empty")
        return self._queue.pop(0)


def test_hash_embedding_deterministic() -> None:
    p = HashEmbeddingProvider(dimensions=32)
    a = p.embed("hello auth")
    b = p.embed("hello auth")
    assert a == b
    assert len(a) == 32
    c = p.batch_embed(["a", "b"])
    assert len(c) == 2


def test_embedding_provider_failure() -> None:
    p = FailingEmbeddingProvider()
    with pytest.raises(RuntimeError):
        p.embed("x")


def test_chunk_python_and_markdown() -> None:
    py = "class A:\n    pass\n\ndef foo():\n    return 1\n"
    chunks = chunk_text("a.py", py)
    assert len(chunks) >= 1
    md = "# Title\nhello\n## Sec\nworld\n"
    mchunks = chunk_text("README.md", md)
    assert any(c.symbol for c in mchunks)


def test_semantic_index_search_incremental(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "auth.py").write_text(
        "def authenticate(user):\n    return token\n", encoding="utf-8"
    )
    (ws / "AGENTS.md").write_text("# Rules\nUse pytest\n", encoding="utf-8")
    store = SqliteStore(tmp_path / "db.sqlite")
    store.connect()
    idx = SemanticIndex(SemanticIndexRepository(store), embedding=HashEmbeddingProvider())
    stats = idx.index_workspace(str(ws))
    assert stats.chunks >= 1
    # unchanged skip
    assert idx.index_file(str(ws), "auth.py") is False
    (ws / "auth.py").write_text(
        "def authenticate(user):\n    return jwt_token\n", encoding="utf-8"
    )
    assert idx.index_file(str(ws), "auth.py") is True
    hits = idx.search(str(ws), "authentication jwt", top_k=5)
    assert hits
    assert any("auth" in (h.path or "") for h in hits)
    idx.delete(str(ws), "auth.py")
    rebuilt = idx.rebuild(str(ws))
    assert rebuilt.documents >= 1


def test_hybrid_memory_search_and_restart(tmp_path: Path) -> None:
    ws = tmp_path / "w"
    ws.mkdir()
    (ws / "order.py").write_text(
        "from decimal import Decimal\ndef price(x): return Decimal(x)\n",
        encoding="utf-8",
    )
    db = tmp_path / "m.db"
    store = SqliteStore(db)
    store.connect()
    svc = SessionService(store)
    session = svc.create_session(workspace=ws, title="m")
    mem = MemoryService(store, embedding=HashEmbeddingProvider())
    mem.index_workspace(str(ws))
    # extract with LLM JSON
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content='{"memories":[{"type":"coding_convention","content":'
                '"Use Decimal for monetary calculations.","confidence":0.95,'
                '"files":["order.py"]}]}',
                tool_calls=(),
            )
        ]
    )
    mem.set_llm(llm)
    items = mem.extract_after_run(
        session_id=session.session_id,
        workspace=str(ws),
        objective="Fix money calculation",
        final_answer="used Decimal",
        observations=["changed order.py to Decimal"],
        changed_files=["order.py"],
        agent_run_id="run_1",
    )
    assert any("Decimal" in i.content for i in items)
    hits = mem.search(str(ws), "money decimal price", session_id=session.session_id)
    assert hits
    store.close()

    store2 = SqliteStore(db)
    store2.connect()
    mem2 = MemoryService(store2, embedding=HashEmbeddingProvider())
    hits2 = mem2.search(str(ws), "Decimal monetary", session_id=session.session_id)
    assert hits2


def test_memory_extraction_invalid_json_falls_back() -> None:
    assert parse_memory_extraction("not json") == []
    llm = ScriptedLLMClient([LLMResponse(content="oops", tool_calls=())])
    ext = MemoryExtractor(llm)
    result = ext.extract(
        session_id="ses_x",
        objective="task",
        final_answer="done",
        observations=["pytest passed"],
        changed_files=[],
    )
    assert result.used_llm is True
    # may be empty or heuristic — must not raise


def test_planner_initial_and_replan(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "p.db")
    store.connect()
    SessionService(store).create_session(workspace=tmp_path, title="p")
    # need session for FK? plans reference session_id
    from backend.app.persistence.context_repository import ContextRepository

    repo = ContextRepository(store)
    sessions = SessionService(store)
    ses = sessions.list_sessions()[0]

    plan_json = (
        '{"objective":"Add JWT auth","steps":['
        '{"index":0,"title":"Find auth","status":"completed","description":"done"},'
        '{"index":1,"title":"Add JWT","status":"in_progress","description":"impl"},'
        '{"index":2,"title":"Update tests","status":"pending","description":"test"}'
        "]}"
    )
    llm = ScriptedLLMClient([LLMResponse(content=plan_json, tool_calls=())])
    planner = PlannerService(llm=llm, repository=repo)
    plan = planner.create_initial_plan(session_id=ses.session_id, goal="Add JWT auth")
    assert len(plan.steps) == 3

    replan_json = (
        '{"objective":"Add JWT auth","steps":['
        '{"index":0,"title":"Find auth","status":"completed"},'
        '{"index":1,"title":"Add JWT","status":"skipped","rationale":"already exists"},'
        '{"index":2,"title":"Update middleware","status":"in_progress"},'
        '{"index":3,"title":"Update tests","status":"pending"}'
        "]}"
    )
    planner.set_llm(ScriptedLLMClient([LLMResponse(content=replan_json, tool_calls=())]))
    updated = planner.replan(plan, observation="JWT already exists in AuthService")
    assert any(s.status == PlanStepStatus.SKIPPED for s in updated.steps)

    # heuristic replan without LLM
    planner.set_llm(None)
    p2 = planner.create_initial_plan(session_id=ses.session_id, goal="Add JWT authentication")
    # force a step title that matches skip heuristics
    p2.steps[0].title = "Add JWT generation"
    p2.steps[0].status = PlanStepStatus.IN_PROGRESS
    p2 = planner.replan(p2, observation="JWT already exists, reuse existing implementation")
    assert any(s.status == PlanStepStatus.SKIPPED for s in p2.steps)


def test_parse_plan_json_roundtrip() -> None:
    text = (
        '{"objective":"t","steps":[{"index":0,"title":"A","status":"pending",'
        '"relevant_files":["a.py"],"verification":"pytest","rationale":"r"}]}'
    )
    plan = parse_plan_json(text, session_id="ses_1")
    assert plan.goal == "t"
    assert plan.steps[0].status == PlanStepStatus.IN_PROGRESS  # auto-activate


def test_parse_plan_json_normalizes_one_based_index() -> None:
    text = (
        '{"objective":"feat","steps":['
        '{"index":2,"title":"Read calculator","status":"failed"},'
        '{"index":3,"title":"Implement","status":"pending"},'
        '{"index":5,"title":"Test","status":"pending"}'
        "]}"
    )
    plan = parse_plan_json(text, session_id="ses_1")
    assert [s.step_index for s in plan.steps] == [0, 1, 2]
    assert [s.title for s in plan.steps] == ["Read calculator", "Implement", "Test"]
    assert plan.steps[0].status == PlanStepStatus.IN_PROGRESS
    assert all(s.status == PlanStepStatus.PENDING for s in plan.steps[1:])


def test_parse_plan_json_replan_shrink_keeps_steps() -> None:
    existing = parse_plan_json(
        '{"objective":"g","steps":['
        '{"index":0,"title":"A"},{"index":1,"title":"B"},{"index":2,"title":"C"}'
        "]}",
        session_id="s",
    )
    assert len(existing.steps) == 3
    shrunk = parse_plan_json(
        '{"objective":"g","steps":['
        '{"index":0,"title":"A","status":"failed","rationale":"x"}'
        "]}",
        session_id="s",
        existing=existing,
    )
    titles = [s.title for s in sorted(shrunk.steps, key=lambda x: x.step_index)]
    assert titles == ["A", "B", "C"]


def test_agent_service_memory_apis(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "user_service.py").write_text(
        "class UserService:\n    def get(self): pass\n", encoding="utf-8"
    )
    store = SqliteStore(tmp_path / "a.db")
    store.connect()
    llm = ScriptedLLMClient([LLMResponse(content="ok", tool_calls=())])
    agents = AgentService(store, llm=llm, max_steps=3)
    session = agents.sessions.create_session(workspace=ws, title="api")
    stats = agents.memory_index(session.session_id)
    assert stats.chunks >= 1
    hits = agents.memory_search(session.session_id, "UserService")
    assert hits
    bundle = agents.get_context_bundle(session.session_id)
    assert "status" in bundle
    agents.run(session.session_id, "say hello about user service")
    plan = agents.get_latest_plan(session.session_id)
    assert plan is not None
