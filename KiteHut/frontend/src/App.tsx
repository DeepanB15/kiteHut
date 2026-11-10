import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PageLayout from './components/layout/PageLayout';
import AnalyzePage from './pages/AnalyzePage';
import AnalysisProgressPage from './pages/AnalysisProgressPage';
import GithubPage from './pages/GithubPage';
import PrAnalysisResultPage from './pages/PrAnalysisResultPage';
import RepositoriesPage from './pages/RepositoriesPage';
import RepositoryPage from './pages/RepositoryPage';
import AnalysisDashboard from './pages/AnalysisDashboard';
import FindingsPage from './pages/FindingsPage';
import FindingDetailPage from './pages/FindingDetailPage';
import ComparisonPage from './pages/ComparisonPage';
import ActionsPage from './pages/ActionsPage';
import HealthPage from './pages/HealthPage';
import RootCausesPage from './pages/RootCausesPage';
import AgentConsolePage from './pages/AgentConsolePage';
import GuardianMonitoringPage from './pages/GuardianMonitoringPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <PageLayout>
          <Routes>
            <Route path="/" element={<AnalyzePage />} />
            <Route path="/jobs/:jobId" element={<AnalysisProgressPage />} />
            <Route path="/repositories" element={<RepositoriesPage />} />
            <Route path="/github" element={<GithubPage />} />
            <Route path="/pr-analyses/:id" element={<PrAnalysisResultPage />} />
            <Route path="/repositories/:id" element={<RepositoryPage />} />
            <Route path="/analyses/:id" element={<AnalysisDashboard />} />
            <Route path="/analyses/:id/findings" element={<FindingsPage />} />
            <Route path="/analyses/:id/compare" element={<ComparisonPage />} />
            <Route path="/findings/:id" element={<FindingDetailPage />} />
            <Route path="/analyses/:id/actions" element={<ActionsPage />} />
            <Route path="/analyses/:id/health" element={<HealthPage />} />
            <Route path="/analyses/:id/root-causes" element={<RootCausesPage />} />
            <Route path="/analyze-actions" element={<ActionsPage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/root-causes" element={<RootCausesPage />} />
            <Route path="/agent" element={<AgentConsolePage />} />
            <Route path="/agent/:taskId" element={<AgentConsolePage />} />
            <Route path="/monitoring" element={<GuardianMonitoringPage />} />
          </Routes>
        </PageLayout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
