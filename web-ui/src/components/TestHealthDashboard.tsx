/**
 * TestHealthDashboard - Display test health aggregates
 *
 * Shows slow, flaky, and currently failing tests across the project.
 * Data comes from the /api/projects/{id}/test-health endpoint.
 */

'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { formatExecutionTime } from '@/lib/utils';
import type { TestHealthResponse, TestWithContext, EpicTestWithContext } from '@/lib/types';
import {
  AlertTriangle,
  Clock,
  RefreshCw,
  XCircle,
  CheckCircle,
  Activity,
  Timer,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

interface TestHealthDashboardProps {
  projectId: string;
}

export function TestHealthDashboard({ projectId }: TestHealthDashboardProps) {
  const [health, setHealth] = useState<TestHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedSection, setExpandedSection] = useState<string | null>('failing');

  useEffect(() => {
    loadHealthData();
  }, [projectId]);

  async function loadHealthData() {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getTestHealth(projectId);
      setHealth(data);
    } catch (err: any) {
      console.error('Failed to load test health:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to load test health data');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3"></div>
          <p className="text-gray-400 text-sm">Loading test health data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
        <p className="font-medium mb-1">Error loading test health</p>
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  if (!health) {
    return (
      <div className="text-center py-8 text-gray-500">
        <Activity className="w-8 h-8 mx-auto mb-2 opacity-50" />
        <p>No test health data available</p>
      </div>
    );
  }

  const { summary } = health;
  const hasSlowTests = health.slow_task_tests.length > 0 || health.slow_epic_tests.length > 0;
  const hasFlakyTests = health.flaky_task_tests.length > 0 || health.flaky_epic_tests.length > 0;
  const hasFailingTests = health.failed_task_tests.length > 0 || health.failed_epic_tests.length > 0;

  const toggleSection = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section);
  };

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard
          label="Total Tests"
          value={summary.total_tests}
          icon={<Activity className="w-5 h-5 text-blue-400" />}
          color="blue"
        />
        <SummaryCard
          label="Failing"
          value={summary.failed_count}
          icon={<XCircle className="w-5 h-5 text-red-400" />}
          color="red"
          highlight={summary.failed_count > 0}
        />
        <SummaryCard
          label="Flaky"
          value={summary.flaky_count}
          icon={<RefreshCw className="w-5 h-5 text-amber-400" />}
          color="amber"
          highlight={summary.flaky_count > 0}
        />
        <SummaryCard
          label="Slow"
          value={summary.slow_count}
          icon={<Clock className="w-5 h-5 text-yellow-400" />}
          color="yellow"
          highlight={summary.slow_count > 0}
        />
      </div>

      {/* No Issues */}
      {!hasFailingTests && !hasFlakyTests && !hasSlowTests && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-6 text-center">
          <CheckCircle className="w-8 h-8 text-green-400 mx-auto mb-2" />
          <p className="text-green-400 font-medium">All tests healthy</p>
          <p className="text-gray-400 text-sm mt-1">No failing, flaky, or slow tests detected</p>
        </div>
      )}

      {/* Currently Failing */}
      {hasFailingTests && (
        <TestSection
          title="Currently Failing"
          icon={<XCircle className="w-4 h-4 text-red-400" />}
          count={health.failed_task_tests.length + health.failed_epic_tests.length}
          color="red"
          expanded={expandedSection === 'failing'}
          onToggle={() => toggleSection('failing')}
        >
          {health.failed_task_tests.map((test) => (
            <TaskTestRow key={test.id} test={test} metric={
              <span className="text-red-400 text-xs">Failed</span>
            } />
          ))}
          {health.failed_epic_tests.map((test) => (
            <EpicTestRow key={test.id} test={test} metric={
              <span className="text-red-400 text-xs">Failed</span>
            } />
          ))}
        </TestSection>
      )}

      {/* Flaky Tests */}
      {hasFlakyTests && (
        <TestSection
          title="Flaky Tests"
          icon={<RefreshCw className="w-4 h-4 text-amber-400" />}
          count={health.flaky_task_tests.length + health.flaky_epic_tests.length}
          color="amber"
          expanded={expandedSection === 'flaky'}
          onToggle={() => toggleSection('flaky')}
        >
          {health.flaky_task_tests.map((test) => (
            <TaskTestRow key={test.id} test={test} metric={
              <span className="text-amber-400 text-xs flex items-center gap-1">
                <RefreshCw className="w-3 h-3" />
                Flaky
              </span>
            } />
          ))}
          {health.flaky_epic_tests.map((test) => (
            <EpicTestRow key={test.id} test={test} metric={
              <span className="text-amber-400 text-xs flex items-center gap-1">
                <RefreshCw className="w-3 h-3" />
                Flaky
              </span>
            } />
          ))}
        </TestSection>
      )}

      {/* Slow Tests */}
      {hasSlowTests && (
        <TestSection
          title="Slow Tests"
          icon={<Clock className="w-4 h-4 text-yellow-400" />}
          count={health.slow_task_tests.length + health.slow_epic_tests.length}
          color="yellow"
          expanded={expandedSection === 'slow'}
          onToggle={() => toggleSection('slow')}
        >
          {health.slow_task_tests.map((test) => (
            <TaskTestRow key={test.id} test={test} metric={
              <span className="text-yellow-400 text-xs flex items-center gap-1">
                <Timer className="w-3 h-3" />
                {test.execution_time_ms != null ? formatExecutionTime(test.execution_time_ms) : '—'}
              </span>
            } />
          ))}
          {health.slow_epic_tests.map((test) => (
            <EpicTestRow key={test.id} test={test} metric={
              <span className="text-yellow-400 text-xs flex items-center gap-1">
                <Timer className="w-3 h-3" />
                {test.execution_time_ms != null ? formatExecutionTime(test.execution_time_ms) : '—'}
              </span>
            } />
          ))}
        </TestSection>
      )}
    </div>
  );
}

