'use client';

import { useState, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import SpecEditor from '@/components/SpecEditor';

type CreationMode = 'upload' | 'generate' | 'import';

interface GenerationProgress {
  stage: 'context' | 'generating' | 'validating' | 'complete';
  message: string;
  percentage: number;
}

export default function CreateProjectPage() {
  const router = useRouter();

  // Mode selection
  const [mode, setMode] = useState<CreationMode>('upload');

  // Common fields
  const [projectName, setProjectName] = useState('');
const [initializerModel, setInitializerModel] = useState('claude-opus-4-6');
  const [codingModel, setCodingModel] = useState('claude-sonnet-4-6');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [nameValidationError, setNameValidationError] = useState<string | null>(null);

  // Upload mode fields
  const [specFiles, setSpecFiles] = useState<File[]>([]);

  // Generate mode fields
  const [description, setDescription] = useState('');
  const [contextFiles, setContextFiles] = useState<File[]>([]);
  const [generatedSpec, setGeneratedSpec] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null);
  const [validationFeedback, setValidationFeedback] = useState<{
    isValid: boolean;
    errors: string[];
    warnings: string[];
    suggestions: string[];
  } | null>(null);

  // Import mode fields
  const [sourceType, setSourceType] = useState<'github' | 'local'>('github');
  const [sourceUrl, setSourceUrl] = useState('');
  const [sourcePath, setSourcePath] = useState('');
  const [sourceBranch, setSourceBranch] = useState('main');
  const [changeSpec, setChangeSpec] = useState('');
  const [isImporting, setIsImporting] = useState(false);

  // Common state
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Handle file operations for upload mode
  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      if (mode === 'upload') {
        setSpecFiles(files);
      } else {
        setContextFiles(files);
      }

      // Auto-fill project name from first file if empty (upload mode only)
      if (!projectName && mode === 'upload') {
        const name = files[0].name
          .replace(/\.(txt|md)$/, '')
          .toLowerCase()
          .replace(/[^a-z0-9_-]+/g, '-')
          .replace(/^-+|-+$/g, '');
        setProjectName(name);
      }
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);

    if (files.length > 0) {
      const allowedExtensions = ['.txt', '.md', '.py', '.ts', '.js', '.tsx', '.jsx', '.json', '.yaml', '.yml', '.sql', '.sh', '.css', '.html'];
      const validFiles = files.filter(f =>
        allowedExtensions.some(ext => f.name.endsWith(ext))
      );

      if (validFiles.length > 0) {
        if (mode === 'upload') {
          setSpecFiles(prevFiles => {
            const newFiles = validFiles.filter(newFile =>
              !prevFiles.some(existingFile => existingFile.name === newFile.name)
            );
            return [...prevFiles, ...newFiles];
          });

          // Auto-fill project name if empty
          if (!projectName) {
            const primaryFile = validFiles.find(f => f.name.endsWith('.md') || f.name.endsWith('.txt')) || validFiles[0];
            const name = primaryFile.name
              .replace(/\.(txt|md|py|ts|js|tsx|jsx|json|yaml|yml|sql|sh|css|html)$/, '')
              .toLowerCase()
              .replace(/[^a-z0-9_-]+/g, '-')
              .replace(/^-+|-+$/g, '');
            setProjectName(name);
          }
        } else {
          setContextFiles(prevFiles => {
            const newFiles = validFiles.filter(newFile =>
              !prevFiles.some(existingFile => existingFile.name === newFile.name)
            );
            return [...prevFiles, ...newFiles];
          });
        }
      }
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
  }

  function removeFile(index: number, isContext: boolean = false) {
    if (isContext) {
      setContextFiles(contextFiles.filter((_, i) => i !== index));
    } else {
      setSpecFiles(specFiles.filter((_, i) => i !== index));
    }
  }

  // Generate specification from description
  const generateSpecification = useCallback(async () => {
    if (!description.trim()) {
      setError('Please provide a description of what you want to build');
      return;
    }

    setIsGenerating(true);
    setError(null);
    setGenerationProgress({ stage: 'context', message: 'Preparing request...', percentage: 10 });

    try {
      // Prepare context files data
      const contextData: { [key: string]: string } = {};
      for (const file of contextFiles) {
        const content = await file.text();
        contextData[file.name] = content;
      }

      setGenerationProgress({ stage: 'generating', message: 'Generating specification...', percentage: 30 });

      // Send POST request to generate specification
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8010'}/api/generate-spec`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          description,
          context_files: contextData,
          project_name: projectName || 'generated-project'
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to generate specification');
      }

      // Read the SSE stream
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      if (reader) {
        let accumulatedSpec = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));

                if (data.event === 'start') {
                  setGenerationProgress({ stage: 'generating', message: data.message, percentage: 40 });
                } else if (data.event === 'progress') {
                  // Accumulate content chunks
                  accumulatedSpec += data.content;
                  setGeneratedSpec(accumulatedSpec);
                  // Update progress
                  setGenerationProgress(prev => prev ? ({
                    ...prev,
                    percentage: Math.min(90, prev.percentage + 2)
                  }) : null);
                } else if (data.event === 'complete') {
                  // The specification has been accumulated through progress events
                  setGenerationProgress({ stage: 'complete', message: 'Specification generated!', percentage: 100 });
                  setIsGenerating(false);
                  // Validate the accumulated spec
                  if (accumulatedSpec) {
                    validateGeneratedSpec(accumulatedSpec);
                  }
                } else if (data.event === 'error') {
                  setError(data.message);
                  setIsGenerating(false);
                }
              } catch (e) {
                console.error('Error parsing SSE data:', e);
              }
            }
          }
        }
      }

    } catch (err: any) {
      console.error('Generation failed:', err);
      setError(err.message || 'Failed to generate specification');
      setIsGenerating(false);
    }
  }, [description, contextFiles, projectName]);

  // Validate generated specification
  const validateGeneratedSpec = useCallback(async (spec: string) => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8010'}/api/validate-spec`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          spec_content: spec,
          project_type: detectProjectType(spec)
        })
      });

      const result = await response.json();
      // Map API response to frontend format
      setValidationFeedback({
        isValid: result.valid || false,
        errors: result.errors || [],
        warnings: result.warnings || [],
        suggestions: result.suggestions || []
      });
      setIsGenerating(false);
    } catch (err) {
      console.error('Validation failed:', err);
      setIsGenerating(false);
    }
  }, []);

  // Helper to detect project type from spec
  const detectProjectType = (spec: string): string => {
    const lowerSpec = spec.toLowerCase();
    if (lowerSpec.includes('react') || lowerSpec.includes('next')) return 'web';
    if (lowerSpec.includes('api') || lowerSpec.includes('fastapi')) return 'api';
    if (lowerSpec.includes('cli') || lowerSpec.includes('command')) return 'cli';
    if (lowerSpec.includes('data') || lowerSpec.includes('pipeline')) return 'data';
    return 'general';
  };

  // Handle form submission
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!projectName.trim()) {
      setError('Project name is required');
      return;
    }

    if (!/^[a-z0-9_-]+$/.test(projectName)) {
      setError('Project name must contain only lowercase letters, numbers, hyphens, and underscores');
      return;
    }

    if (mode === 'upload' && specFiles.length === 0) {
      setError('At least one specification file is required');
      return;
    }

    if (mode === 'generate' && !generatedSpec.trim()) {
      setError('Please generate a specification first');
      return;
    }

    if (mode === 'import') {
      if (sourceType === 'github' && !sourceUrl.trim()) {
        setError('GitHub URL is required');
        return;
      }
      if (sourceType === 'local' && !sourcePath.trim()) {
        setError('Local path is required');
        return;
      }
    }

    setIsCreating(true);

    try {
      let result;

      if (mode === 'import') {
        result = await api.importProject(
          projectName,
          sourceType === 'github' ? sourceUrl : null,
          sourceType === 'local' ? sourcePath : null,
          sourceBranch,
          changeSpec || null,
          initializerModel,
          codingModel
        );
      } else if (mode === 'upload') {
        // Use existing file upload method
        result = await api.createProjectWithFile(
          projectName,
          specFiles.length === 1 ? specFiles[0] : specFiles,
          false,
          initializerModel,
          codingModel
        );
      } else {
        // Create project with generated specification
        const specBlob = new Blob([generatedSpec], { type: 'text/markdown' });
        const specFile = new File([specBlob], 'app_spec.md', { type: 'text/markdown' });

        result = await api.createProjectWithFile(
          projectName,
          specFile,
          false,
          initializerModel,
          codingModel
        );
      }

      router.push(`/projects/${result.id}`);
    } catch (err: any) {
      console.error('Failed to create project:', err);
      const errorMessage = err.response?.data?.detail || err.message;
      if (err.response?.status === 409) {
        setError(errorMessage || 'A project with this name already exists');
      } else {
        setError(errorMessage || 'Failed to create project. Check console for details.');
      }
      setIsCreating(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-2 text-sm">
          <Link href="/" className="text-gray-500 hover:text-gray-300">
            Projects
          </Link>
          <span className="text-gray-600">/</span>
          <span className="text-gray-100">Create</span>
        </div>
        <h1 className="text-4xl font-bold mb-2">Create New Project</h1>
        <p className="text-gray-600 dark:text-gray-400">
          Upload a specification, describe what you want to build, or import an existing codebase
        </p>
      </div>

      {/* Mode Toggle */}
      <div className="mb-8 flex gap-2 p-1 bg-gray-900 rounded-lg">
        <button
          type="button"
          onClick={() => setMode('upload')}
          className={`flex-1 px-4 py-2 rounded-md transition-all ${
            mode === 'upload'
              ? 'bg-blue-600 text-white'
              : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
          }`}
        >
          <div className="flex items-center justify-center gap-2">
            <span>Upload Spec</span>
          </div>
        </button>
        <button
          type="button"
          onClick={() => setMode('generate')}
          className={`flex-1 px-4 py-2 rounded-md transition-all ${
            mode === 'generate'
              ? 'bg-blue-600 text-white'
              : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
          }`}
        >
          <div className="flex items-center justify-center gap-2">
            <span>Generate with AI</span>
          </div>
        </button>
        <button
          type="button"
          onClick={() => setMode('import')}
          className={`flex-1 px-4 py-2 rounded-md transition-all ${
            mode === 'import'
              ? 'bg-purple-600 text-white'
              : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
          }`}
        >
          <div className="flex items-center justify-center gap-2">
            <span>Import Codebase</span>
          </div>
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Project Name */}
        <div>
          <label htmlFor="projectName" className="block text-sm font-medium text-gray-300 mb-2">
            Project Name *
          </label>
          <input
            type="text"
            id="projectName"
            value={projectName}
            onChange={(e) => {
              const value = e.target.value;
              setProjectName(value);
              if (value && !/^[a-z0-9_-]+$/.test(value)) {
                setNameValidationError('Project name must contain only lowercase letters, numbers, hyphens, and underscores');
              } else {
                setNameValidationError(null);
              }
            }}
            placeholder="my-awesome-project"
            className={`w-full px-4 py-3 bg-gray-900 border rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:border-transparent ${
              nameValidationError ? 'border-red-500 focus:ring-red-500' : 'border-gray-800 focus:ring-blue-500'
            }`}
            disabled={isCreating || isGenerating}
          />
          {nameValidationError && (
            <p className="mt-1 text-sm text-red-400">{nameValidationError}</p>
          )}
        </div>

        {/* Upload Mode Content */}
        {mode === 'upload' && (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Specification File(s) *
            </label>
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              className="border-2 border-dashed border-gray-700 rounded-lg p-8 text-center hover:border-gray-600 transition-colors cursor-pointer"
            >
              {specFiles.length > 0 ? (
                <div className="space-y-3">
                  <div className="text-4xl">📄</div>
                  <div>
                    <div className="text-gray-300 font-medium">
                      {specFiles.length} file{specFiles.length > 1 ? 's' : ''} selected
                    </div>
                    <div className="text-sm text-gray-700 dark:text-gray-500">
                      {(specFiles.reduce((sum, f) => sum + f.size, 0) / 1024).toFixed(1)} KB total
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSpecFiles([])}
                    className="text-sm text-blue-400 hover:text-blue-300"
                    disabled={isCreating}
                  >
                    Remove all files
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="text-4xl text-gray-600">📁</div>
                  <div>
                    <label
                      htmlFor="fileInput"
                      className="text-blue-400 hover:text-blue-300 cursor-pointer"
                    >
                      Click to upload
                    </label>
                    <span className="text-gray-700 dark:text-gray-500"> or drag and drop</span>
                  </div>
                  <div className="text-sm text-gray-700 dark:text-gray-500">
                    Specs (.txt, .md) + Code examples (.py, .ts, .js, etc.)
                  </div>
                </div>
              )}
              <input
                type="file"
                id="fileInput"
                onChange={handleFileChange}
                accept=".txt,.md,.py,.ts,.js,.tsx,.jsx,.json,.yaml,.yml,.sql,.sh,.css,.html"
                multiple
                className="hidden"
                disabled={isCreating}
              />
            </div>

            {/* Selected Files List */}
            {specFiles.length > 0 && (
              <div className="mt-3 space-y-2">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">
                  Selected files:
                </div>
                {specFiles.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-gray-900 rounded-lg border border-gray-800"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">📄</span>
                      <div>
                        <div className="text-sm text-gray-300">{file.name}</div>
                        <div className="text-xs text-gray-700 dark:text-gray-500">
                          {(file.size / 1024).toFixed(1)} KB
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      className="text-red-400 hover:text-red-300 text-sm px-3 py-1"
                      disabled={isCreating}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Generate Mode Content */}
        {mode === 'generate' && (
          <>
            {/* Natural Language Description */}
            <div>
              <label htmlFor="description" className="block text-sm font-medium text-gray-300 mb-2">
                Describe what you want to build *
              </label>
              <textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="I want to build a web application that helps users track their daily habits. It should have user authentication, a dashboard showing habit streaks and progress charts, and the ability to set reminders..."
                rows={6}
                className="w-full px-4 py-3 bg-gray-900 border border-gray-800 rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={isCreating || isGenerating}
              />
              <p className="mt-1 text-sm text-gray-700 dark:text-gray-500">
                Be as detailed as possible. Include features, technical requirements, and any specific technologies you want to use.
              </p>
            </div>

            {/* Context Files (Optional) */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Context Files (Optional)
              </label>
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                className="border-2 border-dashed border-gray-700 rounded-lg p-6 text-center hover:border-gray-600 transition-colors cursor-pointer"
              >
                {contextFiles.length > 0 ? (
                  <div className="space-y-3">
                    <div className="text-3xl">📎</div>
                    <div>
                      <div className="text-gray-300 font-medium">
                        {contextFiles.length} context file{contextFiles.length > 1 ? 's' : ''} added
                      </div>
                      <div className="text-sm text-gray-700 dark:text-gray-500">
                        {(contextFiles.reduce((sum, f) => sum + f.size, 0) / 1024).toFixed(1)} KB total
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setContextFiles([])}
                      className="text-sm text-blue-400 hover:text-blue-300"
                      disabled={isCreating || isGenerating}
                    >
                      Remove all
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="text-3xl text-gray-600">📎</div>
                    <div>
                      <label
                        htmlFor="contextInput"
                        className="text-blue-400 hover:text-blue-300 cursor-pointer text-sm"
                      >
                        Add reference files
                      </label>
                    </div>
                    <div className="text-xs text-gray-700 dark:text-gray-500">
                      Code examples, schemas, APIs, designs
                    </div>
                  </div>
                )}
                <input
                  type="file"
                  id="contextInput"
                  onChange={handleFileChange}
                  accept=".txt,.md,.py,.ts,.js,.tsx,.jsx,.json,.yaml,.yml,.sql,.sh,.css,.html"
                  multiple
                  className="hidden"
                  disabled={isCreating || isGenerating}
                />
              </div>

              {/* Context Files List */}
              {contextFiles.length > 0 && (
                <div className="mt-3 space-y-2">
                  {contextFiles.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-2 bg-gray-900 rounded border border-gray-800"
                    >
                      <div className="flex items-center gap-2">
                        <span>📎</span>
                        <span className="text-sm text-gray-400">{file.name}</span>
                        <span className="text-xs text-gray-600">({(file.size / 1024).toFixed(1)} KB)</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeFile(index, true)}
                        className="text-red-400 hover:text-red-300 text-sm px-2"
                        disabled={isCreating || isGenerating}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Generate Button */}
            {!generatedSpec && (
              <div className="flex flex-col items-center gap-2">
                <button
                  type="button"
                  onClick={generateSpecification}
                  disabled={!description.trim() || isGenerating}
                  className="px-6 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 disabled:from-gray-600 disabled:to-gray-700 disabled:cursor-not-allowed text-white rounded-lg transition-all font-medium flex items-center gap-2"
                >
                  {isGenerating ? (
                    <>
                      <span className="animate-spin">⚙️</span>
                      <span>Generating...</span>
                    </>
                  ) : (
                    <>
                      <span>✨</span>
                      <span>Generate Specification</span>
                    </>
                  )}
                </button>
                {isGenerating && (
                  <p className="text-sm text-gray-400 animate-pulse">
                    This may take a few minutes
                  </p>
                )}
              </div>
            )}

            {/* Generation Progress */}
            {generationProgress && (
              <div className="p-4 bg-gray-900 border border-gray-800 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-400">{generationProgress.message}</span>
                  <span className="text-sm text-blue-400">{generationProgress.percentage}%</span>
                </div>
                <div className="w-full bg-gray-800 rounded-full h-2">
                  <div
                    className="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all"
                    style={{ width: `${generationProgress.percentage}%` }}
                  />
                </div>
              </div>
            )}

            {/* Generated Specification Editor */}
            {generatedSpec && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-gray-200">Generated Specification</h3>
                  <button
                    type="button"
                    onClick={() => {
                      setGeneratedSpec('');
                      setValidationFeedback(null);
                      setGenerationProgress(null);
                    }}
                    className="text-sm text-gray-400 hover:text-gray-300"
                  >
                    Regenerate
                  </button>
                </div>

                <SpecEditor
                  value={generatedSpec}
                  onChange={setGeneratedSpec}
                  onValidate={validateGeneratedSpec}
                />

                {/* Validation Feedback */}
                {validationFeedback && (
                  <div className="space-y-3">
                    {/* Validation Status */}
                    <div className={`p-3 rounded-lg border ${
                      validationFeedback.isValid
                        ? 'bg-green-950/30 border-green-900/50'
                        : 'bg-yellow-950/30 border-yellow-900/50'
                    }`}>
                      <div className="flex items-center gap-2">
                        <span>{validationFeedback.isValid ? '✅' : '⚠️'}</span>
                        <span className={validationFeedback.isValid ? 'text-green-400' : 'text-yellow-400'}>
                          {validationFeedback.isValid ? 'Specification is valid' : 'Specification needs improvement'}
                        </span>
                      </div>
                    </div>

                    {/* Errors */}
                    {validationFeedback?.errors?.length > 0 && (
                      <div className="p-3 bg-red-950/30 border border-red-900/50 rounded-lg">
                        <div className="text-red-400 font-medium mb-1">Errors:</div>
                        <ul className="list-disc list-inside text-sm text-red-300 space-y-1">
                          {validationFeedback.errors.map((error, i) => (
                            <li key={i}>{error}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Warnings */}
                    {validationFeedback?.warnings?.length > 0 && (
                      <div className="p-3 bg-yellow-950/30 border border-yellow-900/50 rounded-lg">
                        <div className="text-yellow-400 font-medium mb-1">Warnings:</div>
                        <ul className="list-disc list-inside text-sm text-yellow-300 space-y-1">
                          {validationFeedback.warnings.map((warning, i) => (
                            <li key={i}>{warning}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Suggestions */}
                    {validationFeedback?.suggestions?.length > 0 && (
                      <div className="p-3 bg-blue-950/30 border border-blue-900/50 rounded-lg">
                        <div className="text-blue-400 font-medium mb-1">Suggestions:</div>
                        <ul className="list-disc list-inside text-sm text-blue-300 space-y-1">
                          {validationFeedback.suggestions.map((suggestion, i) => (
                            <li key={i}>{suggestion}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Import Mode Content */}
        {mode === 'import' && (
          <>
            {/* Source Type Toggle */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Import Source *
              </label>
              <div className="flex gap-2 mb-4">
                <button
                  type="button"
                  onClick={() => setSourceType('github')}
                  className={`flex-1 px-4 py-2 rounded-md border transition-all ${
                    sourceType === 'github'
                      ? 'bg-purple-600/20 border-purple-500 text-purple-300'
                      : 'border-gray-700 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  GitHub / Git URL
                </button>
                <button
                  type="button"
                  onClick={() => setSourceType('local')}
                  className={`flex-1 px-4 py-2 rounded-md border transition-all ${
                    sourceType === 'local'
                      ? 'bg-purple-600/20 border-purple-500 text-purple-300'
                      : 'border-gray-700 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  Local Path
                </button>
              </div>

              {sourceType === 'github' ? (
                <div className="space-y-4">
                  <div>
                    <input
                      type="text"
                      value={sourceUrl}
                      onChange={(e) => setSourceUrl(e.target.value)}
                      placeholder="https://github.com/user/repo"
                      className="w-full px-4 py-3 bg-gray-900 border border-gray-800 rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      disabled={isCreating || isImporting}
                    />
                    <p className="mt-1 text-sm text-gray-500">
                      HTTPS or SSH URL. For private repos, set GITHUB_TOKEN environment variable.
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      Branch
                    </label>
                    <input
                      type="text"
                      value={sourceBranch}
                      onChange={(e) => setSourceBranch(e.target.value)}
                      placeholder="main"
                      className="w-full px-4 py-2 bg-gray-900 border border-gray-800 rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      disabled={isCreating || isImporting}
                    />
                  </div>
                </div>
              ) : (
                <div>
                  <input
                    type="text"
                    value={sourcePath}
                    onChange={(e) => setSourcePath(e.target.value)}
                    placeholder="/Users/you/projects/my-app"
                    className="w-full px-4 py-3 bg-gray-900 border border-gray-800 rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                    disabled={isCreating || isImporting}
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    Absolute path to the codebase directory on your machine.
                  </p>
                </div>
              )}
            </div>

            {/* Change Specification */}
            <div>
              <label htmlFor="changeSpec" className="block text-sm font-medium text-gray-300 mb-2">
                Change Specification
              </label>
              <textarea
                id="changeSpec"
                value={changeSpec}
                onChange={(e) => setChangeSpec(e.target.value)}
                placeholder="Describe what you want to change, improve, or add to the existing codebase. For example:&#10;&#10;- Add pagination to the user list API&#10;- Implement dark mode toggle&#10;- Fix the login bug where sessions expire too quickly&#10;- Refactor the database layer to use connection pooling"
                rows={8}
                className="w-full px-4 py-3 bg-gray-900 border border-gray-800 rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                disabled={isCreating || isImporting}
              />
              <p className="mt-1 text-sm text-gray-500">
                Describe the modifications you want to make. The more specific, the better the generated tasks.
              </p>
            </div>
          </>
        )}

        {/* Advanced Options */}
        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-300 transition-colors"
          >
            <span>{showAdvanced ? '▼' : '▶'}</span>
            <span>Advanced Options</span>
          </button>

          {showAdvanced && (
            <div className="mt-4 space-y-4 p-4 bg-gray-900 border border-gray-800 rounded-lg">
              {/* Initializer Model */}
              <div>
                <label htmlFor="initModel" className="block text-sm font-medium text-gray-300 mb-2">
                  Initializer Model
                </label>
                <select
                  id="initModel"
                  value={initializerModel}
                  onChange={(e) => setInitializerModel(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-950 border border-gray-800 rounded-lg text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  disabled={isCreating || isGenerating}
                >
                  <option value="claude-opus-4-6">Claude Opus (better planning)</option>
                  <option value="claude-sonnet-4-6">Claude Sonnet (faster)</option>
                </select>
                <p className="mt-1 text-xs text-gray-700 dark:text-gray-500">
                  Model used for creating the project roadmap
                </p>
              </div>

              {/* Coding Model */}
              <div>
                <label htmlFor="codeModel" className="block text-sm font-medium text-gray-300 mb-2">
                  Coding Model
                </label>
                <select
                  id="codeModel"
                  value={codingModel}
                  onChange={(e) => setCodingModel(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-950 border border-gray-800 rounded-lg text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  disabled={isCreating || isGenerating}
                >
                  <option value="claude-sonnet-4-6">Claude Sonnet (recommended)</option>
                  <option value="claude-opus-4-6">Claude Opus (more capable)</option>
                </select>
                <p className="mt-1 text-xs text-gray-700 dark:text-gray-500">
                  Model used for implementation sessions
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Error Message */}
        {error && (
          <div className="p-4 bg-red-950/30 border border-red-900/50 rounded-lg">
            <div className="text-red-400 text-sm">{error}</div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between pt-4">
          <Link
            href="/"
            className="px-6 py-3 text-gray-400 hover:text-gray-300 transition-colors"
          >
            Cancel
          </Link>
          <button
            type="submit"
            disabled={
              isCreating ||
              isGenerating ||
              isImporting ||
              !projectName ||
              !!nameValidationError ||
              (mode === 'upload' && specFiles.length === 0) ||
              (mode === 'generate' && !generatedSpec.trim()) ||
              (mode === 'import' && sourceType === 'github' && !sourceUrl.trim()) ||
              (mode === 'import' && sourceType === 'local' && !sourcePath.trim())
            }
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
          >
            {isCreating
              ? (mode === 'import' ? 'Importing...' : 'Creating...')
              : (mode === 'import' ? 'Import & Create Project' : 'Create Project')
            }
          </button>
        </div>
      </form>

      {/* Info Note */}
      <div className="mt-8 bg-blue-950/20 border border-blue-900/30 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <div className="text-blue-500 text-xl">💡</div>
          <div>
            <div className="font-semibold text-blue-400 mb-1">
              {mode === 'import' ? 'About Brownfield Import' : mode === 'upload' ? 'What happens next?' : 'About AI Generation'}
            </div>
            <div className="text-sm text-gray-400 space-y-1">
              {mode === 'import' ? (
                <>
                  <p>1. Your codebase is copied/cloned into the project directory</p>
                  <p>2. The codebase is automatically analyzed (languages, frameworks, tests)</p>
                  <p>3. A feature branch is created for modifications</p>
                  <p>4. The initializer explores existing code and creates a change roadmap</p>
                  <p>5. Coding sessions modify existing code on the feature branch</p>
                </>
              ) : mode === 'upload' ? (
                <>
                  <p>1. Project directory is created in projects/</p>
                  <p>2. Your spec file is saved as app_spec.txt</p>
                  <p>3. Initialization session starts automatically</p>
                  <p>4. The initializer creates epics, tasks, and tests</p>
                  <p>5. Then coding sessions implement your application</p>
                </>
              ) : (
                <>
                  <p>- AI analyzes your description and context files</p>
                  <p>- Generates a complete specification with technical details</p>
                  <p>- Validates the spec for completeness and feasibility</p>
                  <p>- You can edit the generated spec before creating the project</p>
                  <p>- The better your description, the better the specification</p>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}