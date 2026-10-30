import React, { useState, useEffect } from 'react';
import { apiFetch } from './api';

export default function AuditLogView({ onBack, currentUser }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiFetch('/audit?limit=100');
      if (res.status === 403) {
        throw new Error('Audit logs can only be inspected by an Administrator or Supply Chain Manager.');
      }
      if (!res.ok) {
        throw new Error(`Failed to load audit records (HTTP ${res.status})`);
      }
      const data = await res.json();
      setLogs(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatActionSentence = (log) => {
    const actor = log.actor_username || `User #${log.actor_id || 'System'}`;
    const roleText = log.actor_role ? ` (${log.actor_role})` : '';
    
    switch (log.action) {
      case 'PLAN_PROPOSED':
        return `${actor}${roleText} proposed recovery plan #${log.entity_id}.`;
      case 'PLAN_APPROVED':
        return `${actor}${roleText} approved recovery plan #${log.entity_id}.`;
      case 'PLAN_REJECTED':
        return `${actor}${roleText} rejected recovery plan #${log.entity_id}.`;
      case 'PLAN_MODIFIED':
        return `${actor}${roleText} requested changes for recovery plan #${log.entity_id}.`;
      case 'PLAN_EXECUTED':
        return `${actor}${roleText} executed recovery plan #${log.entity_id} and reserved warehouse stock.`;
      case 'DISRUPTION_DETECTED':
        return `Automated tracking flagged disruption #${log.entity_id}.`;
      case 'DRAFT_CREATED':
        return `${actor}${roleText} generated communication draft #${log.entity_id}.`;
      case 'DRAFT_APPROVED':
        return `${actor}${roleText} approved communication draft #${log.entity_id} (peer review).`;
      case 'DRAFT_SENT_SIMULATED':
        return `${actor}${roleText} performed simulated dispatch of communication draft #${log.entity_id}.`;
      case 'DRAFT_EDITED':
        return `${actor}${roleText} updated communication draft #${log.entity_id}.`;
      default:
        return `${actor}${roleText} executed ${log.action.toLowerCase().replace(/_/g, ' ')} on ${log.entity_type} #${log.entity_id}.`;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={onBack} className="btn-secondary">
          Back to orders
        </button>
        <div style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
          Immutable append-only audit trail
        </div>
      </div>

      <div className="desk-panel" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: '700' }}>Operational audit log</h1>
            <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
              Complete record of all proposals, manager authorizations, and stock executions.
            </p>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
            {logs.length} logged events
          </div>
        </div>

        {error ? (
          <div style={{ padding: '32px 16px', textAlign: 'center' }}>
            <div style={{ color: 'var(--color-risk-high)', fontWeight: '600', marginBottom: '4px' }}>
              Access restricted
            </div>
            <p style={{ fontSize: '13px', color: 'var(--color-muted-ink)' }}>
              {error} Your current role is <strong>{currentUser?.role}</strong>.
            </p>
          </div>
        ) : loading ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
            Loading audit records...
          </div>
        ) : logs.length === 0 ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
            No audit records have been registered yet.
          </div>
        ) : (
          <table className="ops-table">
            <thead>
              <tr>
                <th style={{ width: '150px' }}>Timestamp</th>
                <th>Activity summary</th>
                <th style={{ width: '130px' }}>Action type</th>
                <th style={{ width: '120px' }}>Target</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td className="num" style={{ color: 'var(--color-muted-ink)', fontSize: '12px' }}>
                    {log.created_at}
                  </td>
                  <td>
                    <div style={{ fontWeight: '500', color: 'var(--color-ink)' }}>
                      {formatActionSentence(log)}
                    </div>
                    {log.note && (
                      <div style={{ fontSize: '12px', color: 'var(--color-muted-ink)', marginTop: '2px' }}>
                        Note: {log.note}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className="severity-pill severity-pill-none">
                      {log.action.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="num" style={{ color: 'var(--color-muted-ink)' }}>
                    {log.entity_type} #{log.entity_id}
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
