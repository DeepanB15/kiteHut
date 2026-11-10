import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAnalysisFindings } from '../hooks/useAnalysis';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import { priorityColor, truthColor, findingStatusColor } from '../utils/formatters';
import { FINDING_STATUSES } from '../types/product';

export default function FindingsPage() {
  const { id } = useParams<{ id: string }>();
  const analysisId = Number(id);

  const [priority, setPriority] = useState('');
  const [category, setCategory] = useState('');
  const [truthValue, setTruthValue] = useState('');
  const [status, setStatus] = useState('');

  const filters = {
    ...(priority && { priority }),
    ...(category && { category }),
    ...(truthValue && { truth_value: truthValue }),
    ...(status && { status }),
  };

  const { data, isLoading } = useAnalysisFindings(analysisId, filters);

  if (isLoading) return <Loading text="Loading findings..." />;

  const findings = data?.findings || [];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          Findings <span className="text-gray-400 text-lg">({data?.total || 0})</span>
        </h1>
        <Link
          to={`/analyses/${analysisId}`}
          className="text-blue-600 hover:underline text-sm"
        >
          Back to Dashboard
        </Link>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-6">
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          <option value="">All Priorities</option>
          <option value="P0">P0</option>
          <option value="P1">P1</option>
          <option value="P2">P2</option>
          <option value="P3">P3</option>
          <option value="P4">P4</option>
        </select>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          <option value="">All Categories</option>
          <option value="security_risk">Security</option>
          <option value="architecture_issue">Architecture</option>
          <option value="quality_issue">Quality</option>
          <option value="testing_issue">Testing</option>
        </select>
        <select
          value={truthValue}
          onChange={(e) => setTruthValue(e.target.value)}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          <option value="">All Truth Values</option>
          <option value="TRUE">TRUE</option>
          <option value="LIKELY_TRUE">LIKELY TRUE</option>
          <option value="UNCERTAIN">UNCERTAIN</option>
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          <option value="">All Statuses</option>
          {FINDING_STATUSES.map((s) => (
            <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
          ))}
        </select>
      </div>

      {findings.length === 0 ? (
        <EmptyState message="No findings match the current filters." />
      ) : (
        <div className="space-y-3">
          {findings.map((f) => (
            <Link
              key={f.id}
              to={`/findings/${f.id}`}
              className="block bg-white rounded-lg border p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-3 mb-2">
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${priorityColor(f.priority)}`}>
                  {f.priority}
                </span>
                <span className="font-semibold text-gray-900">{f.claim_type.replace(/_/g, ' ')}</span>
                <span className="text-xs text-gray-500 capitalize">{f.category.replace(/_/g, ' ')}</span>
                <span className={`ml-auto px-2 py-0.5 rounded-full text-xs font-medium ${findingStatusColor(f.status)}`}>
                  {f.status.replace(/_/g, ' ')}
                </span>
              </div>
              <p className="text-sm text-gray-600 mb-2">{f.statement}</p>
              <div className="flex items-center gap-4 text-xs text-gray-500">
                <span className={truthColor(f.truth_value)}>
                  Truth: {f.truth_value}
                </span>
                <span>Confidence: {f.confidence.toFixed(0)}%</span>
                <span>Score: {f.final_score.toFixed(0)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
