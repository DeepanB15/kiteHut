import { useState, useEffect, useRef } from 'react';
import { Terminal, Trash2, ArrowDownCircle, Check, Copy } from 'lucide-react';
import type { AgentLogEntry } from '../../hooks/useAgent';

interface LiveToolLogsProps {
  logs: AgentLogEntry[];
  onClear?: () => void;
  isConnected?: boolean;
}

export default function LiveToolLogs({
  logs,
  onClear,
  isConnected = false,
}: LiveToolLogsProps) {
  const [autoScroll, setAutoScroll] = useState(true);
  const [filterType, setFilterType] = useState<string>('all');
  const [copied, setCopied] = useState(false);
  const terminalEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (autoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  const filteredLogs = logs.filter((log) => {
    if (filterType === 'all') return true;
    if (filterType === 'tool') return log.type === 'tool_call' || log.type === 'tool_result';
    if (filterType === 'error') return log.type === 'error';
    if (filterType === 'observation') return log.type === 'observation';
    if (filterType === 'approval') return log.type === 'approval';
    return true;
  });

  const handleCopyLogs = () => {
    const text = logs
      .map(
        (l) =>
          `[${l.timestamp}] [${l.type.toUpperCase()}] ${l.message} ${
            l.output ? '\nOutput: ' + l.output : ''
          } ${l.error ? '\nError: ' + l.error : ''}`
      )
      .join('\n');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getLogTypeBadge = (type: AgentLogEntry['type']) => {
    switch (type) {
      case 'tool_call':
        return <span className="text-blue-400 font-bold">[TOOL_CALL]</span>;
      case 'tool_result':
        return <span className="text-emerald-400 font-bold">[TOOL_RES]</span>;
      case 'observation':
        return <span className="text-indigo-400 font-bold">[OBSERVE]</span>;
      case 'approval':
        return <span className="text-amber-400 font-bold">[APPROVAL]</span>;
      case 'error':
        return <span className="text-red-400 font-bold">[ERROR]</span>;
      case 'info':
      default:
        return <span className="text-gray-400 font-bold">[SYS_INFO]</span>;
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-950 rounded-xl border border-gray-800 overflow-hidden shadow-lg">
      {/* Terminal Control Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-gray-900/90 border-b border-gray-800 text-xs text-gray-300">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-emerald-400" />
          <span className="font-mono font-semibold text-gray-200">Execution Console</span>
          <span
            className={`w-2 h-2 rounded-full ${
              isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-gray-600'
            }`}
            title={isConnected ? 'Live WebSocket Connected' : 'Disconnected'}
          />
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1 bg-gray-950 p-0.5 rounded-lg border border-gray-800">
          {(['all', 'tool', 'observation', 'error'] as const).map((ft) => (
            <button
              key={ft}
              type="button"
              onClick={() => setFilterType(ft)}
              className={`px-2 py-0.5 rounded text-[11px] capitalize transition-colors ${
                filterType === ft
                  ? 'bg-blue-600 text-white font-semibold'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {ft}
            </button>
          ))}
        </div>

        {/* Action icons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setAutoScroll(!autoScroll)}
            className={`p-1.5 rounded transition-colors ${
              autoScroll
                ? 'text-blue-400 bg-blue-950/60 border border-blue-800'
                : 'text-gray-400 hover:text-gray-200'
            }`}
            title={autoScroll ? 'Auto-scroll active' : 'Auto-scroll paused'}
          >
            <ArrowDownCircle className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={handleCopyLogs}
            className="p-1.5 text-gray-400 hover:text-gray-200 rounded transition-colors"
            title="Copy logs to clipboard"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>

          {onClear && (
            <button
              type="button"
              onClick={onClear}
              className="p-1.5 text-gray-400 hover:text-red-400 rounded transition-colors"
              title="Clear terminal logs"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Terminal Log Stream */}
      <div className="flex-1 p-4 font-mono text-xs overflow-y-auto space-y-2 select-text leading-relaxed text-gray-300">
        {filteredLogs.length === 0 ? (
          <div className="py-12 text-center text-gray-600 italic">
            No live logs received yet for this task.
          </div>
        ) : (
          filteredLogs.map((log) => {
            const timeStr = log.timestamp
              ? new Date(log.timestamp).toLocaleTimeString()
              : '';

            return (
              <div key={log.id} className="group hover:bg-gray-900/40 p-1 rounded">
                <div className="flex items-start gap-2">
                  <span className="text-gray-600 text-[10px] select-none flex-shrink-0">
                    {timeStr}
                  </span>
                  <div className="flex-shrink-0">{getLogTypeBadge(log.type)}</div>
                  <span className="text-gray-200 flex-1 break-words">{log.message}</span>
                </div>

                {/* Optional Output detail */}
                {log.output && (
                  <div className="mt-1 ml-16 p-2 rounded bg-gray-900/80 border border-gray-800 text-emerald-400 overflow-x-auto whitespace-pre-wrap">
                    {log.output}
                  </div>
                )}

                {/* Optional Error detail */}
                {log.error && (
                  <div className="mt-1 ml-16 p-2 rounded bg-red-950/60 border border-red-900/60 text-red-300 overflow-x-auto whitespace-pre-wrap">
                    {log.error}
                  </div>
                )}

                {/* Optional Payload Details */}
                {log.details && Object.keys(log.details).length > 0 && !log.output && !log.error && (
                  <div className="mt-1 ml-16 p-2 rounded bg-gray-900/60 border border-gray-800/80 text-gray-400 overflow-x-auto">
                    <pre className="text-[11px]">{JSON.stringify(log.details, null, 2)}</pre>
                  </div>
                )}
              </div>
            );
          })
        )}
        <div ref={terminalEndRef} />
      </div>
    </div>
  );
}
