import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const dashboardAPI = {
  getCommandCenter: () => api.get('/dashboard/command-center'),
  getRecoveryQueue: (limit = 50) => api.get(`/dashboard/recovery-queue?limit=${limit}`),
  getBankHealth: () => api.get('/dashboard/bank-health'),
  getDecisionTrace: (mandateId) => api.get(`/dashboard/mandate/${mandateId}/decision-trace`),
  getMetrics: () => api.get('/dashboard/metrics'),
  getRecoveryRate: (days) => api.get(`/dashboard/recovery-rate?days=${days}`),
  getFailureBreakdown: () => api.get('/dashboard/failure-breakdown'),
  getBankPerformance: () => api.get('/dashboard/bank-performance'),
  getRevenueRecovered: () => api.get('/dashboard/revenue-recovered'),
  getMandateExplanation: (mandateId) => api.get(`/dashboard/mandate/${mandateId}/explain`),
  getAuditLog: (mandateId, limit) => api.get(`/dashboard/audit-log?mandate_id=${mandateId || ''}&limit=${limit}`),
  getExceptions: () => api.get('/dashboard/exceptions'),
};

export const mandatesAPI = {
  list: (skip, limit) => api.get(`/mandates?skip=${skip}&limit=${limit}`),
  get: (mandateId) => api.get(`/mandates/${mandateId}`),
  create: (data) => api.post('/mandates', data),
  updateStatus: (mandateId, status) => api.put(`/mandates/${mandateId}/status`, { status }),
};

export const classificationAPI = {
  predict: (data) => api.post('/classification/predict', data),
  explain: (mandateId) => api.get(`/classification/explain/${mandateId}`),
  train: (data) => api.post('/classification/train', data),
};

export const recoveryAPI = {
  processFailed: (data) => api.post('/recovery/process', data),
  checkPortability: (mandateId) => api.post('/recovery/portability/check', { mandate_id: mandateId }),
  initiatePromise: (mandateId) => api.post(`/recovery/promise/initiate?mandate_id=${mandateId}`),
  recordPromise: (data) => api.post('/recovery/promise/record', data),
  checkBackPromise: (mandateId) => api.post(`/recovery/promise/checkback?mandate_id=${mandateId}`),
  getPromiseStatus: (mandateId) => api.get(`/recovery/promise/status/${mandateId}`),
};

export const complianceAPI = {
  getRegistry: () => api.get('/compliance/registry'),
  issueToken: (data) => api.post('/compliance/token', data),
  validateRetry: (data) => api.post('/compliance/validate', data),
  getExecutionWindow: (fromTime) => api.post('/compliance/execution-window', { from_time: fromTime }),
  getRules: () => api.get('/compliance/rules'),
  checkPinReauth: (amount, category) => api.post('/compliance/pin-reauth', null, { params: { amount, category } }),
};

export default api;
