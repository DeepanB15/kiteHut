export default function Loading({ text = 'Loading...' }: { text?: string }) {
  return (
    <div className="flex items-center justify-center p-8">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mr-3" />
      <span className="text-gray-600">{text}</span>
    </div>
  );
}
