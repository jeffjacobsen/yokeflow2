#!/usr/bin/env node
/**
 * MCP Server for Task Management
 * Provides structured task management capabilities for YokeFlow agents
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import crypto from 'crypto';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import type { Tool } from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';
import path from 'path';
import { fileURLToPath } from 'url';
// Import database implementation
import { TaskDatabase } from './database.js';
import type { NewTask, NewTest, NewEpic, NewEpicTest } from './types.js';

// Get __dirname equivalent in ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Initialize database
const db = new TaskDatabase();

// Log database info
console.error(`Using PostgreSQL database for project: ${process.env.PROJECT_ID || 'unknown'}`);

// Helper to define ID field that works with both legacy (number) and PostgreSQL (string/UUID)
const idFieldSchema = {
  oneOf: [
    { type: 'number' },
    { type: 'string' }
  ]
};

// Test execution functions removed - tests are now requirement-based
// Agents receive test requirements via get_task_tests and get_epic_tests

/**
 * Get test requirements for a task
 * Returns integration test requirements for the epic
 */
async function getTaskTestRequirements(taskId: string): Promise<{hasRequirements: boolean, summary: string}> {
  try {
    // Get all tests for the task
    const tests = await db.getTaskTests(taskId);

    if (!tests || tests.length === 0) {
      return {
        hasRequirements: false,
        summary: `No test requirements found for task ${taskId}. Tests should be created during initialization.`
      };
    }

    console.error(`[TaskTests] Found ${tests.length} test requirements for task ${taskId}`);

    const requirements: string[] = [];
    requirements.push(`📋 Test Requirements for Task ${taskId}`);
    requirements.push('');
    requirements.push('The following requirements must be verified before marking this task complete:');
    requirements.push('');

    for (let i = 0; i < tests.length; i++) {
      const test = tests[i];
      requirements.push(`### Test ${i + 1}: ${test.description}`);
      requirements.push(`Test ID: ${test.id}`);
      requirements.push(`Type: ${test.test_type || 'unspecified'}`);
      requirements.push('');

      if (test.requirements) {
        requirements.push('**Requirements:**');
        requirements.push(test.requirements);
        requirements.push('');
      }

      if (test.success_criteria) {
        requirements.push('**Success Criteria:**');
        requirements.push(test.success_criteria);
        requirements.push('');
      }

      if (test.steps && test.steps !== '[]') {
        requirements.push('**Verification Steps:**');
        const steps = typeof test.steps === 'string' ? JSON.parse(test.steps) : test.steps;
        steps.forEach((step: string, idx: number) => {
          requirements.push(`${idx + 1}. ${step}`);
        });
        requirements.push('');
      }

      requirements.push('---');
      requirements.push('');
    }

    requirements.push('');
    requirements.push('⚠️  **IMPORTANT**: You must verify each requirement above and provide evidence that it passes.');
    requirements.push('Use whatever methods are appropriate (manual testing, curl commands, browser verification, etc.)');
    requirements.push('Document your verification in the task notes before marking the task complete.');

    return {
      hasRequirements: true,
      summary: requirements.join('\n')
    };
  } catch (error: any) {
    return {
      hasRequirements: false,
      summary: `Error getting test requirements for task ${taskId}: ${error.message}`
    };
  }
}

/**
 * Get epic test requirements
 * Returns integration test requirements for the epic
 */
