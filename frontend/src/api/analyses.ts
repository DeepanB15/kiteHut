import client from './client';
import type { AnalysisDetail, AnalysisJob, FindingSummary, ComparisonResult } from '../types/analysis';
import type { AnalysisSettings } from '../types/product';

export interface FindingFilters {
  priority?: string;
  severity?: string;
  truth_value?: string;
  category?: string;
  status?: string;
}

export const analyzeRepository = async (
  repositoryUrl: string,
  settings?: AnalysisSettings
): Promise<AnalysisJob> => {
  const { data } = await client.post('/analyze', {
    repository_url: repositoryUrl,
    ...(settings?.mode ? { mode: settings.mode } : {}),
    ...(settings?.enabled_agents?.length ? { enabled_agents: settings.enabled_agents } : {}),
  });
  return data;
};

export const fetchJobStatus = async (jobId: string): Promise<AnalysisJob> => {
  const { data } = await client.get(`/jobs/${jobId}`);
  return data;
};

export const fetchAnalysis = async (id: number): Promise<AnalysisDetail> => {
  const { data } = await client.get(`/analyses/${id}`);
  return data;
};

export const fetchAnalysisFindings = async (
  id: number,
  filters?: FindingFilters
): Promise<{ findings: FindingSummary[]; total: number }> => {
  const params = new URLSearchParams();
  if (filters?.priority) params.append('priority', filters.priority);
  if (filters?.severity) params.append('severity', filters.severity);
  if (filters?.truth_value) params.append('truth_value', filters.truth_value);
  if (filters?.category) params.append('category', filters.category);
  if (filters?.status) params.append('status', filters.status);
  const { data } = await client.get(`/analyses/${id}/findings?${params.toString()}`);
  return data;
};

export const fetchComparison = async (
  analysisId: number,
  previousAnalysisId?: number
): Promise<ComparisonResult> => {
  const params = previousAnalysisId ? `?previous_analysis_id=${previousAnalysisId}` : '';
  const { data } = await client.get(`/analyses/${analysisId}/compare${params}`);
  return data;
};

// ============================================================
// Phase 10 — finding status lifecycle
// ============================================================

export const updateFindingStatus = async (
  findingId: number,
  status: string,
  note?: string
): Promise<{ id: number; status: string; status_note: string | null }> => {
  const { data } = await client.patch(`/findings/${findingId}/status`, {
    status,
    note: note || null,
  });
  return data;
};

export const updatePrFindingStatus = async (
  findingId: number,
  status: string,
  note?: string
): Promise<{ id: number; status: string; status_note: string | null }> => {
  const { data } = await client.patch(`/pr-findings/${findingId}/status`, {
    status,
    note: note || null,
  });
  return data;
};

// ============================================================
// Phase 10 — report downloads
// ============================================================

export const reportUrl = (analysisId: number, format: 'md' | 'json' | 'pdf'): string =>
  `/api/v1/analyses/${analysisId}/report.${format}`;