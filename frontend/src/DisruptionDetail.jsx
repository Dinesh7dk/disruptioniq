import React, { useState, useEffect } from 'react';
import { ArrowLeft, Brain, Cpu, CheckCircle, AlertTriangle, Truck, DollarSign, Calendar } from 'lucide-react';
import { apiFetch } from './api';

export default function DisruptionDetail({ disruption, onBack, onProposePlan, currentUser }) {
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOption, setSelectedOption] = useState(null);

  useEffect(() => {
    fetchOptions();
  }, [disruption.id]);

  const fetchOptions = async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`/disruptions/${disruption.id}/options`);
      if (res.ok) {
        const data = await res.json();
        setOptions(data.options || []);
      }
    } catch (err) {
      console.error('Error fetching options', err);
    } finally {
      setLoading(false);
    }
  };

  // Deterministic summary fallback logic (per rule 2 & FR-AI-04)
  const isLLM = false; // Fallback indicator when LLM API key is not active
  const summarySource = isLLM ? 'LLM (Claude / Gemini)' : 'Rule-Based Fallback (Deterministic)';

  const cheapestFeasible = options.length > 0
    ? [...options].sort((a, b) => a.cost - b.cost)[0]
    : null;

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '24px 16px' }}>
      <button
        onClick={onBack}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          background: 'transparent',
          border: '1px solid var(--border)',
          color: 'var(--text-main)',
          padding: '8px 14px',
          marginBottom: '20px'
        }}
      >
        <ArrowLeft size={16} /> Back to Dashboard
      </button>

      {/* Header */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
              <h2 style={{ fontSize: '22px', fontWeight: 'bold' }}>Disruption #{disruption.id}</h2>
              <span className="badge badge-high">{disruption.type}</span>
              <span className={`badge badge-${(disruption.status || 'open').toLowerCase()}`}>{disruption.status}</span>
            </div>
            <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>{disruption.description}</p>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-dim)', textAlign: 'right' }}>
            Detected: {disruption.detected_at || 'Recently'}
          </div>
        </div>
      </div>

      {/* AI / Fallback Summary Banner */}
      <div className="card" style={{
        marginBottom: '24px',
        backgroundColor: 'rgba(31, 41, 55, 0.6)',
        borderLeft: '4px solid var(--purple)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: '600', color: 'var(--purple)' }}>
            <Brain size={18} /> Recovery Recommendation Summary
          </div>
          <span style={{
            fontSize: '11px',
            padding: '3px 8px',
            borderRadius: '4px',
            backgroundColor: isLLM ? 'rgba(139, 92, 246, 0.2)' : 'rgba(107, 114, 128, 0.3)',
            color: isLLM ? '#c4b5fd' : '#d1d5db',
            border: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}>
            <Cpu size={12} /> Source: {summarySource}
          </span>
        </div>

        <p style={{ color: 'var(--text-main)', fontSize: '14px', lineHeight: '1.5', marginBottom: '12px' }}>
          {cheapestFeasible ? (
            <>
              Identified <strong>{options.length} verified recovery option{options.length > 1 ? 's' : ''}</strong>. 
              The recommended recovery strategy is <strong>{cheapestFeasible.type}</strong> ({cheapestFeasible.details?.description}) 
              at an estimated cost of <strong>₹{cheapestFeasible.cost.toLocaleString()}</strong>, ensuring delivery by <strong>{cheapestFeasible.new_delivery_date}</strong>.
            </>
          ) : (
            'Evaluating network options. No immediate single-action recovery options verified for all affected lines.'
          )}
        </p>
      </div>

      {/* Recovery Options List */}
      <h3 style={{ fontSize: '18px', fontWeight: 'bold', marginBottom: '14px' }}>
        Verified Feasible Recovery Options ({options.length})
      </h3>

      {loading ? (
        <div className="card" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-dim)' }}>
          Computing feasible options across network warehouses...
        </div>
      ) : options.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-dim)' }}>
          No feasible options available without manual intervention.
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
          {options.map((opt, i) => (
            <div key={i} className="card" style={{
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              borderColor: selectedOption === i ? 'var(--primary)' : 'var(--border)'
            }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span className="badge badge-open">{opt.type}</span>
                  {opt.meets_deadline && (
                    <span style={{ fontSize: '11px', color: 'var(--success)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle size={13} /> Meets Deadline
                    </span>
                  )}
                </div>

                <h4 style={{ fontSize: '15px', fontWeight: '600', marginBottom: '6px' }}>
                  {opt.details?.description}
                </h4>

                {opt.order && (
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '10px' }}>
                    Protects: <strong>{opt.order.code}</strong> ({opt.order.customer})
                  </div>
                )}

                <div style={{ display: 'flex', gap: '16px', fontSize: '13px', color: 'var(--text-muted)', margin: '12px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <DollarSign size={14} color="var(--warning)" /> ₹{opt.cost.toLocaleString()}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Calendar size={14} color="var(--primary)" /> {opt.new_delivery_date}
                  </div>
                </div>
              </div>

              {currentUser?.role === 'Operations Analyst' && (
                <button
                  onClick={() => onProposePlan(disruption.id, opt)}
                  style={{
                    backgroundColor: 'var(--primary)',
                    color: '#fff',
                    border: 'none',
                    padding: '8px',
                    fontSize: '13px',
                    marginTop: '12px'
                  }}
                >
                  Propose Recovery Plan
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
