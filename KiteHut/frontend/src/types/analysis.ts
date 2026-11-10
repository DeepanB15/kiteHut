export interface AnalysisRun {
  id: number;
  repository_id: number;
  status: string;
  branch: string;
  commit_hash: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  total_findings: number;
  error_message: string | null;
  created_at: string | null;
  mode: string;
  enabled_agents: string[] | null;
}

export interface AnalysisDetail extends AnalysisRun {
  priority_distribution: Record<string, number>;
}

export interface ComparisonSummary {
  new: number;
  resolved: number;
  existing: number;
  changed: number;
}

export interface ComparisonResult {
  repository_id: number;
  previous_analysis_id: number;
  current_analysis_id: number;
  summary: ComparisonSummary;
  new_findings: FindingSummary[];
  resolved_findings: FindingSummary[];
  existing_findings: FindingSummary[];
  changed_findings: any[];
}

export interface AnalysisJob {
  job_id: string;
  repository_url: string;
  job_type: string;
  pull_number: number | null;
  status: string;
  current_stage: string | null;
  message: string | null;
  error_message: string | null;
  analysis_run_id: number | null;
  pr_analysis_id: number | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface FindingSummary {
  id: number;
  fingerprint: string;
  claim_type: string;
  category: string;
  statement: string;
  source_agent: string;
  truth_value: string;
  confidence: number;
  severity: string;
  severity_score: number;
  final_score: number;
  priority: string;
  status: string;
  status_note: string | null;
}

export interface FindingDetail extends FindingSummary {
  user_impact: number;
  system_impact: number;
  business_impact: number;
  overall_impact: number;
  exploitability: number;
  status_updated_at: string | null;
  evidence: EvidenceItem[];
}

export interface EvidenceItem {
  id: number;
  evidence_type: string;
  source: string;
  file_path: string;
  line_start: number;
  line_end: number;
  content: string;
  relation: string;
  strength: string;
}
