import { AlertCircle } from 'lucide-react';

export default function ErrorState({ message = 'Something went wrong' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <AlertCircle className="h-12 w-12 text-red-500 mb-4" />
      <h3 className="text-lg font-semibold text-gray-900 mb-2">Error</h3>
      <p className="text-gray-600">{message}</p>
    </div>
  );
}
