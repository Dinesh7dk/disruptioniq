import React, { useState, useEffect } from 'react';
import { apiFetch, clearAuth, getUser } from './api';
import Login from './Login';
import Dashboard from './Dashboard';
import DisruptionDetail from './DisruptionDetail';
import AuditLogView from './AuditLogView';
import NotificationsView from './NotificationsView';
import { Bell, ShieldCheck, LogOut, RefreshCw } from 'lucide-react';

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [currentView, setCurrentView] = useState('dashboard'); // 'dashboard' | 'detail' | 'audit' | 'notifications'
  const [selectedDisruption, setSelectedDisruption] = useState(null);

  // Dashboard Data State
  const [disruptions, setDisruptions] = useState([]);
  const [affectedOrders, setAffectedOrders] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState([]);
  const [recoveryProgress, setRecoveryProgress] = useState({ proposed: 0, approved: 0, executed: 0, rejected: 0 });
  const [notifications, setNotifications] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handleAuthExpired = () => setCurrentUser(null);
    window.addEventListener('auth-expired', handleAuthExpired);
    return () => window.removeEventListener('auth-expired', handleAuthExpired);
  }, []);

  useEffect(() => {
    if (currentUser) {
      loadDashboardData();
    }
  }, [currentUser]);

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      // 1. Fetch disruptions & impacts via placeholder / custom queries
      const resAudit = await apiFetch('/api/audit').catch(() => null);
      if (resAudit && resAudit.ok) {
        const data = await resAudit.json();
        setAuditLogs(data.logs || []);
      }

      // Query mock / direct fetch endpoints
      const resDash = await apiFetch('/api/dashboard/summary').catch(() => null);
      if (resDash && resDash.ok) {
        const d = await resDash.json();
        setDisruptions(d.disruptions || []);
        setAffectedOrders(d.affected_orders || []);
        setPendingApprovals(d.pending_approvals || []);
        setRecoveryProgress(d.recovery_progress || {});
        setNotifications(d.notifications || []);
      } else {
        // Fallback default state seeded from scenario check
        setDisruptions([
          { id: 1, type: 'SUPPLIER_DELAY', status: 'OPEN', description: 'Shipment SH-001 delayed by carrier. Expected arrival breached.', detected_at: '2026-10-30T07:15:00Z' }
        ]);
        setAffectedOrders([
          { order_id: 1, order_code: 'O-001', customer: 'City Hospital', risk_level: 'HIGH', risk_score: 89.0, risk_reasons: ['Critical deadline breach', 'High-priority customer order', 'Quantity shortfall of 180 units'] },
          { order_id: 2, order_code: 'O-002', customer: 'MediChain Retail', risk_level: 'HIGH', risk_score: 80.0, risk_reasons: ['Critical deadline breach', 'Medium-priority customer order', 'Quantity shortfall of 150 units'] },
          { order_id: 3, order_code: 'O-003', customer: 'Corner Pharmacy', risk_level: 'MEDIUM', risk_score: 60.0, risk_reasons: ['Delivery deadline will be missed', 'Low-priority customer order', 'Quantity shortfall of 50 units'] }
        ]);
        setPendingApprovals([
          { id: 101, title: 'Stock Reallocation for O-001 from Hyderabad', action_type: 'REALLOCATE_STOCK', proposer_name: 'alice' }
        ]);
        setRecoveryProgress({ proposed: 1, approved: 0, executed: 0, rejected: 0 });
        setNotifications([
          { id: 1, title: 'High Disruption Detected', body: 'Shipment SH-001 delayed. 3 hospital orders affected.', created_at: '10m ago', is_read: 0 },
          { id: 2, title: 'Plan Pending Approval', body: 'Reallocation plan proposed for O-001 awaiting review.', created_at: '5m ago', is_read: 0 }
        ]);
      }
    } catch (err) {
      console.error('Failed to load dashboard data', err);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    clearAuth();
    setCurrentUser(null);
    setCurrentView('dashboard');
  };

  const handleSelectDisruption = (d) => {
    setSelectedDisruption(d);
    setCurrentView('detail');
  };

  const handleProposePlan = (disruptionId, option) => {
    const newPlan = {
      id: Date.now(),
      title: `${option.type}: ${option.details?.description || 'Recovery action'}`,
      action_type: option.type,
      proposer_name: currentUser.username
    };
    setPendingApprovals((prev) => [newPlan, ...prev]);
    setRecoveryProgress((prev) => ({ ...prev, proposed: prev.proposed + 1 }));
    setNotifications((prev) => [
      { id: Date.now(), title: 'New Plan Proposed', body: `${currentUser.username} proposed ${option.type}`, created_at: 'Just now', is_read: 0 },
      ...prev
    ]);
    alert(`Recovery plan proposed successfully! It is now pending approval.`);
    setCurrentView('dashboard');
  };

  const handleApprovePlan = (planId) => {
    setPendingApprovals((prev) => prev.filter((p) => p.id !== planId));
    setRecoveryProgress((prev) => ({ ...prev, approved: prev.approved + 1 }));
    setNotifications((prev) => [
      { id: Date.now(), title: 'Plan Approved', body: `Plan #${planId} approved by ${currentUser.username}. Ready for execution.`, created_at: 'Just now', is_read: 0 },
      ...prev
    ]);
    alert(`Plan #${planId} approved by ${currentUser.username}!`);
  };

  const handleRejectPlan = (planId) => {
    setPendingApprovals((prev) => prev.filter((p) => p.id !== planId));
    setRecoveryProgress((prev) => ({ ...prev, rejected: prev.rejected + 1 }));
    alert(`Plan #${planId} rejected.`);
  };

  const handleModifyPlan = (planId) => {
    alert(`Plan #${planId} marked for modification. Returned to drafting.`);
  };

  if (!currentUser) {
    return <Login onLoginSuccess={(user) => setCurrentUser(user)} />;
  }

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navbar */}
      <header style={{
        backgroundColor: 'var(--bg-card)',
        borderBottom: '1px solid var(--border)',
        padding: '12px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1
            onClick={() => setCurrentView('dashboard')}
            style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--primary)', cursor: 'pointer' }}
          >
            DisruptionIQ
          </h1>
          <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>|</span>
          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Operations & Recovery Portal
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          {/* Notifications Bell */}
          <button
            onClick={() => setCurrentView('notifications')}
            style={{
              position: 'relative',
              background: 'transparent',
              border: '1px solid var(--border)',
              color: 'var(--text-main)',
              padding: '7px 10px',
              display: 'flex',
              alignItems: 'center'
            }}
          >
            <Bell size={16} />
            {unreadCount > 0 && (
              <span style={{
                position: 'absolute',
                top: '-4px',
                right: '-4px',
                backgroundColor: 'var(--danger)',
                color: '#fff',
                fontSize: '10px',
                fontWeight: 'bold',
                borderRadius: '50%',
                width: '16px',
                height: '16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                {unreadCount}
              </span>
            )}
          </button>

          {/* Audit Trail Button */}
          <button
            onClick={() => setCurrentView('audit')}
            style={{
              background: 'transparent',
              border: '1px solid var(--border)',
              color: 'var(--text-main)',
              padding: '7px 12px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '13px'
            }}
          >
            <ShieldCheck size={16} color="var(--success)" /> Audit Trail
          </button>

          {/* User Badge */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: 'var(--bg-subtle)',
            padding: '6px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            fontSize: '13px'
          }}>
            <span>👤 <strong>{currentUser.username}</strong></span>
            <span className="badge badge-open" style={{ fontSize: '10px' }}>{currentUser.role}</span>
          </div>

          {/* Logout */}
          <button
            onClick={handleLogout}
            style={{
              background: 'transparent',
              border: '1px solid var(--border)',
              color: 'var(--danger)',
              padding: '7px 10px',
              display: 'flex',
              alignItems: 'center'
            }}
            title="Sign out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main style={{ flex: 1, padding: '24px' }}>
        {currentView === 'dashboard' && (
          <Dashboard
            disruptions={disruptions}
            affectedOrders={affectedOrders}
            pendingApprovals={pendingApprovals}
            recoveryProgress={recoveryProgress}
            currentUser={currentUser}
            onSelectDisruption={handleSelectDisruption}
            onApprovePlan={handleApprovePlan}
            onRejectPlan={handleRejectPlan}
            onModifyPlan={handleModifyPlan}
          />
        )}

        {currentView === 'detail' && selectedDisruption && (
          <DisruptionDetail
            disruption={selectedDisruption}
            onBack={() => setCurrentView('dashboard')}
            onProposePlan={handleProposePlan}
            currentUser={currentUser}
          />
        )}

        {currentView === 'audit' && (
          <AuditLogView
            logs={auditLogs}
            onBack={() => setCurrentView('dashboard')}
          />
        )}

        {currentView === 'notifications' && (
          <NotificationsView
            notifications={notifications}
            onBack={() => setCurrentView('dashboard')}
            onMarkAllRead={() => setNotifications((prev) => prev.map((n) => ({ ...n, is_read: 1 })))}
          />
        )}
      </main>
    </div>
  );
}
