import client from './client';
import type { FindingDetail } from '../types/analysis';

export const fetchFinding = async (id: number): Promise<FindingDetail> => {
  const { data } = await client.get(`/findings/${id}`);
  return data;
};
