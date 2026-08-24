import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { dashboardAPI, recoveryAPI, complianceAPI } from '../utils/api';
import './styles/MandateDetails.css';

function MandateDetails() {
  const { id } = useParams();
  const [mandateData, setMandateData] = useState(null);
  const [auditLog, setAuditLog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchMandateDetails();
  }, [id]);

  const fetchMandateDetails = async () => {
    try {
      setLoading(true);
      const [explanationRes, auditRes] = await Promise.all([
        dashboardAPI.getMandateExplanation(id),
        dashboardAPI.getAuditLog(id, 20)
      ]);

      setMandateData(explanationRes.data);
      setAuditLog(auditRes.data.audit_log);
      setLoading(false);
    } catch (err) {
      setError('Failed to fetch mandate details');
      setLoading(false);
    }
  };

  const handleRecoveryProcess = async () => {
    try {
      if (mandateData?.failure_events?.length > 0) {
        const latestFailure = mandateData.failure_events[0];
        await recoveryAPI.processFailed({
          mandate_id: id,
          failure_category: latestFailure.category,
          confidence: latestFailure.confidence
        });
        fetchMandateDetails(); // Refresh data
      }
    } catch (err) {
      setError('Failed to process recovery');
    }
  };

  const handlePortabilityCheck = async () => {
    try {
      await recoveryAPI.checkPortability(id);
      alert('Portability check completed');
    } catch (err) {
      setError('Failed to check portability');
    }
  };

  if (loading) return <div className="loading">Loading mandate details...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!mandateData) return <div className="error">Mandate not found</div>;

  return (
    <div className="mandate-details">
      <div className="container">
        <div className="header">
          <h1>Mandate Details</h1>
          <p>ID: {id}</p>
        </div>

        {/* Mandate Information */}
        <div className="info-card">
          <h2>Mandate Information</h2>
          <div className="info-grid">
            <div className="info-item">
              <label>Customer VPA:</label>
              <span>{mandateData.mandate.customer_vpa}</span>
            </div>
            <div className="info-item">
              <label>Bank Code:</label>
              <span>{mandateData.mandate.bank_code}</span>
            </div>
            <div className="info-item">
              <label>PSP App:</label>
              <span>{mandateData.mandate.psp_app}</span>
            </div>
            <div className="info-item">
              <label>Amount:</label>
              <span>₹{mandateData.mandate.amount.toLocaleString()}</span>
            </div>
            <div className="info-item">
              <label>Status:</label>
              <span className={`status-badge status-${mandateData.mandate.status.toLowerCase()}`}>
                {mandateData.mandate.status}
              </span>
            </div>
          </div>
        </div>

        {/* Recovery Actions */}
        <div className="actions-card">
          <h2>Recovery Actions</h2>
          <div className="actions-grid">
            <button className="btn btn-primary" onClick={handleRecoveryProcess}>
              Process Recovery
            </button>
            <button className="btn btn-secondary" onClick={handlePortabilityCheck}>
              Check Portability
            </button>
          </div>
        </div>

        {/* Recent Attempts */}
        <div className="table-card">
          <h2>Recent Debit Attempts</h2>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Scheduled</th>
                <th>Status</th>
                <th>Attempt #</th>
              </tr>
            </thead>
            <tbody>
              {mandateData.recent_attempts.map((attempt) => (
                <tr key={attempt.id}>
                  <td>{attempt.id.substring(0, 8)}...</td>
                  <td>{new Date(attempt.scheduled_at).toLocaleString()}</td>
                  <td>
                    <span className={`status-badge status-${attempt.status.toLowerCase()}`}>
                      {attempt.status}
                    </span>
                  </td>
                  <td>{attempt.attempt_number}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Failure Events */}
        <div className="table-card">
          <h2>Failure Events</h2>
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Confidence</th>
                <th>Detected At</th>
              </tr>
            </thead>
            <tbody>
              {mandateData.failure_events.map((event, index) => (
                <tr key={index}>
                  <td>{event.category}</td>
                  <td>{(event.confidence * 100).toFixed(1)}%</td>
                  <td>{new Date(event.detected_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Recovery Outcome */}
        {mandateData.recovery_outcome && (
          <div className="info-card">
            <h2>Recovery Outcome</h2>
            <div className="info-grid">
              <div className="info-item">
                <label>State:</label>
                <span>{mandateData.recovery_outcome.state}</span>
              </div>
              <div className="info-item">
                <label>Recovery Attempts:</label>
                <span>{mandateData.recovery_outcome.recovery_attempts}</span>
              </div>
              {mandateData.recovery_outcome.final_amount_recovered && (
                <div className="info-item">
                  <label>Amount Recovered:</label>
                  <span>₹{mandateData.recovery_outcome.final_amount_recovered.toLocaleString()}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Audit Log */}
        <div className="table-card">
          <h2>Audit Log</h2>
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Event Type</th>
                <th>Actor</th>
                <th>Reason</th>
                <th>Compliant</th>
              </tr>
            </thead>
            <tbody>
              {auditLog.map((entry) => (
                <tr key={entry.id}>
                  <td>{new Date(entry.timestamp).toLocaleString()}</td>
                  <td>{entry.event_type}</td>
                  <td>{entry.actor}</td>
                  <td>{entry.reason}</td>
                  <td>
                    <span className={`status-badge status-${entry.compliant ? 'success' : 'failed'}`}>
                      {entry.compliant ? 'Yes' : 'No'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default MandateDetails;
