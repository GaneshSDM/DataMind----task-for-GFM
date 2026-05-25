import { useState, useEffect } from 'react'
import { Plus, Trash2, Eye, EyeOff, Save, Plug } from 'lucide-react'
import { getUsers } from '../api/client'
import toast from 'react-hot-toast'

// ── Static seed data ───────────────────────────────────────────────────────────
const SEED_APPS = [
  {
    id: 1,
    name: 'Salesforce',
    icon: '☁️',
    auth_type: 'oauth2',
    base_url: 'https://api.salesforce.com',
    is_active: true,
    apis: [
      { id: 'sf_1', name: 'API_create_customer', method: 'POST',   description: 'Create new customer record' },
      { id: 'sf_2', name: 'API_update_customer', method: 'PUT',    description: 'Update existing customer data' },
      { id: 'sf_3', name: 'API_get_customer',    method: 'GET',    description: 'Retrieve customer by ID' },
      { id: 'sf_4', name: 'API_delete_customer', method: 'DELETE', description: 'Permanently delete customer record' },
      { id: 'sf_5', name: 'API_list_customers',  method: 'GET',    description: 'List all customers with filters' },
    ],
  },
  {
    id: 2,
    name: 'Oracle Apps',
    icon: '🗄️',
    auth_type: 'basic',
    base_url: 'https://oracle.example.com/fscmRestApi/resources/v1',
    is_active: true,
    apis: [
      { id: 'or_1', name: 'API_create_order',   method: 'POST', description: 'Create new sales order' },
      { id: 'or_2', name: 'API_update_order',   method: 'PUT',  description: 'Update order lines or status' },
      { id: 'or_3', name: 'API_get_inventory',  method: 'GET',  description: 'Check real-time inventory levels' },
      { id: 'or_4', name: 'API_create_invoice', method: 'POST', description: 'Generate AR invoice' },
    ],
  },
  {
    id: 3,
    name: 'Outlook / MS Graph',
    icon: '📧',
    auth_type: 'oauth2',
    base_url: 'https://graph.microsoft.com/v1.0',
    is_active: false,
    apis: [
      { id: 'ol_1', name: 'API_send_email',     method: 'POST', description: 'Send email on behalf of user' },
      { id: 'ol_2', name: 'API_get_calendar',   method: 'GET',  description: 'Fetch calendar events' },
      { id: 'ol_3', name: 'API_create_meeting', method: 'POST', description: 'Create Teams / Outlook meeting' },
    ],
  },
]

const AUTH_TYPES    = ['basic', 'apikey', 'oauth2']
const HTTP_METHODS  = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

const CRED_FIELDS = {
  basic: [
    { key: 'username', label: 'Username',   type: 'text',     placeholder: 'service_account' },
    { key: 'password', label: 'Password',   type: 'password', placeholder: '••••••••' },
  ],
  apikey: [
    { key: 'api_key',    label: 'API Key',     type: 'password', placeholder: 'sk-••••••••••••' },
    { key: 'key_header', label: 'Header Name', type: 'text',     placeholder: 'X-API-Key' },
    { key: 'key_query',  label: 'Query Param', type: 'text',     placeholder: 'api_key (if sent via URL)' },
  ],
  oauth2: [
    { key: 'client_id',     label: 'Client ID',     type: 'text',     placeholder: 'client_xxxxxxxx' },
    { key: 'client_secret', label: 'Client Secret', type: 'password', placeholder: '••••••••••••' },
    { key: 'token_url',     label: 'Token URL',     type: 'text',     placeholder: 'https://login.example.com/oauth2/token' },
    { key: 'scope',         label: 'Scope',         type: 'text',     placeholder: 'api read write offline_access' },
    { key: 'access_token',  label: 'Access Token',  type: 'password', placeholder: 'Leave blank to generate via OAuth flow' },
  ],
}

const METHOD_STYLE = {
  GET:    { bg: '#eff6ff', color: '#3b82f6' },
  POST:   { bg: '#f0fdf4', color: '#16a34a' },
  PUT:    { bg: '#fff7ed', color: '#ea580c' },
  PATCH:  { bg: '#faf5ff', color: '#9333ea' },
  DELETE: { bg: '#fef2f2', color: '#ef4444' },
}

const AUTH_STYLE = {
  basic:  { label: 'Basic Auth', bg: '#fff7ed', color: '#ea580c', border: '#fdba74' },
  apikey: { label: 'API Key',    bg: '#faf5ff', color: '#9333ea', border: '#d8b4fe' },
  oauth2: { label: 'OAuth 2.0',  bg: '#eff6ff', color: '#3b82f6', border: '#93c5fd' },
}

