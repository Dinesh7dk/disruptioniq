import React, { useState, useEffect } from 'react';
import { apiFetch } from './api';

export default function NotificationsView({ onBack }) {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchNotifications();
  }, []);

  const fetchNotifications = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiFetch('/notifications?limit=50');
      if (!res.ok) {
        throw new Error(`Failed to load notifications (HTTP ${res.status})`);
      }
      const data = await res.json();
      setNotifications(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleMarkAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
  };

  return (
    <div style={{ maxWidth: '850px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={onBack} className="btn-secondary">
          ← Back to Dashboard
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className="kpi-label">Notification Feed</span>
          {notifications.length > 0 && (
            <button onClick={handleMarkAllRead} className="btn-secondary" style={{ padding: '4px 10px' }}>
              Mark All Read
            </button>
          )}
        </div>
      </div>

      {error && (
        <div style={{
          padding: '10px 14px',
          backgroundColor: 'var(--status-high-bg)',
          border: '1px solid var(--status-high-border)',
          borderRadius: '4px',
          color: 'var(--status-high-text)',
          fontSize: '12px'
        }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {loading ? (
          [1, 2, 3].map((n) => <div key={n} className="skeleton" style={{ height: '70px', width: '100%' }} />)
        ) : notifications.length === 0 ? (
          <div className="surface" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
            No new notifications at this time.
          </div>
        ) : (
          notifications.map((n) => (
            <div
              key={n.id}
              className="surface"
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                gap: '12px',
                padding: '12px 16px',
                opacity: n.is_read ? 0.75 : 1
              }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  <span className={`badge ${n.type === 'APPROVAL' ? 'badge-accent' : 'badge-neutral'}`}>
                    {n.type}
                  </span>
                  <span style={{ fontWeight: '600', color: 'var(--text-primary)', fontSize: '13px' }}>
                    {n.title}
                  </span>
                  {!n.is_read && (
                    <span style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      backgroundColor: '#3b82f6'
                    }} />
                  )}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {n.body}
                </div>
              </div>
              <div className="mono" style={{ fontSize: '11px', color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                {n.created_at}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
