'use client';

import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { RoadmapEpicSection } from './RoadmapEpicSection';
import { RoadmapExportButton } from './RoadmapExportButton';
import { api } from '@/lib/api';
import type { Project, EpicWithTasks } from '@/lib/types';

interface RoadmapViewProps {
  projectId: string;
}

export function RoadmapView({ projectId }: RoadmapViewProps) {
  const [project, setProject] = useState<Project | null>(null);
  const [epicsWithTasks, setEpicsWithTasks] = useState<EpicWithTasks[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadRoadmap();
  }, [projectId]);

  async function loadRoadmap() {
    try {
      setLoading(true);
      setError(null);

      const [projectData, epicsData] = await Promise.all([
        api.getProject(projectId),
        api.listEpics(projectId),
      ]);
      setProject(projectData);

      // Load tasks for each epic in parallel
      const epicDetails = await Promise.all(
        epicsData.map(epic => api.getEpic(projectId, epic.id))
      );
      setEpicsWithTasks(epicDetails);
    } catch (err) {
      console.error('Failed to load roadmap:', err);
      setError('Failed to load roadmap data');
      toast.error('Failed to load roadmap');
    } finally {
      setLoading(false);
    }
  }

  const totalTasks = epicsWithTasks.reduce((sum, e) => sum + e.tasks.length, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3"></div>
          <p className="text-gray-400 text-sm">Loading roadmap...</p>
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="text-center py-24">
        <p className="text-red-400 mb-2">{error || 'Project not found'}</p>
        <button
          onClick={loadRoadmap}
          className="text-sm text-blue-400 hover:text-blue-300"
        >
          Try again
        </button>
      </div>
    );
  }

  if (epicsWithTasks.length === 0) {
    return (
      <div>
        <h1 className="text-3xl font-bold text-gray-100 mb-2">{project.name}</h1>
        <div className="text-center py-24">
          <p className="text-gray-500 mb-2">No roadmap yet</p>
          <p className="text-sm text-gray-600">Initialize the project to create a roadmap.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-8 no-print">
        <div>
          <h1 className="text-3xl font-bold text-gray-100 mb-2">{project.name}</h1>
          <p className="text-gray-400">
            Project Roadmap &mdash; {epicsWithTasks.length} epic{epicsWithTasks.length !== 1 ? 's' : ''}, {totalTasks} task{totalTasks !== 1 ? 's' : ''}
          </p>
        </div>
        <RoadmapExportButton project={project} epicsWithTasks={epicsWithTasks} />
      </div>

      {/* Print-only header */}
      <div className="hidden print-only mb-8">
        <h1 className="text-3xl font-bold text-black mb-2">{project.name}</h1>
        <p className="text-gray-600">
          Project Roadmap &mdash; {epicsWithTasks.length} epic{epicsWithTasks.length !== 1 ? 's' : ''}, {totalTasks} task{totalTasks !== 1 ? 's' : ''}
        </p>
      </div>

      {/* Table of Contents */}
      {epicsWithTasks.length > 4 && (
        <nav className="mb-10 p-5 bg-gray-900 border border-gray-800 rounded-lg no-print">
          <h2 className="text-xs font-medium text-gray-500 mb-3 uppercase tracking-wider">Contents</h2>
          <ol className="space-y-1.5 list-decimal list-inside text-sm">
            {epicsWithTasks.map((epic, i) => (
              <li key={epic.id} className="text-gray-400">
                <a
                  href={`#epic-${i + 1}`}
                  className="text-blue-400 hover:text-blue-300 transition-colors"
                >
                  {epic.name}
                </a>
                <span className="text-gray-600 ml-2">
                  ({epic.tasks.length} task{epic.tasks.length !== 1 ? 's' : ''})
                </span>
              </li>
            ))}
          </ol>
        </nav>
      )}

      {/* Epic Sections */}
      <div className="space-y-10">
        {epicsWithTasks.map((epic, epicIndex) => (
          <RoadmapEpicSection
            key={epic.id}
            epic={epic}
            epicNumber={epicIndex + 1}
            tasks={epic.tasks}
            isLast={epicIndex === epicsWithTasks.length - 1}
          />
        ))}
      </div>
    </div>
  );
}
