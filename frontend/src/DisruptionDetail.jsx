import React, { useState, useEffect, useMemo, useCallback } from 'react';
import ReactFlow, { Background, Controls, Handle, Position, MarkerType } from 'reactflow';
import 'reactflow/dist/style.css';
import { apiFetch } from './api';

// Custom node component for ReactFlow cascade diagram
function CascadeNode({ data, selected }) {
  const isOrder = data.entity_type === 'order';
  const isShipment = data.entity_type === 'shipment';
  const isSupplier = data.entity_type === 'supplier';
  const isWarehouse = data.entity_type === 'warehouse';
  const isCustomer = data.entity_type === 'customer';

  let borderColor = 'var(--color-line)';
  let bgColor = '#FFFFFF';
  let badgeColor = 'var(--color-muted-ink)';

  if (isOrder) {
    if (data.risk_level === 'HIGH') {
      borderColor = 'var(--color-risk-high)';
      bgColor = '#FDF2F2';
      badgeColor = 'var(--color-risk-high)';
    } else if (data.risk_level === 'MEDIUM') {
      borderColor = 'var(--color-risk-medium)';
      bgColor = '#FEF9F0';
      badgeColor = 'var(--color-risk-medium)';
    } else {
      borderColor = 'var(--color-risk-low)';
      bgColor = '#F2F8F4';
      badgeColor = 'var(--color-risk-low)';
    }
  } else if (isShipment && (data.delay_days > 0 || data.status === 'DELAYED')) {
    borderColor = 'var(--color-risk-high)';
    bgColor = '#FDF6F6';
  } else if (isWarehouse) {
    borderColor = 'var(--color-primary)';
    bgColor = '#F8FBFB';
  } else if (isSupplier) {
    borderColor = '#8B9B90';
    bgColor = '#FAFBF9';
  } else if (isCustomer) {
    borderColor = '#5A6A6E';
    bgColor = '#F7F8F7';
  }

  return (
    <div
      style={{
        padding: '10px 14px',
        borderRadius: 'var(--radius-panel)',
        border: `2px solid ${borderColor}`,
        backgroundColor: bgColor,
        minWidth: isOrder ? '160px' : '130px',
        boxShadow: selected ? '0 0 0 2px var(--color-primary)' : 'none',
        cursor: isOrder ? 'pointer' : 'default',
        transition: 'all 0.15s ease',
        fontFamily: "'Public Sans', system-ui, sans-serif",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#5A6A6E', width: 6, height: 6 }} />
      <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-muted-ink)', fontWeight: '600', marginBottom: '3px' }}>
        {data.entity_type}
      </div>
      <div style={{ fontSize: '13px', fontWeight: '700', color: 'var(--color-ink)', lineHeight: '1.2' }}>
        {data.label}
      </div>

      {isOrder && (
        <div style={{ marginTop: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
            <span
              className={`severity-pill severity-pill-${data.risk_level?.toLowerCase()}`}
              style={{ fontSize: '10px', padding: '1px 6px', fontWeight: '700' }}
            >
              {data.risk_level}
            </span>
            <span className="num" style={{ fontSize: '11px', fontWeight: '700', color: badgeColor }}>
              {data.risk_score} pts
            </span>
          </div>
          <div style={{ fontSize: '10px', color: 'var(--color-muted-ink)', marginTop: '4px', textAlign: 'center' }}>
            Click &rarr; waterfall
          </div>
        </div>
      )}

      {isShipment && data.delay_days > 0 && (
        <div style={{ fontSize: '11px', color: 'var(--color-risk-high)', fontWeight: '600', marginTop: '4px' }}>
          +{data.delay_days}d delay
        </div>
      )}

      {isCustomer && (
        <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)', marginTop: '2px' }}>
          Customer
        </div>
      )}

      <Handle type="source" position={Position.Right} style={{ background: '#5A6A6E', width: 6, height: 6 }} />
    </div>
  );
}

// Risk waterfall stacked bar factor configuration
const WATERFALL_FACTORS = [
  { key: 'urgency', label: 'Delivery Urgency', max: 35, color: '#B3261E' },
  { key: 'delay_length', label: 'Delay Length', max: 25, color: '#C77D0A' },
  { key: 'customer_priority', label: 'Customer Priority', max: 20, color: '#0F5E63' },
  { key: 'shortfall', label: 'Stock Shortfall', max: 10, color: '#35557A' },
  { key: 'alt_stock', label: 'Alt Stock Scarcity', max: 10, color: '#5A6A6E' },
];

export default function DisruptionDetail({ disruptionId, onBack, currentUser, onPlanProposed }) {
  const [disruption, setDisruption] = useState(null);
  const [loading, setLoading] = useState(true);
  const [proposing, setProposing] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState({ type: '', text: '' });
  const [activeTab, setActiveTab] = useState('cascade'); // 'cascade' | 'options' | 'orders'

  // What-If Simulation State
  const [simulations, setSimulations] = useState({});
  const [simulating, setSimulating] = useState({});
  const [simulatingAll, setSimulatingAll] = useState(false);
  const [inspectedIndex, setInspectedIndex] = useState(0);

  // Graph State
  const [graphNodes, setGraphNodes] = useState([]);
  const [graphEdges, setGraphEdges] = useState([]);
  const [graphLoading, setGraphLoading] = useState(false);
  const [highlightedOrderId, setHighlightedOrderId] = useState(null);

  // Drafts State
  const [disruptionDrafts, setDisruptionDrafts] = useState([]);
  const [draftAudience, setDraftAudience] = useState('CUSTOMER');
  const [draftOrderId, setDraftOrderId] = useState('');
  const [drafting, setDrafting] = useState(false);
  const [expandedDrafts, setExpandedDrafts] = useState({});

  const nodeTypes = useMemo(() => ({ default: CascadeNode }), []);

  useEffect(() => {
    fetchDetail();
    fetchGraph();
    fetchDisruptionDrafts();
  }, [disruptionId]);

  const fetchDisruptionDrafts = async () => {
    try {
      const res = await apiFetch(`/disruptions/${disruptionId}/drafts`);
      if (res.ok) {
        setDisruptionDrafts(await res.json());
      }
    } catch (err) {
      console.error('Failed to load drafts for disruption', err);
    }
  };

  const handleCreateDraft = async (e) => {
    e.preventDefault();
    setDrafting(true);
    setFeedbackMsg({ type: '', text: '' });
    try {
      const res = await apiFetch(`/disruptions/${disruptionId}/drafts`, {
        method: 'POST',
        body: JSON.stringify({
          audience: draftAudience,
          order_id: draftAudience === 'CUSTOMER' ? (draftOrderId ? Number(draftOrderId) : (disruption?.impacts?.[0]?.order_id || undefined)) : undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Could not generate draft.');
      }
      setFeedbackMsg({
        type: 'success',
        text: `Draft #${data.id} created successfully. Awaiting second-user review & approval.`,
      });
      fetchDisruptionDrafts();
      setExpandedDrafts((prev) => ({ ...prev, [data.id]: true }));
    } catch (err) {
      setFeedbackMsg({ type: 'error', text: err.message });
    } finally {
      setDrafting(false);
    }
  };

  const handleApproveDraft = async (draftId) => {
    setFeedbackMsg({ type: '', text: '' });
    try {
      const res = await apiFetch(`/drafts/${draftId}/approve`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Could not approve draft.');
      }
      setFeedbackMsg({
        type: 'success',
        text: `Draft #${draftId} approved by ${currentUser.username}. Ready for simulated dispatch.`,
      });
      fetchDisruptionDrafts();
    } catch (err) {
      setFeedbackMsg({ type: 'error', text: err.message });
    }
  };

  const handleSendDraft = async (draftId) => {
    setFeedbackMsg({ type: '', text: '' });
    try {
      const res = await apiFetch(`/drafts/${draftId}/send`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Could not send simulated draft.');
      }
      setFeedbackMsg({
        type: 'success',
        text: `Draft #${draftId} dispatched (simulated). Recorded in append-only audit trail.`,
      });
      fetchDisruptionDrafts();
    } catch (err) {
      setFeedbackMsg({ type: 'error', text: err.message });
    }
  };

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

  const fetchGraph = async () => {
    setGraphLoading(true);
    try {
      const res = await apiFetch(`/disruptions/${disruptionId}/graph`);
      if (res.ok) {
        const data = await res.json();
        const edgesWithStyles = (data.edges || []).map(edge => ({
          ...edge,
          style: { stroke: '#8B9B90', strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#8B9B90', width: 14, height: 14 },
        }));
        setGraphNodes(data.nodes || []);
        setGraphEdges(edgesWithStyles);
      }
    } catch (err) {
      console.error('Failed to load cascade graph:', err);
    } finally {
      setGraphLoading(false);
    }
  };

  const scrollToWaterfall = useCallback((orderId) => {
    setHighlightedOrderId(orderId);
    setTimeout(() => {
      const el = document.getElementById(`order-waterfall-${orderId}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 100);
  }, []);

  const handleNodeClick = useCallback((event, node) => {
    if (node.data?.entity_type === 'order') {
      scrollToWaterfall(node.data.order_id);
    }
  }, [scrollToWaterfall]);

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
  const impacts = disruption.impacts || [];

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

      {/* View Switcher Tabs: Cascade Map & Waterfall | Compare Options & Simulator | Affected Orders */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--color-line)', paddingBottom: '4px' }}>
        <button
          type="button"
          onClick={() => setActiveTab('cascade')}
          className={activeTab === 'cascade' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '12px', padding: '4px 12px' }}
        >
          Supply cascade map &amp; Risk waterfall
        </button>
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
          onClick={() => setActiveTab('orders')}
          className={activeTab === 'orders' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '12px', padding: '4px 12px' }}
        >
          Impacted orders ({impacts.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('drafts')}
          className={activeTab === 'drafts' ? 'btn-primary' : 'btn-secondary'}
          style={{ fontSize: '12px', padding: '4px 12px' }}
        >
          Drafted messages ({disruptionDrafts.length})
        </button>
      </div>

      {/* Tab 1: Supply Cascade Graph & Risk Waterfall */}
      {activeTab === 'cascade' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {/* ReactFlow Interactive Graph Panel */}
          <div className="desk-panel" style={{ padding: '16px 20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <h2 style={{ fontSize: '15px', fontWeight: '600' }}>
                  Supply cascade graph: Supplier &rarr; Shipment &rarr; Warehouse &rarr; Orders &rarr; Customers
                </h2>
                <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                  Order nodes are colored by risk severity (HIGH red, MEDIUM amber, LOW green). Click any order node to scroll to its risk waterfall.
                </p>
              </div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '12px' }}>
                <span className="severity-pill severity-pill-high">HIGH risk</span>
                <span className="severity-pill severity-pill-medium">MEDIUM risk</span>
                <span className="severity-pill severity-pill-low">LOW risk</span>
              </div>
            </div>

            <div style={{ height: '360px', width: '100%', border: '1px solid var(--color-line)', borderRadius: 'var(--radius-panel)', backgroundColor: '#FAFCFA' }}>
              {graphLoading ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--color-muted-ink)' }}>
                  Loading supply cascade graph...
                </div>
              ) : (
                <ReactFlow
                  nodes={graphNodes}
                  edges={graphEdges}
                  nodeTypes={nodeTypes}
                  onNodeClick={handleNodeClick}
                  fitView
                  fitViewOptions={{ padding: 0.2 }}
                  attributionPosition="bottom-right"
                >
                  <Background color="var(--color-line)" gap={16} size={1} />
                  <Controls showInteractive={false} />
                </ReactFlow>
              )}
            </div>
          </div>

          {/* Risk Waterfall Section */}
          <div className="desk-panel" style={{ padding: '16px 20px' }}>
            <div style={{ marginBottom: '16px' }}>
              <h3 style={{ fontSize: '15px', fontWeight: '700' }}>
                Risk waterfall &amp; Multi-factor score breakdown
              </h3>
              <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                Deterministic point contributions per affected customer order. Max score is 100 points.
              </p>
            </div>

            {impacts.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
                No impacted orders identified for this disruption.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {impacts.map((imp) => {
                  const orderId = imp.order_id || imp.id;
                  const b = imp.breakdown || imp.risk_breakdown || {};
                  const score = imp.risk_score || 0;
                  const isHighlighted = highlightedOrderId === orderId;

                  return (
                    <div
                      key={orderId}
                      id={`order-waterfall-${orderId}`}
                      className="desk-panel"
                      style={{
                        padding: '16px 20px',
                        border: isHighlighted ? '2px solid var(--color-primary)' : '1px solid var(--color-line)',
                        backgroundColor: isHighlighted ? '#F4F8F6' : '#FFFFFF',
                        transition: 'border 0.3s ease, background-color 0.3s ease',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', flexWrap: 'wrap', gap: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span className={`severity-pill severity-pill-${imp.risk_level?.toLowerCase() || 'high'}`}>
                            {imp.risk_level || 'HIGH'}
                          </span>
                          <span className="num" style={{ fontSize: '15px', fontWeight: '700' }}>
                            {imp.order_code}
                          </span>
                          <span style={{ fontSize: '13px', color: 'var(--color-ink)' }}>
                            &middot; {imp.customer}
                          </span>
                          <span style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                            (Due {imp.due_date})
                          </span>
                        </div>
                        <div className="num" style={{ fontWeight: '700', fontSize: '15px' }}>
                          {score} / 100 <span style={{ fontSize: '12px', fontWeight: '400', color: 'var(--color-muted-ink)' }}>total risk points</span>
                        </div>
                      </div>

                      {/* Stacked Bar Risk Waterfall */}
                      <div style={{
                        width: '100%',
                        height: '24px',
                        backgroundColor: '#EAECE7',
                        borderRadius: '2px',
                        display: 'flex',
                        overflow: 'hidden',
                        marginBottom: '10px',
                        border: '1px solid var(--color-line)',
                      }}>
                        {WATERFALL_FACTORS.map(f => {
                          const pts = Number(b[f.key] || 0);
                          if (pts <= 0) return null;
                          const widthPct = Math.min(100, (pts / 100) * 100);
                          return (
                            <div
                              key={f.key}
                              title={`${f.label}: ${pts} pts (out of ${f.max})`}
                              style={{
                                width: `${widthPct}%`,
                                backgroundColor: f.color,
                                height: '100%',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: '#FFFFFF',
                                fontSize: '11px',
                                fontWeight: '600',
                                transition: 'width 0.4s ease',
                              }}
                            >
                              {widthPct >= 8 ? `${pts}` : ''}
                            </div>
                          );
                        })}
                      </div>

                      {/* Factors Breakdown Grid */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px', marginBottom: '12px' }}>
                        {WATERFALL_FACTORS.map(f => {
                          const pts = Number(b[f.key] || 0);
                          return (
                            <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                              <div style={{ width: '10px', height: '10px', backgroundColor: f.color, borderRadius: '2px', flexShrink: 0 }} />
                              <span style={{ color: 'var(--color-muted-ink)' }}>{f.label}:</span>
                              <strong className="num" style={{ color: pts > 0 ? 'var(--color-ink)' : 'var(--color-muted-ink)' }}>
                                {pts} / {f.max}
                              </strong>
                            </div>
                          );
                        })}
                      </div>

                      {/* Plain English Contributing Reasons */}
                      {imp.reasons && imp.reasons.length > 0 && (
                        <div style={{ borderTop: '1px solid var(--color-line)', paddingTop: '8px', fontSize: '12px' }}>
                          <div style={{ fontWeight: '600', color: 'var(--color-muted-ink)', marginBottom: '4px' }}>
                            Contributing risk explanations:
                          </div>
                          <ul style={{ margin: 0, paddingLeft: '18px', color: 'var(--color-ink)', lineHeight: '1.5' }}>
                            {imp.reasons.map((r, ri) => (
                              <li key={ri}>{r}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 2: Compare Recovery Options & What-If Simulator Panel */}
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

      {/* Tab 3: Impacted Orders Table View */}
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
              {impacts.map((imp) => (
                <tr key={imp.id || imp.order_id} className={`row-${imp.priority === 'HIGH' ? 'high' : 'medium'}`}>
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

      {/* Tab 4: Drafted Messages */}
      {activeTab === 'drafts' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {/* Quick Draft Generator */}
          <div className="desk-panel" style={{ padding: '16px 20px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: '600', marginBottom: '4px' }}>
              Generate operational communication draft
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)', marginBottom: '14px' }}>
              Drafts an email using verified disruption facts and recommended recovery plans. A second user must review &amp; approve before simulated dispatch.
            </p>

            <form onSubmit={handleCreateDraft} style={{ display: 'flex', gap: '16px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div>
                <label style={{ fontSize: '11px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>
                  Audience
                </label>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center', height: '32px' }}>
                  <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <input
                      type="radio"
                      name="tabDraftAudience"
                      value="CUSTOMER"
                      checked={draftAudience === 'CUSTOMER'}
                      onChange={() => setDraftAudience('CUSTOMER')}
                    />
                    Customer
                  </label>
                  <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <input
                      type="radio"
                      name="tabDraftAudience"
                      value="SUPPLIER"
                      checked={draftAudience === 'SUPPLIER'}
                      onChange={() => setDraftAudience('SUPPLIER')}
                    />
                    Supplier
                  </label>
                </div>
              </div>

              {draftAudience === 'CUSTOMER' && impacts.length > 0 && (
                <div style={{ minWidth: '220px' }}>
                  <label style={{ fontSize: '11px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>
                    Target affected order
                  </label>
                  <select
                    value={draftOrderId || impacts[0]?.order_id}
                    onChange={(e) => setDraftOrderId(e.target.value)}
                    style={{
                      width: '100%',
                      height: '32px',
                      fontSize: '12px',
                      padding: '4px 8px',
                      border: '1px solid var(--color-line)',
                      borderRadius: 'var(--radius-panel)',
                    }}
                  >
                    {impacts.map((imp) => (
                      <option key={imp.id || imp.order_id} value={imp.order_id}>
                        {imp.order_code} - {imp.customer} ({imp.priority} risk)
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <button
                  type="submit"
                  disabled={drafting}
                  className="btn-primary"
                  style={{ height: '32px', fontSize: '12px', padding: '0 16px' }}
                >
                  {drafting ? 'Generating draft...' : '+ Generate draft'}
                </button>
              </div>
            </form>
          </div>

          {/* Existing Drafts List */}
          <div className="desk-panel" style={{ overflow: 'hidden' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-line)' }}>
              <h3 style={{ fontSize: '14px', fontWeight: '600' }}>
                Existing communication drafts for this disruption ({disruptionDrafts.length})
              </h3>
            </div>

            {disruptionDrafts.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--color-muted-ink)', fontSize: '13px' }}>
                No drafts generated yet for this disruption. Use the generator above to draft customer or supplier communications.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {disruptionDrafts.map((d) => {
                  const isCreator = currentUser?.username === d.creator_username || currentUser?.id === d.created_by;
                  const isExpanded = !!expandedDrafts[d.id];

                  return (
                    <div
                      key={d.id}
                      style={{
                        padding: '14px 18px',
                        borderBottom: '1px solid var(--color-line)',
                        backgroundColor: d.status === 'SENT_SIMULATED' ? 'var(--color-panel)' : '#FFFFFF',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                            <span
                              className={`severity-pill ${
                                d.audience === 'CUSTOMER' ? 'severity-pill-medium' : 'severity-pill-low'
                              }`}
                              style={{ fontSize: '10px', padding: '1px 6px' }}
                            >
                              {d.audience}
                            </span>
                            <span
                              className={`severity-pill ${
                                d.status === 'SENT_SIMULATED'
                                  ? 'severity-pill-low'
                                  : d.status === 'APPROVED'
                                  ? 'severity-pill-medium'
                                  : 'severity-pill-high'
                              }`}
                              style={{ fontSize: '10px', padding: '1px 6px' }}
                            >
                              {d.status === 'SENT_SIMULATED' ? 'SENT (SIMULATED)' : d.status}
                            </span>
                            <span style={{ fontSize: '12px', fontWeight: '600' }}>
                              Draft #{d.id}
                            </span>
                            {d.order_code && (
                              <span style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                                &middot; {d.order_code} ({d.customer})
                              </span>
                            )}
                          </div>

                          <div
                            onClick={() => setExpandedDrafts(prev => ({ ...prev, [d.id]: !prev[d.id] }))}
                            style={{ fontSize: '13px', fontWeight: '600', cursor: 'pointer', marginBottom: '2px' }}
                          >
                            {d.subject}
                          </div>

                          <div style={{ fontSize: '11px', color: 'var(--color-muted-ink)', display: 'flex', gap: '12px' }}>
                            <span>Created by: <strong>{d.creator_username || `User #${d.created_by}`}</strong></span>
                            {d.approved_by && (
                              <span>Approved by: <strong>{d.approver_username || `User #${d.approved_by}`}</strong></span>
                            )}
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                          <button
                            onClick={() => setExpandedDrafts(prev => ({ ...prev, [d.id]: !prev[d.id] }))}
                            className="btn-subtle"
                            style={{ fontSize: '11px', padding: '3px 8px' }}
                          >
                            {isExpanded ? 'Hide' : 'View'}
                          </button>

                          {d.status === 'DRAFT' && (
                            <div>
                              {isCreator ? (
                                <span
                                  style={{
                                    fontSize: '11px',
                                    color: 'var(--color-risk-high)',
                                    backgroundColor: 'var(--color-risk-high-subtle)',
                                    padding: '3px 8px',
                                    borderRadius: 'var(--radius-panel)',
                                    border: '1px solid var(--color-risk-high)',
                                  }}
                                  title="Rule 4: Creator cannot self-approve. Switch user to approve."
                                >
                                  Requires 2nd user approval
                                </span>
                              ) : (
                                <button
                                  onClick={() => handleApproveDraft(d.id)}
                                  className="btn-primary"
                                  style={{ fontSize: '11px', padding: '3px 10px' }}
                                >
                                  Approve draft
                                </button>
                              )}
                            </div>
                          )}

                          {d.status === 'APPROVED' && (
                            <button
                              onClick={() => handleSendDraft(d.id)}
                              className="btn-primary"
                              style={{
                                fontSize: '11px',
                                padding: '3px 12px',
                                backgroundColor: 'var(--color-risk-low)',
                                borderColor: 'var(--color-risk-low)',
                              }}
                            >
                              &rarr; Send (Simulated)
                            </button>
                          )}

                          {d.status === 'SENT_SIMULATED' && (
                            <span style={{ fontSize: '11px', color: 'var(--color-risk-low)', fontWeight: '600' }}>
                              &check; Dispatched (Simulated)
                            </span>
                          )}
                        </div>
                      </div>

                      {isExpanded && (
                        <div
                          style={{
                            marginTop: '10px',
                            padding: '10px 14px',
                            backgroundColor: '#F8F9F8',
                            borderRadius: 'var(--radius-panel)',
                            border: '1px solid var(--color-line)',
                            fontFamily: 'monospace',
                            fontSize: '11px',
                            whiteSpace: 'pre-wrap',
                            lineHeight: '1.5',
                          }}
                        >
                          {d.body}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
