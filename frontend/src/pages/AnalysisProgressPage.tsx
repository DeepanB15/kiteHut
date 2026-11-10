import { useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { CheckCircle2, Circle, Loader2, AlertCircle, ExternalLink } from 'lucide-react';
import { fetchJobStatus } from '../api/analyses';
import type { AnalysisJob } from '../types/analysis';

const REPOSITORY_STAGES = ['PENDING', 'CLONING', 'SCANNING', 'ANALYZING', 'VERIFYING', 'SCORING', 'SAVING', 'COMPLETED'];
const PR_STAGES = ['PENDING', 'FETCHING', 'ANALYZING', 'SAVING', 'COMPLETED'];

function stageLabel(stage: string): string {
  return stage.charAt(0) + stage.slice(1).toLowerCase().replace(/_/g, ' ');
}

export default function AnalysisProgressPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const status = await fetchJobStatus(jobId);
        if (cancelled) return;
        setJob(status);

        if (status.status === 'COMPLETED') {
          if (status.job_type === 'PR') {
            navigate(`/pr-analyses/${status.pr_analysis_id}`);
          } else if (status.analysis_run_id) {
            navigate(`/analyses/${status.analysis_run_id}`);
          } else {
            navigate('/repositories');
          }
        }
      } catch (err: any) {
        if (cancelled) return;
        setError(err.response?.data?.detail || 'Unable to fetch analysis status.');
      }
    };

    poll();
    const interval = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId, navigate]);

  const STAGES = job?.job_type === 'PR' ? PR_STAGES : REPOSITORY_STAGES;
  const isFailed = job?.status === 'FAILED';

  // Index of the stage currently executing (or the stage that failed)
  const statusIndex = job ? STAGES.indexOf(job.status) : 0;
  const failedStageIndex = isFailed
    ? Math.max(0, STAGES.indexOf(job.current_stage ?? 'PENDING'))
    : -1;
  const activeIndex = isFailed ? failedStageIndex : Math.max(0, statusIndex);

  const progressPercent = isFailed
    ? Math.round(((failedStageIndex + 1) / STAGES.length) * 100)
    : Math.min(100, Math.round(((statusIndex + 1) / STAGES.length) * 100));

  return (
    <div className="max-w-2xl mx-auto mt-12">
      <div className="bg-white rounded-xl shadow-lg p-8">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Repository Analysis</h1>
          {job && (
            <p className="text-gray-500 text-sm break-all">
              {job.repository_url}
            </p>
          )}
        </div>

        {error && !job && (
          <div className="flex items-center gap-2 text-red-600 bg-red-50 rounded-lg p-4">
            <AlertCircle className="h-5 w-5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {job && (
          <>
            {/* Progress bar */}
            <div className="mb-8">
              <div className="flex justify-between text-sm text-gray-500 mb-2">
                <span>{job.message || job.status}</span>
                <span>{progressPercent}%</span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-3 overflow-hidden">
                <div
                  className={`h-3 rounded-full transition-all duration-500 ${
                    isFailed ? 'bg-red-500' : 'bg-blue-600'
                  }`}
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            {/* Stage timeline */}
            <ol className="space-y-3">
              {STAGES.map((stage) => {
                const stageIndex = STAGES.indexOf(stage);
                const isComplete = job.status === 'COMPLETED' || stageIndex < activeIndex;
                const isActive = stageIndex === activeIndex;

                let icon;
                if (isFailed && stageIndex === activeIndex) {
                  icon = <AlertCircle className="h-5 w-5 text-red-500" />;
                } else if (isComplete) {
                  icon = <CheckCircle2 className="h-5 w-5 text-green-500" />;
                } else if (isActive) {
                  icon = <Loader2 className="h-5 w-5 text-blue-600 animate-spin" />;
                } else {
                  icon = <Circle className="h-5 w-5 text-gray-300" />;
                }

                return (
                  <li key={stage} className="flex items-center gap-3">
                    {icon}
                    <span
                      className={`text-sm ${
                        isComplete
                          ? 'text-gray-900 font-medium'
                          : isActive
                          ? 'text-blue-700 font-medium'
                          : 'text-gray-400'
                      }`}
                    >
                      {stageLabel(stage)}
                    </span>
                  </li>
                );
              })}
            </ol>

            {isFailed && (
              <div className="mt-8 bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex items-center gap-2 text-red-700 font-medium mb-1">
                  <AlertCircle className="h-5 w-5" />
                  Analysis failed
                </div>
                <p className="text-sm text-red-600">
                  {job.error_message || job.message || 'An unexpected error occurred.'}
                </p>
                <Link
                  to="/"
                  className="mt-4 inline-flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  Try another repository <ExternalLink className="h-4 w-4" />
                </Link>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}