/**
 * Continuous Guardian Monitoring TypeScript Type Definitions
 */

export interface ChangeEventResponse {
  event_id: string;
  source: string;
  file_path: string;
  change_type: string;
  diff_content?: string | null;
  affected_symbols: string[];
  timestamp: string;
  metadata?: Record<string, any>;
}

export interface FindingSummaryResponse {
  finding_id: string;
  category: string;
  severity: string;
  title: string;
  description: string;
  file_path?: string | null;
  line_number?: number | null;
  priority?: string | null;
  truth_status?: string | null;
}

export interface MonitoringReportResponse {
  report_id: string;
  timestamp: string;
  changed_events: ChangeEventResponse[];
  impacted_files: string[];
  triggered_categories: string[];
  new_findings: FindingSummaryResponse[];
  resolved_findings_count: number;
  duration_ms: number;
}

export interface MonitoringStatusResponse {
  repository_path: string;
  status: string;
  message: string;
  timestamp: string;
}

export interface MonitoringWebSocketEvent {
  event: string;
  report?: MonitoringReportResponse;
  repository_path?: string;
  interval?: number;
  message?: string;
  timestamp?: string;
}
