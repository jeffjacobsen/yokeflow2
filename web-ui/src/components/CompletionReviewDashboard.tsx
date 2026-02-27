/**
 * CompletionReviewDashboard - Display project completion review
 *
 * Phase 7: Project Completion Review
 * Created: February 2, 2026
 *
 * Features:
 * - Overall score and recommendation
 * - Requirements coverage breakdown
 * - Section-by-section status (Frontend, Backend, etc.)
 * - Missing critical requirements
 * - Extra features implemented
 * - Executive summary from Claude
 * - Full review text
 */

'use client';

import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  PlusCircle,
  Download,
  RefreshCw,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8010';

interface CompletionReviewDashboardProps {
  projectId: string;
}

interface CompletionReview {
  id: string;
  project_id: string;
  created_at: string;
  spec_file_path: string;
  requirements_total: number;
  requirements_met: number;
  requirements_missing: number;
  requirements_extra: number;
  coverage_percentage: number;
  overall_score: number;
  recommendation: 'complete' | 'needs_work' | 'failed';
  executive_summary: string;
  review_text: string;
  requirements?: Requirement[];
}

interface Requirement {
  requirement_id: string;
  section: string;
  requirement_text: string;
  keywords: string[];
  priority: 'high' | 'medium' | 'low';
  status: 'met' | 'missing' | 'partial' | 'extra';
  matched_epic_ids: number[];
  matched_task_ids: number[];
  match_confidence: number;
  implementation_notes: string;
}

interface SectionSummary {
  section: string;
  total_requirements: number;
  met_count: number;
  missing_count: number;
  partial_count: number;
  avg_confidence: number;
}

