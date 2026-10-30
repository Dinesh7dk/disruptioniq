import React, { useState } from 'react';
import { apiFetch, setAuth } from './api';

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('anita');
  const [password, setPassword] = useState('pass123');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const demoAccounts = [
    { name: 'Anita', role: 'Operations Analyst', username: 'anita', pass: 'pass123', duty: 'Proposes recovery plans and logs impact' },
    { name: 'Meera', role: 'Supply Chain Manager', username: 'meera', pass: 'pass123', duty: 'Authorizes reallocations, expediting, and splits' },
    { name: 'Ravi', role: 'Warehouse Operator', username: 'ravi', pass: 'pass123', duty: 'Executes approved plans and reserves stock' },
    { name: 'Priya', role: 'Procurement Approver', username: 'priya', pass: 'pass123', duty: 'Authorizes alternative supplier procurement' },
    { name: 'Admin', role: 'Administrator', username: 'admin', pass: 'admin123', duty: 'System configuration, data imports, and audit log' },
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
        throw new Error(data.detail || 'The username or password was not recognized. Please check your credentials.');
      }

      const data = await res.json();
      setAuth(data.access_token, { username: data.username, role: data.role });
      const meRes = await apiFetch('/me');
      let userData = { username: data.username, role: data.role, demo_mode: false };
      if (meRes.ok) {
        userData = await meRes.json();
      }
      setAuth(data.access_token, userData);
      onLoginSuccess(userData);
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
      padding: 'var(--space-6)',
      backgroundColor: 'var(--color-paper)'
    }}>
      <div style={{ width: '100%', maxWidth: '420px', marginBottom: 'var(--space-5)' }}>
        <h1 style={{ fontSize: '24px', fontWeight: '700', marginBottom: 'var(--space-1)', color: 'var(--color-ink)' }}>
          DisruptionIQ
        </h1>
        <p style={{ color: 'var(--color-muted-ink)', fontSize: '13px' }}>
          Operations console for supply disruption recovery
        </p>
      </div>

      <div className="desk-panel" style={{ width: '100%', maxWidth: '420px', padding: 'var(--space-6)' }}>
        <h2 style={{ fontSize: '16px', fontWeight: '600', marginBottom: 'var(--space-3)' }}>
          Sign in
        </h2>

        {error && (
          <div style={{
            padding: '8px 12px',
            backgroundColor: 'var(--color-risk-high-subtle)',
            border: '1px solid var(--color-risk-high)',
            borderRadius: 'var(--radius-input)',
            color: 'var(--color-risk-high)',
            marginBottom: 'var(--space-4)',
            fontSize: '13px'
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: '500', color: 'var(--color-muted-ink)', marginBottom: '4px' }}>
              Username or email address
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: '500', color: 'var(--color-muted-ink)', marginBottom: '4px' }}>
              Password
            </label>
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
            style={{ width: '100%', padding: '8px', fontSize: '13px', marginTop: 'var(--space-2)' }}
          >
            {loading ? 'Checking credentials...' : 'Sign in to console'}
          </button>
        </form>

        <div style={{ marginTop: 'var(--space-6)', paddingTop: 'var(--space-4)', borderTop: '1px solid var(--color-line)' }}>
          <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--color-muted-ink)', marginBottom: 'var(--space-2)' }}>
            Demo roles
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {demoAccounts.map((acc) => (
              <button
                key={acc.username}
                type="button"
                onClick={() => handleSelectDemo(acc)}
                className="btn-secondary"
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '6px 10px',
                  textAlign: 'left',
                  backgroundColor: username === acc.username ? 'var(--color-primary-subtle)' : '#FFFFFF',
                  borderColor: username === acc.username ? 'var(--color-primary)' : 'var(--color-line)'
                }}
              >
                <div>
                  <div style={{ fontWeight: '600', fontSize: '13px', color: 'var(--color-ink)' }}>
                    {acc.name} <span style={{ fontWeight: '400', color: 'var(--color-muted-ink)', fontSize: '12px' }}>({acc.role})</span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)' }}>{acc.duty}</div>
                </div>
                <span className="mono" style={{ fontSize: '12px', color: 'var(--color-primary)' }}>Select</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
