import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  createAgentTask,
  listAgentTasks,
  getAgentTask,
  runAgentTask,
  submitTaskApproval,
  cancelAgentTask,
  rollbackAgentTask,
  remediateFinding,
} from '../api/agent';
import type {
  AgentTaskResponse,
  AgentWebSocketEvent,
  CreateAgentTaskRequest,
  DecisionType,
  RemediationRequest,
  TaskApprovalRequest,
} from '../types/agent';

export interface AgentLogEntry {
  id: string;
  timestamp: string;
  type: 'info' | 'tool_call' | 'tool_result' | 'observation' | 'error' | 'approval';
  message: string;
  toolName?: string;
  output?: string | null;
  error?: string | null;
  details?: Record<string, any>;
}

export const useAgentTasks = (limit: number = 50, offset: number = 0) => {
  return useQuery({
    queryKey: ['agentTasks', limit, offset],
    queryFn: () => listAgentTasks(limit, offset),
    refetchInterval: 10000,
  });
};

export const useAgentTask = (taskId: string | null | undefined) => {
  return useQuery({
    queryKey: ['agentTask', taskId],
    queryFn: () => (taskId ? getAgentTask(taskId) : Promise.reject('No task ID')),
    enabled: !!taskId,
  });
};

export const useCreateAgentTask = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateAgentTaskRequest) => createAgentTask(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentTasks'] });
    },
  });
};

export const useRunAgentTask = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, background = false }: { taskId: string; background?: boolean }) =>
      runAgentTask(taskId, background),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['agentTasks'] });
      queryClient.invalidateQueries({ queryKey: ['agentTask', data.task_id] });
    },
  });
};

export const useSubmitTaskApproval = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, data }: { taskId: string; data: TaskApprovalRequest }) =>
      submitTaskApproval(taskId, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['agentTasks'] });
      queryClient.invalidateQueries({ queryKey: ['agentTask', data.task_id] });
    },
  });
};

export const useCancelAgentTask = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => cancelAgentTask(taskId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['agentTasks'] });
      queryClient.invalidateQueries({ queryKey: ['agentTask', data.task_id] });
    },
  });
};

export const useRollbackAgentTask = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => rollbackAgentTask(taskId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['agentTasks'] });
      queryClient.invalidateQueries({ queryKey: ['agentTask', data.task_id] });
    },
  });
};

export const useRemediateFinding = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: RemediationRequest) => remediateFinding(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['findings'] });
      queryClient.invalidateQueries({ queryKey: ['finding'] });
      queryClient.invalidateQueries({ queryKey: ['agentTasks'] });
    },
  });
};

