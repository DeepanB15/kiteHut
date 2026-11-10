import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { GitBranch, Calendar, ExternalLink, TrendingUp, ShieldCheck } from 'lucide-react';
import { useRepository, useRepositoryAnalyses } from '../hooks/useRepositories';
import { useQualityGateConfig, useRepositoryTrends, useUpdateQualityGate } from '../hooks/useProduct';
import Loading from '../components/common/Loading';
import ErrorState from '../components/common/ErrorState';
import { formatDate, formatDuration, statusColor } from '../utils/formatters';

// Simple SVG line chart (no chart library dependency)
function TrendChart({ values }: { values: { label: string; score: number | null }[] }) {
  const points = values.filter((v) => v.score !== null) as { label: string; score: number }[];
  if (points.length < 1) {
    return <p className="text-sm text-gray-400 py-6 text-center">No trend data yet — run at least one analysis.</p>;
  }

  const W = 560;
  const H = 180;
  const PAD = 30;

  if (points.length === 1) {
    // Single point: draw a dot at the score
    const y = H - PAD - (points[0].score / 100) * (H - 2 * PAD);
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-44">
        <circle cx={W / 2} cy={y} r={6} fill="#3b82f6" />
        <text x={W / 2 + 12} y={y + 4} fontSize="12" fill="#1f2937">
          {points[0].score.toFixed(0)}
        </text>
        <text x={W / 2 - 30} y={H - 8} fontSize="11" fill="#9ca3af">
          Run #{points[0].label}
        </text>
      </svg>
    );
  }

  const min = Math.min(...points.map((p) => p.score), 0);
  const max = Math.max(...points.map((p) => p.score), 100);
  const xStep = (W - 2 * PAD) / (points.length - 1);
  const yFor = (score: number) => H - PAD - ((score - min) / (max - min || 1)) * (H - 2 * PAD);

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${PAD + i * xStep},${yFor(p.score)}`).join(' ');
  const area = `${line} L${PAD + (points.length - 1) * xStep},${H - PAD} L${PAD},${H - PAD} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-44">
      <defs>
        <linearGradient id="healthFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#healthFill)" />
      <path d={line} fill="none" stroke="#3b82f6" strokeWidth="2.5" />
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={PAD + i * xStep} cy={yFor(p.score)} r={4} fill="#3b82f6" />
          <text x={PAD + i * xStep - 12} y={yFor(p.score) - 10} fontSize="10" fill="#1f2937">
            {p.score.toFixed(0)}
          </text>
          <text
            x={PAD + i * xStep - 20}
            y={H - 8}
            fontSize="10"
            fill="#9ca3af"
            textAnchor="middle"
          >
            #{p.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

