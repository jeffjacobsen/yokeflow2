/**
 * ProjectDetailsPanel - Project configuration panel
 *
 * Contains two sub-tabs:
 * - Project Settings: Model configuration, max iterations
 * - Environment: .env file configuration
 */

'use client';

import React from 'react';
import { toast } from 'sonner';
import { ProjectSettingsForm } from './ProjectSettings';
import { EnvEditor } from './EnvEditor';
import type { Project } from '@/lib/types';

interface ProjectDetailsPanelProps {
  projectId: string;
  project: Project;
  isOpen: boolean;
  activeTab: 'settings' | 'environment';
  onTabChange: (tab: 'settings' | 'environment') => void;
  onProjectUpdated?: () => void;
}

export function ProjectDetailsPanel({
  projectId,
  project,
  isOpen,
  activeTab,
  onTabChange,
  onProjectUpdated,
}: ProjectDetailsPanelProps) {
  if (!isOpen) return null;

  return (
    <div>
      {/* Sub-tabs */}
      <div className="flex gap-2 border-b border-gray-700 mb-6">
        <button
          onClick={() => onTabChange('settings')}
          className={`px-4 py-2 text-sm font-medium transition-colors relative ${
            activeTab === 'settings'
              ? 'text-blue-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Project Settings
          {activeTab === 'settings' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-400"></div>
          )}
        </button>
        <button
          onClick={() => onTabChange('environment')}
          className={`px-4 py-2 text-sm font-medium transition-colors relative ${
            activeTab === 'environment'
              ? 'text-blue-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Environment
          {project.needs_env_config && (
            <span className="ml-2 w-2 h-2 bg-amber-400 rounded-full inline-block animate-pulse"></span>
          )}
          {activeTab === 'environment' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-400"></div>
          )}
        </button>
      </div>

      {/* Content */}
      <div>
        {activeTab === 'settings' && (
          <ProjectSettingsForm
            projectId={projectId}
            onSaved={onProjectUpdated}
          />
        )}

        {activeTab === 'environment' && (
          <EnvEditor
            projectId={projectId}
            onSave={() => {
              onProjectUpdated?.();
              toast.success('Environment configuration saved');
            }}
            onCancel={() => {}}
          />
        )}
      </div>
    </div>
  );
}
