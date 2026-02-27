"use client";

import dynamic from "next/dynamic";

// Dynamically import to avoid SSR issues
const InterventionDashboard = dynamic(() => import("@/components/InterventionDashboard"), {
  ssr: false,
  loading: () => (
    <div className="flex justify-center items-center h-64">
      <div className="text-muted-foreground">Loading interventions...</div>
    </div>
  ),
});

export default function InterventionsPage() {
  return (
    <div className="container mx-auto p-6">
      <InterventionDashboard />
    </div>
  );
}