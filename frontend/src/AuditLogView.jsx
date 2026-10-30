import React, { useState, useEffect } from 'react';
import { apiFetch } from './api';

export default function AuditLogView({ onBack, currentUser }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedLog, setSelectedLog] = useState(null);

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiFetch('/audit?limit=100');
      if (res.status === 403) {
        throw new Error('Access Restricted: Audit logs may only be inspected by Administrator or Supply Chain Manager roles (Separation of Duties).');
      }
      if (!res.ok) {
        throw new Error(`Failed to load audit logs (HTTP ${res.status})`);
      }
      const data = await res.json();
      setLogs(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={onBack} className="btn-secondary">
          ← Back to Dashboard
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="kpi-label">Append-Only Audit Trail</span>
          <span className="badge badge-neutral mono">{logs.length} entries</span>
        </div>
      </div>

      {error ? (
        <div className="surface" style={{
          padding: '24px',
          textAlign: 'center',
          backgroundColor: 'var(--status-high-bg)',
          border: '1px solid var(--status-high-border)'
        }}>
          <h3 style={{ fontSize: '14px', color: 'var(--status-high-text)', marginBottom: '6px' }}>
            403 Forbidden
          </h3>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{error}</p>
          <div style={{ marginTop: '12px', fontSize: '11px', color: 'var(--text-muted)' }}>
            Current session role: <strong>{currentUser?.role}</strong>
          </div>
        </div>
      ) : (
        <div className="surface" style={{ padding: '0', overflow: 'hidden' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action</th>
                <th>Target Entity</th>
                <th>Actor</th>
                <th>State Change Snapshot</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                [1, 2, 3, 4, 5].map((n) => (
                  <tr key={n}>
                    <td colSpan="5"><div className="skeleton" style={{ height: '24px', width: '100%' }} /></td>
                  </tr>
                ))
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan="5" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                    No audit records registered yet.
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} style={{ cursor: 'pointer' }} onClick={() => setSelectedLog(log)}>
                    <td className="mono" style={{ whiteSpace: 'nowrap', fontSize: '11px', color: 'var(--text-muted)' }}>
                      {log.created_at}
                    </td>
                    <td>
                      <span className="badge badge-accent mono">{log.action}</span>
                    </td>
                    <td>
                      <span className="mono" style={{ color: 'var(--text-secondary)' }}>{log.entity_type}</span>{' '}
                      <span className="mono" style={{ color: 'var(--text-dim)' }}>#{log.entity_id}</span>
                    </td>
                    <td>
                      <span style={{ fontWeight: '500', color: 'var(--text-primary)' }}>
                        {log.actor_username || `ID #${log.actor_id || 'System'}`}
                      </span>
                      {log.actor_role && (
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '6px' }}>
                          ({log.actor_role})
                        </span>
                      )}
                    </td>
                    <td style={{ maxWidth: '320px' }}>
                      <div className="mono" style={{
                        fontSize: '11px',
                        color: 'var(--text-muted)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap'
                      }}>
                        {log.note || (log.new_value ? JSON.stringify(log.new_value) : '—')}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Snapshot Diff Modal / Detail Pane */}
      {selectedLog && (
        <div className="surface" style={{ marginTop: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h4 style={{ fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Audit Snapshot: {selectedLog.action} (Log #{selectedLog.id})
            </h4>
            <button onClick={() => setSelectedLog(null)} className="btn-secondary" style={{ padding: '3px 8px' }}>
              Close
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <div className="kpi-label" style={{ marginBottom: '4px' }}>Before State</div>
              <pre className="mono" style={{
                backgroundColor: 'var(--bg-canvas)',
                border: '1px solid var(--border-default)',
                borderRadius: '4px',
                padding: '10px',
                fontSize: '11px',
                color: 'var(--text-muted)',
                maxHeight: '160px',
                overflowY: 'auto'
              }}>
                {selectedLog.old_value ? JSON.stringify(selectedLog.old_value, null, 2) : 'null (None)'}
              </pre>
            </div>

            <div>
              <div className="kpi-label" style={{ marginBottom: '4px' }}>After State</div>
              <pre className="mono" style={{
                backgroundColor: 'var(--bg-canvas)',
                border: '1px solid var(--border-default)',
                borderRadius: '4px',
                padding: '10px',
                fontSize: '11px',
                color: '#86efac',
                maxHeight: '160px',
                overflowY: 'auto'
              }}>
                {selectedLog.new_value ? JSON.stringify(selectedLog.new_value, null, 2) : 'null (None)'}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
