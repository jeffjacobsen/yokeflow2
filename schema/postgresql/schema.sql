-- =============================================================================
-- YokeFlow (Autonomous Coding Agent) - Complete PostgreSQL Schema
-- =============================================================================
-- Version: 2.5.1
-- Date: February 26, 2026
--
-- This is the complete, consolidated schema file reflecting the current database.
--
-- To initialize a fresh database:
--   Run: python scripts/init_database.py --docker
--
-- Changelog:
--   2.5.1 (Feb 26, 2026): Standardize test tables on passes boolean
--      - Standardized epic_tests to use passes (boolean) instead of last_result (varchar)
--      - Removed unused columns from epics, tasks, task_tests, epic_tests
--      - Dropped epic_test_failures table and record_epic_test_failure function
--   2.5.0 (Feb 26, 2026): Codebase cleanup
--      - Removed unused columns: projects(github_default_branch, deployment_status,
--        sandbox_config, api_endpoint), prompt_improvement_analyses(sandbox_type)
--      - Removed intervention system tables: paused_sessions, intervention_actions,
--        notification_preferences (archived to archive/intervention/)
--      - Removed deployment_status enum type
--      - Removed 12 unused views and 8 unused functions
--      - Removed broken Migration 017 section (referenced nonexistent 'tests' table)
--      - Cleaned up orphaned comments and empty scaffolding
--   2.1.0 (Feb 2, 2026): Quality system complete - Fully consolidated schema
--   2.0.0 (Jan 9, 2026): Consolidated with all migrations (011-016) - Production ready
-- =============================================================================

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- For UUID generation

-- =============================================================================
-- CUSTOM TYPES
-- =============================================================================

-- Project status enum
DO $$ BEGIN CREATE TYPE project_status AS ENUM ('active', 'paused', 'completed', 'archived');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Session types
-- Note: 'expansion' is deprecated (removed in v2.4) but kept because
-- removing PostgreSQL enum values requires recreating the type.
DO $$ BEGIN CREATE TYPE session_type AS ENUM ('initializer', 'expansion', 'coding', 'review');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Session status
DO $$ BEGIN CREATE TYPE session_status AS ENUM ('pending', 'running', 'completed', 'error', 'interrupted');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Task status
DO $$ BEGIN CREATE TYPE task_status AS ENUM ('pending', 'in_progress', 'completed', 'blocked');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =============================================================================
-- MAIN TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Projects Table - Central metadata for all projects
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    user_id UUID,  -- Ready for multi-user support

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,  -- Project completion tracking

    -- Environment configuration
    env_configured BOOLEAN DEFAULT FALSE,
    env_configured_at TIMESTAMPTZ,

    -- Specification tracking
    spec_file_path TEXT,
    spec_hash VARCHAR(64),  -- SHA256 hash to detect changes

    -- GitHub integration
    github_repo_url TEXT,
    github_branch VARCHAR(100) DEFAULT 'main',

    -- Project status and metrics
    status project_status DEFAULT 'active',
    total_cost_usd DECIMAL(10,4) DEFAULT 0,
    total_time_seconds INTEGER DEFAULT 0,

    -- Flexible metadata storage
    metadata JSONB DEFAULT '{}',

    -- Brownfield support (v2.2)
    project_type VARCHAR(20) DEFAULT 'greenfield'
        CHECK (project_type IN ('greenfield', 'brownfield')),
    source_commit_sha VARCHAR(40),
    codebase_analysis JSONB DEFAULT '{}',

    -- Constraints
    CONSTRAINT valid_total_cost CHECK (total_cost_usd >= 0),
    CONSTRAINT valid_total_time CHECK (total_time_seconds >= 0)
);

CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
CREATE INDEX IF NOT EXISTS idx_projects_metadata ON projects USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_projects_completed_at ON projects(completed_at);
CREATE INDEX IF NOT EXISTS idx_projects_total_time ON projects(total_time_seconds);
CREATE INDEX IF NOT EXISTS idx_projects_project_type ON projects(project_type);

