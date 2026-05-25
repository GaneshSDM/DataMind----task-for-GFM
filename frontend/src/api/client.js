import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('slm_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('slm_token')
      localStorage.removeItem('slm_user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ── Auth ──────────────────────────────────────────────────
export const login = (email, password) =>
  api.post('/auth/login', { email, password }).then(r => r.data)
export const logout = () => api.post('/auth/logout')
export const getMe = () => api.get('/auth/me').then(r => r.data)
export const changePassword = d => api.post('/auth/change-password', d).then(r => r.data)

// ── Users ─────────────────────────────────────────────────
export const getUsers = () => api.get('/users/').then(r => r.data)
export const createUser = d => api.post('/users/', d).then(r => r.data)
export const updateUser = (id, d) => api.put(`/users/${id}`, d).then(r => r.data)
export const resetUserPassword = (id, d) => api.post(`/users/${id}/reset-password`, d).then(r => r.data)
export const deleteUser = id => api.delete(`/users/${id}`).then(r => r.data)
export const assignSecurityGroup = (uid, sgid) => api.post(`/users/${uid}/security-groups/${sgid}`).then(r => r.data)
export const removeSecurityGroup = (uid, sgid) => api.delete(`/users/${uid}/security-groups/${sgid}`).then(r => r.data)
export const getUserSecurityGroups = uid => api.get(`/users/${uid}/security-groups`).then(r => r.data)

// ── Roles ─────────────────────────────────────────────────
export const getRoles = () => api.get('/roles/').then(r => r.data).catch(() => [])

// ── Geography ─────────────────────────────────────────────
export const getGeographies = () => api.get('/geographies/').then(r => r.data)
export const createGeography = d => api.post('/geographies/', d).then(r => r.data)
export const updateGeography = (id, d) => api.put(`/geographies/${id}`, d).then(r => r.data)
export const deleteGeography = id => api.delete(`/geographies/${id}`).then(r => r.data)

// ── Domain ────────────────────────────────────────────────
export const getPgSchemas = () => api.get('/domains/schemas').then(r => r.data)
export const getDomains = () => api.get('/domains/').then(r => r.data)
export const createDomain = d => api.post('/domains/', d).then(r => r.data)
export const updateDomain = (id, d) => api.put(`/domains/${id}`, d).then(r => r.data)
export const deleteDomain = id => api.delete(`/domains/${id}`).then(r => r.data)

// ── SubDomain ─────────────────────────────────────────────
export const getSubDomains = () => api.get('/subdomains/').then(r => r.data)
export const createSubDomain = d => api.post('/subdomains/', d).then(r => r.data)
export const updateSubDomain = (id, d) => api.put(`/subdomains/${id}`, d).then(r => r.data)
export const deleteSubDomain = id => api.delete(`/subdomains/${id}`).then(r => r.data)

// ── Security Groups ───────────────────────────────────────
export const getSecurityGroups = () => api.get('/security-groups/').then(r => r.data)
export const getSecurityGroup = id => api.get(`/security-groups/${id}`).then(r => r.data)
export const createSecurityGroup = d => api.post('/security-groups/', d).then(r => r.data)
export const updateSecurityGroup = (id, d) => api.put(`/security-groups/${id}`, d).then(r => r.data)
export const deleteSecurityGroup = id => api.delete(`/security-groups/${id}`).then(r => r.data)

// ── RLS ───────────────────────────────────────────────────
export const getRLS = () => api.get('/rls/').then(r => r.data)
export const createRLS = d => api.post('/rls/', d).then(r => r.data)
export const updateRLS = (id, d) => api.put(`/rls/${id}`, d).then(r => r.data)
export const deleteRLS = id => api.delete(`/rls/${id}`).then(r => r.data)

// ── CLS ───────────────────────────────────────────────────
export const getCLS = () => api.get('/cls/').then(r => r.data)
export const createCLS = d => api.post('/cls/', d).then(r => r.data)
export const updateCLS = (id, d) => api.put(`/cls/${id}`, d).then(r => r.data)
export const deleteCLS = id => api.delete(`/cls/${id}`).then(r => r.data)

// ── Guardrails ────────────────────────────────────────────
export const getGuardrails = () => api.get('/guardrails/').then(r => r.data)
export const createGuardrail = d => api.post('/guardrails/', d).then(r => r.data)
export const updateGuardrail = (id, d) => api.put(`/guardrails/${id}`, d).then(r => r.data)
export const toggleGuardrail = id => api.patch(`/guardrails/${id}/toggle`).then(r => r.data)
export const deleteGuardrail = id => api.delete(`/guardrails/${id}`).then(r => r.data)

// ── Chats ─────────────────────────────────────────────────
export const getChats = () => api.get('/chats/').then(r => r.data)
export const getChatMessages = id => api.get(`/chats/${id}/messages`).then(r => r.data)
export const sendPrompt = d => api.post('/chats/send', d).then(r => r.data)
export const deleteChat = id => api.delete(`/chats/${id}`).then(r => r.data)

// ── SLM Config ────────────────────────────────────────────
export const getSLMConfigs = () => api.get('/slm-config/').then(r => r.data)
export const createSLMConfig = d => api.post('/slm-config/', d).then(r => r.data)
export const updateSLMConfig = (id, d) => api.put(`/slm-config/${id}`, d).then(r => r.data)
export const testSLMConfig = d => api.post('/slm-config/test', d).then(r => r.data)

// ── DB Connections ─────────────────────────────────────────
export const getDBConnections = () => api.get('/db-connections/').then(r => r.data)
export const createDBConnection = d => api.post('/db-connections/', d).then(r => r.data)
export const testDBConnection = d => api.post('/db-connections/test', d).then(r => r.data)
export const deleteDBConnection = id => api.delete(`/db-connections/${id}`).then(r => r.data)

// ── Agents ───────────────────────────────────────────────────
export const getAgents        = ()         => api.get('/agents/').then(r => r.data)
export const getAgentStatuses = ()         => api.get('/agents/statuses').then(r => r.data)
export const updateAgent      = (name, d)  => api.put(`/agents/${name}`, d).then(r => r.data)

// ── Reports ──────────────────────────────────────────────────
export const exportReport = (data) =>
  api.post('/reports/export', data, { responseType: 'blob' })

// ── RAG ─────────────────────────────────────────────────────
export const getRagCategories     = ()        => api.get('/rag/categories').then(r => r.data)
export const createRagCategory    = d         => api.post('/rag/categories', d).then(r => r.data)
export const updateRagCategory    = (id, d)   => api.put(`/rag/categories/${id}`, d).then(r => r.data)
export const deleteRagCategory    = id        => api.delete(`/rag/categories/${id}`).then(r => r.data)

export const getRagSubCategories  = ()        => api.get('/rag/sub-categories').then(r => r.data)
export const createRagSubCategory = d         => api.post('/rag/sub-categories', d).then(r => r.data)
export const updateRagSubCategory = (id, d)   => api.put(`/rag/sub-categories/${id}`, d).then(r => r.data)
export const deleteRagSubCategory = id        => api.delete(`/rag/sub-categories/${id}`).then(r => r.data)

export const getRagRuns   = ()  => api.get('/rag/runs').then(r => r.data)
export const getRagRun    = id  => api.get(`/rag/runs/${id}`).then(r => r.data)
export const createRagRun = (formData) =>
  api.post('/rag/runs', formData, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
export const getRagJobs    = runId => api.get(`/rag/runs/${runId}/jobs`).then(r => r.data)
export const getRagErrors  = runId => api.get(`/rag/runs/${runId}/errors`).then(r => r.data)
export const getRagFiles   = p     => api.get('/rag/files', { params: p }).then(r => r.data)
