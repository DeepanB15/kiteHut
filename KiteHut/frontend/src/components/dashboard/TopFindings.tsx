import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import type { FindingSummary } from '../../types/analysis';
import { priorityColor } from '../../utils/formatters';

export default function TopFindings({ findings }: { findings: FindingSummary[] }) {
  if (findings.length === 0) return null;

  return (
    <div className="bg-white rounded-lg border p-4">
      <h3 className="font-semibold mb-3 flex items-center gap-2">
        <AlertTriangle className="h-5 w-5 text-orange-500" />
        Top Priority Findings
      </h3>
      <div className="space-y-2">
        {findings.slice(0, 5).map((f) => (
          <Link
            key={f.id}
            to={`/findings/${f.id}`}
            className="flex items-center gap-3 p-2 rounded hover:bg-gray-50"
          >
            <span className={`px-2 py-0.5 rounded text-xs font-bold ${priorityColor(f.priority)}`}>
              {f.priority}
            </span>
            <span className="text-sm text-gray-900 flex-1 truncate">{f.statement}</span>
            <span className="text-xs text-gray-500">{f.final_score.toFixed(0)}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
