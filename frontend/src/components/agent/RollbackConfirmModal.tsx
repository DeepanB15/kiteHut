import { AlertOctagon, RotateCcw, X, Loader2 } from 'lucide-react';

interface RollbackConfirmModalProps {
  isOpen: boolean;
  taskId: string;
  contextFiles?: string[];
  isRollingBack?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export default function RollbackConfirmModal({
  isOpen,
  taskId,
  contextFiles = [],
  isRollingBack = false,
  onConfirm,
  onClose,
}: RollbackConfirmModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-fade-in">
      <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-md w-full overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 bg-red-50 border-b border-red-100 flex items-center justify-between">
          <div className="flex items-center gap-2 text-red-700">
            <AlertOctagon className="w-5 h-5" />
            <h3 className="text-base font-bold">Rollback Task Workspace</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isRollingBack}
            className="text-gray-400 hover:text-gray-600 p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          <p className="text-sm text-gray-700">
            Are you sure you want to revert all filesystem modifications created by Task{' '}
            <span className="font-mono font-bold text-gray-900">{taskId}</span>?
          </p>

          {contextFiles.length > 0 && (
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 block mb-1">
                Affected Context Files ({contextFiles.length})
              </span>
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 max-h-36 overflow-y-auto space-y-1">
                {contextFiles.map((file, idx) => (
                  <div key={idx} className="text-xs font-mono text-gray-700 truncate">
                    {file}
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-xs text-red-600 font-medium">
            This will restore the pre-task snapshot. Any uncommitted code changes in these files will be reverted to their baseline snapshot state.
          </p>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={isRollingBack}
            className="px-4 py-2 bg-white border border-gray-300 text-gray-700 hover:bg-gray-100 rounded-lg text-sm font-medium transition-colors"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={onConfirm}
            disabled={isRollingBack}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold flex items-center gap-2 shadow-xs transition-colors disabled:opacity-50"
          >
            {isRollingBack ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RotateCcw className="w-4 h-4" />
            )}
            {isRollingBack ? 'Restoring Snapshot...' : 'Confirm Rollback'}
          </button>
        </div>
      </div>
    </div>
  );
}
