/**
 * TestCoverageReport - Test coverage statistics and full test listing
 *
 * Shows:
 * - Overall coverage statistics (tasks, tests, coverage %)
 * - All tests grouped by epic → task in a Roadmap-style layout
 */

'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { formatExecutionTime } from '@/lib/utils';
import type {
  TestCoverageResponse,
  AllTestsResponse,
  AllTestsEpic,
  AllTestsTask,
  Test,
  EpicTest,
} from '@/lib/types';
import {
  AlertTriangle,
  BarChart3,
  CheckCircle,
  XCircle,
  Circle,
  Timer,
} from 'lucide-react';

interface TestCoverageReportProps {
  projectId: string;
}

export function TestCoverageReport({ projectId }: TestCoverageReportProps) {
  const [coverage, setCoverage] = useState<TestCoverageResponse | null>(null);
  const [allTests, setAllTests] = useState<AllTestsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [projectId]);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);

      const [coverageData, testsData] = await Promise.all([
        api.getTestCoverage(projectId).catch(() => null),
        api.getAllTests(projectId),
      ]);

      setCoverage(coverageData);
      setAllTests(testsData);
    } catch (err: any) {
      console.error('Failed to load test data:', err);
      setError(err.message || 'Failed to load test data');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3"></div>
          <p className="text-gray-400 text-sm">Loading test coverage...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-600/50 rounded-lg p-4">
        <div className="flex items-center gap-2 text-red-400">
          <AlertTriangle className="w-5 h-5" />
          <span className="font-medium">Failed to load test coverage</span>
        </div>
        <p className="text-sm text-gray-400 mt-1">{error}</p>
      </div>
    );
  }

  if (!allTests || allTests.epics.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-gray-500 text-4xl mb-3">📊</div>
        <p className="text-gray-600 dark:text-gray-400">No test data available</p>
        <p className="text-sm text-gray-500 mt-2">
          Test coverage analysis runs after initialization (Session 0) completes
        </p>
      </div>
    );
  }

  const { overall, warnings } = coverage?.data ?? { overall: null, warnings: [] };

  // Determine coverage quality color
  const getCoverageColor = (percentage: number) => {
    if (percentage >= 90) return 'text-green-400';
    if (percentage >= 70) return 'text-blue-400';
    if (percentage >= 50) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-100 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-blue-400" />
          Test Coverage Analysis
        </h3>
        {coverage?.analyzed_at && (
          <span className="text-xs text-gray-700 dark:text-gray-500">
            Analyzed: {new Date(coverage.analyzed_at).toLocaleString()}
          </span>
        )}
      </div>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="bg-yellow-900/20 border border-yellow-600/50 rounded-lg p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h4 className="font-medium text-yellow-400 mb-2">Coverage Warnings</h4>
              <ul className="space-y-1">
                {warnings.map((warning, idx) => (
                  <li key={idx} className="text-sm text-gray-300">
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Overall Statistics */}
      {overall && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h4 className="font-medium text-gray-100 mb-4">Overall Statistics</h4>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-100">{overall.total_tasks}</div>
              <div className="text-xs text-gray-400 mt-1">Total Tasks</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-400">{overall.total_task_tests || overall.total_tests}</div>
              <div className="text-xs text-gray-400 mt-1">Task Tests</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-400">{overall.total_epic_tests || 0}</div>
              <div className="text-xs text-gray-400 mt-1">Epic Tests</div>
            </div>
            <div className="text-center">
              <div className={`text-2xl font-bold ${getCoverageColor(overall.coverage_percentage)}`}>
                {overall.coverage_percentage.toFixed(1)}%
              </div>
              <div className="text-xs text-gray-400 mt-1">Coverage</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-100">
                {overall.avg_tests_per_task.toFixed(2)}
              </div>
              <div className="text-xs text-gray-400 mt-1">Avg Tests/Task</div>
            </div>
          </div>
        </div>
      )}

      {/* All Tests — Roadmap-style listing */}
      <div className="space-y-10">
        {allTests.epics.map((epic, epicIndex) => (
          <TestCoverageEpicSection
            key={epic.id}
            epic={epic}
            epicNumber={epicIndex + 1}
            isLast={epicIndex === allTests.epics.length - 1}
          />
        ))}
      </div>
    </div>
  );
}


