'use client';

import React from 'react';
import { Download, Copy } from 'lucide-react';
import { toast } from 'sonner';
import type { Project, EpicWithTasks } from '@/lib/types';

interface RoadmapExportButtonProps {
  project: Project;
  epicsWithTasks: EpicWithTasks[];
}

function generateRoadmapMarkdown(project: Project, epicsWithTasks: EpicWithTasks[]): string {
  let md = `# ${project.name} -- Project Roadmap\n\n`;

  epicsWithTasks.forEach((epic, epicIndex) => {
    const epicNum = epicIndex + 1;
    md += `## ${epicNum}. ${epic.name}\n\n`;
    if (epic.description) {
      md += `${epic.description}\n\n`;
    }

    if (epic.tasks.length > 0) {
      epic.tasks.forEach((task, taskIndex) => {
        const taskNum = taskIndex + 1;
        md += `### ${epicNum}.${taskNum} ${task.name}\n\n`;
        if (task.description) {
          md += `${task.description}\n\n`;
        }
      });
    }
  });

  return md;
}

export function RoadmapExportButton({ project, epicsWithTasks }: RoadmapExportButtonProps) {
  function downloadMarkdown() {
    const markdown = generateRoadmapMarkdown(project, epicsWithTasks);
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${project.name}-roadmap.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success('Roadmap downloaded');
  }

  async function copyToClipboard() {
    const markdown = generateRoadmapMarkdown(project, epicsWithTasks);
    try {
      await navigator.clipboard.writeText(markdown);
      toast.success('Roadmap copied to clipboard');
    } catch {
      toast.error('Failed to copy to clipboard');
    }
  }

  return (
    <div className="flex items-center gap-2 no-print">
      <button
        onClick={downloadMarkdown}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors flex items-center gap-2"
        title="Download as Markdown"
      >
        <Download className="w-4 h-4" />
        Export
      </button>
      <button
        onClick={copyToClipboard}
        className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm rounded-lg transition-colors flex items-center gap-2"
        title="Copy Markdown to clipboard"
      >
        <Copy className="w-4 h-4" />
      </button>
    </div>
  );
}
