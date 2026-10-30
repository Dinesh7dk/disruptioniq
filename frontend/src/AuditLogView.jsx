import React from 'react';
import { ArrowLeft, Clock, ShieldCheck, User } from 'lucide-react';

export default function AuditLogView({ logs, onBack }) {
  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px 16px' }}>
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
          <ShieldCheck size={20} color="var(--success)" /> Append-Only Audit Trail
        </h2>

        <div style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
          {logs.length} logged events
        </div>
      </div>

      <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-subtle)', borderBottom: '1px solid var(--border)' }}>
              <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>Timestamp</th>
              <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>Action</th>
              <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>Entity</th>
              <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>Actor</th>
              <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>Details</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan="5" style={{ padding: '30px', textAlign: 'center', color: 'var(--text-dim)' }}>
                  No audit entries recorded yet
                </td>
              </tr>
            ) : (
              logs.map((log, idx) => (
                <tr key={log.id || idx} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '12px 16px', whiteSpace: 'nowrap', color: 'var(--text-dim)', fontSize: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Clock size={14} />
                      {log.created_at}
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', fontWeight: '600', color: 'var(--primary)' }}>
                    {log.action}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ color: 'var(--text-muted)' }}>{log.entity_type}</span> #{log.entity_id}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--text-main)' }}>
                      <User size={13} color="var(--text-muted)" />
                      {log.actor_name || (log.actor_id ? `User #${log.actor_id}` : 'System / Webhook')}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', maxWidth: '300px' }}>
                    <pre style={{
                      margin: 0,
                      fontSize: '11px',
                      backgroundColor: 'var(--bg-main)',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      overflowX: 'auto',
                      color: 'var(--text-muted)'
                    }}>
                      {typeof log.new_value === 'string' ? log.new_value : JSON.stringify(log.new_value)}
                    </pre>
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