async function getEpicTestRequirements(epicId: string): Promise<{hasRequirements: boolean, summary: string}> {
  try {
    // Get all tests for the epic
    const tests = await db.getEpicTests(epicId);

    if (!tests || tests.length === 0) {
      return {
        hasRequirements: false,
        summary: `No integration test requirements found for epic ${epicId}. Epic tests should be created during initialization.`
      };
    }

    // Get epic details for context
    const epic = await db.getEpic(epicId);
    const epicName = epic ? epic.name : `Epic ${epicId}`;

    console.error(`[EpicTests] Found ${tests.length} integration test requirements for ${epicName}`);

    const requirements: string[] = [];
    requirements.push(`📋 Integration Test Requirements for Epic: ${epicName}`);
    requirements.push('');
    requirements.push('The following integration requirements must be verified before marking this epic complete:');
    requirements.push('');

    for (let i = 0; i < tests.length; i++) {
      const test = tests[i];
      requirements.push(`### Integration Test ${i + 1}: ${test.name}`);
      requirements.push(`Test ID: ${test.id}`);
      requirements.push(`Description: ${test.description}`);
      requirements.push(`Type: ${test.test_type || 'integration'}`);
      requirements.push('');

      if (test.requirements) {
        requirements.push('**Requirements:**');
        requirements.push(test.requirements);
        requirements.push('');
      }

      if (test.success_criteria) {
        requirements.push('**Success Criteria:**');
        requirements.push(test.success_criteria);
        requirements.push('');
      }

      if (test.key_verification_points) {
        requirements.push('**Key Verification Points:**');
        const points = typeof test.key_verification_points === 'string'
          ? JSON.parse(test.key_verification_points)
          : test.key_verification_points;
        if (Array.isArray(points)) {
          points.forEach((point: string, idx: number) => {
            requirements.push(`${idx + 1}. ${point}`);
          });
        }
        requirements.push('');
      }

      if (test.depends_on_tasks && test.depends_on_tasks.length > 0) {
        requirements.push(`**Depends on tasks:** ${test.depends_on_tasks.join(', ')}`);
        requirements.push('');
      }

      requirements.push('---');
      requirements.push('');
    }

    requirements.push('');
    requirements.push('⚠️  **IMPORTANT**: These are INTEGRATION tests - verify the complete workflow across all tasks.');
    requirements.push('Ensure data flows correctly between components and the end-to-end user experience works.');
    requirements.push('Document your verification process before marking the epic complete.');

    return {
      hasRequirements: true,
      summary: requirements.join('\n')
    };
  } catch (error: any) {
    return {
      hasRequirements: false,
      summary: `Error getting test requirements for epic ${epicId}: ${error.message}`
    };
  }
}

