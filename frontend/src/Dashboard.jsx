import React from 'react';
import { AlertCircle, AlertTriangle, Clock, ArrowRight, ShieldAlert } from 'lucide-react';

export default function Dashboard({
  disruptions,
  affectedOrders,
  pendingApprovals,
  recoveryProgress,
  currentUser,
  onSelectDisruption,
  onApprovePlan,
  onRejectPlan,
  onModifyPlan,
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Stats Overview */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '16px'
      }}>
        <div className="card">
          <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>ACTIVE DISRUPTIONS</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', marginTop: '6px', color: 'var(--danger)' }}>
            {disruptions.length}
          </div>
        </div>
        <div className="card">
          <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>AFFECTED ORDERS AT RISK</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', marginTop: '6px', color: 'var(--warning)' }}>
            {affectedOrders.length}
          </div>
        </div>
        <div className="card">
          <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>PENDING APPROVALS</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', marginTop: '6px', color: 'var(--primary)' }}>
            {pendingApprovals.length}
          </div>
        </div>
        <div className="card">
          <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>EXECUTED RECOVERIES</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', marginTop: '6px', color: 'var(--success)' }}>
            {recoveryProgress.executed || 0}
          </div>
        </div>
      </div>

      {/* Main 4-Panel Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(480px, 1fr))',
        gap: '20px'
      }}>
        {/* Panel 1: Active Disruptions */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertCircle size={18} color="var(--danger)" /> Active Disruptions ({disruptions.length})
            </h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', flex: 1, overflowY: 'auto', maxHeight: '380px' }}>
            {disruptions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-dim)' }}>
                No open disruptions detected.
              </div>
            ) : (
              disruptions.map((d) => (
                <div
                  key={d.id}
                  onClick={() => onSelectDisruption(d)}
                  style={{
                    backgroundColor: 'var(--bg-subtle)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    padding: '12px',
                    cursor: 'pointer',
                    transition: 'border-color 0.15s ease'
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--primary)')}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border)')}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span className="badge badge-high">{d.type}</span>
                    <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>ID #{d.id}</span>
                  </div>
                  <div style={{ fontWeight: '500', fontSize: '13px', color: 'var(--text-main)', marginBottom: '6px' }}>
                    {d.description}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: 'var(--text-muted)' }}>
                    <span>Detected: {d.detected_at}</span>
                    <span style={{ color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      View Options <ArrowRight size={12} />
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Panel 2: Affected Orders Sorted by Risk */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ShieldAlert size={18} color="var(--warning)" /> Affected Orders Ranked by Risk
            </h3>
            <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Deterministic 0-100 Score</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', flex: 1, overflowY: 'auto', maxHeight: '380px' }}>
            {affectedOrders.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-dim)' }}>
                No customer orders affected.
              </div>
            ) : (
              affectedOrders.map((ord, idx) => {
                const reasons = typeof ord.risk_reasons === 'string'
                  ? JSON.parse(ord.risk_reasons || '[]')
                  : (ord.risk_reasons || []);

                return (
                  <div key={ord.order_id || idx} style={{
                    backgroundColor: 'var(--bg-subtle)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    padding: '12px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                      <div>
                        <strong style={{ color: 'var(--text-main)', fontSize: '14px' }}>{ord.order_code || ord.code}</strong>
                        <span style={{ marginLeft: '8px', color: 'var(--text-muted)', fontSize: '12px' }}>{ord.customer}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className={`badge badge-${(ord.risk_level || 'low').toLowerCase()}`}>
                          {ord.risk_level} ({ord.risk_score})
                        </span>
                      </div>
                    </div>

                    {/* Visible Risk Reasons */}
                    <div style={{ marginTop: '6px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      {reasons.slice(0, 3).map((r, rIdx) => (
                        <div key={rIdx} style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '5px' }}>
                          <span style={{ color: 'var(--warning)' }}>•</span> {r}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Panel 3: Pending Approvals (Role Gated) */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Clock size={18} color="var(--primary)" /> Pending Recovery Approvals ({pendingApprovals.length})
            </h3>
            <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Your Role: {currentUser?.role}</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', flex: 1, overflowY: 'auto', maxHeight: '380px' }}>
            {pendingApprovals.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-dim)' }}>
                No recovery plans awaiting approval.
              </div>
            ) : (
              pendingApprovals.map((plan) => {
                // Separation of duty and role checks
                const canApprove = (
                  (currentUser?.role === 'Supply Chain Manager' && ['REALLOCATE_STOCK', 'EXPEDITE_ORDER', 'PARTIAL_FULFIL'].includes(plan.action_type)) ||
                  (currentUser?.role === 'Procurement Approver' && plan.action_type === 'ALTERNATIVE_SUPPLIER')
                ) && (currentUser?.username !== plan.proposer_name);

                return (
                  <div key={plan.id} style={{
                    backgroundColor: 'var(--bg-subtle)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    padding: '12px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span className="badge badge-pending">{plan.action_type}</span>
                      <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Plan #{plan.id}</span>
                    </div>

                    <div style={{ fontWeight: '500', fontSize: '13px', marginBottom: '4px' }}>{plan.title}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                      Proposed by <strong>{plan.proposer_name || 'Operations Analyst'}</strong>
                    </div>

                    {/* Action buttons shown ONLY for permitted roles */}
                    {canApprove ? (
                      <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
                        <button
                          onClick={() => onApprovePlan(plan.id)}
                          style={{
                            flex: 1,
                            backgroundColor: 'var(--success)',
                            color: '#fff',
                            border: 'none',
                            padding: '6px 10px',
                            fontSize: '12px'
                          }}
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => onModifyPlan(plan.id)}
                          style={{
                            flex: 1,
                            backgroundColor: 'var(--primary)',
                            color: '#fff',
                            border: 'none',
                            padding: '6px 10px',
                            fontSize: '12px'
                          }}
                        >
                          Modify
                        </button>
                        <button
                          onClick={() => onRejectPlan(plan.id)}
                          style={{
                            flex: 1,
                            backgroundColor: 'var(--danger)',
                            color: '#fff',
                            border: 'none',
                            padding: '6px 10px',
                            fontSize: '12px'
                          }}
                        >
                          Reject
                        </button>
                      </div>
                    ) : (
                      <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontStyle: 'italic', marginTop: '6px' }}>
                        {currentUser?.username === plan.proposer_name
                          ? 'Self-approval prohibited (Separation of duties)'
                          : 'Requires Supply Chain Manager or Procurement Approver role'}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Panel 4: Recovery Progress */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 'bold' }}>Recovery Progress</h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', justifyContent: 'center', flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Plans Proposed</span>
              <span className="badge badge-open" style={{ fontSize: '14px', padding: '4px 12px' }}>
                {recoveryProgress.proposed || 0}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Approved (Pending Execution)</span>
              <span className="badge badge-approved" style={{ fontSize: '14px', padding: '4px 12px' }}>
                {recoveryProgress.approved || 0}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Successfully Executed</span>
              <span className="badge badge-executed" style={{ fontSize: '14px', padding: '4px 12px' }}>
                {recoveryProgress.executed || 0}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Rejected Plans</span>
              <span className="badge badge-rejected" style={{ fontSize: '14px', padding: '4px 12px' }}>
                {recoveryProgress.rejected || 0}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
