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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={onBack} className="btn-secondary">
          Back to orders
        </button>
        {notifications.length > 0 && (
          <button onClick={handleMarkAllRead} className="btn-secondary">
            Mark all read
          </button>
        )}
      </div>

      <div className="desk-panel" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-line)' }}>
          <h1 style={{ fontSize: '18px', fontWeight: '700' }}>System notifications</h1>
          <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
            Real-time updates on carrier tracking, plan proposals, and approval requests.
          </p>
        </div>

        {error ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-risk-high)' }}>
            {error}
          </div>
        ) : loading ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
            Checking for updates...
          </div>
        ) : notifications.length === 0 ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
            No new notifications.
          </div>
        ) : (
          <table className="ops-table">
            <thead>
              <tr>
                <th style={{ width: '130px' }}>Time</th>
                <th style={{ width: '100px' }}>Category</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {notifications.map((n) => (
                <tr key={n.id} style={{ opacity: n.is_read ? 0.7 : 1 }}>
                  <td className="num" style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                    {n.created_at}
                  </td>
                  <td>
                    <span className="severity-pill severity-pill-none">
                      {n.type}
                    </span>
                  </td>
                  <td>
                    <div style={{ fontWeight: n.is_read ? '500' : '600', color: 'var(--color-ink)' }}>
                      {n.title}
                    </div>
                    <div style={{ fontSize: '13px', color: 'var(--color-muted-ink)', marginTop: '2px' }}>
                      {n.body}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
