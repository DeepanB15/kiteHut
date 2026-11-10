import { useQuery } from '@tanstack/react-query';
import { fetchRepositories, fetchRepository, fetchRepositoryAnalyses } from '../api/repositories';

export const useRepositories = () => {
  return useQuery({
    queryKey: ['repositories'],
    queryFn: fetchRepositories,
  });
};

export const useRepository = (id: number) => {
  return useQuery({
    queryKey: ['repository', id],
    queryFn: () => fetchRepository(id),
    enabled: !!id,
  });
};

export const useRepositoryAnalyses = (id: number) => {
  return useQuery({
    queryKey: ['repositoryAnalyses', id],
    queryFn: () => fetchRepositoryAnalyses(id),
    enabled: !!id,
  });
};
