import { useState, useEffect } from 'react'
import { Plus, Pencil, ToggleLeft, ToggleRight } from 'lucide-react'
import PageHeader from '../components/common/PageHeader'
import Modal from '../components/common/Modal'
import { getGuardrails, createGuardrail, updateGuardrail, toggleGuardrail } from '../api/client'
import toast from 'react-hot-toast'

const CHECK_TYPES = ['keyword_block', 'max_length', 'regex', 'context']
const ACTIONS = ['allow', 'block', 'warn', 'redact', 'escalate']
const SEVERITIES = ['low', 'medium', 'high', 'critical']

const EMPTY = {
  policy_name: '', description: '',
  check_type: 'keyword_block', check_value: {}, action: 'block',
  severity: 'high', priority: 100
}

export default function Guardrails() {
  const [items, setItems] = useState([])
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [checkValueStr, setCheckValueStr] = useState('{}')
  const [saving, setSaving] = useState(false)

  useEffect(() => { load() }, [])

  const load = () => getGuardrails().then(setItems).catch(() => toast.error('Load failed'))

  const openCreate = () => {
    const f = { ...EMPTY }
    setForm(f)
    setCheckValueStr(getDefaultCheckValue(f.check_type))
    setModal('create')
  }

  const openEdit = item => {
    setForm({ ...item })
    setCheckValueStr(JSON.stringify(item.check_value, null, 2))
    setModal(item)
  }

  const getDefaultCheckValue = type => {
    if (type === 'keyword_block') return JSON.stringify({ keywords: [] }, null, 2)
    if (type === 'max_length') return JSON.stringify({ max_length: 500 }, null, 2)
    if (type === 'regex') return JSON.stringify({ pattern: '' }, null, 2)
    if (type === 'context') return JSON.stringify({ forbidden_topics: [], description: 'Only answer questions about data available in the connected database' }, null, 2)
    return '{}'
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      let cv
      try { cv = JSON.parse(checkValueStr) } catch { toast.error('Invalid JSON in check_value'); setSaving(false); return }
      const payload = { ...form, check_value: cv }
      if (modal === 'create') { await createGuardrail(payload); toast.success('Created') }
      else { await updateGuardrail(modal.id, payload); toast.success('Updated') }
      load()
      setModal(null)
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed') }
    finally { setSaving(false) }
  }

  const handleToggle = async item => {
    await toggleGuardrail(item.id)
    load()
  }

  const severityColor = s => ({ low: 'info', medium: 'warning', high: 'error', critical: 'error' }[s] || 'neutral')

  return (
    <>
      <PageHeader
        title="Guard Rails"
        subtitle="Configure prompt and response guardrails"
        actions={<button className="btn btn-primary btn-sm" onClick={openCreate}><Plus size={12} /> Add Guardrail</button>}
      />
      <div className="page-content">
        <div className="card">
          {items.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-title">No guardrails yet</div>
              <div className="empty-state-desc">Add guardrails to control what prompts and responses are allowed.</div>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Priority</th><th>Name</th><th>Check Type</th>
                  <th>Action</th><th>Severity</th><th>Status</th><th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id}>
                    <td><span className="badge badge-neutral">{item.priority}</span></td>
                    <td>
                      <div style={{ fontWeight: 600, fontSize: 12.5 }}>{item.policy_name}</div>
                      {item.description && <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>{item.description}</div>}
                    </td>
                    <td><span className="tag">{item.check_type}</span></td>
                    <td><span className="tag">{item.action}</span></td>
                    <td><span className={`badge badge-${severityColor(item.severity)}`}>{item.severity}</span></td>
                    <td>
                      <span className={`badge badge-${item.is_active ? 'success' : 'neutral'}`}>
                        {item.is_active ? 'Active' : 'Disabled'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="btn btn-ghost btn-icon btn-sm" title="Toggle active" onClick={() => handleToggle(item)}>
                          {item.is_active ? <ToggleRight size={13} style={{ color: 'var(--color-success)' }} /> : <ToggleLeft size={13} />}
                        </button>
                        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => openEdit(item)}><Pencil size={12} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {modal && (
        <Modal
          title={modal === 'create' ? 'New Guardrail' : `Edit: ${modal.policy_name}`}
          onClose={() => setModal(null)}
          size="lg"
          footer={
            <>
              <button className="btn btn-secondary btn-sm" type="button" onClick={() => setModal(null)}>Cancel</button>
              <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
            </>
          }
        >
          <div className="form-group">
              <label className="form-label">Policy Name *</label>
              <input className="form-input" value={form.policy_name} onChange={e => setForm(p => ({ ...p, policy_name: e.target.value }))} placeholder="e.g. Block PII" />
          </div>
          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="form-textarea" value={form.description || ''} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} style={{ minHeight: 50 }} />
          </div>
          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Check Type</label>
              <select className="form-select" value={form.check_type} onChange={e => {
                setForm(p => ({ ...p, check_type: e.target.value }))
                setCheckValueStr(getDefaultCheckValue(e.target.value))
              }}>
                {CHECK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Action</label>
              <select className="form-select" value={form.action} onChange={e => setForm(p => ({ ...p, action: e.target.value }))}>
                {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
          </div>
          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Severity</label>
              <select className="form-select" value={form.severity} onChange={e => setForm(p => ({ ...p, severity: e.target.value }))}>
                {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Priority (lower = first)</label>
              <input className="form-input" type="number" value={form.priority} onChange={e => setForm(p => ({ ...p, priority: parseInt(e.target.value) }))} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Check Value (JSON)</label>
            <textarea
              className="form-textarea"
              value={checkValueStr}
              onChange={e => setCheckValueStr(e.target.value)}
              style={{ minHeight: 100, fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
              keyword_block: {`{"keywords":["password","ssn"]}`} &nbsp;|&nbsp;
              max_length: {`{"max_length":500}`} &nbsp;|&nbsp;
              regex: {`{"pattern":"\\\\d{9}"}`} &nbsp;|&nbsp;
              context: {`{"forbidden_topics":["personal data"],"description":"DB-only context"}`}
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}
