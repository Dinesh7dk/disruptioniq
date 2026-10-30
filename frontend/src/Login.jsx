import React, { useState } from 'react';
import { apiFetch, setAuth } from './api';

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('anita');
  const [password, setPassword] = useState('pass123');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const demoAccounts = [
    { name: 'Anita', role: 'Operations Analyst', username: 'anita', pass: 'pass123', desc: 'Proposes recovery plans & evaluates disruptions' },
    { name: 'Meera', role: 'Supply Chain Manager', username: 'meera', pass: 'pass123', desc: 'Approves stock reallocations, expedites & split shipments' },
    { name: 'Ravi', role: 'Warehouse Operator', username: 'ravi', pass: 'pass123', desc: 'Executes approved plans with stock reservation' },
    { name: 'Priya', role: 'Procurement Approver', username: 'priya', pass: 'pass123', desc: 'Approves emergency alternative supplier contracts' },
    { name: 'Admin', role: 'Administrator', username: 'admin', pass: 'admin123', desc: 'System governance, user roles & audit access' },
  ];

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Authentication failed. Please verify credentials.');
      }

      const data = await res.json();
      setAuth(data.access_token, { username: data.username, role: data.role });
      onLoginSuccess({ username: data.username, role: data.role });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectDemo = (acc) => {
    setUsername(acc.username);
    setPassword(acc.pass);
    setError('');
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px 16px',
      backgroundColor: 'var(--bg-canvas)'
    }}>
      <div style={{ width: '100%', maxWidth: '440px', marginBottom: '24px', textAlign: 'center' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <div style={{
            width: '10px',
            height: '10px',
            borderRadius: '2px',
            backgroundColor: '#2563eb'
          }} />
          <span className="mono" style={{ fontSize: '18px', fontWeight: '700', letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
            DISRUPTION<span style={{ color: '#3b82f6' }}>IQ</span>
          </span>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
          Autonomous Logistics Disruption Detection & Recovery Platform
        </p>
      </div>

      <div className="surface" style={{ width: '100%', maxWidth: '440px', padding: '24px' }}>
        <div style={{ marginBottom: '18px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '14px' }}>
          <h2 style={{ fontSize: '15px', fontWeight: '600', color: 'var(--text-primary)' }}>Sign In to Control Console</h2>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
            Role-enforced authentication with in-memory session protection.
          </p>
        </div>

        {error && (
          <div style={{
            padding: '10px 12px',
            backgroundColor: 'var(--status-high-bg)',
            border: '1px solid var(--status-high-border)',
            borderRadius: '4px',
            color: 'var(--status-high-text)',
            marginBottom: '16px',
            fontSize: '12px'
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label className="kpi-label" style={{ display: 'block', marginBottom: '6px' }}>Username or Email</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={{ width: '100%' }}
              placeholder="e.g. anita, meera, ravi"
            />
          </div>

          <div>
            <label className="kpi-label" style={{ display: 'block', marginBottom: '6px' }}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{ width: '100%' }}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn-primary"
            style={{ width: '100%', padding: '9px', fontSize: '13px', marginTop: '6px' }}
          >
            {loading ? 'Authenticating...' : 'Sign In'}
          </button>
        </form>

        {/* Demo Persona Quick Fill */}
        <div style={{ marginTop: '22px', paddingTop: '16px', borderTop: '1px solid var(--border-subtle)' }}>
          <div className="kpi-label" style={{ marginBottom: '10px' }}>Select Demo Persona:</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {demoAccounts.map((acc) => (
              <div
                key={acc.username}
                onClick={() => handleSelectDemo(acc)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '7px 10px',
                  backgroundColor: username === acc.username ? 'var(--bg-surface-elevated)' : 'var(--bg-surface-subtle)',
                  border: username === acc.username ? '1px solid var(--border-focus)' : '1px solid var(--border-subtle)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s ease'
                }}
              >
                <div>
                  <span style={{ fontWeight: '600', color: 'var(--text-primary)', fontSize: '12px' }}>{acc.name}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px', marginLeft: '6px' }}>({acc.role})</span>
                </div>
                <span className="mono" style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{acc.username}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ marginTop: '20px', fontSize: '11px', color: 'var(--text-dim)', textAlign: 'center' }}>
        Protected by ISO-compliant audit logging & deterministic separation of duties.
      </div>
    </div>
  );
}
