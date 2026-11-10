import { useQuery } from '@tanstack/react-query';
import { fetchFinding } from '../api/findings';

export const useFinding = (id: number) => {
  return useQuery({
    queryKey: ['finding', id],
    queryFn: () => fetchFinding(id),
    enabled: !!id,
  });
};
