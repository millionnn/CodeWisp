-- V0.6 schema v1：Session / Conversation / AgentRun / AgentStep / ToolCall
-- 不含 snapshots、providers、api_keys（后续版本）

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    workspace TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    status TEXT NOT NULL,
    termination_reason TEXT,
    max_steps INTEGER NOT NULL DEFAULT 15,
    final_answer TEXT,
    error TEXT,
    created_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_steps (
    id TEXT PRIMARY KEY,
    agent_run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    UNIQUE (agent_run_id, step_index)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_run_id TEXT,
    step_id TEXT,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_call_id TEXT,
    tool_calls_json TEXT,
    created_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES agent_steps(id) ON DELETE SET NULL,
    UNIQUE (session_id, seq)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL DEFAULT '{}',
    arguments_raw TEXT,
    parse_error TEXT,
    result_json TEXT,
    created_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES agent_steps(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session_seq ON messages(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run ON agent_steps(agent_run_id, step_index);
CREATE INDEX IF NOT EXISTS idx_tool_calls_step ON tool_calls(step_id);
