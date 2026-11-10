import { useParams, Link } from 'react-router-dom';
import { FileText, GitCompare, Zap, Heart, GitBranch, Download } from 'lucide-react';
import { useAnalysis, useAnalysisFindings } from '../hooks/useAnalysis';
import { reportUrl } from '../api/analyses';
import Loading from '../components/common/Loading';
import ErrorState from '../components/common/ErrorState';
import StatsCard from '../components/dashboard/StatsCard';
import PriorityChart from '../components/dashboard/PriorityChart';
import TopFindings from '../components/dashboard/TopFindings';
import { formatDate } from '../utils/formatters';

export default function AnalysisDashboard() {
  const { id } = useParams<{ id: string }>();
  const analysisId = Number(id);

  const { data: analysis, isLoading } = useAnalysis(analysisId);
  const { data: findingsData } = useAnalysisFindings(analysisId);

  if (isLoading) return <Loading text="Loading analysis..." />;
  if (!analysis) return <ErrorState message="Analysis not found" />;

  const findings = findingsData?.findings || [];
  const verifiedCount = findings.filter(
    (f) => f.truth_value === 'TRUE' || f.truth_value === 'LIKELY_TRUE'
  ).length;
  const avgConfidence =
    findings.length > 0
      ? (findings.reduce((sum, f) => sum + f.confidence, 0) / findings.length).toFixed(0)
      : '0';
  const p0Count = findings.filter((f) => f.priority === 'P0').length;
  const p1Count = findings.filter((f) => f.priority === 'P1').length;

  // Category breakdown
  const categories: Record<string, number> = {};
  findings.forEach((f) => {
    categories[f.category] = (categories[f.category] || 0) + 1;
  });

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analysis #{analysis.id}</h1>
          <p className="text-gray-500 text-sm">
            {formatDate(analysis.created_at)} &middot; {analysis.status}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {/* Phase 10: report downloads */}
          <div className="flex items-center gap-1 border border-gray-200 rounded-lg px-2">
            <Download className="h-4 w-4 text-gray-500 ml-1" />
            {(['md', 'json', 'pdf'] as const).map((format, i) => (
              <a
                key={format}
                href={reportUrl(analysisId, format)}
                className={`px-2.5 py-2 text-sm font-medium text-gray-600 hover:text-blue-600 ${
                  i > 0 ? 'border-l border-gray-200' : ''
                }`}
              >
                {format.toUpperCase()}
              </a>
            ))}
          </div>
          <Link
            to={`/analyses/${analysisId}/findings`}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 flex items-center gap-2"
          >
            <FileText className="h-4 w-4" />
            View Findings
          </Link>
          <Link
            to={`/analyses/${analysisId}/compare`}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 flex items-center gap-2"
          >
            <GitCompare className="h-4 w-4" />
            Compare
          </Link>
          <Link
            to={`/analyses/${analysisId}/actions`}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 flex items-center gap-2"
          >
            <Zap className="h-4 w-4" />
            Actions
          </Link>
          <Link
            to={`/analyses/${analysisId}/health`}
            className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 flex items-center gap-2"
          >
            <Heart className="h-4 w-4" />
            Health
          </Link>
          <Link
            to={`/analyses/${analysisId}/root-causes`}
            className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 flex items-center gap-2"
          >
            <GitBranch className="h-4 w-4" />
            Root Causes
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatsCard label="Total Findings" value={findings.length} />
        <StatsCard
          label="Critical (P0+P1)"
          value={p0Count + p1Count}
          color="text-red-600"
        />
        <StatsCard
          label="Verified"
          value={verifiedCount}
          color="text-green-600"
        />
        <StatsCard
          label="Avg Confidence"
          value={`${avgConfidence}%`}
          color="text-blue-600"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <PriorityChart distribution={analysis.priority_distribution} />

        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-semibold mb-3">Findings by Category</h3>
          <div className="space-y-2">
            {Object.entries(categories).map(([cat, count]) => (
              <div key={cat} className="flex items-center gap-3">
                <span className="text-sm text-gray-700 w-32 capitalize">
                  {cat.replace(/_/g, ' ')}
                </span>
                <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
                  <div
                    className="bg-blue-500 h-full rounded-full"
                    style={{
                      width: `${(count / findings.length) * 100}%`,
                    }}
                  />
                </div>
                <span className="text-sm font-medium text-gray-600 w-8 text-right">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top Findings */}
      <TopFindings findings={findings} />
    </div>
  );
}
