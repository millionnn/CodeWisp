-- V1.0+ Semantic Memory / Code Index
-- 扩展既有 memories；不删除旧表

PRAGMA foreign_keys = ON;

-- 扩展 V1.0 memories（幂等列）
ALTER TABLE memories ADD COLUMN workspace TEXT;
ALTER TABLE memories ADD COLUMN memory_type TEXT;
ALTER TABLE memories ADD COLUMN confidence REAL DEFAULT 0.5;
ALTER TABLE memories ADD COLUMN embedding_status TEXT DEFAULT 'pending';
ALTER TABLE memories ADD COLUMN access_count INTEGER DEFAULT 0;
ALTER TABLE memories ADD COLUMN last_accessed_at TEXT;

CREATE TABLE IF NOT EXISTS memory_sources (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    file_path TEXT,
    start_line INTEGER,
    end_line INTEGER,
    created_at TEXT,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS semantic_documents (
    id TEXT PRIMARY KEY,
    workspace TEXT NOT NULL,
    path TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    mtime REAL,
    size INTEGER,
    indexed_at TEXT,
    UNIQUE (workspace, path)
);

CREATE TABLE IF NOT EXISTS semantic_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    workspace TEXT NOT NULL,
    path TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    symbol TEXT,
    embedding_json TEXT,
    embedding_dim INTEGER,
    embedding_model TEXT,
    created_at TEXT,
    FOREIGN KEY (document_id) REFERENCES semantic_documents(id) ON DELETE CASCADE,
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS embedding_metadata (
    id TEXT PRIMARY KEY,
    workspace TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    updated_at TEXT,
    UNIQUE (workspace, key)
);

CREATE TABLE IF NOT EXISTS task_summaries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_run_id TEXT,
    workspace TEXT NOT NULL,
    objective TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    embedding_json TEXT,
    embedding_dim INTEGER,
    created_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- PlanStep  enrichment（幂等 ADD COLUMN；已存在则忽略由应用层保证只跑一次）
ALTER TABLE plan_steps ADD COLUMN dependencies_json TEXT DEFAULT '[]';
ALTER TABLE plan_steps ADD COLUMN relevant_files_json TEXT DEFAULT '[]';
ALTER TABLE plan_steps ADD COLUMN verification TEXT;
ALTER TABLE plan_steps ADD COLUMN rationale TEXT;

CREATE INDEX IF NOT EXISTS idx_semantic_chunks_ws ON semantic_chunks(workspace);
CREATE INDEX IF NOT EXISTS idx_semantic_chunks_path ON semantic_chunks(workspace, path);
CREATE INDEX IF NOT EXISTS idx_semantic_docs_ws ON semantic_documents(workspace);
CREATE INDEX IF NOT EXISTS idx_memory_sources_mem ON memory_sources(memory_id);
CREATE INDEX IF NOT EXISTS idx_task_summaries_ws ON task_summaries(workspace);