// Summary card component
function SummaryCard({ label, value, icon, color, highlight }: {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: string;
  highlight?: boolean;
}) {
  const borderColor = highlight
    ? color === 'red' ? 'border-red-500/50' :
      color === 'amber' ? 'border-amber-500/50' :
      color === 'yellow' ? 'border-yellow-500/50' :
      'border-gray-700/50'
    : 'border-gray-700/50';

  return (
    <div className={`bg-gray-800/50 rounded-lg p-4 border ${borderColor}`}>
      <div className="flex items-center justify-between mb-2">
        {icon}
        <span className="text-2xl font-bold text-gray-100">{value}</span>
      </div>
      <p className="text-xs text-gray-400">{label}</p>
    </div>
  );
}

// Collapsible test section
function TestSection({ title, icon, count, color, expanded, onToggle, children }: {
  title: string;
  icon: React.ReactNode;
  count: number;
  color: string;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  const borderColor = color === 'red' ? 'border-red-500/30' :
    color === 'amber' ? 'border-amber-500/30' :
    'border-yellow-500/30';

  return (
    <div className={`bg-gray-800/50 rounded-lg border ${borderColor} overflow-hidden`}>
      <button
        onClick={onToggle}
        className="w-full p-4 flex items-center gap-3 hover:bg-gray-800/80 transition-colors text-left"
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
        )}
        {icon}
        <span className="text-sm font-medium text-gray-200">{title}</span>
        <span className="text-xs text-gray-500">({count})</span>
      </button>
      {expanded && (
        <div className="border-t border-gray-700/50 divide-y divide-gray-700/30">
          {children}
        </div>
      )}
    </div>
  );
}

// Task test row
function TaskTestRow({ test, metric }: { test: TestWithContext; metric: React.ReactNode }) {
  return (
    <div className="px-4 py-3 flex items-start gap-3">
      <div className="flex-shrink-0 mt-0.5">
        {test.passes === true ? (
          <CheckCircle className="w-4 h-4 text-green-400" />
        ) : test.passes === false ? (
          <XCircle className="w-4 h-4 text-red-400" />
        ) : (
          <AlertTriangle className="w-4 h-4 text-gray-500" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-200 truncate">{test.description}</p>
        <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
          {test.epic_name && <span>{test.epic_name}</span>}
          {test.epic_name && test.task_name && <span>{'>'}</span>}
          {test.task_name && <span className="truncate">{test.task_name}</span>}
        </div>
      </div>
      <div className="flex-shrink-0">
        {metric}
      </div>
    </div>
  );
}

// Epic test row
function EpicTestRow({ test, metric }: { test: EpicTestWithContext; metric: React.ReactNode }) {
  return (
    <div className="px-4 py-3 flex items-start gap-3">
      <div className="flex-shrink-0 mt-0.5">
        {test.passes === true ? (
          <CheckCircle className="w-4 h-4 text-green-400" />
        ) : test.passes === false ? (
          <XCircle className="w-4 h-4 text-red-400" />
        ) : (
          <AlertTriangle className="w-4 h-4 text-gray-500" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm text-gray-200 truncate">{test.name || test.description}</p>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-500/20 text-purple-400 border border-purple-500/30">
            epic
          </span>
        </div>
        {test.epic_name && (
          <p className="text-xs text-gray-500 mt-1">{test.epic_name}</p>
        )}
      </div>
      <div className="flex-shrink-0">
        {metric}
      </div>
    </div>
  );
}
