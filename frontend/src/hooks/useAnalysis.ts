import { useQuery } from '@tanstack/react-query';
import { fetchAnalysis, fetchAnalysisFindings, fetchComparison } from '../api/analyses';

export const useAnalysis = (id: number) => {
  return useQuery({
    queryKey: ['analysis', id],
    queryFn: () => fetchAnalysis(id),
    enabled: !!id,
  });
};

export const useAnalysisFindings = (
  id: number,
  filters?: { priority?: string; severity?: string; truth_value?: string; category?: string; status?: string }
) => {
  return useQuery({
    queryKey: ['analysisFindings', id, filters],
    queryFn: () => fetchAnalysisFindings(id, filters),
    enabled: !!id,
  });
};

export const useComparison = (analysisId: number, previousAnalysisId?: number) => {
  return useQuery({
    queryKey: ['comparison', analysisId, previousAnalysisId],
    queryFn: () => fetchComparison(analysisId, previousAnalysisId),
    enabled: !!analysisId,
  });
};
