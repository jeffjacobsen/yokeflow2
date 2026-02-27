"use client";

import { useState, useEffect } from "react";
import { format } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import {
  AlertCircle,
  Pause,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Bot,
  History,
  Send
} from "lucide-react";

interface Intervention {
  id: string;
  session_id: string;
  project_id: string;
  project_name: string;
  pause_reason: string;
  pause_type: string;
  paused_at: string;
  resolved: boolean;
  resolved_at?: string;
  resolved_by?: string;
  resolution_notes?: string;
  blocker_info: Record<string, any>;
  retry_stats: Record<string, any>;
  current_task_id?: string;
  current_task_description?: string;
  can_auto_resume: boolean;
}

interface InterventionDashboardProps {
  projectId?: string;
}

export default function InterventionDashboard({ projectId }: InterventionDashboardProps) {
  const [activeInterventions, setActiveInterventions] = useState<Intervention[]>([]);
  const [historyInterventions, setHistoryInterventions] = useState<Intervention[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [resumeDialogOpen, setResumeDialogOpen] = useState(false);
  const [selectedIntervention, setSelectedIntervention] = useState<Intervention | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [resuming, setResuming] = useState(false);

  useEffect(() => {
    fetchInterventions();
    // Refresh every 30 seconds
    const interval = setInterval(fetchInterventions, 30000);
    return () => clearInterval(interval);
  }, [projectId]);

  const fetchInterventions = async () => {
    try {
      setRefreshing(true);

      // Fetch active interventions
      const activeData = await api.getActiveInterventions(projectId);
      setActiveInterventions(activeData);

      // Fetch history
      const historyData = await api.getInterventionHistory(projectId, 20);
      setHistoryInterventions(historyData);

    } catch (error) {
      console.error("Failed to fetch interventions:", error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleResume = (intervention: Intervention) => {
    setSelectedIntervention(intervention);
    setResolutionNotes("");
    setResumeDialogOpen(true);
  };

  const confirmResume = async () => {
    if (!selectedIntervention) return;

    try {
      setResuming(true);
      await api.resumeIntervention(
        selectedIntervention.id,
        "user",
        resolutionNotes || undefined
      );

      setResumeDialogOpen(false);
      setSelectedIntervention(null);

      // Refresh the list
      await fetchInterventions();
    } catch (error) {
      console.error("Failed to resume session:", error);
      alert("Failed to resume session. Please check the issue has been resolved and try again.");
    } finally {
      setResuming(false);
    }
  };

  const getPauseTypeIcon = (type: string) => {
    switch (type) {
      case "retry_limit":
        return <RefreshCw className="h-4 w-4" />;
      case "critical_error":
        return <XCircle className="h-4 w-4" />;
      case "timeout":
        return <Clock className="h-4 w-4" />;
      case "manual":
        return <Pause className="h-4 w-4" />;
      default:
        return <AlertCircle className="h-4 w-4" />;
    }
  };

  const getPauseTypeBadge = (type: string) => {
    const variants: Record<string, "destructive" | "secondary" | "outline" | "default"> = {
      retry_limit: "destructive",
      critical_error: "destructive",
      timeout: "secondary",
      manual: "outline",
    };

    return (
      <Badge variant={variants[type] || "default"} className="gap-1">
        {getPauseTypeIcon(type)}
        {type.replace("_", " ").toUpperCase()}
      </Badge>
    );
  };

  const getTimeSincePause = (pausedAt: string) => {
    const pauseTime = new Date(pausedAt);
    const now = new Date();
    const diffMs = now.getTime() - pauseTime.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 60) {
      return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
    }

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) {
      return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    }

    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Intervention Management</h2>
          <p className="text-muted-foreground">
            Monitor and resolve session blockers requiring human intervention
          </p>
        </div>
        <Button
          onClick={fetchInterventions}
          disabled={refreshing}
          variant="outline"
          size="sm"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Active Interventions Alert */}
      {activeInterventions.length > 0 && (
        <Alert className="border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950">
          <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
          <AlertDescription className="text-red-800 dark:text-red-200">
            <strong>{activeInterventions.length} active intervention{activeInterventions.length > 1 ? 's' : ''}</strong> requiring attention
          </AlertDescription>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs defaultValue="active" className="space-y-4">
        <TabsList>
          <TabsTrigger value="active" className="gap-2">
            <AlertCircle className="h-4 w-4" />
            Active ({activeInterventions.length})
          </TabsTrigger>
          <TabsTrigger value="history" className="gap-2">
            <History className="h-4 w-4" />
            History ({historyInterventions.length})
          </TabsTrigger>
        </TabsList>

        {/* Active Interventions Tab */}
        <TabsContent value="active" className="space-y-4">
          {activeInterventions.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <CheckCircle2 className="h-12 w-12 text-green-500 mb-4" />
                <p className="text-lg font-semibold">No Active Interventions</p>
                <p className="text-muted-foreground">All sessions are running smoothly</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4">
              {activeInterventions.map((intervention) => (
                <Card key={intervention.id} className="border-red-200 dark:border-red-800">
                  <CardHeader>
                    <div className="flex justify-between items-start">
                      <div className="space-y-1">
                        <CardTitle className="flex items-center gap-2">
                          <Bot className="h-5 w-5" />
                          {intervention.project_name}
                        </CardTitle>
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                          {getPauseTypeBadge(intervention.pause_type)}
                          <span>•</span>
                          <span>Paused {getTimeSincePause(intervention.paused_at)}</span>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        {intervention.can_auto_resume && (
                          <Badge variant="secondary">Auto-Resumable</Badge>
                        )}
                        <Button
                          onClick={() => handleResume(intervention)}
                          size="sm"
                          className="gap-2"
                        >
                          <Play className="h-4 w-4" />
                          Resume
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <h4 className="font-semibold mb-1">Reason for Pause</h4>
                      <p className="text-sm text-muted-foreground">
                        {intervention.pause_reason}
                      </p>
                    </div>

                    {intervention.current_task_description && (
                      <div>
                        <h4 className="font-semibold mb-1">Current Task</h4>
                        <p className="text-sm text-muted-foreground">
                          {intervention.current_task_description}
                        </p>
                      </div>
                    )}

                    {Object.keys(intervention.blocker_info).length > 0 && (
                      <div>
                        <h4 className="font-semibold mb-1">Blocker Details</h4>
                        <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
                          {JSON.stringify(intervention.blocker_info, null, 2)}
                        </pre>
                      </div>
                    )}

                    {Object.keys(intervention.retry_stats).length > 0 && (
                      <div>
                        <h4 className="font-semibold mb-1">Retry Statistics</h4>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          {Object.entries(intervention.retry_stats).map(([key, value]) => (
                            <div key={key} className="flex justify-between">
                              <span className="text-muted-foreground">{key}:</span>
                              <span className="font-mono">{String(value)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history">
          {historyInterventions.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <History className="h-12 w-12 text-gray-400 mb-4" />
                <p className="text-lg font-semibold">No Intervention History</p>
                <p className="text-muted-foreground">No resolved interventions yet</p>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Project</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Paused</TableHead>
                    <TableHead>Resolved</TableHead>
                    <TableHead>Resolved By</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {historyInterventions.map((intervention) => (
                    <TableRow key={intervention.id}>
                      <TableCell className="font-medium">
                        {intervention.project_name}
                      </TableCell>
                      <TableCell>{getPauseTypeBadge(intervention.pause_type)}</TableCell>
                      <TableCell className="max-w-xs truncate">
                        {intervention.pause_reason}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {format(new Date(intervention.paused_at), "MMM d, HH:mm")}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {intervention.resolved_at
                          ? format(new Date(intervention.resolved_at), "MMM d, HH:mm")
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {intervention.resolved_by || "Unknown"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Resume Dialog */}
      <Dialog open={resumeDialogOpen} onOpenChange={setResumeDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Resume Session</DialogTitle>
            <DialogDescription>
              Confirm that the issue has been resolved and provide any notes for the agent.
            </DialogDescription>
          </DialogHeader>

          {selectedIntervention && (
            <div className="space-y-4">
              <div className="p-3 bg-muted rounded-lg space-y-2">
                <p className="text-sm font-semibold">Project: {selectedIntervention.project_name}</p>
                <p className="text-sm">Reason: {selectedIntervention.pause_reason}</p>
                {selectedIntervention.current_task_description && (
                  <p className="text-sm">Task: {selectedIntervention.current_task_description}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="resolution-notes">
                  Resolution Notes (Optional)
                </Label>
                <Textarea
                  id="resolution-notes"
                  placeholder="Describe what was done to resolve the issue..."
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  rows={4}
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setResumeDialogOpen(false)}
              disabled={resuming}
            >
              Cancel
            </Button>
            <Button
              onClick={confirmResume}
              disabled={resuming}
              className="gap-2"
            >
              {resuming ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  Resuming...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  Resume Session
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}