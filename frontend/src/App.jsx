import React, { useState, useEffect } from 'react';
import { apiFetch, clearAuth, setAuth } from './api';
import Login from './Login';
import Dashboard from './Dashboard';
import DisruptionDetail from './DisruptionDetail';
import AuditLogView from './AuditLogView';
import NotificationsView from './NotificationsView';
import LiveEventsFeed from './LiveEventsFeed';
import DraftsView from './DraftsView';
import DemoBar from './DemoBar';

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [currentView, setCurrentView] = useState('orders'); // 'orders' | 'detail' | 'audit' | 'notifications' | 'events'
  const [selectedDisruptionId, setSelectedDisruptionId] = useState(null);

  // Operational State
  const [summary, setSummary] = useState({
    active_disruptions: 0,
    affected_orders: 0,
    pending_approvals: 0,
    executed_plans: 0,
  });
  const [disruptions, setDisruptions] = useState([]);
  const [affectedOrders, setAffectedOrders] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState([]);
  const [recoveryProgress, setRecoveryProgress] = useState({
    proposed: 0,
    approved: 0,
    executed: 0,
    rejected: 0,
  });
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handleAuthExpired = () => setCurrentUser(null);
    window.addEventListener('auth-expired', handleAuthExpired);
    return () => window.removeEventListener('auth-expired', handleAuthExpired);
  }, []);

  useEffect(() => {
    if (currentUser) {
      loadAllData();
    }
  }, [currentUser]);

  const loadAllData = async () => {
    setLoading(true);
    try {
      const resSum = await apiFetch('/dashboard/summary');
      if (resSum.ok) {
        setSummary(await resSum.json());
      }

      const resDisr = await apiFetch('/disruptions');
      if (resDisr.ok) {
        const disrData = await resDisr.json();
        setDisruptions(disrData);

        let allPlans = [];
        for (const d of disrData.slice(0, 5)) {
          const resDetail = await apiFetch(`/disruptions/${d.id}`);
          if (resDetail.ok) {
            const detailData = await resDetail.json();
            if (detailData.plans) {
              allPlans.push(...detailData.plans);
            }
          }
        }

        const uniquePlans = Array.from(new Map(allPlans.map(p => [p.id, p])).values());
        setPendingApprovals(uniquePlans.filter(p => p.status === 'PENDING_APPROVAL' || p.status === 'APPROVED'));

        setRecoveryProgress({
          proposed: uniquePlans.length,
          approved: uniquePlans.filter(p => p.status === 'APPROVED').length,
          executed: uniquePlans.filter(p => p.status === 'EXECUTED').length,
          rejected: uniquePlans.filter(p => p.status === 'REJECTED').length,
        });
      }

      const resOrders = await apiFetch('/orders?sort=risk');
      if (resOrders.ok) {
        setAffectedOrders(await resOrders.json());
      }

      const resNotif = await apiFetch('/notifications?limit=30');
      if (resNotif.ok) {
        setNotifications(await resNotif.json());
      }
    } catch (err) {
      console.error('Failed to load operational data', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRoleSwitch = async (username) => {
    const password = username === 'admin' ? 'admin123' : 'pass123';
    try {
      const res = await apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      if (res.ok) {
        const data = await res.json();
        setAuth(data.access_token, { username: data.username, role: data.role });
        const meRes = await apiFetch('/me');
        let userData = { username: data.username, role: data.role, demo_mode: false };
        if (meRes.ok) {
          userData = await meRes.json();
        }
        setAuth(data.access_token, userData);
        setCurrentUser(userData);
      }
    } catch (err) {
      console.error('Role switch failed', err);
    }
  };

  const handleLogout = () => {
    clearAuth();
    setCurrentUser(null);
    setCurrentView('orders');
  };

  const handleSelectDisruption = (d) => {
    setSelectedDisruptionId(d.id);
    setCurrentView('detail');
  };

  if (!currentUser) {
    return <Login onLoginSuccess={(u) => setCurrentUser(u)} />;
  }

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--color-paper)' }}>
      {/* Demo bar: visible only to Administrator in demo mode */}
      <DemoBar
        currentUser={currentUser}
        onRoleSwitch={handleRoleSwitch}
        onActionComplete={loadAllData}
      />

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* Left Slim Navigation Rail */}
        <aside style={{
        width: '220px',
        borderRight: '1px solid var(--color-line)',
        backgroundColor: 'var(--color-panel)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        flexShrink: 0
      }}>
        {/* Top Brand & Navigation Links */}
        <div>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--color-line)' }}>
            <h1 style={{ fontSize: '18px', fontWeight: '700', color: 'var(--color-ink)', letterSpacing: '-0.02em' }}>
              DisruptionIQ
            </h1>
            <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)', marginTop: '2px' }}>
              Operations desk
            </div>
          </div>

          <nav style={{ padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <button
              type="button"
              onClick={() => setCurrentView('orders')}
              className={currentView === 'orders' ? 'btn-primary' : 'btn-subtle'}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '8px 12px',
                fontWeight: currentView === 'orders' ? '600' : '400',
                backgroundColor: currentView === 'orders' ? 'var(--color-primary)' : 'transparent',
                color: currentView === 'orders' ? '#FFFFFF' : 'var(--color-ink)'
              }}
            >
              Orders at risk
            </button>

            <button
              type="button"
              onClick={() => setCurrentView('drafts')}
              className={currentView === 'drafts' ? 'btn-primary' : 'btn-subtle'}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '8px 12px',
                fontWeight: currentView === 'drafts' ? '600' : '400',
                backgroundColor: currentView === 'drafts' ? 'var(--color-primary)' : 'transparent',
                color: currentView === 'drafts' ? '#FFFFFF' : 'var(--color-ink)'
              }}
            >
              Drafted messages
            </button>

            <button
              type="button"
              onClick={() => setCurrentView('audit')}
              className={currentView === 'audit' ? 'btn-primary' : 'btn-subtle'}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '8px 12px',
                fontWeight: currentView === 'audit' ? '600' : '400',
                backgroundColor: currentView === 'audit' ? 'var(--color-primary)' : 'transparent',
                color: currentView === 'audit' ? '#FFFFFF' : 'var(--color-ink)'
              }}
            >
              Audit trail
            </button>

            <button
              type="button"
              onClick={() => setCurrentView('events')}
              className={currentView === 'events' ? 'btn-primary' : 'btn-subtle'}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '8px 12px',
                fontWeight: currentView === 'events' ? '600' : '400',
                backgroundColor: currentView === 'events' ? 'var(--color-primary)' : 'transparent',
                color: currentView === 'events' ? '#FFFFFF' : 'var(--color-ink)'
              }}
            >
              Live event feed
            </button>

            <button
              type="button"
              onClick={() => setCurrentView('notifications')}
              className={currentView === 'notifications' ? 'btn-primary' : 'btn-subtle'}
              style={{
                width: '100%',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 12px',
                fontWeight: currentView === 'notifications' ? '600' : '400',
                backgroundColor: currentView === 'notifications' ? 'var(--color-primary)' : 'transparent',
                color: currentView === 'notifications' ? '#FFFFFF' : 'var(--color-ink)'
              }}
            >
              <span>Notifications</span>
              {unreadCount > 0 && (
                <span className="num" style={{
                  backgroundColor: 'var(--color-risk-high)',
                  color: '#FFFFFF',
                  fontSize: '11px',
                  fontWeight: '600',
                  padding: '1px 6px',
                  borderRadius: '2px'
                }}>
                  {unreadCount}
                </span>
              )}
            </button>
          </nav>
        </div>

        {/* Bottom Rail: Active Session, Role Switcher, Sign Out */}
        <div style={{ padding: '16px', borderTop: '1px solid var(--color-line)' }}>
          <div style={{ marginBottom: '12px' }}>
            <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)' }}>Current user</div>
            <div style={{ fontWeight: '600', fontSize: '13px', color: 'var(--color-ink)' }}>
              {currentUser.username}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--color-primary)' }}>
              {currentUser.role}
            </div>
          </div>

          <div style={{ marginBottom: '12px' }}>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--color-muted-ink)', marginBottom: '4px' }}>
              Switch demo role
            </label>
            <select
              value={currentUser.username}
              onChange={(e) => handleRoleSwitch(e.target.value)}
              style={{ width: '100%', fontSize: '12px', padding: '4px 6px' }}
            >
              <option value="anita">Anita (Analyst)</option>
              <option value="meera">Meera (Manager)</option>
              <option value="ravi">Ravi (Operator)</option>
              <option value="priya">Priya (Procurement)</option>
              <option value="admin">Admin (Administrator)</option>
            </select>
          </div>

          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              type="button"
              onClick={loadAllData}
              className="btn-secondary"
              style={{ flex: 1, fontSize: '12px', padding: '4px' }}
              title="Refresh data"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="btn-secondary"
              style={{ flex: 1, fontSize: '12px', padding: '4px' }}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Main Work Area */}
      <main style={{ flex: 1, padding: 'var(--space-6)', overflowY: 'auto' }}>
        {currentView === 'orders' && (
          <Dashboard
            summary={summary}
            disruptions={disruptions}
            affectedOrders={affectedOrders}
            pendingApprovals={pendingApprovals}
            recoveryProgress={recoveryProgress}
            currentUser={currentUser}
            loading={loading}
            onSelectDisruption={handleSelectDisruption}
            onRefreshData={loadAllData}
          />
        )}

        {currentView === 'detail' && selectedDisruptionId && (
          <DisruptionDetail
            disruptionId={selectedDisruptionId}
            currentUser={currentUser}
            onBack={() => setCurrentView('orders')}
            onPlanProposed={loadAllData}
          />
        )}

        {currentView === 'drafts' && (
          <DraftsView
            currentUser={currentUser}
            onBack={() => setCurrentView('orders')}
          />
        )}

        {currentView === 'audit' && (
          <AuditLogView
            currentUser={currentUser}
            onBack={() => setCurrentView('orders')}
          />
        )}

        {currentView === 'events' && (
          <LiveEventsFeed
            onBack={() => setCurrentView('orders')}
          />
        )}

        {currentView === 'notifications' && (
          <NotificationsView
            onBack={() => setCurrentView('orders')}
          />
        )}
      </main>
      </div>
    </div>
  );
}
