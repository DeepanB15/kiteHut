/**
 * Agent Core TypeScript Type Definitions
 */

export type TaskStatus =
  | 'PENDING'
  | 'PLANNING'
  | 'RUNNING'
  | 'WAITING_APPROVAL'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export type DecisionType =
  | 'ALLOW_ONCE'
  | 'ALLOW_FOR_TASK'
  | 'ALLOW_FOR_REPO'
  | 'DENY';

export type RiskCategory = 'SAFE' | 'APPROVAL_REQUIRED' | 'DANGEROUS';

export interface ToolResultResponse {
  call_id: string;
  tool_name: string;
  success: boolean;
  output?: string | null;
  error?: string | null;
  duration_ms: number;
  created_at: string;
}

export interface PlanStepResponse {
  step_id: string | number;
  description: string;
  tool_name: string;
  arguments: Record<string, any>;
  expected_output?: string | null;
  status: string;
  result?: ToolResultResponse | null;
  error?: string | null;
}

export interface PlanResponse {
  task_id: string;
  goal: string;
  steps: PlanStepResponse[];
  created_at: string;
  status: string;
}

export interface AgentObservationResponse {
  step_id?: string | number | null;
  observation: string;
  timestamp: string;
}

export interface AgentTaskResponse {
  task_id: string;
  session_id?: string | null;
  repository_path: string;
  user_goal: string;
  status: TaskStatus;
  plan?: PlanResponse | null;
  current_step_index: number;
  tool_history: ToolResultResponse[];
  observations: AgentObservationResponse[];
  context_files: string[];
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentTaskRequest {
  repository_path: string;
  user_goal: string;
  session_id?: string;
  auto_allow_safe?: boolean;
  auto_allow_all?: boolean;
}

export interface TaskApprovalRequest {
  decision: DecisionType;
  tool_name?: string;
}

export interface TaskRollbackResponse {
  task_id: string;
  restored_files: string[];
  success: boolean;
  message: string;
}

export interface RemediationTestResult {
  passed: boolean;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  output?: string;
  error_message?: string;
  duration_ms: number;
}

export interface RemediationRequest {
  repository_path: string;
  finding_id?: string;
  finding_data?: Record<string, any>;
  auto_approve?: boolean;
  run_tests?: boolean;
  test_paths?: string[];
}

export interface RemediationResponse {
  action_id: string;
  finding_id: string;
  success: boolean;
  applied_patch_id?: string | null;
  modified_files: string[];
  test_results?: RemediationTestResult | null;
  message: string;
  error?: string | null;
  rolled_back: boolean;
}

export interface AgentWebSocketEvent {
  event: string;
  task_id?: string;
  data?: any;
  state?: AgentTaskResponse;
  status?: string;
  restored_files?: string[];
  message?: string;
  timestamp?: string;
}
