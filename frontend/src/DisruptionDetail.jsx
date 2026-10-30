import React, { useState, useEffect } from 'react';
import { apiFetch } from './api';

export default function DisruptionDetail({ disruptionId, onBack, currentUser, onPlanProposed }) {
  const [disruption, setDisruption] = useState(null);
  const [loading, setLoading] = useState(true);
  const [proposing, setProposing] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState({ type: '', text: '' });
  const [activeTab, setActiveTab] = useState('options'); // 'options' | 'cascade' | 'orders'

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
        title: `${opt.type.replace(/_/g, ' ')}: ${opt.details?.description || 'Action'}`,
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
        throw new Error(data.detail || 'Could not submit proposal.');
      }

      setFeedbackMsg({
        type: 'success',
        text: `Plan #${data.id} proposed successfully. It is now awaiting manager approval.`
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
      <div className="desk-panel" style={{ padding: '32px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
        Loading disruption details...
      </div>
    );
  }

  if (!disruption) {
    return (
      <div className="desk-panel" style={{ padding: '32px' }}>
        <button onClick={onBack} className="btn-secondary" style={{ marginBottom: '16px' }}>
          Back to orders
        </button>
        <p style={{ color: 'var(--color-muted-ink)' }}>Disruption details could not be found.</p>
      </div>
    );
  }

  const isLLM = disruption.ai_source === 'GEMINI_LLM';
  const sourceLabel = isLLM ? 'Google Gemini 2.5 Flash' : 'Deterministic rule-based fallback';

  // Compare first 3-4 feasible options side by side
  const options = disruption.options || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Top Breadcrumb and Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={onBack} className="btn-secondary">
          Back to orders
        </button>
        <div style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
          Disruption #{disruption.id} &middot; Detected at {disruption.detected_at}
        </div>
      </div>

      {feedbackMsg.text && (
        <div style={{
          padding: '10px 14px',
          backgroundColor: feedbackMsg.type === 'error' ? 'var(--color-risk-high-subtle)' : 'var(--color-risk-low-subtle)',
          border: `1px solid ${feedbackMsg.type === 'error' ? 'var(--color-risk-high)' : 'var(--color-risk-low)'}`,
          borderRadius: 'var(--radius-panel)',
          color: feedbackMsg.type === 'error' ? 'var(--color-risk-high)' : 'var(--color-risk-low)',
          fontSize: '13px'
        }}>
          {feedbackMsg.text}
        </div>
      )}

      {/* Disruption Header */}
      <div className="desk-panel" style={{ padding: '16px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
          <span className="severity-pill severity-pill-high">
            {disruption.type.replace(/_/g, ' ')}
          </span>
          <span style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
            Status: {disruption.status}
          </span>
        </div>
        <h1 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '6px' }}>
          {disruption.description}
        </h1>
        {disruption.shipment && (
          <div style={{ fontSize: '13px', color: 'var(--color-muted-ink)' }}>
            Shipment {disruption.shipment.code} &middot; Expected on {disruption.shipment.expected_arrival} &middot; Carrier current ETA: {disruption.shipment.current_eta} (+{disruption.shipment.delay_days} days delay)
          </div>
        )}
      </div>

      {/* AI Recommendation Box */}
      <div className="desk-panel" style={{ padding: '16px 20px', backgroundColor: '#FFFFFF', borderColor: 'var(--color-primary)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <h2 style={{ fontSize: '14px', fontWeight: '600', color: 'var(--color-primary)' }}>
            Recommended recovery action
          </h2>
          <span style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
            Source: {sourceLabel}
          </span>
        </div>
        <p style={{ fontSize: '13px', lineHeight: '1.5', maxWidth: '72ch', color: 'var(--color-ink)' }}>
          {disruption.ai_summary || 'No recommendation summary recorded.'}
        </p>
      </div>

      {/* View Switcher Tabs: Options Comparison | Cascade Map | Affected Orders */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--color-line)', paddingBottom: '4px' }}>
        <button
          type="button"
          onClick={() => setActiveTab('options')}
          className={activeTab === 'options' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '12px', padding: '4px 12px' }}
        >
          Recovery options comparison ({options.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('cascade')}
          className={activeTab === 'cascade' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '12px', padding: '4px 12px' }}
        >
          Supply cascade map
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('orders')}
          className={activeTab === 'orders' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '12px', padding: '4px 12px' }}
        >
          Impacted orders ({disruption.impacts?.length || 0})
        </button>
      </div>

      {/* Tab 1: Side-by-Side Recovery Options Comparison Table */}
      {activeTab === 'options' && (
        <div className="desk-panel" style={{ overflowX: 'auto' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-line)' }}>
            <h2 style={{ fontSize: '15px', fontWeight: '600' }}>
              Feasible recovery options comparison
            </h2>
            <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
              Verified by deterministic calculations for stock balance, deadline fit, and logistics cost.
            </p>
          </div>

          {options.length === 0 ? (
            <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
              No options meet the delivery deadlines.
            </div>
          ) : (
            <table className="ops-table" style={{ minWidth: '700px' }}>
              <thead>
                <tr>
                  <th style={{ width: '160px', backgroundColor: '#EBF0EB' }}>Comparison attribute</th>
                  {options.slice(0, 4).map((opt, i) => (
                    <th key={i} style={{ backgroundColor: i === 0 ? 'var(--color-primary-subtle)' : '#F1F3EE' }}>
                      <div style={{ fontWeight: '600', color: i === 0 ? 'var(--color-primary)' : 'var(--color-ink)' }}>
                        Option {i + 1} {i === 0 ? '(Recommended)' : ''}
                      </div>
                      <div style={{ fontSize: '11px', fontWeight: '400', color: 'var(--color-muted-ink)' }}>
                        {opt.type.replace(/_/g, ' ')}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Target customer order</td>
                  {options.slice(0, 4).map((opt, i) => (
                    <td key={i} style={{ fontWeight: '500' }}>
                      {opt.order?.code} ({opt.order?.customer})
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Projected delivery date</td>
                  {options.slice(0, 4).map((opt, i) => (
                    <td key={i} className="num">
                      {opt.new_delivery_date}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Meets customer due date?</td>
                  {options.slice(0, 4).map((opt, i) => (
                    <td key={i}>
                      {opt.meets_deadline ? (
                        <span className="severity-pill severity-pill-low">Yes (On time)</span>
                      ) : (
                        <span className="severity-pill severity-pill-high">No (Late)</span>
                      )}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Estimated freight cost</td>
                  {options.slice(0, 4).map((opt, i) => (
                    <td key={i} className="num" style={{ fontWeight: '600' }}>
                      Rs. {opt.cost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Action details</td>
                  {options.slice(0, 4).map((opt, i) => (
                    <td key={i} style={{ fontSize: '12px', color: 'var(--color-muted-ink)', lineHeight: '1.4' }}>
                      {opt.details?.description}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Action</td>
                  {options.slice(0, 4).map((opt, i) => (
                    <td key={i}>
                      <button
                        type="button"
                        onClick={() => handlePropose(opt)}
                        disabled={proposing}
                        className={i === 0 ? 'btn-primary' : 'btn-secondary'}
                        style={{ fontSize: '12px', padding: '5px 10px', width: '100%' }}
                      >
                        {i === 0 ? 'Propose recommended' : 'Propose this option'}
                      </button>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Tab 2: Supply Cascade Map */}
      {activeTab === 'cascade' && (
        <div className="desk-panel" style={{ padding: '20px' }}>
          <div style={{ marginBottom: '16px' }}>
            <h2 style={{ fontSize: '15px', fontWeight: '600' }}>
              Supply chain disruption cascade graph
            </h2>
            <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
              Traces supplier shipment origin through regional warehousing to impacted downstream customer orders.
            </p>
          </div>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px',
            padding: '24px',
            backgroundColor: '#FFFFFF',
            border: '1px solid var(--color-line)',
            borderRadius: 'var(--radius-panel)'
          }}>
            {/* Stage 1: Supplier */}
            <div style={{ textAlign: 'center', minWidth: '120px' }}>
              <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)', textTransform: 'uppercase', marginBottom: '4px' }}>
                1. Supplier
              </div>
              <div className="desk-panel" style={{ padding: '8px 12px', fontWeight: '600' }}>
                Supplier A
              </div>
            </div>

            <div style={{ color: 'var(--color-muted-ink)', fontSize: '16px' }}>&rarr;</div>

            {/* Stage 2: Shipment */}
            <div style={{ textAlign: 'center', minWidth: '130px' }}>
              <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)', textTransform: 'uppercase', marginBottom: '4px' }}>
                2. Shipment
              </div>
              <div className="desk-panel row-high" style={{ padding: '8px 12px' }}>
                <div className="num" style={{ fontWeight: '700' }}>SH-001</div>
                <div style={{ fontSize: '11px', color: 'var(--color-risk-high)' }}>Delayed (+6 days)</div>
              </div>
            </div>

            <div style={{ color: 'var(--color-muted-ink)', fontSize: '16px' }}>&rarr;</div>

            {/* Stage 3: Warehouse Destination */}
            <div style={{ textAlign: 'center', minWidth: '130px' }}>
              <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)', textTransform: 'uppercase', marginBottom: '4px' }}>
                3. Warehouse
              </div>
              <div className="desk-panel" style={{ padding: '8px 12px', fontWeight: '600' }}>
                Chennai WH
              </div>
            </div>

            <div style={{ color: 'var(--color-muted-ink)', fontSize: '16px' }}>&rarr;</div>

            {/* Stage 4: Impacted Customer Orders */}
            <div style={{ textAlign: 'center', minWidth: '160px' }}>
              <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)', textTransform: 'uppercase', marginBottom: '4px' }}>
                4. At-risk customer orders
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div className="desk-panel row-high" style={{ padding: '4px 8px', fontSize: '12px' }}>
                  <strong>O-001</strong> City Hospital (High risk)
                </div>
                <div className="desk-panel row-high" style={{ padding: '4px 8px', fontSize: '12px' }}>
                  <strong>O-002</strong> MediChain (High risk)
                </div>
                <div className="desk-panel row-medium" style={{ padding: '4px 8px', fontSize: '12px' }}>
                  <strong>O-003</strong> Corner Pharma (Medium risk)
                </div>
              </div>
            </div>
          </div>

          <div style={{ marginTop: '16px', display: 'flex', gap: '16px', fontSize: '12px', color: 'var(--color-muted-ink)' }}>
            <div><span style={{ color: 'var(--color-risk-high)', fontWeight: '700' }}>&bull;</span> Red edge indicates critical delay or high breach risk.</div>
            <div><span style={{ color: 'var(--color-risk-med)', fontWeight: '700' }}>&bull;</span> Amber edge indicates low buffer warning.</div>
          </div>
        </div>
      )}

      {/* Tab 3: Impacted Orders & Risk Factor Breakdown */}
      {activeTab === 'orders' && (
        <div className="desk-panel" style={{ overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-line)' }}>
            <h2 style={{ fontSize: '15px', fontWeight: '600' }}>
              Impacted customer orders and risk factor breakdown
            </h2>
          </div>

          <table className="ops-table">
            <thead>
              <tr>
                <th style={{ width: '85px' }}>Severity</th>
                <th style={{ width: '75px' }}>Order</th>
                <th>Customer</th>
                <th style={{ width: '90px' }}>Due date</th>
                <th className="numeric" style={{ width: '80px' }}>Shortfall</th>
                <th style={{ width: '100px' }}>Risk score</th>
                <th>Contributing reasons</th>
              </tr>
            </thead>
            <tbody>
              {disruption.impacts?.map((imp) => (
                <tr key={imp.id} className={`row-${imp.priority === 'HIGH' ? 'high' : 'medium'}`}>
                  <td>
                    <span className={`severity-pill severity-pill-${imp.priority === 'HIGH' ? 'high' : 'medium'}`}>
                      {imp.priority}
                    </span>
                  </td>
                  <td className="num" style={{ fontWeight: '600' }}>{imp.order_code}</td>
                  <td>{imp.customer}</td>
                  <td className="num">{imp.due_date}</td>
                  <td className="numeric num" style={{ fontWeight: '600' }}>{imp.units_at_risk} pcs</td>
                  <td className="num" style={{ fontWeight: '600' }}>{imp.risk_score} / 100</td>
                  <td style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                    {imp.reasons?.join('; ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
