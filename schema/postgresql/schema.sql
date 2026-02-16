-- =============================================================================
-- YokeFlow (Autonomous Coding Agent) - Complete PostgreSQL Schema
-- =============================================================================
-- Version: 2.1.0
-- Date: February 2, 2026
--
-- This is the complete, consolidated schema file reflecting the current database.
-- All migrations through 020 have been applied and integrated.
--
-- To initialize a fresh database:
--   Run: python scripts/init_database.py --docker
--
-- Changelog:
--   2.1.0 (Feb 2, 2026): Quality system complete - Fully consolidated schema
--      - Migration 017: Test error tracking (last_error_message, execution_time_ms, retry_count)
--      - Migration 018: Epic test failures table with comprehensive tracking
--      - Migration 019: Epic re-testing system (epic_retest_runs, epic_stability_metrics)
--      - Migration 020: Project completion reviews (spec verification)
--      - Cleanup: Removed 17 unused tables and 21 unused views
--      - Note: All migrations consolidated into this file for clarity
--   2.0.0 (Jan 9, 2026): Consolidated with all migrations (011-016) - Production ready
--   2.2.0 (Dec 25, 2025): Added total_time_seconds, removed budget_usd, updated trigger
--   2.1.0 (Dec 23, 2025): Added session heartbeat tracking
--   2.0.0 (Dec 2025): Initial consolidated schema
-- =============================================================================

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- For UUID generation

-- =============================================================================
-- CUSTOM TYPES
-- =============================================================================

-- Project status enum
CREATE TYPE project_status AS ENUM (
    'active',
    'paused',
    'completed',
    'archived'
);

-- Session types
CREATE TYPE session_type AS ENUM (
    'initializer',
    'expansion',
    'coding',
    'review'
);

-- Session status
CREATE TYPE session_status AS ENUM (
    'pending',
    'running',
    'completed',
    'error',
    'interrupted'
);

-- Deployment status
CREATE TYPE deployment_status AS ENUM (
    'local',
    'sandbox',
    'production'
);

-- Task status
CREATE TYPE task_status AS ENUM (
    'pending',
    'in_progress',
    'completed',
    'blocked'
);

