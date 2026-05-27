import { useState, useEffect } from 'react'
import { User, Mail, Shield, Tag, KeyRound, Eye, EyeOff } from 'lucide-react'
import { getMe, changePassword } from '../api/client'
import toast from 'react-hot-toast'

export default function UserProfile() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  // change password form
  const [pwForm, setPwForm]     = useState({ current: '', next: '', confirm: '' })
  const [pwShow, setPwShow]     = useState({ current: false, next: false, confirm: false })
  const [pwSaving, setPwSaving] = useState(false)

  useEffect(() => {
    getMe()
      .then(setProfile)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const toggleShow = key => setPwShow(s => ({ ...s, [key]: !s[key] }))

  const handleChangePassword = async e => {
    e.preventDefault()
    if (!pwForm.current || !pwForm.next || !pwForm.confirm) {
      toast.error('All password fields required')
      return
    }
    if (pwForm.next !== pwForm.confirm) {
      toast.error('New passwords do not match')
      return
    }
    if (pwForm.next.length < 6) {
      toast.error('New password must be at least 6 characters')
      return
    }
    setPwSaving(true)
    try {
      await changePassword({ current_password: pwForm.current, new_password: pwForm.next })
      toast.success('Password changed')
      setPwForm({ current: '', next: '', confirm: '' })
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to change password')
    } finally {
      setPwSaving(false)
    }
  }

  if (loading) return (
    <div style={{ padding: 32, color: 'var(--text-tertiary)', fontSize: 13 }}>Loading…</div>
  )

  if (!profile) return (
    <div style={{ padding: 32, color: 'var(--color-error, #ef4444)', fontSize: 13 }}>Failed to load profile.</div>
  )

  const sgs       = profile.security_groups || []
  const firstName = profile.FirstName || profile.first_name || ''
  const lastName  = profile.LastName  || profile.last_name  || ''
  const email     = profile.Email     || profile.email      || ''
  const role      = profile.role      || ''

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        height: 52, minHeight: 52, background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex', alignItems: 'center', padding: '0 16px', flexShrink: 0,
      }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>My Profile</span>
      </div>

      {/* Content — two-column on wide screens */}
      <div style={{ flex: 1, overflow: 'auto', padding: 24, display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 20, alignItems: 'flex-start' }}>

        {/* ── Profile card (left) ── */}
        <div style={{
          flex: '1 1 340px', maxWidth: 480,
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-default)',
          borderRadius: 10, padding: 24,
          display: 'flex', flexDirection: 'column', gap: 20,
        }}>
          {/* Avatar row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{
              width: 52, height: 52, borderRadius: '50%',
              background: 'var(--brand-primary)', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 18, fontWeight: 700, flexShrink: 0,
            }}>
              {`${firstName[0] || ''}${lastName[0] || ''}`.toUpperCase() || '?'}
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                {firstName} {lastName}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 2 }}>{role}</div>
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--border-subtle)' }} />

          <Field icon={<User size={13} />} label="First Name" value={firstName} />
          <Field icon={<User size={13} />} label="Last Name"  value={lastName} />
          <Field icon={<Mail size={13} />} label="Email"      value={email} />
          <Field icon={<Tag  size={13} />} label="Role"       value={role} />

          {/* Security Groups */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Shield size={13} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }} />
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Security Groups
              </span>
            </div>
            {sgs.length === 0 ? (
              <span style={{ fontSize: 12, color: 'var(--text-placeholder)' }}>No groups assigned</span>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {sgs.map(sg => (
                  <span key={sg.SecurityGroupID} style={{
                    display: 'inline-flex', alignItems: 'center',
                    padding: '3px 10px', borderRadius: 'var(--radius-pill)',
                    fontSize: 11.5, fontWeight: 600,
                    background: 'var(--brand-orange-subtle)',
                    color: 'var(--brand-orange)',
                    border: '1px solid var(--brand-orange)',
                  }}>
                    {sg.SecurityGroupName}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Change Password card (right) ── */}
        <div style={{
          flex: '1 1 280px', maxWidth: 420,
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-default)',
          borderRadius: 10, padding: 24,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
            <KeyRound size={14} style={{ color: 'var(--text-tertiary)' }} />
            <span style={{ fontSize: 13, fontWeight: 700 }}>Change Password</span>
          </div>

          <form onSubmit={handleChangePassword} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <PwField
              label="Current Password"
              value={pwForm.current}
              show={pwShow.current}
              onChange={v => setPwForm(f => ({ ...f, current: v }))}
              onToggle={() => toggleShow('current')}
              disabled={pwSaving}
            />
            <PwField
              label="New Password"
              value={pwForm.next}
              show={pwShow.next}
              onChange={v => setPwForm(f => ({ ...f, next: v }))}
              onToggle={() => toggleShow('next')}
              disabled={pwSaving}
            />
            <PwField
              label="Confirm New Password"
              value={pwForm.confirm}
              show={pwShow.confirm}
              onChange={v => setPwForm(f => ({ ...f, confirm: v }))}
              onToggle={() => toggleShow('confirm')}
              disabled={pwSaving}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={pwSaving}
              >
                {pwSaving ? 'Saving…' : 'Change Password'}
              </button>
            </div>
          </form>
        </div>

      </div>
    </div>
  )
}

function Field({ icon, label, value }) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
        <span style={{ color: 'var(--text-tertiary)' }}>{icon}</span>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {label}
        </span>
      </div>
      <div style={{
        fontSize: 13, color: 'var(--text-primary)',
        background: 'var(--bg-subtle)', border: '1px solid var(--border-default)',
        borderRadius: 6, padding: '7px 12px',
      }}>
        {value || '—'}
      </div>
    </div>
  )
}

function PwField({ label, value, show, onChange, onToggle, disabled }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 5 }}>
        {label}
      </div>
      <div style={{ position: 'relative' }}>
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={e => onChange(e.target.value)}
          disabled={disabled}
          className="form-input"
          style={{ width: '100%', paddingRight: 36, boxSizing: 'border-box' }}
          autoComplete="new-password"
        />
        <button
          type="button"
          onClick={onToggle}
          style={{
            position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
            background: 'none', border: 'none', padding: 0,
            color: 'var(--text-tertiary)', cursor: 'pointer', display: 'flex',
          }}
          tabIndex={-1}
        >
          {show ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
      </div>
    </div>
  )
}
