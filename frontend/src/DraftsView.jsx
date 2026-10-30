import React, { useState, useEffect } from 'react';
import { apiFetch } from './api';

export default function DraftsView({ onBack, currentUser, defaultOrderId, defaultDisruptionId }) {
  const [drafts, setDrafts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState({ type: '', text: '' });

  // Filters
  const [audienceFilter, setAudienceFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Draft Creator form state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newAudience, setNewAudience] = useState('CUSTOMER');
  const [selectedOrderId, setSelectedOrderId] = useState(defaultOrderId || '');
  const [customReason, setCustomReason] = useState('');
  const [creating, setCreating] = useState(false);

  // Edit Draft state
  const [editingDraftId, setEditingDraftId] = useState(null);
  const [editSubject, setEditSubject] = useState('');
  const [editBody, setEditBody] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);

  // Expanded body preview
  const [expandedDrafts, setExpandedDrafts] = useState({});

  useEffect(() => {
    fetchDrafts();
    fetchOrders();
  }, []);

  const fetchDrafts = async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/drafts');
      if (res.ok) {
        const data = await res.json();
        setDrafts(data);
      }
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to load drafts: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  const fetchOrders = async () => {
    try {
      const res = await apiFetch('/orders?sort=risk');
      if (res.ok) {
        const data = await res.json();
        setOrders(data);
        if (!selectedOrderId && data.length > 0) {
          setSelectedOrderId(data[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to load orders', err);
    }
  };

  const toggleExpand = (id) => {
    setExpandedDrafts((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleCreateDraft = async (e) => {
    e.preventDefault();
    if (!selectedOrderId) {
      setFeedback({ type: 'error', text: 'Please select an order.' });
      return;
    }
    setCreating(true);
    setFeedback({ type: '', text: '' });
    try {
      const payload = {
        audience: newAudience,
        custom_facts: customReason ? { reason: customReason } : undefined,
      };
      const res = await apiFetch(`/orders/${selectedOrderId}/drafts`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Could not generate draft.');
      }
      setFeedback({
        type: 'success',
        text: `Draft #${data.id} created successfully. It requires review & approval by a second user.`,
      });
      setShowCreateModal(false);
      setCustomReason('');
      fetchDrafts();
      // Automatically expand new draft
      setExpandedDrafts((prev) => ({ ...prev, [data.id]: true }));
    } catch (err) {
      setFeedback({ type: 'error', text: err.message });
    } finally {
      setCreating(false);
    }
  };

  const handleApprove = async (draft) => {
    setFeedback({ type: '', text: '' });
    try {
      const res = await apiFetch(`/drafts/${draft.id}/approve`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Could not approve draft.');
      }
      setFeedback({
        type: 'success',
        text: `Draft #${draft.id} approved by ${currentUser.username}. Ready for simulated dispatch.`,
      });
      fetchDrafts();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message });
    }
  };

  const handleSendSimulated = async (draft) => {
    setFeedback({ type: '', text: '' });
    try {
      const res = await apiFetch(`/drafts/${draft.id}/send`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Could not send simulated draft.');
      }
      setFeedback({
        type: 'success',
        text: `Draft #${draft.id} simulated dispatch successful! Status updated to SENT_SIMULATED and recorded in audit trail.`,
      });
      fetchDrafts();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message });
    }
  };

  const startEdit = (draft) => {
    setEditingDraftId(draft.id);
    setEditSubject(draft.subject);
    setEditBody(draft.body);
  };

  const cancelEdit = () => {
    setEditingDraftId(null);
    setEditSubject('');
    setEditBody('');
  };

  const handleSaveEdit = async (draftId) => {
    setSavingEdit(true);
    setFeedback({ type: '', text: '' });
    try {
      const res = await apiFetch(`/drafts/${draftId}`, {
        method: 'PUT',
        body: JSON.stringify({
          subject: editSubject,
          body: editBody,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to update draft.');
      }
      setFeedback({
        type: 'success',
        text: `Draft #${draftId} updated. Status has been reset to DRAFT for review.`,
      });
      setEditingDraftId(null);
      fetchDrafts();
    } catch (err) {
      setFeedback({ type: 'error', text: err.message });
    } finally {
      setSavingEdit(false);
    }
  };

  const filteredDrafts = drafts.filter((d) => {
    if (audienceFilter !== 'ALL' && d.audience !== audienceFilter) return false;
    if (statusFilter !== 'ALL' && d.status !== statusFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchSub = d.subject?.toLowerCase().includes(q);
      const matchCust = d.customer?.toLowerCase().includes(q);
      const matchCode = d.order_code?.toLowerCase().includes(q);
      if (!matchSub && !matchCust && !matchCode) return false;
    }
    return true;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Top Breadcrumb & Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={onBack} className="btn-secondary">
          Back to orders
        </button>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-primary"
          style={{ fontSize: '12px', padding: '6px 14px' }}
        >
          + Create communication draft
        </button>
      </div>

      {feedback.text && (
        <div
          style={{
            padding: '10px 14px',
            backgroundColor: feedback.type === 'error' ? 'var(--color-risk-high-subtle)' : 'var(--color-risk-low-subtle)',
            border: `1px solid ${feedback.type === 'error' ? 'var(--color-risk-high)' : 'var(--color-risk-low)'}`,
            borderRadius: 'var(--radius-panel)',
            color: feedback.type === 'error' ? 'var(--color-risk-high)' : 'var(--color-risk-low)',
            fontSize: '13px',
          }}
        >
          {feedback.text}
        </div>
      )}

      {/* Main Panel */}
      <div className="desk-panel" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--color-line)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
            <div>
              <h1 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '4px' }}>
                Drafted communications desk
              </h1>
              <p style={{ fontSize: '12px', color: 'var(--color-muted-ink)', maxWidth: '75ch' }}>
                Customer and supplier communications written from verified operational facts.
                Strictly enforces peer review (separation of duty: creator cannot self-approve) and logs simulated transmission to the append-only audit trail.
              </p>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
              Logged in as <strong>{currentUser?.username}</strong> ({currentUser?.role})
            </div>
          </div>

          {/* Filter Bar */}
          <div style={{ display: 'flex', gap: '12px', marginTop: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
            <div>
              <span style={{ fontSize: '11px', color: 'var(--color-muted-ink)', marginRight: '6px' }}>Audience:</span>
              <select
                value={audienceFilter}
                onChange={(e) => setAudienceFilter(e.target.value)}
                style={{
                  fontSize: '12px',
                  padding: '4px 8px',
                  border: '1px solid var(--color-line)',
                  borderRadius: 'var(--radius-panel)',
                  background: 'var(--color-panel)',
                }}
              >
                <option value="ALL">All audiences</option>
                <option value="CUSTOMER">Customer emails</option>
                <option value="SUPPLIER">Supplier coordination</option>
              </select>
            </div>

            <div>
              <span style={{ fontSize: '11px', color: 'var(--color-muted-ink)', marginRight: '6px' }}>Status:</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                style={{
                  fontSize: '12px',
                  padding: '4px 8px',
                  border: '1px solid var(--color-line)',
                  borderRadius: 'var(--radius-panel)',
                  background: 'var(--color-panel)',
                }}
              >
                <option value="ALL">All statuses</option>
                <option value="DRAFT">DRAFT (Pending review)</option>
                <option value="APPROVED">APPROVED (Ready to send)</option>
                <option value="SENT_SIMULATED">SENT_SIMULATED (Dispatched)</option>
              </select>
            </div>

            <div style={{ flex: '1', minWidth: '180px' }}>
              <input
                type="text"
                placeholder="Search by order, customer, subject..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  fontSize: '12px',
                  padding: '4px 10px',
                  border: '1px solid var(--color-line)',
                  borderRadius: 'var(--radius-panel)',
                }}
              />
            </div>
          </div>
        </div>

        {/* Drafts List */}
        {loading ? (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--color-muted-ink)' }}>
            Loading communication drafts...
          </div>
        ) : filteredDrafts.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center' }}>
            <p style={{ color: 'var(--color-muted-ink)', fontSize: '14px', marginBottom: '12px' }}>
              No communication drafts found matching current filters.
            </p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="btn-primary"
              style={{ fontSize: '12px', padding: '6px 14px' }}
            >
              Draft your first customer or supplier message
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {filteredDrafts.map((d) => {
              const isCreator = currentUser?.username === d.creator_username || currentUser?.id === d.created_by;
              const isExpanded = !!expandedDrafts[d.id];
              const isEditing = editingDraftId === d.id;

              return (
                <div
                  key={d.id}
                  style={{
                    padding: '16px 20px',
                    borderBottom: '1px solid var(--color-line)',
                    backgroundColor: d.status === 'SENT_SIMULATED' ? 'var(--color-panel)' : '#FFFFFF',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                    <div style={{ flex: '1', minWidth: '280px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                        <span
                          className={`severity-pill ${
                            d.audience === 'CUSTOMER' ? 'severity-pill-medium' : 'severity-pill-low'
                          }`}
                          style={{ fontSize: '10px', padding: '1px 6px', fontWeight: '700' }}
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
                          style={{ fontSize: '10px', padding: '1px 6px', fontWeight: '700' }}
                        >
                          {d.status === 'SENT_SIMULATED' ? 'SENT (SIMULATED)' : d.status}
                        </span>

                        <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--color-ink)' }}>
                          Draft #{d.id}
                        </span>
                        {d.order_code && (
                          <span className="num" style={{ fontSize: '12px', color: 'var(--color-muted-ink)' }}>
                            &middot; Order {d.order_code} ({d.customer})
                          </span>
                        )}
                      </div>

                      <div
                        onClick={() => toggleExpand(d.id)}
                        style={{
                          fontSize: '14px',
                          fontWeight: '600',
                          color: 'var(--color-ink)',
                          cursor: 'pointer',
                          marginBottom: '4px',
                        }}
                      >
                        {d.subject}
                      </div>

                      <div style={{ fontSize: '12px', color: 'var(--color-muted-ink)', display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
                        <span>
                          Created by: <strong>{d.creator_username || `User #${d.created_by}`}</strong>
                        </span>
                        {d.approved_by && (
                          <span>
                            Approved by: <strong>{d.approver_username || `User #${d.approved_by}`}</strong>
                          </span>
                        )}
                        <span>{d.created_at?.slice(0, 16).replace('T', ' ')}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                      <button
                        onClick={() => toggleExpand(d.id)}
                        className="btn-subtle"
                        style={{ fontSize: '11px', padding: '4px 8px' }}
                      >
                        {isExpanded ? 'Hide body' : 'View email'}
                      </button>

                      {d.status !== 'SENT_SIMULATED' && !isEditing && (
                        <button
                          onClick={() => startEdit(d)}
                          className="btn-subtle"
                          style={{ fontSize: '11px', padding: '4px 8px' }}
                        >
                          Edit
                        </button>
                      )}

                      {/* Approval Button: separation of duty */}
                      {d.status === 'DRAFT' && (
                        <div>
                          {isCreator ? (
                            <span
                              style={{
                                fontSize: '11px',
                                color: 'var(--color-risk-high)',
                                backgroundColor: 'var(--color-risk-high-subtle)',
                                padding: '4px 8px',
                                borderRadius: 'var(--radius-panel)',
                                border: '1px solid var(--color-risk-high)',
                              }}
                              title="Rule 4: Creator cannot approve their own draft. Switch user to approve."
                            >
                              Requires 2nd user approval
                            </span>
                          ) : (
                            <button
                              onClick={() => handleApprove(d)}
                              className="btn-primary"
                              style={{ fontSize: '11px', padding: '4px 10px' }}
                            >
                              Approve draft
                            </button>
                          )}
                        </div>
                      )}

                      {/* Send Simulated Button */}
                      {d.status === 'APPROVED' && (
                        <button
                          onClick={() => handleSendSimulated(d)}
                          className="btn-primary"
                          style={{
                            fontSize: '11px',
                            padding: '4px 12px',
                            backgroundColor: 'var(--color-risk-low)',
                            borderColor: 'var(--color-risk-low)',
                          }}
                        >
                          &rarr; Send (Simulated)
                        </button>
                      )}

                      {d.status === 'SENT_SIMULATED' && (
                        <span
                          style={{
                            fontSize: '11px',
                            color: 'var(--color-risk-low)',
                            fontWeight: '600',
                            padding: '2px 6px',
                          }}
                        >
                          &check; Dispatched (Simulated)
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Inline Editing */}
                  {isEditing && (
                    <div style={{ marginTop: '12px', padding: '12px', backgroundColor: 'var(--color-panel)', borderRadius: 'var(--radius-panel)' }}>
                      <div style={{ marginBottom: '8px' }}>
                        <label style={{ fontSize: '11px', fontWeight: '600', display: 'block', marginBottom: '2px' }}>
                          Subject line
                        </label>
                        <input
                          type="text"
                          value={editSubject}
                          onChange={(e) => setEditSubject(e.target.value)}
                          style={{
                            width: '100%',
                            fontSize: '12px',
                            padding: '6px 8px',
                            border: '1px solid var(--color-line)',
                            borderRadius: 'var(--radius-panel)',
                          }}
                        />
                      </div>
                      <div style={{ marginBottom: '8px' }}>
                        <label style={{ fontSize: '11px', fontWeight: '600', display: 'block', marginBottom: '2px' }}>
                          Email body
                        </label>
                        <textarea
                          rows={6}
                          value={editBody}
                          onChange={(e) => setEditBody(e.target.value)}
                          style={{
                            width: '100%',
                            fontSize: '12px',
                            fontFamily: 'monospace',
                            padding: '6px 8px',
                            border: '1px solid var(--color-line)',
                            borderRadius: 'var(--radius-panel)',
                          }}
                        />
                      </div>
                      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          className="btn-secondary"
                          style={{ fontSize: '11px', padding: '4px 10px' }}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => handleSaveEdit(d.id)}
                          disabled={savingEdit}
                          className="btn-primary"
                          style={{ fontSize: '11px', padding: '4px 10px' }}
                        >
                          {savingEdit ? 'Saving...' : 'Save changes'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Body Preview */}
                  {isExpanded && !isEditing && (
                    <div
                      style={{
                        marginTop: '12px',
                        padding: '12px 16px',
                        backgroundColor: '#F8F9F8',
                        borderRadius: 'var(--radius-panel)',
                        border: '1px solid var(--color-line)',
                        fontFamily: 'monospace',
                        fontSize: '12px',
                        whiteSpace: 'pre-wrap',
                        lineHeight: '1.5',
                        color: 'var(--color-ink)',
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

      {/* Create Draft Modal */}
      {showCreateModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            className="desk-panel"
            style={{
              width: '520px',
              maxWidth: '90vw',
              padding: '24px',
              backgroundColor: '#FFFFFF',
              boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ fontSize: '16px', fontWeight: '700' }}>Create communication draft</h2>
              <button
                onClick={() => setShowCreateModal(false)}
                className="btn-subtle"
                style={{ fontSize: '14px', padding: '2px 6px' }}
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateDraft}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>
                  Audience
                </label>
                <div style={{ display: 'flex', gap: '16px' }}>
                  <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <input
                      type="radio"
                      name="audience"
                      value="CUSTOMER"
                      checked={newAudience === 'CUSTOMER'}
                      onChange={() => setNewAudience('CUSTOMER')}
                    />
                    Customer update
                  </label>
                  <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <input
                      type="radio"
                      name="audience"
                      value="SUPPLIER"
                      checked={newAudience === 'SUPPLIER'}
                      onChange={() => setNewAudience('SUPPLIER')}
                    />
                    Supplier coordination
                  </label>
                </div>
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>
                  Select customer order
                </label>
                <select
                  value={selectedOrderId}
                  onChange={(e) => setSelectedOrderId(e.target.value)}
                  style={{
                    width: '100%',
                    fontSize: '12px',
                    padding: '6px 8px',
                    border: '1px solid var(--color-line)',
                    borderRadius: 'var(--radius-panel)',
                  }}
                  required
                >
                  {orders.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.code} - {o.customer} ({o.priority} priority, Due {o.due_date})
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ marginBottom: '16px' }}>
                <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>
                  Operational note / reason (optional override)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Shipment SH-001 delayed due to port congestion"
                  value={customReason}
                  onChange={(e) => setCustomReason(e.target.value)}
                  style={{
                    width: '100%',
                    fontSize: '12px',
                    padding: '6px 8px',
                    border: '1px solid var(--color-line)',
                    borderRadius: 'var(--radius-panel)',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn-secondary"
                  style={{ fontSize: '12px', padding: '6px 12px' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="btn-primary"
                  style={{ fontSize: '12px', padding: '6px 16px' }}
                >
                  {creating ? 'Generating draft...' : 'Generate draft'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
