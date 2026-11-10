import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Plus, CheckCircle, Minus, RefreshCw } from 'lucide-react';
import { useComparison } from '../hooks/useAnalysis';
import Loading from '../components/common/Loading';
import ErrorState from '../components/common/ErrorState';
import { priorityColor } from '../utils/formatters';

export default function ComparisonPage() {
  const { id } = useParams<{ id: string }>();
  const analysisId = Number(id);

  const { data: comparison, isLoading } = useComparison(analysisId);

  if (isLoading) return <Loading text="Loading comparison..." />;
  if (!comparison) return <ErrorState message="No previous analysis found for comparison" />;

  const { summary } = comparison;

  return (
    <div>
      <Link
        to={`/analyses/${analysisId}`}
        className="text-blue-600 hover:underline text-sm mb-4 inline-flex items-center gap-1"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Analysis
      </Link>

      <h1 className="text-2xl font-bold text-gray-900 mb-6">Change Intelligence</h1>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
          <Plus className="h-6 w-6 text-green-600 mx-auto mb-2" />
          <p className="text-3xl font-bold text-green-600">{summary.new}</p>
          <p className="text-sm text-green-700">New</p>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-center">
          <CheckCircle className="h-6 w-6 text-blue-600 mx-auto mb-2" />
          <p className="text-3xl font-bold text-blue-600">{summary.resolved}</p>
          <p className="text-sm text-blue-700">Resolved</p>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-center">
          <Minus className="h-6 w-6 text-gray-600 mx-auto mb-2" />
          <p className="text-3xl font-bold text-gray-600">{summary.existing}</p>
          <p className="text-sm text-gray-700">Existing</p>
        </div>
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-center">
          <RefreshCw className="h-6 w-6 text-yellow-600 mx-auto mb-2" />
          <p className="text-3xl font-bold text-yellow-600">{summary.changed}</p>
          <p className="text-sm text-yellow-700">Changed</p>
        </div>
      </div>

      {/* New Findings */}
      {comparison.new_findings.length > 0 && (
        <div className="mb-6">
          <h2 className="font-semibold text-green-700 mb-3 flex items-center gap-2">
            <Plus className="h-5 w-5" />
            New Findings ({comparison.new_findings.length})
          </h2>
          <div className="space-y-2">
            {comparison.new_findings.map((f) => (
              <div key={f.id} className="bg-green-50 border border-green-200 rounded-lg p-3">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${priorityColor(f.priority)}`}>
                    {f.priority}
                  </span>
                  <span className="font-medium">{f.claim_type.replace(/_/g, ' ')}</span>
                </div>
                <p className="text-sm text-gray-600 mt-1">{f.statement}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Resolved Findings */}
      {comparison.resolved_findings.length > 0 && (
        <div className="mb-6">
          <h2 className="font-semibold text-blue-700 mb-3 flex items-center gap-2">
            <CheckCircle className="h-5 w-5" />
            Resolved Findings ({comparison.resolved_findings.length})
          </h2>
          <div className="space-y-2">
            {comparison.resolved_findings.map((f) => (
              <div key={f.id} className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${priorityColor(f.priority)}`}>
                    {f.priority}
                  </span>
                  <span className="font-medium line-through text-gray-500">
                    {f.claim_type.replace(/_/g, ' ')}
                  </span>
                </div>
                <p className="text-sm text-gray-500 mt-1">{f.statement}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Changed Findings */}
      {comparison.changed_findings.length > 0 && (
        <div className="mb-6">
          <h2 className="font-semibold text-yellow-700 mb-3 flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Changed Findings ({comparison.changed_findings.length})
          </h2>
          <div className="space-y-2">
            {comparison.changed_findings.map((item: any, idx: number) => (
              <div key={idx} className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium">{item.fingerprint}</span>
                </div>
                <div className="text-sm text-gray-600">
                  {item.changes?.map((c: string, i: number) => (
                    <span key={i} className="block">{c}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Existing Findings */}
      {comparison.existing_findings.length > 0 && (
        <div>
          <h2 className="font-semibold text-gray-600 mb-3">
            Existing Findings ({comparison.existing_findings.length})
          </h2>
          <p className="text-sm text-gray-500">
            {comparison.existing_findings.length} findings remain unchanged between analyses.
          </p>
        </div>
      )}
    </div>
  );
}
