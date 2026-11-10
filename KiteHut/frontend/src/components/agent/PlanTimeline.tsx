import { useState } from 'react';
import {
  CheckCircle2,
  CircleDashed,
  AlertCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  Terminal,
  FileCode,
  Search,
  Wrench,
  GitBranch,
} from 'lucide-react';
import type { PlanStepResponse } from '../../types/agent';

interface PlanTimelineProps {
  steps: PlanStepResponse[];
  currentStepIndex: number;
}

export default function PlanTimeline({ steps, currentStepIndex }: PlanTimelineProps) {
  const [expandedStepId, setExpandedStepId] = useState<string | number | null>(null);

  const toggleExpand = (stepId: string | number) => {
    setExpandedStepId((prev) => (prev === stepId ? null : stepId));
  };

  const getToolIcon = (toolName: string) => {
    switch (toolName.toLowerCase()) {
      case 'read_file':
      case 'view_file':
        return <FileCode className="w-4 h-4 text-blue-500" />;
      case 'search_codebase':
      case 'find_symbol':
        return <Search className="w-4 h-4 text-indigo-500" />;
      case 'git_diff':
      case 'git_commit':
      case 'git_status':
        return <GitBranch className="w-4 h-4 text-emerald-500" />;
      case 'run_command':
      case 'run_tests':
        return <Terminal className="w-4 h-4 text-amber-500" />;
      default:
        return <Wrench className="w-4 h-4 text-gray-500" />;
    }
  };

  const getStepStatus = (index: number, step: PlanStepResponse) => {
    const rawStatus = (step.status || '').toUpperCase();
    if (rawStatus === 'COMPLETED') return 'COMPLETED';
    if (rawStatus === 'FAILED') return 'FAILED';
    if (index === currentStepIndex) return 'RUNNING';
    if (index < currentStepIndex) return 'COMPLETED';
    return 'PENDING';
  };

  if (!steps || steps.length === 0) {
    return (
      <div className="p-8 text-center bg-gray-50 rounded-xl border border-dashed border-gray-300">
        <p className="text-sm text-gray-500">No execution plan generated yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {steps.map((step, idx) => {
        const status = getStepStatus(idx, step);
        const isExpanded = expandedStepId === step.step_id;
        const isCurrent = idx === currentStepIndex;

        return (
          <div
            key={step.step_id ?? idx}
            className={`rounded-xl border transition-all duration-200 overflow-hidden ${
              isCurrent
                ? 'border-blue-400 bg-blue-50/40 shadow-sm ring-1 ring-blue-400/50'
                : status === 'COMPLETED'
                ? 'border-gray-200 bg-white hover:border-gray-300'
                : status === 'FAILED'
                ? 'border-red-300 bg-red-50/30'
                : 'border-gray-200 bg-gray-50/50 opacity-80'
            }`}
          >
            {/* Step header row */}
            <div
              onClick={() => toggleExpand(step.step_id)}
              className="px-4 py-3 flex items-center justify-between cursor-pointer select-none"
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                {/* Status Indicator */}
                <div className="flex-shrink-0">
                  {status === 'COMPLETED' && (
                    <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                  )}
                  {status === 'RUNNING' && (
                    <div className="relative flex items-center justify-center">
                      <div className="w-5 h-5 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
                    </div>
                  )}
                  {status === 'FAILED' && (
                    <AlertCircle className="w-5 h-5 text-red-500" />
                  )}
                  {status === 'PENDING' && (
                    <CircleDashed className="w-5 h-5 text-gray-400" />
                  )}
                </div>

                {/* Step Index badge */}
                <span className="text-xs font-mono font-bold text-gray-400 px-1.5 py-0.5 rounded bg-gray-100">
                  #{idx + 1}
                </span>

                {/* Tool Icon & Name */}
                <div className="flex items-center gap-1.5 px-2 py-0.5 bg-gray-100/80 rounded text-xs font-mono font-semibold text-gray-700">
                  {getToolIcon(step.tool_name)}
                  <span>{step.tool_name}</span>
                </div>

                {/* Description */}
                <p className="text-sm font-medium text-gray-800 truncate">
                  {step.description}
                </p>
              </div>

              {/* Right indicators */}
              <div className="flex items-center gap-3 ml-2 flex-shrink-0">
                {step.result?.duration_ms ? (
                  <span className="text-xs text-gray-400 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {step.result.duration_ms}ms
                  </span>
                ) : null}

                <button
                  type="button"
                  className="text-gray-400 hover:text-gray-600 p-1"
                  aria-label={isExpanded ? 'Collapse step' : 'Expand step'}
                >
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4" />
                  ) : (
                    <ChevronDown className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Expandable Step Details */}
            {isExpanded && (
              <div className="px-4 pb-4 pt-1 border-t border-gray-100 space-y-3 bg-white/70">
                {/* Arguments */}
                {step.arguments && Object.keys(step.arguments).length > 0 && (
                  <div>
                    <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 block mb-1">
                      Arguments
                    </span>
                    <pre className="bg-gray-950 text-gray-100 p-2.5 rounded-lg text-xs font-mono overflow-x-auto border border-gray-800">
                      {JSON.stringify(step.arguments, null, 2)}
                    </pre>
                  </div>
                )}

                {/* Expected Output */}
                {step.expected_output && (
                  <div>
                    <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 block mb-1">
                      Expected Output
                    </span>
                    <p className="text-xs text-gray-600 bg-gray-50 p-2 rounded border border-gray-200">
                      {step.expected_output}
                    </p>
                  </div>
                )}

                {/* Result output */}
                {step.result?.output && (
                  <div>
                    <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600 block mb-1">
                      Execution Result
                    </span>
                    <pre className="bg-gray-950 text-emerald-400 p-2.5 rounded-lg text-xs font-mono overflow-x-auto max-h-60 border border-gray-800">
                      {step.result.output}
                    </pre>
                  </div>
                )}

                {/* Error */}
                {(step.error || step.result?.error) && (
                  <div>
                    <span className="text-xs font-semibold uppercase tracking-wider text-red-600 block mb-1">
                      Error Output
                    </span>
                    <pre className="bg-red-950 text-red-300 p-2.5 rounded-lg text-xs font-mono overflow-x-auto max-h-48 border border-red-900">
                      {step.error || step.result?.error}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
