import React, { useState, useEffect } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { dashboardAPI, mandatesAPI } from '../utils/api';
import './Dashboard.css';

const COLORS = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe'];

function Dashboard() {
  const [metrics, setMetrics] = useState(null);
  const [recoveryTrend, setRecoveryTrend] = useState([]);
  const [failureBreakdown, setFailureBreakdown] = useState([]);
  const [bankPerformance, setBankPerformance] = useState([]);
  const [revenueRecovered, setRevenueRecovered] = useState(0);
  const [mandates, setMandates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const [metricsRes, trendRes, failureRes, bankRes, revenueRes, mandatesRes] = await Promise.all([
        dashboardAPI.getMetrics(),
        dashboardAPI.getRecoveryRate(30),
        dashboardAPI.getFailureBreakdown(),
        dashboardAPI.getBankPerformance(),
        dashboardAPI.getRevenueRecovered(),
        mandatesAPI.list(0, 10)
      ]);

      setMetrics(metricsRes.data);
      setRecoveryTrend(trendRes.data.trend);
      setFailureBreakdown(failureRes.data.breakdown);
      setBankPerformance(bankRes.data.bank_performance);
      setRevenueRecovered(revenueRes.data.total_recovered);
      setMandates(mandatesRes.data);
      setLoading(false);
    } catch (err) {
      setError('Failed to fetch dashboard data');
      setLoading(false);
    }
  };

  if (loading) return <div className="loading">Loading dashboard...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="dashboard">
      <div className="container">
        <div className="header">
          <h1>Reclaim Dashboard</h1>
          <p>UPI AutoPay Mandate Recovery Engine</p>
        </div>

        {/* Key Metrics */}
        <div className="metrics-grid">
          <div className="metric-card">
            <h3>Total Mandates</h3>
            <div className="value">{metrics?.total_mandates || 0}</div>
            <div className="label">Active: {metrics?.active_mandates || 0}</div>
          </div>
          <div className="metric-card">
            <h3>Success Rate</h3>
            <div className="value">{metrics?.success_rate || 0}%</div>
            <div className="label">{metrics?.successful_attempts || 0} successful attempts</div>
          </div>
          <div className="metric-card">
            <h3>Recovery Rate</h3>
            <div className="value">{metrics?.recovery_rate || 0}%</div>
            <div className="label">{metrics?.recovered || 0} recovered</div>
          </div>
          <div className="metric-card">
            <h3>Revenue Recovered</h3>
            <div className="value">₹{revenueRecovered?.toLocaleString() || 0}</div>
            <div className="label">Total amount recovered</div>
          </div>
        </div>

        {/* Charts */}
        <div className="charts-grid">
          <div className="chart-card">
            <h2>Recovery Rate Trend (30 Days)</h2>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={recoveryTrend}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="recovery_rate" stroke="#667eea" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card">
            <h2>Failure Category Breakdown</h2>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={failureBreakdown}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={(entry) => `${entry.category}: ${entry.count}`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="count"
                >
                  {failureBreakdown.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card">
            <h2>Bank Performance</h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={bankPerformance}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="bank_code" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="success_rate" fill="#667eea" name="Success Rate %" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Recent Mandates */}
        <div className="table-container">
          <h2>Recent Mandates</h2>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Customer VPA</th>
                <th>Bank</th>
                <th>PSP App</th>
                <th>Amount</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {mandates.map((mandate) => (
                <tr key={mandate.id}>
                  <td>
                    <a href={`/mandate/${mandate.id}`} className="mandate-link">
                      {mandate.id.substring(0, 8)}...
                    </a>
                  </td>
                  <td>{mandate.customer_vpa}</td>
                  <td>{mandate.bank_code}</td>
                  <td>{mandate.psp_app}</td>
                  <td>₹{mandate.amount.toLocaleString()}</td>
                  <td>
                    <span className={`status-badge status-${mandate.status.toLowerCase()}`}>
                      {mandate.status}
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

export default Dashboard;
