import { useState } from 'react';
import {
  FileCode,
  PlusCircle,
  MinusCircle,
  FileEdit,
  Clock,
  ChevronDown,
  ChevronUp,
  Boxes,
} from 'lucide-react';
import type { ChangeEventResponse } from '../../types/monitoring';

interface ChangeStreamFeedProps {
  events: ChangeEventResponse[];
  onClear?: () => void;
}

export default function ChangeStreamFeed({ events }: ChangeStreamFeedProps) {
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedEventId((prev) => (prev === id ? null : id));
  };

  const getChangeTypeBadge = (type: string) => {
    const t = type.toLowerCase();
    if (t.includes('add') || t.includes('create')) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">
          <PlusCircle className="w-3 h-3" /> ADDED
        </span>
      );
    }
    if (t.includes('del') || t.includes('remove')) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-800">
          <MinusCircle className="w-3 h-3" /> DELETED
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800">
        <FileEdit className="w-3 h-3" /> MODIFIED
      </span>
    );
  };

  if (!events || events.length === 0) {
    return (
      <div className="p-10 text-center bg-gray-50 rounded-xl border border-dashed border-gray-300">
        <FileCode className="w-8 h-8 text-gray-400 mx-auto mb-2" />
        <p className="text-sm text-gray-500 font-medium">
          Watching filesystem & Git working tree...
        </p>
        <p className="text-xs text-gray-400 mt-1">
          Make a code change in the target repository to see incremental blast-radius and AST impact.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {events.map((ev) => {
        const isExpanded = expandedEventId === ev.event_id;
        const timeStr = ev.timestamp
          ? new Date(ev.timestamp).toLocaleTimeString()
          : '';

        return (
          <div
            key={ev.event_id}
            className="rounded-xl border border-gray-200 bg-white shadow-xs overflow-hidden transition-all hover:border-gray-300"
          >
            {/* Main event row */}
            <div
              onClick={() => toggleExpand(ev.event_id)}
              className="px-4 py-3 flex items-center justify-between cursor-pointer select-none"
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                {getChangeTypeBadge(ev.change_type)}

                <span className="font-mono text-xs font-bold text-gray-800 truncate">
                  {ev.file_path}
                </span>

                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 uppercase">
                  {ev.source}
                </span>
              </div>

              <div className="flex items-center gap-3 ml-2 flex-shrink-0">
                {ev.affected_symbols && ev.affected_symbols.length > 0 && (
                  <span className="hidden sm:inline-flex items-center gap-1 text-xs text-indigo-600 font-mono bg-indigo-50 px-2 py-0.5 rounded">
                    <Boxes className="w-3 h-3" />
                    {ev.affected_symbols.length} symbol{ev.affected_symbols.length > 1 ? 's' : ''}
                  </span>
                )}

                {timeStr && (
                  <span className="text-xs text-gray-400 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {timeStr}
                  </span>
                )}

                <button
                  type="button"
                  className="text-gray-400 hover:text-gray-600 p-1"
                  aria-label={isExpanded ? 'Collapse' : 'Expand'}
                >
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4" />
                  ) : (
                    <ChevronDown className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Expanded details */}
            {isExpanded && (
              <div className="px-4 pb-4 pt-1 border-t border-gray-100 space-y-3 bg-gray-50/60">
                {/* Affected AST symbols */}
                {ev.affected_symbols && ev.affected_symbols.length > 0 && (
                  <div>
                    <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 block mb-1.5">
                      Impacted AST Symbols
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {ev.affected_symbols.map((sym, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-1 bg-indigo-100/70 border border-indigo-200 text-indigo-800 font-mono text-xs rounded-md font-medium"
                        >
                          {sym}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Diff Preview */}
                {ev.diff_content && (
                  <div>
                    <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 block mb-1">
                      Unified Diff Snippet
                    </span>
                    <pre className="bg-gray-950 text-gray-200 p-3 rounded-lg text-xs font-mono overflow-x-auto max-h-60 border border-gray-800">
                      {ev.diff_content}
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
