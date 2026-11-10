import { useParams } from 'react-router-dom';
import { Zap, Clock, Archive, AlertTriangle, ArrowRight } from 'lucide-react';
import { useActionPlan } from '../hooks/useActions';
import Loading from '../components/common/Loading';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import { priorityColor } from '../utils/formatters';

const effortBadge = (effort: string) => {
  const colors: Record<string, string> = {
    LOW: 'bg-green-100 text-green-800',
    MEDIUM: 'bg-yellow-100 text-yellow-800',
    HIGH: 'bg-orange-100 text-orange-800',
    VERY_HIGH: 'bg-red-100 text-red-800',
  };
  return colors[effort] || 'bg-gray-100 text-gray-800';
};

const impactBadge = (impact: string) => {
  const colors: Record<string, string> = {
    CRITICAL: 'bg-red-100 text-red-800',
    HIGH: 'bg-orange-100 text-orange-800',
    MEDIUM: 'bg-yellow-100 text-yellow-800',
    LOW: 'bg-blue-100 text-blue-800',
  };
  return colors[impact] || 'bg-gray-100 text-gray-800';
};

export default function ActionsPage() {
  const { id } = useParams<{ id: string }>();
  const analysisId = Number(id);
  const { data, isLoading } = useActionPlan(analysisId);

  if (isLoading) return <Loading text="Loading action plan..." />;
  if (!data) return <ErrorState message="Failed to load action plan" />;

  const plan = data.action_plan;
  if (!plan) {
    return <EmptyState message="No action plan available for this analysis." />;
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Developer Action Plan</h1>
        <p className="text-gray-500 text-sm mt-1">
          {plan.total_actions} actions &middot; {plan.now_count} fix now &middot; {plan.next_count} fix next &middot; {plan.later_count} improve later
        </p>
      </div>

      {/* Summary */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6 text-sm text-blue-800">
        {plan.summary}
      </div>

      {/* FIX NOW */}
      {plan.fix_now.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            <div className="bg-red-500 text-white p-1.5 rounded-lg">
              <Zap className="h-4 w-4" />
            </div>
            <h2 className="text-lg font-semibold text-red-700">Fix Now</h2>
            <span className="text-sm text-gray-500">({plan.fix_now.length})</span>
          </div>
          <div className="space-y-3">
            {plan.fix_now.map((item, i) => (
              <ActionCard key={i} item={item} borderClass="border-l-red-500" />
            ))}
          </div>
        </div>
      )}

      {/* FIX NEXT */}
      {plan.fix_next.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            <div className="bg-orange-500 text-white p-1.5 rounded-lg">
              <Clock className="h-4 w-4" />
            </div>
            <h2 className="text-lg font-semibold text-orange-700">Fix Next</h2>
            <span className="text-sm text-gray-500">({plan.fix_next.length})</span>
          </div>
          <div className="space-y-3">
            {plan.fix_next.map((item, i) => (
              <ActionCard key={i} item={item} borderClass="border-l-orange-500" />
            ))}
          </div>
        </div>
      )}

      {/* IMPROVE LATER */}
      {plan.improve_later.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            <div className="bg-blue-500 text-white p-1.5 rounded-lg">
              <Archive className="h-4 w-4" />
            </div>
            <h2 className="text-lg font-semibold text-blue-700">Improve Later</h2>
            <span className="text-sm text-gray-500">({plan.improve_later.length})</span>
          </div>
          <div className="space-y-3">
            {plan.improve_later.map((item, i) => (
              <ActionCard key={i} item={item} borderClass="border-l-blue-500" />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ActionCard({
  item,
  borderClass,
}: {
  item: {
    finding_id: string;
    claim_type: string;
    statement: string;
    priority: string;
    final_score: number;
    effort: string;
    expected_impact: string;
    blast_radius: string;
    recommendation_title: string;
    action_order: number;
  };
  borderClass: string;
}) {
  return (
    <div
      className={`bg-white border rounded-lg p-4 border-l-4 ${borderClass} hover:shadow-sm transition-shadow`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs font-bold px-2 py-0.5 rounded ${priorityColor(item.priority)}`}>
              {item.priority}
            </span>
            <span className="text-xs text-gray-500 uppercase tracking-wide">
              {item.claim_type.replace(/_/g, ' ')}
            </span>
            <span className="text-xs font-mono text-gray-400">
              Score: {item.final_score.toFixed(0)}
            </span>
          </div>
          <p className="text-sm text-gray-800 font-medium mt-1">{item.statement}</p>
          {item.recommendation_title && (
            <p className="text-xs text-blue-600 mt-1 flex items-center gap-1">
              <ArrowRight className="h-3 w-3" />
              {item.recommendation_title}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 ml-4">
          <span className={`text-xs px-2 py-0.5 rounded ${effortBadge(item.effort)}`}>
            {item.effort}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded ${impactBadge(item.expected_impact)}`}>
            {item.expected_impact}
          </span>
          {item.blast_radius && item.blast_radius !== 'low' && (
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              {item.blast_radius} blast
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
