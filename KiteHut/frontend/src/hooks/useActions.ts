import { useQuery } from '@tanstack/react-query';
import { fetchActionPlan, fetchRootCauses, fetchHealthScore, fetchFindingRecommendation } from '../api/actions';

export const useActionPlan = (analysisId: number) => {
  return useQuery({
    queryKey: ['actionPlan', analysisId],
    queryFn: () => fetchActionPlan(analysisId),
    enabled: !!analysisId,
  });
};

export const useRootCauses = (analysisId: number) => {
  return useQuery({
    queryKey: ['rootCauses', analysisId],
    queryFn: () => fetchRootCauses(analysisId),
    enabled: !!analysisId,
  });
};

export const useHealthScore = (analysisId: number) => {
  return useQuery({
    queryKey: ['healthScore', analysisId],
    queryFn: () => fetchHealthScore(analysisId),
    enabled: !!analysisId,
  });
};

export const useFindingRecommendation = (findingId: number) => {
  return useQuery({
    queryKey: ['findingRecommendation', findingId],
    queryFn: () => fetchFindingRecommendation(findingId),
    enabled: !!findingId,
  });
};
