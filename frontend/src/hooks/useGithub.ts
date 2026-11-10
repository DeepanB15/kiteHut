import { useQuery } from '@tanstack/react-query';
import {
  fetchGithubStatus,
  fetchPrAnalysis,
  fetchPrAnalyses,
} from '../api/github';

export const useGithubStatus = () => {
  return useQuery({
    queryKey: ['githubStatus'],
    queryFn: fetchGithubStatus,
  });
};

export const usePrAnalyses = () => {
  return useQuery({
    queryKey: ['prAnalyses'],
    queryFn: fetchPrAnalyses,
  });
};

export const usePrAnalysis = (id: number) => {
  return useQuery({
    queryKey: ['prAnalysis', id],
    queryFn: () => fetchPrAnalysis(id),
    enabled: !!id,
  });
};