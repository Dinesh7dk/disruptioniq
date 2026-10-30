import React from 'react';
import { Bell, ArrowLeft, RefreshCw } from 'lucide-react';

export default function NotificationsView({ notifications, onBack, onMarkAllRead }) {
  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '24px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <button
          onClick={onBack}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'transparent',
            border: '1px solid var(--border)',
            color: 'var(--text-main)',
            padding: '8px 14px'
          }}
        >
          <ArrowLeft size={16} /> Back to Dashboard
        </button>

        <h2 style={{ fontSize: '20px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Bell size={20} color="var(--primary)" /> Notifications
        </h2>

        {notifications.length > 0 && (
          <button
            onClick={onMarkAllRead}
            style={{
              background: 'var(--bg-subtle)',
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
              padding: '6px 12px',
              fontSize: '12px'
            }}
          >
            Mark all read
          </button>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {notifications.length === 0 ? (
          <div className="card" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-dim)' }}>
            No notifications available
          </div>
        ) : (
          notifications.map((n, i) => (
            <div key={n.id || i} className="card" style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '14px',
              borderLeft: n.is_read ? '1px solid var(--border)' : '4px solid var(--primary)'
            }}>
              <div style={{
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0
              }}>
                <Bell size={16} color="var(--primary)" />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <span style={{ fontWeight: '600', color: 'var(--text-main)' }}>{n.title}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{n.created_at || 'Just now'}</span>
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{n.body}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
