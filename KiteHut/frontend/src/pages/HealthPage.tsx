import { useParams } from 'react-router-dom';
import { Shield, Building2, Code, TestTube, Wrench } from 'lucide-react';
import { useHealthScore } from '../hooks/useActions';
import Loading from '../components/common/Loading';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import { healthColor, healthBgColor } from '../utils/formatters';

const categoryIcon = (name: string) => {
  const icons: Record<string, React.ReactNode> = {
    security: <Shield className="h-4 w-4" />,
    architecture: <Building2 className="h-4 w-4" />,
    quality: <Code className="h-4 w-4" />,
    testing: <TestTube className="h-4 w-4" />,
    maintainability: <Wrench className="h-4 w-4" />,
  };
  return icons[name] || <Code className="h-4 w-4" />;
};

export default function HealthPage() {
  const { id } = useParams<{ id: string }>();
  const analysisId = Number(id);
  const { data, isLoading } = useHealthScore(analysisId);

  if (isLoading) return <Loading text="Loading health score..." />;
  if (!data) return <ErrorState message="Failed to load health data" />;

  const health = data.health;
  if (!health) {
    return <EmptyState message="No health data available for this analysis." />;
  }

  const circumference = 2 * Math.PI * 70;
  const offset = circumference - (health.overall_score / 100) * circumference;

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Repository Health</h1>
        <p className="text-gray-500 text-sm mt-1">
          Overall health assessment based on {health.total_findings} findings
        </p>
      </div>

      <div className="grid grid-cols-3 gap-6 mb-8">
        {/* Score Circle */}
        <div className="bg-white rounded-lg border p-6 flex flex-col items-center justify-center">
          <div className="relative">
            <svg width="160" height="160">
              <circle
                cx="80"
                cy="80"
                r="70"
                fill="none"
                stroke="#e5e7eb"
                strokeWidth="12"
              />
              <circle
                cx="80"
                cy="80"
                r="70"
                fill="none"
                stroke={
                  health.overall_score >= 90
                    ? '#16a34a'
                    : health.overall_score >= 75
                    ? '#2563eb'
                    : health.overall_score >= 60
                    ? '#eab308'
                    : health.overall_score >= 40
                    ? '#f97316'
                    : '#dc2626'
                }
                strokeWidth="12"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                transform="rotate(-90 80 80)"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-4xl font-bold text-gray-900">{health.overall_score}</span>
              <span className="text-xs text-gray-500">/ 100</span>
            </div>
          </div>
          <div className={`mt-3 px-3 py-1 rounded-full text-sm font-semibold ${healthBgColor(health.health_level)} text-white`}>
            {health.health_level}
          </div>
          <p className="text-xs text-gray-500 mt-2 text-center">{health.summary}</p>
        </div>

        {/* Category Scores */}
        <div className="col-span-2 bg-white rounded-lg border p-6">
          <h3 className="font-semibold mb-4 text-gray-900">Health by Category</h3>
          <div className="space-y-4">
            {health.categories.map((cat) => (
              <div key={cat.name}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={`${healthColor(cat.name === 'security' ? 'CRITICAL' : 'GOOD')}`}>
                      {categoryIcon(cat.name)}
                    </span>
                    <span className="text-sm font-medium text-gray-700 capitalize">{cat.name}</span>
                    <span className="text-xs text-gray-400">({cat.finding_count} findings)</span>
                  </div>
                  <span className={`text-sm font-bold ${
                    cat.score >= 80 ? 'text-green-600' :
                    cat.score >= 60 ? 'text-yellow-600' :
                    cat.score >= 40 ? 'text-orange-500' :
                    'text-red-600'
                  }`}>
                    {cat.score.toFixed(0)}%
                  </span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      cat.score >= 80 ? 'bg-green-500' :
                      cat.score >= 60 ? 'bg-yellow-500' :
                      cat.score >= 40 ? 'bg-orange-500' :
                      'bg-red-500'
                    }`}
                    style={{ width: `${cat.score}%` }}
                  />
                </div>
                {cat.top_issue && (
                  <p className="text-xs text-gray-500 mt-1 ml-6">
                    Top issue: {cat.top_issue}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-semibold text-sm text-gray-500 uppercase tracking-wide mb-2">Findings Summary</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-2xl font-bold text-gray-900">{health.total_findings}</p>
              <p className="text-xs text-gray-500">Total findings</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-red-600">{health.critical_findings}</p>
              <p className="text-xs text-gray-500">Critical findings</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-semibold text-sm text-gray-500 uppercase tracking-wide mb-2">Health Levels</h3>
          <div className="grid grid-cols-5 gap-1 text-center text-xs">
            <div>
              <div className="bg-green-500 text-white rounded py-1 mb-1">90+</div>
              <p className="text-gray-500">Excellent</p>
            </div>
            <div>
              <div className="bg-blue-500 text-white rounded py-1 mb-1">75+</div>
              <p className="text-gray-500">Good</p>
            </div>
            <div>
              <div className="bg-yellow-500 text-white rounded py-1 mb-1">60+</div>
              <p className="text-gray-500">Fair</p>
            </div>
            <div>
              <div className="bg-orange-500 text-white rounded py-1 mb-1">40+</div>
              <p className="text-gray-500">Poor</p>
            </div>
            <div>
              <div className="bg-red-500 text-white rounded py-1 mb-1">0+</div>
              <p className="text-gray-500">Critical</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
