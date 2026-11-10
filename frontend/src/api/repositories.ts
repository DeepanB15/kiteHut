import client from './client';
import type { Repository } from '../types/repository';
import type { AnalysisRun } from '../types/analysis';

export const fetchRepositories = async (): Promise<{ repositories: Repository[] }> => {
  const { data } = await client.get('/repositories');
  return data;
};

export const fetchRepository = async (id: number): Promise<Repository> => {
  const { data } = await client.get(`/repositories/${id}`);
  return data;
};

export const fetchRepositoryAnalyses = async (id: number): Promise<{ analyses: AnalysisRun[] }> => {
  const { data } = await client.get(`/repositories/${id}/analyses`);
  return data;
};