export function useAgentWebSocket(taskId: string | null | undefined) {
  const [isConnected, setIsConnected] = useState(false);
  const [taskState, setTaskState] = useState<AgentTaskResponse | null>(null);
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [pendingApproval, setPendingApproval] = useState<{
    toolName: string;
    arguments: Record<string, any>;
    riskCategory: string;
    stepIndex?: number;
  } | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queryClient = useQueryClient();

  const addLog = useCallback((entry: Omit<AgentLogEntry, 'id'>) => {
    setLogs((prev) => [
      ...prev,
      {
        ...entry,
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      },
    ]);
  }, []);

  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  useEffect(() => {
    if (!taskId) {
      setTaskState(null);
      setIsConnected(false);
      setPendingApproval(null);
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/v1/agent/ws/${taskId}`;

    function connect() {
      try {
        const ws = new WebSocket(wsUrl);
        socketRef.current = ws;

        ws.onopen = () => {
          setIsConnected(true);
          addLog({
            timestamp: new Date().toISOString(),
            type: 'info',
            message: `Connected to Agent Task ${taskId} live stream.`,
          });
          // Request initial state
          ws.send(JSON.stringify({ action: 'get_state' }));
        };

        ws.onmessage = (event) => {
          try {
            const data: AgentWebSocketEvent = JSON.parse(event.data);
            const timestamp = data.timestamp || new Date().toISOString();

            switch (data.event) {
              case 'connected':
                addLog({
                  timestamp,
                  type: 'info',
                  message: data.message || 'Stream active',
                });
                break;

              case 'task_state':
                if (data.state) {
                  setTaskState(data.state);
                  queryClient.setQueryData(['agentTask', taskId], data.state);
                  if (data.state.status === 'WAITING_APPROVAL') {
                    const currentStep = data.state.plan?.steps[data.state.current_step_index];
                    if (currentStep) {
                      setPendingApproval({
                        toolName: currentStep.tool_name,
                        arguments: currentStep.arguments,
                        riskCategory: 'APPROVAL_REQUIRED',
                        stepIndex: data.state.current_step_index,
                      });
                    }
                  } else {
                    setPendingApproval(null);
                  }
                }
                break;

              case 'plan_created':
                addLog({
                  timestamp,
                  type: 'info',
                  message: `Execution plan established (${data.data?.steps?.length || 0} steps).`,
                  details: data.data,
                });
                break;

              case 'step_started':
                addLog({
                  timestamp,
                  type: 'info',
                  message: `Executing Step ${data.data?.step_id}: ${data.data?.tool_name}`,
                  toolName: data.data?.tool_name,
                  details: data.data,
                });
                break;

              case 'step_completed':
                addLog({
                  timestamp,
                  type: data.data?.status === 'COMPLETED' ? 'info' : 'error',
                  message: `Completed Step ${data.data?.step_id} - ${data.data?.status}`,
                  toolName: data.data?.tool_name,
                  output: data.data?.result?.output,
                  error: data.data?.error || data.data?.result?.error,
                });
                break;

              case 'tool_call_start':
                addLog({
                  timestamp,
                  type: 'tool_call',
                  message: `Invoking tool: ${data.data?.tool_name}`,
                  toolName: data.data?.tool_name,
                  details: data.data?.arguments,
                });
                break;

              case 'tool_call_end':
                addLog({
                  timestamp,
                  type: data.data?.success ? 'tool_result' : 'error',
                  message: `Tool ${data.data?.tool_name} finished (${data.data?.duration_ms}ms)`,
                  toolName: data.data?.tool_name,
                  output: data.data?.output,
                  error: data.data?.error,
                });
                break;

              case 'observation':
                addLog({
                  timestamp,
                  type: 'observation',
                  message: data.data?.observation || 'Observation recorded',
                  details: data.data,
                });
                break;

              case 'approval_required':
                setPendingApproval({
                  toolName: data.data?.tool_name || 'unknown',
                  arguments: data.data?.arguments || {},
                  riskCategory: data.data?.risk_category || 'APPROVAL_REQUIRED',
                  stepIndex: data.data?.step_id,
                });
                addLog({
                  timestamp,
                  type: 'approval',
                  message: `Action requires human approval: ${data.data?.tool_name}`,
                  toolName: data.data?.tool_name,
                  details: data.data,
                });
                break;

              case 'execution_cycle_ended':
                addLog({
                  timestamp,
                  type: 'info',
                  message: `Execution cycle ended: ${data.status}`,
                });
                break;

              case 'task_cancelled':
                addLog({
                  timestamp,
                  type: 'info',
                  message: 'Agent task was cancelled.',
                });
                setPendingApproval(null);
                break;

              case 'task_rolled_back':
                addLog({
                  timestamp,
                  type: 'info',
                  message: `Task snapshot restored. Restored files: ${data.restored_files?.join(', ') || 'None'}`,
                });
                break;

              case 'error':
                addLog({
                  timestamp,
                  type: 'error',
                  message: data.message || 'Unknown WebSocket error',
                });
                break;

              default:
                break;
            }
          } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
          }
        };

        ws.onclose = () => {
          setIsConnected(false);
        };

        ws.onerror = (err) => {
          console.error('Agent WebSocket error:', err);
          setIsConnected(false);
        };
      } catch (e) {
        console.error('WebSocket connection initialization failed:', e);
      }
    }

    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [taskId, addLog, queryClient]);

  const sendAction = useCallback((payload: Record<string, any>) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const runTask = useCallback(
    (background: boolean = false) => {
      sendAction({ action: 'run', background });
    },
    [sendAction]
  );

  const approveTool = useCallback(
    (decision: DecisionType, toolName?: string) => {
      sendAction({ action: 'approval', decision, tool_name: toolName });
      setPendingApproval(null);
    },
    [sendAction]
  );

  const cancelTask = useCallback(() => {
    sendAction({ action: 'cancel' });
    setPendingApproval(null);
  }, [sendAction]);

  const rollbackTask = useCallback(() => {
    sendAction({ action: 'rollback' });
  }, [sendAction]);

  const refreshState = useCallback(() => {
    sendAction({ action: 'get_state' });
  }, [sendAction]);

  return {
    isConnected,
    taskState,
    logs,
    pendingApproval,
    runTask,
    approveTool,
    cancelTask,
    rollbackTask,
    refreshState,
    clearLogs,
  };
}