-- =============================================================================
-- MAIN TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Projects Table - Central metadata for all projects
-- -----------------------------------------------------------------------------
CREATE TABLE projects (
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
    github_default_branch VARCHAR(100) DEFAULT 'main',

    -- Deployment configuration
    deployment_status deployment_status DEFAULT 'local',
    sandbox_config JSONB DEFAULT '{}',
    api_endpoint TEXT,

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

CREATE INDEX idx_projects_user_id ON projects(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX idx_projects_status ON projects(status);
CREATE INDEX idx_projects_name ON projects(name);
CREATE INDEX idx_projects_metadata ON projects USING GIN (metadata);
CREATE INDEX idx_projects_completed_at ON projects(completed_at);
CREATE INDEX idx_projects_total_time ON projects(total_time_seconds);
CREATE INDEX idx_projects_project_type ON projects(project_type);

COMMENT ON COLUMN projects.project_type IS 'greenfield = new project from scratch, brownfield = modifications to existing codebase';
COMMENT ON COLUMN projects.source_commit_sha IS 'Git commit SHA at import time for brownfield projects, used to track drift';
COMMENT ON COLUMN projects.codebase_analysis IS 'Automated analysis of imported codebase: languages, frameworks, test suite, structure';
COMMENT ON COLUMN projects.completed_at IS 'Timestamp when all epics/tasks/tests were completed. NULL means project is still in progress.';
COMMENT ON COLUMN projects.total_time_seconds IS 'Total time spent on project in seconds, automatically aggregated from session durations';

-- -----------------------------------------------------------------------------
-- Sessions Table - Track all agent sessions
-- -----------------------------------------------------------------------------
CREATE TABLE sessions (
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

CREATE INDEX idx_sessions_project_status ON sessions(project_id, status);
CREATE INDEX idx_sessions_type ON sessions(type);
CREATE INDEX idx_sessions_created_at ON sessions(created_at DESC);
CREATE INDEX idx_sessions_metrics ON sessions USING GIN (metrics);
CREATE INDEX idx_sessions_stale_detection ON sessions (status, last_heartbeat) WHERE status = 'running';

COMMENT ON COLUMN sessions.last_heartbeat IS 'Timestamp of last heartbeat update during session execution. Used to detect truly stale sessions vs. long-running active sessions.';

-- -----------------------------------------------------------------------------
-- Hierarchical Task Management Tables
-- -----------------------------------------------------------------------------

-- Epics Table - High-level feature areas
CREATE TABLE epics (
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

    -- Metadata
    metadata JSONB DEFAULT '{}',

    UNIQUE(project_id, name)
);

CREATE INDEX idx_epics_project_id ON epics(project_id);
CREATE INDEX idx_epics_status ON epics(status);
CREATE INDEX idx_epics_priority ON epics(priority);

-- Tasks Table - Individual implementation steps
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    description TEXT NOT NULL,
    action TEXT,
    priority INTEGER DEFAULT 0,
    done BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Session tracking
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    session_notes TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_tasks_epic_id ON tasks(epic_id);
CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_tasks_done ON tasks(done);
CREATE INDEX idx_tasks_priority ON tasks(priority);
CREATE INDEX idx_tasks_session_id ON tasks(session_id);

-- Task Tests Table - Verification requirements for tasks (renamed from tests)
CREATE TABLE task_tests (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

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
    last_result VARCHAR(20),
    last_execution TIMESTAMPTZ,
    execution_log TEXT,  -- Execution log for debugging
    verification_notes TEXT,  -- Notes from coding agent about verification

    -- Error tracking (Migration 017)
    last_error_message TEXT,
    execution_time_ms INTEGER,
    retry_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    verified_at TIMESTAMPTZ,

    -- Legacy compatibility
    result JSONB DEFAULT '{}',

    CONSTRAINT valid_category CHECK (category IN ('functional', 'style', 'accessibility', 'performance', 'security'))
);

CREATE INDEX idx_task_tests_task_id ON task_tests(task_id);
CREATE INDEX idx_task_tests_project_id ON task_tests(project_id);
CREATE INDEX idx_task_tests_type ON task_tests(test_type);
CREATE INDEX idx_task_tests_task_type ON task_tests(task_id, test_type);
CREATE INDEX idx_task_tests_last_result ON task_tests(last_result);
CREATE INDEX idx_task_tests_passes ON task_tests(passes);
CREATE INDEX idx_task_tests_category ON task_tests(category);

COMMENT ON TABLE task_tests IS 'Test requirements for individual tasks - defines WHAT to test, not HOW';
COMMENT ON COLUMN task_tests.requirements IS 'Test requirements describing what to verify (not how)';
COMMENT ON COLUMN task_tests.success_criteria IS 'Clear criteria for determining test success';
COMMENT ON COLUMN task_tests.verification_notes IS 'Notes from coding agent about how requirements were verified';

-- -----------------------------------------------------------------------------
-- Deep Review Results (Phase 2 Review System)
-- -----------------------------------------------------------------------------
-- Note: Quality metrics now stored in sessions.metrics JSONB field
-- Deep reviews stored in this table for AI-powered analysis

CREATE TABLE session_deep_reviews (
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
    CONSTRAINT unique_session_deep_review UNIQUE (session_id)  -- Each session can have at most one deep review
);

CREATE INDEX idx_deep_reviews_session ON session_deep_reviews(session_id);
CREATE INDEX idx_deep_reviews_created ON session_deep_reviews(created_at DESC);
CREATE INDEX idx_deep_reviews_rating ON session_deep_reviews(overall_rating) WHERE overall_rating IS NOT NULL;
CREATE INDEX idx_deep_reviews_improvements ON session_deep_reviews USING GIN (prompt_improvements);

COMMENT ON TABLE session_deep_reviews IS 'Deep review results for coding sessions. Automated or on-demand Claude-powered reviews for prompt improvement analysis.';
COMMENT ON COLUMN session_deep_reviews.overall_rating IS '1-10 quality score from deep review analysis. May differ from quick check rating.';
COMMENT ON COLUMN session_deep_reviews.review_text IS 'Full markdown review text from Claude, including analysis and recommendations.';
COMMENT ON COLUMN session_deep_reviews.prompt_improvements IS 'Structured list of recommendation strings extracted from review text for aggregation across sessions.';
COMMENT ON CONSTRAINT unique_session_deep_review ON session_deep_reviews IS 'Ensures each session has at most one deep review. If a session needs to be re-reviewed, the existing review should be updated rather than creating a new one.';

-- -----------------------------------------------------------------------------
-- Prompt Improvement System Tables (Phase 4)
-- -----------------------------------------------------------------------------

-- Prompt Improvement Analyses
CREATE TABLE prompt_improvement_analyses (
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
    analysis_model VARCHAR(100) DEFAULT 'claude-sonnet-4-5-20250929',
    sandbox_type VARCHAR(20),

    -- Results
    overall_findings TEXT,
    patterns_identified JSONB DEFAULT '{}',
    proposed_changes JSONB DEFAULT '[]',
    quality_impact_estimate DECIMAL(3,1),

    -- Metadata
    triggered_by VARCHAR(50),
    user_id UUID,
    notes TEXT,

    CONSTRAINT status_valid CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT sandbox_type_valid CHECK (sandbox_type IN ('docker', 'local'))
);

CREATE INDEX idx_prompt_analyses_status ON prompt_improvement_analyses(status);
CREATE INDEX idx_prompt_analyses_created ON prompt_improvement_analyses(created_at DESC);
CREATE INDEX idx_prompt_analyses_sandbox ON prompt_improvement_analyses(sandbox_type);

-- Prompt Proposals
CREATE TABLE prompt_proposals (
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

    -- Additional metadata (diff details, etc.)
    metadata JSONB DEFAULT '{}',

    CONSTRAINT change_type_valid CHECK (change_type IN ('addition', 'modification', 'deletion', 'reorganization')),
    CONSTRAINT status_valid CHECK (status IN ('proposed', 'accepted', 'rejected', 'implemented')),
    CONSTRAINT confidence_valid CHECK (confidence_level BETWEEN 1 AND 10)
);

CREATE INDEX idx_proposals_analysis ON prompt_proposals(analysis_id);
CREATE INDEX idx_proposals_status ON prompt_proposals(status);
CREATE INDEX idx_proposals_file ON prompt_proposals(prompt_file);

COMMENT ON TABLE prompt_improvement_analyses IS 'Stores cross-project prompt improvement analyses';
COMMENT ON TABLE prompt_proposals IS 'Individual prompt change proposals from analyses';

-- Note: github_commits and project_preferences tables removed in Migration 007
-- (GitHub integration never implemented, preferences handled by config files)

-- =============================================================================
-- VIEWS
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Progress View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_progress AS
SELECT
    p.id as project_id,
    p.name as project_name,
    COUNT(DISTINCT e.id) as total_epics,
    COUNT(DISTINCT CASE WHEN e.status = 'completed' THEN e.id END) as completed_epics,
    COUNT(DISTINCT t.id) as total_tasks,
    COUNT(DISTINCT CASE WHEN t.done = true THEN t.id END) as completed_tasks,
    COUNT(DISTINCT test.id) as total_tests,
    COUNT(DISTINCT CASE WHEN test.passes = true THEN test.id END) as passing_tests,
    ROUND(
        CASE
            WHEN COUNT(DISTINCT t.id) > 0
            THEN (COUNT(DISTINCT CASE WHEN t.done = true THEN t.id END)::DECIMAL / COUNT(DISTINCT t.id) * 100)
            ELSE 0
        END, 2
    ) as task_completion_pct,
    ROUND(
        CASE
            WHEN COUNT(DISTINCT test.id) > 0
            THEN (COUNT(DISTINCT CASE WHEN test.passes = true THEN test.id END)::DECIMAL / COUNT(DISTINCT test.id) * 100)
            ELSE 0
        END, 2
    ) as test_pass_pct
FROM projects p
LEFT JOIN epics e ON p.id = e.project_id
LEFT JOIN tasks t ON p.id = t.project_id
LEFT JOIN task_tests test ON p.id = test.project_id
GROUP BY p.id, p.name;

-- -----------------------------------------------------------------------------
-- Next Task View
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_next_task AS
SELECT DISTINCT ON (p.id)
    t.id as task_id,
    t.description,
    t.action,
    e.id as epic_id,
    e.name as epic_name,
    e.description as epic_description,
    p.id as project_id,
    p.name as project_name
FROM projects p
JOIN epics e ON p.id = e.project_id
JOIN tasks t ON e.id = t.epic_id
WHERE t.done = false
    AND e.status != 'completed'
    AND p.status = 'active'
ORDER BY p.id, e.priority, t.priority, t.id;

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

-- Recent Analyses with Summary Stats
CREATE OR REPLACE VIEW v_recent_analyses AS
SELECT
    a.id,
    a.created_at,
    a.completed_at,
    a.status,
    a.sandbox_type,
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

-- Pending Proposals with Analysis Info
CREATE OR REPLACE VIEW v_pending_proposals AS
SELECT
    p.id,
    p.created_at,
    p.prompt_file,
    p.section_name,
    p.change_type,
    p.confidence_level,
    p.rationale,
    a.sandbox_type,
    a.sessions_analyzed,
    CARDINALITY(a.projects_analyzed) as num_projects_analyzed
FROM prompt_proposals p
JOIN prompt_improvement_analyses a ON p.analysis_id = a.id
WHERE p.status = 'proposed'
ORDER BY p.confidence_level DESC, p.created_at DESC;

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
    -- Count existing epics for the project
    SELECT COUNT(*) INTO epic_count
    FROM epics
    WHERE project_id = NEW.project_id;

    -- First session (session_number = 0) must be initializer if no epics exist
    IF NEW.session_number = 0 AND epic_count = 0 AND NEW.type != 'initializer' THEN
        RAISE EXCEPTION 'First session (session_number = 0) must be initializer type when no epics exist';
    END IF;

    -- Can't run initializer if epics already exist
    IF NEW.type = 'initializer' AND epic_count > 0 THEN
        RAISE EXCEPTION 'Cannot run initializer session when epics already exist (% epics found)', epic_count;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_session_type_consistency
    BEFORE INSERT ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION validate_session_type();

COMMENT ON FUNCTION validate_session_type() IS 'Validates session type consistency: First session (session_number=0) must be initializer when no epics exist, and initializer cannot run when epics exist';

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
-- Paused Sessions and Intervention Management
-- ============================================
-- Stores session state when paused due to blockers

-- Table for paused sessions
CREATE TABLE IF NOT EXISTS paused_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Pause information
    paused_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pause_reason TEXT NOT NULL,
    pause_type VARCHAR(50) NOT NULL, -- 'retry_limit', 'critical_error', 'manual', 'timeout'

    -- Current state when paused
    current_task_id INTEGER REFERENCES tasks(id),
    current_task_description TEXT,
    message_count INTEGER,

    -- Blocker details
    blocker_info JSONB NOT NULL DEFAULT '{}',
    retry_stats JSONB NOT NULL DEFAULT '{}',
    error_messages TEXT[],

    -- Resolution tracking
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    resolved_by VARCHAR(255),

    -- Resume information
    can_auto_resume BOOLEAN DEFAULT FALSE,
    resume_prompt TEXT, -- Custom prompt to use when resuming
    resume_context JSONB DEFAULT '{}', -- Additional context for resume

    -- Error tracking (Migration 017)
    last_error_message TEXT,
    execution_time_ms INTEGER,
    retry_count INTEGER DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_active_pause_per_session UNIQUE (session_id, resolved)
);

-- Table for intervention actions taken
CREATE TABLE IF NOT EXISTS intervention_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paused_session_id UUID NOT NULL REFERENCES paused_sessions(id) ON DELETE CASCADE,

    -- Action details
    action_type VARCHAR(50) NOT NULL, -- 'notification_sent', 'auto_recovery', 'manual_fix', 'resumed'
    action_status VARCHAR(20) NOT NULL, -- 'pending', 'success', 'failed'
    action_details JSONB NOT NULL DEFAULT '{}',

    -- Timing
    initiated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Results
    result_message TEXT,
    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table for notification preferences per project
CREATE TABLE IF NOT EXISTS notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Notification channels
    webhook_enabled BOOLEAN DEFAULT FALSE,
    webhook_url TEXT,

    email_enabled BOOLEAN DEFAULT FALSE,
    email_addresses TEXT[],

    sms_enabled BOOLEAN DEFAULT FALSE,
    sms_numbers TEXT[],

    -- Notification triggers
    notify_on_retry_limit BOOLEAN DEFAULT TRUE,
    notify_on_critical_error BOOLEAN DEFAULT TRUE,
    notify_on_timeout BOOLEAN DEFAULT TRUE,
    notify_on_manual_pause BOOLEAN DEFAULT FALSE,

    -- Rate limiting
    min_notification_interval INTEGER DEFAULT 300, -- Minimum seconds between notifications
    last_notification_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_preferences_per_project UNIQUE (project_id)
);

-- Indexes for performance
CREATE INDEX idx_paused_sessions_project ON paused_sessions(project_id);
CREATE INDEX idx_paused_sessions_resolved ON paused_sessions(resolved);
CREATE INDEX idx_paused_sessions_paused_at ON paused_sessions(paused_at DESC);
CREATE INDEX idx_intervention_actions_paused_session ON intervention_actions(paused_session_id);
CREATE INDEX idx_intervention_actions_initiated_at ON intervention_actions(initiated_at DESC);

-- Views for dashboard
CREATE OR REPLACE VIEW v_active_interventions AS
SELECT
    ps.id,
    ps.session_id,
    ps.project_id,
    p.name as project_name,
    ps.paused_at,
    ps.pause_reason,
    ps.pause_type,
    ps.current_task_description,
    ps.blocker_info,
    ps.retry_stats,
    ps.can_auto_resume,
    COALESCE(
        (SELECT COUNT(*)
         FROM intervention_actions ia
         WHERE ia.paused_session_id = ps.id
         AND ia.action_type = 'notification_sent'
         AND ia.action_status = 'success'),
        0
    ) as notifications_sent,
    NOW() - ps.paused_at as time_paused
FROM paused_sessions ps
JOIN projects p ON ps.project_id = p.id
WHERE ps.resolved = FALSE
ORDER BY ps.paused_at DESC;

CREATE OR REPLACE VIEW v_intervention_history AS
SELECT
    ps.id,
    ps.project_id,
    p.name as project_name,
    ps.paused_at,
    ps.pause_type,
    ps.resolved_at,
    ps.resolution_notes,
    ps.resolved_by,
    ps.resolved_at - ps.paused_at as resolution_time,
    array_agg(
        DISTINCT jsonb_build_object(
            'type', ia.action_type,
            'status', ia.action_status,
            'initiated_at', ia.initiated_at
        )
    ) as actions_taken
FROM paused_sessions ps
JOIN projects p ON ps.project_id = p.id
LEFT JOIN intervention_actions ia ON ps.id = ia.paused_session_id
WHERE ps.resolved = TRUE
GROUP BY ps.id, p.id, p.name
ORDER BY ps.resolved_at DESC;

-- Function to pause a session
CREATE OR REPLACE FUNCTION pause_session(
    p_session_id UUID,
    p_project_id UUID,
    p_reason TEXT,
    p_pause_type VARCHAR(50),
    p_blocker_info JSONB DEFAULT '{}',
    p_retry_stats JSONB DEFAULT '{}',
    p_current_task_id INTEGER DEFAULT NULL,
    p_current_task_description TEXT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_paused_session_id UUID;
BEGIN
    INSERT INTO paused_sessions (
        session_id,
        project_id,
        pause_reason,
        pause_type,
        blocker_info,
        retry_stats,
        current_task_id,
        current_task_description
    ) VALUES (
        p_session_id,
        p_project_id,
        p_reason,
        p_pause_type,
        p_blocker_info,
        p_retry_stats,
        p_current_task_id,
        p_current_task_description
    )
    RETURNING id INTO v_paused_session_id;

    -- Update session status
    UPDATE sessions
    SET status = 'paused',
        updated_at = NOW()
    WHERE id = p_session_id;

    RETURN v_paused_session_id;
END;
$$ LANGUAGE plpgsql;

-- Function to resume a session
CREATE OR REPLACE FUNCTION resume_session(
    p_paused_session_id UUID,
    p_resolved_by VARCHAR(255) DEFAULT 'system',
    p_resolution_notes TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
BEGIN
    -- Mark as resolved
    UPDATE paused_sessions
    SET resolved = TRUE,
        resolved_at = NOW(),
        resolved_by = p_resolved_by,
        resolution_notes = p_resolution_notes,
        updated_at = NOW()
    WHERE id = p_paused_session_id
    AND resolved = FALSE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Update session status
    UPDATE sessions
    SET status = 'resumed',
        updated_at = NOW()
    WHERE id = (
        SELECT session_id
        FROM paused_sessions
        WHERE id = p_paused_session_id
    );

    -- Log the resume action
    INSERT INTO intervention_actions (
        paused_session_id,
        action_type,
        action_status,
        action_details,
        completed_at
    ) VALUES (
        p_paused_session_id,
        'resumed',
        'success',
        jsonb_build_object('resolved_by', p_resolved_by),
        NOW()
    );

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;-- Session Checkpoints for Resume Capability
-- ============================================
-- Stores session state at key points for recovery and resumption

-- Checkpoint table - stores session state snapshots
CREATE TABLE IF NOT EXISTS session_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Checkpoint metadata
    checkpoint_number INTEGER NOT NULL, -- Sequential within session (1, 2, 3...)
    checkpoint_type VARCHAR(50) NOT NULL, -- 'task_completion', 'epic_completion', 'manual', 'error'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Session state at checkpoint
    current_task_id INTEGER REFERENCES tasks(id),
    current_epic_id INTEGER REFERENCES epics(id),
    message_count INTEGER NOT NULL DEFAULT 0,
    iteration_count INTEGER NOT NULL DEFAULT 0,

    -- Agent conversation state
    conversation_history JSONB NOT NULL DEFAULT '[]', -- Array of messages
    tool_results_cache JSONB NOT NULL DEFAULT '{}', -- Recent tool results for context

    -- Task progress state
    completed_tasks INTEGER[] DEFAULT '{}', -- Array of completed task IDs
    in_progress_tasks INTEGER[] DEFAULT '{}', -- Array of in-progress task IDs
    blocked_tasks INTEGER[] DEFAULT '{}', -- Array of blocked task IDs

    -- Session metrics snapshot
    metrics_snapshot JSONB NOT NULL DEFAULT '{}',

    -- File system state (for verification)
    files_modified TEXT[], -- List of files modified in this session
    git_commit_sha VARCHAR(40), -- Last git commit at checkpoint

    -- Resumption info
    can_resume_from BOOLEAN DEFAULT TRUE,
    resume_notes TEXT, -- Notes about how to resume from this checkpoint
    invalidated BOOLEAN DEFAULT FALSE, -- Set to true if checkpoint is no longer valid
    invalidation_reason TEXT,

    -- Recovery metadata
    recovery_count INTEGER DEFAULT 0, -- How many times resumed from this checkpoint
    last_resumed_at TIMESTAMPTZ,

    CONSTRAINT unique_checkpoint_per_session UNIQUE (session_id, checkpoint_number),
    CONSTRAINT valid_checkpoint_number CHECK (checkpoint_number > 0),
    CONSTRAINT valid_message_count CHECK (message_count >= 0),
    CONSTRAINT valid_iteration_count CHECK (iteration_count >= 0)
);


-- Indexes for performance
CREATE INDEX idx_checkpoints_session ON session_checkpoints(session_id);
CREATE INDEX idx_checkpoints_project ON session_checkpoints(project_id);
CREATE INDEX idx_checkpoints_created_at ON session_checkpoints(created_at DESC);
CREATE INDEX idx_checkpoints_type ON session_checkpoints(checkpoint_type);
CREATE INDEX idx_checkpoints_can_resume ON session_checkpoints(can_resume_from) WHERE can_resume_from = TRUE;
CREATE INDEX idx_checkpoints_task ON session_checkpoints(current_task_id) WHERE current_task_id IS NOT NULL;


-- View: Resumable checkpoints (valid and not invalidated)
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
    t.description as current_task_description,
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

-- View: Checkpoint recovery history
create a checkpoint
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
    -- Get next checkpoint number for this session
    SELECT COALESCE(MAX(checkpoint_number), 0) + 1
    INTO v_checkpoint_number
    FROM session_checkpoints
    WHERE session_id = p_session_id;

    -- Create the checkpoint
    INSERT INTO session_checkpoints (
        session_id,
        project_id,
        checkpoint_number,
        checkpoint_type,
        current_task_id,
        current_epic_id,
        message_count,
        iteration_count,
        conversation_history,
        tool_results_cache,
        completed_tasks,
        in_progress_tasks,
        blocked_tasks,
        metrics_snapshot,
        files_modified,
        git_commit_sha,
        resume_notes
    ) VALUES (
        p_session_id,
        p_project_id,
        v_checkpoint_number,
        p_checkpoint_type,
        p_current_task_id,
        p_current_epic_id,
        p_message_count,
        p_iteration_count,
        p_conversation_history,
        p_tool_results_cache,
        p_completed_tasks,
        p_in_progress_tasks,
        p_blocked_tasks,
        p_metrics_snapshot,
        p_files_modified,
        p_git_commit_sha,
        p_resume_notes
    )
    RETURNING id INTO v_checkpoint_id;

    RETURN v_checkpoint_id;
END;
$$ LANGUAGE plpgsql;

-- Function to invalidate checkpoints (when state has changed)
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

-- Function to start checkpoint recovery


-- Function to get latest resumable checkpoint for a session
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

-- Trigger to update session status enum to include checkpointing states
-- Note: We're adding 'paused' and 'resumed' to the session_status enum if needed
DO $$
BEGIN
    -- Add 'paused' status if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'paused' AND enumtypid = 'session_status'::regtype) THEN
        ALTER TYPE session_status ADD VALUE 'paused';
    END IF;

    -- Add 'resumed' status if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'resumed' AND enumtypid = 'session_status'::regtype) THEN
        ALTER TYPE session_status ADD VALUE 'resumed';
    END IF;
