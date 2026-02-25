'use client';

import React from 'react';
import type { EpicWithTasks, TaskWithTestCount } from '@/lib/types';

interface RoadmapEpicSectionProps {
  epic: EpicWithTasks;
  epicNumber: number;
  tasks: TaskWithTestCount[];
  isLast?: boolean;
}

export function RoadmapEpicSection({ epic, epicNumber, tasks, isLast }: RoadmapEpicSectionProps) {
  return (
    <section id={`epic-${epicNumber}`} className="scroll-mt-20">
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

      {/* Task list */}
      {tasks.length > 0 ? (
        <div className="ml-2 space-y-3">
          {tasks.map((task, taskIndex) => (
            <div key={task.id} className="flex items-start gap-3">
              <span className="text-gray-500 font-mono text-sm mt-0.5 w-10 text-right flex-shrink-0">
                {epicNumber}.{taskIndex + 1}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-gray-200 font-medium">{task.name}</p>
                {task.description && (
                  <p className="mt-1 text-sm text-gray-500 leading-relaxed">{task.description}</p>
                )}
              </div>
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
