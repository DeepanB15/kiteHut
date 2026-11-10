import client from './client';
import type {
  Notification,
  NotificationList,
  QualityGateConfig,
  TrendResponse,
} from '../types/product';

// ============================================================
// Trends
// ============================================================

export const fetchRepositoryTrends = async (repositoryId: number): Promise<TrendResponse> => {
  const { data } = await client.get(`/repositories/${repositoryId}/trends`);
  return data;
};

// ============================================================
// Quality gate configuration
// ============================================================

export const fetchQualityGateConfig = async (repositoryId: number): Promise<QualityGateConfig> => {
  const { data } = await client.get(`/repositories/${repositoryId}/quality-gate`);
  return data;
};

export const updateQualityGateConfig = async (
  repositoryId: number,
  config: { critical_limit: number; security_limit: number; min_health: number }
): Promise<QualityGateConfig> => {
  const { data } = await client.put(`/repositories/${repositoryId}/quality-gate`, config);
  return data;
};

// ============================================================
// Notifications
// ============================================================

export const fetchNotifications = async (unreadOnly = false): Promise<NotificationList> => {
  const params = unreadOnly ? '?unread_only=true' : '';
  const { data } = await client.get(`/notifications${params}`);
  return data;
};

export const markNotificationRead = async (id: number): Promise<Notification> => {
  const { data } = await client.post(`/notifications/${id}/read`);
  return data;
};

export const markAllNotificationsRead = async (): Promise<{ updated: number }> => {
  const { data } = await client.post('/notifications/read-all');
  return data;
};