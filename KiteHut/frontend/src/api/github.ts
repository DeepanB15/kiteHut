import client from './client';
import type { AnalysisJob } from '../types/analysis';
import type { GithubStatus, PrAnalysis, PrAnalysisSummary } from '../types/pr';

export const analyzePullRequest = async (
  repositoryUrl: string,
  pullNumber: number
): Promise<AnalysisJob> => {
  const { data } = await client.post('/analyze-pr', {
    repository_url: repositoryUrl,
    pull_number: pullNumber,
  });
  return data;
};

export const fetchGithubStatus = async (): Promise<GithubStatus> => {
  const { data } = await client.get('/github/status');
  return data;
};

export const fetchPrAnalyses = async (): Promise<{ pr_analyses: PrAnalysisSummary[]; total: number }> => {
  const { data } = await client.get('/pr-analyses');
  return data;
};

export const fetchPrAnalysis = async (id: number): Promise<PrAnalysis> => {
  const { data } = await client.get(`/pr-analyses/${id}`);
  return data;
};