import client from './client';
import type {
  MonitoringReportResponse,
  MonitoringStatusResponse,
} from '../types/monitoring';

export async function triggerMonitoringCheck(
  repositoryPath: string = '.'
): Promise<MonitoringReportResponse> {
  const response = await client.post<MonitoringReportResponse>(
    '/monitoring/check',
    {
      repository_path: repositoryPath,
    }
  );
  return response.data;
}

export async function getMonitoringStatus(
  repositoryPath: string = '.'
): Promise<MonitoringStatusResponse> {
  const response = await client.get<MonitoringStatusResponse>(
    '/monitoring/status',
    {
      params: { repository_path: repositoryPath },
    }
  );
  return response.data;
}