// Define tool schemas
const tools: Tool[] = [
  {
    name: 'task_status',
    description: 'Get overall project status including epics, tasks, and tests progress',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'get_next_task',
    description: 'Get the next highest priority incomplete task to work on',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'list_epics',
    description: 'List all epics or epics that need task expansion',
    inputSchema: {
      type: 'object',
      properties: {
        needs_expansion: {
          type: 'boolean',
          description: 'If true, only show epics with no tasks'
        }
      }
    }
  },
  {
    name: 'get_epic',
    description: 'Get details of a specific epic including its tasks',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The ID of the epic'
        }
      },
      required: ['epic_id']
    }
  },
  {
    name: 'list_tasks',
    description: 'List tasks with optional filtering',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'Filter by epic ID'
        },
        only_pending: {
          type: 'boolean',
          description: 'Only show incomplete tasks'
        }
      }
    }
  },
  {
    name: 'get_task',
    description: 'Get detailed information about a specific task including its tests',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task'
        }
      },
      required: ['task_id']
    }
  },
  {
    name: 'list_tests',
    description: 'List all tests for a specific task',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task'
        }
      },
      required: ['task_id']
    }
  },
  {
    name: 'create_epic',
    description: 'Create a new epic',
    inputSchema: {
      type: 'object',
      properties: {
        name: {
          type: 'string',
          description: 'Name of the epic'
        },
        description: {
          type: 'string',
          description: 'Detailed description of the epic'
        },
        priority: {
          type: 'number',
          description: 'Priority (lower number = higher priority)'
        }
      },
      required: ['name', 'priority']
    }
  },
  {
    name: 'create_task',
    description: 'Create a new task within an epic',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The epic this task belongs to'
        },
        name: {
          type: 'string',
          description: 'Brief name/title of the task'
        },
        description: {
          type: 'string',
          description: 'Detailed implementation instructions'
        },
        priority: {
          type: 'number',
          description: 'Priority within the epic (optional, auto-increments)'
        }
      },
      required: ['epic_id', 'name', 'description']
    }
  },
  {
    name: 'create_task_test',
    description: 'Create a test case for a task',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The task this test belongs to'
        },
        category: {
          type: 'string',
          enum: ['functional', 'style', 'accessibility', 'performance'],
          description: 'Category of test'
        },
        test_type: {
          type: 'string',
          enum: ['unit', 'api', 'browser', 'database', 'integration'],
          description: 'Type of test execution needed'
        },
        description: {
          type: 'string',
          description: 'What this test verifies'
        },
        steps: {
          type: 'array',
          items: { type: 'string' },
          description: 'Array of test steps to perform'
        },
        requirements: {
          type: 'string',
          description: 'Test requirements describing what to verify (not how)'
        },
        success_criteria: {
          type: 'string',
          description: 'Clear criteria for determining test success'
        }
      },
      required: ['task_id', 'category', 'description', 'steps']
    }
  },
  {
    name: 'update_task_status',
    description: 'Mark a task as done or not done',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task'
        },
        done: {
          type: 'boolean',
          description: 'Whether the task is completed'
        }
      },
      required: ['task_id', 'done']
    }
  },
  {
    name: 'start_task',
    description: 'Mark a task as started/in progress',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task to start'
        }
      },
      required: ['task_id']
    }
  },
  {
    name: 'claim_next_task',
    description: 'Atomically claim the next available task for a worker. Uses row-level locking to prevent duplicate claims in parallel execution. Returns the claimed task or null if no tasks available.',
    inputSchema: {
      type: 'object',
      properties: {
        worker_id: {
          type: 'string',
          description: 'Unique identifier for the worker claiming the task (e.g. "worker-1")'
        }
      },
      required: ['worker_id']
    }
  },
  {
    name: 'update_task_test_result',
    description: 'Mark a task test as passing or failing',
    inputSchema: {
      type: 'object',
      properties: {
        test_id: {
          ...idFieldSchema,
          description: 'The ID of the task test'
        },
        passes: {
          type: 'boolean',
          description: 'Whether the test passes'
        },
        verification_notes: {
          type: 'string',
          description: 'Optional notes about how the test was verified (what was checked and results)'
        },
        error_message: {
          type: 'string',
          description: 'Optional brief error message if test failed (for UI display)'
        },
        execution_time_ms: {
          type: 'number',
          description: 'Optional execution time in milliseconds for performance tracking'
        }
      },
      required: ['test_id', 'passes']
    }
  },
  {
    name: 'update_epic_test_result',
    description: 'Mark an epic test as passing or failing',
    inputSchema: {
      type: 'object',
      properties: {
        test_id: {
          ...idFieldSchema,
          description: 'The ID of the epic test'
        },
        result: {
          type: 'string',
          enum: ['passed', 'failed'],
          description: 'The test result (passed or failed)'
        },
        execution_log: {
          type: 'string',
          description: 'Optional execution log for the test'
        },
        verification_notes: {
          type: 'string',
          description: 'Optional notes about how the epic was verified (what was checked and results)'
        },
        error_message: {
          type: 'string',
          description: 'Optional brief error message if test failed (for UI display)'
        },
        execution_time_ms: {
          type: 'number',
          description: 'Optional execution time in milliseconds for performance tracking'
        }
      },
      required: ['test_id', 'result']
    }
  },
  {
    name: 'create_epic_test',
    description: 'Create an integration test for an epic',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The epic this test belongs to'
        },
        name: {
          type: 'string',
          description: 'Name of the integration test'
        },
        description: {
          type: 'string',
          description: 'What this integration test verifies'
        },
        test_type: {
          type: 'string',
          enum: ['integration', 'e2e', 'workflow'],
          description: 'Type of epic test (default: integration)'
        },
        depends_on_tasks: {
          type: 'array',
          items: { ...idFieldSchema },
          description: 'Task IDs that must complete before this test'
        },
        requirements: {
          type: 'string',
          description: 'Integration test requirements for the epic'
        },
        success_criteria: {
          type: 'string',
          description: 'Clear criteria for epic test success'
        },
        key_verification_points: {
          type: 'array',
          items: { type: 'string' },
          description: 'Key points to verify in the workflow'
        }
      },
      required: ['epic_id', 'name', 'description']
    }
  },
  {
    name: 'get_task_tests',
    description: 'Get test requirements and details for a task',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task whose tests to retrieve'
        },
        stop_on_failure: {
          type: 'boolean',
          description: 'Whether to stop on first failure (default: true)'
        }
      },
      required: ['task_id']
    }
  },
  {
    name: 'get_epic_tests',
    description: 'Get integration test requirements and details for an epic',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The ID of the epic whose tests to retrieve'
        },
        stop_on_failure: {
          type: 'boolean',
          description: 'Whether to stop on first failure (default: false)'
        },
        verbose: {
          type: 'boolean',
          description: 'Whether to show detailed output (default: false)'
        }
      },
      required: ['epic_id']
    }
  },
  {
    name: 'trigger_epic_retest',
    description: 'Trigger epic re-testing after epic completion. Re-tests prior epics to catch regressions. Called automatically after every 2nd epic completion (configurable).',
    inputSchema: {
      type: 'object',
      properties: {
        triggered_by_epic_id: {
          ...idFieldSchema,
          description: 'The epic that just completed (triggers re-testing)'
        },
        session_id: {
          type: 'string',
          description: 'Current session ID'
        }
      },
      required: ['triggered_by_epic_id']
    }
  },
  {
    name: 'record_epic_retest_result',
    description: 'Record the result of an epic re-test. Call this after re-running epic tests to track stability and detect regressions.',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The epic that was re-tested'
        },
        triggered_by_epic_id: {
          ...idFieldSchema,
          description: 'The epic that triggered this re-test'
        },
        session_id: {
          type: 'string',
          description: 'Current session ID'
        },
        test_result: {
          type: 'string',
          enum: ['passed', 'failed', 'skipped', 'error'],
          description: 'Overall result of the re-test'
        },
        execution_time_ms: {
          type: 'number',
          description: 'Total execution time in milliseconds'
        },
        error_details: {
          type: 'string',
          description: 'Error message if test failed'
        },
        tests_run: {
          type: 'number',
          description: 'Number of tests executed'
        },
        tests_passed: {
          type: 'number',
          description: 'Number of tests that passed'
        },
        tests_failed: {
          type: 'number',
          description: 'Number of tests that failed'
        }
      },
      required: ['epic_id', 'test_result']
    }
  },
  {
    name: 'get_epic_stability_metrics',
    description: 'Get stability metrics and re-test history for epics. Shows stability scores, regression counts, and re-test patterns.',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'Specific epic ID (optional - omit for all epics)'
        }
      }
    }
  },
  {
    name: 'expand_epic',
    description: 'Break down an epic into multiple tasks',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The ID of the epic to expand'
        },
        tasks: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              description: { type: 'string' },
              priority: { type: 'number' }
            },
            required: ['name', 'description']
          },
          description: 'Array of tasks to create for this epic'
        }
      },
      required: ['epic_id', 'tasks']
    }
  },
  {
    name: 'mark_project_complete',
    description: 'Mark the project as complete when all epics, tasks, and tests are finished. Sets the completion timestamp in the database.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'get_session_history',
    description: 'Get recent session history',
    inputSchema: {
      type: 'object',
      properties: {
        limit: {
          type: 'number',
          description: 'Maximum number of sessions to return (default: 10)'
        }
      }
    }
  },
];

