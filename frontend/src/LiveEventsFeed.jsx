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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={onBack} className="btn-secondary">
          Back to orders
        </button>
        <button onClick={fetchEvents} className="btn-secondary">
          Refresh feed
        </button>
      </div>

      <div className="desk-panel" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-line)' }}>
          <h1 style={{ fontSize: '18px', fontWeight: '700' }}>Live operational event stream</h1>
          <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
            Real-time feed merging carrier webhook tracking updates and user plan authorizations.
          </p>
        </div>

        {error ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-risk-high)' }}>
            {error}
          </div>
        ) : loading ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
            Loading events...
          </div>
        ) : events.length === 0 ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
            No operational events recorded yet.
          </div>
        ) : (
          <table className="ops-table">
            <thead>
              <tr>
                <th style={{ width: '150px' }}>Timestamp</th>
                <th style={{ width: '90px' }}>Source</th>
                <th>Event summary</th>
                <th style={{ width: '120px' }}>Actor</th>
                <th>Payload / details</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, idx) => (
                <tr key={ev.id || idx}>
                  <td className="num" style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                    {ev.timestamp}
                  </td>
                  <td>
                    <span className="severity-pill severity-pill-none">
                      {ev.category}
                    </span>
                  </td>
                  <td style={{ fontWeight: '500', color: 'var(--color-ink)' }}>
                    {ev.title}
                  </td>
                  <td>
                    <span style={{ color: 'var(--color-muted-ink)' }}>{ev.actor}</span>
                  </td>
                  <td className="num" style={{ fontSize: '12px', color: 'var(--color-muted-ink)', maxWidth: '320px' }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {typeof ev.details === 'object' ? JSON.stringify(ev.details) : String(ev.details || '—')}
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
