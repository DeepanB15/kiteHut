import Sidebar from './Sidebar';
import NotificationBell from './NotificationBell';

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <header className="flex items-center justify-end px-6 py-3 bg-white border-b border-gray-100">
          <NotificationBell />
        </header>
        <main className="flex-1 p-6 overflow-auto">{children}</main>
      </div>
    </div>
  );
}