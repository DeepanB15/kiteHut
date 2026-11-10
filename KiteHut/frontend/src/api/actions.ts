import client from './client';

export interface ActionItem {
  finding_id: string;
  claim_type: string;
  statement: string;
  priority: string;
  final_score: number;
  effort: string;
  expected_impact: string;
  blast_radius: string;
  recommendation_title: string;
  action_order: number;
}

export interface ActionPlan {
  total_actions: number;
  now_count: number;
  next_count: number;
  later_count: number;
  summary: string;
  fix_now: ActionItem[];
  fix_next: ActionItem[];
  improve_later: ActionItem[];
}

export interface RootCauseGroup {
  group_id: string;
  root_cause: string;
  category: string;
  finding_count: number;
  severity: string;
  priority: string;
  description: string;
  fix_suggestion: string;
}

export interface CategoryScore {
  name: string;
  score: number;
  finding_count: number;
  top_issue: string;
}

export interface HealthScore {
  overall_score: number;
  health_level: string;
  total_findings: number;
  critical_findings: number;
  summary: string;
  categories: CategoryScore[];
}

export interface FindingRecommendation {
  title: string;
  description: string;
  why: string;
  fix_steps: Array<{ order: number; action: string; file_hint: string }>;
  best_practice: string;
  expected_result: string;
  risk_if_ignored: string;
  effort: string;
  confidence: number;
}

export const fetchActionPlan = async (analysisId: number) => {
  const { data } = await client.get(`/analyses/${analysisId}/actions`);
  return data as { analysis_id: number; action_plan: ActionPlan | null };
};

export const fetchRootCauses = async (analysisId: number) => {
  const { data } = await client.get(`/analyses/${analysisId}/root-causes`);
  return data as { analysis_id: number; root_causes: RootCauseGroup[] };
};

export const fetchHealthScore = async (analysisId: number) => {
  const { data } = await client.get(`/analyses/${analysisId}/health`);
  return data as { analysis_id: number; health: HealthScore | null };
};

export const fetchFindingRecommendation = async (findingId: number) => {
  const { data } = await client.get(`/findings/${findingId}/recommendation`);
  return data as { finding_id: number; recommendation: FindingRecommendation | null };
};
