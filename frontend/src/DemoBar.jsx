import React, { useState, useEffect } from 'react';
import { apiFetch } from './api';

export default function DemoBar({ currentUser, onRoleSwitch, onActionComplete }) {
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [showFeed, setShowFeed] = useState(false);
  const [events, setEvents] = useState([]);
  const [feedLoading, setFeedLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Seeded demo users for the role switcher
  const roleUsers = [
    { username: 'admin', label: 'Administrator (admin)', role: 'Administrator' },
    { username: 'anita', label: 'Operations Analyst (anita)', role: 'Operations Analyst' },
    { username: 'meera', label: 'Supply Chain Manager (meera)', role: 'Supply Chain Manager' },
    { username: 'ravi', label: 'Warehouse Operator (ravi)', role: 'Warehouse Operator' },
    { username: 'priya', label: 'Procurement Approver (priya)', role: 'Procurement Approver' },
  ];

  const isVisible = currentUser?.role === 'Administrator' && currentUser?.demo_mode;

  useEffect(() => {
    let interval = null;
    if (showFeed && isVisible) {
      fetchEvents();
      if (autoRefresh) {
        interval = setInterval(fetchEvents, 4000);
      }
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [showFeed, autoRefresh, isVisible]);

  const fetchEvents = async () => {
    setFeedLoading(true);
    try {
      const res = await apiFetch('/events/recent?limit=25');
      if (res.ok) {
        const data = await res.json();
        setEvents(data);
      }
    } catch (err) {
      console.error('Failed to load recent events', err);
    } finally {
      setFeedLoading(false);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    setFeedback({ type: 'info', text: 'Resetting and reseeding database...' });
    try {
      const res = await apiFetch('/demo/reset', { method: 'POST' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Reset failed');
      }
      setFeedback({ type: 'success', text: 'Database successfully reset and reseeded to clean demo state.' });
      if (onActionComplete) onActionComplete();
      if (showFeed) fetchEvents();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handleRunScenario = async (scenarioId) => {
    setLoading(true);
    setFeedback({ type: 'info', text: `Triggering Scenario ${scenarioId}...` });
    try {
      const res = await apiFetch(`/demo/scenario/${scenarioId}`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Scenario ${scenarioId} failed`);
      }
      const data = await res.json();
      setFeedback({
        type: 'success',
        text: `Scenario ${scenarioId} (${data.name || 'Disruption'}): Disruption #${data.disruption?.id || ''} triggered with ${data.impacts?.length || 0} affected orders.`,
      });
      if (onActionComplete) onActionComplete();
      if (showFeed) fetchEvents();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  if (!isVisible) {
    return null;
  }

  return (
    <div style={{
      backgroundColor: '#1E293B',
      color: '#F8FAFC',
      borderBottom: '2px solid #38BDF8',
      boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
      position: 'relative',
      zIndex: 100,
    }}>
      {/* Top Controls Strip */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
        padding: '8px 16px',
        fontSize: '12px',
      }}>
        {/* Left: Badge & Quick Scenarios */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span style={{
            backgroundColor: '#0284C7',
            color: '#FFFFFF',
            fontWeight: '700',
            fontSize: '11px',
            padding: '2px 8px',
            borderRadius: '3px',
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}>
            Demo Bar (Admin)
          </span>

          <button
            type="button"
            disabled={loading}
            onClick={() => handleRunScenario(1)}
            style={{
              backgroundColor: '#334155',
              color: '#F1F5F9',
              border: '1px solid #475569',
              borderRadius: '3px',
              padding: '4px 10px',
              fontSize: '12px',
              fontWeight: '600',
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
            title="Trigger Supplier Delay on SH-001 (Chennai warehouse, P1 stock shortage)"
          >
            <span>▶</span> Run Scenario 1
          </button>

          <button
            type="button"
            disabled={loading}
            onClick={() => handleRunScenario(2)}
            style={{
              backgroundColor: '#334155',
              color: '#F1F5F9',
              border: '1px solid #475569',
              borderRadius: '3px',
              padding: '4px 10px',
              fontSize: '12px',
              fontWeight: '600',
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
            title="Trigger Stock Shortage at Bangalore for P2 (O-004 and O-005 affected)"
          >
            <span>▶</span> Run Scenario 2
          </button>

          <button
            type="button"
            disabled={loading}
            onClick={handleReset}
            style={{
              backgroundColor: '#B91C1C',
              color: '#FFFFFF',
              border: '1px solid #DC2626',
              borderRadius: '3px',
              padding: '4px 10px',
              fontSize: '12px',
              fontWeight: '600',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
            title="Reset and reseed database to initial demo state"
          >
            ↺ Reset
          </button>
        </div>

        {/* Right: Role Switcher & Live Feed Toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ color: '#94A3B8', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
              Switch Role:
            </span>
            <select
              value={currentUser.username}
              onChange={(e) => onRoleSwitch(e.target.value)}
              style={{
                backgroundColor: '#0F172A',
                color: '#F8FAFC',
                border: '1px solid #475569',
                borderRadius: '3px',
                padding: '3px 8px',
                fontSize: '12px',
                cursor: 'pointer',
              }}
            >
              {roleUsers.map((u) => (
                <option key={u.username} value={u.username}>
                  {u.label}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={() => setShowFeed(!showFeed)}
            style={{
              backgroundColor: showFeed ? '#0284C7' : '#334155',
              color: '#FFFFFF',
              border: '1px solid #475569',
              borderRadius: '3px',
              padding: '3px 10px',
              fontSize: '12px',
              fontWeight: '600',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span style={{
              display: 'inline-block',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: '#10B981',
            }} />
            {showFeed ? 'Hide Event Feed' : 'Live Event Feed'}
          </button>
        </div>
      </div>

      {/* Feedback Alert Bar */}
      {feedback && (
        <div style={{
          backgroundColor: feedback.type === 'error' ? '#7F1D1D' : feedback.type === 'success' ? '#064E3B' : '#1E3A8A',
          color: '#FFFFFF',
          padding: '6px 16px',
          fontSize: '12px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderTop: '1px solid rgba(255,255,255,0.1)',
        }}>
          <div>{feedback.text}</div>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#FFFFFF',
              cursor: 'pointer',
              fontSize: '14px',
              padding: '0 4px',
            }}
          >
            ×
          </button>
        </div>
      )}

      {/* Embedded Live Event Feed Panel */}
      {showFeed && (
        <div style={{
          backgroundColor: '#0F172A',
          borderTop: '1px solid #334155',
          padding: '12px 16px',
          maxHeight: '320px',
          overflowY: 'auto',
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '8px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: '700', fontSize: '13px', color: '#F8FAFC' }}>
                Live Operational Event Feed (/events/recent)
              </span>
              <span style={{ color: '#64748B', fontSize: '11px' }}>
                ({events.length} events logged)
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ fontSize: '11px', color: '#94A3B8', display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                Auto-refresh (4s)
              </label>
              <button
                type="button"
                onClick={fetchEvents}
                disabled={feedLoading}
                style={{
                  backgroundColor: '#1E293B',
                  color: '#94A3B8',
                  border: '1px solid #475569',
                  borderRadius: '3px',
                  padding: '2px 8px',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
              >
                {feedLoading ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
          </div>

          {events.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '16px', color: '#64748B', fontSize: '12px' }}>
              No recent audit or webhook events recorded yet.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', color: '#CBD5E1' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #334155', textAlign: 'left', color: '#94A3B8' }}>
                  <th style={{ padding: '6px 8px', width: '140px' }}>Timestamp</th>
                  <th style={{ padding: '6px 8px', width: '80px' }}>Source</th>
                  <th style={{ padding: '6px 8px' }}>Event / Title</th>
                  <th style={{ padding: '6px 8px', width: '120px' }}>Actor</th>
                  <th style={{ padding: '6px 8px' }}>Details</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev, idx) => (
                  <tr
                    key={ev.id || idx}
                    style={{
                      borderBottom: '1px solid #1E293B',
                      backgroundColor: idx % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '4px 8px', fontFamily: 'monospace', color: '#94A3B8' }}>
                      {ev.timestamp ? ev.timestamp.replace('T', ' ').slice(0, 19) : '—'}
                    </td>
                    <td style={{ padding: '4px 8px' }}>
                      <span style={{
                        backgroundColor: ev.category === 'webhook' ? '#312E81' : '#064E3B',
                        color: ev.category === 'webhook' ? '#A5B4FC' : '#6EE7B7',
                        padding: '1px 6px',
                        borderRadius: '2px',
                        fontSize: '10px',
                        fontWeight: '600',
                        textTransform: 'uppercase',
                      }}>
                        {ev.category}
                      </span>
                    </td>
                    <td style={{ padding: '4px 8px', fontWeight: '600', color: '#F1F5F9' }}>
                      {ev.title}
                    </td>
                    <td style={{ padding: '4px 8px', color: '#94A3B8' }}>
                      {ev.actor || 'System'}
                    </td>
                    <td style={{
                      padding: '4px 8px',
                      maxWidth: '360px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      color: '#94A3B8',
                    }}>
                      {typeof ev.details === 'object' ? JSON.stringify(ev.details) : String(ev.details || '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
