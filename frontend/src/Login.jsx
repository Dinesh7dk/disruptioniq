import React, { useState } from 'react';
import { apiFetch, setAuth } from './api';

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('alice');
  const [password, setPassword] = useState('pass123');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Authentication failed');
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

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px'
    }}>
      <div className="card" style={{ width: '100%', maxWidth: '400px' }}>
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <h1 style={{ fontSize: '24px', fontWeight: 'bold', color: 'var(--primary)' }}>DisruptionIQ</h1>
          <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>Logistics Disruption & Recovery Platform</p>
        </div>

        {error && (
          <div style={{
            padding: '10px 14px',
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid var(--danger)',
            borderRadius: '6px',
            color: '#fca5a5',
            marginBottom: '16px',
            fontSize: '13px'
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '6px', color: 'var(--text-muted)' }}>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={{ width: '100%' }}
              placeholder="e.g. alice, carol, admin"
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '6px', color: 'var(--text-muted)' }}>Password</label>
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
            style={{
              backgroundColor: 'var(--primary)',
              color: '#fff',
              border: 'none',
              padding: '10px',
              fontSize: '14px',
              marginTop: '8px'
            }}
          >
            {loading ? 'Authenticating...' : 'Sign In'}
          </button>
        </form>

        <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid var(--border)', fontSize: '12px', color: 'var(--text-dim)' }}>
          <div style={{ fontWeight: '600', marginBottom: '6px', color: 'var(--text-muted)' }}>Available Roles (Demo):</div>
          <div>• <strong>alice</strong> (Operations Analyst)</div>
          <div>• <strong>carol</strong> (Supply Chain Manager)</div>
          <div>• <strong>dave</strong> (Warehouse Operator)</div>
          <div>• <strong>admin</strong> (Administrator, pass: admin123)</div>
        </div>
      </div>
    </div>
  );
}
