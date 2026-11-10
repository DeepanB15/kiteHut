import { useState } from 'react';
import {
  ShieldCheck,
  Radio,
  Play,
  Pause,
  RefreshCw,
  FolderGit2,
  AlertTriangle,
  FileCode2,
  Trash2,
} from 'lucide-react';
import {
  useTriggerMonitoringCheck,
  useMonitoringWebSocket,
} from '../hooks/useMonitoring';
import ImpactRadar from '../components/monitoring/ImpactRadar';
import ChangeStreamFeed from '../components/monitoring/ChangeStreamFeed';
import { priorityColor, severityColor } from '../utils/formatters';

export default function GuardianMonitoringPage() {
  const [targetRepo, setTargetRepo] = useState('.');
  const [sliderInterval, setSliderInterval] = useState(3);

  // Trigger manual check mutation
  const checkMutation = useTriggerMonitoringCheck();

  // WebSocket hook
  const {
    isConnected,
    isSubscribed,
    latestReport,
    changeEvents,
    newFindings,
    subscribe,
    unsubscribe,
    checkNow,
    clearHistory,
  } = useMonitoringWebSocket(targetRepo, sliderInterval);

  const handleToggleStreaming = () => {
    if (isSubscribed) {
      unsubscribe();
    } else {
      subscribe(targetRepo, sliderInterval);
    }
  };

  const handleManualCheck = () => {
    if (isConnected) {
      checkNow(targetRepo);
    } else {
      checkMutation.mutate(targetRepo);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)] gap-4">
      {/* Header & Controls */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
        {/* Left: Title & Status */}
        <div className="flex items-center gap-3">
          <div className="p-2 bg-emerald-50 text-emerald-600 rounded-xl">
            <ShieldCheck className="w-6 h-6" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-gray-900">
                Continuous Guardian Monitor
              </h1>
              {isSubscribed ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                  <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse" />
                  Live Streaming
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-700">
                  Paused
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500">
              Incremental AST Blast-Radius Detection & Autonomous Specialist Guarding
            </p>
          </div>
        </div>

        {/* Center/Right Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* Target Repo Input */}
          <div className="flex items-center gap-1.5 bg-gray-50 border border-gray-300 rounded-lg px-2.5 py-1.5 text-xs">
            <FolderGit2 className="w-3.5 h-3.5 text-gray-500" />
            <input
              type="text"
              value={targetRepo}
              onChange={(e) => setTargetRepo(e.target.value)}
              placeholder="Repository path"
              className="bg-transparent font-mono outline-none text-xs w-28 sm:w-36 text-gray-800"
            />
          </div>

          {/* Interval Control */}
          <div className="flex items-center gap-2 text-xs text-gray-600 bg-gray-50 border border-gray-300 rounded-lg px-2.5 py-1.5">
            <Radio className="w-3.5 h-3.5 text-blue-500" />
            <span>{sliderInterval}s</span>
            <input
              type="range"
              min={1}
              max={10}
              step={0.5}
              value={sliderInterval}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                setSliderInterval(val);
                if (isSubscribed) subscribe(targetRepo, val);
              }}
              className="w-16 sm:w-20 cursor-pointer"
            />
          </div>

          {/* Stream Toggle Button */}
          <button
            type="button"
            onClick={handleToggleStreaming}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold shadow-xs transition-colors ${
              isSubscribed
                ? 'bg-amber-600 hover:bg-amber-700 text-white'
                : 'bg-emerald-600 hover:bg-emerald-700 text-white'
            }`}
          >
            {isSubscribed ? (
              <>
                <Pause className="w-3.5 h-3.5" /> Pause Stream
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" /> Start Stream
              </>
            )}
          </button>

          {/* Check Now */}
          <button
            type="button"
            onClick={handleManualCheck}
            disabled={checkMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors disabled:opacity-50"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${checkMutation.isPending ? 'animate-spin' : ''}`}
            />
            Scan Now
          </button>

          {/* Clear History */}
          <button
            type="button"
            onClick={clearHistory}
            className="p-2 text-gray-400 hover:text-red-500 rounded-lg hover:bg-gray-100 transition-colors"
            title="Clear stream events"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Impact Radar (4 KPI Cards) */}
      <ImpactRadar
        latestReport={latestReport}
        totalEventsCount={changeEvents.length}
        totalNewFindingsCount={newFindings.length}
      />

      {/* Split Stream Content */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
        {/* Left Pane (7 cols): File Change Stream & Diffs */}
        <div className="lg:col-span-7 flex flex-col bg-white rounded-xl border border-gray-200 p-4 shadow-xs overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <FileCode2 className="w-4 h-4 text-blue-600" />
              <h2 className="text-sm font-bold text-gray-900">
                File Alteration Stream & AST Diff
              </h2>
            </div>
            <span className="text-xs font-semibold text-gray-500">
              {changeEvents.length} Captured Events
            </span>
          </div>

          <div className="flex-1 overflow-y-auto">
            <ChangeStreamFeed events={changeEvents} onClear={clearHistory} />
          </div>
        </div>

        {/* Right Pane (5 cols): Incremental Specialist Findings */}
        <div className="lg:col-span-5 flex flex-col bg-white rounded-xl border border-gray-200 p-4 shadow-xs overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              <h2 className="text-sm font-bold text-gray-900">
                Incremental Guard Findings
              </h2>
            </div>
            <span className="text-xs font-semibold text-gray-500">
              {newFindings.length} Detected
            </span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-3">
            {newFindings.length === 0 ? (
              <div className="p-8 text-center bg-gray-50 rounded-xl border border-dashed border-gray-300">
                <ShieldCheck className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                <p className="text-sm text-gray-600 font-medium">
                  Workspace Clean & Protected
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  Continuous Guardian will surface issues dynamically upon file saves.
                </p>
              </div>
            ) : (
              newFindings.map((finding) => (
                <div
                  key={finding.finding_id}
                  className="p-3.5 rounded-xl border border-amber-200 bg-amber-50/40 shadow-xs space-y-2 hover:border-amber-300 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${priorityColor(
                        finding.priority || 'P2'
                      )}`}
                    >
                      {finding.priority || 'P2'}
                    </span>
                    <span
                      className={`text-xs font-semibold ${severityColor(
                        finding.severity
                      )}`}
                    >
                      {finding.severity}
                    </span>
                  </div>

                  <h4 className="text-xs font-bold text-gray-900">{finding.title}</h4>
                  <p className="text-xs text-gray-600 line-clamp-2 leading-relaxed">
                    {finding.description}
                  </p>

                  <div className="flex items-center justify-between pt-1 text-[11px] text-gray-500 border-t border-amber-100">
                    <span className="font-mono truncate max-w-[200px]">
                      {finding.file_path}
                      {finding.line_number ? `:${finding.line_number}` : ''}
                    </span>

                    <span className="capitalize px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-semibold">
                      {finding.category}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
