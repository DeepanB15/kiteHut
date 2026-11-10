import { useParams } from 'react-router-dom';
import { GitBranch, AlertTriangle, ArrowRight } from 'lucide-react';
import { useRootCauses } from '../hooks/useActions';
import Loading from '../components/common/Loading';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import { priorityColor, severityColor } from '../utils/formatters';

export default function RootCausesPage() {
  const { id } = useParams<{ id: string }>();
  const analysisId = Number(id);
  const { data, isLoading } = useRootCauses(analysisId);

  if (isLoading) return <Loading text="Analyzing root causes..." />;
  if (!data) return <ErrorState message="Failed to load root causes" />;

  const rootCauses = data.root_causes;

  if (!rootCauses || rootCauses.length === 0) {
    return <EmptyState message="No root cause groups identified for this analysis." />;
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Root Cause Analysis</h1>
        <p className="text-gray-500 text-sm mt-1">
          {rootCauses.length} root cause{rootCauses.length !== 1 ? 's' : ''} identified from related findings
        </p>
      </div>

      <div className="space-y-4">
        {rootCauses.map((rc, i) => (
          <div
            key={rc.group_id || i}
            className="bg-white border rounded-lg p-5 hover:shadow-sm transition-shadow"
          >
            <div className="flex items-start gap-4">
              {/* Icon */}
              <div className={`p-2 rounded-lg ${
                rc.severity === 'CRITICAL' || rc.severity === 'HIGH'
                  ? 'bg-red-100'
                  : rc.severity === 'MEDIUM'
                  ? 'bg-yellow-100'
                  : 'bg-blue-100'
              }`}>
                <GitBranch className={`h-5 w-5 ${
                  rc.severity === 'CRITICAL' || rc.severity === 'HIGH'
                    ? 'text-red-600'
                    : rc.severity === 'MEDIUM'
                    ? 'text-yellow-600'
                    : 'text-blue-600'
                }`} />
              </div>

              {/* Content */}
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-semibold text-gray-900">{rc.root_cause}</h3>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${priorityColor(rc.priority)}`}>
                    {rc.priority}
                  </span>
                  <span className={`text-xs font-medium ${severityColor(rc.severity)}`}>
                    {rc.severity}
                  </span>
                </div>

                <p className="text-sm text-gray-600 mb-3">{rc.description}</p>

                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span className="flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" />
                    {rc.finding_count} related finding{rc.finding_count !== 1 ? 's' : ''}
                  </span>
                  <span className="capitalize">{rc.category.replace(/_/g, ' ')}</span>
                </div>

                {/* Fix Suggestion */}
                {rc.fix_suggestion && (
                  <div className="mt-3 bg-gray-50 border rounded p-3 text-sm">
                    <div className="flex items-center gap-1 text-xs text-gray-500 mb-1 font-medium">
                      <ArrowRight className="h-3 w-3" />
                      Fix Suggestion
                    </div>
                    <p className="text-gray-700">{rc.fix_suggestion}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
