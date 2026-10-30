import React, { useState, useEffect } from 'react';
import { apiFetch } from './api';

export default function DisruptionDetail({ disruptionId, onBack, currentUser, onPlanProposed }) {
  const [disruption, setDisruption] = useState(null);
  const [loading, setLoading] = useState(true);
  const [proposing, setProposing] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState({ type: '', text: '' });

  useEffect(() => {
    fetchDetail();
  }, [disruptionId]);

  const fetchDetail = async () => {
    setLoading(true);
    setFeedbackMsg({ type: '', text: '' });
    try {
      const res = await apiFetch(`/disruptions/${disruptionId}`);
      if (!res.ok) {
        throw new Error(`Failed to load disruption details (HTTP ${res.status})`);
      }
      const data = await res.json();
      setDisruption(data);
    } catch (err) {
      setFeedbackMsg({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handlePropose = async (opt) => {
    setProposing(true);
    setFeedbackMsg({ type: '', text: '' });
    try {
      const payload = {
        title: `${opt.type}: ${opt.details?.description || 'Recovery action'}`,
        action_type: opt.type,
        description: opt.details?.description || '',
        plan_payload: {
          order_id: opt.order?.id,
          order_code: opt.order?.code,
          source_warehouse_id: opt.details?.source_warehouse_id,
          product_code: opt.details?.product_code,
          quantity: opt.details?.quantity || opt.details?.immediate_quantity,
          cost: opt.cost,
          new_delivery_date: opt.new_delivery_date,
          meets_deadline: opt.meets_deadline,
        }
      };

      const res = await apiFetch(`/disruptions/${disruptionId}/plans`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to propose recovery plan');
      }

      setFeedbackMsg({
        type: 'success',
        text: `Plan #${data.id} proposed successfully! Status: PENDING_APPROVAL. Awaiting manager authorization.`
      });
      fetchDetail();
      if (onPlanProposed) onPlanProposed();
    } catch (err) {
      setFeedbackMsg({ type: 'error', text: err.message });
    } finally {
      setProposing(false);
    }
  };

  if (loading) {
    return (
      <div style={{ maxWidth: '1000px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div className="skeleton" style={{ height: '40px', width: '160px' }} />
        <div className="skeleton" style={{ height: '120px', width: '100%' }} />
        <div className="skeleton" style={{ height: '140px', width: '100%' }} />
        <div className="skeleton" style={{ height: '260px', width: '100%' }} />
      </div>
    );
  }

  if (!disruption) {
    return (
      <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
        <button onClick={onBack} className="btn-secondary" style={{ marginBottom: '16px' }}>
          ← Back to Dashboard
        </button>
        <div className="surface" style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Disruption details could not be found.
        </div>
      </div>
    );
  }

  const isLLM = disruption.ai_source === 'GEMINI_LLM';
  const sourceLabel = isLLM ? 'Google Gemini 2.5 Flash' : 'Deterministic Rule-Based Fallback';

  return (
    <div style={{ maxWidth: '1050px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={onBack} className="btn-secondary">
          ← Back to Dashboard
        </button>
        <div className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Detected: {disruption.detected_at}
        </div>
      </div>

      {feedbackMsg.text && (
        <div style={{
          padding: '10px 14px',
          backgroundColor: feedbackMsg.type === 'error' ? 'var(--status-high-bg)' : 'var(--status-low-bg)',
          border: `1px solid ${feedbackMsg.type === 'error' ? 'var(--status-high-border)' : 'var(--status-low-border)'}`,
          borderRadius: '4px',
          color: feedbackMsg.type === 'error' ? 'var(--status-high-text)' : 'var(--status-low-text)',
          fontSize: '12px'
        }}>
          {feedbackMsg.text}
        </div>
      )}

      {/* Disruption Base Info Header */}
      <div className="surface">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <span className="badge badge-critical">{disruption.type}</span>
              <span className="badge badge-neutral">{disruption.status}</span>
              <span className="mono" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Disruption #{disruption.id}</span>
            </div>
            <h2 style={{ fontSize: '16px', color: 'var(--text-primary)', marginBottom: '6px' }}>
              {disruption.description}
            </h2>
            {disruption.shipment && (
              <div className="mono" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                Shipment: <strong>{disruption.shipment.code}</strong> | Status: <strong>{disruption.shipment.status}</strong> | Expected: {disruption.shipment.expected_arrival} | Current ETA: {disruption.shipment.current_eta} (+{disruption.shipment.delay_days} days)
              </div>
            )}
          </div>
        </div>
      </div>

      {/* AI Recommendation Summary Box */}
      <div className="surface" style={{ backgroundColor: 'var(--bg-surface-elevated)', borderColor: 'var(--border-strong)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <div className="kpi-label" style={{ color: 'var(--text-primary)' }}>
            AI Disruption Analysis & Recommended Recovery
          </div>
          <span className="badge" style={{
            backgroundColor: isLLM ? 'rgba(59, 130, 246, 0.15)' : 'rgba(100, 116, 139, 0.2)',
            borderColor: isLLM ? '#3b82f6' : '#64748b',
            color: isLLM ? '#93c5fd' : '#cbd5e1'
          }}>
            Source: {sourceLabel}
          </span>
        </div>

        <p style={{ fontSize: '13px', lineHeight: '1.6', color: 'var(--text-primary)', margin: 0 }}>
          {disruption.ai_summary || 'No AI summary generated for this disruption.'}
        </p>
      </div>

      {/* Affected Customer Orders Table */}
      <div className="surface" style={{ padding: '0', overflow: 'hidden' }}>
        <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-default)' }}>
          <h3 style={{ fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-primary)' }}>
            Impacted Customer Orders ({disruption.impacts?.length || 0})
          </h3>
        </div>

        <table className="data-table">
          <thead>
            <tr>
              <th>Order</th>
              <th>Customer</th>
              <th>Priority</th>
              <th>Due Date</th>
              <th>Shortfall</th>
              <th>Risk Score</th>
              <th>Contributing Factors</th>
            </tr>
          </thead>
          <tbody>
            {disruption.impacts?.length === 0 ? (
              <tr>
                <td colSpan="7" style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                  No customer orders affected.
                </td>
              </tr>
            ) : (
              disruption.impacts.map((imp) => (
                <tr key={imp.id}>
                  <td className="mono" style={{ fontWeight: '600', color: 'var(--text-primary)' }}>{imp.order_code}</td>
                  <td>{imp.customer}</td>
                  <td>
                    <span className={`badge ${imp.priority === 'HIGH' ? 'badge-critical' : 'badge-medium'}`}>
                      {imp.priority}
                    </span>
                  </td>
                  <td className="mono">{imp.due_date}</td>
                  <td className="mono" style={{ color: '#f59e0b' }}>{imp.units_at_risk} units</td>
                  <td>
                    <span className="badge badge-critical mono">
                      {imp.risk_score} / 100
                    </span>
                  </td>
                  <td style={{ fontSize: '11px', color: 'var(--text-muted)', maxWidth: '300px' }}>
                    {imp.reasons?.join('; ') || '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Verified Feasible Recovery Options */}
      <div className="surface" style={{ padding: '0', overflow: 'hidden' }}>
        <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-default)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-primary)' }}>
              Verified Feasible Recovery Options ({disruption.options?.length || 0})
            </h3>
            <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
              Pure deterministic Python calculations (deadlines, network stock, and logistics cost verified)
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', backgroundColor: 'var(--border-subtle)' }}>
          {disruption.options?.length === 0 ? (
            <div style={{ padding: '30px', textAlign: 'center', backgroundColor: 'var(--bg-surface)', color: 'var(--text-muted)' }}>
              No feasible recovery options meet the delivery deadlines.
            </div>
          ) : (
            disruption.options.map((opt, idx) => (
              <div
                key={idx}
                style={{
                  padding: '14px 16px',
                  backgroundColor: 'var(--bg-surface)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '12px'
                }}
              >
                <div style={{ flex: 1, minWidth: '300px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span className="badge badge-accent">{opt.type}</span>
                    {opt.order && (
                      <span className="mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                        For {opt.order.code} ({opt.order.customer})
                      </span>
                    )}
                    {opt.meets_deadline && (
                      <span className="badge badge-low">Meets Deadline</span>
                    )}
                  </div>

                  <div style={{ fontSize: '13px', color: 'var(--text-primary)', marginBottom: '4px' }}>
                    {opt.details?.description}
                  </div>

                  <div className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    New Delivery: <strong>{opt.new_delivery_date}</strong> | Estimated Cost: <strong>Rs. {opt.cost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>
                  </div>
                </div>

                <div>
                  <button
                    onClick={() => handlePropose(opt)}
                    disabled={proposing}
                    className="btn-primary"
                    style={{ whiteSpace: 'nowrap' }}
                  >
                    Propose This Plan
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
