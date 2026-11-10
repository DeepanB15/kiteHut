import { Sparkles, Brain, Clock } from 'lucide-react';
import type { AgentObservationResponse } from '../../types/agent';

interface ObservationFeedProps {
  observations: AgentObservationResponse[];
}

export default function ObservationFeed({ observations }: ObservationFeedProps) {
  if (!observations || observations.length === 0) {
    return (
      <div className="p-8 text-center bg-gray-50 rounded-xl border border-dashed border-gray-300">
        <Brain className="w-8 h-8 text-gray-400 mx-auto mb-2" />
        <p className="text-sm text-gray-500">No agent reasoning observations recorded yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {observations.map((obs, idx) => {
        const timeStr = obs.timestamp
          ? new Date(obs.timestamp).toLocaleTimeString()
          : '';

        return (
          <div
            key={idx}
            className="p-4 rounded-xl border border-indigo-100 bg-gradient-to-r from-indigo-50/50 to-white shadow-xs space-y-2"
          >
            <div className="flex items-center justify-between text-xs text-indigo-700">
              <div className="flex items-center gap-1.5 font-semibold">
                <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                <span>Agent Hypothesis & Discovery</span>
                {obs.step_id !== undefined && obs.step_id !== null && (
                  <span className="px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800 font-mono text-[10px]">
                    Step #{obs.step_id}
                  </span>
                )}
              </div>
              {timeStr && (
                <span className="text-gray-400 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {timeStr}
                </span>
              )}
            </div>

            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap font-sans">
              {obs.observation}
            </p>
          </div>
        );
      })}
    </div>
  );
}