// ── Shared style constants ─────────────────────────────────────────────────────
const TH = {
  padding: '8px 12px', textAlign: 'left', fontWeight: 600,
  color: 'var(--text-secondary)', fontSize: 11, whiteSpace: 'nowrap',
  borderBottom: '1px solid var(--border-default)',
}
const LBL = {
  fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
  display: 'block', marginBottom: 5,
}
const INPUT = {
  width: '100%', boxSizing: 'border-box',
  padding: '7px 10px', borderRadius: 6,
  border: '1px solid var(--border-default)',
  background: 'var(--bg-surface)', color: 'var(--text-primary)',
  fontSize: 12.5, outline: 'none',
}

// ── Sub-components ─────────────────────────────────────────────────────────────
function MethodBadge({ method }) {
  const s = METHOD_STYLE[method] || { bg: '#f1f5f9', color: '#475569' }
  return (
    <span style={{
      display: 'inline-block', fontSize: 9, fontWeight: 700, letterSpacing: '0.05em',
      padding: '2px 6px', borderRadius: 4, background: s.bg, color: s.color,
      minWidth: 48, textAlign: 'center', flexShrink: 0,
    }}>
      {method}
    </span>
  )
}

function AuthBadge({ type }) {
  const s = AUTH_STYLE[type] || { label: type, bg: '#f1f5f9', color: '#475569', border: '#e2e8f0' }
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: '2px 9px', borderRadius: 12,
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
    }}>
      {s.label}
    </span>
  )
}