COMMENT ON COLUMN projects.project_type IS 'greenfield = new project from scratch, brownfield = modifications to existing codebase';
COMMENT ON COLUMN projects.source_commit_sha IS 'Git commit SHA at import time for brownfield projects, used to track drift';
COMMENT ON COLUMN projects.codebase_analysis IS 'Automated analysis of imported codebase: languages, frameworks, test suite, structure';
COMMENT ON COLUMN projects.completed_at IS 'Timestamp when all epics/tasks/tests were completed. NULL means project is still in progress.';
COMMENT ON COLUMN projects.total_time_seconds IS 'Total time spent on project in seconds, automatically aggregated from session durations';

-- -----------------------------------------------------------------------------
-- Sessions Table - Track all agent sessions
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_number INTEGER NOT NULL,
    type session_type NOT NULL,

    -- Model configuration
    model TEXT NOT NULL,
    max_iterations INTEGER,

    -- Session status
    status session_status DEFAULT 'pending',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    last_heartbeat TIMESTAMPTZ,  -- Track active sessions to prevent false-positive stale detection

    -- Session outcome
    error_message TEXT,
    interruption_reason TEXT,

    -- Session metrics stored as JSONB for flexibility
    metrics JSONB DEFAULT '{
        "duration_seconds": 0,
        "tool_calls_count": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "cost_usd": 0,
        "tasks_completed": 0,
        "tests_passed": 0,
        "errors_count": 0,
        "browser_verifications": 0
    }',

    -- Log file references
    log_path TEXT,

    UNIQUE(project_id, session_number)
);

CREATE INDEX IF NOT EXISTS idx_sessions_project_status ON sessions(project_id, status);
CREATE INDEX IF NOT EXISTS idx_sessions_type ON sessions(type);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_metrics ON sessions USING GIN (metrics);
CREATE INDEX IF NOT EXISTS idx_sessions_stale_detection ON sessions (status, last_heartbeat) WHERE status = 'running';

COMMENT ON COLUMN sessions.last_heartbeat IS 'Timestamp of last heartbeat update during session execution. Used to detect truly stale sessions vs. long-running active sessions.';

-- -----------------------------------------------------------------------------
-- Hierarchical Task Management Tables
-- -----------------------------------------------------------------------------

