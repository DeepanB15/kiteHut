export const formatDate = (dateStr: string | null): string => {
  if (!dateStr) return 'N/A';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

export const formatDuration = (seconds: number | null): string => {
  if (!seconds) return 'N/A';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = (seconds % 60).toFixed(0);
  return `${mins}m ${secs}s`;
};

export const priorityColor = (priority: string): string => {
  const colors: Record<string, string> = {
    P0: 'bg-red-500 text-white',
    P1: 'bg-orange-500 text-white',
    P2: 'bg-yellow-500 text-black',
    P3: 'bg-blue-500 text-white',
    P4: 'bg-gray-400 text-white',
  };
  return colors[priority] || 'bg-gray-300';
};

export const severityColor = (severity: string): string => {
  const colors: Record<string, string> = {
    CRITICAL: 'text-red-600',
    HIGH: 'text-orange-500',
    MEDIUM: 'text-yellow-600',
    LOW: 'text-blue-500',
    INFO: 'text-gray-500',
  };
  return colors[severity] || 'text-gray-500';
};

export const truthColor = (truth: string): string => {
  const colors: Record<string, string> = {
    TRUE: 'text-green-600',
    LIKELY_TRUE: 'text-green-500',
    UNCERTAIN: 'text-yellow-500',
    LIKELY_FALSE: 'text-orange-500',
    FALSE: 'text-red-500',
  };
  return colors[truth] || 'text-gray-500';
};

export const findingStatusColor = (status: string): string => {
  const colors: Record<string, string> = {
    OPEN: 'bg-blue-100 text-blue-700',
    IN_PROGRESS: 'bg-purple-100 text-purple-700',
    RESOLVED: 'bg-green-100 text-green-700',
    IGNORED: 'bg-gray-100 text-gray-600',
    FALSE_POSITIVE: 'bg-gray-100 text-gray-600',
    ACCEPTED_RISK: 'bg-amber-100 text-amber-700',
  };
  return colors[status] || 'bg-gray-100 text-gray-600';
};

export const statusColor = (status: string): string => {
  const colors: Record<string, string> = {
    COMPLETED: 'bg-green-100 text-green-800',
    RUNNING: 'bg-blue-100 text-blue-800',
    PENDING: 'bg-gray-100 text-gray-800',
    FAILED: 'bg-red-100 text-red-800',
  };
  return colors[status] || 'bg-gray-100 text-gray-800';
};

export const healthColor = (level: string): string => {
  const colors: Record<string, string> = {
    EXCELLENT: 'text-green-600',
    GOOD: 'text-blue-600',
    FAIR: 'text-yellow-600',
    POOR: 'text-orange-500',
    CRITICAL: 'text-red-600',
  };
  return colors[level] || 'text-gray-500';
};

export const healthBgColor = (level: string): string => {
  const colors: Record<string, string> = {
    EXCELLENT: 'bg-green-500',
    GOOD: 'bg-blue-500',
    FAIR: 'bg-yellow-500',
    POOR: 'bg-orange-500',
    CRITICAL: 'bg-red-500',
  };
  return colors[level] || 'bg-gray-400';
};