function Modal({ title, onClose, onConfirm, confirmLabel, children }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--bg-surface)', borderRadius: 10,
        border: '1px solid var(--border-default)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
        width: 460, padding: '24px 26px',
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 20 }}>
          {title}
        </div>
        {children}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 22 }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={onConfirm}>{confirmLabel || 'Add'}</button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function AppMapping() {
  const [apps,       setApps]       = useState(() => JSON.parse(JSON.stringify(SEED_APPS)))
  const [selected,   setSelected]   = useState(SEED_APPS[0].id)
  const [users,      setUsers]      = useState([])
  const [userId,     setUserId]     = useState('')
  const [mappings,   setMappings]   = useState({})  // { `${appId}_${userId}`: { permissions, credentials } }
  const [revealed,   setRevealed]   = useState(new Set())
  const [dirty,      setDirty]      = useState(false)
  const [addAppOpen, setAddAppOpen] = useState(false)
  const [addApiOpen, setAddApiOpen] = useState(false)
  const [newApp, setNewApp]         = useState({ name: '', icon: '🔌', auth_type: 'basic', base_url: '' })
  const [newApi, setNewApi]         = useState({ name: 'API_', method: 'POST', description: '' })

  useEffect(() => {
    getUsers()
      .then(list => {
        setUsers(list)
        if (list.length) setUserId(String(list[0].UserID ?? list[0].id ?? ''))
      })
      .catch(() => {})
  }, [])

  const app    = apps.find(a => a.id === selected)
  const mapKey = `${selected}_${userId}`
  const umap   = mappings[mapKey] || { permissions: {}, credentials: {} }

  const setPerm = (apiId, field, val) => {
    setMappings(m => ({
      ...m,
      [mapKey]: {
        ...umap,
        permissions: {
          ...umap.permissions,
          [apiId]: { ...(umap.permissions[apiId] || {}), [field]: val },
        },
      },
    }))
    setDirty(true)
  }

  const setCred = (key, val) => {
    setMappings(m => ({
      ...m,
      [mapKey]: { ...umap, credentials: { ...umap.credentials, [key]: val } },
    }))
    setDirty(true)
  }

  const toggleReveal = key => setRevealed(s => {
    const n = new Set(s)
    n.has(key) ? n.delete(key) : n.add(key)
    return n
  })

  const handleSave = () => {
    toast.success('Mapping saved — backend integration pending', { icon: '✅' })
    setDirty(false)
  }

  const handleAddApp = () => {
    if (!newApp.name.trim()) return toast.error('App name required')
    const id = Date.now()
    setApps(prev => [...prev, { ...newApp, id, is_active: true, apis: [] }])
    setSelected(id)
    setAddAppOpen(false)
    setNewApp({ name: '', icon: '🔌', auth_type: 'basic', base_url: '' })
    toast.success(`${newApp.name} added`)
  }

  const handleAddApi = () => {
    if (!newApi.name.trim()) return toast.error('API name required')
    setApps(prev => prev.map(a =>
      a.id === selected
        ? { ...a, apis: [...a.apis, { ...newApi, id: `custom_${Date.now()}` }] }
        : a
    ))
    setAddApiOpen(false)
    setNewApi({ name: 'API_', method: 'POST', description: '' })
    toast.success('API endpoint added')
  }

  const toggleActive = () => {
    if (!app) return
    setApps(prev => prev.map(a => a.id === selected ? { ...a, is_active: !a.is_active } : a))
    toast(app.is_active ? `${app.name} deactivated` : `${app.name} activated`)
  }

  const deleteApp = id => {
    const a = apps.find(x => x.id === id)
    if (!window.confirm(`Remove "${a?.name}" from the list?`)) return
    const remaining = apps.filter(x => x.id !== id)
    setApps(remaining)
    if (selected === id) setSelected(remaining[0]?.id ?? null)
    toast.success('Application removed')
  }

  const credFields = CRED_FIELDS[app?.auth_type] || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <div style={{
        height: 52, minHeight: 52, background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Plug size={15} style={{ color: 'var(--brand-blue, #1A4FA0)' }} />
          <span style={{ fontSize: 14, fontWeight: 700 }}>Application User Mapping</span>
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 12,
            background: '#fff3cd', color: '#856404', border: '1px solid #ffc107',
          }}>
            UI Preview — Backend Pending
          </span>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setAddAppOpen(true)}>
          <Plus size={12} /> New Application
        </button>
      </div>

      {/* ── Body ────────────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Left: App list */}
        <div style={{
          width: 236, minWidth: 236,
          borderRight: '1px solid var(--border-default)',
          overflowY: 'auto',
          background: 'var(--bg-sidebar, var(--bg-surface))',
          display: 'flex', flexDirection: 'column',
        }}>
          <div style={{
            padding: '10px 12px 6px',
            fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)',
            textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            Applications ({apps.length})
          </div>

          {apps.map(a => (
            <div
              key={a.id}
              onClick={() => { setSelected(a.id); setDirty(false) }}
              style={{
                padding: '10px 12px', cursor: 'pointer',
                borderLeft: `3px solid ${a.id === selected ? 'var(--brand-orange, #F47920)' : 'transparent'}`,
                background: a.id === selected ? 'var(--bg-subtle)' : 'transparent',
                display: 'flex', alignItems: 'center', gap: 9,
              }}
            >
              <span style={{ fontSize: 20, flexShrink: 0 }}>{a.icon}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {a.name}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 1 }}>
                  {AUTH_STYLE[a.auth_type]?.label || a.auth_type} · {a.apis.length} API{a.apis.length !== 1 ? 's' : ''}
                </div>
              </div>
              <span
                style={{ width: 7, height: 7, borderRadius: '50%', background: a.is_active ? '#16a34a' : '#9ca3af', flexShrink: 0 }}
                title={a.is_active ? 'Active' : 'Inactive'}
              />
            </div>
          ))}

          {apps.length === 0 && (
            <div style={{ padding: '28px 12px', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 12 }}>
              No applications. Click "+ New Application".
            </div>
          )}
        </div>

        {/* Right: Detail */}
        {app ? (
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>

            {/* App header bar */}
            <div style={{
              padding: '14px 20px',
              borderBottom: '1px solid var(--border-default)',
              background: 'var(--bg-surface)',
              display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
            }}>
              <span style={{ fontSize: 26, flexShrink: 0 }}>{app.icon}</span>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{app.name}</div>
                <div style={{ fontSize: 10.5, color: 'var(--text-tertiary)', fontFamily: 'monospace', marginTop: 1 }}>{app.base_url}</div>
              </div>
              <AuthBadge type={app.auth_type} />
              <button
                onClick={toggleActive}
                style={{
                  fontSize: 10.5, fontWeight: 600, padding: '3px 10px', borderRadius: 12,
                  border: `1px solid ${app.is_active ? '#86efac' : 'var(--border-default)'}`,
                  background: app.is_active ? '#f0fdf4' : 'var(--bg-subtle)',
                  color: app.is_active ? '#16a34a' : 'var(--text-tertiary)',
                  cursor: 'pointer',
                }}
              >
                {app.is_active ? '● Active' : '○ Inactive'}
              </button>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                <button className="btn btn-sm" onClick={() => setAddApiOpen(true)}>
                  <Plus size={11} /> Add API
                </button>
                <button
                  className="btn btn-sm"
                  style={{ color: '#ef4444', borderColor: '#fca5a5' }}
                  onClick={() => deleteApp(app.id)}
                  title="Remove application"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            </div>

            {/* Content */}
            <div style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 24 }}>

              {/* ── User selector ──────────────────────────────────────────── */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
                  Configure Access For User
                </div>
                <select
                  value={userId}
                  onChange={e => { setUserId(e.target.value); setDirty(false) }}
                  style={{ ...INPUT, maxWidth: 360 }}
                >
                  {users.length === 0 && <option value="">Loading users…</option>}
                  {users.map(u => (
                    <option key={u.UserID ?? u.id} value={String(u.UserID ?? u.id)}>
                      {u.FirstName} {u.LastName} ({u.Email})
                    </option>
                  ))}
                </select>
                <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 5 }}>
                  Permissions and credentials are stored per user per application.
                </div>
              </div>

              {/* ── API Permissions ────────────────────────────────────────── */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
                  API Permissions
                </div>

                <div style={{ border: '1px solid var(--border-default)', borderRadius: 8, overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead>
                      <tr style={{ background: 'var(--bg-subtle)' }}>
                        <th style={TH}>Method</th>
                        <th style={{ ...TH, width: '100%' }}>API Endpoint</th>
                        <th style={{ ...TH, textAlign: 'center', minWidth: 56 }}>Read</th>
                        <th style={{ ...TH, textAlign: 'center', minWidth: 56 }}>Write</th>
                      </tr>
                    </thead>
                    <tbody>
                      {app.apis.length === 0 && (
                        <tr>
                          <td colSpan={4} style={{ padding: '28px 12px', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 12 }}>
                            No API endpoints defined. Click "Add API" to add endpoints.
                          </td>
                        </tr>
                      )}
                      {app.apis.map((api, i) => {
                        const perm = umap.permissions[api.id] || {}
                        return (
                          <tr
                            key={api.id}
                            style={{ borderTop: i > 0 ? '1px solid var(--border-default)' : 'none' }}
                          >
                            <td style={{ padding: '10px 12px', verticalAlign: 'middle' }}>
                              <MethodBadge method={api.method} />
                            </td>
                            <td style={{ padding: '10px 12px', verticalAlign: 'middle' }}>
                              <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'monospace', fontSize: 11.5 }}>
                                {api.name}
                              </div>
                              {api.description && (
                                <div style={{ fontSize: 10.5, color: 'var(--text-tertiary)', marginTop: 2 }}>
                                  {api.description}
                                </div>
                              )}
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'center', verticalAlign: 'middle' }}>
                              <input
                                type="checkbox"
                                checked={!!perm.read}
                                onChange={e => setPerm(api.id, 'read', e.target.checked)}
                                style={{ accentColor: '#1A4FA0', width: 15, height: 15, cursor: 'pointer' }}
                                title="Grant Read access"
                              />
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'center', verticalAlign: 'middle' }}>
                              <input
                                type="checkbox"
                                checked={!!perm.write}
                                onChange={e => setPerm(api.id, 'write', e.target.checked)}
                                style={{ accentColor: '#F47920', width: 15, height: 15, cursor: 'pointer' }}
                                title="Grant Write access"
                              />
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 5, paddingLeft: 2 }}>
                  <span style={{ color: '#1A4FA0', fontWeight: 600 }}>Read</span> = GET · <span style={{ color: '#F47920', fontWeight: 600 }}>Write</span> = POST / PUT / PATCH / DELETE
                </div>
              </div>

              {/* ── Credentials ───────────────────────────────────────────── */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
                  Credentials — {AUTH_STYLE[app.auth_type]?.label}
                  <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, fontSize: 9.5, marginLeft: 8, color: '#f59e0b' }}>
                    ⚠ One set per application · Encryption pending
                  </span>
                </div>

                <div style={{
                  border: '1px solid var(--border-default)', borderRadius: 8,
                  padding: '18px 20px', background: 'var(--bg-subtle)',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(270px, 1fr))',
                  gap: 16,
                }}>
                  {credFields.map(f => {
                    const isPassword  = f.type === 'password'
                    const revKey      = `${mapKey}_${f.key}`
                    const isRevealed  = revealed.has(revKey)
                    const inputType   = isPassword && !isRevealed ? 'password' : 'text'
                    return (
                      <div key={f.key}>
                        <label style={LBL}>{f.label}</label>
                        <div style={{ position: 'relative' }}>
                          <input
                            type={inputType}
                            value={umap.credentials[f.key] || ''}
                            onChange={e => setCred(f.key, e.target.value)}
                            placeholder={f.placeholder}
                            style={{
                              ...INPUT,
                              paddingRight: isPassword ? 34 : 10,
                              fontFamily: isPassword ? 'monospace' : 'inherit',
                            }}
                          />
                          {isPassword && (
                            <button
                              type="button"
                              onClick={() => toggleReveal(revKey)}
                              style={{
                                position: 'absolute', right: 8, top: '50%',
                                transform: 'translateY(-50%)',
                                background: 'none', border: 'none', cursor: 'pointer',
                                color: 'var(--text-tertiary)', padding: 0,
                                display: 'flex', alignItems: 'center',
                              }}
                              title={isRevealed ? 'Hide' : 'Show'}
                            >
                              {isRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* ── Save bar ──────────────────────────────────────────────── */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, paddingBottom: 24 }}>
                <button
                  className="btn btn-primary"
                  onClick={handleSave}
                  disabled={!dirty}
                  style={{ opacity: dirty ? 1 : 0.45 }}
                >
                  <Save size={13} /> Save Mapping
                </button>
                {dirty && (
                  <span style={{ fontSize: 11, color: '#f59e0b', fontWeight: 600 }}>
                    ● Unsaved changes
                  </span>
                )}
                {!dirty && (
                  <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                    All changes saved
                  </span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
            Select an application to manage user mappings.
          </div>
        )}
      </div>

      {/* ── Add Application modal ─────────────────────────────────────────────── */}
      {addAppOpen && (
        <Modal
          title="Add New Application"
          onClose={() => setAddAppOpen(false)}
          onConfirm={handleAddApp}
          confirmLabel="Add Application"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', gap: 10 }}>
              <div style={{ flex: '0 0 66px' }}>
                <label style={LBL}>Icon</label>
                <input
                  value={newApp.icon}
                  onChange={e => setNewApp(n => ({ ...n, icon: e.target.value }))}
                  style={{ ...INPUT, textAlign: 'center', fontSize: 22, padding: '5px 4px' }}
                  maxLength={2}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={LBL}>Application Name *</label>
                <input
                  value={newApp.name}
                  onChange={e => setNewApp(n => ({ ...n, name: e.target.value }))}
                  placeholder="e.g. Salesforce, SAP, Workday"
                  style={INPUT}
                  autoFocus
                />
              </div>
            </div>
            <div>
              <label style={LBL}>Base URL</label>
              <input
                value={newApp.base_url}
                onChange={e => setNewApp(n => ({ ...n, base_url: e.target.value }))}
                placeholder="https://api.example.com/v1"
                style={INPUT}
              />
            </div>
            <div>
              <label style={LBL}>Authentication Type</label>
              <select
                value={newApp.auth_type}
                onChange={e => setNewApp(n => ({ ...n, auth_type: e.target.value }))}
                style={INPUT}
              >
                {AUTH_TYPES.map(t => (
                  <option key={t} value={t}>{AUTH_STYLE[t]?.label || t}</option>
                ))}
              </select>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Add API modal ─────────────────────────────────────────────────────── */}
      {addApiOpen && (
        <Modal
          title={`Add API Endpoint — ${app?.name}`}
          onClose={() => setAddApiOpen(false)}
          onConfirm={handleAddApi}
          confirmLabel="Add Endpoint"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', gap: 10 }}>
              <div style={{ flex: '0 0 110px' }}>
                <label style={LBL}>HTTP Method</label>
                <select
                  value={newApi.method}
                  onChange={e => setNewApi(n => ({ ...n, method: e.target.value }))}
                  style={INPUT}
                >
                  {HTTP_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label style={LBL}>API Name *</label>
                <input
                  value={newApi.name}
                  onChange={e => setNewApi(n => ({ ...n, name: e.target.value }))}
                  placeholder="API_create_record"
                  style={{ ...INPUT, fontFamily: 'monospace' }}
                  autoFocus
                />
              </div>
            </div>
            <div>
              <label style={LBL}>Description</label>
              <input
                value={newApi.description}
                onChange={e => setNewApi(n => ({ ...n, description: e.target.value }))}
                placeholder="Brief description of what this endpoint does"
                style={INPUT}
              />
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
