import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  triggerMonitoringCheck,
  getMonitoringStatus,
} from '../api/monitoring';
import type {
  ChangeEventResponse,
  FindingSummaryResponse,
  MonitoringReportResponse,
  MonitoringWebSocketEvent,
} from '../types/monitoring';

export const useMonitoringStatus = (repositoryPath: string = '.') => {
  return useQuery({
    queryKey: ['monitoringStatus', repositoryPath],
    queryFn: () => getMonitoringStatus(repositoryPath),
    refetchInterval: 30000,
  });
};

export const useTriggerMonitoringCheck = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (repositoryPath: string) => triggerMonitoringCheck(repositoryPath),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitoringStatus'] });
      queryClient.invalidateQueries({ queryKey: ['findings'] });
    },
  });
};

export function useMonitoringWebSocket(
  initialRepoPath: string | null = '.',
  initialInterval: number = 3.0
) {
  const [isConnected, setIsConnected] = useState(false);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [activeRepoPath, setActiveRepoPath] = useState<string | null>(initialRepoPath);
  const [pollInterval, setPollInterval] = useState<number>(initialInterval);
  const [latestReport, setLatestReport] = useState<MonitoringReportResponse | null>(null);
  const [changeEvents, setChangeEvents] = useState<ChangeEventResponse[]>([]);
  const [newFindings, setNewFindings] = useState<FindingSummaryResponse[]>([]);
  const [allImpactedFiles, setAllImpactedFiles] = useState<string[]>([]);
  const [allTriggeredCategories, setAllTriggeredCategories] = useState<string[]>([]);
  const [lastHeartbeat, setLastHeartbeat] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();

  const handleIncomingReport = useCallback(
    (report: MonitoringReportResponse) => {
      setLatestReport(report);
      setLastHeartbeat(report.timestamp);

      if (report.changed_events && report.changed_events.length > 0) {
        setChangeEvents((prev) => [...report.changed_events, ...prev].slice(0, 100));
      }

      if (report.new_findings && report.new_findings.length > 0) {
        setNewFindings((prev) => [...report.new_findings, ...prev].slice(0, 100));
        queryClient.invalidateQueries({ queryKey: ['findings'] });
      }

      if (report.impacted_files && report.impacted_files.length > 0) {
        setAllImpactedFiles((prev) =>
          Array.from(new Set([...report.impacted_files, ...prev]))
        );
      }

      if (report.triggered_categories && report.triggered_categories.length > 0) {
        setAllTriggeredCategories((prev) =>
          Array.from(new Set([...report.triggered_categories, ...prev]))
        );
      }
    },
    [queryClient]
  );

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/v1/monitoring/ws`;

    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      if (activeRepoPath) {
        ws.send(
          JSON.stringify({
            action: 'subscribe',
            repository_path: activeRepoPath,
            interval: pollInterval,
          })
        );
      }
    };

    ws.onmessage = (event) => {
      try {
        const data: MonitoringWebSocketEvent = JSON.parse(event.data);
        switch (data.event) {
          case 'connected':
            break;
          case 'subscribed':
            setIsSubscribed(true);
            if (data.repository_path) setActiveRepoPath(data.repository_path);
            if (data.interval) setPollInterval(data.interval);
            break;
          case 'unsubscribed':
            setIsSubscribed(false);
            break;
          case 'changes_detected':
          case 'monitoring_heartbeat':
          case 'check_result':
            if (data.report) {
              handleIncomingReport(data.report);
            }
            break;
          default:
            break;
        }
      } catch (e) {
        console.error('Failed to parse monitoring websocket message:', e);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      setIsSubscribed(false);
    };

    ws.onerror = (err) => {
      console.error('Monitoring WebSocket error:', err);
      setIsConnected(false);
    };

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [activeRepoPath, pollInterval, handleIncomingReport]);

  const sendAction = useCallback((payload: Record<string, any>) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const subscribe = useCallback(
    (repoPath: string, interval?: number) => {
      setActiveRepoPath(repoPath);
      if (interval) setPollInterval(interval);
      sendAction({
        action: 'subscribe',
        repository_path: repoPath,
        interval: interval || pollInterval,
      });
    },
    [sendAction, pollInterval]
  );

  const unsubscribe = useCallback(() => {
    sendAction({ action: 'unsubscribe' });
    setIsSubscribed(false);
  }, [sendAction]);

  const checkNow = useCallback(
    (repoPath?: string) => {
      sendAction({
        action: 'check_now',
        repository_path: repoPath || activeRepoPath || '.',
      });
    },
    [sendAction, activeRepoPath]
  );

  const clearHistory = useCallback(() => {
    setChangeEvents([]);
    setNewFindings([]);
    setAllImpactedFiles([]);
    setAllTriggeredCategories([]);
  }, []);

  return {
    isConnected,
    isSubscribed,
    activeRepoPath,
    pollInterval,
    latestReport,
    changeEvents,
    newFindings,
    allImpactedFiles,
    allTriggeredCategories,
    lastHeartbeat,
    subscribe,
    unsubscribe,
    checkNow,
    clearHistory,
  };
}
