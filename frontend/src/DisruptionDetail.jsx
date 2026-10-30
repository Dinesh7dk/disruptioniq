import React, { useState, useEffect } from 'react';
import { apiFetch } from './api';

export default function DisruptionDetail({ disruptionId, onBack, currentUser, onPlanProposed }) {
  const [disruption, setDisruption] = useState(null);
  const [loading, setLoading] = useState(true);
  const [proposing, setProposing] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState({ type: '', text: '' });
  const [activeTab, setActiveTab] = useState('options'); // 'options' | 'cascade' | 'orders'

  // What-If Simulation State
  const [simulations, setSimulations] = useState({});
  const [simulating, setSimulating] = useState({});
  const [simulatingAll, setSimulatingAll] = useState(false);
  const [inspectedIndex, setInspectedIndex] = useState(0);

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

  const handleSimulate = async (opt, index) => {
    setSimulating(prev => ({ ...prev, [index]: true }));
    setFeedbackMsg({ type: '', text: '' });
    try {
      const res = await apiFetch(`/disruptions/${disruptionId}/simulate`, {
        method: 'POST',
        body: JSON.stringify({
          action_type: opt.type,
          parameters: {
            source_warehouse_id: opt.details?.source_warehouse_id,
            quantity: opt.details?.quantity || opt.details?.immediate_quantity,
            order_id: opt.order?.id,
          },
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Simulation failed.');
      }
      setSimulations(prev => ({ ...prev, [index]: data }));
      setInspectedIndex(index);
    } catch (err) {
      setFeedbackMsg({ type: 'error', text: `Simulation error: ${err.message}` });
    } finally {
      setSimulating(prev => ({ ...prev, [index]: false }));
    }
  };

  const handleSimulateAll = async () => {
    if (!disruption?.options?.length) return;
    setSimulatingAll(true);
    const topOpts = disruption.options.slice(0, 4);
    for (let i = 0; i < topOpts.length; i++) {
      await handleSimulate(topOpts[i], i);
    }
    setSimulatingAll(false);
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
        },
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
        text: `Plan #${data.id} proposed successfully. It is now awaiting manager approval.`,
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
  const options = disruption.options || [];
  const activeSim = simulations[inspectedIndex];

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
          fontSize: '13px',
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

      {/* View Switcher Tabs: Compare Options & Simulator | Cascade Map | Affected Orders */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--color-line)', paddingBottom: '4px' }}>
        <button
          type="button"
          onClick={() => setActiveTab('options')}
          className={activeTab === 'options' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '12px', padding: '4px 12px' }}
        >
          Compare recovery options &amp; What-If simulator ({options.length})
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

      {/* Tab 1: Compare Recovery Options & What-If Simulator Panel */}
      {activeTab === 'options' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {/* Main Side-by-Side Comparison Panel */}
          <div className="desk-panel" style={{ overflowX: 'auto' }}>
            <div style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--color-line)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '8px',
            }}>
              <div>
                <h2 style={{ fontSize: '15px', fontWeight: '600' }}>
                  Compare recovery options side by side
                </h2>
                <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                  Evaluated with deterministic feasibility, freight cost models, and zero database mutations.
                </p>
              </div>
              <button
                type="button"
                onClick={handleSimulateAll}
                disabled={simulatingAll || options.length === 0}
                className="btn-secondary"
                style={{ fontSize: '12px', padding: '6px 12px' }}
              >
                {simulatingAll ? 'Simulating all options...' : 'Simulate all options side-by-side'}
              </button>
            </div>

            {options.length === 0 ? (
              <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
                No feasible options meet the delivery deadlines.
              </div>
            ) : (
              <table className="ops-table" style={{ minWidth: '760px' }}>
                <thead>
                  <tr>
                    <th style={{ width: '180px', backgroundColor: '#EBF0EB' }}>Comparison attribute</th>
                    {options.slice(0, 4).map((opt, i) => (
                      <th
                        key={i}
                        onClick={() => setInspectedIndex(i)}
                        style={{
                          backgroundColor: inspectedIndex === i ? 'var(--color-primary-subtle)' : (i === 0 ? '#EEF2EC' : '#F1F3EE'),
                          borderLeft: inspectedIndex === i ? '2px solid var(--color-primary)' : '1px solid var(--color-line)',
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: '600', color: inspectedIndex === i ? 'var(--color-primary)' : 'var(--color-ink)' }}>
                            Option {i + 1} {i === 0 ? '(Recommended)' : ''}
                          </span>
                          {simulations[i] && (
                            <span style={{ fontSize: '10px', color: 'var(--color-primary)', fontWeight: '600' }}>
                              Simulated
                            </span>
                          )}
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
                        {simulations[i]?.new_delivery_date || opt.new_delivery_date}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Meets customer due date?</td>
                    {options.slice(0, 4).map((opt, i) => {
                      const meets = simulations[i] ? simulations[i].meets_deadline : opt.meets_deadline;
                      return (
                        <td key={i}>
                          {meets ? (
                            <span className="severity-pill severity-pill-low">Yes (On time)</span>
                          ) : (
                            <span className="severity-pill severity-pill-high">No (Late)</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Estimated freight cost</td>
                    {options.slice(0, 4).map((opt, i) => (
                      <td key={i} className="num" style={{ fontWeight: '600' }}>
                        Rs. {(simulations[i]?.cost ?? opt.cost).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Simulated risk score change</td>
                    {options.slice(0, 4).map((opt, i) => {
                      const sim = simulations[i];
                      if (!sim) {
                        return (
                          <td key={i} style={{ color: 'var(--color-muted-ink)', fontSize: '12px' }}>
                            Not simulated yet
                          </td>
                        );
                      }
                      const red = sim.overall_after?.risk_reduction ?? 0;
                      return (
                        <td key={i}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span className="num" style={{ fontWeight: '600', color: 'var(--color-risk-low)' }}>
                              {sim.overall_before?.avg_risk_score} &rarr; {sim.overall_after?.avg_risk_score}
                            </span>
                            <span className="severity-pill severity-pill-low" style={{ fontSize: '11px' }}>
                              -{red} pts
                            </span>
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Other orders sharing stock</td>
                    {options.slice(0, 4).map((opt, i) => {
                      const sim = simulations[i];
                      if (!sim) {
                        return (
                          <td key={i} style={{ color: 'var(--color-muted-ink)', fontSize: '12px' }}>
                            Click simulate to verify
                          </td>
                        );
                      }
                      const colCount = sim.collateral_orders_affected?.length || 0;
                      const hasShortfall = sim.collateral_orders_affected?.some(c => c.deficit > 0);
                      return (
                        <td key={i}>
                          {colCount === 0 ? (
                            <span style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                              None affected
                            </span>
                          ) : (
                            <span
                              className={`severity-pill ${hasShortfall ? 'severity-pill-high' : 'severity-pill-medium'}`}
                              style={{ cursor: 'pointer' }}
                              onClick={() => setInspectedIndex(i)}
                            >
                              {colCount} order{colCount > 1 ? 's' : ''} affected {hasShortfall ? '(Shortfall)' : '(Buffer safe)'}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Action details</td>
                    {options.slice(0, 4).map((opt, i) => (
                      <td key={i} style={{ fontSize: '12px', color: 'var(--color-muted-ink)', lineHeight: '1.4' }}>
                        {simulations[i]?.action_summary || opt.details?.description}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: '600', color: 'var(--color-muted-ink)' }}>Simulation &amp; Proposal</td>
                    {options.slice(0, 4).map((opt, i) => (
                      <td key={i}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          <button
                            type="button"
                            onClick={() => handleSimulate(opt, i)}
                            disabled={simulating[i]}
                            className="btn-secondary"
                            style={{ fontSize: '11px', padding: '4px 8px', width: '100%' }}
                          >
                            {simulating[i] ? 'Simulating...' : (simulations[i] ? 'Re-simulate' : 'Simulate what-if')}
                          </button>
                          <button
                            type="button"
                            onClick={() => handlePropose(opt)}
                            disabled={proposing}
                            className={i === 0 ? 'btn-primary' : 'btn-secondary'}
                            style={{ fontSize: '11px', padding: '5px 8px', width: '100%' }}
                          >
                            {i === 0 ? 'Propose recommended' : 'Propose option'}
                          </button>
                        </div>
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            )}
          </div>

          {/* Detailed What-If Simulation Inspection Box */}
          {activeSim && (
            <div className="desk-panel" style={{ padding: '16px 20px', borderLeft: '4px solid var(--color-primary)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <h3 style={{ fontSize: '15px', fontWeight: '700' }}>
                    What-If simulation result: Option {inspectedIndex + 1} ({activeSim.action_type})
                  </h3>
                  <div style={{ fontSize: '12px', color: 'var(--color-muted-ink)', marginTop: '2px' }}>
                    Executed inside a sandboxed transaction and strictly rolled back. Database row counts and stock values remain unchanged.
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                  <div style={{ fontSize: '12px', textAlign: 'right' }}>
                    <div style={{ color: 'var(--color-muted-ink)' }}>Simulated landed cost</div>
                    <div className="num" style={{ fontWeight: '700', fontSize: '14px' }}>
                      Rs. {activeSim.cost?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div style={{ fontSize: '12px', textAlign: 'right' }}>
                    <div style={{ color: 'var(--color-muted-ink)' }}>Average risk score</div>
                    <div className="num" style={{ fontWeight: '700', fontSize: '14px', color: 'var(--color-risk-low)' }}>
                      {activeSim.overall_before?.avg_risk_score} &rarr; {activeSim.overall_after?.avg_risk_score} (-{activeSim.overall_after?.risk_reduction} pts)
                    </div>
                  </div>
                </div>
              </div>

              {/* Before vs After Impact on Orders directly in Disruption */}
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ fontSize: '13px', fontWeight: '600', marginBottom: '8px', color: 'var(--color-ink)' }}>
                  Direct order recovery before vs after comparison
                </h4>
                <table className="ops-table">
                  <thead>
                    <tr>
                      <th style={{ width: '85px' }}>Order</th>
                      <th>Customer</th>
                      <th style={{ width: '85px' }}>Due date</th>
                      <th style={{ width: '100px' }}>Delivery date</th>
                      <th style={{ width: '80px' }}>Buffer</th>
                      <th style={{ width: '80px' }}>Shortfall</th>
                      <th style={{ width: '120px' }}>Risk score</th>
                      <th>Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeSim.affected_orders?.map((ord) => (
                      <tr key={ord.order_id}>
                        <td className="num" style={{ fontWeight: '600' }}>{ord.order_code}</td>
                        <td>{ord.customer}</td>
                        <td className="num">{ord.due_date}</td>
                        <td className="num">
                          <span style={{ textDecoration: 'line-through', color: 'var(--color-muted-ink)', marginRight: '6px' }}>
                            {ord.before?.delivery_date}
                          </span>
                          <span style={{ fontWeight: '600', color: 'var(--color-primary)' }}>
                            {ord.after?.delivery_date}
                          </span>
                        </td>
                        <td className="num">
                          {ord.before?.buffer_days}d &rarr; <strong>{ord.after?.buffer_days}d</strong>
                        </td>
                        <td className="num">
                          {ord.before?.shortfall} &rarr; <strong>{ord.after?.shortfall}</strong>
                        </td>
                        <td className="num">
                          <span className={`severity-pill severity-pill-${ord.before?.risk_level.toLowerCase()}`} style={{ marginRight: '4px' }}>
                            {ord.before?.risk_score}
                          </span>
                          &rarr;
                          <span className={`severity-pill severity-pill-${ord.after?.risk_level.toLowerCase()}`} style={{ marginLeft: '4px' }}>
                            {ord.after?.risk_score}
                          </span>
                        </td>
                        <td>
                          <span className={`severity-pill ${ord.status === 'IMPROVED' ? 'severity-pill-low' : 'severity-pill-medium'}`}>
                            {ord.status} ({ord.risk_score_delta} pts)
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Collateral Orders Sharing Same Stock */}
              <div>
                <h4 style={{ fontSize: '13px', fontWeight: '600', marginBottom: '8px', color: 'var(--color-ink)' }}>
                  Collateral impact: Other customer orders sharing the same inventory stock
                </h4>
                {activeSim.collateral_orders_affected?.length === 0 ? (
                  <div style={{ fontSize: '13px', color: 'var(--color-muted-ink)', padding: '8px 0' }}>
                    No other orders share stock with this recovery action. Zero collateral impact.
                  </div>
                ) : (
                  <table className="ops-table">
                    <thead>
                      <tr>
                        <th style={{ width: '85px' }}>Order</th>
                        <th>Customer</th>
                        <th style={{ width: '85px' }}>Due date</th>
                        <th>Warehouse</th>
                        <th className="numeric" style={{ width: '80px' }}>Order qty</th>
                        <th className="numeric" style={{ width: '95px' }}>Stock before</th>
                        <th className="numeric" style={{ width: '95px' }}>Stock after</th>
                        <th style={{ width: '130px' }}>Impact status</th>
                        <th>Analysis note</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeSim.collateral_orders_affected?.map((col) => (
                        <tr key={col.order_id} className={col.deficit > 0 ? 'row-high' : ''}>
                          <td className="num" style={{ fontWeight: '600' }}>{col.order_code}</td>
                          <td>{col.customer}</td>
                          <td className="num">{col.due_date}</td>
                          <td>{col.warehouse_city}</td>
                          <td className="numeric num">{col.order_quantity}</td>
                          <td className="numeric num">{col.stock_before}</td>
                          <td className="numeric num" style={{ fontWeight: '600', color: col.deficit > 0 ? 'var(--color-risk-high)' : 'inherit' }}>
                            {col.stock_after}
                          </td>
                          <td>
                            <span className={`severity-pill ${col.deficit > 0 ? 'severity-pill-high' : 'severity-pill-medium'}`}>
                              {col.deficit > 0 ? `Shortfall: ${col.deficit}` : 'Buffer reduced'}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                            {col.impact_note}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
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
            borderRadius: 'var(--radius-panel)',
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