export default function RepositoryPage() {
  const { id } = useParams<{ id: string }>();
  const repoId = Number(id);

  const { data: repo, isLoading: repoLoading } = useRepository(repoId);
  const { data: analysesData, isLoading: analysesLoading } = useRepositoryAnalyses(repoId);
  const { data: trendsData } = useRepositoryTrends(repoId);
  const { data: gateConfig, isLoading: gateLoading } = useQualityGateConfig(repoId);
  const updateGate = useUpdateQualityGate(repoId);

  const [criticalLimit, setCriticalLimit] = useState(0);
  const [securityLimit, setSecurityLimit] = useState(0);
  const [minHealth, setMinHealth] = useState(60);
  const [gateSaved, setGateSaved] = useState('');

  if (repoLoading || analysesLoading) return <Loading />;
  if (!repo) return <ErrorState message="Repository not found" />;

  const analyses = analysesData?.analyses || [];
  const trend = trendsData?.trend || [];

  const handleSaveGate = async (e: React.FormEvent) => {
    e.preventDefault();
    setGateSaved('');
    try {
      await updateGate.mutateAsync({
        critical_limit: criticalLimit,
        security_limit: securityLimit,
        min_health: minHealth,
      });
      setGateSaved('Quality gate rules saved.');
    } catch {
      setGateSaved('Failed to save quality gate rules.');
    }
  };

  const healthValues = trend.map((t) => ({
    label: String(t.analysis_run_id),
    score: t.health_score,
  }));

  // Category totals across runs (for the trend summary)
  const categoryTotals = trend.reduce(
    (acc, t) => {
      acc.security += t.security;
      acc.architecture += t.architecture;
      acc.quality += t.quality;
      acc.testing += t.testing;
      return acc;
    },
    { security: 0, architecture: 0, quality: 0, testing: 0 }
  );

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          {repo.owner}/{repo.name}
        </h1>
        <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
          <span className="flex items-center gap-1">
            <GitBranch className="h-4 w-4" />
            {repo.default_branch}
          </span>
          <a
            href={repo.github_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-blue-600 hover:underline"
          >
            <ExternalLink className="h-4 w-4" />
            GitHub
          </a>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-white rounded-lg border p-4">
          <p className="text-sm text-gray-500">First Analyzed</p>
          <p className="font-semibold">{formatDate(repo.first_analyzed_at)}</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-sm text-gray-500">Last Analyzed</p>
          <p className="font-semibold">{formatDate(repo.last_analyzed_at)}</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-sm text-gray-500">Total Analyses</p>
          <p className="font-semibold text-2xl">{repo.analysis_count}</p>
        </div>
      </div>

      {/* Phase 10: health timeline + trends */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-white rounded-lg border p-4 col-span-2">
          <h2 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-blue-500" />
            Repository Health Timeline
          </h2>
          <TrendChart values={healthValues} />
          {trend.length > 1 && (
            <p className="text-xs text-gray-500 mt-2">
              {trend[0].health_score !== null && trend[trend.length - 1].health_score !== null ? (
                trend[trend.length - 1].health_score! >= trend[0].health_score! ? (
                  <span className="text-green-600">↑ Health improving</span>
                ) : (
                  <span className="text-red-600">↓ Health declining</span>
                )
              ) : null}
            </p>
          )}
        </div>

        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-semibold text-gray-900 mb-3">Finding trends (all runs)</h3>
          <div className="space-y-2 text-sm">
            {(['security', 'architecture', 'quality', 'testing'] as const).map((cat) => (
              <div key={cat} className="flex items-center justify-between">
                <span className="capitalize text-gray-600">{cat}</span>
                <span className="font-semibold">{categoryTotals[cat]}</span>
              </div>
            ))}
            <div className="flex items-center justify-between border-t pt-2">
              <span className="text-gray-600">P0 + P1 (total)</span>
              <span className="font-semibold text-red-600">
                {trend.reduce((s, t) => s + t.p0 + t.p1, 0)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Phase 10: custom quality gate */}
      <div className="bg-white rounded-lg border p-4 mb-8">
        <h2 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-purple-500" />
          Custom Quality Gate Rules
        </h2>
        {!gateLoading && gateConfig && (
          <form onSubmit={handleSaveGate} className="flex items-end gap-4 flex-wrap">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Critical limit</label>
              <input
                type="number"
                min={0}
                value={criticalLimit}
                onChange={(e) => setCriticalLimit(Number(e.target.value))}
                className="w-24 px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Security limit</label>
              <input
                type="number"
                min={0}
                value={securityLimit}
                onChange={(e) => setSecurityLimit(Number(e.target.value))}
                className="w-24 px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Min health</label>
              <input
                type="number"
                min={0}
                max={100}
                value={minHealth}
                onChange={(e) => setMinHealth(Number(e.target.value))}
                className="w-24 px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={updateGate.isPending}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50"
            >
              {updateGate.isPending ? 'Saving...' : 'Save rules'}
            </button>
            {gateSaved && <span className="text-sm text-gray-600">{gateSaved}</span>}
            {gateConfig.uses_defaults && (
              <span className="text-xs text-gray-400">
                Currently using global defaults ({gateConfig.critical_limit ?? 0} /{' '}
                {gateConfig.security_limit ?? 0} / {gateConfig.min_health ?? 60}).
              </span>
            )}
          </form>
        )}
      </div>

      <h2 className="text-lg font-semibold mb-4">Analysis History</h2>
      {analyses.length === 0 ? (
        <p className="text-gray-500">No analyses yet.</p>
      ) : (
        <div className="space-y-3">
          {analyses.map((run) => (
            <Link
              key={run.id}
              to={`/analyses/${run.id}`}
              className="block bg-white rounded-lg border p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-semibold">Run #{run.id}</span>
                  <span className={`ml-3 px-2 py-0.5 rounded text-xs font-medium ${statusColor(run.status)}`}>
                    {run.status}
                  </span>
                  <span className="ml-3 text-xs text-gray-400 capitalize">{run.mode}</span>
                </div>
                <div className="text-sm text-gray-500 flex items-center gap-4">
                  <span>{run.total_findings} findings</span>
                  <span>{formatDuration(run.duration_seconds)}</span>
                  <span className="flex items-center gap-1">
                    <Calendar className="h-4 w-4" />
                    {formatDate(run.created_at)}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}