-- Epics Table - High-level feature areas
CREATE TABLE IF NOT EXISTS epics (
    id SERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 0,
    status task_status DEFAULT 'pending',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    UNIQUE(project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_epics_project_id ON epics(project_id);
CREATE INDEX IF NOT EXISTS idx_epics_status ON epics(status);
CREATE INDEX IF NOT EXISTS idx_epics_priority ON epics(priority);

-- Tasks Table - Individual implementation steps
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    name TEXT NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 0,
    done BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Session tracking
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    session_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_epic_id ON tasks(epic_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks(done);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_session_id ON tasks(session_id);

-- Task Tests Table - Verification requirements for tasks
CREATE TABLE IF NOT EXISTS task_tests (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Test identification
    category VARCHAR(50) NOT NULL DEFAULT 'functional',
    test_type VARCHAR(20) NOT NULL DEFAULT 'unit',

    -- Test definition (requirements-based approach)
    description TEXT NOT NULL,
    requirements TEXT,  -- What to verify (not how)
    success_criteria TEXT,  -- Clear criteria for success
    steps JSONB DEFAULT '[]',

    -- Test results
    passes BOOLEAN DEFAULT false,
    last_execution TIMESTAMPTZ,
    verification_notes TEXT,  -- Notes from coding agent about verification
    execution_time_ms INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    verified_at TIMESTAMPTZ,

    CONSTRAINT valid_category CHECK (category IN ('functional', 'style', 'accessibility', 'performance', 'security'))
);

CREATE INDEX IF NOT EXISTS idx_task_tests_task_id ON task_tests(task_id);
CREATE INDEX IF NOT EXISTS idx_task_tests_project_id ON task_tests(project_id);
CREATE INDEX IF NOT EXISTS idx_task_tests_type ON task_tests(test_type);
CREATE INDEX IF NOT EXISTS idx_task_tests_task_type ON task_tests(task_id, test_type);
CREATE INDEX IF NOT EXISTS idx_task_tests_passes ON task_tests(passes);
CREATE INDEX IF NOT EXISTS idx_task_tests_category ON task_tests(category);

COMMENT ON TABLE task_tests IS 'Test requirements for individual tasks - defines WHAT to test, not HOW';
COMMENT ON COLUMN task_tests.requirements IS 'Test requirements describing what to verify (not how)';
COMMENT ON COLUMN task_tests.success_criteria IS 'Clear criteria for determining test success';
COMMENT ON COLUMN task_tests.verification_notes IS 'Notes from coding agent about how requirements were verified';

-- -----------------------------------------------------------------------------
-- Epic Tests Table - Integration tests for epics
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS epic_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    project_id UUID NOT NULL,

    -- Test details
    name VARCHAR(255) NOT NULL,
    description TEXT,
    test_type VARCHAR(20) DEFAULT 'integration',

    -- Requirements-based approach
    requirements TEXT,
    success_criteria TEXT,
    key_verification_points JSONB,
    verification_notes TEXT,

    -- Test results
    passes BOOLEAN DEFAULT false,
    last_execution TIMESTAMPTZ,
    execution_time_ms INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Foreign key for project
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,

    -- Constraints
    CONSTRAINT chk_epic_test_type
        CHECK (test_type IN ('integration', 'e2e', 'workflow'))
);

CREATE INDEX IF NOT EXISTS idx_epic_tests_epic_id ON epic_tests(epic_id);
CREATE INDEX IF NOT EXISTS idx_epic_tests_project_id ON epic_tests(project_id);
CREATE INDEX IF NOT EXISTS idx_epic_tests_passes ON epic_tests(passes);
CREATE INDEX IF NOT EXISTS idx_epic_tests_test_type ON epic_tests(test_type);

COMMENT ON TABLE epic_tests IS 'Integration test requirements for epics - end-to-end workflow verification';

-- -----------------------------------------------------------------------------
-- Deep Review Results
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS session_deep_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,

    -- Review version and timing
    review_version VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Overall score (1-10)
    overall_rating INTEGER,

    -- Deep review results
    review_text TEXT,
    review_summary JSONB DEFAULT '{}',
    prompt_improvements JSONB DEFAULT '[]',

    -- Model used for review
    model VARCHAR(100),

    -- Constraints
    CONSTRAINT valid_deep_review_rating CHECK (overall_rating IS NULL OR (overall_rating >= 1 AND overall_rating <= 10)),
    CONSTRAINT unique_session_deep_review UNIQUE (session_id)
);

CREATE INDEX IF NOT EXISTS idx_deep_reviews_session ON session_deep_reviews(session_id);
CREATE INDEX IF NOT EXISTS idx_deep_reviews_created ON session_deep_reviews(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_deep_reviews_rating ON session_deep_reviews(overall_rating) WHERE overall_rating IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_deep_reviews_improvements ON session_deep_reviews USING GIN (prompt_improvements);

COMMENT ON TABLE session_deep_reviews IS 'Deep review results for coding sessions. Automated or on-demand Claude-powered reviews for prompt improvement analysis.';

-- -----------------------------------------------------------------------------
-- Prompt Improvement System Tables
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS prompt_improvement_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'pending',

    -- Analysis scope
    projects_analyzed UUID[] NOT NULL,
    sessions_analyzed INTEGER NOT NULL DEFAULT 0,
    date_range_start TIMESTAMPTZ,
    date_range_end TIMESTAMPTZ,

    -- Configuration
    analysis_model VARCHAR(100) DEFAULT 'claude-sonnet-4-6',

    -- Results
    overall_findings TEXT,
    patterns_identified JSONB DEFAULT '{}',
    proposed_changes JSONB DEFAULT '[]',
    quality_impact_estimate DECIMAL(3,1),

    -- Metadata
    triggered_by VARCHAR(50),
    user_id UUID,
    notes TEXT,

    CONSTRAINT status_valid CHECK (status IN ('pending', 'running', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_prompt_analyses_status ON prompt_improvement_analyses(status);
CREATE INDEX IF NOT EXISTS idx_prompt_analyses_created ON prompt_improvement_analyses(created_at DESC);

CREATE TABLE IF NOT EXISTS prompt_proposals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_id UUID REFERENCES prompt_improvement_analyses(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Change details
    prompt_file VARCHAR(100) NOT NULL,
    section_name VARCHAR(200),
    line_start INTEGER,
    line_end INTEGER,

    -- The actual change
    original_text TEXT NOT NULL,
    proposed_text TEXT NOT NULL,
    change_type VARCHAR(50),

    -- Justification
    rationale TEXT NOT NULL,
    evidence JSONB DEFAULT '[]',
    confidence_level INTEGER,

    -- Implementation status
    status VARCHAR(20) DEFAULT 'proposed',
    applied_at TIMESTAMPTZ,
    applied_to_version VARCHAR(50),
    applied_by VARCHAR(100),

    -- Impact tracking
    sessions_before_change INTEGER,
    quality_before DECIMAL(3,1),
    sessions_after_change INTEGER,
    quality_after DECIMAL(3,1),

    -- Additional metadata
    metadata JSONB DEFAULT '{}',

    CONSTRAINT change_type_valid CHECK (change_type IN ('addition', 'modification', 'deletion', 'reorganization')),
    CONSTRAINT pp_status_valid CHECK (status IN ('proposed', 'accepted', 'rejected', 'implemented')),
    CONSTRAINT confidence_valid CHECK (confidence_level BETWEEN 1 AND 10)
);

CREATE INDEX IF NOT EXISTS idx_proposals_analysis ON prompt_proposals(analysis_id);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON prompt_proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_file ON prompt_proposals(prompt_file);

COMMENT ON TABLE prompt_improvement_analyses IS 'Stores cross-project prompt improvement analyses';
COMMENT ON TABLE prompt_proposals IS 'Individual prompt change proposals from analyses';

-- -----------------------------------------------------------------------------
-- Session Checkpoints for Resume Capability
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS session_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Checkpoint metadata
    checkpoint_number INTEGER NOT NULL,
    checkpoint_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Session state at checkpoint
    current_task_id INTEGER REFERENCES tasks(id),
    current_epic_id INTEGER REFERENCES epics(id),
    message_count INTEGER NOT NULL DEFAULT 0,
    iteration_count INTEGER NOT NULL DEFAULT 0,

    -- Agent conversation state
    conversation_history JSONB NOT NULL DEFAULT '[]',
    tool_results_cache JSONB NOT NULL DEFAULT '{}',

    -- Task progress state
    completed_tasks INTEGER[] DEFAULT '{}',
    in_progress_tasks INTEGER[] DEFAULT '{}',
    blocked_tasks INTEGER[] DEFAULT '{}',

    -- Session metrics snapshot
    metrics_snapshot JSONB NOT NULL DEFAULT '{}',

    -- File system state
    files_modified TEXT[],
    git_commit_sha VARCHAR(40),

    -- Resumption info
    can_resume_from BOOLEAN DEFAULT TRUE,
    resume_notes TEXT,
    invalidated BOOLEAN DEFAULT FALSE,
    invalidation_reason TEXT,

    -- Recovery metadata
    recovery_count INTEGER DEFAULT 0,
    last_resumed_at TIMESTAMPTZ,

    CONSTRAINT unique_checkpoint_per_session UNIQUE (session_id, checkpoint_number),
    CONSTRAINT valid_checkpoint_number CHECK (checkpoint_number > 0),
    CONSTRAINT valid_message_count CHECK (message_count >= 0),
    CONSTRAINT valid_iteration_count CHECK (iteration_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON session_checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_project ON session_checkpoints(project_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON session_checkpoints(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkpoints_type ON session_checkpoints(checkpoint_type);
CREATE INDEX IF NOT EXISTS idx_checkpoints_can_resume ON session_checkpoints(can_resume_from) WHERE can_resume_from = TRUE;
CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON session_checkpoints(current_task_id) WHERE current_task_id IS NOT NULL;

COMMENT ON TABLE session_checkpoints IS 'Stores session state snapshots at key points for recovery and resumption';
COMMENT ON COLUMN session_checkpoints.conversation_history IS 'Full conversation history at checkpoint for context restoration';
COMMENT ON COLUMN session_checkpoints.tool_results_cache IS 'Recent tool results to avoid re-execution';
COMMENT ON COLUMN session_checkpoints.invalidated IS 'Set to true if state has diverged and checkpoint is no longer safe to resume from';

-- =============================================================================
-- VIEWS
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Progress View (includes both task tests and epic tests)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_progress AS
SELECT
    p.id as project_id,
    p.name as project_name,
    COUNT(DISTINCT e.id) as total_epics,
    COUNT(DISTINCT CASE WHEN e.status = 'completed' THEN e.id END) as completed_epics,
    COUNT(DISTINCT t.id) as total_tasks,
    COUNT(DISTINCT CASE WHEN t.done = true THEN t.id END) as completed_tasks,
    COUNT(DISTINCT test.id) as total_task_tests,
    COUNT(DISTINCT CASE WHEN test.passes = true THEN test.id END) as passing_task_tests,
    COUNT(DISTINCT et.id) as total_epic_tests,
    COUNT(DISTINCT CASE WHEN et.passes = true THEN et.id END) as passing_epic_tests,
    COUNT(DISTINCT test.id) + COUNT(DISTINCT et.id) as total_tests,
    COUNT(DISTINCT CASE WHEN test.passes = true THEN test.id END) +
        COUNT(DISTINCT CASE WHEN et.passes = true THEN et.id END) as passing_tests,
    ROUND(
        CASE
            WHEN COUNT(DISTINCT t.id) > 0
            THEN (COUNT(DISTINCT CASE WHEN t.done = true THEN t.id END)::DECIMAL / COUNT(DISTINCT t.id) * 100)
            ELSE 0
        END, 2
    ) as task_completion_pct,
    ROUND(
        CASE
            WHEN (COUNT(DISTINCT test.id) + COUNT(DISTINCT et.id)) > 0
            THEN ((COUNT(DISTINCT CASE WHEN test.passes = true THEN test.id END) +
                   COUNT(DISTINCT CASE WHEN et.passes = true THEN et.id END))::DECIMAL /
                  (COUNT(DISTINCT test.id) + COUNT(DISTINCT et.id)) * 100)
            ELSE 0
        END, 2
    ) as test_pass_pct
FROM projects p
LEFT JOIN epics e ON e.project_id = p.id
LEFT JOIN tasks t ON t.epic_id = e.id
LEFT JOIN task_tests test ON test.task_id = t.id
LEFT JOIN epic_tests et ON et.epic_id = e.id
GROUP BY p.id, p.name;

COMMENT ON VIEW v_progress IS 'Project progress metrics including task tests and epic tests separately';

-- -----------------------------------------------------------------------------
-- Epic Progress View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_epic_progress AS
SELECT
    e.id as epic_id,
    e.project_id,
    e.name,
    e.status,
    COUNT(t.id) as total_tasks,
    SUM(CASE WHEN t.done = true THEN 1 ELSE 0 END) as completed_tasks,
    ROUND(
        CASE
            WHEN COUNT(t.id) > 0
            THEN (SUM(CASE WHEN t.done = true THEN 1 ELSE 0 END)::DECIMAL / COUNT(t.id) * 100)
            ELSE 0
        END, 2
    ) as completion_percentage
FROM epics e
LEFT JOIN tasks t ON e.id = t.epic_id
GROUP BY e.id;

-- -----------------------------------------------------------------------------
-- Prompt Improvement Views
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_recent_analyses AS
SELECT
    a.id,
    a.created_at,
    a.completed_at,
    a.status,
    CARDINALITY(a.projects_analyzed) as num_projects,
    a.sessions_analyzed,
    a.quality_impact_estimate,
    COUNT(p.id) as total_proposals,
    COUNT(CASE WHEN p.status = 'proposed' THEN 1 END) as pending_proposals,
    COUNT(CASE WHEN p.status = 'accepted' THEN 1 END) as accepted_proposals,
    COUNT(CASE WHEN p.status = 'implemented' THEN 1 END) as implemented_proposals
FROM prompt_improvement_analyses a
LEFT JOIN prompt_proposals p ON a.id = p.analysis_id
GROUP BY a.id
ORDER BY a.created_at DESC;

CREATE OR REPLACE VIEW v_pending_proposals AS
SELECT
    p.id,
    p.created_at,
    p.prompt_file,
    p.section_name,
    p.change_type,
    p.confidence_level,
    p.rationale,
    a.sessions_analyzed,
    CARDINALITY(a.projects_analyzed) as num_projects_analyzed
FROM prompt_proposals p
JOIN prompt_improvement_analyses a ON p.analysis_id = a.id
WHERE p.status = 'proposed'
ORDER BY p.confidence_level DESC, p.created_at DESC;

-- -----------------------------------------------------------------------------
-- Resumable Checkpoints View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_resumable_checkpoints AS
SELECT
    cp.id,
    cp.session_id,
    cp.project_id,
    p.name as project_name,
    cp.checkpoint_number,
    cp.checkpoint_type,
    cp.created_at,
    cp.current_task_id,
    t.name as current_task_name,
    cp.message_count,
    cp.recovery_count,
    cp.last_resumed_at,
    s.session_number,
    s.type as session_type,
    s.status as session_status,
    NOW() - cp.created_at as age
FROM session_checkpoints cp
JOIN sessions s ON cp.session_id = s.id
JOIN projects p ON cp.project_id = p.id
LEFT JOIN tasks t ON cp.current_task_id = t.id
WHERE cp.can_resume_from = TRUE
  AND cp.invalidated = FALSE
  AND s.status IN ('error', 'interrupted')
ORDER BY cp.created_at DESC;

-- =============================================================================
-- FUNCTIONS AND TRIGGERS
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Update updated_at Timestamp
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_projects_updated_at ON projects;
CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- -----------------------------------------------------------------------------
-- Update Project Metrics (Cost and Time) on Session Complete
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_project_metrics()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        UPDATE projects
        SET
            total_cost_usd = total_cost_usd + COALESCE((NEW.metrics->>'cost_usd')::DECIMAL, 0),
            total_time_seconds = total_time_seconds + COALESCE(ROUND((NEW.metrics->>'duration_seconds')::NUMERIC)::INTEGER, 0)
        WHERE id = NEW.project_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_project_metrics_on_session_complete ON sessions;
CREATE TRIGGER update_project_metrics_on_session_complete
    AFTER UPDATE ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_project_metrics();

-- -----------------------------------------------------------------------------
-- Validate Session Type Consistency (0-based session numbering)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION validate_session_type()
RETURNS TRIGGER AS $$
DECLARE
    epic_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO epic_count
    FROM epics
    WHERE project_id = NEW.project_id;

    IF NEW.session_number = 0 AND epic_count = 0 AND NEW.type != 'initializer' THEN
        RAISE EXCEPTION 'First session (session_number = 0) must be initializer type when no epics exist';
    END IF;

    IF NEW.type = 'initializer' AND epic_count > 0 THEN
        RAISE EXCEPTION 'Cannot run initializer session when epics already exist (% epics found)', epic_count;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS validate_session_type_consistency ON sessions;
CREATE TRIGGER validate_session_type_consistency
    BEFORE INSERT ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION validate_session_type();

COMMENT ON FUNCTION validate_session_type() IS 'Validates session type consistency: First session (session_number=0) must be initializer when no epics exist, and initializer cannot run when epics exist';

-- -----------------------------------------------------------------------------
-- Checkpoint Functions
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION create_checkpoint(
    p_session_id UUID,
    p_project_id UUID,
    p_checkpoint_type VARCHAR(50),
    p_current_task_id INTEGER DEFAULT NULL,
    p_current_epic_id INTEGER DEFAULT NULL,
    p_message_count INTEGER DEFAULT 0,
    p_iteration_count INTEGER DEFAULT 0,
    p_conversation_history JSONB DEFAULT '[]',
    p_tool_results_cache JSONB DEFAULT '{}',
    p_completed_tasks INTEGER[] DEFAULT '{}',
    p_in_progress_tasks INTEGER[] DEFAULT '{}',
    p_blocked_tasks INTEGER[] DEFAULT '{}',
    p_metrics_snapshot JSONB DEFAULT '{}',
    p_files_modified TEXT[] DEFAULT '{}',
    p_git_commit_sha VARCHAR(40) DEFAULT NULL,
    p_resume_notes TEXT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_checkpoint_id UUID;
    v_checkpoint_number INTEGER;
BEGIN
    SELECT COALESCE(MAX(checkpoint_number), 0) + 1
    INTO v_checkpoint_number
    FROM session_checkpoints
    WHERE session_id = p_session_id;

    INSERT INTO session_checkpoints (
        session_id, project_id, checkpoint_number, checkpoint_type,
        current_task_id, current_epic_id, message_count, iteration_count,
        conversation_history, tool_results_cache,
        completed_tasks, in_progress_tasks, blocked_tasks,
        metrics_snapshot, files_modified, git_commit_sha, resume_notes
    ) VALUES (
        p_session_id, p_project_id, v_checkpoint_number, p_checkpoint_type,
        p_current_task_id, p_current_epic_id, p_message_count, p_iteration_count,
        p_conversation_history, p_tool_results_cache,
        p_completed_tasks, p_in_progress_tasks, p_blocked_tasks,
        p_metrics_snapshot, p_files_modified, p_git_commit_sha, p_resume_notes
    )
    RETURNING id INTO v_checkpoint_id;

    RETURN v_checkpoint_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION invalidate_checkpoints(
    p_session_id UUID,
    p_reason TEXT
) RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    UPDATE session_checkpoints
    SET invalidated = TRUE,
        invalidation_reason = p_reason
    WHERE session_id = p_session_id
      AND invalidated = FALSE
      AND can_resume_from = TRUE;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_latest_resumable_checkpoint(
    p_session_id UUID
) RETURNS UUID AS $$
DECLARE
    v_checkpoint_id UUID;
BEGIN
    SELECT id INTO v_checkpoint_id
    FROM session_checkpoints
    WHERE session_id = p_session_id
      AND can_resume_from = TRUE
      AND invalidated = FALSE
    ORDER BY checkpoint_number DESC
    LIMIT 1;

    RETURN v_checkpoint_id;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- PROJECT COMPLETION REVIEWS
-- =============================================================================

CREATE TABLE IF NOT EXISTS project_completion_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Specification metadata
    spec_file_path TEXT NOT NULL,
    spec_hash VARCHAR(64) NOT NULL,
    spec_parsed_at TIMESTAMPTZ DEFAULT NOW(),

    -- Requirements tracking
    requirements_total INTEGER NOT NULL DEFAULT 0,
    requirements_met INTEGER NOT NULL DEFAULT 0,
    requirements_missing INTEGER NOT NULL DEFAULT 0,
    requirements_extra INTEGER NOT NULL DEFAULT 0,

    -- Overall assessment
    coverage_percentage DECIMAL(5,2),
    overall_score INTEGER,
    recommendation VARCHAR(20),

    -- Review content
    executive_summary TEXT,
    review_text TEXT,

    -- Model used
    review_model VARCHAR(100) DEFAULT 'claude-sonnet-4-6',

    CONSTRAINT recommendation_valid CHECK (
        recommendation IN ('complete', 'needs_work', 'failed')
    ),
    CONSTRAINT score_valid CHECK (overall_score BETWEEN 1 AND 100)
);

CREATE TABLE IF NOT EXISTS completion_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID REFERENCES project_completion_reviews(id) ON DELETE CASCADE,

    -- Requirement details
    requirement_id VARCHAR(50) NOT NULL,
    section VARCHAR(100) NOT NULL,
    requirement_text TEXT NOT NULL,
    keywords TEXT[],
    priority VARCHAR(20),

    -- Implementation status
    status VARCHAR(20) NOT NULL,

    -- Mapping to epics/tasks
    matched_epic_ids INTEGER[],
    matched_task_ids INTEGER[],
    match_confidence DECIMAL(3,2),

    -- Notes
    implementation_notes TEXT,

    CONSTRAINT cr_status_valid CHECK (
        status IN ('met', 'missing', 'partial', 'extra')
    )
);

CREATE INDEX IF NOT EXISTS idx_completion_reviews_project ON project_completion_reviews(project_id);
CREATE INDEX IF NOT EXISTS idx_completion_reviews_created ON project_completion_reviews(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_completion_requirements_review ON completion_requirements(review_id);
CREATE INDEX IF NOT EXISTS idx_completion_requirements_status ON completion_requirements(status);
CREATE INDEX IF NOT EXISTS idx_completion_requirements_section ON completion_requirements(section);

-- Completion review views
CREATE OR REPLACE VIEW v_latest_completion_review AS
SELECT DISTINCT ON (project_id)
    pcr.*,
    p.name as project_name,
    p.completed_at as project_completed_at
FROM project_completion_reviews pcr
JOIN projects p ON pcr.project_id = p.id
ORDER BY project_id, created_at DESC;

CREATE OR REPLACE VIEW v_completion_section_summary AS
SELECT
    cr.review_id,
    cr.section,
    COUNT(*) as total_requirements,
    SUM(CASE WHEN cr.status = 'met' THEN 1 ELSE 0 END) as met_count,
    SUM(CASE WHEN cr.status = 'missing' THEN 1 ELSE 0 END) as missing_count,
    SUM(CASE WHEN cr.status = 'partial' THEN 1 ELSE 0 END) as partial_count,
    ROUND(AVG(cr.match_confidence), 2) as avg_confidence
FROM completion_requirements cr
GROUP BY cr.review_id, cr.section;

CREATE OR REPLACE VIEW v_project_completion_stats AS
SELECT
    p.id as project_id,
    p.name as project_name,
    p.completed_at,
    pcr.id as review_id,
    pcr.coverage_percentage,
    pcr.overall_score,
    pcr.recommendation,
    pcr.requirements_total,
    pcr.requirements_met,
    pcr.requirements_missing,
    pcr.requirements_extra,
    pcr.created_at as review_created_at
FROM projects p
LEFT JOIN v_latest_completion_review pcr ON p.id = pcr.project_id
WHERE p.completed_at IS NOT NULL;

COMMENT ON TABLE project_completion_reviews IS 'Stores project completion verification reviews comparing implementation against specifications';
COMMENT ON TABLE completion_requirements IS 'Individual requirements from spec with implementation tracking and mapping to epics/tasks';

-- =============================================================================
-- End of Consolidated Schema
-- =============================================================================
