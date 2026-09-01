import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { dashboardAPI, recoveryAPI } from '../utils/api';
import './MandateDetails.css';

function MandateDetails() {
  const { id } = useParams();
  const [mandateData, setMandateData] = useState(null);
  const [decisionTrace, setDecisionTrace] = useState(null);
  const [auditLog, setAuditLog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);

  useEffect(() => {
    fetchMandateDetails();
  }, [id]);

  const fetchMandateDetails = async () => {
    try {
      setLoading(true);
      const [explanationRes, traceRes, auditRes] = await Promise.all([
        dashboardAPI.getMandateExplanation(id),
        dashboardAPI.getDecisionTrace(id),
        dashboardAPI.getAuditLog(id, 25)
      ]);

      setMandateData(explanationRes.data);
      setDecisionTrace(traceRes.data);
      setAuditLog(auditRes.data.audit_log);
      setLoading(false);
    } catch (err) {
      setError('Failed to fetch mandate decision details');
      setLoading(false);
    }
  };

  const handleExecutePlan = async () => {
    try {
      setExecuting(true);
      setActionMessage(null);
      const res = await recoveryAPI.processFailed({ mandate_id: id });
      setActionMessage(`Plan executed successfully! Action: ${res.data.action}, State: ${res.data.next_state}`);
      fetchMandateDetails();
    } catch (err) {
      setError('Failed to execute recovery plan: ' + (err.response?.data?.detail || err.message));
    } finally {
      setExecuting(false);
    }
  };

  if (loading) return <div className="loading">Loading Mandate Decision Intelligence...</div>;
  if (error && !mandateData) return <div className="error">{error}</div>;
  if (!mandateData) return <div className="error">Mandate not found</div>;

  return (
    <div className="mandate-details">
      <div className="container">
        {/* Navigation / Header */}
        <div className="nav-bar">
          <a href="/" className="back-link">← Back to Command Center</a>
          <span className="mandate-id-pill">MANDATE ID: {id}</span>
        </div>

        {actionMessage && <div className="alert-success">{actionMessage}</div>}

        {/* DECISION INTELLIGENCE TRACE CARD (PRIMARY) */}
        {decisionTrace && (
          <div className="trace-card">
            <div className="trace-header">
              <div>
                <div className="trace-badge-row">
                  <span className="trace-id-badge">DECISION ID: {decisionTrace.decision_id}</span>
                  <span className={`status-pill pill-${decisionTrace.execution_status.toLowerCase()}`}>
                    ● {decisionTrace.execution_status}
                  </span>
                </div>
                <h2>🧠 AI Revenue Recovery Decision Trace</h2>
                <p className="trace-subtitle">Autonomous Diagnosis, Expected Value Optimization & Compliance Approval</p>
              </div>

              <div className="erv-hero-box">
                <span className="erv-label">OPTIMAL RECOVERY ERV</span>
                <span className="erv-value">₹{decisionTrace.expected_recovered_revenue?.toLocaleString()}</span>
                <span className="risk-sub">Revenue at Risk: ₹{decisionTrace.revenue_at_risk?.toLocaleString()}</span>
              </div>
            </div>

            {/* Diagnosis & Evidence Grid */}
            <div className="trace-section-grid">
              <div className="diag-box">
                <h3>Root Cause Diagnosis</h3>
                <div className="diag-title">{decisionTrace.diagnosis}</div>
                <div className="diag-meta">
                  <span>Confidence: {(decisionTrace.confidence * 100).toFixed(0)}%</span>
                  <span className="tier-badge">{decisionTrace.resolution_tier}</span>
                </div>
              </div>

              <div className="evidence-box">
                <h3>Contextual Evidence Synthesized</h3>
                <ul className="evidence-list">
                  {decisionTrace.evidence_points?.map((ev, idx) => (
                    <li key={idx}>✓ {ev}</li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Candidate Action ERV Matrix & Counterfactuals */}
            <div className="candidate-matrix-section">
              <h3>Candidate Action Evaluation & Counterfactual Matrix</h3>
              <p className="matrix-subtitle">Evaluates ERV = P(Recovery|Action)*Amount - Friction - Risk across all playbook candidates</p>
              <table className="matrix-table">
                <thead>
                  <tr>
                    <th>Candidate Playbook</th>
                    <th>P(Success)</th>
                    <th>Friction (₹)</th>
                    <th>Expected Revenue (ERV)</th>
                    <th>Compliance Gate</th>
                    <th>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {decisionTrace.candidate_evaluations?.map((cand, idx) => (
                    <tr key={idx} className={cand.is_selected ? 'selected-row' : ''}>
                      <td>
                        <strong>{cand.action}</strong>
                        <div className="cand-desc">{cand.description}</div>
                      </td>
                      <td>{(cand.recovery_probability * 100).toFixed(0)}%</td>
                      <td>₹{cand.friction_cost}</td>
                      <td>
                        <strong className="erv-matrix-val">₹{cand.expected_revenue_value?.toLocaleString()}</strong>
                      </td>
                      <td>
                        <span className={`compliance-tag ${cand.is_compliant ? 'tag-approved' : 'tag-blocked'}`}>
                          {cand.is_compliant ? '✓ APPROVED' : '✕ BLOCKED'}
                        </span>
                      </td>
                      <td>
                        {cand.is_selected ? (
                          <span className="selected-pill">★ SELECTED (MAX ERV)</span>
                        ) : (
                          <span className="alt-pill">Counterfactual</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Counterfactual Explanation Box */}
            <div className="counterfactual-box">
              <h3>🔍 Why This Recovery Action? (Decision Rationale)</h3>
              <pre className="counterfactual-text">{decisionTrace.counterfactual_explanation}</pre>
            </div>

            {/* Compliance Approval Token Section */}
            {decisionTrace.compliance_token && (
              <div className="token-box">
                <div className="token-header">
                  <span className="token-id">TOKEN: {decisionTrace.compliance_token.decision_id}</span>
                  <span className="token-auth-status">
                    {decisionTrace.compliance_token.approved ? '✓ COMPLIANCE GATE AUTHORIZED' : '✕ BLOCKED'}
                  </span>
                </div>
                <div className="token-details-grid">
                  <div>
                    <strong>Action:</strong> {decisionTrace.compliance_token.action}
                  </div>
                  <div>
                    <strong>Valid Until:</strong> {new Date(decisionTrace.compliance_token.valid_until).toLocaleString()}
                  </div>
                  <div>
                    <strong>Rules Verified:</strong> {decisionTrace.compliance_token.rules_checked?.join(', ')}
                  </div>
                </div>
                <div className="token-citations">
                  <strong>Authoritative Circular Citations:</strong>
                  <ul>
                    {decisionTrace.compliance_token.citations?.map((c, i) => (
                      <li key={i}>
                        <strong>[{c.authority}]</strong> {c.circular}: {c.title}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* Action Trigger */}
            <div className="execution-bar">
              <button
                className="btn-execute-plan"
                disabled={executing || !decisionTrace.compliance_token.approved}
                onClick={handleExecutePlan}
              >
                {executing ? 'Executing Recovery...' : '⚡ Execute Approved Recovery Playbook'}
              </button>
              <span className="gate-note">
                🔒 Protected by Deterministic Compliance Gate · No payment executes without approval token
              </span>
            </div>
          </div>
        )}

        {/* Mandate Info & Audit Trail */}
        <div className="mandate-lower-grid">
          {/* Mandate Info */}
          <div className="card mandate-info-card">
            <h2>Mandate Specifications</h2>
            <div className="spec-list">
              <div className="spec-item">
                <label>Customer VPA:</label>
                <span>{mandateData.mandate.customer_vpa}</span>
              </div>
              <div className="spec-item">
                <label>Issuing Bank:</label>
                <span>{mandateData.mandate.bank_code}</span>
              </div>
              <div className="spec-item">
                <label>PSP App:</label>
                <span>{mandateData.mandate.psp_app}</span>
              </div>
              <div className="spec-item">
                <label>Amount:</label>
                <span>₹{mandateData.mandate.amount.toLocaleString()}</span>
              </div>
              <div className="spec-item">
                <label>Mandate Status:</label>
                <span className="status-tag">{mandateData.mandate.status}</span>
              </div>
            </div>
          </div>

          {/* Audit Trail */}
          <div className="card audit-trail-card">
            <h2>Immutable Audit Trail</h2>
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Event</th>
                  <th>Actor</th>
                  <th>Compliance</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {auditLog.map((entry) => (
                  <tr key={entry.id}>
                    <td>{new Date(entry.timestamp).toLocaleTimeString()}</td>
                    <td><span className="event-pill">{entry.event_type}</span></td>
                    <td>{entry.actor}</td>
                    <td>
                      <span className={`compliance-tag ${entry.compliant ? 'tag-approved' : 'tag-blocked'}`}>
                        {entry.compliant ? 'Compliant' : 'Blocked'}
                      </span>
                    </td>
                    <td className="reason-cell">{entry.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default MandateDetails;
