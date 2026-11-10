import { useParams, Link } from 'react-router-dom';
import { ExternalLink, MessageSquare, AlertCircle, CheckCircle2, ShieldCheck } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { usePrAnalysis } from '../hooks/useGithub';
import { updatePrFindingStatus } from '../api/analyses';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import { formatDate, priorityColor, severityColor, findingStatusColor } from '../utils/formatters';
import { FINDING_STATUSES } from '../types/product';
import type { PrFinding } from '../types/pr';

const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

export default function PrAnalysisResultPage() {
  const { id } = useParams<{ id: string }>();
  const prAnalysisId = Number(id);
  const queryClient = useQueryClient();
  const { data, isLoading } = usePrAnalysis(prAnalysisId);

  const handleStatusChange = async (finding: PrFinding, status: string) => {
    await updatePrFindingStatus(finding.id, status);
    queryClient.invalidateQueries({ queryKey: ['prAnalysis', prAnalysisId] });
  };


  if (isLoading) return <Loading text="Loading PR analysis..." />;

  if (!data) {
    return <EmptyState message="PR analysis not found." />;
  }

  const findings = [...data.findings].sort(
    (a, b) =>
      SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
      (a.line_start ?? 0) - (b.line_start ?? 0)
  );

  const counts = SEVERITY_ORDER.map((severity) => ({
    severity,
    count: findings.filter((f) => f.severity === severity).length,
  })).filter((c) => c.count > 0);

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-bold text-gray-900">
              PR #{data.pull_number} Analysis
            </h1>
            {data.comment_posted && (
              <span className="inline-flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                <MessageSquare className="h-3 w-3" />
                Comment posted
              </span>
            )}
            {data.status_check_posted && (
              <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
                <ShieldCheck className="h-3 w-3" />
                Status check posted
              </span>
            )}
          </div>
          <p className="text-gray-600">{data.pr_title || 'Untitled pull request'}</p>
          <p className="text-xs text-gray-400 mt-1">
            Analyzed {formatDate(data.created_at)}
          </p>
        </div>
        {data.pr_url && (
          <a
            href={data.pr_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700 font-medium"
          >
            View on GitHub <ExternalLink className="h-4 w-4" />
          </a>
        )}
      </div>

      {/* Quality gate */}
      {data.gate_result && (
        data.gate_result === 'PASS' ? (
          <div className="mb-6 flex items-start gap-2 bg-green-50 border border-green-200 rounded-lg p-4 text-green-800">
            <CheckCircle2 className="h-5 w-5 shrink-0" />
            <div>
              <p className="font-semibold">🟢 Quality gate: PASS</p>
              <p className="text-sm">No critical or security issues in the changed code.</p>
            </div>
          </div>
        ) : (
          <div className="mb-6 flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
            <AlertCircle className="h-5 w-5 shrink-0" />
            <div>
              <p className="font-semibold">🔴 Quality gate: FAIL</p>
              <ul className="text-sm list-disc list-inside mt-1 space-y-0.5">
                {(data.gate_reasons ?? []).map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          </div>
        )
      )}

      {/* Summary chips */}
      <div className="flex gap-3 mb-6 flex-wrap">
        <span className="px-3 py-1.5 bg-gray-100 rounded-lg text-sm font-medium text-gray-700">
          {data.findings_count} finding{data.findings_count === 1 ? '' : 's'}
        </span>
        {counts.map((c) => (
          <span
            key={c.severity}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium ${severityColor(c.severity)} bg-gray-50 border`}
          >
            {c.severity.toLowerCase()}: {c.count}
          </span>
        ))}
      </div>

      {data.status === 'FAILED' && (
        <div className="mb-6 flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <div>
            <p className="font-medium">Analysis failed</p>
            <p className="text-sm">{data.error_message}</p>
          </div>
        </div>
      )}

      {/* Findings */}
      {findings.length === 0 ? (
        <EmptyState message="No issues detected in this pull request's changes." />
      ) : (
        <div className="space-y-3">
          {findings.map((finding) => (
            <div key={finding.id} className="bg-white rounded-lg border p-4">
              <div className="flex items-center gap-3 mb-2">
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${priorityColor(finding.priority)}`}>
                  {finding.priority}
                </span>
                <span className={`font-semibold text-sm ${severityColor(finding.severity)} uppercase`}>
                  {finding.severity}
                </span>
                <span className="font-medium text-gray-900 text-sm capitalize">
                  {finding.category.replace(/_/g, ' ')}
                </span>
                <span className="ml-auto text-xs text-gray-400 font-mono">
                  {finding.file_path}
                  {finding.line_start ? `:${finding.line_start}` : ''}
                </span>
              </div>

              <p className="text-sm text-gray-800 mb-2">{finding.message}</p>

              {finding.code_snippet && (
                <pre className="text-xs bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto mb-2">
                  {finding.code_snippet}
                </pre>
              )}

              {finding.recommendation && (
                <p className="text-xs text-gray-500">
                  <span className="font-medium text-gray-600">Recommended: </span>
                  {finding.recommendation}
                </p>
              )}
              <div className="flex items-center justify-between mt-2">
                <p className="text-xs text-gray-400">
                  Confidence: {finding.confidence.toFixed(0)}% · Source: {finding.source}
                </p>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${findingStatusColor(finding.status)}`}>
                    {finding.status.replace(/_/g, ' ')}
                  </span>
                  <select
                    value=""
                    onChange={(e) => e.target.value && handleStatusChange(finding, e.target.value)}
                    className="px-2 py-1 border border-gray-300 rounded-lg text-xs"
                  >
                    <option value="">Set status…</option>
                    {FINDING_STATUSES.map((s) => (
                      <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-6">
        <Link to="/github" className="text-blue-600 hover:underline text-sm">
          ← Back to GitHub overview
        </Link>
      </div>
    </div>
  );
}