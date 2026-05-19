import { useState, useEffect } from 'react'
import { Plus, Pencil } from 'lucide-react'
import PageHeader from '../components/common/PageHeader'
import Modal from '../components/common/Modal'
import {
  getSecurityGroups, createSecurityGroup, updateSecurityGroup,
  getDomains, getSubDomains, getGeographies, getRLS, getCLS
} from '../api/client'
import toast from 'react-hot-toast'

export default function SecurityGroups() {
  const [items, setItems] = useState([])
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({ SecurityGroupName: '', domain_ids: [], subdomain_ids: [], geo_ids: [], rls_ids: [], cls_ids: [] })
  const [refs, setRefs] = useState({ domains: [], subdomains: [], geos: [], rls: [], cls: [] })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    load()
    Promise.all([getDomains(), getSubDomains(), getGeographies(), getRLS(), getCLS()])
      .then(([d, sd, g, r, c]) => setRefs({ domains: d, subdomains: sd, geos: g, rls: r, cls: c }))
      .catch(() => {})
  }, [])

  const load = () => getSecurityGroups().then(setItems).catch(() => toast.error('Load failed'))

  const openCreate = () => {
    setForm({ SecurityGroupName: '', domain_ids: [], subdomain_ids: [], geo_ids: [], rls_ids: [], cls_ids: [] })
    setModal('create')
  }

  const openEdit = item => { setForm({ ...item }); setModal(item) }

  const toggle = (key, id) => {
    const arr = form[key] || []
    setForm(p => ({ ...p, [key]: arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id] }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = {
        SecurityGroupName: form.SecurityGroupName,
        ...(modal !== 'create' && { is_active: form.is_active !== false }),
        domain_ids: form.domain_ids || [],
        subdomain_ids: form.subdomain_ids || [],
        geo_ids: form.geo_ids || [],
        rls_ids: form.rls_ids || [],
        cls_ids: form.cls_ids || [],
      }
      if (modal === 'create') { await createSecurityGroup(payload); toast.success('Created') }
      else { await updateSecurityGroup(modal.SecurityGroupID, payload); toast.success('Updated') }
      load()
      setModal(null)
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed') }
    finally { setSaving(false) }
  }

  const MultiSelect = ({ label, fieldKey, options, idKey, labelKey }) => (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <div style={{ border: '1px solid var(--border-default)', borderRadius: 6, padding: 8, maxHeight: 140, overflowY: 'auto', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {options.length === 0 ? <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>None available</span> :
          options.map(o => {
            const id = o[idKey]; const checked = (form[fieldKey] || []).includes(id)
            return (
              <label key={id} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', padding: '3px 8px', borderRadius: 4, background: checked ? 'var(--brand-primary-subtle)' : 'var(--bg-elevated)', border: `1px solid ${checked ? 'var(--brand-primary)' : 'var(--border-default)'}`, fontSize: 11.5 }}>
                <input type="checkbox" checked={checked} onChange={() => toggle(fieldKey, id)} style={{ display: 'none' }} />
                <span style={{ color: checked ? 'var(--brand-primary)' : 'var(--text-secondary)' }}>{o[labelKey]}</span>
              </label>
            )
          })
        }
      </div>
    </div>
  )

  return (
    <>
      <PageHeader
        title="Security Groups"
        subtitle="Group security configurations and assign to users"
        actions={<button className="btn btn-primary btn-sm" onClick={openCreate}><Plus size={12} /> New Group</button>}
      />
      <div className="page-content">
        <div className="card">
          {items.length === 0 ? (
            <div className="empty-state"><div className="empty-state-title">No security groups</div></div>
          ) : (
            <table className="data-table">
              <thead><tr><th>#</th><th>Name</th><th>Domains</th><th>Geographies</th><th>RLS</th><th>CLS</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {items.map(sg => (
                  <tr key={sg.SecurityGroupID}>
                    <td>{sg.SecurityGroupID}</td>
                    <td style={{ fontWeight: 600 }}>{sg.SecurityGroupName}</td>
                    <td><span className="badge badge-blue">{sg.domain_ids?.length ?? 0}</span></td>
                    <td><span className="badge badge-blue">{sg.geo_ids?.length ?? 0}</span></td>
                    <td><span className="badge badge-blue">{sg.rls_ids?.length ?? 0}</span></td>
                    <td><span className="badge badge-blue">{sg.cls_ids?.length ?? 0}</span></td>
                    <td><span className={`badge badge-${sg.IsActive ? 'success' : 'neutral'}`}>{sg.IsActive ? 'Active' : 'Inactive'}</span></td>
                    <td>
                      <button className="btn btn-ghost btn-icon btn-sm" onClick={() => openEdit(sg)}><Pencil size={12} /></button>
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
          title={modal === 'create' ? 'New Security Group' : `Edit: ${modal.SecurityGroupName}`}
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
            <label className="form-label">Group Name *</label>
            <input className="form-input" value={form.SecurityGroupName} onChange={e => setForm(p => ({ ...p, SecurityGroupName: e.target.value }))} placeholder="e.g. APAC Sales Team" />
          </div>
          {modal !== 'create' && (
            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form.is_active !== false} onChange={e => setForm(p => ({ ...p, is_active: e.target.checked }))} />
                Active
              </label>
            </div>
          )}
          <div className="grid-2">
            <MultiSelect label="Domains" fieldKey="domain_ids" options={refs.domains} idKey="DomainID" labelKey="DomainName" />
            <MultiSelect label="Sub-Domains" fieldKey="subdomain_ids" options={refs.subdomains} idKey="SubDomainID" labelKey="SubDomainName" />
          </div>
          <div className="grid-2">
            <MultiSelect label="Geographies" fieldKey="geo_ids" options={refs.geos} idKey="GeoID" labelKey="GeoName" />
            <MultiSelect label="Row Level Security" fieldKey="rls_ids" options={refs.rls} idKey="RLS_ID" labelKey="RLSName" />
          </div>
          <MultiSelect label="Column Level Security" fieldKey="cls_ids" options={refs.cls} idKey="CLS_ID" labelKey="CLSName" />
        </Modal>
      )}
    </>
  )
}
