import React, { useState } from 'react';
import { apiFetch } from './api';

export default function Dashboard({
  summary,
  disruptions,
  affectedOrders,
  pendingApprovals,
  recoveryProgress,
  currentUser,
  loading,
  onSelectDisruption,
  onRefreshData,
}) {
  const [actionError, setActionError] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const handleApprove = async (planId) => {
    setActionError('');
    setActionSuccess('');
    setActionLoading(true);
    try {
      const res = await apiFetch(`/plans/${planId}/approve`, {
        method: 'POST',
        body: JSON.stringify({ note: `Approved by ${currentUser.username} (${currentUser.role})` }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Approval failed');
      }
      setActionSuccess(`Plan #${planId} successfully approved.`);
      onRefreshData();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (planId) => {
    setActionError('');
    setActionSuccess('');
    setActionLoading(true);
    try {
      const res = await apiFetch(`/plans/${planId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ note: `Rejected by ${currentUser.username}` }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Rejection failed');
      }
      setActionSuccess(`Plan #${planId} rejected.`);
      onRefreshData();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleModify = async (planId) => {
    setActionError('');
    setActionSuccess('');
    setActionLoading(true);
    try {
      const res = await apiFetch(`/plans/${planId}/modify`, {
        method: 'POST',
        body: JSON.stringify({ note: `Modification requested by ${currentUser.username}` }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Modification failed');
      }
      setActionSuccess(`Plan #${planId} returned to pending approval with revision note.`);
      onRefreshData();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleExecute = async (planId) => {
    setActionError('');
    setActionSuccess('');
    setActionLoading(true);
    try {
      const res = await apiFetch(`/plans/${planId}/execute`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Execution failed');
      }
      setActionSuccess(`Plan #${planId} executed successfully. Stock reserved and inventory version updated.`);
      onRefreshData();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Action Notification Banner */}
      {actionError && (
        <div style={{
          padding: '10px 14px',
          backgroundColor: 'var(--status-high-bg)',
          border: '1px solid var(--status-high-border)',
          borderRadius: '4px',
          color: 'var(--status-high-text)',
          fontSize: '12px'
        }}>
          <strong>Action Blocked:</strong> {actionError}
        </div>
      )}
      {actionSuccess && (
        <div style={{
          padding: '10px 14px',
          backgroundColor: 'var(--status-low-bg)',
          border: '1px solid var(--status-low-border)',
          borderRadius: '4px',
          color: 'var(--status-low-text)',
          fontSize: '12px'
        }}>
          <strong>Success:</strong> {actionSuccess}
        </div>
      )}

      {/* Top Operational Metrics */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '12px'
      }}>
        <div className="surface" style={{ padding: '14px 18px' }}>
          <div className="kpi-label">Active Disruptions</div>
          <div className="mono" style={{ fontSize: '26px', fontWeight: '700', marginTop: '4px', color: 'var(--text-primary)' }}>
            {loading ? <div className="skeleton" style={{ width: '40px', height: '32px' }} /> : (summary.active_disruptions ?? disruptions.length)}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>Requiring mitigation</div>
        </div>

        <div className="surface" style={{ padding: '14px 18px' }}>
          <div className="kpi-label">Affected Customer Orders</div>
          <div className="mono" style={{ fontSize: '26px', fontWeight: '700', marginTop: '4px', color: '#f59e0b' }}>
            {loading ? <div className="skeleton" style={{ width: '40px', height: '32px' }} /> : (summary.affected_orders ?? affectedOrders.length)}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>Ranked by risk severity</div>
        </div>

        <div className="surface" style={{ padding: '14px 18px' }}>
          <div className="kpi-label">Pending Recovery Approvals</div>
          <div className="mono" style={{ fontSize: '26px', fontWeight: '700', marginTop: '4px', color: '#3b82f6' }}>
            {loading ? <div className="skeleton" style={{ width: '40px', height: '32px' }} /> : (summary.pending_approvals ?? pendingApprovals.length)}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>Role-authorized review queue</div>
        </div>

        <div className="surface" style={{ padding: '14px 18px' }}>
          <div className="kpi-label">Executed Plans</div>
          <div className="mono" style={{ fontSize: '26px', fontWeight: '700', marginTop: '4px', color: '#10b981' }}>
            {loading ? <div className="skeleton" style={{ width: '40px', height: '32px' }} /> : (summary.executed_plans ?? 0)}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>Stock reserved in warehouse</div>
        </div>
      </div>

      {/* Main 4-Panel Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(500px, 1fr))',
        gap: '16px'
      }}>
        {/* Panel 1: Active Disruptions */}
        <div className="surface" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div>
              <h3 style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-primary)' }}>
                Active Disruptions ({disruptions.length})
              </h3>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Click disruption to inspect impacts and verified recovery options</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, overflowY: 'auto', maxHeight: '360px' }}>
            {loading ? (
              [1, 2, 3].map((n) => <div key={n} className="skeleton" style={{ height: '70px', width: '100%' }} />)
            ) : disruptions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)', fontSize: '12px' }}>
                No active disruptions currently detected in the network.
              </div>
            ) : (
              disruptions.map((d) => (
                <div
                  key={d.id}
                  onClick={() => onSelectDisruption(d)}
                  style={{
                    backgroundColor: 'var(--bg-surface-subtle)',
                    border: '1px solid var(--border-default)',
                    borderRadius: '4px',
                    padding: '12px 14px',
                    cursor: 'pointer',
                    transition: 'border-color 0.15s ease, background 0.15s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border-focus)';
                    e.currentTarget.style.backgroundColor = 'var(--bg-surface-elevated)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border-default)';
                    e.currentTarget.style.backgroundColor = 'var(--bg-surface-subtle)';
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="badge badge-critical">{d.type}</span>
                      {d.shipment?.code && (
                        <span className="mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                          {d.shipment.code}
                        </span>
                      )}
                    </div>
                    <span className="mono" style={{ fontSize: '11px', color: 'var(--text-dim)' }}>ID #{d.id}</span>
                  </div>

                  <div style={{ fontSize: '13px', color: 'var(--text-primary)', marginBottom: '6px' }}>
                    {d.description}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: 'var(--text-muted)' }}>
                    <span>{d.affected_orders_count || 0} order(s) impacted</span>
                    <span style={{ color: '#3b82f6', fontWeight: '500' }}>Inspect Recovery Options →</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Panel 2: Affected Orders Sorted by Risk */}
        <div className="surface" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div>
              <h3 style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-primary)' }}>
                Affected Orders (Ranked by Risk)
              </h3>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Deterministic 0-100 composite scoring with visible factor contributions</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, overflowY: 'auto', maxHeight: '360px' }}>
            {loading ? (
              [1, 2, 3].map((n) => <div key={n} className="skeleton" style={{ height: '70px', width: '100%' }} />)
            ) : affectedOrders.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)', fontSize: '12px' }}>
                All customer orders are currently on schedule.
              </div>
            ) : (
              affectedOrders.map((ord) => {
                const reasons = Array.isArray(ord.reasons) ? ord.reasons : [];
                const badgeClass = ord.risk_score >= 80 ? 'badge-critical' : (ord.risk_score >= 50 ? 'badge-medium' : 'badge-low');

                return (
                  <div key={ord.id} style={{
                    backgroundColor: 'var(--bg-surface-subtle)',
                    border: '1px solid var(--border-default)',
                    borderRadius: '4px',
                    padding: '12px 14px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="mono" style={{ fontWeight: '700', color: 'var(--text-primary)', fontSize: '13px' }}>
                          {ord.code}
                        </span>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>{ord.customer}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Due: {ord.due_date}</span>
                        <span className={`badge ${badgeClass}`}>
                          {ord.risk_level || 'RISK'} ({ord.risk_score})
                        </span>
                      </div>
                    </div>

                    {/* Visible Risk Factors */}
                    {reasons.length > 0 && (
                      <div style={{ marginTop: '6px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                        {reasons.slice(0, 3).map((r, rIdx) => (
                          <div key={rIdx} style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            <span style={{ color: '#f59e0b', marginRight: '5px' }}>›</span> {r}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Panel 3: Pending Approvals (Role Gated) */}
        <div className="surface" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div>
              <h3 style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-primary)' }}>
                Pending Approvals & Execution
              </h3>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Active session: {currentUser?.username} ({currentUser?.role})</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, overflowY: 'auto', maxHeight: '360px' }}>
            {loading ? (
              [1, 2].map((n) => <div key={n} className="skeleton" style={{ height: '90px', width: '100%' }} />)
            ) : pendingApprovals.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)', fontSize: '12px' }}>
                No recovery plans awaiting approval or execution.
              </div>
            ) : (
              pendingApprovals.map((plan) => {
                const isProposer = (currentUser?.id === plan.proposed_by) || (currentUser?.username === plan.proposer_username);
                
                // Permission checks
                const canApprove = (
                  (currentUser?.role === 'Supply Chain Manager' && ['REALLOCATE_STOCK', 'EXPEDITE_ORDER', 'PARTIAL_FULFIL'].includes(plan.action_type)) ||
                  (currentUser?.role === 'Procurement Approver' && plan.action_type === 'ALTERNATIVE_SUPPLIER') ||
                  (currentUser?.role === 'Administrator')
                ) && !isProposer && plan.status === 'PENDING_APPROVAL';

                const canExecute = (
                  currentUser?.role === 'Warehouse Operator' || currentUser?.role === 'Administrator'
                ) && plan.status === 'APPROVED';

                return (
                  <div key={plan.id} style={{
                    backgroundColor: 'var(--bg-surface-subtle)',
                    border: '1px solid var(--border-default)',
                    borderRadius: '4px',
                    padding: '12px 14px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <span className="badge badge-accent">{plan.action_type}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span className={`badge ${plan.status === 'APPROVED' ? 'badge-low' : 'badge-medium'}`}>{plan.status}</span>
                        <span className="mono" style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Plan #{plan.id}</span>
                      </div>
                    </div>

                    <div style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-primary)', marginBottom: '4px' }}>
                      {plan.title}
                    </div>

                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                      Proposed by <strong style={{ color: 'var(--text-secondary)' }}>{plan.proposer_username || `User #${plan.proposed_by}`}</strong>
                    </div>

                    {/* Role-Gated Action Buttons */}
                    {canApprove && (
                      <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                        <button
                          onClick={() => handleApprove(plan.id)}
                          disabled={actionLoading}
                          className="btn-success"
                          style={{ flex: 1 }}
                        >
                          Approve Plan
                        </button>
                        <button
                          onClick={() => handleModify(plan.id)}
                          disabled={actionLoading}
                          className="btn-secondary"
                          style={{ flex: 1 }}
                        >
                          Request Revision
                        </button>
                        <button
                          onClick={() => handleReject(plan.id)}
                          disabled={actionLoading}
                          className="btn-danger"
                          style={{ flex: 1 }}
                        >
                          Reject
                        </button>
                      </div>
                    )}

                    {canExecute && (
                      <div style={{ marginTop: '8px' }}>
                        <button
                          onClick={() => handleExecute(plan.id)}
                          disabled={actionLoading}
                          className="btn-primary"
                          style={{ width: '100%' }}
                        >
                          Execute Stock Reservation & Disruption Recovery
                        </button>
                      </div>
                    )}

                    {!canApprove && !canExecute && (
                      <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontStyle: 'italic', marginTop: '6px' }}>
                        {isProposer
                          ? 'Self-approval blocked: Separation of duties requires another approver.'
                          : plan.status === 'APPROVED'
                          ? 'Plan approved. Awaiting Warehouse Operator to execute.'
                          : 'Review requires Supply Chain Manager or Procurement Approver.'}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Panel 4: Recovery Progress & Governance */}
        <div className="surface" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div>
              <h3 style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-primary)' }}>
                Recovery Pipeline
              </h3>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Status transition lifecycle enforcement</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', flex: 1 }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '10px 14px',
              backgroundColor: 'var(--bg-surface-subtle)',
              borderRadius: '4px',
              border: '1px solid var(--border-subtle)'
            }}>
              <div>
                <div style={{ fontSize: '12px', fontWeight: '500', color: 'var(--text-primary)' }}>Plans Proposed</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Operations Analyst submissions</div>
              </div>
              <span className="mono" style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-primary)' }}>
                {recoveryProgress.proposed || 0}
              </span>
            </div>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '10px 14px',
              backgroundColor: 'var(--bg-surface-subtle)',
              borderRadius: '4px',
              border: '1px solid var(--border-subtle)'
            }}>
              <div>
                <div style={{ fontSize: '12px', fontWeight: '500', color: 'var(--text-primary)' }}>Approved (Pending Execution)</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Authorized by SCM / Procurement</div>
              </div>
              <span className="mono" style={{ fontSize: '16px', fontWeight: '700', color: '#f59e0b' }}>
                {recoveryProgress.approved || 0}
              </span>
            </div>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '10px 14px',
              backgroundColor: 'var(--bg-surface-subtle)',
              borderRadius: '4px',
              border: '1px solid var(--border-subtle)'
            }}>
              <div>
                <div style={{ fontSize: '12px', fontWeight: '500', color: 'var(--text-primary)' }}>Successfully Executed</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Atomic inventory reservation committed</div>
              </div>
              <span className="mono" style={{ fontSize: '16px', fontWeight: '700', color: '#10b981' }}>
                {recoveryProgress.executed || 0}
              </span>
            </div>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '10px 14px',
              backgroundColor: 'var(--bg-surface-subtle)',
              borderRadius: '4px',
              border: '1px solid var(--border-subtle)'
            }}>
              <div>
                <div style={{ fontSize: '12px', fontWeight: '500', color: 'var(--text-primary)' }}>Rejected Plans</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Logged in audit trail with reason</div>
              </div>
              <span className="mono" style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-muted)' }}>
                {recoveryProgress.rejected || 0}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
