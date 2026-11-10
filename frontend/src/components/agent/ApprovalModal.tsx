import { AlertTriangle, ShieldCheck, ShieldAlert, Check, X, Shield, Lock } from 'lucide-react';
import type { DecisionType } from '../../types/agent';

interface ApprovalModalProps {
  isOpen: boolean;
  toolName: string;
  argumentsData: Record<string, any>;
  riskCategory?: string;
  stepIndex?: number;
  onDecision: (decision: DecisionType, toolName?: string) => void;
  onClose?: () => void;
}

export default function ApprovalModal({
  isOpen,
  toolName,
  argumentsData,
  riskCategory = 'APPROVAL_REQUIRED',
  stepIndex,
  onDecision,
}: ApprovalModalProps) {
  if (!isOpen) return null;

  const getRiskBadge = () => {
    switch (riskCategory.toUpperCase()) {
      case 'SAFE':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <ShieldCheck className="w-3.5 h-3.5" /> Safe
          </span>
        );
      case 'DANGEROUS':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800 border border-red-300">
            <ShieldAlert className="w-3.5 h-3.5" /> High Risk
          </span>
        );
      case 'APPROVAL_REQUIRED':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">
            <AlertTriangle className="w-3.5 h-3.5" /> Approval Required
          </span>
        );
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-fade-in">
      <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-xl w-full overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-amber-100 text-amber-700 rounded-lg">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-900">
                Action Approval Request
              </h3>
              <p className="text-xs text-gray-500">
                {stepIndex !== undefined ? `Step ${stepIndex + 1} ` : ''}Execution paused for human permission
              </p>
            </div>
          </div>
          {getRiskBadge()}
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 block mb-1">
              Requested Tool
            </span>
            <div className="font-mono text-sm bg-gray-100 text-blue-700 font-bold px-3 py-1.5 rounded-lg inline-block border border-gray-200">
              {toolName}
            </div>
          </div>

          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 block mb-1">
              Tool Arguments & Target
            </span>
            <div className="bg-gray-950 text-gray-100 p-3 rounded-lg font-mono text-xs overflow-x-auto max-h-56 border border-gray-800">
              <pre>{JSON.stringify(argumentsData, null, 2)}</pre>
            </div>
          </div>

          <p className="text-xs text-gray-500 italic">
            Grant permission to let the Autonomous Agent proceed, or deny to block this operation.
          </p>
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 grid grid-cols-2 sm:grid-cols-4 gap-2">
          <button
            type="button"
            onClick={() => onDecision('ALLOW_ONCE', toolName)}
            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
          >
            <Check className="w-3.5 h-3.5" /> Allow Once
          </button>

          <button
            type="button"
            onClick={() => onDecision('ALLOW_FOR_TASK', toolName)}
            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
          >
            <Shield className="w-3.5 h-3.5" /> Allow Task
          </button>

          <button
            type="button"
            onClick={() => onDecision('ALLOW_FOR_REPO', toolName)}
            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
          >
            <ShieldCheck className="w-3.5 h-3.5" /> Allow Repo
          </button>

          <button
            type="button"
            onClick={() => onDecision('DENY', toolName)}
            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-white hover:bg-red-50 text-red-600 border border-red-300 rounded-lg text-xs font-semibold shadow-xs transition-colors"
          >
            <X className="w-3.5 h-3.5" /> Deny
          </button>
        </div>
      </div>
    </div>
  );
}
