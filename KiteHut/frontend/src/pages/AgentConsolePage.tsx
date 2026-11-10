import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Bot,
  Play,
  Square,
  RotateCcw,
  Plus,
  ShieldAlert,
  Loader2,
  FileCode,
  Terminal,
  Brain,
  ListOrdered,
  AlertTriangle,
  FolderGit2,
} from 'lucide-react';
import {
  useAgentTasks,
  useAgentTask,
  useCreateAgentTask,
  useRunAgentTask,
  useCancelAgentTask,
  useRollbackAgentTask,
  useSubmitTaskApproval,
  useAgentWebSocket,
} from '../hooks/useAgent';
import ApprovalModal from '../components/agent/ApprovalModal';
import PlanTimeline from '../components/agent/PlanTimeline';
import LiveToolLogs from '../components/agent/LiveToolLogs';
import ObservationFeed from '../components/agent/ObservationFeed';
import RollbackConfirmModal from '../components/agent/RollbackConfirmModal';
import type { DecisionType } from '../types/agent';

export default function AgentConsolePage() {
  const { taskId: paramTaskId } = useParams<{ taskId?: string }>();
  const navigate = useNavigate();

  // Queries
  const { data: tasksData } = useAgentTasks();
  const tasks = tasksData?.tasks || [];

  // Selected Task ID (from URL or first available)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(
    paramTaskId || null
  );

  useEffect(() => {
    if (paramTaskId) {
      setSelectedTaskId(paramTaskId);
    } else if (tasks.length > 0 && !selectedTaskId) {
      setSelectedTaskId(tasks[0].task_id);
    }
  }, [paramTaskId, tasks, selectedTaskId]);

  const { data: serverTask, refetch: refetchTask } = useAgentTask(selectedTaskId);

  // WebSocket Live Hook
  const {
    isConnected,
    taskState: wsTaskState,
    logs,
    pendingApproval,
    runTask: wsRunTask,
    approveTool: wsApproveTool,
    cancelTask: wsCancelTask,
    rollbackTask: wsRollbackTask,
    clearLogs,
  } = useAgentWebSocket(selectedTaskId);

  // Active state merged from WS or server query
  const activeTask = wsTaskState || serverTask;

  // Mutations
  const createTaskMutation = useCreateAgentTask();
  const runMutation = useRunAgentTask();
  const cancelMutation = useCancelAgentTask();
  const rollbackMutation = useRollbackAgentTask();
  const approvalMutation = useSubmitTaskApproval();

  // UI Local States
  const [activeTab, setActiveTab] = useState<'logs' | 'observations' | 'context'>('logs');
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);
  const [isRollbackModalOpen, setIsRollbackModalOpen] = useState(false);

  // New Task Form
  const [newGoal, setNewGoal] = useState('');
  const [newRepoPath, setNewRepoPath] = useState('.');
  const [autoAllowSafe, setAutoAllowSafe] = useState(true);

  const handleSelectTask = (id: string) => {
    setSelectedTaskId(id);
    navigate(`/agent/${id}`);
    clearLogs();
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGoal.trim()) return;

    try {
      const created = await createTaskMutation.mutateAsync({
        repository_path: newRepoPath.trim() || '.',
        user_goal: newGoal.trim(),
        auto_allow_safe: autoAllowSafe,
      });
      setIsNewTaskModalOpen(false);
      setNewGoal('');
      setSelectedTaskId(created.task_id);
      navigate(`/agent/${created.task_id}`);
    } catch (err) {
      console.error('Failed to create agent task:', err);
    }
  };

  const handleRunTask = () => {
    if (!selectedTaskId) return;
    if (isConnected) {
      wsRunTask(false);
    } else {
      runMutation.mutate({ taskId: selectedTaskId, background: false });
    }
  };

  const handleCancelTask = () => {
    if (!selectedTaskId) return;
    if (isConnected) {
      wsCancelTask();
    } else {
      cancelMutation.mutate(selectedTaskId);
    }
  };

  const handleDecision = (decision: DecisionType, toolName?: string) => {
    if (!selectedTaskId) return;
    if (isConnected) {
      wsApproveTool(decision, toolName);
    } else {
      approvalMutation.mutate({
        taskId: selectedTaskId,
        data: { decision, tool_name: toolName },
      });
    }
  };

  const handleConfirmRollback = async () => {
    if (!selectedTaskId) return;
    try {
      if (isConnected) {
        wsRollbackTask();
      } else {
        await rollbackMutation.mutateAsync(selectedTaskId);
      }
      setIsRollbackModalOpen(false);
      refetchTask();
    } catch (err) {
      console.error('Rollback failed:', err);
    }
  };

  const getStatusBadge = (status: string = 'PENDING') => {
    switch (status) {
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200">
            <span className="w-2 h-2 rounded-full bg-blue-600 animate-ping" />
            RUNNING
          </span>
        );
      case 'WAITING_APPROVAL':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300 animate-pulse">
            <ShieldAlert className="w-3.5 h-3.5" />
            WAITING APPROVAL
          </span>
        );
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
            COMPLETED
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800 border border-red-200">
            FAILED
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-800 border border-gray-300">
            CANCELLED
          </span>
        );
      case 'PLANNING':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-purple-100 text-purple-800 border border-purple-200">
            PLANNING
          </span>
        );
      case 'PENDING':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-700 border border-gray-200">
            PENDING
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)] gap-4">
      {/* Top Action Bar */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
        {/* Left: Title & Task Selector */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="p-2 bg-blue-50 text-blue-600 rounded-xl">
            <Bot className="w-6 h-6" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-gray-900">Live Agent Console</h1>
              {activeTask && getStatusBadge(activeTask.status)}
            </div>
            <p className="text-xs text-gray-500">
              Autonomous Plan Execution, Permission Approvals & Workspace Rollback
            </p>
          </div>

          {/* Task Dropdown */}
          <div className="ml-2">
            <select
              value={selectedTaskId || ''}
              onChange={(e) => handleSelectTask(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-xs font-mono bg-gray-50 focus:bg-white outline-none focus:ring-2 focus:ring-blue-500"
            >
              {tasks.length === 0 && <option value="">No tasks available</option>}
              {tasks.map((t) => (
                <option key={t.task_id} value={t.task_id}>
                  {t.task_id.slice(0, 8)}... - {t.user_goal.slice(0, 30)}... ({t.status})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Right: Action Buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setIsNewTaskModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
          >
            <Plus className="w-3.5 h-3.5" /> New Task
          </button>

          {activeTask && (
            <>
              {activeTask.status === 'RUNNING' || activeTask.status === 'WAITING_APPROVAL' ? (
                <button
                  type="button"
                  onClick={handleCancelTask}
                  className="flex items-center gap-1.5 px-3 py-2 bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 rounded-lg text-xs font-semibold transition-colors"
                >
                  <Square className="w-3.5 h-3.5" /> Cancel
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleRunTask}
                  disabled={runMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors disabled:opacity-50"
                >
                  {runMutation.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5" />
                  )}
                  Execute Task
                </button>
              )}

              <button
                type="button"
                onClick={() => setIsRollbackModalOpen(true)}
                className="flex items-center gap-1.5 px-3 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-xs font-semibold transition-colors"
                title="Restore pre-task workspace snapshot"
              >
                <RotateCcw className="w-3.5 h-3.5 text-gray-600" /> Rollback Workspace
              </button>
            </>
          )}
        </div>
      </div>

      {/* Main Split Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
        {/* Left Column (5 cols): Goal & Plan Timeline */}
        <div className="lg:col-span-5 flex flex-col gap-4 overflow-y-auto pr-1">
          {/* Goal Card */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-xs">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 block mb-1">
              Task Objective
            </span>
            <p className="text-sm font-medium text-gray-900 leading-relaxed">
              {activeTask?.user_goal || 'No task selected.'}
            </p>
            {activeTask && (
              <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
                <span className="flex items-center gap-1 font-mono">
                  <FolderGit2 className="w-3.5 h-3.5 text-gray-400" />
                  {activeTask.repository_path}
                </span>
                <span className="font-mono text-[11px]">
                  ID: {activeTask.task_id.slice(0, 12)}...
                </span>
              </div>
            )}
          </div>

          {/* Interactive Approval Banner if waiting */}
          {activeTask?.status === 'WAITING_APPROVAL' && (
            <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 shadow-xs animate-pulse flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
                <div>
                  <h4 className="text-xs font-bold text-amber-900">
                    Human Approval Required
                  </h4>
                  <p className="text-[11px] text-amber-700">
                    Agent paused for tool authorization.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  /* Modal is also rendered below */
                }}
                className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold"
              >
                Review Request
              </button>
            </div>
          )}

          {/* Plan Timeline */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-xs flex-1 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <ListOrdered className="w-4 h-4 text-blue-600" />
                <h3 className="text-sm font-bold text-gray-900">Execution Plan</h3>
              </div>
              <span className="text-xs font-semibold text-gray-500">
                {activeTask?.plan?.steps ? `${activeTask.plan.steps.length} Steps` : '0 Steps'}
              </span>
            </div>

            <div className="flex-1 overflow-y-auto">
              <PlanTimeline
                steps={activeTask?.plan?.steps || []}
                currentStepIndex={activeTask?.current_step_index ?? 0}
              />
            </div>
          </div>
        </div>

        {/* Right Column (7 cols): Terminal Logs & Observations Tabs */}
        <div className="lg:col-span-7 flex flex-col bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
          {/* Tab bar */}
          <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setActiveTab('logs')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  activeTab === 'logs'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-gray-600 hover:bg-gray-200'
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                Live Tool Logs ({logs.length})
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('observations')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  activeTab === 'observations'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-gray-600 hover:bg-gray-200'
                }`}
              >
                <Brain className="w-3.5 h-3.5" />
                Agent Observations ({activeTask?.observations?.length || 0})
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('context')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  activeTab === 'context'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-gray-600 hover:bg-gray-200'
                }`}
              >
                <FileCode className="w-3.5 h-3.5" />
                Context Files ({activeTask?.context_files?.length || 0})
              </button>
            </div>
          </div>

          {/* Tab content area */}
          <div className="flex-1 min-h-0 p-4 overflow-y-auto">
            {activeTab === 'logs' && (
              <LiveToolLogs
                logs={logs}
                onClear={clearLogs}
                isConnected={isConnected}
              />
            )}

            {activeTab === 'observations' && (
              <ObservationFeed observations={activeTask?.observations || []} />
            )}

            {activeTab === 'context' && (
              <div className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 block mb-2">
                  Loaded Context Files
                </span>
                {(!activeTask?.context_files || activeTask.context_files.length === 0) ? (
                  <p className="text-xs text-gray-400 italic">No context files recorded.</p>
                ) : (
                  activeTask.context_files.map((file, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded-lg bg-gray-50 border border-gray-200 font-mono text-xs text-gray-800 flex items-center gap-2"
                    >
                      <FileCode className="w-3.5 h-3.5 text-blue-500" />
                      <span>{file}</span>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Interactive Approval Modal */}
      {pendingApproval && (
        <ApprovalModal
          isOpen={!!pendingApproval}
          toolName={pendingApproval.toolName}
          argumentsData={pendingApproval.arguments}
          riskCategory={pendingApproval.riskCategory}
          stepIndex={pendingApproval.stepIndex}
          onDecision={handleDecision}
        />
      )}

      {/* Rollback Confirmation Modal */}
      <RollbackConfirmModal
        isOpen={isRollbackModalOpen}
        taskId={selectedTaskId || ''}
        contextFiles={activeTask?.context_files || []}
        isRollingBack={rollbackMutation.isPending}
        onConfirm={handleConfirmRollback}
        onClose={() => setIsRollbackModalOpen(false)}
      />

      {/* New Task Dialog */}
      {isNewTaskModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-lg w-full overflow-hidden">
            <div className="px-6 py-4 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bot className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold text-gray-900">Create Agent Task</h3>
              </div>
            </div>

            <form onSubmit={handleCreateTask} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase text-gray-600 mb-1">
                  Goal / Prompt
                </label>
                <textarea
                  rows={4}
                  value={newGoal}
                  onChange={(e) => setNewGoal(e.target.value)}
                  placeholder="e.g. Audit auth module for token validation vulnerabilities, write unit tests, and fix findings."
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase text-gray-600 mb-1">
                  Target Repository Path
                </label>
                <input
                  type="text"
                  value={newRepoPath}
                  onChange={(e) => setNewRepoPath(e.target.value)}
                  placeholder="."
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="autoAllow"
                  checked={autoAllowSafe}
                  onChange={(e) => setAutoAllowSafe(e.target.checked)}
                  className="rounded text-blue-600"
                />
                <label htmlFor="autoAllow" className="text-xs text-gray-700">
                  Auto-allow safe read-only operations without approval prompt
                </label>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsNewTaskModalOpen(false)}
                  className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createTaskMutation.isPending || !newGoal.trim()}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50"
                >
                  {createTaskMutation.isPending ? 'Initializing...' : 'Create & Plan'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
