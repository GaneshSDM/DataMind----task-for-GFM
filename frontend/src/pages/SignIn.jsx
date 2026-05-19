import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import { Eye, EyeOff, Shield, Database, GitBranch, Zap, Lock, X } from 'lucide-react'

const FEATURES = [
  { icon: Shield, title: 'Multi-Layer Security', desc: 'Row & column level security with fine-grained access control per user group' },
  { icon: Database, title: 'Data Governance', desc: 'Domain, sub-domain and geography-based data classification and access policies' },
  { icon: GitBranch, title: 'Smart Guardrails', desc: 'Keyword, regex and context-aware prompt filtering before LLM execution' },
  { icon: Zap, title: 'Secure AI Queries', desc: 'Security context injected into every LLM request — zero trust data access' },
]

export default function SignIn() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [forgotModal, setForgotModal] = useState(false)
  const { login, loading } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async e => {
    e.preventDefault()
    try {
      await login(email, password)
      navigate('/chats')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Invalid credentials')
    }
  }

  return (
    <div className="signin-page">
      {/* Left panel — branding */}
      <div className="signin-left">
        <div className="signin-brand">
          <div className="signin-logo">
            <span>DM</span>
          </div>
          <div>
            <div className="signin-appname">DataMind</div>
            <div className="signin-powered">Powered by <strong>Decision Minds</strong></div>
          </div>
        </div>

        <div className="signin-headline">
          <h2>Secure Intelligence.<br />Governed Access.</h2>
          <p>Enterprise-grade data query platform with built-in security, governance, and AI guardrails.</p>
        </div>

        <div className="signin-features">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="signin-feature">
              <div className="signin-feature-icon"><Icon size={16} /></div>
              <div>
                <div className="signin-feature-title">{title}</div>
                <div className="signin-feature-desc">{desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel — form */}
      <div className="signin-right">
        <div className="signin-card">
          <div className="signin-card-header">
            <div className="signin-card-logo">DM</div>
            <h1>Welcome back</h1>
            <p>Sign in to your DataMind account</p>
          </div>

          <form onSubmit={handleSubmit} className="signin-form">
            <div className="form-group">
              <label className="form-label">Email address</label>
              <input
                className="form-input"
                type="email" required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@company.com"
                autoFocus
              />
            </div>

            <div className="form-group">
              <div className="signin-pw-label">
                <label className="form-label">Password</label>
                <button type="button" className="signin-forgot" onClick={() => setForgotModal(true)}>
                  Forgot password?
                </button>
              </div>
              <div className="signin-pw-wrap">
                <input
                  className="form-input"
                  type={showPw ? 'text' : 'password'} required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{ paddingRight: 38 }}
                />
                <button type="button" className="signin-pw-toggle" onClick={() => setShowPw(p => !p)} tabIndex={-1}>
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-lg"
              disabled={loading}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <div className="signin-footer">
            <Lock size={11} />
            Secured by DataMind · Decision Minds © 2026
          </div>
        </div>
      </div>

      {/* Forgot password modal */}
      {forgotModal && (
        <div className="modal-overlay" onClick={() => setForgotModal(false)}>
          <div className="modal" style={{ maxWidth: 400 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">Reset Password</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setForgotModal(false)}><X size={14} /></button>
            </div>
            <div className="modal-body">
              <div style={{ textAlign: 'center', padding: '12px 0' }}>
                <div style={{ width: 48, height: 48, borderRadius: '50%', background: 'var(--color-info-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <Lock size={20} style={{ color: 'var(--color-info)' }} />
                </div>
                <p style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>Contact your administrator</p>
                <p style={{ fontSize: 12.5, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
                  Password resets are managed by your system administrator.<br />
                  Please reach out to your admin to reset your password.
                </p>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-primary btn-sm" onClick={() => setForgotModal(false)}>Got it</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
