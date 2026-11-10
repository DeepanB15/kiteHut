import { Inbox } from 'lucide-react';

export default function EmptyState({ message = 'No data found' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <Inbox className="h-12 w-12 text-gray-400 mb-4" />
      <h3 className="text-lg font-semibold text-gray-900 mb-2">Empty</h3>
      <p className="text-gray-600">{message}</p>
    </div>
  );
}