// Create MCP server
const server = new Server(
  {
    name: 'mcp-task-manager',
    version: '1.0.0'
  },
  {
    capabilities: {
      tools: {},
      resources: {}
    }
  }
);

// Handle tool listing
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools };
});

// Handle resource listing (we don't use resources, but SDK might expect this)
server.setRequestHandler(ListResourcesRequestSchema, async () => {
  return { resources: [] };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'task_status':
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(await db.getProjectStatus(), null, 2)
            }
          ]
        };

      case 'get_next_task':
        const nextTask = await db.getNextTask();
        if (!nextTask) {
          return {
            content: [
              {
                type: 'text',
                text: 'No pending tasks found. Consider expanding epics that need tasks.'
              }
            ]
          };
        }

        // Check if this is a special epic test requirement task
        if (nextTask.id === 'EPIC_TEST_REQUIRED') {
          // Return it as formatted text with clear instructions
          return {
            content: [
              {
                type: 'text',
                text: `${nextTask.name}\n\n${nextTask.description}\n\nEpic: ${nextTask.epic_name} (ID: ${nextTask.epic_id})`
              }
            ]
          };
        }

        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(nextTask, null, 2)
            }
          ]
        };

      case 'list_epics':
        const epics = await db.listEpics(args?.needs_expansion as boolean);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(epics, null, 2)
            }
          ]
        };

      case 'get_epic':
        const epic = await db.getEpic(args?.epic_id as any);
        if (!epic) {
          throw new Error(`Epic ${args?.epic_id} not found`);
        }
        const epicProgress = await db.getEpicProgress(args?.epic_id as any);
        const epicTasks = await db.listTasks(args?.epic_id as any);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({ epic, progress: epicProgress[0], tasks: epicTasks }, null, 2)
            }
          ]
        };

      case 'list_tasks':
        const tasks = await db.listTasks(
          args?.epic_id as any | undefined,
          args?.only_pending as boolean
        );
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(tasks, null, 2)
            }
          ]
        };

      case 'get_task':
        const task = await db.getTask(args?.task_id as any);
        if (!task) {
          throw new Error(`Task ${args?.task_id} not found`);
        }
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(task, null, 2)
            }
          ]
        };

      case 'list_tests':
        const tests = await db.listTests(args?.task_id as any);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(tests, null, 2)
            }
          ]
        };

      case 'create_epic':
        const newEpic: NewEpic = {
          name: args?.name as string,
          description: args?.description as string,
          priority: args?.priority as number
        };
        const createdEpic = await db.createEpic(newEpic);
        return {
          content: [
            {
              type: 'text',
              text: `Created epic ${createdEpic.id}: ${createdEpic.name}`
            }
          ]
        };

      case 'create_task':
        const newTask: NewTask = {
          epic_id: args?.epic_id as any,
          name: args?.name as string,
          description: args?.description as string,
          priority: args?.priority as number
        };
        const createdTask = await db.createTask(newTask);
        return {
          content: [
            {
              type: 'text',
              text: `Created task ${createdTask.id}: ${createdTask.name}`
            }
          ]
        };

      case 'create_task_test':
        const newTest: NewTest = {
          task_id: args?.task_id as any,
          category: args?.category as any,
          description: args?.description as string,
          steps: args?.steps as string[],
          test_type: args?.test_type as any,
          requirements: args?.requirements as string | undefined,
          success_criteria: args?.success_criteria as string | undefined
        };
        const createdTest = await db.createTest(newTest);
        return {
          content: [
            {
              type: 'text',
              text: `Created test ${createdTest.id}: ${createdTest.description}${newTest.test_type ? ` (${newTest.test_type})` : ''}`
            }
          ]
        };

      case 'update_task_status':
        // Simply update the task status without verification
        // Verification should happen BEFORE this using run_task_tests
        const updatedTask = await db.updateTaskStatus(
          args?.task_id as any,
          args?.done as boolean
        );
        if (!updatedTask) {
          throw new Error(`Task ${args?.task_id} not found`);
        }

        return {
          content: [
            {
              type: 'text',
              text: `Task ${updatedTask.id} marked as ${args?.done ? 'completed' : 'incomplete'}`
            }
          ]
        };

      case 'start_task':
        await db.startTask(args?.task_id as any);
        return {
          content: [
            {
              type: 'text',
              text: `Task ${args?.task_id} marked as started`
            }
          ]
        };

      case 'claim_next_task':
        const claimedTask = await db.claimNextTask(args?.worker_id as string);
        if (!claimedTask) {
          return {
            content: [
              {
                type: 'text',
                text: 'No tasks available to claim'
              }
            ]
          };
        }
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(claimedTask, null, 2)
            }
          ]
        };

      case 'update_task_test_result':
        const updatedTest = await db.updateTestResult(
          args?.test_id as any,
          args?.passes as boolean,
          args?.verification_notes as string | undefined,
          args?.error_message as string | undefined,
          args?.execution_time_ms as number | undefined
        );
        if (!updatedTest) {
          throw new Error(`Test ${args?.test_id} not found`);
        }
        return {
          content: [
            {
              type: 'text',
              text: `Test ${updatedTest.id} marked as ${args?.passes ? 'passing' : 'failing'}${args?.execution_time_ms ? ` (${args.execution_time_ms}ms)` : ''}`
            }
          ]
        };

      case 'update_epic_test_result':
        await db.updateEpicTestResult(
          args?.test_id as any,
          args?.result as 'passed' | 'failed',
          args?.execution_log as string | undefined,
          args?.verification_notes as string | undefined,
          args?.error_message as string | undefined,
          args?.execution_time_ms as number | undefined
        );
        return {
          content: [
            {
              type: 'text',
              text: `Epic test ${args?.test_id} marked as ${args?.result}${args?.execution_time_ms ? ` (${args.execution_time_ms}ms)` : ''}`
            }
          ]
        };

      case 'create_epic_test':
        const newEpicTest: NewEpicTest = {
          epic_id: args?.epic_id as any,
          name: args?.name as string,
          description: args?.description as string,
          test_type: args?.test_type as any || 'integration',
          requirements: args?.requirements as string | undefined,
          success_criteria: args?.success_criteria as string | undefined,
          key_verification_points: args?.key_verification_points as any | undefined,
          depends_on_tasks: args?.depends_on_tasks as any[] | undefined
        };
        const createdEpicTest = await db.createEpicTest(newEpicTest);
        return {
          content: [
            {
              type: 'text',
              text: `Created epic test ${createdEpicTest.id}: ${createdEpicTest.name} (${newEpicTest.test_type})`
            }
          ]
        };


      case 'get_task_tests':
        const taskIdForTests = args?.task_id as any;
        const taskTestRequirements = await getTaskTestRequirements(taskIdForTests);

        return {
          content: [
            {
              type: 'text',
              text: taskTestRequirements.summary
            }
          ],
          isError: !taskTestRequirements.hasRequirements
        };

      case 'get_epic_tests':
        const epicIdForTests = args?.epic_id as any;
        const epicTestRequirements = await getEpicTestRequirements(epicIdForTests);

        return {
          content: [
            {
              type: 'text',
              text: epicTestRequirements.summary
            }
          ],
          isError: !epicTestRequirements.hasRequirements
        };

      case 'trigger_epic_retest':
        const triggeredByEpicId = args?.triggered_by_epic_id as any;
        const sessionIdForRetest = args?.session_id as string | undefined;

        try {
          const retestResult = await db.triggerEpicRetest(triggeredByEpicId, sessionIdForRetest);

          return {
            content: [
              {
                type: 'text',
                text: retestResult.message
              }
            ]
          };
        } catch (error: any) {
          console.error(`[trigger_epic_retest] Error: ${error.message}`);
          return {
            content: [
              {
                type: 'text',
                text: `Failed to trigger epic re-testing: ${error.message}`
              }
            ],
            isError: true
          };
        }

      case 'record_epic_retest_result':
        const epicIdForRetest = args?.epic_id as any;
        const triggeredByForResult = args?.triggered_by_epic_id as any;
        const sessionIdForResult = args?.session_id as string | undefined;
        const testResult = args?.test_result as string;
        const executionTimeMs = args?.execution_time_ms as number | undefined;
        const errorDetails = args?.error_details as string | undefined;
        const testsRun = args?.tests_run as number | undefined;
        const testsPassed = args?.tests_passed as number | undefined;
        const testsFailed = args?.tests_failed as number | undefined;

        try {
          const retestId = await db.recordEpicRetestResult({
            epicId: epicIdForRetest,
            triggeredByEpicId: triggeredByForResult,
            sessionId: sessionIdForResult,
            testResult,
            executionTimeMs,
            errorDetails,
            testsRun,
            testsPassed,
            testsFailed
          });

          // Check if this was a regression
          const metrics = await db.getEpicStabilityMetrics(epicIdForRetest);
          const isRegression = metrics && metrics.length > 0 &&
            metrics[0].last_retest_result === 'failed' &&
            testResult === 'failed';

          let message = `✅ Epic re-test result recorded (ID: ${retestId})\n\n`;
          message += `Epic: ${epicIdForRetest}\n`;
          message += `Result: ${testResult}\n`;

          if (testsRun !== undefined) {
            message += `Tests: ${testsPassed || 0}/${testsRun} passed`;
            if (testsFailed) message += `, ${testsFailed} failed`;
            message += `\n`;
          }

          if (executionTimeMs) {
            message += `Execution time: ${(executionTimeMs / 1000).toFixed(2)}s\n`;
          }

          if (isRegression) {
            message += `\n⚠️  REGRESSION DETECTED: This epic was passing before and is now failing!\n`;
          }

          if (errorDetails) {
            message += `\nError: ${errorDetails}\n`;
          }

          return {
            content: [
              {
                type: 'text',
                text: message
              }
            ],
            isError: testResult === 'failed' || testResult === 'error'
          };
        } catch (error: any) {
          console.error(`[record_epic_retest_result] Error: ${error.message}`);
          return {
            content: [
              {
                type: 'text',
                text: `Failed to record epic re-test result: ${error.message}`
              }
            ],
            isError: true
          };
        }

      case 'get_epic_stability_metrics':
        const epicIdForMetrics = args?.epic_id as any | undefined;

        try {
          const metrics = await db.getEpicStabilityMetrics(epicIdForMetrics);

          if (!metrics || metrics.length === 0) {
            return {
              content: [
                {
                  type: 'text',
                  text: epicIdForMetrics
                    ? `No stability metrics found for epic ${epicIdForMetrics}`
                    : 'No stability metrics found for any epics yet'
                }
              ]
            };
          }

          let message = '📊 Epic Stability Metrics\n\n';

          for (const metric of metrics) {
            message += `**Epic ${metric.epic_id}: ${metric.epic_name}**\n`;
            message += `Status: ${metric.epic_status} | Priority: ${metric.priority}\n`;
            message += `Stability Score: ${metric.stability_score?.toFixed(2) || 'N/A'} (${metric.stability_rating || 'unrated'})\n`;
            message += `Re-tests: ${metric.total_retests} total, ${metric.passed_retests} passed, ${metric.failed_retests} failed\n`;

            if (metric.regression_count > 0) {
              message += `⚠️  Regressions: ${metric.regression_count}\n`;
            }

            if (metric.last_retest_at) {
              const daysAgo = metric.days_since_retest;
              message += `Last re-tested: ${daysAgo} day(s) ago - ${metric.last_retest_result}\n`;
            } else {
              message += `Last re-tested: Never\n`;
            }

            if (metric.avg_execution_time_ms) {
              message += `Avg execution time: ${(metric.avg_execution_time_ms / 1000).toFixed(2)}s\n`;
            }

            message += '\n';
          }

          return {
            content: [
              {
                type: 'text',
                text: message
              }
            ]
          };
        } catch (error: any) {
          console.error(`[get_epic_stability_metrics] Error: ${error.message}`);
          return {
            content: [
              {
                type: 'text',
                text: `Failed to get epic stability metrics: ${error.message}`
              }
            ],
            isError: true
          };
        }

      case 'expand_epic':
        const expandedTasks = await db.expandEpic(
          args?.epic_id as any,
          args?.tasks as NewTask[]
        );
        return {
          content: [
            {
              type: 'text',
              text: `Expanded epic ${args?.epic_id} with ${expandedTasks.length} tasks:\n${
                expandedTasks.map(t => `- Task ${t.id}: ${t.name}`).join('\n')
              }`
            }
          ]
        };

      // REMOVED: case 'log_session' - deprecated tool that created phantom sessions
      // Sessions are now managed entirely by the orchestrator

      case 'mark_project_complete':
        await db.markProjectComplete();
        return {
          content: [
            {
              type: 'text',
              text: 'Project marked as complete! 🎉'
            }
          ]
        };

      case 'get_session_history':
        const sessions = await db.getSessionHistory(args?.limit as number);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(sessions, null, 2)
            }
          ]
        };

      // Test execution removed - tests are now requirement-based

      // Agents use get_task_tests and get_epic_tests to get requirements

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
    return {
      content: [
        {
          type: 'text',
          text: `Error: ${errorMessage}`
        }
      ],
      isError: true
    };
  }
});

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('MCP Task Manager Server started');
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});

// Handle cleanup
process.on('SIGINT', () => {
  db.close();
  process.exit(0);
});

process.on('SIGTERM', () => {
  db.close();
  process.exit(0);
});