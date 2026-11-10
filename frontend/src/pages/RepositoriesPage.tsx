import { Link } from 'react-router-dom';
import { FolderOpen, GitBranch, Calendar } from 'lucide-react';
import { useRepositories } from '../hooks/useRepositories';
import Loading from '../components/common/Loading';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import { formatDate } from '../utils/formatters';

export default function RepositoriesPage() {
  const { data, isLoading, error } = useRepositories();

  if (isLoading) return <Loading text="Loading repositories..." />;
  if (error) return <ErrorState message="Failed to load repositories" />;

  const repos = data?.repositories || [];

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Repositories</h1>

      {repos.length === 0 ? (
        <EmptyState message="No repositories analyzed yet. Go to Analyze to get started." />
      ) : (
        <div className="grid gap-4">
          {repos.map((repo) => (
            <Link
              key={repo.id}
              to={`/repositories/${repo.id}`}
              className="block bg-white rounded-lg border border-gray-200 p-5 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-3 mb-2">
                <FolderOpen className="h-5 w-5 text-blue-500" />
                <h3 className="font-semibold text-gray-900">
                  {repo.owner}/{repo.name}
                </h3>
              </div>
              <div className="flex items-center gap-4 text-sm text-gray-500">
                <span className="flex items-center gap-1">
                  <GitBranch className="h-4 w-4" />
                  {repo.default_branch}
                </span>
                <span>{repo.analysis_count} analysis(es)</span>
                {repo.last_analyzed_at && (
                  <span className="flex items-center gap-1">
                    <Calendar className="h-4 w-4" />
                    {formatDate(repo.last_analyzed_at)}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
