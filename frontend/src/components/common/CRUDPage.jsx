import { useState, useEffect } from 'react'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import PageHeader from './PageHeader'
import Modal from './Modal'
import toast from 'react-hot-toast'

export default function CRUDPage({
  title, subtitle, fetchFn, createFn, updateFn, deleteFn,
  columns, formFields, getItemId, getItemLabel,
  readOnly = false, noDelete = false,
}) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null) // null | 'create' | item
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)

  useEffect(() => { load() }, [])

  const load = async () => {
    setLoading(true)
    try { setItems(await fetchFn()) } catch { toast.error('Failed to load') } finally { setLoading(false) }
  }

  const openCreate = () => { setForm({}); setModal('create') }
  const openEdit   = item => { setForm({ ...item }); setModal(item) }
  const closeModal = () => { setModal(null); setForm({}) }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (modal === 'create') {
        await createFn(form)
        toast.success('Created successfully')
      } else {
        await updateFn(getItemId(modal), form)
        toast.success('Updated successfully')
      }
      await load()
      closeModal()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Save failed')
    } finally { setSaving(false) }
  }

  const handleDelete = async item => {
    if (!confirm(`Delete "${getItemLabel(item)}"?`)) return
    try {
      await deleteFn(getItemId(item))
      toast.success('Deleted')
      await load()
    } catch { toast.error('Delete failed') }
  }

  return (
    <>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={!readOnly && (
          <button className="btn btn-primary btn-sm" onClick={openCreate}>
            <Plus size={12} /> Add {title.replace('s','')}
          </button>
        )}
      />
      <div className="page-content">
        <div className="card">
          {loading ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>Loading…</div>
          ) : items.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-title">No {title.toLowerCase()} yet</div>
              {!readOnly && <div className="empty-state-desc">Click "Add" to create the first one.</div>}
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  {columns.map(c => <th key={c.key}>{c.label}</th>)}
                  {!readOnly && <th style={{ width: 80 }}>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={getItemId(item)}>
                    {columns.map(c => (
                      <td key={c.key}>
                        {c.render ? c.render(item[c.key], item) : (item[c.key] ?? '—')}
                      </td>
                    ))}
                    {!readOnly && (
                      <td>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button className="btn btn-ghost btn-icon btn-sm" onClick={() => openEdit(item)}>
                            <Pencil size={12} />
                          </button>
                          {!noDelete && (
                            <button className="btn btn-ghost btn-icon btn-sm" style={{ color: 'var(--color-error)' }} onClick={() => handleDelete(item)}>
                              <Trash2 size={12} />
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {modal && (
        <Modal
          title={modal === 'create' ? `New ${title.replace(/s$/,'')}` : `Edit ${getItemLabel(modal)}`}
          onClose={closeModal}
          footer={
            <>
              <button className="btn btn-secondary btn-sm" type="button" onClick={closeModal}>Cancel</button>
              <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </button>
            </>
          }
        >
          {formFields.filter(f => !f.editOnly || modal !== 'create').map(f => (
            <div className="form-group" key={f.key}>
              {f.type === 'checkbox' ? (
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={form[f.key] !== false}
                    onChange={e => setForm(p => ({ ...p, [f.key]: e.target.checked }))}
                  />
                  {f.label}
                </label>
              ) : (
                <>
                  <label className="form-label">{f.label}{f.required && ' *'}</label>
                  {f.type === 'select' ? (
                    <select
                      className="form-select"
                      value={form[f.key] ?? ''}
                      onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    >
                      <option value="">Select…</option>
                      {f.options?.map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  ) : f.type === 'textarea' ? (
                    <textarea
                      className="form-textarea"
                      value={form[f.key] ?? ''}
                      onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                      placeholder={f.placeholder}
                    />
                  ) : (
                    <input
                      className="form-input"
                      type={f.type || 'text'}
                      value={form[f.key] ?? ''}
                      onChange={e => setForm(p => ({ ...p, [f.key]: f.type === 'number' ? parseInt(e.target.value) : e.target.value }))}
                      placeholder={f.placeholder}
                    />
                  )}
                </>
              )}
            </div>
          ))}
        </Modal>
      )}
    </>
  )
}
