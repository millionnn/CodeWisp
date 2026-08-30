-- V0.9 Phase 2：Workspace Snapshot / FileChange 持久化
-- 关联 Session → AgentRun → AgentStep → ToolCall；不删除既有表

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    workspace_root TEXT NOT NULL,
    session_id TEXT,
    agent_run_id TEXT,
    agent_step_id TEXT,
    tool_call_id TEXT,
    reason TEXT NOT NULL,
    created_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_step_id) REFERENCES agent_steps(id) ON DELETE SET NULL,
    FOREIGN KEY (tool_call_id) REFERENCES tool_calls(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS snapshot_files (
    snapshot_id TEXT NOT NULL,
    path TEXT NOT NULL,
    exists_flag INTEGER NOT NULL,
    content TEXT,
    size INTEGER,
    content_hash TEXT,
    PRIMARY KEY (snapshot_id, path),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS file_changes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_run_id TEXT NOT NULL,
    agent_step_id TEXT NOT NULL,
    tool_call_id TEXT,
    path TEXT NOT NULL,
    change_type TEXT NOT NULL,
    before_snapshot_id TEXT,
    after_snapshot_id TEXT,
    created_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_step_id) REFERENCES agent_steps(id) ON DELETE CASCADE,
    FOREIGN KEY (tool_call_id) REFERENCES tool_calls(id) ON DELETE SET NULL,
    FOREIGN KEY (before_snapshot_id) REFERENCES snapshots(id) ON DELETE SET NULL,
    FOREIGN KEY (after_snapshot_id) REFERENCES snapshots(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_run ON snapshots(agent_run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_step ON snapshots(agent_step_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_tool ON snapshots(tool_call_id);
CREATE INDEX IF NOT EXISTS idx_file_changes_run ON file_changes(agent_run_id);
CREATE INDEX IF NOT EXISTS idx_file_changes_step ON file_changes(agent_step_id);
CREATE INDEX IF NOT EXISTS idx_file_changes_tool ON file_changes(tool_call_id);
