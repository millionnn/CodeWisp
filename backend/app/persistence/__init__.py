"""SQLite 持久化层（V0.6）。

Phase 2-B：SqliteStore + migration。
Phase 2-C：Repositories。
"""

from backend.app.persistence.agent_run_repository import AgentRunRepository, PersistedToolCall
from backend.app.persistence.conversation_repository import ConversationRepository
from backend.app.persistence.errors import (
    ConflictError,
    MigrationError,
    NotFoundError,
    PersistenceError,
    RepositoryError,
)
from backend.app.persistence.migrate import (
    apply_migrations,
    get_schema_version,
    load_migrations,
)
from backend.app.persistence.session_repository import SessionRepository
from backend.app.persistence.store import SqliteStore

__all__ = [
    "AgentRunRepository",
    "ConflictError",
    "ConversationRepository",
    "MigrationError",
    "NotFoundError",
    "PersistedToolCall",
    "PersistenceError",
    "RepositoryError",
    "SessionRepository",
    "SqliteStore",
    "apply_migrations",
    "get_schema_version",
    "load_migrations",
]
