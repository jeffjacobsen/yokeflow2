/**
 * QualityDashboard - Display project-wide quality metrics and trends
 *
 * Features:
 * - Overall quality summary
 * - Quality trend chart over sessions
 * - Browser verification compliance
 * - Recent quality issues
 * - Deep review recommendations
 */

'use client';

import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { api } from '@/lib/api';
import { TestCoverageReport } from './TestCoverageReport';
import { TestHealthDashboard } from './TestHealthDashboard';
import { CompletionReviewDashboard } from './CompletionReviewDashboard';
import { ScreenshotsGallery } from './ScreenshotsGallery';
import { Download, AlertTriangle } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8010';

interface QualityDashboardProps {
  projectId: string;
}

interface DeepReview {
  id: string;  // Review ID
  session_id: string;
  session_number: number;
  review_version: string;
  created_at: string;
  overall_rating: number;
  review_text: string;
  review_summary: {
    rating: number;
    one_line: string;
    summary: string;
  };
  prompt_improvements: string[];
  model: string;
}

export function QualityDashboard({ projectId }: QualityDashboardProps) {
  const [deepReviews, setDeepReviews] = useState<DeepReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedSession, setExpandedSession] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'test-coverage' | 'test-health' | 'session-reviews' | 'completion-review' | 'screenshots'>('test-coverage');

  useEffect(() => {
    loadQualityData();
  }, [projectId]);

  function downloadReview(sessionNumber: number, reviewText: string) {
    const blob = new Blob([reviewText], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `deep-review-session-${sessionNumber}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function loadQualityData() {
    try {
      setLoading(true);
      setError(null);

      // Load deep reviews
      const deepReviewsRes = await axios.get(`${API_BASE}/api/projects/${projectId}/deep-reviews`);
      setDeepReviews(deepReviewsRes.data.reviews || []);
    } catch (err: any) {
      console.error('Failed to load quality data:', err);
      setError(err.message || 'Failed to load quality data');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3"></div>
          <p className="text-gray-400 text-sm">Loading quality data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-600/50 rounded-lg p-4">
        <div className="flex items-center gap-2 text-red-400">
          <AlertTriangle className="w-5 h-5" />
          <span className="font-medium">Failed to load quality data</span>
        </div>
        <p className="text-sm text-gray-400 mt-1">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Sub-tabs */}
      <div className="flex gap-2 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('test-coverage')}
          className={`px-4 py-2 text-sm font-medium transition-colors relative ${
            activeTab === 'test-coverage'
              ? 'text-blue-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Test Coverage
          {activeTab === 'test-coverage' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-400"></div>
          )}
        </button>
        <button
          onClick={() => setActiveTab('test-health')}
          className={`px-4 py-2 text-sm font-medium transition-colors relative ${
            activeTab === 'test-health'
              ? 'text-blue-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Test Health
          {activeTab === 'test-health' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-400"></div>
          )}
        </button>
        <button
          onClick={() => setActiveTab('session-reviews')}
          className={`px-4 py-2 text-sm font-medium transition-colors relative ${
            activeTab === 'session-reviews'
              ? 'text-blue-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Session Reviews
          {deepReviews.length > 0 && (
            <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-blue-500/20 text-blue-300 rounded">
              {deepReviews.length}
            </span>
          )}
          {activeTab === 'session-reviews' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-400"></div>
          )}
        </button>
        <button
          onClick={() => setActiveTab('completion-review')}
          className={`px-4 py-2 text-sm font-medium transition-colors relative ${
            activeTab === 'completion-review'
              ? 'text-blue-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Completion Review
          {activeTab === 'completion-review' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-400"></div>
          )}
        </button>
        <button
          onClick={() => setActiveTab('screenshots')}
          className={`px-4 py-2 text-sm font-medium transition-colors relative ${
            activeTab === 'screenshots'
              ? 'text-blue-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Screenshots
          {activeTab === 'screenshots' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-400"></div>
          )}
        </button>
      </div>

      {/* Test Coverage Tab */}
      {activeTab === 'test-coverage' && (
        <div className="animate-fadeIn">
          <TestCoverageReport projectId={projectId} />
        </div>
      )}

      {/* Test Health Tab */}
      {activeTab === 'test-health' && (
        <div className="animate-fadeIn">
          <TestHealthDashboard projectId={projectId} />
        </div>
      )}

      {/* Deep Reviews Tab */}
      {activeTab === 'session-reviews' && (
        <div className="animate-fadeIn space-y-6">
          {deepReviews.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-gray-500 text-4xl mb-3">🔍</div>
              <p className="text-gray-600 dark:text-gray-400">No session reviews available yet</p>
              <p className="text-sm text-gray-500 mt-2">
                Session reviews are AI-powered analyses of coding sessions
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {deepReviews.map((review) => {
                const isExpanded = expandedSession === review.id;
                return (
                  <div key={review.id} className="border border-gray-700 rounded-lg bg-gray-800">
                    <div className="flex items-center justify-between p-4">
                      <button
                        onClick={() => setExpandedSession(isExpanded ? null : review.id)}
                        className="flex-1 flex items-center justify-between hover:bg-gray-700/30 transition-colors text-left pr-3 -ml-4 -my-4 pl-4 py-4 rounded-l-lg"
                      >
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-medium text-gray-300">
                            Session {review.session_number}
                          </span>
                          <span className={`px-2 py-0.5 text-xs rounded ${
                            review.overall_rating >= 9
                              ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                              : review.overall_rating >= 7
                              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                              : review.overall_rating >= 5
                              ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
                              : 'bg-red-500/20 text-red-400 border border-red-500/30'
                          }`}>
                            {review.overall_rating}/10
                          </span>
                          {review.review_summary?.one_line && (
                            <span className="text-xs text-gray-400 max-w-md truncate">
                              {review.review_summary.one_line}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-700 dark:text-gray-500">
                            {isExpanded ? 'Collapse' : 'Expand'}
                          </span>
                          <svg
                            className={`w-5 h-5 text-gray-400 transition-transform ${
                              isExpanded ? 'transform rotate-180' : ''
                            }`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 9l-7 7-7-7"
                            />
                          </svg>
                        </div>
                      </button>
                      <button
                        onClick={() => downloadReview(review.session_number, review.review_text)}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs text-blue-400 hover:text-blue-300 hover:bg-blue-500/10 rounded transition-colors"
                        title="Download review as markdown"
                      >
                        <Download className="w-4 h-4" />
                        <span>Download</span>
                      </button>
                    </div>
                    {isExpanded && (
                      <div className="border-t border-gray-700 p-4 bg-gray-900/30">
                        {/* Review Summary */}
                        {review.review_summary && (
                          <div className="mb-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded">
                            <p className="text-sm text-gray-300">{review.review_summary.summary}</p>
                          </div>
                        )}

                        {/* Prompt Improvements Badge */}
                        {review.prompt_improvements && review.prompt_improvements.length > 0 && (
                          <div className="mb-4 flex items-center gap-2">
                            <span className="text-xs font-medium text-yellow-400">
                              ⚡ {review.prompt_improvements.length} Prompt Improvement{review.prompt_improvements.length > 1 ? 's' : ''}
                            </span>
                          </div>
                        )}

                        {/* Full Review Text */}
                        <div className="prose prose-invert prose-sm max-w-none">
                          <div
                            className="text-sm text-gray-300 whitespace-pre-wrap"
                            style={{
                              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                              lineHeight: '1.6'
                            }}
                          >
                            {review.review_text}
                          </div>
                        </div>

                        {/* Metadata Footer */}
                        <div className="mt-4 pt-4 border-t border-gray-700 flex items-center justify-between text-xs text-gray-700 dark:text-gray-500">
                          <span>Model: {review.model}</span>
                          <span>Version: {review.review_version}</span>
                          <span>{new Date(review.created_at).toLocaleString()}</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Completion Review Tab */}
      {activeTab === 'completion-review' && (
        <div className="animate-fadeIn">
          <CompletionReviewDashboard projectId={projectId} />
        </div>
      )}

      {/* Screenshots Tab */}
      {activeTab === 'screenshots' && (
        <div className="animate-fadeIn">
          <ScreenshotsGallery projectId={projectId} />
        </div>
      )}
    </div>
  );
}
