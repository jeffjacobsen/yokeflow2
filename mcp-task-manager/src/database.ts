/**
 * PostgreSQL database connection and query functions for task management
 * Uses the pg library for PostgreSQL connections
 */

import { Pool } from 'pg';
import type {
  Epic, Task, Test, ProjectStatus, EpicProgress,
  TaskWithEpic, TaskDetail, Session, NewEpic, NewTask, NewTest,
  EpicTest, NewEpicTest
} from './types.js';

export class TaskDatabase {
  private pool: Pool;
  private projectId: string;

  constructor() {
    // Get PostgreSQL connection from environment
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) {
      throw new Error('DATABASE_URL environment variable is required');
    }

    // Get project ID from environment
    this.projectId = process.env.PROJECT_ID || '';
    if (!this.projectId) {
      throw new Error('PROJECT_ID environment variable is required');
    }

    // Create connection pool
    this.pool = new Pool({
      connectionString,
      max: 10, // Maximum number of connections in the pool
      idleTimeoutMillis: 30000, // Close idle clients after 30 seconds
      connectionTimeoutMillis: 2000, // Return an error after 2 seconds if connection could not be established
    });

    // Test connection on startup (log-only, don't crash the process)
    // The pool will retry connections automatically on subsequent queries
    this.pool.query('SELECT NOW()').then(() => {
      console.error('[MCP] PostgreSQL connection verified');
    }).catch((err) => {
      console.error(`[MCP] Warning: Initial PostgreSQL connection failed: ${err.message}`);
      console.error('[MCP] The server will retry connections on subsequent queries');
    });
  }

  // Execute a query and return results
  async query<T>(sql: string, params: any[] = []): Promise<T[]> {
    try {
      const result = await this.pool.query(sql, params);
      return result.rows as T[];
    } catch (error: any) {
      throw new Error(`Database query failed: ${error.message}\nSQL: ${sql}`);
    }
  }

  // Execute a command without expecting results
  private async exec(sql: string, params: any[] = []): Promise<void> {
    try {
      await this.pool.query(sql, params);
    } catch (error: any) {
      throw new Error(`Database command failed: ${error.message}\nSQL: ${sql}`);
    }
  }

  // Query methods

  async getProjectStatus(): Promise<ProjectStatus> {
    const result = await this.query<ProjectStatus>(`
      SELECT
        (SELECT COUNT(*)::int FROM epics WHERE project_id = $1) as total_epics,
        (SELECT COUNT(*)::int FROM epics WHERE project_id = $1 AND status = 'completed') as completed_epics,
        (SELECT COUNT(*)::int FROM tasks WHERE project_id = $1) as total_tasks,
        (SELECT COUNT(*)::int FROM tasks WHERE project_id = $1 AND done = true) as completed_tasks,
        (SELECT COUNT(*)::int FROM task_tests t
         JOIN tasks tk ON t.task_id = tk.id
         WHERE tk.project_id = $1) as total_tests,
        (SELECT COUNT(*)::int FROM task_tests t
         JOIN tasks tk ON t.task_id = tk.id
         WHERE tk.project_id = $1 AND t.passes = true) as passing_tests,
        COALESCE(ROUND(100.0 * (SELECT COUNT(*) FROM tasks WHERE project_id = $1 AND done = true) /
              NULLIF((SELECT COUNT(*) FROM tasks WHERE project_id = $1), 0), 1), 0) as task_completion_pct,
        COALESCE(ROUND(100.0 * (SELECT COUNT(*) FROM task_tests t
         JOIN tasks tk ON t.task_id = tk.id
         WHERE tk.project_id = $1 AND t.passes = true) /
              NULLIF((SELECT COUNT(*) FROM task_tests t
         JOIN tasks tk ON t.task_id = tk.id
         WHERE tk.project_id = $1), 0), 1), 0) as test_pass_pct
    `, [this.projectId]);

    return result[0] ? { ...result[0], project_id: this.projectId } : {
      project_id: this.projectId,
      total_epics: 0,
      completed_epics: 0,
      total_tasks: 0,
      completed_tasks: 0,
      total_tests: 0,
      passing_tests: 0,
      task_completion_pct: 0,
      test_pass_pct: 0
    };
  }

  async getNextTask(): Promise<TaskWithEpic | null> {
    // First, check if there are any epics with all tasks complete but epic tests not verified
    const epicsPendingTests = await this.query<{
      epic_id: string;
      epic_name: string;
      pending_tasks: number;
      epic_test_status: string | null;
    }>(`
      WITH epic_status AS (
        SELECT
          e.id,
          e.name,
          COUNT(t.id) FILTER (WHERE t.done = false) as pending_tasks,
          MAX(et.last_result) as epic_test_status
        FROM epics e
        LEFT JOIN tasks t ON t.epic_id = e.id
        LEFT JOIN epic_tests et ON et.epic_id = e.id AND et.project_id = e.project_id
        WHERE e.project_id = $1
          AND e.status != 'completed'
        GROUP BY e.id, e.name
        HAVING COUNT(t.id) > 0  -- Has tasks
      )
      SELECT
        id::text as epic_id,
        name as epic_name,
        pending_tasks::int,
        epic_test_status
      FROM epic_status
      WHERE pending_tasks = 0  -- All tasks done
        AND (epic_test_status IS NULL OR epic_test_status != 'passed')  -- But epic test not passed
      ORDER BY id
      LIMIT 1
    `, [this.projectId]);

    if (epicsPendingTests.length > 0) {
      const epic = epicsPendingTests[0];
      // Return a special task indicating epic tests need to be run
      return {
        id: 'EPIC_TEST_REQUIRED',
        epic_id: epic.epic_id,
        epic_name: epic.epic_name,
        description: `⚠️ EPIC COMPLETION REQUIRED: All tasks for epic "${epic.epic_name}" are complete. Run epic tests before continuing.`,
        action: `IMPORTANT: Epic ${epic.epic_id} has all tasks completed but epic tests have not been verified.\n\n` +
                `REQUIRED ACTIONS:\n` +
                `1. Run: mcp__task-manager__get_epic_tests({ epic_id: ${epic.epic_id}, verbose: true })\n` +
                `2. Verify all epic integration requirements\n` +
                `3. Update test results: mcp__task-manager__update_epic_test_result({ test_id: <id>, result: "passed" })\n` +
                `4. Only after epic tests pass, call get_next_task again\n\n` +
                `DO NOT proceed to next epic until these tests are verified!`,
        status: 'epic_test_required',
        priority: 0,
        created_at: new Date().toISOString(),
        completed_at: null,
        session_notes: `Epic ${epic.epic_id} pending test verification`,
        done: 0
      } as TaskWithEpic;
    }

    // If no epics need testing, return the next pending task as before
    const result = await this.query<TaskWithEpic>(`
      SELECT
        t.id::text,
        t.epic_id::text,
        t.description,
        t.action,
        'pending' as status,
        t.priority,
        t.created_at,
        t.completed_at,
        t.session_notes,
        CASE WHEN t.done = true THEN 1 ELSE 0 END as done,
        e.name as epic_name
      FROM tasks t
      JOIN epics e ON t.epic_id = e.id
      WHERE t.project_id = $1 AND t.done = false
      ORDER BY e.priority, t.priority
      LIMIT 1
    `, [this.projectId]);

    return result[0] || null;
  }

  async listEpics(needsExpansion = false): Promise<Epic[]> {
    let sql: string;
    let params: any[];

    if (needsExpansion) {
      sql = `
        SELECT
          e.id::text,
          e.name,
          e.description,
          e.priority,
          e.status,
          e.created_at,
          e.started_at,
          e.completed_at
        FROM epics e
        LEFT JOIN tasks t ON e.id = t.epic_id
        WHERE e.project_id = $1
        GROUP BY e.id, e.name, e.description, e.priority, e.status, e.created_at, e.started_at, e.completed_at
        HAVING COUNT(t.id) = 0
        ORDER BY e.priority
      `;
      params = [this.projectId];
    } else {
      sql = `
        SELECT
          id::text,
          name,
          description,
          priority,
          status,
          created_at,
          started_at,
          completed_at
        FROM epics
        WHERE project_id = $1
        ORDER BY priority
      `;
      params = [this.projectId];
    }

    const result = await this.query<Epic>(sql, params);
    return result || [];
  }

  async getEpic(id: string | number): Promise<Epic | null> {
    const result = await this.query<Epic>(`
      SELECT
        id::text,
        name,
        description,
        priority,
        status,
        created_at,
        started_at,
        completed_at
      FROM epics
      WHERE id = $1 AND project_id = $2
    `, [String(id), this.projectId]);

    return result[0] || null;
  }

  async getEpicProgress(id?: string | number): Promise<EpicProgress[]> {
    let sql = `
      SELECT
        e.id::text,
        e.name,
        e.priority,
        e.status,
        COUNT(t.id)::int as total_tasks,
        SUM(CASE WHEN t.done = true THEN 1 ELSE 0 END)::int as completed_tasks,
        (SELECT COUNT(*)::int FROM task_tests ts
         JOIN tasks tk ON ts.task_id = tk.id
         WHERE tk.epic_id = e.id) as total_tests,
        (SELECT COUNT(*)::int FROM task_tests ts
         JOIN tasks tk ON ts.task_id = tk.id
         WHERE tk.epic_id = e.id AND ts.passes = true) as passing_tests
      FROM epics e
      LEFT JOIN tasks t ON e.id = t.epic_id
      WHERE e.project_id = $1
    `;

    const params: any[] = [this.projectId];

    if (id !== undefined) {
      sql += ` AND e.id = $2`;
      params.push(String(id));
    }

    sql += ' GROUP BY e.id, e.name, e.priority, e.status ORDER BY e.priority';

    const result = await this.query<EpicProgress>(sql, params);
    return result || [];
  }

  async listTasks(epicId?: string | number, onlyPending = false): Promise<Task[]> {
    let sql = `
      SELECT
        id::text,
        epic_id::text,
        description,
        action,
        'pending' as status,
        priority,
        created_at,
        completed_at,
        session_notes,
        CASE WHEN done = true THEN 1 ELSE 0 END as done
      FROM tasks
      WHERE project_id = $1
    `;
    const params: any[] = [this.projectId];
    let paramCount = 1;

    if (epicId !== undefined) {
      sql += ` AND epic_id = $${++paramCount}`;
      params.push(String(epicId));
    }

    if (onlyPending) {
      sql += ` AND done = false`;
    }

    sql += ' ORDER BY priority';

    const result = await this.query<Task>(sql, params);
    return result || [];
  }

  async getTask(id: string | number): Promise<TaskDetail | null> {
    const taskResult = await this.query<any>(`
      SELECT
        t.id::text,
        t.epic_id::text,
        t.description,
        t.action,
        'pending' as status,
        t.priority,
        t.created_at,
        t.completed_at,
        t.session_notes,
        CASE WHEN t.done = true THEN 1 ELSE 0 END as done,
        e.name as epic_name
      FROM tasks t
      JOIN epics e ON t.epic_id = e.id
      WHERE t.id = $1 AND t.project_id = $2
    `, [String(id), this.projectId]);

    const task = taskResult[0];
    if (!task) return null;

    const tests = await this.query<Test>(`
      SELECT
        id::text,
        task_id::text,
        category,
        description,
        steps,
        passes,
        created_at,
        verified_at
      FROM task_tests
      WHERE task_id = $1
    `, [String(id)]) || [];

    return { ...task, tests };
  }

  async listTests(taskId: string | number): Promise<Test[]> {
    const result = await this.query<Test>(`
      SELECT
        id::text,
        task_id::text,
        category,
        description,
        steps,
        passes,
        created_at,
        verified_at
      FROM task_tests
      WHERE task_id = $1
      ORDER BY id
    `, [String(taskId)]);

    return result || [];
  }

  async getTest(id: string | number): Promise<Test | null> {
    const result = await this.query<Test>(`
      SELECT
        id::text,
        task_id::text,
        category,
        description,
        steps,
        passes,
        test_type,
        requirements,
        success_criteria,
        verification_notes,
        last_execution,
        last_result,
        execution_log,
        created_at,
        verified_at
      FROM task_tests
      WHERE id = $1
    `, [String(id)]);

    return result[0] || null;
  }

  async getTaskTests(taskId: string | number): Promise<Test[]> {
    const result = await this.query<Test>(`
      SELECT
        id::text,
        task_id::text,
        category,
        description,
        steps,
        passes,
        test_type,
        requirements,
        success_criteria,
        verification_notes,
        last_execution,
        last_result,
        execution_log,
        created_at,
        verified_at
      FROM task_tests
      WHERE task_id = $1
      ORDER BY created_at ASC
    `, [String(taskId)]);

    return result;
  }

  // Mutation methods

  async createEpic(epic: NewEpic): Promise<Epic> {
    const result = await this.query<Epic>(`
      INSERT INTO epics (project_id, name, description, priority)
      VALUES ($1, $2, $3, $4)
      RETURNING
        id::text,
        name,
        description,
        priority,
        status,
        created_at,
        started_at,
        completed_at
    `, [this.projectId, epic.name, epic.description || null, epic.priority]);

    return result[0];
  }

  async createTask(task: NewTask): Promise<Task> {
    // Get next priority if not specified
    const priority = task.priority ?? await this.getNextTaskPriority(String(task.epic_id));

    const result = await this.query<Task>(`
      INSERT INTO tasks (epic_id, project_id, description, action, priority)
      VALUES ($1, $2, $3, $4, $5)
      RETURNING
        id::text,
        epic_id::text,
        description,
        action,
        'pending' as status,
        priority,
        created_at,
        completed_at,
        session_notes,
        CASE WHEN done = true THEN 1 ELSE 0 END as done
    `, [String(task.epic_id), this.projectId, task.description, task.action, priority]);

    return result[0];
  }

  async createTest(test: NewTest): Promise<Test> {
    const result = await this.query<Test>(`
      INSERT INTO task_tests (task_id, project_id, category, description, steps, test_type, requirements, success_criteria)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
      RETURNING
        id::text,
        task_id::text,
        category,
        description,
        steps,
        passes,
        test_type,
        requirements,
        success_criteria,
        verification_notes,
        last_execution,
        last_result,
        execution_log,
        created_at,
        verified_at
    `, [
      String(test.task_id),
      this.projectId,
      test.category,
      test.description,
      JSON.stringify(test.steps),
      test.test_type || null,
      test.requirements || null,
      test.success_criteria || null
    ]);

    return result[0];
  }

  async getEpicTests(epicId: string | number): Promise<EpicTest[]> {
    const result = await this.query<EpicTest>(`
      SELECT
        id::text,
        epic_id::text,
        name,
        description,
        test_type,
        requirements,
        success_criteria,
        key_verification_points,
        verification_notes,
        depends_on_tasks,
        last_execution,
        last_result,
        execution_log,
        created_at,
        updated_at
      FROM epic_tests
      WHERE epic_id = $1 AND project_id = $2
      ORDER BY created_at
    `, [String(epicId), this.projectId]);

    return result || [];
  }

  async getEpicTest(testId: string | number): Promise<EpicTest | null> {
    const result = await this.query<EpicTest>(`
      SELECT
        id::text,
        epic_id::text,
        name,
        description,
        test_type,
        requirements,
        success_criteria,
        key_verification_points,
        verification_notes,
        depends_on_tasks,
        last_execution,
        last_result,
        execution_log,
        created_at,
        updated_at
      FROM epic_tests
      WHERE id = $1 AND project_id = $2
    `, [String(testId), this.projectId]);

    return result[0] || null;
  }

  async updateEpicTestResult(
    testId: string | number,
    result: 'passed' | 'failed',
    executionLog?: string,
    verificationNotes?: string,
    errorMessage?: string,
    executionTimeMs?: number
  ): Promise<void> {
    // Increment retry count if test failed
    const retryIncrement = result === 'passed' ? '' : `, retry_count = COALESCE(retry_count, 0) + 1`;

    // Update the test result
    await this.exec(`
      UPDATE epic_tests
      SET
        last_result = $1,
        last_execution = NOW(),
        execution_log = $2,
        verification_notes = $3,
        last_error_message = $4,
        execution_time_ms = $5,
        updated_at = NOW()
        ${retryIncrement}
      WHERE id = $6 AND project_id = $7
    `, [result, executionLog || null, verificationNotes || null, errorMessage || null, executionTimeMs || null, String(testId), this.projectId]);

    // Record failure in epic_test_failures table (Phase 2)
    if (result === 'failed') {
      try {
        // Get current session_id if available
        const sessionResult = await this.query<{ id: string }>(`
          SELECT id::text FROM sessions
          WHERE project_id = $1
          ORDER BY created_at DESC
          LIMIT 1
        `, [this.projectId]);

        const sessionId = sessionResult && sessionResult.length > 0 ? sessionResult[0].id : null;

        // Call the record_epic_test_failure function
        await this.exec(`
          SELECT record_epic_test_failure(
            $1::uuid,  -- epic_test_id
            $2::uuid,  -- session_id
            $3::text,  -- error_message
            $4::text,  -- full_error_log
            $5::integer,  -- execution_time_ms
            $6::text,  -- verification_notes
            'unknown'::varchar,  -- failure_type (can be enhanced later)
            'other'::varchar,  -- failure_category (can be enhanced later)
            NULL,  -- agent_diagnosis (can be added later)
            NULL,  -- attempted_fixes (can be added later)
            NULL   -- environment_info (can be added later)
          )
        `, [
          String(testId),
          sessionId,
          errorMessage || 'Epic test failed',
          executionLog || null,
          executionTimeMs || null,
          verificationNotes || null
        ]);
      } catch (err) {
        // Log error but don't fail the test update
        console.error('Failed to record epic test failure:', err);
      }
    }

    // Get the epic_id for this test
    const epicResult = await this.query<{epic_id: number}>(`
      SELECT epic_id
      FROM epic_tests
      WHERE id = $1 AND project_id = $2
    `, [String(testId), this.projectId]);

    // If test passed, check if the epic should be marked complete
    if (result === 'passed' && epicResult[0]) {
      await this.checkEpicCompletion(epicResult[0].epic_id);
    }
  }

  async createEpicTest(test: NewEpicTest): Promise<EpicTest> {
    const result = await this.query<EpicTest>(`
      INSERT INTO epic_tests (epic_id, project_id, name, description, test_type, requirements, success_criteria, key_verification_points, depends_on_tasks)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
      RETURNING
        id::text,
        epic_id::text,
        name,
        description,
        test_type,
        requirements,
        success_criteria,
        key_verification_points,
        verification_notes,
        depends_on_tasks,
        last_execution,
        last_result,
        execution_log,
        created_at,
        updated_at
    `, [
      String(test.epic_id),
      this.projectId,
      test.name,
      test.description,
      test.test_type || 'integration',
      test.requirements || null,
      test.success_criteria || null,
      test.key_verification_points ? JSON.stringify(test.key_verification_points) : null,
      test.depends_on_tasks ? test.depends_on_tasks.map(id => Number(id)) : null
    ]);
    return result[0];
  }

  async updateTaskStatus(taskId: string | number, done: boolean): Promise<Task | null> {
    // Use a dedicated client for transactional consistency:
    // test validation + status update + epic completion check all in one transaction
    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');

      // CRITICAL: If marking task as complete, validate all tests are passing
      if (done === true) {
        const testResult = await client.query(
          `SELECT id::text, description, passes FROM task_tests WHERE task_id = $1`,
          [String(taskId)]
        );
        const tests = testResult.rows;

        if (tests.length > 0) {
          const failingTests = tests.filter((t: any) => t.passes !== true);

          if (failingTests.length > 0) {
            await client.query('ROLLBACK');
            throw new Error(
              `Cannot mark task ${taskId} as complete: ${failingTests.length} of ${tests.length} test(s) not passing.\n` +
              `Failing tests:\n${failingTests.map((t: any) => `  - Test ${t.id}: ${t.description}`).join('\n')}\n\n` +
              `All tests must pass before marking task complete. Use update_task_test_result to mark tests as passing.`
            );
          }
        }
      }

      const completedAt = done ? 'NOW()' : 'NULL';

      await client.query(`
        UPDATE tasks
        SET done = $1, completed_at = ${completedAt}
        WHERE id = $2 AND project_id = $3
      `, [done, String(taskId), this.projectId]);

      // Check if all tasks in epic are done and update epic status
      if (done) {
        const taskResult = await client.query(
          `SELECT epic_id::text FROM tasks WHERE id = $1 AND project_id = $2`,
          [String(taskId), this.projectId]
        );
        if (taskResult.rows[0]) {
          // Inline epic completion check within the transaction
          const epicId = taskResult.rows[0].epic_id;
          const pendingResult = await client.query(
            `SELECT COUNT(*)::int as pending FROM tasks WHERE epic_id = $1 AND done = false`,
            [epicId]
          );
          if (pendingResult.rows[0]?.pending === 0) {
            await client.query(
              `UPDATE epics SET status = 'completed' WHERE id = $1 AND project_id = $2`,
              [epicId, this.projectId]
            );
          }
        }
      }

      const result = await client.query(`
        SELECT
          id::text,
          epic_id::text,
          description,
          action,
          'pending' as status,
          priority,
          created_at,
          completed_at,
          session_notes,
          CASE WHEN done = true THEN 1 ELSE 0 END as done
        FROM tasks
        WHERE id = $1 AND project_id = $2
      `, [String(taskId), this.projectId]);

      await client.query('COMMIT');
      return result.rows[0] || null;
    } catch (error) {
      await client.query('ROLLBACK').catch(() => {});
      throw error;
    } finally {
      client.release();
    }
  }

  async updateTestResult(
    testId: string | number,
    passes: boolean,
    verificationNotes?: string,
    errorMessage?: string,
    executionTimeMs?: number
  ): Promise<Test | null> {
    const verifiedAt = passes ? 'NOW()' : 'NULL';

    // Increment retry count if test failed and has been run before
    const retryIncrement = passes ? '' : `, retry_count = COALESCE(retry_count, 0) + 1`;

    await this.exec(`
      UPDATE task_tests
      SET
        passes = $1,
        verified_at = ${verifiedAt},
        verification_notes = $3,
        last_error_message = $4,
        execution_time_ms = $5,
        last_execution = NOW()
        ${retryIncrement}
      WHERE id = $2
    `, [passes, String(testId), verificationNotes || null, errorMessage || null, executionTimeMs || null]);

    return await this.getTest(testId);
  }

  async startTask(taskId: string | number): Promise<void> {
    await this.exec(`
      UPDATE tasks
      SET session_notes = 'Started at ' || NOW()::text
      WHERE id = $1 AND project_id = $2 AND session_notes IS NULL
    `, [String(taskId), this.projectId]);
  }

  async claimNextTask(workerId: string): Promise<TaskWithEpic | null> {
    // Atomic CTE: SELECT + UPDATE in one round-trip
    // FOR UPDATE SKIP LOCKED: if worker A locks row 1, worker B skips to row 2
    const result = await this.query<TaskWithEpic>(`
      WITH next AS (
        SELECT t.id
        FROM tasks t
        JOIN epics e ON t.epic_id = e.id
        WHERE t.project_id = $1
          AND t.done = false
          AND t.session_notes IS NULL
          AND e.status != 'completed'
        ORDER BY e.priority, t.priority, t.id
        LIMIT 1
        FOR UPDATE OF t SKIP LOCKED
      )
      UPDATE tasks
      SET session_notes = $2 || ' claimed at ' || NOW()::text
      FROM next
      WHERE tasks.id = next.id
      RETURNING tasks.id::text, tasks.epic_id::text, tasks.description,
                tasks.action, tasks.priority, tasks.session_notes,
                tasks.created_at, tasks.completed_at,
                CASE WHEN tasks.done THEN 1 ELSE 0 END as done
    `, [this.projectId, workerId]);

    if (!result[0]) return null;

    // Get epic name
    const epicResult = await this.query<{name: string}>(
      `SELECT name FROM epics WHERE id = $1`, [result[0].epic_id]
    );
    return { ...result[0], epic_name: epicResult[0]?.name || '' };
  }

  // Helper methods

  private async getNextTaskPriority(epicId: string | number): Promise<number> {
    const result = await this.query<{next: number}>(`
      SELECT COALESCE(MAX(priority), 0) + 1 as next
      FROM tasks
      WHERE epic_id = $1
    `, [String(epicId)]);

    return result[0]?.next || 1;
  }

  private async checkEpicCompletion(epicId: string | number): Promise<void> {
    const result = await this.query<{pending: number}>(`
      SELECT COUNT(*)::int as pending
      FROM tasks
      WHERE epic_id = $1 AND done = false
    `, [String(epicId)]);

    if (result[0]?.pending === 0) {
      // All tasks are done, but before marking epic complete, check if epic tests are passing
      const epicTests = await this.query<{id: string, name: string, last_result: string | null}>(`
        SELECT id::text, name, last_result
        FROM epic_tests
        WHERE epic_id = $1 AND project_id = $2
      `, [String(epicId), this.projectId]);

      if (epicTests.length > 0) {
        // Separate actually failed tests from tests that haven't been run yet
        const failedTests = epicTests.filter(t => t.last_result === 'failed');
        const notRunTests = epicTests.filter(t => t.last_result === null);
        const passingTests = epicTests.filter(t => t.last_result === 'passed');

        // Get epic details (needed for logging in all branches)
        const epicInfo = await this.query<{name: string}>(`
          SELECT name FROM epics WHERE id = $1
        `, [String(epicId)]);
        const epicName = epicInfo[0]?.name || `Epic ${epicId}`;

        // Only block on ACTUAL failures, not unrun tests
        if (failedTests.length > 0) {
          // Phase 3: Check epic testing mode from project configuration
          const projectConfig = await this.query<{epic_testing_mode: string, name: string}>(`
            SELECT epic_testing_mode, name FROM projects WHERE id = $1
          `, [this.projectId]);

          const epicTestingMode = projectConfig[0]?.epic_testing_mode || 'autonomous';
          const projectName = projectConfig[0]?.name || 'unknown';

          // Check if this is a critical epic (for autonomous mode)
          const criticalEpicPatterns = ['Authentication', 'Database', 'Payment', 'Security', 'Core API'];
          const isCriticalEpic = criticalEpicPatterns.some(pattern =>
            epicName.toLowerCase().includes(pattern.toLowerCase())
          );

          // Determine if we should block based on mode
          let shouldBlock = false;
          let blockReason = '';

          if (epicTestingMode === 'strict') {
            // Strict mode: Always block on any failure
            shouldBlock = true;
            blockReason = 'Strict mode: Any epic test failure requires intervention';
          } else {
            // Autonomous mode: Block only on critical epics or if >3 failures (from config)
            const autoFailureTolerance = 3; // Could be loaded from config
            if (isCriticalEpic) {
              shouldBlock = true;
              blockReason = 'Autonomous mode: Critical epic failed tests';
            } else if (failedTests.length > autoFailureTolerance) {
              shouldBlock = true;
              blockReason = `Autonomous mode: Exceeded failure tolerance (${failedTests.length} > ${autoFailureTolerance})`;
            }
          }

          if (shouldBlock) {
            // BLOCK: Create intervention record
            console.error(
              `\n❌ BLOCKED: Epic "${epicName}" has failing tests in ${epicTestingMode} mode\n` +
              `   Mode: ${epicTestingMode}\n` +
              `   Critical: ${isCriticalEpic}\n` +
              `   Failures: ${failedTests.length}/${epicTests.length}\n` +
              `   Reason: ${blockReason}\n\n` +
              `   Failed tests:\n${failedTests.map(t => `     • ${t.name}: ${t.last_result}`).join('\n')}\n\n` +
              `   ⚠️  Session blocked - human intervention required.\n` +
              `   Use update_epic_test_result to fix tests, then resume session.\n`
            );

            // Record intervention
            try {
              const sessionResult = await this.query<{id: string}>(`
                SELECT id::text FROM sessions
                WHERE project_id = $1
                ORDER BY created_at DESC
                LIMIT 1
              `, [this.projectId]);
              const sessionId = sessionResult && sessionResult.length > 0 ? sessionResult[0].id : null;

              await this.exec(`
                INSERT INTO epic_test_interventions
                (epic_id, session_id, failure_count, blocked, notification_sent, created_at)
                VALUES ($1, $2::uuid, $3, true, false, NOW())
              `, [String(epicId), sessionId, failedTests.length]);

              // Update epic status to blocked
              await this.exec(`
                UPDATE epics
                SET status = 'blocked'
                WHERE id = $1
              `, [String(epicId)]);

              // TODO Phase 3.2: Create checkpoint for session resumption
              // TODO Phase 3.4: Send notification if configured
            } catch (err) {
              console.error('Failed to record intervention:', err);
            }

            // Throw error to stop the session
            throw new Error(
              `Epic test failure blocked in ${epicTestingMode} mode: ${blockReason}\n` +
              `Failed tests: ${failedTests.map(t => t.name).join(', ')}`
            );
          } else {
            // CONTINUE: Log warning but allow autonomous mode to proceed
            console.warn(
              `\n⚠️  Epic "${epicName}" has failing tests (autonomous mode - continuing)\n` +
              `   Failures: ${failedTests.length}/${epicTests.length}\n` +
              `   Critical: ${isCriticalEpic}\n` +
              `   Failed tests:\n${failedTests.map(t => `     • ${t.name}: ${t.last_result}`).join('\n')}\n\n` +
              `   🔄 Continuing session - tests can be fixed later.\n` +
              `   All epic tests must pass before marking epic complete. Use update_epic_test_result to mark tests as passing.\n`
            );

            // Keep epic status as in_progress since tests still need to pass
            await this.exec(`
              UPDATE epics
              SET status = 'in_progress'
              WHERE id = $1 AND status != 'in_progress'
            `, [String(epicId)]);
            return;
          }
        } else if (notRunTests.length > 0) {
          // Tests haven't been run yet - don't mark epic complete, but don't block either
          console.log(
            `\n📋 Epic "${epicName}" has tests that need to be run\n` +
            `   Not run: ${notRunTests.length}/${epicTests.length}\n` +
            `   Passing: ${passingTests.length}/${epicTests.length}\n` +
            `   Tests to run:\n${notRunTests.map(t => `     • ${t.name}`).join('\n')}\n\n` +
            `   ℹ️  Epic cannot be marked complete until all tests pass.\n` +
            `   Run the epic tests and mark results with update_epic_test_result.\n`
          );

          // Keep epic status as in_progress since tests need to be run
          await this.exec(`
            UPDATE epics
            SET status = 'in_progress'
            WHERE id = $1 AND status != 'in_progress'
          `, [String(epicId)]);
          return;
        }
      }

      // All tasks done and all epic tests passing (or no epic tests), mark as complete
      await this.exec(`
        UPDATE epics
        SET status = 'completed', completed_at = NOW()
        WHERE id = $1
      `, [String(epicId)]);
    }
  }

  async logSession(sessionNumber: number, notes?: string): Promise<Session> {
    // Calculate metrics
    const tasksCompleted = await this.query<{count: number}>(`
      SELECT COUNT(*)::int as count FROM tasks
      WHERE project_id = $1 AND completed_at >= NOW() - INTERVAL '1 hour'
    `, [this.projectId]);

    const testsPassed = await this.query<{count: number}>(`
      SELECT COUNT(*)::int as count FROM task_tests t
      JOIN tasks tk ON t.task_id = tk.id
      WHERE tk.project_id = $1 AND t.verified_at >= NOW() - INTERVAL '1 hour'
    `, [this.projectId]);

    const metrics = {
      tasks_completed: tasksCompleted[0]?.count || 0,
      tests_passed: testsPassed[0]?.count || 0,
      notes: notes || null
    };

    const result = await this.query<Session>(`
      INSERT INTO sessions (project_id, session_number, type, model, status, metrics)
      VALUES ($1, $2, 'coding', 'claude-sonnet', 'completed', $3)
      RETURNING
        id::text,
        session_number,
        metrics,
        created_at
    `, [this.projectId, sessionNumber, JSON.stringify(metrics)]);

    return result[0];
  }

  async getSessionHistory(limit = 10): Promise<Session[]> {
    const result = await this.query<Session>(`
      SELECT
        id::text,
        session_number,
        type,
        model,
        status,
        metrics,
        created_at,
        started_at,
        ended_at
      FROM sessions
      WHERE project_id = $1
      ORDER BY session_number DESC
      LIMIT $2
    `, [this.projectId, limit]);

    return result || [];
  }

  async expandEpic(epicId: string | number, tasks: NewTask[]): Promise<Task[]> {
    const id = String(epicId);
    await this.exec(`
      UPDATE epics
      SET status = 'in_progress', started_at = NOW()
      WHERE id = $1 AND status = 'pending'
    `, [id]);

    const createdTasks: Task[] = [];
    for (const task of tasks) {
      const created = await this.createTask({ ...task, epic_id: id });
      createdTasks.push(created);
    }
    return createdTasks;
  }

  async markProjectComplete(): Promise<void> {
    await this.exec(`
      UPDATE projects
      SET completed_at = COALESCE(completed_at, NOW())
      WHERE id = $1
    `, [this.projectId]);
  }

  async getProjectName(): Promise<string> {
    const result = await this.query<{name: string}>(`
      SELECT name FROM projects WHERE id = $1
    `, [this.projectId]);

    if (!result || result.length === 0) {
      throw new Error(`Project ${this.projectId} not found`);
    }

    return result[0].name;
  }

  async getProjectId(): Promise<string> {
    return this.projectId;
  }

  // =========================================================================
  // Epic Re-testing Methods (Phase 5 - Quality System)
  // =========================================================================

  /**
   * Trigger epic re-testing after epic completion.
   * Selects epics to re-test based on priority and returns instructions.
   */
  async triggerEpicRetest(triggeredByEpicId: string | number, sessionId?: string): Promise<{message: string, epics: any[]}> {
    // Get count of completed epics
    const countResult = await this.query<{count: number}>(`
      SELECT COUNT(*)::int as count
      FROM epics
      WHERE project_id = $1 AND status = 'completed'
    `, [this.projectId]);

    const completedCount = countResult[0]?.count || 0;

    console.error(`[triggerEpicRetest] Completed epics: ${completedCount}, triggered by: ${triggeredByEpicId}`);

    // Check if re-testing should be triggered (every 2nd epic by default)
    // This check could be made configurable via .yokeflow.yaml
    const triggerFrequency = 2;
    if (completedCount % triggerFrequency !== 0) {
      return {
        message: `Re-testing not triggered. Completed ${completedCount} epics (triggers every ${triggerFrequency} epics).`,
        epics: []
      };
    }

    // Get epics to re-test using database view
    const epicsToRetest = await this.query<any>(`
      SELECT
        epic_id,
        epic_name,
        priority,
        last_retest_at,
        days_since_last_test,
        stability_score,
        is_foundation,
        retest_priority
      FROM v_foundation_epic_retest_schedule
      WHERE epic_id != $1
      ORDER BY retest_priority DESC, priority DESC
      LIMIT 2
    `, [triggeredByEpicId]);

    if (epicsToRetest.length === 0) {
      return {
        message: 'No epics selected for re-testing (all recently tested or none available).',
        epics: []
      };
    }

    // Build message with instructions
    let message = `🔄 Epic Re-testing Triggered (after epic ${triggeredByEpicId} completion)\n\n`;
    message += `Selected ${epicsToRetest.length} epic(s) for re-testing:\n\n`;

    for (const epic of epicsToRetest) {
      message += `**Epic ${epic.epic_id}: ${epic.epic_name}**\n`;
      message += `- Priority: ${epic.retest_priority} (${epic.is_foundation ? 'foundation' : 'standard'})\n`;

      if (epic.last_retest_at) {
        message += `- Last tested: ${epic.days_since_last_test} day(s) ago\n`;
      } else {
        message += `- Last tested: Never\n`;
      }

      if (epic.stability_score !== null) {
        message += `- Stability: ${(epic.stability_score * 100).toFixed(0)}%\n`;
      }

      message += '\n';
    }

    message += '**Next Steps:**\n';
    message += '1. For each epic above, use `get_epic_tests` to retrieve test requirements\n';
    message += '2. Execute the epic tests (verify requirements are met)\n';
    message += '3. Use `record_epic_retest_result` to record the result\n';
    message += '\nThis helps catch regressions introduced by recent changes.\n';

    return {
      message,
      epics: epicsToRetest
    };
  }

  /**
   * Record the result of an epic re-test.
   */
  async recordEpicRetestResult(params: {
    epicId: string | number;
    triggeredByEpicId?: string | number;
    sessionId?: string;
    testResult: string;
    executionTimeMs?: number;
    errorDetails?: string;
    testsRun?: number;
    testsPassed?: number;
    testsFailed?: number;
  }): Promise<string> {
    const {
      epicId,
      triggeredByEpicId,
      sessionId,
      testResult,
      executionTimeMs,
      errorDetails,
      testsRun = 0,
      testsPassed = 0,
      testsFailed = 0
    } = params;

    // Determine selection reason based on previous data
    const selectionReason = await this._getSelectionReason(Number(epicId));

    // Call database function to record retest
    const result = await this.query<{record_epic_retest: string}>(`
      SELECT record_epic_retest(
        $1::integer,
        $2::integer,
        $3::uuid,
        $4::text,
        false,
        $5::integer,
        $6::text,
        $7::integer,
        $8::integer,
        $9::integer,
        $10::text
      ) as record_epic_retest
    `, [
      epicId,
      triggeredByEpicId || null,
      sessionId || null,
      testResult,
      executionTimeMs || null,
      errorDetails || null,
      testsRun,
      testsPassed,
      testsFailed,
      selectionReason
    ]);

    const retestId = result[0].record_epic_retest;

    console.error(`[recordEpicRetestResult] Recorded retest for epic ${epicId}: ${testResult} (ID: ${retestId})`);

    return retestId;
  }

  /**
   * Get epic stability metrics.
   */
  async getEpicStabilityMetrics(epicId?: string | number): Promise<any[]> {
    if (epicId !== undefined) {
      // Get metrics for specific epic
      const metrics = await this.query<any>(`
        SELECT *
        FROM v_epic_stability_summary
        WHERE epic_id IN (
          SELECT id FROM epics WHERE project_id = $1
        ) AND epic_id = $2
      `, [this.projectId, epicId]);

      return metrics;
    } else {
      // Get metrics for all epics
      const metrics = await this.query<any>(`
        SELECT *
        FROM v_epic_stability_summary
        WHERE epic_id IN (
          SELECT id FROM epics WHERE project_id = $1
        )
        ORDER BY priority DESC, stability_score ASC
      `, [this.projectId]);

      return metrics;
    }
  }

  /**
   * Helper to determine why an epic was selected for re-testing.
   */
  private async _getSelectionReason(epicId: number): Promise<string> {
    // Check if foundation epic
    const epicResult = await this.query<{name: string, priority: number}>(`
      SELECT name, priority
      FROM epics
      WHERE id = $1
    `, [epicId]);

    if (epicResult.length === 0) {
      return 'unknown';
    }

    const epic = epicResult[0];
    const epicName = epic.name.toLowerCase();

    // Foundation keywords
    const foundationKeywords = [
      'database', 'db', 'schema', 'migration',
      'auth', 'authentication', 'authorization', 'security',
      'api', 'endpoint', 'server', 'backend',
      'config', 'configuration', 'setup', 'foundation'
    ];

    const isFoundation = foundationKeywords.some(kw => epicName.includes(kw));
    if (isFoundation) {
      return 'foundation';
    }

    // High priority epic
    if (epic.priority >= 90) {
      return 'high_priority';
    }

    // Check if never tested
    const metricResult = await this.query<{last_retest_at: Date | null}>(`
      SELECT last_retest_at
      FROM epic_stability_metrics
      WHERE epic_id = $1
    `, [epicId]);

    if (metricResult.length === 0 || metricResult[0].last_retest_at === null) {
      return 'never_tested';
    }

    // Check age
    const lastRetest = new Date(metricResult[0].last_retest_at);
    const daysSince = Math.floor((Date.now() - lastRetest.getTime()) / (1000 * 60 * 60 * 24));

    if (daysSince > 14) {
      return `aged_${daysSince}d`;
    } else if (daysSince > 7) {
      return `aged_${daysSince}d`;
    }

    return 'random_sampling';
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}