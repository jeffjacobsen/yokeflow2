'use client';

import Link from 'next/link';

export default function ContainersPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Docker Containers</h1>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-lg p-8 text-center">
          <div className="text-gray-400 mb-4 text-lg">
            Container management has been removed. Projects now run locally.
          </div>
          <Link
            href="/"
            className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
          >
            Back to Projects
          </Link>
        </div>
      </div>
    </div>
  );
}
