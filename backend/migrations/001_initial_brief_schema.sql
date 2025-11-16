-- Migration: Initial schema for Asana Brief Creation
-- Date: 2025-11-15
-- Description: Creates tables for brief processing, task creation, and custom field management

-- ============================================================================
-- Table: briefs
-- Purpose: Track Google Doc brief processing requests
-- ============================================================================
CREATE TABLE IF NOT EXISTS briefs (
    id VARCHAR(255) PRIMARY KEY,
    google_doc_url VARCHAR(1000) NOT NULL,
    google_doc_id VARCHAR(255) NOT NULL,
    document_title VARCHAR(500),
    raw_content TEXT,
    parsed_structure JSONB,
    workspace_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(255) NOT NULL,
    project_name VARCHAR(500),
    section_id VARCHAR(255),
    section_name VARCHAR(500),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    total_tasks_expected INTEGER DEFAULT 0,
    total_tasks_created INTEGER DEFAULT 0,
    total_tasks_failed INTEGER DEFAULT 0,
    error_message TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_briefs_google_doc_id ON briefs(google_doc_id);
CREATE INDEX IF NOT EXISTS idx_briefs_project_id ON briefs(project_id);
CREATE INDEX IF NOT EXISTS idx_briefs_status ON briefs(status);
CREATE INDEX IF NOT EXISTS idx_briefs_created_at ON briefs(created_at DESC);

-- ============================================================================
-- Table: brief_tasks
-- Purpose: Track individual tasks created from each brief
-- ============================================================================
CREATE TABLE IF NOT EXISTS brief_tasks (
    id VARCHAR(255) PRIMARY KEY,
    brief_id VARCHAR(255) NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    asana_task_gid VARCHAR(255),
    asana_task_url VARCHAR(1000),
    task_name VARCHAR(1000) NOT NULL,
    task_description TEXT,
    task_order INTEGER,
    custom_fields JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    asana_created_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_brief_tasks_brief_id ON brief_tasks(brief_id);
CREATE INDEX IF NOT EXISTS idx_brief_tasks_asana_task_gid ON brief_tasks(asana_task_gid);
CREATE INDEX IF NOT EXISTS idx_brief_tasks_status ON brief_tasks(status);
CREATE INDEX IF NOT EXISTS idx_brief_tasks_created_at ON brief_tasks(created_at DESC);

-- GIN indexes for JSONB columns
CREATE INDEX IF NOT EXISTS idx_briefs_parsed_structure ON briefs USING GIN(parsed_structure);
CREATE INDEX IF NOT EXISTS idx_brief_tasks_custom_fields ON brief_tasks USING GIN(custom_fields);

COMMENT ON TABLE briefs IS 'Stores Google Doc brief processing requests and results';
COMMENT ON TABLE brief_tasks IS 'Individual tasks created from each brief with full Asana integration';
