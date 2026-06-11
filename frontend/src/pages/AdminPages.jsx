import { useState, useEffect } from 'react'
import { Plus, Pencil, Trash2, TestTube, KeyRound, Shield, Mail, User } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import PageHeader from '../components/common/PageHeader'
import Modal from '../components/common/Modal'
import CRUDPage from '../components/common/CRUDPage'
import {
  getUsers, createUser, updateUser, resetUserPassword,
  getRLS, createRLS, updateRLS, deleteRLS,
  getCLS, createCLS, updateCLS, deleteCLS,
  getSLMConfigs, createSLMConfig, updateSLMConfig, testSLMConfig,
  getDBConnections, createDBConnection, deleteDBConnection, testDBConnection,
  getSecurityGroups, assignSecurityGroup, removeSecurityGroup, getUserSecurityGroups,
  getMe, changePassword,
} from '../api/client'
import toast from 'react-hot-toast'

// ── User Management ──────────────────────────────────────────────────────────
export function UserManagement() {
  const { user } = useAuth()
  const [users, setUsers] = useState([])
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({})
  const [formSGs, setFormSGs] = useState([])
  const [saving, setSaving] = useState(false)
  const [securityGroups, setSecurityGroups] = useState([])
  const [pwModal, setPwModal] = useState(false)
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', confirm_password: '' })
  const [pwSaving, setPwSaving] = useState(false)
  const [resetModal, setResetModal] = useState(null) // holds target user object
  const [resetPw, setResetPw] = useState('')
  const [resetSaving, setResetSaving] = useState(false)
  const isAdmin = user?.role === 'Admin'

  useEffect(() => {
    if (isAdmin) {
      loadUsers()
      getSecurityGroups().then(setSecurityGroups).catch(() => {})
    } else {
      getMe().then(u => setUsers([u])).catch(() => toast.error('Load failed'))
    }
  }, [isAdmin])

  const handleResetPassword = async () => {
    if (!resetPw || resetPw.length < 6) { toast.error('Password must be at least 6 characters'); return }
    setResetSaving(true)
    try {
      await resetUserPassword(resetModal.UserID, { new_password: resetPw })
      toast.success(`Password reset for ${resetModal.FirstName} ${resetModal.LastName}`)
      setResetModal(null); setResetPw('')
    } catch (err) { toast.error(err.response?.data?.detail || 'Reset failed') }
    finally { setResetSaving(false) }
  }

  const handleChangePassword = async () => {
    if (pwForm.new_password !== pwForm.confirm_password) {
      toast.error('New passwords do not match'); return
    }
    setPwSaving(true)
    try {
      await changePassword({ current_password: pwForm.current_password, new_password: pwForm.new_password })
      toast.success('Password changed successfully')
      setPwModal(false)
      setPwForm({ current_password: '', new_password: '', confirm_password: '' })
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to change password') }
    finally { setPwSaving(false) }
  }

  const loadUsers = () => getUsers().then(setUsers).catch(() => toast.error('Load failed'))

  const openCreate = () => { setForm({}); setFormSGs([]); setModal('create') }
  const openEdit = u => {
    setForm({ ...u, RoleID: u.role === 'Admin' ? 1 : 2 })
    setFormSGs((u.security_groups || []).map(sg => sg.SecurityGroupID))
    setModal(u)
  }

  const toggleSG = id => setFormSGs(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const handleSave = async () => {
    setSaving(true)
    try {
      let savedUser
      if (modal === 'create') {
        savedUser = await createUser(form)
        toast.success('User created')
      } else {
        savedUser = await updateUser(modal.UserID, form)
        toast.success('User updated')
      }
      const uid = savedUser.UserID
      const prevSGIds = modal === 'create' ? [] : (modal.security_groups || []).map(sg => sg.SecurityGroupID)
      const toAdd = formSGs.filter(id => !prevSGIds.includes(id))
      const toRemove = prevSGIds.filter(id => !formSGs.includes(id))
      await Promise.all([
        ...toAdd.map(id => assignSecurityGroup(uid, id)),
        ...toRemove.map(id => removeSecurityGroup(uid, id)),
      ])
      loadUsers(); setModal(null)
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed') }
    finally { setSaving(false) }
  }

  if (!isAdmin) {
    const u = users[0]
    const initials = u ? `${(u.FirstName || '')[0] || ''}${(u.LastName || '')[0] || ''}`.toUpperCase() : '?'
    return (
      <>
        <PageHeader
          title="My Account"
          subtitle="View your profile and manage security settings"
          actions={<button className="btn btn-primary btn-sm" onClick={() => setPwModal(true)}><KeyRound size={12} /> Change Password</button>}
        />
        <div className="page-content">
          {u && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Profile header card */}
              <div className="card" style={{ padding: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                  <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'var(--brand-primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, fontWeight: 700, flexShrink: 0 }}>
                    {initials}
                  </div>
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>{u.FirstName} {u.LastName}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                      <span className={`badge badge-${u.role === 'Admin' ? 'error' : 'blue'}`}>{u.role || 'User'}</span>
                      <span className={`badge badge-${u.IsActive ? 'success' : 'neutral'}`}>{u.IsActive ? 'Active' : 'Inactive'}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Details card */}
              <div className="card">
                <div className="card-header">
                  <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><User size={14} /> Account Details</span>
                </div>
                <div className="card-body">
                  <div className="grid-2">
                    <div className="form-group">
                      <label className="form-label">First Name</label>
                      <input className="form-input" type="text" value={u.FirstName || ''} disabled style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Last Name</label>
                      <input className="form-input" type="text" value={u.LastName || ''} disabled style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }} />
                    </div>
                    <div className="form-group">
                      <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 5 }}><Mail size={11} /> Email</label>
                      <input className="form-input" type="text" value={u.Email || ''} disabled style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Contact</label>
                      <input className="form-input" type="text" value={u.Contact || '—'} disabled style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Security groups card */}
              {u.security_groups && u.security_groups.length > 0 && (
                <div className="card">
                  <div className="card-header">
                    <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Shield size={14} /> Security Groups</span>
                  </div>
                  <div className="card-body">
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {u.security_groups.map(sg => (
                        <span key={sg.SecurityGroupID} className="tag">{sg.SecurityGroupName}</span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Change Password Modal */}
        {pwModal && (
          <Modal
            title="Change Password"
            onClose={() => { setPwModal(false); setPwForm({ current_password: '', new_password: '', confirm_password: '' }) }}
            footer={<>
              <button className="btn btn-secondary btn-sm" onClick={() => setPwModal(false)}>Cancel</button>
              <button className="btn btn-primary btn-sm" onClick={handleChangePassword} disabled={pwSaving}>{pwSaving ? 'Saving…' : 'Change Password'}</button>
            </>}
          >
            <div className="form-group">
              <label className="form-label">Current Password</label>
              <input className="form-input" type="password" value={pwForm.current_password} onChange={e => setPwForm(p => ({ ...p, current_password: e.target.value }))} placeholder="Enter current password" />
            </div>
            <div className="form-group">
              <label className="form-label">New Password</label>
              <input className="form-input" type="password" value={pwForm.new_password} onChange={e => setPwForm(p => ({ ...p, new_password: e.target.value }))} placeholder="Enter new password (min. 6 chars)" />
            </div>
            <div className="form-group">
              <label className="form-label">Confirm New Password</label>
              <input className="form-input" type="password" value={pwForm.confirm_password} onChange={e => setPwForm(p => ({ ...p, confirm_password: e.target.value }))} placeholder="Confirm new password" />
            </div>
          </Modal>
        )}
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="User Management"
        subtitle="Create and manage users and their roles"
        actions={<button className="btn btn-primary btn-sm" onClick={openCreate}><Plus size={12} /> New User</button>}
      />
      <div className="page-content">
        <div className="card">
          {users.length === 0 ? <div className="empty-state"><div className="empty-state-title">No users</div></div> : (
            <table className="data-table">
              <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Security Groups</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.UserID}>
                    <td style={{ fontWeight: 600 }}>{u.FirstName} {u.LastName}</td>
                    <td style={{ color: 'var(--text-secondary)' }}>{u.Email}</td>
                    <td><span className={`badge badge-${u.role === 'Admin' ? 'error' : 'blue'}`}>{u.role || 'User'}</span></td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {(u.security_groups || []).length === 0
                          ? <span style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>—</span>
                          : (u.security_groups || []).map(sg => (
                            <span key={sg.SecurityGroupID} className="tag" style={{ fontSize: 11 }}>{sg.SecurityGroupName}</span>
                          ))
                        }
                      </div>
                    </td>
                    <td><span className={`badge badge-${u.IsActive ? 'success' : 'neutral'}`}>{u.IsActive ? 'Active' : 'Inactive'}</span></td>
                    <td>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => openEdit(u)} title="Edit user"><Pencil size={12} /></button>
                        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => { setResetModal(u); setResetPw('') }} title="Reset password"><KeyRound size={12} /></button>
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
          title={modal === 'create' ? 'New User' : 'Edit User'}
          onClose={() => setModal(null)}
          footer={<>
            <button className="btn btn-secondary btn-sm" type="button" onClick={() => setModal(null)}>Cancel</button>
            <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          </>}
        >
          <div className="grid-2">
            <div className="form-group"><label className="form-label">First Name</label><input className="form-input" value={form.FirstName || ''} onChange={e => setForm(p => ({ ...p, FirstName: e.target.value }))} /></div>
            <div className="form-group"><label className="form-label">Last Name</label><input className="form-input" value={form.LastName || ''} onChange={e => setForm(p => ({ ...p, LastName: e.target.value }))} /></div>
          </div>
          <div className="form-group"><label className="form-label">Email</label><input className="form-input" type="email" value={form.Email || ''} onChange={e => setForm(p => ({ ...p, Email: e.target.value }))} /></div>
          {modal === 'create' && <div className="form-group"><label className="form-label">Password</label><input className="form-input" type="password" value={form.Password || ''} onChange={e => setForm(p => ({ ...p, Password: e.target.value }))} /></div>}
          <div className="form-group">
            <label className="form-label">Role</label>
            <select className="form-select" value={form.RoleID || 2} onChange={e => setForm(p => ({ ...p, RoleID: parseInt(e.target.value) }))}>
              <option value={2}>User</option>
              <option value={1}>Admin</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Security Groups</label>
            <div style={{ border: '1px solid var(--border-default)', borderRadius: 6, padding: 8, maxHeight: 120, overflowY: 'auto', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {securityGroups.length === 0
                ? <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>No security groups available</span>
                : securityGroups.map(sg => {
                  const checked = formSGs.includes(sg.SecurityGroupID)
                  return (
                    <label key={sg.SecurityGroupID} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', padding: '3px 8px', borderRadius: 4, background: checked ? 'var(--brand-primary-subtle)' : 'var(--bg-elevated)', border: `1px solid ${checked ? 'var(--brand-primary)' : 'var(--border-default)'}`, fontSize: 11.5 }}>
                      <input type="checkbox" checked={checked} onChange={() => toggleSG(sg.SecurityGroupID)} style={{ display: 'none' }} />
                      <span style={{ color: checked ? 'var(--brand-primary)' : 'var(--text-secondary)' }}>{sg.SecurityGroupName}</span>
                    </label>
                  )
                })
              }
            </div>
          </div>
          {modal !== 'create' && (
            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form.IsActive !== false} onChange={e => setForm(p => ({ ...p, IsActive: e.target.checked }))} />
                Active
              </label>
            </div>
          )}
        </Modal>
      )}

      {resetModal && (
        <Modal
          title={`Reset Password — ${resetModal.FirstName} ${resetModal.LastName}`}
          onClose={() => { setResetModal(null); setResetPw('') }}
          footer={<>
            <button className="btn btn-secondary btn-sm" onClick={() => setResetModal(null)}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={handleResetPassword} disabled={resetSaving}>{resetSaving ? 'Resetting…' : 'Reset Password'}</button>
          </>}
        >
          <div className="form-group">
            <label className="form-label">New Password</label>
            <input className="form-input" type="password" value={resetPw} onChange={e => setResetPw(e.target.value)} placeholder="Enter new password (min. 6 chars)" autoFocus />
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>User will need to use this new password on next login.</p>
        </Modal>
      )}
    </>
  )
}


// ── RLS Page ─────────────────────────────────────────────────────────────────
export function RLSPage() {
  const [items, setItems] = useState([])
  const [modal, setModal] = useState(null) // null | 'create' | item
  const [form, setForm] = useState({ RLSName: '', TargetTable: '', FilterExpression: '', Description: '', IsActive: true })
  const [saving, setSaving] = useState(false)

  const load = () => getRLS().then(setItems).catch(() => {})
  useEffect(() => { load() }, [])

  const openCreate = () => { setForm({ RLSName: '', TargetTable: '', FilterExpression: '', Description: '', IsActive: true }); setModal('create') }
  const openEdit = r => { setForm({ RLSName: r.RLSName, TargetTable: r.TargetTable, FilterExpression: r.FilterExpression || '', Description: r.Description || '', IsActive: r.IsActive }); setModal(r) }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (modal === 'create') { await createRLS(form); toast.success('RLS created') }
      else { await updateRLS(modal.RLS_ID, form); toast.success('RLS updated') }
      load(); setModal(null)
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
    finally { setSaving(false) }
  }

  return (
    <>
      <PageHeader
        title="Row Level Security"
        subtitle="Define row-level filtering rules for tables"
        actions={<button className="btn btn-primary btn-sm" onClick={openCreate}><Plus size={12} /> New RLS</button>}
      />
      <div className="page-content">
        <div className="card">
          {items.length === 0 ? <div className="empty-state"><div className="empty-state-title">No RLS policies</div></div> : (
            <table className="data-table">
              <thead><tr><th>#</th><th>Name</th><th>Target Table</th><th>Filter</th><th>Conditions</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {items.map(r => (
                  <tr key={r.RLS_ID}>
                    <td>{r.RLS_ID}</td>
                    <td style={{ fontWeight: 600 }}>{r.RLSName}</td>
                    <td><span className="tag">{r.TargetTable}</span></td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{r.FilterExpression || '—'}</td>
                    <td><span className="badge badge-blue">{r.conditions?.length ?? 0}</span></td>
                    <td><span className={`badge badge-${r.IsActive ? 'success' : 'neutral'}`}>{r.IsActive ? 'Active' : 'Inactive'}</span></td>
                    <td>
                      <button className="btn btn-ghost btn-icon btn-sm" onClick={() => openEdit(r)}><Pencil size={12} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {modal && (
        <Modal title={modal === 'create' ? 'New Row Level Security' : `Edit: ${modal.RLSName}`} onClose={() => setModal(null)} size="lg"
          footer={<>
            <button className="btn btn-secondary btn-sm" type="button" onClick={() => setModal(null)}>Cancel</button>
            <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          </>}
        >
          <div className="grid-2">
            <div className="form-group"><label className="form-label">RLS Name *</label><input className="form-input" value={form.RLSName} onChange={e => setForm(p => ({ ...p, RLSName: e.target.value }))} /></div>
            <div className="form-group"><label className="form-label">Target Table *</label><input className="form-input" value={form.TargetTable} onChange={e => setForm(p => ({ ...p, TargetTable: e.target.value }))} placeholder="e.g. sales_data" /></div>
          </div>
          <div className="form-group"><label className="form-label">Filter Expression</label><input className="form-input" value={form.FilterExpression || ''} onChange={e => setForm(p => ({ ...p, FilterExpression: e.target.value }))} placeholder="e.g. region = 'APAC'" /></div>
          <div className="form-group"><label className="form-label">Description</label><textarea className="form-textarea" value={form.Description || ''} onChange={e => setForm(p => ({ ...p, Description: e.target.value }))} style={{ minHeight: 60 }} /></div>
          {modal !== 'create' && (
            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form.IsActive !== false} onChange={e => setForm(p => ({ ...p, IsActive: e.target.checked }))} />
                Active
              </label>
            </div>
          )}
        </Modal>
      )}
    </>
  )
}


// ── CLS Page ─────────────────────────────────────────────────────────────────
export function CLSPage() {
  const [items, setItems] = useState([])
  const [modal, setModal] = useState(null) // null | 'create' | item
  const [form, setForm] = useState({ CLSName: '', TargetTable: '', columns: [], IsActive: true })
  const [colRow, setColRow] = useState({ ColumnName: '', CanRead: true, CanWrite: false })
  const [saving, setSaving] = useState(false)

  const load = () => getCLS().then(setItems).catch(() => {})
  useEffect(() => { load() }, [])

  const openCreate = () => { setForm({ CLSName: '', TargetTable: '', columns: [], IsActive: true }); setModal('create') }
  const openEdit = c => {
    setForm({
      CLSName: c.CLSName, TargetTable: c.TargetTable, IsActive: c.IsActive,
      columns: (c.column_mappings || []).map(cm => ({ ColumnName: cm.ColumnName, CanRead: cm.CanRead, CanWrite: cm.CanWrite })),
    })
    setModal(c)
  }

  const addCol = () => {
    if (!colRow.ColumnName) return
    setForm(p => ({ ...p, columns: [...(p.columns || []), { ...colRow }] }))
    setColRow({ ColumnName: '', CanRead: true, CanWrite: false })
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (modal === 'create') { await createCLS(form); toast.success('CLS created') }
      else { await updateCLS(modal.CLS_ID, form); toast.success('CLS updated') }
      load(); setModal(null)
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
    finally { setSaving(false) }
  }

  return (
    <>
      <PageHeader
        title="Column Level Security"
        subtitle="Define column-level access rules for tables"
        actions={<button className="btn btn-primary btn-sm" onClick={openCreate}><Plus size={12} /> New CLS</button>}
      />
      <div className="page-content">
        <div className="card">
          {items.length === 0 ? <div className="empty-state"><div className="empty-state-title">No CLS policies</div></div> : (
            <table className="data-table">
              <thead><tr><th>#</th><th>Name</th><th>Target Table</th><th>Columns</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {items.map(c => (
                  <tr key={c.CLS_ID}>
                    <td>{c.CLS_ID}</td>
                    <td style={{ fontWeight: 600 }}>{c.CLSName}</td>
                    <td><span className="tag">{c.TargetTable}</span></td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {c.column_mappings?.map(cm => (
                          <span key={cm.MappingID} className="tag">{cm.ColumnName} {cm.CanRead ? '📖' : ''}{cm.CanWrite ? '✏️' : ''}</span>
                        ))}
                      </div>
                    </td>
                    <td><span className={`badge badge-${c.IsActive ? 'success' : 'neutral'}`}>{c.IsActive ? 'Active' : 'Inactive'}</span></td>
                    <td>
                      <button className="btn btn-ghost btn-icon btn-sm" onClick={() => openEdit(c)}><Pencil size={12} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {modal && (
        <Modal title={modal === 'create' ? 'New Column Level Security' : `Edit: ${modal.CLSName}`} onClose={() => setModal(null)} size="lg"
          footer={<>
            <button className="btn btn-secondary btn-sm" type="button" onClick={() => setModal(null)}>Cancel</button>
            <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          </>}
        >
          <div className="grid-2">
            <div className="form-group"><label className="form-label">CLS Name</label><input className="form-input" value={form.CLSName} onChange={e => setForm(p => ({ ...p, CLSName: e.target.value }))} /></div>
            <div className="form-group"><label className="form-label">Target Table</label><input className="form-input" value={form.TargetTable} onChange={e => setForm(p => ({ ...p, TargetTable: e.target.value }))} /></div>
          </div>
          {modal !== 'create' && (
            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form.IsActive !== false} onChange={e => setForm(p => ({ ...p, IsActive: e.target.checked }))} />
                Active
              </label>
            </div>
          )}
          <div style={{ border: '1px solid var(--border-default)', borderRadius: 6, padding: 12 }}>
            <div style={{ fontSize: 11.5, fontWeight: 700, marginBottom: 8 }}>Column Mappings</div>
            {(form.columns || []).map((c, i) => (
              <div key={i} className="flex-row" style={{ marginBottom: 6, background: 'var(--bg-elevated)', padding: '4px 8px', borderRadius: 4 }}>
                <span style={{ flex: 1, fontSize: 12, fontFamily: 'var(--font-mono)' }}>{c.ColumnName}</span>
                <span className={`badge badge-${c.CanRead ? 'success' : 'neutral'}`}>Read</span>
                <span className={`badge badge-${c.CanWrite ? 'success' : 'neutral'}`}>Write</span>
                <button className="btn btn-ghost btn-icon btn-sm" style={{ color: 'var(--color-error)' }} onClick={() => setForm(p => ({ ...p, columns: p.columns.filter((_, j) => j !== i) }))}><Trash2 size={10} /></button>
              </div>
            ))}
            <div className="flex-row" style={{ marginTop: 8 }}>
              <input className="form-input" style={{ flex: 1 }} placeholder="Column name" value={colRow.ColumnName} onChange={e => setColRow(p => ({ ...p, ColumnName: e.target.value }))} />
              <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                <input type="checkbox" checked={colRow.CanRead} onChange={e => setColRow(p => ({ ...p, CanRead: e.target.checked }))} /> Read
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                <input type="checkbox" checked={colRow.CanWrite} onChange={e => setColRow(p => ({ ...p, CanWrite: e.target.checked }))} /> Write
              </label>
              <button className="btn btn-secondary btn-sm" onClick={addCol}><Plus size={11} /></button>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}


// ── SLM Config ────────────────────────────────────────────────────────────────
export function SLMConfigPage() {
  const [configs, setConfigs] = useState([])
  const [modal, setModal] = useState(null) // null | 'create' | config object
  const [form, setForm] = useState({ BaseURL: '', APIKey: '', TimeoutSeconds: 30, MaxRetries: 3 })
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  useEffect(() => { load() }, [])

  const load = () => getSLMConfigs().then(setConfigs).catch(() => {})

  const openCreate = () => {
    setForm({ BaseURL: '', APIKey: '', TimeoutSeconds: 30, MaxRetries: 3 })
    setModal('create')
  }

  const openEdit = (cfg) => {
    setForm({ BaseURL: cfg.BaseURL, APIKey: '', TimeoutSeconds: cfg.TimeoutSeconds, MaxRetries: cfg.MaxRetries })
    setModal(cfg)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (modal === 'create') await createSLMConfig(form)
      else await updateSLMConfig(modal.ConfigID, form)
      toast.success('Saved')
      load()
      setModal(null)
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
    finally { setSaving(false) }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const r = await testSLMConfig(form)
      if (r.status === 'ok') toast.success('Connection successful!')
      else toast.error(r.detail || 'Connection failed')
    } catch { toast.error('Test failed') }
    finally { setTesting(false) }
  }

  const handleActivate = async (cfg) => {
    // Deactivate all then activate selected — done server-side on create/update
    await updateSLMConfig(cfg.ConfigID, { BaseURL: cfg.BaseURL, TimeoutSeconds: cfg.TimeoutSeconds, MaxRetries: cfg.MaxRetries })
    toast.success(`"${cfg.BaseURL}" set as active`)
    load()
  }

  const activeConfig = configs.find(c => c.IsActive)

  return (
    <>
      <PageHeader
        title="LLM API Configuration"
        subtitle="Only one connection can be active at a time"
        actions={<button className="btn btn-primary btn-sm" type="button" onClick={openCreate}><Plus size={12} /> Add Config</button>}
      />
      <div className="page-content">
        {configs.length === 0 ? (
          <div className="empty-state card" style={{ padding: 40 }}>
            <div className="empty-state-title">No LLM API configured</div>
            <div className="empty-state-desc">Add an endpoint to connect to Groq, OpenAI, or any OpenAI-compatible API.</div>
          </div>
        ) : (
          <div className="card">
            <table className="data-table">
              <thead>
                <tr><th>Base URL</th><th>Timeout</th><th>Retries</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {configs.map(cfg => (
                  <tr key={cfg.ConfigID}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{cfg.BaseURL}</td>
                    <td>{cfg.TimeoutSeconds}s</td>
                    <td>{cfg.MaxRetries}</td>
                    <td>
                      {cfg.IsActive
                        ? <span className="badge badge-success">● Active</span>
                        : <span className="badge badge-neutral">Inactive</span>
                      }
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {!cfg.IsActive && (
                          <button className="btn btn-secondary btn-sm" type="button" onClick={() => handleActivate(cfg)}>
                            Set Active
                          </button>
                        )}
                        <button className="btn btn-ghost btn-icon btn-sm" type="button" onClick={() => openEdit(cfg)}>
                          <Pencil size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modal && (
        <Modal title={modal === 'create' ? 'New LLM API Config' : 'Edit Config'} onClose={() => setModal(null)}
          footer={<>
            <button className="btn btn-secondary btn-sm" type="button" onClick={handleTest} disabled={testing}>{testing ? 'Testing…' : 'Test Connection'}</button>
            <button className="btn btn-secondary btn-sm" type="button" onClick={() => setModal(null)}>Cancel</button>
            <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save & Set Active'}</button>
          </>}
        >
          <div className="form-group">
            <label className="form-label">Base URL *</label>
            <input className="form-input" value={form.BaseURL} onChange={e => setForm(p => ({ ...p, BaseURL: e.target.value }))}
              placeholder="https://api.groq.com/openai/v1/chat/completions" autoComplete="off" onKeyDown={e => e.key === 'Enter' && e.preventDefault()} />
          </div>
          <div className="form-group">
            <label className="form-label">API Key</label>
            <input className="form-input" value={form.APIKey} onChange={e => setForm(p => ({ ...p, APIKey: e.target.value }))}
              placeholder="gsk_… (leave blank to use .env LLM_API_KEY)" autoComplete="off" onKeyDown={e => e.key === 'Enter' && e.preventDefault()} />
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>Leave blank — key loaded from .env LLM_API_KEY</div>
          </div>
          <div className="grid-2">
            <div className="form-group"><label className="form-label">Timeout (s)</label>
              <input className="form-input" type="number" value={form.TimeoutSeconds} onChange={e => setForm(p => ({ ...p, TimeoutSeconds: parseInt(e.target.value) }))} /></div>
            <div className="form-group"><label className="form-label">Max Retries</label>
              <input className="form-input" type="number" value={form.MaxRetries} onChange={e => setForm(p => ({ ...p, MaxRetries: parseInt(e.target.value) }))} /></div>
          </div>
          <div style={{ background: 'var(--bg-subtle)', borderRadius: 6, padding: '10px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>
            <strong>Saving activates this config</strong> and deactivates all others.
          </div>
        </Modal>
      )}
    </>
  )
}


// ── DB Connections ────────────────────────────────────────────────────────────
const EMPTY_PG_FORM = {
  ConnectionName: '', DbType: 'postgres',
  Host: 'localhost', Port: 5432, DatabaseName: '', Username: '', Password: '',
}
const EMPTY_SF_FORM = {
  ConnectionName: '', DbType: 'snowflake',
  Host: '', Port: 443, DatabaseName: '', Username: '', Password: '',
  Account: '', Warehouse: '', Role: '', Schema: '', Authenticator: 'externalbrowser',
}

export function DBConnectionsPage() {
  const [conns, setConns] = useState([])
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState(EMPTY_PG_FORM)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  useEffect(() => { getDBConnections().then(setConns).catch(() => {}) }, [])

  const openAdd = () => {
    setForm(EMPTY_PG_FORM)
    setModal(true)
  }

  const switchType = (newType) => {
    setForm(f => {
      // preserve ConnectionName + Username across switch, reset type-specific fields
      if (newType === 'snowflake') {
        return {
          ...EMPTY_SF_FORM,
          ConnectionName: f.ConnectionName,
          Username: f.Username,
          Password: f.Password,
        }
      }
      return {
        ...EMPTY_PG_FORM,
        ConnectionName: f.ConnectionName,
        Username: f.Username,
        Password: f.Password,
      }
    })
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = form.DbType === 'snowflake'
        ? {
            ConnectionName: form.ConnectionName, DbType: 'snowflake',
            Host: form.Account || form.Host,            // SF connects by account, not host
            Port: 443,
            DatabaseName: form.DatabaseName,
            Username: form.Username, Password: form.Password,
            Account: form.Account, Warehouse: form.Warehouse,
            Role: form.Role, Schema: form.Schema, Authenticator: form.Authenticator,
          }
        : { ...form }
      await createDBConnection(payload)
      toast.success('Connection saved')
      getDBConnections().then(setConns)
      setModal(false)
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
    finally { setSaving(false) }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const payload = form.DbType === 'snowflake'
        ? {
            ConnectionName: form.ConnectionName, DbType: 'snowflake',
            Host: form.Account || form.Host, Port: 443,
            DatabaseName: form.DatabaseName,
            Username: form.Username, Password: form.Password,
            Account: form.Account, Warehouse: form.Warehouse,
            Role: form.Role, Schema: form.Schema, Authenticator: form.Authenticator,
          }
        : { ...form }
      const r = await testDBConnection(payload)
      if (r.status === 'ok') toast.success(`Connection successful! (${r.db_type})`)
      else toast.error(r.detail || 'Connection failed')
    } catch { toast.error('Test failed') }
    finally { setTesting(false) }
  }

  const F = ({ label, fkey, type = 'text', placeholder }) => (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <input
        className="form-input"
        type={type === 'password' ? 'text' : type}
        placeholder={type === 'password' ? '••••••••' : placeholder}
        autoComplete="off"
        onKeyDown={e => e.key === 'Enter' && e.preventDefault()}
        value={form[fkey] ?? ''}
        onChange={e => setForm(p => ({ ...p, [fkey]: type === 'number' ? (parseInt(e.target.value) || '') : e.target.value }))}
      />
    </div>
  )

  const Sel = ({ label, fkey, options }) => (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <select
        className="form-input"
        value={form[fkey] || ''}
        onChange={e => {
          const v = e.target.value
          if (fkey === 'DbType') { switchType(v); return }
          setForm(p => ({ ...p, [fkey]: v }))
        }}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )

  return (
    <>
      <PageHeader
        title="Database Connections"
        subtitle="Manage PostgreSQL and Snowflake database connections"
        actions={<button className="btn btn-primary btn-sm" onClick={openAdd}><Plus size={12} /> Add Connection</button>}
      />
      <div className="page-content">
        <div className="card">
          {conns.length === 0 ? <div className="empty-state"><div className="empty-state-title">No database connections</div></div> : (
            <table className="data-table">
              <thead><tr><th>Name</th><th>Type</th><th>Host / Account</th><th>Database</th><th>User</th><th>Actions</th></tr></thead>
              <tbody>
                {conns.map(c => (
                  <tr key={c.ConnectionID}>
                    <td style={{ fontWeight: 600 }}>{c.ConnectionName}</td>
                    <td><span className="tag" style={{ textTransform: 'uppercase' }}>{c.DbType || 'postgres'}</span></td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                      {c.DbType === 'snowflake' ? (c.Account || c.Host) : `${c.Host}:${c.Port}`}
                    </td>
                    <td><span className="tag">{c.DatabaseName}</span></td>
                    <td>{c.Username}</td>
                    <td>
                      <button className="btn btn-ghost btn-icon btn-sm" style={{ color: 'var(--color-error)' }} onClick={async () => { await deleteDBConnection(c.ConnectionID); getDBConnections().then(setConns) }}><Trash2 size={12} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {modal && (
        <Modal title="New Database Connection" onClose={() => setModal(false)}
          footer={<>
            <button className="btn btn-secondary btn-sm" type="button" onClick={handleTest} disabled={testing}>{testing ? 'Testing…' : 'Test Connection'}</button>
            <button className="btn btn-secondary btn-sm" type="button" onClick={() => setModal(false)}>Cancel</button>
            <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          </>}
        >
          <Sel
            label="Database Type"
            fkey="DbType"
            options={[
              { value: 'postgres',  label: 'PostgreSQL' },
              { value: 'snowflake', label: 'Snowflake' },
            ]}
          />
          <F label="Connection Name" fkey="ConnectionName" placeholder="My Database" />

          {form.DbType === 'postgres' ? (
            <>
              <div className="grid-2">
                <F label="Host" fkey="Host" placeholder="localhost" />
                <F label="Port" fkey="Port" type="number" />
              </div>
              <F label="Database Name" fkey="DatabaseName" placeholder="my_db" />
              <div className="grid-2">
                <F label="Username" fkey="Username" />
                <F label="Password" fkey="Password" type="password" />
              </div>
            </>
          ) : (
            <>
              <div className="grid-2">
                <F label="Account"     fkey="Account"       placeholder="xy12345.ap-south-1" />
                <F label="Warehouse"   fkey="Warehouse"     placeholder="COMPUTE_WH" />
              </div>
              <div className="grid-2">
                <F label="Role"   fkey="Role"   placeholder="SYSADMIN" />
                <F label="Schema" fkey="Schema" placeholder="PUBLIC" />
              </div>
              <F label="Database Name" fkey="DatabaseName" placeholder="MY_DB" />
              <div className="grid-2">
                <F label="Username" fkey="Username" />
                <F label="Password" fkey="Password" type="password" placeholder="leave blank for SSO" />
              </div>
              <Sel
                label="Authenticator"
                fkey="Authenticator"
                options={[
                  { value: 'externalbrowser', label: 'External Browser (SSO)' },
                  { value: 'snowflake',       label: 'Username + Password' },
                  { value: 'oauth',           label: 'OAuth' },
                ]}
              />
            </>
          )}
        </Modal>
      )}
    </>
  )
}
