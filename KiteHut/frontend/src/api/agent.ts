import client from './client';
import type {
  AgentTaskResponse,
  CreateAgentTaskRequest,
  RemediationRequest,
  RemediationResponse,
  TaskApprovalRequest,
  TaskRollbackResponse,
} from '../types/agent';

export interface ListTasksResponse {
  tasks: AgentTaskResponse[];
  total: number;
}

export async function createAgentTask(
  data: CreateAgentTaskRequest
): Promise<AgentTaskResponse> {
  const response = await client.post<AgentTaskResponse>('/agent/tasks', data);
  return response.data;
}

export async function listAgentTasks(
  limit: number = 50,
  offset: number = 0
): Promise<ListTasksResponse> {
  const response = await client.get<ListTasksResponse>('/agent/tasks', {
    params: { limit, offset },
  });
  return response.data;
}

export async function getAgentTask(taskId: string): Promise<AgentTaskResponse> {
  const response = await client.get<AgentTaskResponse>(`/agent/tasks/${taskId}`);
  return response.data;
}

export async function runAgentTask(
  taskId: string,
  background: boolean = false
): Promise<AgentTaskResponse> {
  const response = await client.post<AgentTaskResponse>(
    `/agent/tasks/${taskId}/run`,
    null,
    {
      params: { background },
    }
  );
  return response.data;
}

export async function submitTaskApproval(
  taskId: string,
  data: TaskApprovalRequest
): Promise<AgentTaskResponse> {
  const response = await client.post<AgentTaskResponse>(
    `/agent/tasks/${taskId}/approval`,
    data
  );
  return response.data;
}

export async function cancelAgentTask(
  taskId: string
): Promise<AgentTaskResponse> {
  const response = await client.post<AgentTaskResponse>(
    `/agent/tasks/${taskId}/cancel`
  );
  return response.data;
}

export async function rollbackAgentTask(
  taskId: string
): Promise<TaskRollbackResponse> {
  const response = await client.post<TaskRollbackResponse>(
    `/agent/tasks/${taskId}/rollback`
  );
  return response.data;
}

export async function remediateFinding(
  data: RemediationRequest
): Promise<RemediationResponse> {
  const response = await client.post<RemediationResponse>(
    '/agent/remediate',
    data
  );
  return response.data;
}
