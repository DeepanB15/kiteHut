import {
  FileCode2,
  Code2,
  ShieldCheck,
  AlertTriangle,
  Zap,
} from 'lucide-react';
import type { MonitoringReportResponse } from '../../types/monitoring';

interface ImpactRadarProps {
  latestReport: MonitoringReportResponse | null;
  totalEventsCount: number;
  totalNewFindingsCount: number;
}

export default function ImpactRadar({
  latestReport,
  totalEventsCount,
  totalNewFindingsCount,
}: ImpactRadarProps) {
  const impactedFilesCount = latestReport?.impacted_files?.length || 0;
  const categories = latestReport?.triggered_categories || [];
  const durationMs = latestReport?.duration_ms || 0;
  const resolvedCount = latestReport?.resolved_findings_count || 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Metric 1: Impacted Files */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-xs flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Impacted Files
          </p>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-2xl font-bold text-gray-900">{impactedFilesCount}</span>
            <span className="text-xs text-gray-500">
              ({totalEventsCount} total events)
            </span>
          </div>
        </div>
        <div className="p-3 bg-blue-50 text-blue-600 rounded-xl">
          <FileCode2 className="w-5 h-5" />
        </div>
      </div>

      {/* Metric 2: Specialist Scanners */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-xs flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Targeted Scans
          </p>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-2xl font-bold text-gray-900">{categories.length}</span>
            <span className="text-xs text-gray-500">specialists</span>
          </div>
          {categories.length > 0 && (
            <div className="flex gap-1 flex-wrap mt-1.5">
              {categories.slice(0, 3).map((cat, idx) => (
                <span
                  key={idx}
                  className="px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 text-[10px] font-mono capitalize"
                >
                  {cat}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="p-3 bg-indigo-50 text-indigo-600 rounded-xl">
          <ShieldCheck className="w-5 h-5" />
        </div>
      </div>

      {/* Metric 3: Incremental Findings */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-xs flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            New / Resolved
          </p>
          <div className="flex items-baseline gap-2 mt-1">
            <span
              className={`text-2xl font-bold ${
                totalNewFindingsCount > 0 ? 'text-amber-600' : 'text-gray-900'
              }`}
            >
              +{totalNewFindingsCount}
            </span>
            <span className="text-xs text-emerald-600 font-medium">
              /{resolvedCount} fixed
            </span>
          </div>
        </div>
        <div className="p-3 bg-amber-50 text-amber-600 rounded-xl">
          <AlertTriangle className="w-5 h-5" />
        </div>
      </div>

      {/* Metric 4: Blast-Radius AST Scan Latency */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-xs flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            AST Scan Latency
          </p>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-2xl font-bold text-gray-900">{durationMs}</span>
            <span className="text-xs text-gray-500">ms</span>
          </div>
          <p className="text-[11px] text-emerald-600 mt-1 flex items-center gap-1 font-medium">
            <Zap className="w-3 h-3" /> Sub-second incremental
          </p>
        </div>
        <div className="p-3 bg-emerald-50 text-emerald-600 rounded-xl">
          <Code2 className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
}
