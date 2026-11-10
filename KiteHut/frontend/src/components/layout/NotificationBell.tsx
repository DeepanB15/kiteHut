import { useState } from 'react';
import { Bell, CheckCheck } from 'lucide-react';
import { useNotifications, useMarkAllNotificationsRead, useMarkNotificationRead } from '../../hooks/useProduct';
import { formatDate } from '../../utils/formatters';
import { NOTIFICATION_ICONS } from '../../types/product';

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();

  const notifications = data?.notifications || [];
  const unread = data?.unread || 0;

  const handleMarkAll = async () => {
    await markAll.mutateAsync();
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded-lg hover:bg-gray-100 text-gray-600"
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-red-500 text-white text-[10px] font-bold rounded-full min-w-4 h-4 px-1 flex items-center justify-center">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          {/* Click-outside backdrop */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-96 bg-white rounded-xl shadow-lg border border-gray-100 z-20 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
              <span className="font-semibold text-gray-900 text-sm">Notifications</span>
              {unread > 0 && (
                <button
                  onClick={handleMarkAll}
                  className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                >
                  <CheckCheck className="h-3 w-3" />
                  Mark all read
                </button>
              )}
            </div>

            <div className="max-h-96 overflow-y-auto">
              {notifications.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-8">
                  No notifications yet.
                </p>
              ) : (
                notifications.map((n) => (
                  <button
                    key={n.id}
                    onClick={async () => {
                      if (!n.read) await markRead.mutateAsync(n.id);
                    }}
                    className={`w-full text-left px-4 py-3 border-b border-gray-50 hover:bg-gray-50 ${
                      n.read ? 'opacity-60' : ''
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span className="text-lg leading-none mt-0.5">
                        {NOTIFICATION_ICONS[n.kind] || '🔔'}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900">{n.title}</p>
                        <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{n.message}</p>
                        <p className="text-[11px] text-gray-400 mt-1">
                          {formatDate(n.created_at)}
                        </p>
                      </div>
                      {!n.read && <span className="w-2 h-2 rounded-full bg-blue-500 mt-1 shrink-0" />}
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}