import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchNotifications,
  fetchQualityGateConfig,
  fetchRepositoryTrends,
  markAllNotificationsRead,
  markNotificationRead,
  updateQualityGateConfig,
} from '../api/product';

// ============================================================
// Trends
// ============================================================

export const useRepositoryTrends = (repositoryId: number) => {
  return useQuery({
    queryKey: ['trends', repositoryId],
    queryFn: () => fetchRepositoryTrends(repositoryId),
    enabled: !!repositoryId,
  });
};

// ============================================================
// Quality gate configuration
// ============================================================

export const useQualityGateConfig = (repositoryId: number) => {
  return useQuery({
    queryKey: ['qualityGate', repositoryId],
    queryFn: () => fetchQualityGateConfig(repositoryId),
    enabled: !!repositoryId,
  });
};

export const useUpdateQualityGate = (repositoryId: number) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: { critical_limit: number; security_limit: number; min_health: number }) =>
      updateQualityGateConfig(repositoryId, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['qualityGate', repositoryId] });
    },
  });
};

// ============================================================
// Notifications
// ============================================================

export const useNotifications = (unreadOnly = false) => {
  return useQuery({
    queryKey: ['notifications', unreadOnly],
    queryFn: () => fetchNotifications(unreadOnly),
    refetchInterval: 30_000,
  });
};

export const useMarkNotificationRead = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
};

export const useMarkAllNotificationsRead = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
};