// Epic section — mirrors RoadmapEpicSection layout
function TestCoverageEpicSection({ epic, epicNumber, isLast }: {
  epic: AllTestsEpic;
  epicNumber: number;
  isLast?: boolean;
}) {
  return (
    <section className="scroll-mt-20">
      {/* Epic heading */}
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-gray-100">
          <span className="text-gray-500 font-mono mr-2">{epicNumber}.</span>
          {epic.name}
        </h2>
        {epic.description && (
          <p className="mt-2 text-gray-400 leading-relaxed">{epic.description}</p>
        )}
      </div>

      {/* Epic-level integration tests */}
      {epic.epic_tests.length > 0 && (
        <div className="ml-2 mb-5">
          <p className="text-xs font-medium text-purple-400 uppercase tracking-wider mb-2">
            Epic Integration Tests
          </p>
          <div className="space-y-1.5">
            {epic.epic_tests.map((test) => (
              <EpicTestItem key={test.id} test={test} />
            ))}
          </div>
        </div>
      )}

      {/* Tasks with their tests */}
      {epic.tasks.length > 0 ? (
        <div className="ml-2 space-y-5">
          {epic.tasks.map((task, taskIndex) => (
            <div key={task.id}>
              {/* Task heading */}
              <div className="flex items-start gap-3 mb-2">
                <span className="text-gray-500 font-mono text-sm mt-0.5 w-10 text-right flex-shrink-0">
                  {epicNumber}.{taskIndex + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-gray-200 font-medium">{task.name}</p>
                </div>
              </div>

              {/* Task tests */}
              {task.tests.length > 0 ? (
                <div className="ml-14 space-y-1.5">
                  {task.tests.map((test) => (
                    <TaskTestItem key={test.id} test={test} />
                  ))}
                </div>
              ) : (
                <p className="ml-14 text-xs text-gray-600 italic">No tests</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="ml-2 text-sm text-gray-600 italic">No tasks defined</p>
      )}

      {/* Divider */}
      {!isLast && (
        <div className="mt-8 border-b border-gray-800/50"></div>
      )}
    </section>
  );
}


// Individual task test row
function TaskTestItem({ test }: { test: Test }) {
  return (
    <div className="flex items-start gap-2.5 py-1">
      {/* Status icon */}
      <div className="flex-shrink-0 mt-0.5">
        {test.passes === true ? (
          <CheckCircle className="w-4 h-4 text-green-400" />
        ) : test.passes === false ? (
          <XCircle className="w-4 h-4 text-red-400" />
        ) : (
          <Circle className="w-4 h-4 text-gray-600" />
        )}
      </div>

      {/* Description and metadata */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-300">{test.description}</span>
          {test.test_type && (
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${
              test.test_type === 'unit' ? 'bg-green-500/20 text-green-400 border-green-500/30' :
              test.test_type === 'api' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
              test.test_type === 'browser' ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' :
              test.test_type === 'database' ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' :
              'bg-gray-500/20 text-gray-400 border-gray-500/30'
            }`}>
              {test.test_type}
            </span>
          )}
          {test.execution_time_ms != null && (
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <Timer className="w-3 h-3" />
              {formatExecutionTime(test.execution_time_ms)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}


// Epic-level test row
function EpicTestItem({ test }: { test: EpicTest }) {
  return (
    <div className="flex items-start gap-2.5 py-1">
      {/* Status icon */}
      <div className="flex-shrink-0 mt-0.5">
        {test.passes === true ? (
          <CheckCircle className="w-4 h-4 text-green-400" />
        ) : test.passes === false ? (
          <XCircle className="w-4 h-4 text-red-400" />
        ) : (
          <Circle className="w-4 h-4 text-gray-600" />
        )}
      </div>

      {/* Description and metadata */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-300">{test.name || test.description}</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-500/20 text-purple-400 border border-purple-500/30">
            epic
          </span>
          {test.test_type && (
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${
              test.test_type === 'integration' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
              test.test_type === 'e2e' ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' :
              'bg-gray-500/20 text-gray-400 border-gray-500/30'
            }`}>
              {test.test_type}
            </span>
          )}
          {test.execution_time_ms != null && (
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <Timer className="w-3 h-3" />
              {formatExecutionTime(test.execution_time_ms)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
