import { Link } from 'react-router-dom';
import { CheckCircle2, XCircle, GitPullRequest, ShieldCheck, MessageSquare, Webhook } from 'lucide-react';
import { useGithubStatus, usePrAnalyses } from '../hooks/useGithub';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import { formatDate } from '../utils/formatters';

function StatusRow({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail: string;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-2">
        {ok ? (
          <CheckCircle2 className="h-4 w-4 text-green-500" />
        ) : (
          <XCircle className="h-4 w-4 text-red-400" />
        )}
        <span className="text-sm font-medium text-gray-700">{label}</span>
      </div>
      <span className="text-sm text-gray-500">{detail}</span>
    </div>
  );
}

export default function GithubPage() {
  const { data: status, isLoading } = useGithubStatus();
  const { data: prData, isLoading: prLoading } = usePrAnalyses();

  if (isLoading) return <Loading text="Checking GitHub connection..." />;

  const remaining = status?.rate_limit?.remaining;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <GitPullRequest className="h-6 w-6 text-gray-700" />
        <h1 className="text-2xl font-bold text-gray-900">GitHub Integration</h1>
      </div>

      {/* Connection card */}
      <div className="bg-white rounded-xl shadow p-6 mb-6">
        <h2 className="font-semibold text-gray-900 mb-4">Connection status</h2>
        <StatusRow
          label="Authenticated"
          ok={!!status?.authenticated}
          detail={status?.authenticated ? `Connected as @${status.username}` : 'No token'}
        />
        {status?.rate_limit && (
          <StatusRow
            label="API rate limit"
            ok={(remaining ?? 0) > 10}
            detail={`${remaining ?? 0} / ${status.rate_limit.limit} requests remaining`}
          />
        )}
        <StatusRow
          label="Webhook receiver"
          ok={!!status?.webhook_secret_configured}
          detail={status?.webhook_secret_configured ? 'Configured' : 'GITHUB_WEBHOOK_SECRET not set'}
        />
        <StatusRow
          label="PR comments"
          ok={!!status?.pr_comments_enabled}
          detail={status?.pr_comments_enabled ? 'Enabled' : 'Disabled'}
        />
        <StatusRow
          label="Status checks"
          ok={!!status?.status_checks_enabled}
          detail={status?.status_checks_enabled ? 'Enabled' : 'Disabled'}
        />
        {status?.message && (
          <p className="mt-4 text-xs text-gray-500 bg-gray-50 rounded-lg p-3">{status.message}</p>
        )}
      </div>

      {/* Recent PR analyses */}
      <div className="bg-white rounded-xl shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-gray-900">Recent pull request analyses</h2>
          <Link to="/" className="text-blue-600 hover:underline text-sm">
            Analyze a PR →
          </Link>
        </div>

        {prLoading ? (
          <Loading text="Loading..." />
        ) : !prData?.pr_analyses?.length ? (
          <EmptyState message="No pull requests analyzed yet." />
        ) : (
          <div className="space-y-2">
            {prData.pr_analyses.slice(0, 10).map((pr) => (
              <Link
                key={pr.id}
                to={`/pr-analyses/${pr.id}`}
                className="flex items-center gap-3 border border-gray-100 rounded-lg px-4 py-3 hover:shadow-md transition-shadow"
              >
                <GitPullRequest className="h-4 w-4 text-gray-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    #{pr.pull_number} {pr.pr_title || ''}
                  </p>
                  <p className="text-xs text-gray-400">{formatDate(pr.created_at)}</p>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  {pr.gate_result && (
                    <span
                      className={`px-1.5 py-0.5 rounded font-semibold ${
                        pr.gate_result === 'PASS'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {pr.gate_result}
                    </span>
                  )}
                  {pr.comment_posted && (
                    <span className="inline-flex items-center gap-1 text-green-600">
                      <MessageSquare className="h-3 w-3" /> posted
                    </span>
                  )}
                  <span className="font-semibold text-gray-700">
                    {pr.findings_count} findings
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Setup hints */}
      <div className="bg-white rounded-xl shadow p-6 mt-6">
        <h2 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-gray-500" /> Setup
        </h2>
        <ul className="text-sm text-gray-600 space-y-2">
          <li>
            1. Create a GitHub{' '}
            <span className="font-mono text-xs bg-gray-100 px-1 rounded">fine-grained PAT</span>{' '}
            (repo read + issues write) and set{' '}
            <span className="font-mono text-xs bg-gray-100 px-1 rounded">GITHUB_TOKEN</span>.
          </li>
          <li>
            2. For automatic triggers, expose the webhook receiver and set{' '}
            <span className="font-mono text-xs bg-gray-100 px-1 rounded">GITHUB_WEBHOOK_SECRET</span>.
          </li>
          <li className="flex items-center gap-2 text-gray-400">
            <Webhook className="h-4 w-4" />
            See docs/GITHUB_INTEGRATION.md for the full guide.
          </li>
        </ul>
      </div>
    </div>
  );
}