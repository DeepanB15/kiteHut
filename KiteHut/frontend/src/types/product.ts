export type AnalysisMode = 'fast' | 'balanced' | 'deep';

export const ANALYSIS_MODES: AnalysisMode[] = ['fast', 'balanced', 'deep'];
export const AGENT_NAMES = ['architecture', 'security', 'quality', 'testing'] as const;
export type AgentName = (typeof AGENT_NAMES)[number];

export interface AnalysisSettings {
  mode: AnalysisMode;
  enabled_agents: AgentName[] | null;
}

export const FINDING_STATUSES = [
  'OPEN',
  'IN_PROGRESS',
  'RESOLVED',
  'IGNORED',
  'FALSE_POSITIVE',
  'ACCEPTED_RISK',
] as const;
export type FindingStatus = (typeof FINDING_STATUSES)[number];

export interface TrendPoint {
  analysis_run_id: number;
  created_at: string | null;
  health_score: number | null;
  health_level: string | null;
  total_findings: number;
  p0: number;
  p1: number;
  p2: number;
  security: number;
  architecture: number;
  quality: number;
  testing: number;
}

export interface TrendResponse {
  repository_id: number;
  trend: TrendPoint[];
}

export interface QualityGateConfig {
  critical_limit: number | null;
  security_limit: number | null;
  min_health: number | null;
  uses_defaults: boolean;
}

export interface Notification {
  id: number;
  repository_id: number | null;
  kind: string;
  severity: string;
  title: string;
  message: string;
  read: boolean;
  created_at: string;
}

export interface NotificationList {
  notifications: Notification[];
  total: number;
  unread: number;
}

export const NOTIFICATION_ICONS: Record<string, string> = {
  NEW_P0: '🔴',
  SECURITY_RISK: '🔐',
  CRITICAL_RESOLVED: '🟢',
  HEALTH_DROP: '⚠️',
};