EXCEPTION
    WHEN duplicate_object THEN
        -- Ignore if values already exist
        NULL;
END$$;

COMMENT ON TABLE session_checkpoints IS 'Stores session state snapshots at key points for recovery and resumption';

COMMENT ON COLUMN session_checkpoints.conversation_history IS 'Full conversation history at checkpoint for context restoration';
COMMENT ON COLUMN session_checkpoints.tool_results_cache IS 'Recent tool results to avoid re-execution';
COMMENT ON COLUMN session_checkpoints.invalidated IS 'Set to true if state has diverged and checkpoint is no longer safe to resume from';

-- Task Verification System Tables


-- Index for quick lookups


-- Index for quick lookups


-- Add verification columns to tasks table
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS review_reason TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verification_attempts INTEGER DEFAULT 0;


-- Function: Get verification summary for a project


-- Function: Mark task as verified
CREATE OR REPLACE FUNCTION mark_task_verified(
    p_task_id INTEGER,
    p_session_id UUID DEFAULT NULL
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE tasks
    SET verified = true,
        verified_at = CURRENT_TIMESTAMP,
        needs_review = false,
        review_reason = NULL,
        session_id = COALESCE(p_session_id, session_id)
    WHERE id = p_task_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation


-- Epic Validation System Tables
-- ===============================


-- Index for quick lookups


-- Index for quick lookups


-- Index for quick lookups


-- Index for dependency lookups


-- Add validation columns to epics table
ALTER TABLE epics ADD COLUMN IF NOT EXISTS validated BOOLEAN DEFAULT FALSE;
ALTER TABLE epics ADD COLUMN IF NOT EXISTS validated_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE epics ADD COLUMN IF NOT EXISTS validation_status VARCHAR(50);
ALTER TABLE epics ADD COLUMN IF NOT EXISTS acceptance_criteria JSONB DEFAULT '[]'::jsonb;


-- Function: Get next epic to validate


-- Function: Mark epic as validated


-- Function: Create epic rework tasks


-- Comments for documentation


COMMENT ON FUNCTION get_next_epic_to_validate IS 'Returns the next epic that should be validated';
COMMENT ON FUNCTION mark_epic_validated IS 'Marks an epic as validated based on validation results';
COMMENT ON FUNCTION create_epic_rework_task IS 'Creates a new rework task when epic validation fails';-- Quality Gates System Tables
-- ============================


-- Index for quick lookups


-- Index for relationships


-- Index for lookups


-- Function: Get quality gate summary for a project


-- Function: Create rework task from quality gate


-- Function: Check if entity passes quality gates


-- Comments for documentation


COMMENT ON FUNCTION get_project_quality_summary IS 'Returns quality gate summary statistics for a project';
COMMENT ON FUNCTION create_quality_rework_task IS 'Creates a rework task when quality gates fail';
COMMENT ON FUNCTION check_quality_gates IS 'Checks if an entity passes quality gate requirements';-- ============================================================================
-- YokeFlow Task Verification System Schema


-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Task verifications indexes


-- Epic validations indexes


-- Generated tests indexes


-- Verification history indexes


-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to get verification pass rate for a project


-- Function to get average retry count for a project


-- Function to mark verification as requiring manual review


-- ============================================================================
-- Comments for Documentation
-- ============================================================================


COMMENT ON FUNCTION get_verification_pass_rate IS 'Calculates the verification pass rate for a given project';
COMMENT ON FUNCTION get_avg_retry_count IS 'Calculates the average retry count for verifications in a project';
COMMENT ON FUNCTION mark_verification_for_manual_review IS 'Marks a verification as requiring manual review with a reason';

-- ============================================================================


-- GRANT SELECT ON v_verification_statistics TO yokeflow_app;
-- GRANT SELECT ON v_epic_validation_summary TO yokeflow_app;
-- GRANT SELECT ON v_test_generation_stats TO yokeflow_app;
-- GRANT SELECT ON v_recent_verification_activity TO yokeflow_app;
-- GRANT SELECT ON v_tasks_requiring_review TO yokeflow_app;
-- GRANT EXECUTE ON FUNCTION get_verification_pass_rate TO yokeflow_app;
-- GRANT EXECUTE ON FUNCTION get_avg_retry_count TO yokeflow_app;
-- GRANT EXECUTE ON FUNCTION mark_verification_for_manual_review TO yokeflow_app;

-- ============================================================================
-- End of Schema
-- ============================================================================

-- ============================================================================
-- MIGRATIONS 017-022: Testing & Quality System Enhancements
-- ============================================================================
-- These migrations were consolidated from individual migration files
-- Date: January 25, 2026

-- ----------------------------------------------------------------------------
-- Migration 017: Enhance tests table for proper test storage and execution
-- ----------------------------------------------------------------------------

-- Add new columns to tests table for proper test management
ALTER TABLE tests ADD COLUMN IF NOT EXISTS test_type VARCHAR(20);
COMMENT ON COLUMN tests.test_type IS 'Type of test: unit, api, browser, database, integration';

ALTER TABLE tests ADD COLUMN IF NOT EXISTS test_code TEXT;
COMMENT ON COLUMN tests.test_code IS 'Actual executable test code/commands';

ALTER TABLE tests ADD COLUMN IF NOT EXISTS last_execution TIMESTAMPTZ;
COMMENT ON COLUMN tests.last_execution IS 'Timestamp of last test execution';

ALTER TABLE tests ADD COLUMN IF NOT EXISTS last_result VARCHAR(20);
COMMENT ON COLUMN tests.last_result IS 'Result of last execution: passed, failed, skipped, error';

ALTER TABLE tests ADD COLUMN IF NOT EXISTS execution_log TEXT;
COMMENT ON COLUMN tests.execution_log IS 'Detailed log of last execution';

-- Add check constraint for valid test types
ALTER TABLE tests DROP CONSTRAINT IF EXISTS chk_test_type;
ALTER TABLE tests ADD CONSTRAINT chk_test_type
CHECK (test_type IN ('unit', 'api', 'browser', 'database', 'integration'));

-- Add check constraint for valid test results
ALTER TABLE tests DROP CONSTRAINT IF EXISTS chk_last_result;
ALTER TABLE tests ADD CONSTRAINT chk_last_result
CHECK (last_result IN ('passed', 'failed', 'skipped', 'error'));

-- Create indexes for faster test lookups by type
CREATE INDEX IF NOT EXISTS idx_tests_type ON tests(test_type);
CREATE INDEX IF NOT EXISTS idx_tests_task_type ON tests(task_id, test_type);
CREATE INDEX IF NOT EXISTS idx_tests_last_result ON tests(last_result);

-- Update existing tests to have a default test_type based on category
UPDATE tests
SET test_type = CASE
    WHEN category = 'functional' THEN 'integration'
    WHEN category = 'style' THEN 'unit'
    WHEN category = 'accessibility' THEN 'browser'
    WHEN category = 'performance' THEN 'api'
    ELSE 'integration'
END
WHERE test_type IS NULL;

-- ----------------------------------------------------------------------------
-- Migration 018: Create epic_tests table for integration testing
-- ----------------------------------------------------------------------------

-- Create table for epic-level integration tests
CREATE TABLE IF NOT EXISTS epic_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    project_id UUID NOT NULL,

    -- Test details
    name VARCHAR(255) NOT NULL,
    description TEXT,
    test_type VARCHAR(20) DEFAULT 'integration',
    
    -- Requirements-based approach (replaces test_code)
    requirements TEXT,  -- Integration test requirements for the epic
    success_criteria TEXT,  -- Clear criteria for epic test success
    key_verification_points JSONB,  -- Array of key points to verify in the workflow
    verification_notes TEXT,  -- Notes about how epic was verified

    -- Task dependencies
    depends_on_tasks INTEGER[], -- Array of task IDs that must be complete

    -- Execution tracking
    last_execution TIMESTAMPTZ,
    last_result VARCHAR(20),
    execution_log TEXT,
    execution_count INTEGER DEFAULT 0,

    -- Success metrics
    pass_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    skip_count INTEGER DEFAULT 0,

    -- Error tracking (Migration 017)
    last_error_message TEXT,
    execution_time_ms INTEGER,
    retry_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Session tracking
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

    -- Foreign key for project
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,

    -- Constraints
    CONSTRAINT chk_epic_test_type
        CHECK (test_type IN ('integration', 'e2e', 'workflow')),
    CONSTRAINT chk_epic_last_result
        CHECK (last_result IN ('passed', 'failed', 'skipped', 'error'))
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_epic_tests_epic_id ON epic_tests(epic_id);
CREATE INDEX IF NOT EXISTS idx_epic_tests_project_id ON epic_tests(project_id);
CREATE INDEX IF NOT EXISTS idx_epic_tests_last_result ON epic_tests(last_result);
CREATE INDEX IF NOT EXISTS idx_epic_tests_test_type ON epic_tests(test_type);

-- Create GIN index for task dependencies array searches
CREATE INDEX IF NOT EXISTS idx_epic_tests_depends_on_tasks ON epic_tests USING GIN (depends_on_tasks);

-- Add comments
COMMENT ON TABLE epic_tests IS 'Integration test requirements for epics - end-to-end workflow verification';
COMMENT ON COLUMN epic_tests.depends_on_tasks IS 'Array of task UUIDs that must be complete before running this test';
COMMENT ON COLUMN epic_tests.test_type IS 'Type of epic test: integration, e2e, workflow';
COMMENT ON COLUMN epic_tests.requirements IS 'Integration test requirements for the epic';
COMMENT ON COLUMN epic_tests.success_criteria IS 'Clear criteria for epic test success';
COMMENT ON COLUMN epic_tests.key_verification_points IS 'Array of key points to verify in the workflow';
COMMENT ON COLUMN epic_tests.verification_notes IS 'Notes about how epic was verified';


-- Create function to check if epic test dependencies are met
CREATE OR REPLACE FUNCTION epic_test_dependencies_met(test_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    depends_on INTEGER[];
    task_id_val INTEGER;
    task_done BOOLEAN;
BEGIN
    -- Get the task dependencies
    SELECT depends_on_tasks INTO depends_on
    FROM epic_tests
    WHERE id = test_id;

    -- If no dependencies, they're met
    IF depends_on IS NULL OR array_length(depends_on, 1) IS NULL THEN
        RETURN TRUE;
    END IF;

    -- Check each dependency
    FOREACH task_id_val IN ARRAY depends_on
    LOOP
        -- Check if task is done
        SELECT done INTO task_done
        FROM tasks
        WHERE id = task_id_val;

        -- If any task is not done, dependencies not met
        IF task_done IS NULL OR task_done = FALSE THEN
            RETURN FALSE;
        END IF;
    END LOOP;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Create view for runnable epic tests (dependencies met) - updated for requirements-based approach
CREATE OR REPLACE VIEW v_runnable_epic_tests AS
SELECT * FROM v_epic_tests_status
WHERE dependencies_met = true
AND epic_status = 'completed';

-- ----------------------------------------------------------------------------
-- Migration 019: Update progress view to include epic test counts
-- ----------------------------------------------------------------------------

-- Drop the existing view first
DROP VIEW IF EXISTS v_progress CASCADE;

-- Create the enhanced progress view with epic test counts
CREATE OR REPLACE VIEW v_progress AS
SELECT
    p.id as project_id,
    p.name as project_name,
    COUNT(DISTINCT e.id) as total_epics,
    COUNT(DISTINCT CASE WHEN e.status = 'completed' THEN e.id END) as completed_epics,
    COUNT(DISTINCT t.id) as total_tasks,
    COUNT(DISTINCT CASE WHEN t.done = true THEN t.id END) as completed_tasks,
    -- Task tests (from tests table)
    COUNT(DISTINCT test.id) as total_task_tests,
    COUNT(DISTINCT CASE WHEN test.passes = true THEN test.id END) as passing_task_tests,
    -- Epic tests (from epic_tests table)
    COUNT(DISTINCT et.id) as total_epic_tests,
    COUNT(DISTINCT CASE WHEN et.last_result = 'passed' THEN et.id END) as passing_epic_tests,
    -- Total tests (combined)
    COUNT(DISTINCT test.id) + COUNT(DISTINCT et.id) as total_tests,
    COUNT(DISTINCT CASE WHEN test.passes = true THEN test.id END) +
        COUNT(DISTINCT CASE WHEN et.last_result = 'passed' THEN et.id END) as passing_tests,
    -- Percentages
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
                   COUNT(DISTINCT CASE WHEN et.last_result = 'passed' THEN et.id END))::DECIMAL /
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

-- Add comment describing the view
COMMENT ON VIEW v_progress IS 'Project progress metrics including task tests and epic tests separately';

-- -----------------------------------------------------------------------------
-- Functions for requirements-based testing (from Migration 023)
-- -----------------------------------------------------------------------------

-- Function to get test requirements for a task
CREATE OR REPLACE FUNCTION get_task_test_requirements(p_task_id INTEGER)
RETURNS TABLE (
    test_id INTEGER,
    description TEXT,
    requirements TEXT,
    success_criteria TEXT,
    test_type VARCHAR(20),
    steps JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        tt.id,
        tt.description,
        tt.requirements,
        tt.success_criteria,
        tt.test_type,
        tt.steps
    FROM task_tests tt
    WHERE tt.task_id = p_task_id
    ORDER BY tt.created_at;
END;
$$ LANGUAGE plpgsql;

-- Function to get epic test requirements
CREATE OR REPLACE FUNCTION get_epic_test_requirements(p_epic_id INTEGER)
RETURNS TABLE (
    test_id UUID,
    name VARCHAR(255),
    description TEXT,
    requirements TEXT,
    success_criteria TEXT,
    key_verification_points JSONB,
    depends_on_tasks INTEGER[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        et.id,
        et.name,
        et.description,
        et.requirements,
        et.success_criteria,
        et.key_verification_points,
        et.depends_on_tasks
    FROM epic_tests et
    WHERE et.epic_id = p_epic_id
    ORDER BY et.created_at;
END;
$$ LANGUAGE plpgsql;

-- View for test requirements summary
CREATE OR REPLACE VIEW v_test_requirements AS
SELECT
    'task' as test_level,
    tt.id::text,
    tt.task_id::text as parent_id,
    tt.description,
    tt.requirements,
    tt.success_criteria,
    tt.test_type,
    tt.last_result,
    tt.passes
FROM task_tests tt
UNION ALL
SELECT
    'epic' as test_level,
    et.id::text,
    et.epic_id::text as parent_id,
    et.description,
    et.requirements,
    et.success_criteria,
    et.test_type,
    et.last_result,
    CASE WHEN et.last_result = 'passed' THEN true ELSE false END as passes
FROM epic_tests et;

-- View for task tests (replaces old tests references)
CREATE OR REPLACE VIEW v_task_tests AS
SELECT
    tt.id,
    tt.task_id,
    tt.project_id,
    tt.category,
    tt.test_type,
    tt.description,
    tt.requirements,
    tt.success_criteria,
    tt.steps,
    tt.passes,
    tt.last_result,
    tt.last_execution,
    tt.verification_notes,
    t.description as task_name,
    t.epic_id,
    e.name as epic_name
FROM task_tests tt
JOIN tasks t ON tt.task_id = t.id
JOIN epics e ON t.epic_id = e.id;


-- 


-- Create view for test reliability metrics
Create function to record test execution


-- Create view for session test summary


-- Add comment describing the system


-- ----------------------------------------------------------------------------
-- Migration 021: Add epic test interventions and policy tracking
-- ----------------------------------------------------------------------------

-- Add epic testing mode to projects
ALTER TABLE projects ADD COLUMN IF NOT EXISTS epic_testing_mode VARCHAR(20)
  DEFAULT 'autonomous'
  CHECK (epic_testing_mode IN ('strict', 'autonomous'));

-- Create table for tracking epic test interventions
CREATE TABLE IF NOT EXISTS epic_test_interventions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_id INTEGER REFERENCES epics(id),
    session_id UUID REFERENCES sessions(id),
    failure_count INTEGER NOT NULL,
    blocked BOOLEAN NOT NULL DEFAULT false,
    notification_sent BOOLEAN DEFAULT false,
    checkpoint_id UUID,
    resolution_notes TEXT,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for finding active interventions
CREATE INDEX IF NOT EXISTS idx_epic_interventions_active
ON epic_test_interventions (epic_id, blocked)
WHERE blocked = true AND resolved_at IS NULL;

-- Index for session lookup
CREATE INDEX IF NOT EXISTS idx_epic_interventions_session
ON epic_test_interventions (session_id);

-- View for active epic test interventions
CREATE OR REPLACE VIEW v_active_epic_interventions AS
SELECT
    eti.id as intervention_id,
    e.id as epic_id,
    e.name as epic_name,
    p.name as project_name,
    s.session_number,
    eti.failure_count,
    eti.blocked,
    eti.notification_sent,
    eti.created_at,
    EXTRACT(EPOCH FROM (NOW() - eti.created_at)) / 60 as minutes_blocked
FROM epic_test_interventions eti
JOIN epics e ON eti.epic_id = e.id
JOIN projects p ON e.project_id = p.id
LEFT JOIN sessions s ON eti.session_id = s.id
WHERE eti.blocked = true
  AND eti.resolved_at IS NULL
ORDER BY eti.created_at DESC;

-- View for epic test intervention history
CREATE OR REPLACE VIEW v_epic_intervention_history AS
SELECT
    p.name as project_name,
    e.name as epic_name,
    COUNT(*) as intervention_count,
    SUM(CASE WHEN eti.blocked THEN 1 ELSE 0 END) as times_blocked,
    AVG(eti.failure_count) as avg_failure_count,
    MAX(eti.created_at) as last_intervention,
    SUM(CASE WHEN eti.notification_sent THEN 1 ELSE 0 END) as notifications_sent
FROM epic_test_interventions eti
JOIN epics e ON eti.epic_id = e.id
JOIN projects p ON e.project_id = p.id
GROUP BY p.name, e.name
ORDER BY intervention_count DESC;

-- Function to resolve an epic test intervention
CREATE OR REPLACE FUNCTION resolve_epic_intervention(
    p_intervention_id UUID,
    p_resolution_notes TEXT
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE epic_test_interventions
    SET
        blocked = false,
        resolved_at = NOW(),
        resolution_notes = p_resolution_notes,
        updated_at = NOW()
    WHERE id = p_intervention_id
      AND resolved_at IS NULL;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Add comment
COMMENT ON TABLE epic_test_interventions IS 'Tracks epic test failures that require intervention based on testing policy (strict/autonomous modes)';
COMMENT ON COLUMN epic_test_interventions.blocked IS 'Whether the epic is currently blocked waiting for intervention';
COMMENT ON COLUMN epic_test_interventions.checkpoint_id IS 'Optional checkpoint ID for session recovery after intervention';

-- ----------------------------------------------------------------------------
-- Migration 022: Add blocked status to session_status enum
-- ----------------------------------------------------------------------------

-- Add 'blocked' status to session_status enum for epic test interventions
-- Note: ALTER TYPE ADD VALUE cannot be run in a transaction, so this may need
-- to be run separately if applying within a transaction
DO $$ 
BEGIN
    -- Check if 'blocked' value already exists in the enum
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_enum 
        WHERE enumlabel = 'blocked' 
        AND enumtypid = 'session_status'::regtype
    ) THEN
        ALTER TYPE session_status ADD VALUE 'blocked' AFTER 'interrupted';
    END IF;
END $$;

-- Add comment explaining the new status
COMMENT ON TYPE session_status IS 'Session status: pending (not started), running (active), completed (finished successfully), error (failed), interrupted (stopped by user), blocked (epic test intervention required)';

-- =============================================================================
-- QUALITY SYSTEM TABLES (Migrations 018-020)
-- =============================================================================
-- Integrated: February 2, 2026
-- Source: schema/postgresql/migrations/
-- Note: Migration 017 fields already added to task_tests and epic_tests above

-- -----------------------------------------------------------------------------
-- Migration 017: Test Error Tracking Indexes
-- -----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_task_tests_execution_time
  ON task_tests(execution_time_ms DESC)
  WHERE execution_time_ms IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_epic_tests_execution_time
  ON epic_tests(execution_time_ms DESC)
  WHERE execution_time_ms IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_task_tests_retry_count
  ON task_tests(retry_count DESC)
  WHERE retry_count > 0;

CREATE INDEX IF NOT EXISTS idx_epic_tests_retry_count
  ON epic_tests(retry_count DESC)
  WHERE retry_count > 0;

-- -----------------------------------------------------------------------------
-- Migration 018: Epic Test Failures
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS epic_test_failures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    epic_test_id UUID NOT NULL REFERENCES epic_tests(id) ON DELETE CASCADE,
    epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id),
    intervention_id UUID REFERENCES epic_test_interventions(id),  -- Link to intervention if one was created

    -- Failure details (from Phase 1 error tracking pattern)
    error_message TEXT,  -- Brief error for UI display
    full_error_log TEXT,  -- Complete error output for debugging
    execution_time_ms INTEGER,  -- Performance tracking

    -- Test context
    test_description TEXT,  -- What was being tested
    test_requirements JSONB,  -- Original test requirements for comparison
    verification_notes TEXT,  -- Agent's verification notes at time of failure

    -- Failure classification
    failure_type VARCHAR(50),  -- 'test_quality', 'implementation', 'infrastructure', 'flaky', 'timeout', 'unknown'
    failure_category VARCHAR(50),  -- 'assertion', 'timeout', 'crash', 'network', 'dependency', 'other'
    is_flaky BOOLEAN DEFAULT false,  -- Detected as flaky (passed before, failed now)

    -- Agent behavior tracking
    retry_attempt INTEGER DEFAULT 1,  -- Which retry attempt (1 = first failure, 2 = first retry, etc.)
    agent_diagnosis TEXT,  -- Agent's understanding of the failure
    attempted_fixes JSONB,  -- Array of fixes the agent tried (for learning)

    -- Analysis flags (for pattern detection)
    poor_test_quality_indicator BOOLEAN DEFAULT false,  -- Flag for potential poor test creation
    implementation_gap_indicator BOOLEAN DEFAULT false,  -- Flag for potential implementation issues

    -- Context snapshot
    files_modified JSONB,  -- Files changed in the task
    environment_info JSONB,  -- Docker/local, versions, etc.

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT valid_failure_type CHECK (failure_type IN
        ('test_quality', 'implementation', 'infrastructure', 'flaky', 'timeout', 'unknown')),
    CONSTRAINT valid_failure_category CHECK (failure_category IN
        ('assertion', 'timeout', 'crash', 'network', 'dependency', 'other')),
    CONSTRAINT valid_retry_attempt CHECK (retry_attempt >= 1)
);

-- -----------------------------------------------------------------------------
-- Indexes for Performance
-- -----------------------------------------------------------------------------

-- Common query patterns
CREATE INDEX idx_epic_test_failures_epic ON epic_test_failures(epic_id);
CREATE INDEX idx_epic_test_failures_session ON epic_test_failures(session_id);
CREATE INDEX idx_epic_test_failures_test ON epic_test_failures(epic_test_id);
CREATE INDEX idx_epic_test_failures_type ON epic_test_failures(failure_type);
CREATE INDEX idx_epic_test_failures_created ON epic_test_failures(created_at DESC);

-- Analysis indexes
CREATE INDEX idx_epic_test_failures_flaky ON epic_test_failures(is_flaky)
    WHERE is_flaky = true;
CREATE INDEX idx_epic_test_failures_poor_quality ON epic_test_failures(poor_test_quality_indicator)
    WHERE poor_test_quality_indicator = true;
CREATE INDEX idx_epic_test_failures_impl_gap ON epic_test_failures(implementation_gap_indicator)
    WHERE implementation_gap_indicator = true;

-- -----------------------------------------------------------------------------
-- Analysis Views
-- -----------------------------------------------------------------------------

-- View: Test Quality Issues (potential poor test creation)
CREATE OR REPLACE VIEW v_poor_test_quality_analysis AS
SELECT
    et.id as test_id,
    et.description as test_description,
    e.name as epic_name,
    p.name as project_name,
    COUNT(etf.id) as total_failures,
    COUNT(CASE WHEN etf.failure_type = 'test_quality' THEN 1 END) as quality_failures,
    COUNT(CASE WHEN etf.is_flaky THEN 1 END) as flaky_count,
    AVG(etf.retry_attempt) as avg_retry_attempt,
    array_agg(DISTINCT etf.failure_category ORDER BY etf.failure_category) as failure_categories,
    MAX(etf.created_at) as last_failure,
    MIN(etf.created_at) as first_failure
FROM epic_test_failures etf
JOIN epic_tests et ON etf.epic_test_id = et.id
JOIN epics e ON et.epic_id = e.id
JOIN projects p ON e.project_id = p.id
WHERE etf.poor_test_quality_indicator = true
   OR etf.is_flaky = true
GROUP BY et.id, et.description, e.name, p.name
HAVING COUNT(etf.id) > 2  -- Failed at least 3 times
ORDER BY total_failures DESC, flaky_count DESC;

-- View: Epic Test Reliability Score
CREATE OR REPLACE VIEW v_epic_test_reliability AS
SELECT
    et.id as test_id,
    et.description,
    e.name as epic_name,
    p.name as project_name,
    et.last_result,
    COUNT(etf.id) as total_failures,
    COUNT(CASE WHEN etf.is_flaky THEN 1 END) as flaky_count,
    MAX(etf.retry_attempt) as max_retry_attempt,
    AVG(etf.execution_time_ms) as avg_execution_time_ms,
    -- Reliability score: 1.0 = perfect (no failures), 0.0 = always fails
    CASE
        WHEN et.retry_count = 0 THEN 1.0  -- Never failed
        ELSE GREATEST(0.0, 1.0 - (COUNT(etf.id)::FLOAT / (et.retry_count + 1)))
    END as reliability_score,
    MAX(etf.created_at) as last_failure_at
FROM epic_tests et
LEFT JOIN epic_test_failures etf ON et.id = etf.epic_test_id
JOIN epics e ON et.epic_id = e.id
JOIN projects p ON e.project_id = p.id
GROUP BY et.id, et.description, e.name, p.name, et.last_result, et.retry_count
ORDER BY reliability_score ASC, total_failures DESC;

-- View: Failure Pattern Analysis
CREATE OR REPLACE VIEW v_failure_pattern_analysis AS
SELECT
    failure_type,
    failure_category,
    COUNT(*) as occurrence_count,
    COUNT(DISTINCT epic_id) as affected_epics,
    COUNT(DISTINCT session_id) as affected_sessions,
    AVG(retry_attempt) as avg_retry_attempt,
    AVG(execution_time_ms) as avg_execution_time_ms,
    COUNT(CASE WHEN is_flaky THEN 1 END) as flaky_count,
    COUNT(CASE WHEN poor_test_quality_indicator THEN 1 END) as poor_quality_count,
    COUNT(CASE WHEN implementation_gap_indicator THEN 1 END) as impl_gap_count,
    MIN(created_at) as first_occurrence,
    MAX(created_at) as last_occurrence
FROM epic_test_failures
GROUP BY failure_type, failure_category
ORDER BY occurrence_count DESC;

-- View: Agent Retry Behavior
CREATE OR REPLACE VIEW v_agent_retry_behavior AS
SELECT
    session_id,
    COUNT(*) as failures_encountered,
    AVG(retry_attempt) as avg_retry_attempt,
    MAX(retry_attempt) as max_retry_attempt,
    COUNT(CASE WHEN retry_attempt = 1 THEN 1 END) as first_attempt_failures,
    COUNT(CASE WHEN retry_attempt > 1 THEN 1 END) as retry_failures,
    COUNT(CASE WHEN retry_attempt > 3 THEN 1 END) as stubborn_failures,
    COUNT(DISTINCT epic_id) as unique_epics_affected,
    AVG(execution_time_ms) as avg_test_execution_time
FROM epic_test_failures
WHERE session_id IS NOT NULL
GROUP BY session_id
ORDER BY failures_encountered DESC;

-- View: Flaky Test Detection
CREATE OR REPLACE VIEW v_flaky_tests AS
SELECT
    et.id as test_id,
    et.description,
    e.name as epic_name,
    p.name as project_name,
    COUNT(etf.id) as total_failures,
    COUNT(DISTINCT etf.session_id) as failed_in_sessions,
    MAX(etf.created_at) as last_failure,
    array_agg(DISTINCT etf.error_message ORDER BY etf.error_message) as unique_errors
FROM epic_test_failures etf
JOIN epic_tests et ON etf.epic_test_id = et.id
JOIN epics e ON et.epic_id = e.id
JOIN projects p ON e.project_id = p.id
WHERE etf.is_flaky = true
GROUP BY et.id, et.description, e.name, p.name
ORDER BY total_failures DESC;

-- -----------------------------------------------------------------------------
-- Helper Functions
-- -----------------------------------------------------------------------------

-- Function to record an epic test failure
CREATE OR REPLACE FUNCTION record_epic_test_failure(
    p_epic_test_id UUID,
    p_session_id UUID,
    p_error_message TEXT,
    p_full_error_log TEXT DEFAULT NULL,
    p_execution_time_ms INTEGER DEFAULT NULL,
    p_verification_notes TEXT DEFAULT NULL,
    p_failure_type VARCHAR(50) DEFAULT 'unknown',
    p_failure_category VARCHAR(50) DEFAULT 'other',
    p_agent_diagnosis TEXT DEFAULT NULL,
    p_attempted_fixes JSONB DEFAULT NULL,
    p_environment_info JSONB DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_epic_id INTEGER;
    v_test_description TEXT;
    v_test_requirements JSONB;
    v_retry_attempt INTEGER;
    v_is_flaky BOOLEAN;
    v_failure_id UUID;
BEGIN
    -- Get epic test details
    SELECT epic_id, description, requirements, retry_count + 1
    INTO v_epic_id, v_test_description, v_test_requirements, v_retry_attempt
    FROM epic_tests
    WHERE id = p_epic_test_id;

    IF v_epic_id IS NULL THEN
        RAISE EXCEPTION 'Epic test % not found', p_epic_test_id;
    END IF;

    -- Detect if this is a flaky test (passed before, failing now)
    SELECT EXISTS (
        SELECT 1 FROM epic_tests
        WHERE id = p_epic_test_id
        AND last_result = 'passed'
        AND retry_count > 0
    ) INTO v_is_flaky;

    -- Insert failure record
    INSERT INTO epic_test_failures (
        epic_test_id,
        epic_id,
        session_id,
        error_message,
        full_error_log,
        execution_time_ms,
        test_description,
        test_requirements,
        verification_notes,
        failure_type,
        failure_category,
        is_flaky,
        retry_attempt,
        agent_diagnosis,
        attempted_fixes,
        environment_info
    ) VALUES (
        p_epic_test_id,
        v_epic_id,
        p_session_id,
        p_error_message,
        p_full_error_log,
        p_execution_time_ms,
        v_test_description,
        v_test_requirements,
        p_verification_notes,
        p_failure_type,
        p_failure_category,
        v_is_flaky,
        v_retry_attempt,
        p_agent_diagnosis,
        p_attempted_fixes,
        p_environment_info
    ) RETURNING id INTO v_failure_id;

    RETURN v_failure_id;
END;
$$ LANGUAGE plpgsql;

-- Function to mark a failure as poor test quality
CREATE OR REPLACE FUNCTION flag_poor_test_quality(
    p_failure_id UUID,
    p_reason TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE epic_test_failures
    SET
        poor_test_quality_indicator = true,
        agent_diagnosis = COALESCE(agent_diagnosis || E'\n\n', '') ||
                         'FLAGGED AS POOR TEST QUALITY: ' || COALESCE(p_reason, 'Manual flag')
    WHERE id = p_failure_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function to mark a failure as implementation gap
CREATE OR REPLACE FUNCTION flag_implementation_gap(
    p_failure_id UUID,
    p_reason TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE epic_test_failures
    SET
        implementation_gap_indicator = true,
        agent_diagnosis = COALESCE(agent_diagnosis || E'\n\n', '') ||
                         'FLAGGED AS IMPLEMENTATION GAP: ' || COALESCE(p_reason, 'Manual flag')
    WHERE id = p_failure_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- Comments
-- -----------------------------------------------------------------------------

COMMENT ON TABLE epic_test_failures IS
    'Records every epic test failure for pattern analysis and quality improvement. Complements epic_tests.last_error_message (Phase 1) and epic_test_interventions (Phase 2).';

COMMENT ON COLUMN epic_test_failures.retry_attempt IS
    'Which retry attempt: 1 = first failure, 2 = first retry, 3 = second retry, etc.';

COMMENT ON COLUMN epic_test_failures.is_flaky IS
    'Detected as flaky: test previously passed but now failing';

COMMENT ON COLUMN epic_test_failures.poor_test_quality_indicator IS
    'Flag indicating this failure may be due to poorly written test requirements';

COMMENT ON COLUMN epic_test_failures.implementation_gap_indicator IS
    'Flag indicating this failure may be due to incomplete/incorrect implementation';

COMMENT ON COLUMN epic_test_failures.attempted_fixes IS
    'JSONB array of fixes the agent tried: useful for learning patterns';

COMMENT ON FUNCTION record_epic_test_failure IS
    'Records an epic test failure with full context. Auto-detects flaky tests and calculates retry attempt.';

-- -----------------------------------------------------------------------------
-- Migration 019: Epic Re-testing System
-- -----------------------------------------------------------------------------

CREATE TABLE epic_retest_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
  triggered_by_epic_id INTEGER REFERENCES epics(id) ON DELETE SET NULL,
  session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
  test_result TEXT NOT NULL CHECK (test_result IN ('passed', 'failed', 'skipped', 'error')),
  is_regression BOOLEAN DEFAULT FALSE,
  execution_time_ms INTEGER,
  error_details TEXT,
  tests_run INTEGER DEFAULT 0,
  tests_passed INTEGER DEFAULT 0,
  tests_failed INTEGER DEFAULT 0,
  selection_reason TEXT,  -- 'foundation', 'dependency', 'age', 'random'
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: epic_stability_metrics
-- Aggregated stability metrics per epic for quick analysis
CREATE TABLE epic_stability_metrics (
  epic_id INTEGER PRIMARY KEY REFERENCES epics(id) ON DELETE CASCADE,
  total_retests INTEGER NOT NULL DEFAULT 0,
  passed_retests INTEGER NOT NULL DEFAULT 0,
  failed_retests INTEGER NOT NULL DEFAULT 0,
  regression_count INTEGER NOT NULL DEFAULT 0,
  stability_score DECIMAL(3,2),  -- 0.00-1.00 (passed_retests / total_retests)
  avg_execution_time_ms INTEGER,
  last_retest_at TIMESTAMPTZ,
  last_retest_result TEXT CHECK (last_retest_result IN ('passed', 'failed', 'skipped', 'error')),
  last_regression_at TIMESTAMPTZ,
  last_regression_by_epic_id INTEGER REFERENCES epics(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_epic_retest_runs_epic_id ON epic_retest_runs(epic_id);
CREATE INDEX idx_epic_retest_runs_triggered_by ON epic_retest_runs(triggered_by_epic_id);
CREATE INDEX idx_epic_retest_runs_session_id ON epic_retest_runs(session_id);
CREATE INDEX idx_epic_retest_runs_result ON epic_retest_runs(test_result);
CREATE INDEX idx_epic_retest_runs_regression ON epic_retest_runs(is_regression) WHERE is_regression = TRUE;
CREATE INDEX idx_epic_retest_runs_created_at ON epic_retest_runs(created_at DESC);
CREATE INDEX idx_epic_stability_metrics_score ON epic_stability_metrics(stability_score);
CREATE INDEX idx_epic_stability_metrics_last_retest ON epic_stability_metrics(last_retest_at DESC);

-- View: v_epic_retest_history
-- Comprehensive re-test history with epic details
CREATE VIEW v_epic_retest_history AS
SELECT
  err.id AS retest_id,
  err.epic_id,
  e.name AS epic_name,
  e.status AS epic_status,
  err.triggered_by_epic_id,
  te.name AS triggered_by_epic_name,
  err.session_id,
  err.test_result,
  err.is_regression,
  err.execution_time_ms,
  err.error_details,
  err.tests_run,
  err.tests_passed,
  err.tests_failed,
  err.selection_reason,
  err.created_at,
  -- Calculate days since epic was last worked on
  EXTRACT(DAY FROM (err.created_at - e.updated_at)) AS days_since_epic_updated
FROM epic_retest_runs err
JOIN epics e ON err.epic_id = e.id
LEFT JOIN epics te ON err.triggered_by_epic_id = te.id
ORDER BY err.created_at DESC;

-- View: v_epic_stability_summary
-- Epic stability metrics with current status
CREATE VIEW v_epic_stability_summary AS
SELECT
  esm.epic_id,
  e.name AS epic_name,
  e.status AS epic_status,
  e.order_index,
  esm.total_retests,
  esm.passed_retests,
  esm.failed_retests,
  esm.regression_count,
  esm.stability_score,
  CASE
    WHEN esm.stability_score >= 0.95 THEN 'excellent'
    WHEN esm.stability_score >= 0.80 THEN 'good'
    WHEN esm.stability_score >= 0.60 THEN 'fair'
    ELSE 'poor'
  END AS stability_rating,
  esm.avg_execution_time_ms,
  esm.last_retest_at,
  esm.last_retest_result,
  esm.last_regression_at,
  esm.last_regression_by_epic_id,
  lre.name AS last_regression_by_epic_name,
  -- Calculate staleness (days since last re-test)
  EXTRACT(DAY FROM (NOW() - esm.last_retest_at)) AS days_since_retest
FROM epic_stability_metrics esm
JOIN epics e ON esm.epic_id = e.id
LEFT JOIN epics lre ON esm.last_regression_by_epic_id = lre.id
ORDER BY e.order_index;

-- View: v_regressions_by_epic
-- Which epics are causing regressions in other epics
CREATE VIEW v_regressions_by_epic AS
SELECT
  err.triggered_by_epic_id AS epic_id,
  te.name AS epic_name,
  COUNT(*) AS regressions_caused,
  COUNT(DISTINCT err.epic_id) AS epics_broken,
  MAX(err.created_at) AS last_regression_caused,
  ARRAY_AGG(DISTINCT e.name) AS broken_epic_names
FROM epic_retest_runs err
JOIN epics e ON err.epic_id = e.id
JOIN epics te ON err.triggered_by_epic_id = te.id
WHERE err.is_regression = TRUE
GROUP BY err.triggered_by_epic_id, te.name
ORDER BY regressions_caused DESC;

-- View: v_foundation_epic_retest_schedule
-- Identify foundation epics that need re-testing based on age
CREATE VIEW v_foundation_epic_retest_schedule AS
SELECT
  e.id AS epic_id,
  e.name AS epic_name,
  e.order_index,
  esm.last_retest_at,
  EXTRACT(DAY FROM (NOW() - COALESCE(esm.last_retest_at, e.completed_at))) AS days_since_last_test,
  esm.stability_score,
  -- Identify foundation epics (first 3 epics typically contain database, API, auth)
  CASE WHEN e.order_index <= 3 THEN TRUE ELSE FALSE END AS is_foundation,
  -- Priority score (higher = more urgent to re-test)
  CASE
    WHEN esm.last_retest_at IS NULL THEN 100  -- Never tested
    WHEN EXTRACT(DAY FROM (NOW() - esm.last_retest_at)) > 7 THEN 50  -- Over 7 days
    WHEN esm.stability_score < 0.80 THEN 30  -- Low stability
    ELSE 10
  END AS retest_priority
FROM epics e
LEFT JOIN epic_stability_metrics esm ON e.id = esm.epic_id
WHERE e.status = 'complete'
  AND e.order_index <= 5  -- Focus on first 5 epics (typically foundations)
ORDER BY retest_priority DESC, e.order_index;

-- Function: record_epic_retest
-- Helper function to record a re-test run and update metrics
CREATE OR REPLACE FUNCTION record_epic_retest(
  p_epic_id INTEGER,
  p_triggered_by_epic_id INTEGER,
  p_session_id UUID,
  p_test_result TEXT,
  p_is_regression BOOLEAN,
  p_execution_time_ms INTEGER DEFAULT NULL,
  p_error_details TEXT DEFAULT NULL,
  p_tests_run INTEGER DEFAULT 0,
  p_tests_passed INTEGER DEFAULT 0,
  p_tests_failed INTEGER DEFAULT 0,
  p_selection_reason TEXT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
  v_retest_id UUID;
  v_previous_result TEXT;
BEGIN
  -- Get previous test result to detect regressions
  SELECT test_result INTO v_previous_result
  FROM epic_retest_runs
  WHERE epic_id = p_epic_id
  ORDER BY created_at DESC
  LIMIT 1;

  -- Auto-detect regression if previous was passing and now failing
  IF v_previous_result = 'passed' AND p_test_result IN ('failed', 'error') THEN
    p_is_regression := TRUE;
  END IF;

  -- Insert re-test run
  INSERT INTO epic_retest_runs (
    epic_id,
    triggered_by_epic_id,
    session_id,
    test_result,
    is_regression,
    execution_time_ms,
    error_details,
    tests_run,
    tests_passed,
    tests_failed,
    selection_reason
  ) VALUES (
    p_epic_id,
    p_triggered_by_epic_id,
    p_session_id,
    p_test_result,
    p_is_regression,
    p_execution_time_ms,
    p_error_details,
    p_tests_run,
    p_tests_passed,
    p_tests_failed,
    p_selection_reason
  ) RETURNING id INTO v_retest_id;

  -- Update or insert stability metrics
  INSERT INTO epic_stability_metrics (
    epic_id,
    total_retests,
    passed_retests,
    failed_retests,
    regression_count,
    stability_score,
    avg_execution_time_ms,
    last_retest_at,
    last_retest_result,
    last_regression_at,
    last_regression_by_epic_id,
    updated_at
  ) VALUES (
    p_epic_id,
    1,
    CASE WHEN p_test_result = 'passed' THEN 1 ELSE 0 END,
    CASE WHEN p_test_result = 'failed' THEN 1 ELSE 0 END,
    CASE WHEN p_is_regression THEN 1 ELSE 0 END,
    CASE WHEN p_test_result = 'passed' THEN 1.00 ELSE 0.00 END,
    p_execution_time_ms,
    NOW(),
    p_test_result,
    CASE WHEN p_is_regression THEN NOW() ELSE NULL END,
    CASE WHEN p_is_regression THEN p_triggered_by_epic_id ELSE NULL END,
    NOW()
  )
  ON CONFLICT (epic_id) DO UPDATE SET
    total_retests = epic_stability_metrics.total_retests + 1,
    passed_retests = epic_stability_metrics.passed_retests + CASE WHEN p_test_result = 'passed' THEN 1 ELSE 0 END,
    failed_retests = epic_stability_metrics.failed_retests + CASE WHEN p_test_result = 'failed' THEN 1 ELSE 0 END,
    regression_count = epic_stability_metrics.regression_count + CASE WHEN p_is_regression THEN 1 ELSE 0 END,
    stability_score = ROUND(
      (epic_stability_metrics.passed_retests + CASE WHEN p_test_result = 'passed' THEN 1 ELSE 0 END)::DECIMAL /
      (epic_stability_metrics.total_retests + 1)::DECIMAL,
      2
    ),
    avg_execution_time_ms = CASE
      WHEN p_execution_time_ms IS NOT NULL THEN
        ((COALESCE(epic_stability_metrics.avg_execution_time_ms, 0) * epic_stability_metrics.total_retests + p_execution_time_ms) /
         (epic_stability_metrics.total_retests + 1))::INTEGER
      ELSE epic_stability_metrics.avg_execution_time_ms
    END,
    last_retest_at = NOW(),
    last_retest_result = p_test_result,
    last_regression_at = CASE WHEN p_is_regression THEN NOW() ELSE epic_stability_metrics.last_regression_at END,
    last_regression_by_epic_id = CASE WHEN p_is_regression THEN p_triggered_by_epic_id ELSE epic_stability_metrics.last_regression_by_epic_id END,
    updated_at = NOW();

  RETURN v_retest_id;
END;
$$ LANGUAGE plpgsql;

-- Add comment
COMMENT ON TABLE epic_retest_runs IS 'Tracks every epic re-test execution for regression detection';
COMMENT ON TABLE epic_stability_metrics IS 'Aggregated stability metrics per epic';
COMMENT ON FUNCTION record_epic_retest IS 'Records epic re-test run and updates stability metrics';

-- -----------------------------------------------------------------------------
-- Migration 020: Project Completion Reviews
-- -----------------------------------------------------------------------------

CREATE TABLE project_completion_reviews (
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
    coverage_percentage DECIMAL(5,2), -- 0.00 to 100.00
    overall_score INTEGER, -- 1-100
    recommendation VARCHAR(20), -- 'complete', 'needs_work', 'failed'

    -- Review content
    executive_summary TEXT,
    review_text TEXT, -- Full Claude analysis

    -- Model used
    review_model VARCHAR(100) DEFAULT 'claude-sonnet-4-5-20250929',

    CONSTRAINT recommendation_valid CHECK (
        recommendation IN ('complete', 'needs_work', 'failed')
    ),
    CONSTRAINT score_valid CHECK (overall_score BETWEEN 1 AND 100)
);

-- Individual requirement tracking
CREATE TABLE completion_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID REFERENCES project_completion_reviews(id) ON DELETE CASCADE,

    -- Requirement details
    requirement_id VARCHAR(50) NOT NULL, -- req_1, req_2, etc.
    section VARCHAR(100) NOT NULL, -- Frontend, Backend, etc.
    requirement_text TEXT NOT NULL,
    keywords TEXT[], -- For matching
    priority VARCHAR(20), -- high, medium, low

    -- Implementation status
    status VARCHAR(20) NOT NULL, -- 'met', 'missing', 'partial', 'extra'

    -- Mapping to epics/tasks
    matched_epic_ids INTEGER[], -- epics.id references
    matched_task_ids INTEGER[], -- tasks.id references
    match_confidence DECIMAL(3,2), -- 0.00 to 1.00

    -- Notes
    implementation_notes TEXT,

    CONSTRAINT status_valid CHECK (
        status IN ('met', 'missing', 'partial', 'extra')
    )
);

-- Indexes
CREATE INDEX idx_completion_reviews_project ON project_completion_reviews(project_id);
CREATE INDEX idx_completion_reviews_created ON project_completion_reviews(created_at DESC);
CREATE INDEX idx_completion_requirements_review ON completion_requirements(review_id);
CREATE INDEX idx_completion_requirements_status ON completion_requirements(status);
CREATE INDEX idx_completion_requirements_section ON completion_requirements(section);

-- View: Latest completion review per project
CREATE VIEW v_latest_completion_review AS
SELECT DISTINCT ON (project_id)
    pcr.*,
    p.name as project_name,
    p.completed_at as project_completed_at
FROM project_completion_reviews pcr
JOIN projects p ON pcr.project_id = p.id
ORDER BY project_id, created_at DESC;

-- View: Requirement summary by review
CREATE VIEW v_completion_requirement_summary AS
SELECT
    review_id,
    status,
    COUNT(*) as count,
    ROUND(AVG(match_confidence), 2) as avg_confidence
FROM completion_requirements
GROUP BY review_id, status;

-- View: Requirement summary by section
CREATE VIEW v_completion_section_summary AS
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

-- View: Project completion statistics
CREATE VIEW v_project_completion_stats AS
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

-- Comments
COMMENT ON TABLE project_completion_reviews IS 'Stores project completion verification reviews comparing implementation against specifications';
COMMENT ON TABLE completion_requirements IS 'Individual requirements from spec with implementation tracking and mapping to epics/tasks';
COMMENT ON VIEW v_latest_completion_review IS 'Latest completion review for each project';
COMMENT ON VIEW v_completion_requirement_summary IS 'Summary of requirement statuses by review';
COMMENT ON VIEW v_completion_section_summary IS 'Summary of requirements grouped by section (Frontend, Backend, etc.)';
COMMENT ON VIEW v_project_completion_stats IS 'Completion statistics for all completed projects';

-- ============================================================================
-- End of Consolidated Schema
-- ============================================================================
