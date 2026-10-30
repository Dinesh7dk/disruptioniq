import React, { useState, useEffect } from 'react';
import { apiFetch } from './api';

export default function LiveEventsFeed({ onBack }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchEvents();
  }, []);

  const fetchEvents = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiFetch('/events/recent?limit=50');
      if (!res.ok) {
        throw new Error(`Failed to load event feed (HTTP ${res.status})`);
      }
      const data = await res.json();
      setEvents(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={onBack} className="btn-secondary">
          ← Back to Dashboard
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className="kpi-label">Live Operational Event Stream</span>
          <button onClick={fetchEvents} className="btn-secondary" style={{ padding: '4px 10px' }}>
            Refresh Feed
          </button>
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

      <div className="surface" style={{ padding: '0', overflow: 'hidden' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Channel</th>
              <th>Event Title</th>
              <th>Actor / Source</th>
              <th>Payload / Notes</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              [1, 2, 3, 4, 5].map((n) => (
                <tr key={n}>
                  <td colSpan="5"><div className="skeleton" style={{ height: '24px', width: '100%' }} /></td>
                </tr>
              ))
            ) : events.length === 0 ? (
              <tr>
                <td colSpan="5" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                  No operational events recorded yet.
                </td>
              </tr>
            ) : (
              events.map((ev, idx) => (
                <tr key={ev.id || idx}>
                  <td className="mono" style={{ whiteSpace: 'nowrap', fontSize: '11px', color: 'var(--text-muted)' }}>
                    {ev.timestamp}
                  </td>
                  <td>
                    <span className={`badge ${ev.category === 'webhook' ? 'badge-low' : 'badge-accent'}`}>
                      {ev.category}
                    </span>
                  </td>
                  <td style={{ fontWeight: '500', color: 'var(--text-primary)' }}>
                    {ev.title}
                  </td>
                  <td>
                    <span style={{ color: 'var(--text-secondary)' }}>{ev.actor}</span>
                  </td>
                  <td className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)', maxWidth: '320px' }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {typeof ev.details === 'object' ? JSON.stringify(ev.details) : String(ev.details || '—')}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
