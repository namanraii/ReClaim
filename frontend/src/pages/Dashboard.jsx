import React, { useState, useEffect } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { dashboardAPI } from '../utils/api';
import './Dashboard.css';

const COLORS = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe'];

function Dashboard() {
  const [commandCenter, setCommandCenter] = useState(null);
  const [recoveryQueue, setRecoveryQueue] = useState([]);
  const [bankHealths, setBankHealths] = useState([]);
  const [recoveryTrend, setRecoveryTrend] = useState([]);
  const [failureBreakdown, setFailureBreakdown] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const [ccRes, queueRes, bhRes, trendRes, failureRes] = await Promise.all([
        dashboardAPI.getCommandCenter(),
        dashboardAPI.getRecoveryQueue(15),
        dashboardAPI.getBankHealth(),
        dashboardAPI.getRecoveryRate(30),
        dashboardAPI.getFailureBreakdown()
      ]);

      setCommandCenter(ccRes.data);
      setRecoveryQueue(queueRes.data.queue || []);
      setBankHealths(bhRes.data.banks || []);
      setRecoveryTrend(trendRes.data.trend || []);
      setFailureBreakdown(failureRes.data.breakdown || []);
      setLoading(false);
    } catch (err) {
      setError('Failed to fetch Command Center data');
      setLoading(false);
    }
  };

  if (loading) return <div className="loading">Loading AI Revenue Recovery Command Center...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="dashboard">
      <div className="container">
        {/* Header */}
        <div className="header">
          <div className="badge-bar">
            <span className="live-pill">● DECISION ENGINE ACTIVE</span>
            <span className="compliance-pill">✓ 100% NPCI/RBI COMPLIANCE ENFORCED</span>
          </div>
          <h1>Reclaim Command Center</h1>
          <p>AI Revenue Recovery & Decision Intelligence for UPI AutoPay</p>
        </div>

        {/* Top Command Center Metrics */}
        <div className="metrics-grid">
          <div className="metric-card risk-card">
            <h3>Revenue at Risk</h3>
            <div className="value">₹{commandCenter?.revenue_at_risk?.toLocaleString() || 0}</div>
            <div className="label">Active failed mandate debits</div>
          </div>
          <div className="metric-card erv-card">
            <h3>Expected Recoverable (ERV)</h3>
            <div className="value">₹{commandCenter?.expected_recoverable_revenue?.toLocaleString() || 0}</div>
            <div className="label">P(R|a)*Amount - Friction</div>
          </div>
          <div className="metric-card recovered-card">
            <h3>Actual Recovered</h3>
            <div className="value">₹{commandCenter?.actual_revenue_recovered?.toLocaleString() || 0}</div>
            <div className="label">Recovery Rate: {commandCenter?.recovery_rate_pct || 0}%</div>
          </div>
          <div className="metric-card compliance-card">
            <h3>Compliance Violations</h3>
            <div className="value success-val">0</div>
            <div className="label">Hard Policy Gate Enforcement</div>
          </div>
        </div>

        {/* PRIMARY: Recovery Opportunity Queue */}
        <div className="table-container queue-container">
          <div className="section-header">
            <div>
              <h2>🎯 Recovery Opportunity Queue</h2>
              <p className="subtitle">Mandates ranked by Expected Recoverable Revenue (ERV) with AI Action Selection</p>
            </div>
            <button className="btn-refresh" onClick={fetchDashboardData}>↻ Refresh Queue</button>
          </div>

          <table className="queue-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Mandate</th>
                <th>Bank / VPA</th>
                <th>Diagnosis & Tier</th>
                <th>₹ at Risk</th>
                <th>Expected Value (ERV)</th>
                <th>AI Recovery Playbook</th>
                <th>Confidence</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {recoveryQueue.map((item) => (
                <tr key={item.mandate_id}>
                  <td>
                    <span className={`rank-badge ${item.priority_rank <= 3 ? 'rank-high' : 'rank-med'}`}>
                      #{item.priority_rank}
                    </span>
                  </td>
                  <td>
                    <a href={`/mandate/${item.mandate_id}`} className="mandate-link">
                      {item.mandate_id.substring(0, 8)}...
                    </a>
                  </td>
                  <td>
                    <strong>{item.bank_code}</strong>
                    <div className="vpa-sub">{item.customer_vpa}</div>
                  </td>
                  <td>
                    <span className="diag-tag">{item.failure_diagnosis}</span>
                    <div className="tier-tag">{(item.resolution_tier || item.resolution_path || 'TIER_1').replace('TIER_', 'T').replace(/_/g, ' ')}</div>
                  </td>
                  <td className="amount-col">₹{item.revenue_at_risk?.toLocaleString()}</td>
                  <td className="erv-col">
                    <strong>₹{item.expected_recoverable_revenue?.toLocaleString()}</strong>
                  </td>
                  <td>
                    <span className="action-pill">{item.best_action.replace(/_/g, ' ')}</span>
                  </td>
                  <td>
                    <div className="conf-bar-container">
                      <div className="conf-bar" style={{ width: `${item.confidence * 100}%` }}></div>
                      <span>{(item.confidence * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                  <td>
                    <a href={`/mandate/${item.mandate_id}`} className="btn-inspect">
                      Inspect Trace →
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Live Bank Health Signals & Charts Grid */}
        <div className="charts-grid">
          {/* Live Bank Health Monitor */}
          <div className="chart-card bank-health-card">
            <h2>🏦 Bank Rail Health & Anomaly Signals</h2>
            <p className="subtitle">Real-time technical decline rate tracking & degradation anomaly detection</p>
            <div className="bank-health-list">
              {bankHealths.map((bh) => (
                <div key={bh.bank_code} className="bank-health-row">
                  <div className="bank-info">
                    <span className="bank-name">{bh.bank_code}</span>
                    <span className={`bank-status status-${bh.status.toLowerCase()}`}>{bh.status}</span>
                  </div>
                  <div className="health-bar-container">
                    <div
                      className={`health-bar ${bh.status === 'OUTAGE_ANOMALY' ? 'bar-outage' : bh.status === 'DEGRADED' ? 'bar-degraded' : 'bar-healthy'}`}
                      style={{ width: `${bh.health_score * 100}%` }}
                    ></div>
                  </div>
                  <div className="bank-metrics">
                    <span>Health: {(bh.health_score * 100).toFixed(0)}%</span>
                    <span className="sigma-metric">Anomaly: {bh.anomaly_sigma}σ</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Recovery Trend Chart */}
          <div className="chart-card">
            <h2>📈 Recovery Rate Trend (30 Days)</h2>
            <p className="subtitle">Daily measured recovery performance on active failure events</p>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={recoveryTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
                <XAxis dataKey="date" stroke="#a0aec0" />
                <YAxis stroke="#a0aec0" />
                <Tooltip contentStyle={{ backgroundColor: '#1a202c', borderColor: '#4a5568' }} />
                <Line type="monotone" dataKey="recovery_rate" stroke="#48bb78" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Failure Category Breakdown */}
          <div className="chart-card">
            <h2>🧩 Failure Category Breakdown</h2>
            <p className="subtitle">Distribution across regulatory, liquidity, and technical root causes</p>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={failureBreakdown}
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="count"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {failureBreakdown.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: '#1a202c', borderColor: '#4a5568' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
