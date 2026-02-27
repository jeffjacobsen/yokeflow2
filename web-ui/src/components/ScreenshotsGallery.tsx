/**
 * ScreenshotsGallery - Screenshots grouped by Epic → Task in Roadmap-style layout
 *
 * Shows:
 * - Total screenshot count with refresh
 * - Screenshots organized by epic → task hierarchy (matching Roadmap/TestCoverage layout)
 * - Epic-level screenshots shown first in each epic section
 * - Task screenshots shown under numbered task headings
 * - Lightbox modal for full-size viewing
 */

'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { Screenshot, AllTestsResponse } from '@/lib/types';
import { Download, X, Image as ImageIcon, Camera } from 'lucide-react';

interface ScreenshotsGalleryProps {
  projectId: string;
}

// Organized epic with its screenshots
interface EpicScreenshots {
  epic: { id: number; name: string; description?: string };
  epicScreenshots: Screenshot[]; // epic-level screenshots
  tasks: {
    task: { id: number; name: string };
    screenshots: Screenshot[];
  }[];
}

export function ScreenshotsGallery({ projectId }: ScreenshotsGalleryProps) {
  const [screenshots, setScreenshots] = useState<Screenshot[]>([]);
  const [hierarchy, setHierarchy] = useState<AllTestsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState<Screenshot | null>(null);

  useEffect(() => {
    loadData();
  }, [projectId]);

  async function loadData() {
    try {
      setLoading(true);

      const [screenshotData, hierarchyData] = await Promise.all([
        api.listScreenshots(projectId),
        api.getAllTests(projectId).catch(() => null),
      ]);

      // Convert relative URLs to absolute URLs
      const screenshotsWithFullUrls = screenshotData.map(s => ({
        ...s,
        url: api.getScreenshotUrl(projectId, s.filename),
      }));

      setScreenshots(screenshotsWithFullUrls);
      setHierarchy(hierarchyData);
    } catch (error) {
      console.error('Failed to load screenshots:', error);
    } finally {
      setLoading(false);
    }
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function parseScreenshotDescription(filename: string): string | null {
    const match = filename.match(/^(?:task|epic)_\d+_(.+)\.png$/);
    if (!match) return null;
    return match[1]
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  function downloadScreenshot(screenshot: Screenshot) {
    const link = document.createElement('a');
    link.href = screenshot.url;
    link.download = screenshot.filename;
    link.click();
  }

  // Build the epic → task → screenshots hierarchy
  function buildHierarchy(): { epics: EpicScreenshots[]; other: Screenshot[] } {
    if (!hierarchy) {
      // No hierarchy data — put everything in "other"
      return { epics: [], other: screenshots };
    }

    // Build lookup: task_id → epic_id
    const taskToEpic = new Map<number, number>();
    for (const epic of hierarchy.epics) {
      for (const task of epic.tasks) {
        taskToEpic.set(task.id, epic.id);
      }
    }

    // Group screenshots by epic and task
    const epicScreenshotMap = new Map<number, Screenshot[]>();
    const taskScreenshotMap = new Map<number, Screenshot[]>();
    const other: Screenshot[] = [];

    for (const s of screenshots) {
      if (s.task_id) {
        const epicId = taskToEpic.get(s.task_id);
        if (epicId !== undefined) {
          if (!taskScreenshotMap.has(s.task_id)) taskScreenshotMap.set(s.task_id, []);
          taskScreenshotMap.get(s.task_id)!.push(s);
        } else {
          other.push(s);
        }
      } else if (s.epic_id) {
        if (!epicScreenshotMap.has(s.epic_id)) epicScreenshotMap.set(s.epic_id, []);
        epicScreenshotMap.get(s.epic_id)!.push(s);
      } else {
        other.push(s);
      }
    }

    // Build ordered epic sections, skipping epics with no screenshots at all
    const epics: EpicScreenshots[] = [];
    for (const epic of hierarchy.epics) {
      const epicShots = epicScreenshotMap.get(epic.id) || [];
      const tasks: EpicScreenshots['tasks'] = [];

      for (const task of epic.tasks) {
        const taskShots = taskScreenshotMap.get(task.id) || [];
        if (taskShots.length > 0) {
          tasks.push({
            task: { id: task.id, name: task.name },
            screenshots: taskShots,
          });
        }
      }

      if (epicShots.length > 0 || tasks.length > 0) {
        epics.push({
          epic: { id: epic.id, name: epic.name, description: epic.description },
          epicScreenshots: epicShots,
          tasks,
        });
      }
    }

    return { epics, other };
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3"></div>
          <p className="text-gray-400 text-sm">Loading screenshots...</p>
        </div>
      </div>
    );
  }

  if (screenshots.length === 0) {
    return (
      <div className="text-center py-12">
        <ImageIcon className="h-16 w-16 mx-auto mb-4 text-gray-600 opacity-50" />
        <p className="text-gray-400 text-lg font-medium">No screenshots yet</p>
        <p className="text-sm text-gray-500 mt-2">Screenshots will appear here as sessions run</p>
      </div>
    );
  }

  const { epics, other } = buildHierarchy();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-100 flex items-center gap-2">
          <Camera className="w-5 h-5 text-blue-400" />
          Screenshots ({screenshots.length})
        </h3>
        <button
          onClick={loadData}
          className="text-sm text-blue-400 hover:text-blue-300 font-medium"
        >
          Refresh
        </button>
      </div>

      {/* Roadmap-style epic → task → screenshots listing */}
      <div className="space-y-10">
        {epics.map((epicSection, epicIndex) => (
          <ScreenshotEpicSection
            key={epicSection.epic.id}
            epicSection={epicSection}
            epicNumber={epicIndex + 1}
            isLast={epicIndex === epics.length - 1 && other.length === 0}
            parseDescription={parseScreenshotDescription}
            formatSize={formatFileSize}
            onImageClick={setSelectedImage}
            onDownload={downloadScreenshot}
          />
        ))}

        {/* Other screenshots (no epic/task association) */}
        {other.length > 0 && (
          <section>
            <div className="mb-4">
              <h2 className="text-xl font-semibold text-gray-100">Other Screenshots</h2>
              <p className="mt-2 text-gray-400 leading-relaxed">
                Screenshots not associated with a specific epic or task
              </p>
            </div>
            <div className="ml-2 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {other.map((s) => (
                <ScreenshotThumbnail
                  key={s.filename}
                  screenshot={s}
                  description={parseScreenshotDescription(s.filename)}
                  formatSize={formatFileSize}
                  onClick={() => setSelectedImage(s)}
                  onDownload={() => downloadScreenshot(s)}
                />
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Lightbox Modal */}
      {selectedImage && (
        <div
          className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedImage(null)}
        >
          <button
            onClick={() => setSelectedImage(null)}
            className="absolute top-4 right-4 text-white hover:text-gray-300 transition-colors"
            aria-label="Close"
          >
            <X className="h-8 w-8" />
          </button>

          <div className="max-w-6xl max-h-[90vh] flex flex-col items-center gap-4">
            <img
              src={selectedImage.url}
              alt={selectedImage.filename}
              className="max-w-full max-h-[80vh] object-contain"
              onClick={(e) => e.stopPropagation()}
            />
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 flex items-center gap-4">
              <div className="flex-1">
                <p className="font-medium text-sm text-gray-100">{selectedImage.filename}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {formatFileSize(selectedImage.size)} • {new Date(selectedImage.modified_at).toLocaleString()}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  downloadScreenshot(selectedImage);
                }}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                <Download className="h-4 w-4" />
                Download
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// Epic section — mirrors TestCoverageEpicSection layout
function ScreenshotEpicSection({
  epicSection,
  epicNumber,
  isLast,
  parseDescription,
  formatSize,
  onImageClick,
  onDownload,
}: {
  epicSection: EpicScreenshots;
  epicNumber: number;
  isLast?: boolean;
  parseDescription: (filename: string) => string | null;
  formatSize: (bytes: number) => string;
  onImageClick: (s: Screenshot) => void;
  onDownload: (s: Screenshot) => void;
}) {
  const { epic, epicScreenshots, tasks } = epicSection;

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

      {/* Epic-level screenshots */}
      {epicScreenshots.length > 0 && (
        <div className="ml-2 mb-5">
          <p className="text-xs font-medium text-purple-400 uppercase tracking-wider mb-2">
            Epic Screenshots
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {epicScreenshots.map((s) => (
              <ScreenshotThumbnail
                key={s.filename}
                screenshot={s}
                description={parseDescription(s.filename)}
                formatSize={formatSize}
                onClick={() => onImageClick(s)}
                onDownload={() => onDownload(s)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Tasks with their screenshots */}
      {tasks.length > 0 && (
        <div className="ml-2 space-y-5">
          {tasks.map((taskSection, taskIndex) => (
            <div key={taskSection.task.id}>
              {/* Task heading */}
              <div className="flex items-start gap-3 mb-2">
                <span className="text-gray-500 font-mono text-sm mt-0.5 w-10 text-right flex-shrink-0">
                  {epicNumber}.{taskIndex + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-gray-200 font-medium">{taskSection.task.name}</p>
                </div>
              </div>

              {/* Task screenshots */}
              <div className="ml-14 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {taskSection.screenshots.map((s) => (
                  <ScreenshotThumbnail
                    key={s.filename}
                    screenshot={s}
                    description={parseDescription(s.filename)}
                    formatSize={formatSize}
                    onClick={() => onImageClick(s)}
                    onDownload={() => onDownload(s)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Divider */}
      {!isLast && (
        <div className="mt-8 border-b border-gray-800/50"></div>
      )}
    </section>
  );
}


// Individual screenshot thumbnail card
function ScreenshotThumbnail({
  screenshot,
  description,
  formatSize,
  onClick,
  onDownload,
}: {
  screenshot: Screenshot;
  description: string | null;
  formatSize: (bytes: number) => string;
  onClick: () => void;
  onDownload: () => void;
}) {
  return (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700/50 overflow-hidden hover:border-gray-600 transition-colors">
      <div className="cursor-pointer" onClick={onClick}>
        <img
          src={screenshot.url}
          alt={screenshot.filename}
          className="w-full h-32 object-contain bg-gray-900"
          loading="lazy"
        />
      </div>
      <div className="p-2.5 space-y-1">
        <p className="text-xs text-gray-300 font-medium truncate" title={description || screenshot.filename}>
          {description || screenshot.filename}
        </p>
        <div className="flex items-center justify-between text-[10px] text-gray-500">
          <span>{formatSize(screenshot.size)}</span>
          <button
            onClick={(e) => { e.stopPropagation(); onDownload(); }}
            className="flex items-center gap-1 text-blue-400 hover:text-blue-300"
            title="Download"
          >
            <Download className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