export function CompletionReviewDashboard({ projectId }: CompletionReviewDashboardProps) {
  const [review, setReview] = useState<CompletionReview | null>(null);
  const [sectionSummaries, setSectionSummaries] = useState<SectionSummary[]>([]);
  const [requirementsBySection, setRequirementsBySection] = useState<Record<string, Requirement[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const [showFullReview, setShowFullReview] = useState(false);

  useEffect(() => {
    loadReview();
  }, [projectId]);

  async function loadReview() {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.get(`${API_BASE}/api/projects/${projectId}/completion-review`);
      setReview(response.data);

      // Load section summaries if we have a review
      if (response.data && response.data.id) {
        const summaryRes = await axios.get(
          `${API_BASE}/api/completion-reviews/${response.data.id}/section-summary`
        );
        setSectionSummaries(summaryRes.data);

        const reqsRes = await axios.get(
          `${API_BASE}/api/completion-reviews/${response.data.id}/requirements`
        );
        setRequirementsBySection(reqsRes.data);
      }
    } catch (err: any) {
      if (err.response?.status === 404) {
        setError('No completion review found. The review will be generated when the project completes.');
      } else {
        console.error('Failed to load completion review:', err);
        setError(err.message || 'Failed to load completion review');
      }
    } finally {
      setLoading(false);
    }
  }

  async function triggerReview() {
    try {
      setTriggering(true);
      setError(null);

      await axios.post(`${API_BASE}/api/projects/${projectId}/completion-review`);

      // Reload the review
      await loadReview();
    } catch (err: any) {
      console.error('Failed to trigger review:', err);
      setError(err.message || 'Failed to trigger review');
    } finally {
      setTriggering(false);
    }
  }

  function downloadReview() {
    if (!review) return;

    const blob = new Blob([review.review_text], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `completion-review-${projectId}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function toggleSection(section: string) {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  }

  function getRecommendationColor(recommendation: string) {
    switch (recommendation) {
      case 'complete':
        return 'text-green-400 bg-green-900/20 border-green-600/50';
      case 'needs_work':
        return 'text-yellow-400 bg-yellow-900/20 border-yellow-600/50';
      case 'failed':
        return 'text-red-400 bg-red-900/20 border-red-600/50';
      default:
        return 'text-gray-400 bg-gray-900/20 border-gray-600/50';
    }
  }

  function getStatusIcon(status: string) {
    switch (status) {
      case 'met':
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'partial':
        return <AlertTriangle className="w-5 h-5 text-yellow-400" />;
      case 'missing':
        return <XCircle className="w-5 h-5 text-red-400" />;
      case 'extra':
        return <PlusCircle className="w-5 h-5 text-blue-400" />;
      default:
        return null;
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3"></div>
          <p className="text-gray-400 text-sm">Loading completion review...</p>
        </div>
      </div>
    );
  }

  if (error && !review) {
    return (
      <div className="space-y-4">
        <div className="bg-yellow-900/20 border border-yellow-600/50 rounded-lg p-4">
          <p className="text-yellow-400">{error}</p>
        </div>
        <button
          onClick={triggerReview}
          disabled={triggering}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
        >
          {triggering ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Generating Review...</span>
            </>
          ) : (
            <>
              <RefreshCw className="w-4 h-4" />
              <span>Generate Completion Review</span>
            </>
          )}
        </button>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="text-center py-12 text-gray-400">
        No completion review available.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Score and Recommendation */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Project Completion Review</h2>
        <div className="flex items-center gap-3">
          <button
            onClick={triggerReview}
            disabled={triggering}
            className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${triggering ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={downloadReview}
            className="flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm"
          >
            <Download className="w-4 h-4" />
            <span>Download Report</span>
          </button>
        </div>
      </div>

      {/* Overall Score Card */}
      <div className={`border rounded-lg p-6 ${getRecommendationColor(review.recommendation)}`}>
        <div className="grid grid-cols-3 gap-6 mb-4">
          <div className="text-center">
            <div className="text-4xl font-bold mb-1">{review.overall_score}/100</div>
            <div className="text-sm opacity-80">Overall Score</div>
          </div>
          <div className="text-center">
            <div className="text-4xl font-bold mb-1">{parseFloat(String(review.coverage_percentage)).toFixed(1)}%</div>
            <div className="text-sm opacity-80">Coverage</div>
          </div>
          <div className="text-center">
            <div className="text-4xl font-bold mb-1 uppercase">{review.recommendation.replace('_', ' ')}</div>
            <div className="text-sm opacity-80">Recommendation</div>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4 pt-4 border-t border-current/30">
          <div className="text-center">
            <div className="text-2xl font-bold">{review.requirements_total}</div>
            <div className="text-sm opacity-80">Total</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-400">{review.requirements_met}</div>
            <div className="text-sm opacity-80">Met</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-yellow-400">
              {review.requirements_total - review.requirements_met - review.requirements_missing}
            </div>
            <div className="text-sm opacity-80">Partial</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-400">{review.requirements_missing}</div>
            <div className="text-sm opacity-80">Missing</div>
          </div>
        </div>
      </div>

      {/* Executive Summary */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-3 text-white">Executive Summary</h3>
        <p className="text-gray-300 whitespace-pre-wrap">{review.executive_summary}</p>
      </div>

      {/* Section Breakdown */}
      {sectionSummaries.length > 0 && (
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4 text-white">Requirements by Section</h3>
          <div className="space-y-3">
            {sectionSummaries.map((section) => {
              const percentage = (section.met_count / section.total_requirements) * 100;
              const isExpanded = expandedSections.has(section.section);
              const requirements = requirementsBySection[section.section] || [];

              return (
                <div key={section.section} className="border border-gray-700 rounded-lg">
                  <button
                    onClick={() => toggleSection(section.section)}
                    className="w-full flex items-center justify-between p-4 hover:bg-gray-700/30"
                  >
                    <div className="flex items-center gap-4">
                      <span className="font-medium text-white">{section.section}</span>
                      <span className="text-sm text-gray-400">
                        {section.met_count}/{section.total_requirements} met
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-32 bg-gray-700 rounded-full h-2">
                        <div
                          className="bg-green-500 h-2 rounded-full"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-white w-12 text-right">
                        {percentage.toFixed(0)}%
                      </span>
                      {isExpanded ? (
                        <ChevronUp className="w-5 h-5 text-gray-400" />
                      ) : (
                        <ChevronDown className="w-5 h-5 text-gray-400" />
                      )}
                    </div>
                  </button>

                  {isExpanded && requirements.length > 0 && (
                    <div className="border-t border-gray-700 p-4 space-y-2">
                      {requirements.map((req) => (
                        <div
                          key={req.requirement_id}
                          className="flex items-start gap-3 p-3 bg-gray-900/50 rounded"
                        >
                          {getStatusIcon(req.status)}
                          <div className="flex-1">
                            <div className="text-sm text-gray-200">{req.requirement_text}</div>

                            {/* Code evidence breakdown */}
                            {req.implementation_notes && req.implementation_notes !== 'No matching code found' && (
                              <div className="mt-2 space-y-1">
                                {req.implementation_notes.split('; ').map((part, i) => {
                                  if (part.startsWith('Files:')) {
                                    return (
                                      <div key={i} className="text-xs text-blue-400">
                                        <span className="font-medium">Files:</span>{' '}
                                        {part.replace('Files: ', '').split(', ').map((f, j) => (
                                          <span key={j} className="inline-block bg-blue-900/30 px-1.5 py-0.5 rounded mr-1 mb-0.5">
                                            {f}
                                          </span>
                                        ))}
                                      </div>
                                    );
                                  }
                                  if (part.startsWith('Artifacts:')) {
                                    return (
                                      <div key={i} className="text-xs text-purple-400">
                                        <span className="font-medium">Code:</span>{' '}
                                        {part.replace('Artifacts: ', '')}
                                      </div>
                                    );
                                  }
                                  if (part.startsWith("Task '")) {
                                    const passed = part.includes('passed');
                                    const failed = part.includes('failed');
                                    return (
                                      <div key={i} className={`text-xs ${failed ? 'text-red-400' : passed ? 'text-green-400' : 'text-gray-400'}`}>
                                        {failed ? <XCircle className="w-3 h-3 inline mr-1" /> : passed ? <CheckCircle className="w-3 h-3 inline mr-1" /> : null}
                                        {part}
                                      </div>
                                    );
                                  }
                                  return <div key={i} className="text-xs text-gray-400">{part}</div>;
                                })}
                              </div>
                            )}
                            {req.implementation_notes === 'No matching code found' && (
                              <div className="text-xs text-red-400 mt-1">No matching code found</div>
                            )}

                            <div className="flex items-center gap-2 mt-2">
                              <span className={`text-xs px-2 py-0.5 rounded ${
                                req.priority === 'high' ? 'bg-red-900/40 text-red-300' :
                                req.priority === 'medium' ? 'bg-yellow-900/40 text-yellow-300' :
                                'bg-gray-700 text-gray-300'
                              }`}>
                                {req.priority}
                              </span>
                              <div className="flex items-center gap-1.5">
                                <div className="w-16 bg-gray-700 rounded-full h-1.5">
                                  <div
                                    className={`h-1.5 rounded-full ${
                                      req.match_confidence >= 0.5 ? 'bg-green-500' :
                                      req.match_confidence >= 0.25 ? 'bg-yellow-500' :
                                      'bg-red-500'
                                    }`}
                                    style={{ width: `${req.match_confidence * 100}%` }}
                                  />
                                </div>
                                <span className="text-xs text-gray-500">
                                  {(req.match_confidence * 100).toFixed(0)}%
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Full Review Text */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-6">
        <button
          onClick={() => setShowFullReview(!showFullReview)}
          className="flex items-center justify-between w-full mb-3"
        >
          <h3 className="text-lg font-semibold text-white">Full Review Report</h3>
          {showFullReview ? (
            <ChevronUp className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          )}
        </button>
        {showFullReview && (
          <div className="prose prose-invert max-w-none">
            <pre className="whitespace-pre-wrap text-sm text-gray-300 bg-gray-900/50 p-4 rounded">
              {review.review_text}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
