import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, GitPullRequest, Loader2, Settings2 } from 'lucide-react';
import { analyzeRepository } from '../api/analyses';
import { analyzePullRequest } from '../api/github';
import {
  AGENT_NAMES,
  ANALYSIS_MODES,
  type AnalysisMode,
  type AgentName,
} from '../types/product';

type Mode = 'repo' | 'pr';

const MODE_DESCRIPTIONS: Record<AnalysisMode, string> = {
  fast: 'Security-focused scan, no AI recon — quickest',
  balanced: 'All agents with AI recon — recommended',
  deep: 'All agents with AI recon — most thorough',
};

export default function AnalyzePage() {
  const [mode, setMode] = useState<Mode>('repo');
  const [url, setUrl] = useState('');
  const [pullNumber, setPullNumber] = useState('');
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('balanced');
  const [selectedAgents, setSelectedAgents] = useState<AgentName[]>(['architecture', 'security', 'quality', 'testing']);
  const [customAgents, setCustomAgents] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const toggleAgent = (agent: AgentName) => {
    setSelectedAgents((prev) =>
      prev.includes(agent) ? prev.filter((a) => a !== agent) : [...prev, agent]
    );
  };

  const resetMode = (nextMode: AnalysisMode) => {
    setAnalysisMode(nextMode);
    setCustomAgents(false);
    if (nextMode === 'fast') {
      setSelectedAgents(['security']);
    } else {
      setSelectedAgents([...AGENT_NAMES]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;

    const repoUrl = url.trim();
    const number = Number(pullNumber);

    if (!repoUrl) return;
    if (mode === 'pr' && (!pullNumber.trim() || !Number.isInteger(number) || number < 1)) {
      setError('Enter a valid pull request number.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      if (mode === 'pr') {
        const job = await analyzePullRequest(repoUrl, number);
        navigate(`/jobs/${job.job_id}`);
      } else {
        const job = await analyzeRepository(repoUrl, {
          mode: analysisMode,
          enabled_agents: customAgents ? selectedAgents : null,
        });
        navigate(`/jobs/${job.job_id}`);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Analysis failed. Please check the URL.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto mt-16">
      <div className="text-center mb-10">
        <h1 className="text-4xl font-bold text-gray-900 mb-3">RepoLens</h1>
        <p className="text-gray-600 text-lg">AI-Powered Repository Intelligence</p>
      </div>

      <div className="bg-white rounded-xl shadow-lg p-8">
        {/* Mode tabs */}
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-6">
          <button
            type="button"
            onClick={() => { setMode('repo'); setError(''); }}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              mode === 'repo' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Search className="h-4 w-4" />
            Repository analysis
          </button>
          <button
            type="button"
            onClick={() => { setMode('pr'); setError(''); }}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              mode === 'pr' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <GitPullRequest className="h-4 w-4" />
            Pull request analysis
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              GitHub Repository URL
            </label>
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              disabled={loading}
            />
          </div>

          {mode === 'pr' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Pull Request Number
              </label>
              <input
                type="number"
                min={1}
                value={pullNumber}
                onChange={(e) => setPullNumber(e.target.value)}
                placeholder="e.g. 42"
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                disabled={loading}
              />
            </div>
          )}

          {/* Phase 10: analysis settings (repository analyses only) */}
          {mode === 'repo' && (
            <div className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <Settings2 className="h-4 w-4 text-gray-500" />
                <span className="text-sm font-semibold text-gray-700">Analysis settings</span>
              </div>

              {/* Mode preset */}
              <div className="flex gap-2 mb-3">
                {ANALYSIS_MODES.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => resetMode(m)}
                    title={MODE_DESCRIPTIONS[m]}
                    className={`flex-1 px-3 py-2 rounded-lg border text-sm font-medium capitalize transition-colors ${
                      analysisMode === m && !customAgents
                        ? 'border-blue-500 bg-blue-50 text-blue-700'
                        : 'border-gray-200 text-gray-600 hover:border-gray-300'
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-400 mb-3">
                {MODE_DESCRIPTIONS[analysisMode]}
              </p>

              {/* Custom agent selection */}
              <label className="flex items-center gap-2 text-sm text-gray-600 mb-2">
                <input
                  type="checkbox"
                  checked={customAgents}
                  onChange={(e) => setCustomAgents(e.target.checked)}
                  className="rounded"
                />
                Choose agents manually
              </label>
              {customAgents && (
                <div className="flex gap-3 flex-wrap">
                  {AGENT_NAMES.map((agent) => (
                    <label key={agent} className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={selectedAgents.includes(agent)}
                        onChange={() => toggleAgent(agent)}
                        className="rounded"
                      />
                      <span className="capitalize">{agent}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !url.trim() || (mode === 'pr' && !pullNumber.trim())}
            className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : mode === 'pr' ? (
              <GitPullRequest className="h-5 w-5" />
            ) : (
              <Search className="h-5 w-5" />
            )}
            {loading
              ? 'Queuing...'
              : mode === 'pr'
              ? 'Analyze Pull Request'
              : 'Analyze Repository'}
          </button>

          {error && (
            <p className="text-red-600 text-sm">{error}</p>
          )}
        </form>
      </div>
    </div>
  );
}