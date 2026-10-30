import React, { useState, useEffect } from 'react';
import { apiFetch, clearAuth, setAuth } from './api';
import Login from './Login';
import Dashboard from './Dashboard';
import DisruptionDetail from './DisruptionDetail';
import AuditLogView from './AuditLogView';
import NotificationsView from './NotificationsView';
import LiveEventsFeed from './LiveEventsFeed';

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [currentView, setCurrentView] = useState('dashboard');
  const [selectedDisruptionId, setSelectedDisruptionId] = useState(null);
  const [showLegalModal, setShowLegalModal] = useState(null); // 'terms' | 'privacy' | null

  // Dashboard Live Data States
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
      // 1. Fetch dashboard summary counts
      const resSum = await apiFetch('/dashboard/summary');
      if (resSum.ok) {
        const sumData = await resSum.json();
        setSummary(sumData);
      }

      // 2. Fetch disruptions list
      const resDisr = await apiFetch('/disruptions');
      if (resDisr.ok) {
        const disrData = await resDisr.json();
        setDisruptions(disrData);

        // Aggregate plans across disruptions for pipeline stats & pending queue
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

        // Deduplicate plans
        const uniquePlans = Array.from(new Map(allPlans.map(p => [p.id, p])).values());
        const pending = uniquePlans.filter(p => p.status === 'PENDING_APPROVAL' || p.status === 'APPROVED');
        setPendingApprovals(pending);

        const proposedCount = uniquePlans.length;
        const approvedCount = uniquePlans.filter(p => p.status === 'APPROVED').length;
        const executedCount = uniquePlans.filter(p => p.status === 'EXECUTED').length;
        const rejectedCount = uniquePlans.filter(p => p.status === 'REJECTED').length;

        setRecoveryProgress({
          proposed: proposedCount,
          approved: approvedCount,
          executed: executedCount,
          rejected: rejectedCount,
        });
      }

      // 3. Fetch affected orders sorted by risk
      const resOrders = await apiFetch('/orders?sort=risk');
      if (resOrders.ok) {
        const ordersData = await resOrders.json();
        setAffectedOrders(ordersData);
      }

      // 4. Fetch notifications
      const resNotif = await apiFetch('/notifications?limit=20');
      if (resNotif.ok) {
        const notifData = await resNotif.json();
        setNotifications(notifData);
      }
    } catch (err) {
      console.error('Error loading operational data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRoleSwitch = async (username, role) => {
    const password = username === 'admin' ? 'admin123' : 'pass123';
    try {
      const res = await apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      if (res.ok) {
        const data = await res.json();
        setAuth(data.access_token, { username: data.username, role: data.role });
        setCurrentUser({ username: data.username, role: data.role });
      }
    } catch (err) {
      console.error('Failed to switch persona:', err);
    }
  };

  const handleLogout = () => {
    clearAuth();
    setCurrentUser(null);
    setCurrentView('dashboard');
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
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navigation Bar */}
      <header style={{
        backgroundColor: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border-default)',
        padding: '10px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        {/* Left: Brand & Navigation Tabs */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div
            onClick={() => setCurrentView('dashboard')}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}
          >
            <div style={{ width: '8px', height: '8px', backgroundColor: '#2563eb', borderRadius: '1px' }} />
            <span className="mono" style={{ fontSize: '15px', fontWeight: '700', letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
              DISRUPTION<span style={{ color: '#3b82f6' }}>IQ</span>
            </span>
          </div>

          <nav style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <button
              onClick={() => setCurrentView('dashboard')}
              className={currentView === 'dashboard' ? 'btn-primary' : 'btn-secondary'}
              style={{ padding: '5px 12px' }}
            >
              Dashboard
            </button>
            <button
              onClick={() => setCurrentView('audit')}
              className={currentView === 'audit' ? 'btn-primary' : 'btn-secondary'}
              style={{ padding: '5px 12px' }}
            >
              Audit Trail
            </button>
            <button
              onClick={() => setCurrentView('events')}
              className={currentView === 'events' ? 'btn-primary' : 'btn-secondary'}
              style={{ padding: '5px 12px' }}
            >
              Live Feed
            </button>
            <button
              onClick={() => setCurrentView('notifications')}
              className={currentView === 'notifications' ? 'btn-primary' : 'btn-secondary'}
              style={{ padding: '5px 12px', position: 'relative' }}
            >
              Alerts
              {unreadCount > 0 && (
                <span className="mono" style={{
                  marginLeft: '6px',
                  backgroundColor: '#dc2626',
                  color: '#fff',
                  fontSize: '10px',
                  padding: '1px 5px',
                  borderRadius: '2px',
                  fontWeight: '700'
                }}>
                  {unreadCount}
                </span>
              )}
            </button>
          </nav>
        </div>

        {/* Right: Quick Role Switcher & Active Session */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Quick Persona Switcher */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span className="kpi-label" style={{ fontSize: '10px' }}>Role Switcher:</span>
            <select
              value={currentUser.username}
              onChange={(e) => handleRoleSwitch(e.target.value)}
              style={{ padding: '4px 8px', fontSize: '11px', height: '28px' }}
            >
              <option value="anita">Anita (Operations Analyst)</option>
              <option value="meera">Meera (Supply Chain Manager)</option>
              <option value="ravi">Ravi (Warehouse Operator)</option>
              <option value="priya">Priya (Procurement Approver)</option>
              <option value="admin">Admin (Administrator)</option>
            </select>
          </div>

          {/* Active Identity Pill */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            backgroundColor: 'var(--bg-surface-elevated)',
            border: '1px solid var(--border-default)',
            padding: '4px 10px',
            borderRadius: '4px',
            fontSize: '12px'
          }}>
            <span style={{ fontWeight: '600', color: 'var(--text-primary)' }}>{currentUser.username}</span>
            <span className="badge badge-accent" style={{ fontSize: '10px', padding: '1px 5px' }}>
              {currentUser.role}
            </span>
          </div>

          <button
            onClick={loadAllData}
            className="btn-secondary"
            title="Refresh Data"
            style={{ padding: '5px 10px' }}
          >
            ↻
          </button>

          <button
            onClick={handleLogout}
            className="btn-secondary"
            style={{ padding: '5px 10px', color: '#fca5a5' }}
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Main Workspace Area */}
      <main style={{ flex: 1, padding: '20px', maxWidth: '1400px', width: '100%', margin: '0 auto' }}>
        {currentView === 'dashboard' && (
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
            onBack={() => setCurrentView('dashboard')}
            onPlanProposed={loadAllData}
          />
        )}

        {currentView === 'audit' && (
          <AuditLogView
            currentUser={currentUser}
            onBack={() => setCurrentView('dashboard')}
          />
        )}

        {currentView === 'events' && (
          <LiveEventsFeed
            onBack={() => setCurrentView('dashboard')}
          />
        )}

        {currentView === 'notifications' && (
          <NotificationsView
            onBack={() => setCurrentView('dashboard')}
          />
        )}
      </main>

      {/* Legal & Governance Footer (Anti-patterns 26 & 27 compliant) */}
      <footer style={{
        borderTop: '1px solid var(--border-subtle)',
        padding: '12px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '11px',
        color: 'var(--text-muted)',
        backgroundColor: 'var(--bg-canvas)'
      }}>
        <div>
          DisruptionIQ Core Platform &middot; Deterministic Recovery Engine &middot; Real-time SQLite ACID transactions
        </div>
        <div style={{ display: 'flex', gap: '14px' }}>
          <span
            onClick={() => setShowLegalModal('terms')}
            style={{ cursor: 'pointer', textDecoration: 'underline' }}
          >
            Enterprise Terms of Service
          </span>
          <span
            onClick={() => setShowLegalModal('privacy')}
            style={{ cursor: 'pointer', textDecoration: 'underline' }}
          >
            Supply Chain Data Privacy Policy
          </span>
        </div>
      </footer>

      {/* Legal Modal */}
      {showLegalModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '20px',
          zIndex: 999
        }}>
          <div className="surface" style={{ maxWidth: '600px', width: '100%', maxHeight: '80vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 style={{ fontSize: '15px' }}>
                {showLegalModal === 'terms' ? 'Enterprise Terms of Service' : 'Supply Chain Data Privacy & Integrity Policy'}
              </h3>
              <button onClick={() => setShowLegalModal(null)} className="btn-secondary" style={{ padding: '3px 8px' }}>
                Close
              </button>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
              {showLegalModal === 'terms' ? (
                <div>
                  <p style={{ marginBottom: '8px' }}>
                    1. <strong>Separation of Duties:</strong> All proposed disruption mitigation plans require distinct proposer and approver identities. Self-approval is blocked at application and database schema constraints.
                  </p>
                  <p style={{ marginBottom: '8px' }}>
                    2. <strong>Inventory Versioning:</strong> Inventory reservations are performed under strict optimistic locking semantics (WHERE id = ? AND version = ?). Concurrent conflicting modifications are aborted with HTTP 409 Conflict.
                  </p>
                  <p>
                    3. <strong>Audit Immutability:</strong> All plan proposals, modifications, reviews, and warehouse executions are written to an append-only audit trail capturing full JSON snapshots.
                  </p>
                </div>
              ) : (
                <div>
                  <p style={{ marginBottom: '8px' }}>
                    1. <strong>Deterministic Computation:</strong> Logistics calculations, deadline verification, risk scores, and stock feasibility checks are executed deterministically in Python without non-deterministic AI interference.
                  </p>
                  <p style={{ marginBottom: '8px' }}>
                    2. <strong>LLM Boundary:</strong> AI services are strictly constrained to summarization and ranking from verified, pre-computed recovery options. No business database mutations are initiated directly by LLM calls.
                  </p>
                  <p>
                    3. <strong>Data Retention:</strong> Carrier webhooks, customer orders, and shipment tracking updates are retained within localized on-premise SQLite stores under parameterized SQL protocols.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
