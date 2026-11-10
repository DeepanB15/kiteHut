export interface PrFinding {
  id: number;
  category: string;
  severity: string;
  priority: string;
  file_path: string;
  line_start: number | null;
  code_snippet: string | null;
  message: string;
  recommendation: string | null;
  source: string;
  confidence: number;
  status: string;
  status_note: string | null;
}

export interface PrAnalysis {
  id: number;
  repository_id: number;
  pull_number: number;
  pr_title: string | null;
  pr_url: string | null;
  status: string;
  findings_count: number;
  error_message: string | null;
  comment_posted: boolean;
  gate_result: string | null;
  gate_reasons: string[] | null;
  status_check_posted: boolean;
  base_sha: string | null;
  head_sha: string | null;
  created_at: string;
  completed_at: string | null;
  findings: PrFinding[];
}

export interface PrAnalysisSummary {
  id: number;
  repository_id: number;
  pull_number: number;
  pr_title: string | null;
  pr_url: string | null;
  status: string;
  findings_count: number;
  error_message: string | null;
  comment_posted: boolean;
  gate_result: string | null;
  gate_reasons: string[] | null;
  status_check_posted: boolean;
  created_at: string;
  completed_at: string | null;
}

export interface GithubStatus {
  authenticated: boolean;
  username: string | null;
  rate_limit: { limit: number; remaining: number; reset: number } | null;
  webhook_secret_configured: boolean;
  pr_comments_enabled: boolean;
  status_checks_enabled: boolean;
  message: string | null;
}