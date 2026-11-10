import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  FileText,
  CheckCircle,
  XCircle,
  AlertCircle,
  Wrench,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { useFinding } from '../hooks/useFindings';
import { useRemediateFinding } from '../hooks/useAgent';
import { useQueryClient } from '@tanstack/react-query';
import { updateFindingStatus } from '../api/analyses';
import Loading from '../components/common/Loading';
import ErrorState from '../components/common/ErrorState';
import { priorityColor, truthColor, severityColor, findingStatusColor } from '../utils/formatters';
import { FINDING_STATUSES } from '../types/product';
import type { RemediationResponse } from '../types/agent';

export default function FindingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const findingId = Number(id);
  const queryClient = useQueryClient();

  const { data: finding, isLoading } = useFinding(findingId);
  const remediateMutation = useRemediateFinding();

  const [status, setStatus] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [remediationResult, setRemediationResult] = useState<RemediationResponse | null>(null);

  if (isLoading) return <Loading />;
  if (!finding) return <ErrorState message="Finding not found" />;

  const handleStatusChange = async () => {
    if (!status) return;
    setSaving(true);
    setMessage('');
    try {
      await updateFindingStatus(findingId, status, note);
      setMessage(`Status updated to ${status.replace(/_/g, ' ')}.`);
      setNote('');
      queryClient.invalidateQueries({ queryKey: ['finding', findingId] });
    } catch (err: any) {
      setMessage(err.response?.data?.detail || 'Failed to update status.');
    } finally {
      setSaving(false);
    }
  };

  const handleAutonomousRemediate = async () => {
    try {
      const result = await remediateMutation.mutateAsync({
        repository_path: '.',
        finding_id: String(findingId),
        auto_approve: true,
        run_tests: true,
      });
      setRemediationResult(result);
    } catch (err: any) {
      console.error('Autonomous remediation failed:', err);
    }
  };

  return (
    <div>
      <Link to="javascript:history.back()" className="text-blue-600 hover:underline text-sm mb-4 inline-flex items-center gap-1">
        <ArrowLeft className="h-4 w-4" />
        Back
      </Link>

      {/* Header */}
      <div className="bg-white rounded-lg border p-6 mb-6">
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-3">
            <span className={`px-3 py-1 rounded text-sm font-bold ${priorityColor(finding.priority)}`}>
              {finding.priority}
            </span>
            <h1 className="text-xl font-bold text-gray-900">
              {finding.claim_type.replace(/_/g, ' ')}
            </h1>
          </div>

          {/* Autonomous Remediation Action Button */}
          <button
            type="button"
            onClick={handleAutonomousRemediate}
            disabled={remediateMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg text-sm font-semibold shadow-xs transition-all disabled:opacity-50"
          >
            {remediateMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Wrench className="w-4 h-4" />
            )}
            {remediateMutation.isPending ? 'Executing Remediation Loop...' : 'Autonomous 1-Click Remediate'}
          </button>
        </div>
        <p className="text-gray-600 mb-4">{finding.statement}</p>

        {/* Remediation Feedback Card */}
        {remediationResult && (
          <div
            className={`p-4 rounded-xl border mb-4 ${
              remediationResult.success
                ? 'bg-emerald-50/70 border-emerald-300'
                : 'bg-red-50/70 border-red-300'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                {remediationResult.success ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                ) : (
                  <AlertCircle className="w-5 h-5 text-red-600" />
                )}
                <h3 className="text-sm font-bold text-gray-900">
                  {remediationResult.success
                    ? 'Autonomous Patch Applied & Verified'
                    : 'Remediation Failed'}
                </h3>
              </div>
              <span className="text-xs font-mono text-gray-500">
                Action ID: {remediationResult.action_id}
              </span>
            </div>

            <p className="text-xs text-gray-700 mb-2">{remediationResult.message}</p>

            {remediationResult.modified_files && remediationResult.modified_files.length > 0 && (
              <div className="mb-2">
                <span className="text-[11px] font-semibold uppercase text-gray-500 block mb-1">
                  Modified Files:
                </span>
                <div className="flex flex-wrap gap-1">
                  {remediationResult.modified_files.map((f, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded bg-white border border-gray-200 text-xs font-mono text-gray-800"
                    >
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {remediationResult.test_results && (
              <div className="bg-white p-2.5 rounded-lg border border-gray-200 text-xs flex items-center justify-between">
                <span className="font-semibold text-gray-700">Test Verification Suite:</span>
                <span
                  className={`font-bold ${
                    remediationResult.test_results.passed ? 'text-emerald-600' : 'text-red-600'
                  }`}
                >
                  {remediationResult.test_results.passed ? 'PASSED' : 'FAILED'} (
                  {remediationResult.test_results.passed_tests}/
                  {remediationResult.test_results.total_tests} tests)
                </span>
              </div>
            )}
          </div>
        )}

        {/* Phase 10: status lifecycle */}
        <div className="border-t pt-4 mt-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${findingStatusColor(finding.status)}`}>
              {finding.status.replace(/_/g, ' ')}
            </span>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
            >
              <option value="">Change status...</option>
              {FINDING_STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
              ))}
            </select>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Note (optional)"
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm flex-1 min-w-40"
            >
            </input>
            <button
              onClick={handleStatusChange}
              disabled={!status || saving}
              className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Update'}
            </button>
            {message && <span className="text-sm text-gray-600">{message}</span>}
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4 mt-6">
          <div>
            <p className="text-xs text-gray-500">Truth</p>
            <p className={`font-semibold ${truthColor(finding.truth_value)}`}>
              {finding.truth_value}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Confidence</p>
            <p className="font-semibold">{finding.confidence.toFixed(0)}%</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Final Score</p>
            <p className="font-semibold text-2xl">{finding.final_score.toFixed(0)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Severity</p>
            <p className={`font-semibold ${severityColor(finding.severity)}`}>
              {finding.severity} ({finding.severity_score.toFixed(0)})
            </p>
          </div>
        </div>
      </div>

      {/* Score Breakdown */}
      <div className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="font-semibold mb-4">Score Breakdown</h2>
        <div className="space-y-3">
          {[
            { label: 'Severity', value: finding.severity_score, color: 'bg-red-500' },
            { label: 'Impact', value: finding.overall_impact, color: 'bg-orange-500' },
            { label: 'Exploitability', value: finding.exploitability, color: 'bg-purple-500' },
            { label: 'Confidence', value: finding.confidence, color: 'bg-blue-500' },
          ].map((item) => (
            <div key={item.label} className="flex items-center gap-3">
              <span className="text-sm text-gray-600 w-28">{item.label}</span>
              <div className="flex-1 bg-gray-100 rounded-full h-5 overflow-hidden">
                <div
                  className={`${item.color} h-full rounded-full transition-all`}
                  style={{ width: `${item.value}%` }}
                />
              </div>
              <span className="text-sm font-medium w-10 text-right">{item.value.toFixed(0)}</span>
            </div>
          ))}
        </div>

        <div className="mt-4 pt-4 border-t">
          <p className="text-xs text-gray-500">
            Final = Severity(35%) + Impact(30%) + Confidence(20%) + Exploitability(15%)
          </p>
        </div>
      </div>

      {/* Impact Details */}
      <div className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="font-semibold mb-4">Impact Analysis</h2>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <p className="text-sm text-gray-500">User Impact</p>
            <p className="text-2xl font-bold">{finding.user_impact.toFixed(0)}</p>
          </div>
          <div className="text-center">
            <p className="text-sm text-gray-500">System Impact</p>
            <p className="text-2xl font-bold">{finding.system_impact.toFixed(0)}</p>
          </div>
          <div className="text-center">
            <p className="text-sm text-gray-500">Business Impact</p>
            <p className="text-2xl font-bold">{finding.business_impact.toFixed(0)}</p>
          </div>
        </div>
      </div>

      {/* Evidence */}
      <div className="bg-white rounded-lg border p-6">
        <h2 className="font-semibold mb-4 flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Evidence ({finding.evidence.length})
        </h2>
        {finding.evidence.length === 0 ? (
          <p className="text-gray-500 text-sm">No evidence collected.</p>
        ) : (
          <div className="space-y-3">
            {finding.evidence.map((ev) => (
              <div
                key={ev.id}
                className="border rounded-lg p-3 bg-gray-50"
              >
                <div className="flex items-center gap-2 mb-2">
                  {ev.relation === 'supports' ? (
                    <CheckCircle className="h-4 w-4 text-green-500" />
                  ) : ev.relation === 'contradicts' ? (
                    <XCircle className="h-4 w-4 text-red-500" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-yellow-500" />
                  )}
                  <span className="text-xs font-medium uppercase text-gray-500">
                    {ev.relation}
                  </span>
                  <span className="text-xs text-gray-400">|</span>
                  <span className="text-xs text-gray-500">{ev.source}</span>
                  <span className="text-xs text-gray-400">|</span>
                  <span className="text-xs text-gray-500">{ev.strength}</span>
                </div>
                {ev.file_path && (
                  <p className="text-xs text-blue-600 mb-1">
                    {ev.file_path}
                    {ev.line_start > 0 && ` (line ${ev.line_start})`}
                  </p>
                )}
                <pre className="text-sm text-gray-700 bg-white p-2 rounded border overflow-x-auto">
                  {ev.content}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
