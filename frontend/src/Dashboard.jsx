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
  const [activeFilter, setActiveFilter] = useState('all'); // 'all' | 'high' | 'medium' | 'pending' | 'disruptions'
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [actionError, setActionError] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  // Filtered orders
  const filteredOrders = affectedOrders.filter((ord) => {
    if (activeFilter === 'high') return (ord.risk_score || 0) >= 70;
    if (activeFilter === 'medium') return (ord.risk_score || 0) >= 40 && (ord.risk_score || 0) < 70;
    return true;
  });

  const highRiskCount = affectedOrders.filter((o) => (o.risk_score || 0) >= 70).length;
  const pendingCount = pendingApprovals.filter((p) => p.status === 'PENDING_APPROVAL').length;
  const openDisruptionsCount = disruptions.filter((d) => d.status === 'OPEN').length;

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
        if (res.status === 403) {
          throw new Error('You proposed this plan, so someone else needs to approve it.');
        }
        throw new Error(data.detail || 'The plan could not be approved.');
      }
      setActionSuccess(`Plan #${planId} was approved and is now ready for warehouse execution.`);
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
        throw new Error(data.detail || 'The plan could not be rejected.');
      }
      setActionSuccess(`Plan #${planId} was rejected and logged.`);
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
        body: JSON.stringify({ note: `Changes requested by ${currentUser.username}` }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'The plan could not be marked for modification.');
      }
      setActionSuccess(`Plan #${planId} was returned to pending approval.`);
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
        throw new Error(data.detail || 'Execution failed. Stock levels may have changed.');
      }
      setActionSuccess(`Plan #${planId} was executed. Warehouse stock has been reserved.`);
      onRefreshData();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Alert Feedback Messages */}
      {actionError && (
        <div style={{
          padding: '10px 14px',
          backgroundColor: 'var(--color-risk-high-subtle)',
          border: '1px solid var(--color-risk-high)',
          borderRadius: 'var(--radius-panel)',
          color: 'var(--color-risk-high)',
          fontSize: '13px'
        }}>
          {actionError}
        </div>
      )}
      {actionSuccess && (
        <div style={{
          padding: '10px 14px',
          backgroundColor: 'var(--color-risk-low-subtle)',
          border: '1px solid var(--color-risk-low)',
          borderRadius: 'var(--radius-panel)',
          color: 'var(--color-risk-low)',
          fontSize: '13px'
        }}>
          {actionSuccess}
        </div>
      )}

      {/* Plain-Language Operational Status Line with Clickable Filters */}
      <div className="status-line">
        <span>Operational overview:</span>
        <div>
          <button
            type="button"
            onClick={() => setActiveFilter(activeFilter === 'high' ? 'all' : 'high')}
            className={`status-filter-btn ${activeFilter === 'high' ? 'active' : ''}`}
          >
            <span className="num">{highRiskCount}</span> orders
          </button>{' '}
          may miss their due date.
        </div>
        <div>
          <button
            type="button"
            onClick={() => setActiveFilter(activeFilter === 'pending' ? 'all' : 'pending')}
            className={`status-filter-btn ${activeFilter === 'pending' ? 'active' : ''}`}
          >
            <span className="num">{pendingCount}</span> plans
          </button>{' '}
          are waiting for approval.
        </div>
        <div>
          <button
            type="button"
            onClick={() => setActiveFilter(activeFilter === 'disruptions' ? 'all' : 'disruptions')}
            className={`status-filter-btn ${activeFilter === 'disruptions' ? 'active' : ''}`}
          >
            <span className="num">{openDisruptionsCount}</span> active
          </button>{' '}
          disruption reported in transit.
        </div>
        {activeFilter !== 'all' && (
          <button
            type="button"
            onClick={() => setActiveFilter('all')}
            className="btn-subtle"
            style={{ fontSize: '12px', marginLeft: 'auto' }}
          >
            Clear filter
          </button>
        )}
      </div>

      {/* Main Work Area: Table First */}
      <div style={{ display: 'grid', gridTemplateColumns: selectedOrder ? '1fr 380px' : '1fr', gap: 'var(--space-4)', alignItems: 'start' }}>
        
        {/* Ranked Order List (Primary Artifact) */}
        <div className="desk-panel" style={{ overflow: 'hidden' }}>
          <div style={{
            padding: '12px 16px',
            borderBottom: '1px solid var(--color-line)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div>
              <h2 style={{ fontSize: '16px', fontWeight: '600' }}>
                Customer orders ranked by risk
              </h2>
              <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                Deterministic risk score combines delivery due date, shortfall quantity, delay length, and customer priority.
              </p>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
              Showing {filteredOrders.length} orders
            </div>
          </div>

          <table className="ops-table">
            <thead>
              <tr>
                <th style={{ width: '85px' }}>Severity</th>
                <th style={{ width: '70px' }}>Order</th>
                <th>Customer</th>
                <th style={{ width: '90px' }}>Due date</th>
                <th className="numeric" style={{ width: '75px' }}>Shortfall</th>
                <th style={{ width: '120px' }}>Risk score</th>
                <th>Primary risk reasons</th>
                <th style={{ width: '80px', textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredOrders.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
                    No orders match the current filter.
                  </td>
                </tr>
              ) : (
                filteredOrders.map((ord) => {
                  const score = ord.risk_score || 0;
                  const severity = score >= 70 ? 'high' : (score >= 40 ? 'medium' : (score > 0 ? 'low' : 'none'));
                  const severityLabel = score >= 70 ? 'High' : (score >= 40 ? 'Medium' : (score > 0 ? 'Low' : 'None'));
                  const reasons = Array.isArray(ord.reasons) ? ord.reasons : [];
                  const isSelected = selectedOrder?.id === ord.id;

                  return (
                    <tr
                      key={ord.id}
                      className={`row-${severity} ${isSelected ? 'selected' : ''}`}
                      onClick={() => setSelectedOrder(ord)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <span className={`severity-pill severity-pill-${severity}`}>
                          <span
                            className="marker-dot"
                            style={{
                              backgroundColor: severity === 'high' ? 'var(--color-risk-high)'
                                : (severity === 'medium' ? 'var(--color-risk-med)'
                                : (severity === 'low' ? 'var(--color-risk-low)' : 'var(--color-muted-ink)'))
                            }}
                          />
                          {severityLabel}
                        </span>
                      </td>
                      <td className="num" style={{ fontWeight: '600' }}>
                        {ord.code}
                      </td>
                      <td>
                        <span style={{ fontWeight: '500' }}>{ord.customer}</span>
                      </td>
                      <td className="num" style={{ color: 'var(--color-muted-ink)' }}>
                        {ord.due_date}
                      </td>
                      <td className="numeric num" style={{ fontWeight: ord.units_at_risk > 0 ? '600' : '400' }}>
                        {ord.units_at_risk ? `${ord.units_at_risk} pcs` : '0'}
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          <div className="risk-bar-track">
                            <div
                              className="risk-bar-fill"
                              style={{
                                width: `${Math.min(100, score)}%`,
                                backgroundColor: severity === 'high' ? 'var(--color-risk-high)'
                                  : (severity === 'medium' ? 'var(--color-risk-med)' : 'var(--color-risk-low)')
                              }}
                            />
                          </div>
                          <span className="num" style={{ fontWeight: '600', fontSize: '12px' }}>
                            {score.toFixed(1)}
                          </span>
                        </div>
                      </td>
                      <td style={{ color: 'var(--color-muted-ink)', fontSize: '12px', maxWidth: '320px' }}>
                        {reasons.length > 0 ? reasons[0] : 'All delivery requirements met.'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedOrder(ord);
                          }}
                          className="btn-subtle"
                          style={{ fontSize: '12px' }}
                        >
                          Details
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Selected Order Detail Side Panel (Drawer) */}
        {selectedOrder && (
          <div className="desk-panel drawer-overlay" style={{ padding: '16px', position: 'sticky', top: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
              <div>
                <span className="num" style={{ fontSize: '18px', fontWeight: '700', color: 'var(--color-ink)' }}>
                  {selectedOrder.code}
                </span>
                <div style={{ fontSize: '13px', fontWeight: '500', color: 'var(--color-muted-ink)' }}>
                  {selectedOrder.customer}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedOrder(null)}
                className="btn-subtle"
                style={{ fontSize: '13px' }}
              >
                Close
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
              <div style={{ padding: '8px 10px', backgroundColor: '#F1F3EE', borderRadius: 'var(--radius-panel)' }}>
                <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)', textTransform: 'uppercase' }}>Delivery commitment</div>
                <div style={{ fontWeight: '600' }}>Due on {selectedOrder.due_date} ({selectedOrder.priority} priority)</div>
              </div>

              {/* Factor Contribution Breakdown */}
              {selectedOrder.breakdown && (
                <div>
                  <div style={{ fontSize: '12px', fontWeight: '600', marginBottom: '6px' }}>
                    Score breakdown ({selectedOrder.risk_score} points)
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px' }}>
                    {Object.entries(selectedOrder.breakdown).map(([factor, pts]) => (
                      <div key={factor} style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-muted-ink)' }}>
                        <span style={{ textTransform: 'capitalize' }}>{factor.replace(/_/g, ' ')}</span>
                        <span className="num" style={{ fontWeight: '500', color: 'var(--color-ink)' }}>+{pts} pts</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Order Lines */}
              {selectedOrder.lines && selectedOrder.lines.length > 0 && (
                <div>
                  <div style={{ fontSize: '12px', fontWeight: '600', marginBottom: '6px' }}>Order line items</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px' }}>
                    {selectedOrder.lines.map((ln, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--color-line)' }}>
                        <span>{ln.product_name} ({ln.product_code})</span>
                        <span className="num">{ln.quantity} pcs</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Link to Disruption */}
              {selectedOrder.disruption_id && (
                <div style={{ marginTop: '8px' }}>
                  <button
                    type="button"
                    onClick={() => {
                      const d = disruptions.find(x => x.id === selectedOrder.disruption_id) || { id: selectedOrder.disruption_id };
                      onSelectDisruption(d);
                    }}
                    className="btn-primary"
                    style={{ width: '100%', padding: '8px' }}
                  >
                    Compare recovery options for disruption #{selectedOrder.disruption_id}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Active Disruptions Section */}
      <div className="desk-panel" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: '600' }}>Reported supply disruptions</h2>
            <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
              Shipments delayed by carrier tracking or inventory shortages flagged at warehouse.
            </p>
          </div>
        </div>

        <table className="ops-table">
          <thead>
            <tr>
              <th style={{ width: '60px' }}>ID</th>
              <th style={{ width: '140px' }}>Type</th>
              <th>Description</th>
              <th style={{ width: '120px' }}>Shipment / target</th>
              <th style={{ width: '100px' }}>Orders at risk</th>
              <th style={{ width: '100px', textAlign: 'right' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {disruptions.length === 0 ? (
              <tr>
                <td colSpan="6" style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
                  No active disruptions. Imported shipments are checked automatically.
                </td>
              </tr>
            ) : (
              disruptions.map((d) => (
                <tr key={d.id} onClick={() => onSelectDisruption(d)} style={{ cursor: 'pointer' }}>
                  <td className="num">#{d.id}</td>
                  <td>
                    <span className="severity-pill severity-pill-high">
                      {d.type.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td>
                    <div style={{ fontWeight: '500' }}>{d.description}</div>
                  </td>
                  <td className="num" style={{ color: 'var(--color-muted-ink)' }}>
                    {d.shipment?.code || (d.warehouse ? `${d.warehouse.city} WH` : '—')}
                  </td>
                  <td className="num">
                    {d.affected_orders_count || 0} orders
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectDisruption(d);
                      }}
                      className="btn-primary"
                      style={{ fontSize: '12px', padding: '4px 8px' }}
                    >
                      Compare options
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pending Approvals & Execution Queue */}
      <div className="desk-panel" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-line)' }}>
          <h2 style={{ fontSize: '16px', fontWeight: '600' }}>
            Recovery approval queue ({pendingApprovals.length})
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
            Permitted manager review required before inventory reservation or carrier rerouting.
          </p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {pendingApprovals.length === 0 ? (
            <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--color-muted-ink)', fontSize: '13px' }}>
              No recovery plans are currently waiting for approval.
            </div>
          ) : (
            pendingApprovals.map((plan) => {
              const isProposer = (currentUser?.id === plan.proposed_by) || (currentUser?.username === plan.proposer_username);
              
              const canApprove = (
                (currentUser?.role === 'Supply Chain Manager' && ['REALLOCATE_STOCK', 'EXPEDITE_ORDER', 'PARTIAL_FULFIL'].includes(plan.action_type)) ||
                (currentUser?.role === 'Procurement Approver' && plan.action_type === 'ALTERNATIVE_SUPPLIER') ||
                (currentUser?.role === 'Administrator')
              ) && !isProposer && plan.status === 'PENDING_APPROVAL';

              const canExecute = (
                currentUser?.role === 'Warehouse Operator' || currentUser?.role === 'Administrator'
              ) && plan.status === 'APPROVED';

              return (
                <div
                  key={plan.id}
                  style={{
                    padding: '12px 16px',
                    borderBottom: '1px solid var(--color-line)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: '12px'
                  }}
                >
                  <div style={{ maxWidth: '650px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span className="severity-pill severity-pill-none">
                        {plan.action_type.replace(/_/g, ' ')}
                      </span>
                      <span className="num" style={{ fontWeight: '600' }}>Plan #{plan.id}</span>
                      <span style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>Status: {plan.status}</span>
                    </div>
                    <div style={{ fontSize: '14px', fontWeight: '500', color: 'var(--color-ink)' }}>
                      {plan.title}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--color-muted-ink)', marginTop: '2px' }}>
                      Proposed by {plan.proposer_username || `User #${plan.proposed_by}`}
                    </div>
                  </div>

                  <div>
                    {canApprove && (
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          type="button"
                          onClick={() => handleApprove(plan.id)}
                          disabled={actionLoading}
                          className="btn-primary"
                        >
                          Approve plan
                        </button>
                        <button
                          type="button"
                          onClick={() => handleModify(plan.id)}
                          disabled={actionLoading}
                          className="btn-secondary"
                        >
                          Request revision
                        </button>
                        <button
                          type="button"
                          onClick={() => handleReject(plan.id)}
                          disabled={actionLoading}
                          className="btn-danger"
                        >
                          Reject plan
                        </button>
                      </div>
                    )}

                    {canExecute && (
                      <button
                        type="button"
                        onClick={() => handleExecute(plan.id)}
                        disabled={actionLoading}
                        className="btn-primary"
                      >
                        Execute plan (reserve stock)
                      </button>
                    )}

                    {!canApprove && !canExecute && (
                      <span style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                        {isProposer
                          ? 'You proposed this plan, so someone else needs to approve it.'
                          : plan.status === 'APPROVED'
                          ? 'Approved. Waiting for warehouse operator to execute.'
                          : 'Review requires Supply Chain Manager or Procurement Approver.'}
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
