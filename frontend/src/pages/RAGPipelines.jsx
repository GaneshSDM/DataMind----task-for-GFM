import { useState, useRef, useEffect, useCallback } from 'react'
import { Upload, Globe, Play, FileText, X, CheckCircle, Clock, AlertCircle, HardDrive, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../contexts/AuthContext'
import { Navigate } from 'react-router-dom'
import {
  getDomains, getSubDomains,
  getRagCategories, getRagSubCategories,
  getRagRuns, createRagRun,
} from '../api/client'

const SOURCES = [
  { id: 'local',      label: 'Local Upload', icon: Upload    },
  { id: 'gdrive',     label: 'Google Drive', icon: HardDrive },
  { id: 'sharepoint', label: 'SharePoint',   icon: Globe     },
]

const StatusBadge = ({ status }) => {
  const map = {
    completed:              { cls: 'badge-success', icon: <CheckCircle size={10} />, label: 'Completed'           },
    completed_with_errors:  { cls: 'badge-warning', icon: <AlertCircle size={10} />, label: 'Completed w/ Errors' },
    failed:                 { cls: 'badge-error',   icon: <AlertCircle size={10} />, label: 'Failed'              },
    running:                { cls: 'badge-info',    icon: <Clock size={10} />,       label: 'Running'             },
    pending:                { cls: 'badge-neutral', icon: <Clock size={10} />,       label: 'Pending'             },
  }
  const { cls, icon, label } = map[status] || map.pending
  return <span className={`badge ${cls}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>{icon}{label}</span>
}

const SelectField = ({ label, value, onChange, options, placeholder, required, disabled }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    <label style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)' }}>
      {label}{required && <span style={{ color: 'var(--color-error)', marginLeft: 2 }}>*</span>}
    </label>
    <select
      className="form-input"
      value={value}
      onChange={e => onChange(e.target.value)}
      disabled={disabled}
      style={{ fontSize: 12.5 }}
    >
      <option value="">{placeholder || `-- Select ${label} --`}</option>
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  </div>
)

export default function RAGPipelines() {
  const { isAdmin } = useAuth()
  if (!isAdmin) return <Navigate to="/chats" replace />

  const [source, setSource]               = useState('local')
  const [files, setFiles]                 = useState([])
  const [dragging, setDragging]           = useState(false)
  const [pipelineName, setPipelineName]   = useState('')
  const [gdriveUrl, setGdriveUrl]         = useState('')
  const [spSiteUrl, setSpSiteUrl]         = useState('')
  const [spFolder, setSpFolder]           = useState('')
  const [spUser, setSpUser]               = useState('')
  const [spPass, setSpPass]               = useState('')
  const fileRef = useRef()

  // LOV state
  const [domains,        setDomains]        = useState([])
  const [subDomains,     setSubDomains]     = useState([])
  const [categories,     setCategories]     = useState([])
  const [subCategories,  setSubCategories]  = useState([])

  const [selDomain,      setSelDomain]      = useState('')
  const [selSubDomain,   setSelSubDomain]   = useState('')
  const [selCategory,    setSelCategory]    = useState('')
  const [selSubCategory, setSelSubCategory] = useState('')

  const [subDomainLoading,  setSubDomainLoading]  = useState(false)
  const [subCatsLoading,    setSubCatsLoading]     = useState(false)
  const [description,       setDescription]        = useState('')

  // Run history + polling
  const [runs,           setRuns]           = useState([])
  const [runsLoading,    setRunsLoading]    = useState(false)
  const [submitting,     setSubmitting]     = useState(false)
  const [pollingRunId,   setPollingRunId]   = useState(null)
  const pollRef = useRef(null)

  // On mount: fetch domains, categories, sub-categories, run history
  useEffect(() => {
    getDomains().then(ds => setDomains(ds.map(d => ({ value: d.DomainID, label: d.DomainName })))).catch(() => {})
    getRagCategories().then(cs => setCategories(cs.map(c => ({ value: c.category_id, label: c.category_name })))).catch(() => {})
    setSubCatsLoading(true)
    getRagSubCategories().then(scs => setSubCategories(scs.map(sc => ({ value: sc.sub_category_id, label: sc.sub_category_name })))).catch(() => {}).finally(() => setSubCatsLoading(false))
    fetchRuns()
  }, [])

  const fetchRuns = useCallback(() => {
    setRunsLoading(true)
    getRagRuns().then(r => setRuns(r)).catch(() => {}).finally(() => setRunsLoading(false))
  }, [])

  // Poll a specific run until terminal status
  const startPolling = useCallback((runId) => {
    setPollingRunId(runId)
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const run = await getRagRun(runId)
        setRuns(prev => prev.map(r => r.run_id === runId ? run : r))
        const terminal = ['completed', 'completed_with_errors', 'failed']
        if (terminal.includes(run.status)) {
          clearInterval(pollRef.current)
          pollRef.current = null
          setPollingRunId(null)
          const msg = run.status === 'completed'
            ? `✅ Run complete — ${run.processed_files} file(s) embedded`
            : run.status === 'completed_with_errors'
              ? `⚠️ Completed with errors — ${run.processed_files} ok, ${run.failed_files} failed`
              : `❌ Run failed`
          toast(msg, { duration: 5000 })
        }
      } catch { /* network blip — keep polling */ }
    }, 3000)
  }, [])

  // Cleanup poll on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  // Domain → SubDomain cascade
  useEffect(() => {
    setSelSubDomain('')
    setSubDomains([])
    if (!selDomain) return
    setSubDomainLoading(true)
    getSubDomains()
      .then(sds => {
        const filtered = sds.filter(sd => String(sd.DomainID) === String(selDomain))
        setSubDomains(filtered.map(sd => ({ value: sd.SubDomainID, label: sd.SubDomainName })))
      })
      .catch(() => {})
      .finally(() => setSubDomainLoading(false))
  }, [selDomain])


  const addFiles = newFiles => {
    const arr = Array.from(newFiles)
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name))
      return [...prev, ...arr.filter(f => !names.has(f.name))]
    })
  }

  const onDrop = e => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files) }
  const removeFile = name => setFiles(f => f.filter(x => x.name !== name))
  const formatSize = b => b < 1048576 ? (b / 1024).toFixed(1) + ' KB' : (b / 1048576).toFixed(1) + ' MB'

  const handleLoad = async () => {
    if (!pipelineName.trim())                     { toast.error('Enter a pipeline name'); return }
    if (!selDomain)                               { toast.error('Select a Domain'); return }
    if (!selSubDomain)                            { toast.error('Select a Sub-Domain'); return }
    if (!selCategory)                             { toast.error('Select a Category'); return }
    if (source === 'local' && files.length === 0) { toast.error('Add at least one file'); return }
    if (source === 'gdrive' && !gdriveUrl.trim()) { toast.error('Enter Google Drive folder URL'); return }
    if (source === 'sharepoint' && (!spSiteUrl.trim() || !spFolder.trim())) {
      toast.error('Enter SharePoint site URL and folder path'); return
    }

    // Build multipart FormData — actual file bytes included
    const fd = new FormData()
    fd.append('run_name',      pipelineName.trim())
    fd.append('source_type',   source)
    fd.append('domain_id',     selDomain)
    fd.append('sub_domain_id', selSubDomain)
    fd.append('category_id',   selCategory)
    if (selSubCategory) fd.append('sub_category_id', selSubCategory)
    if (description.trim()) fd.append('description', description.trim())

    if (source === 'local') {
      files.forEach(f => fd.append('files', f, f.name))
    }

    setSubmitting(true)
    try {
      const run = await createRagRun(fd)
      toast.success(`Run queued — ${files.length} file(s) queued for embedding`)
      // Add optimistically to history, then start polling
      setRuns(prev => [run, ...prev])
      startPolling(run.run_id)
      // Reset form
      setPipelineName(''); setDescription('')
      setFiles([])
      setGdriveUrl('')
      setSpSiteUrl(''); setSpFolder(''); setSpUser(''); setSpPass('')
      setSelDomain(''); setSelSubDomain(''); setSelCategory(''); setSelSubCategory('')
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to queue pipeline run')
    } finally {
      setSubmitting(false)
    }
  }

  const fmtDate = v => {
    if (!v) return '—'
    try { return new Date(v).toLocaleString() } catch { return v }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '16px 20px', gap: 12, overflow: 'hidden' }}>

      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div>
          <h1 style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.3px' }}>Manage RAG Pipelines</h1>
          <p style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 2 }}>Load documents into the vector database for AI-powered retrieval</p>
        </div>
        <span className="badge badge-info">Admin Only</span>
      </div>

      {/* ── Top: Upload card ── */}
      <div className="card" style={{ flexShrink: 0 }}>
        <div className="card-header" style={{ padding: '10px 16px' }}>
          <span className="card-title">Upload Files</span>
        </div>
        <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>

          {/* Source tabs */}
          <div style={{ display: 'flex', gap: 6 }}>
            {SOURCES.map(s => {
              const Icon = s.icon
              const active = source === s.id
              return (
                <button key={s.id} onClick={() => setSource(s.id)} style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  padding: '4px 12px', borderRadius: 'var(--radius-pill)',
                  fontSize: 12, fontWeight: 600,
                  border: `1px solid ${active ? 'var(--brand-primary)' : 'var(--border-default)'}`,
                  background: active ? 'var(--brand-primary-subtle)' : 'var(--bg-surface)',
                  color: active ? 'var(--brand-primary)' : 'var(--text-secondary)',
                  cursor: 'pointer', transition: 'all var(--transition-fast)',
                }}>
                  <Icon size={12} />{s.label}
                </button>
              )
            })}
          </div>

          {/* Pipeline Name + Description */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)' }}>
                Pipeline Name <span style={{ color: 'var(--color-error)' }}>*</span>
              </label>
              <input
                className="form-input"
                placeholder="e.g. Sales Docs Q2 2026"
                value={pipelineName}
                onChange={e => setPipelineName(e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)' }}>Description</label>
              <input
                className="form-input"
                placeholder="Optional — describe this batch"
                value={description}
                onChange={e => setDescription(e.target.value)}
              />
            </div>
          </div>

          {/* LOV row: Domain + SubDomain + Category + SubCategory */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 10 }}>
            <SelectField
              label="Domain"
              value={selDomain}
              onChange={v => setSelDomain(v)}
              options={domains}
              placeholder="-- Select Domain --"
              required
            />
            <SelectField
              label="Sub-Domain"
              value={selSubDomain}
              onChange={v => setSelSubDomain(v)}
              options={subDomains}
              placeholder={selDomain ? (subDomainLoading ? 'Loading…' : '-- Select Sub-Domain --') : '-- Select Domain first --'}
              required
              disabled={!selDomain || subDomainLoading}
            />
            <SelectField
              label="Category"
              value={selCategory}
              onChange={v => setSelCategory(v)}
              options={categories}
              placeholder="-- Select Category --"
              required
            />
            <SelectField
              label="Sub-Category"
              value={selSubCategory}
              onChange={v => setSelSubCategory(v)}
              options={subCategories}
              placeholder={subCatsLoading ? 'Loading…' : '-- Select Sub-Category --'}
              disabled={subCatsLoading}
            />
          </div>

          {/* LOCAL */}
          {source === 'local' && (
            <>
              <div
                className={`rag-dropzone ${dragging ? 'rag-dropzone--drag' : ''}`}
                style={{ padding: '18px 16px' }}
                onDragOver={e => { e.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => fileRef.current.click()}
              >
                <Upload size={22} style={{ opacity: 0.4, marginBottom: 6 }} />
                <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)' }}>Drag & drop files, or click to browse</div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>Multiple files supported — all formats accepted</div>
                <input ref={fileRef} type="file" multiple style={{ display: 'none' }} onChange={e => addFiles(e.target.files)} />
              </div>
              {files.length > 0 && (
                <div className="rag-file-list" style={{ maxHeight: 90 }}>
                  {files.map(f => (
                    <div key={f.name} className="rag-file-item">
                      <FileText size={12} style={{ flexShrink: 0, color: 'var(--brand-primary)' }} />
                      <span style={{ flex: 1, fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-tertiary)', flexShrink: 0 }}>{formatSize(f.size)}</span>
                      <button className="btn btn-ghost btn-icon btn-sm" onClick={() => removeFile(f.name)} style={{ width: 18, height: 18 }}><X size={9} /></button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* GOOGLE DRIVE */}
          {source === 'gdrive' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <input className="form-input" placeholder="https://drive.google.com/drive/folders/..." value={gdriveUrl} onChange={e => setGdriveUrl(e.target.value)} />
              <div className="rag-info-box" style={{ padding: '8px 10px' }}>
                <AlertCircle size={12} style={{ flexShrink: 0, color: 'var(--color-info)' }} />
                <span style={{ fontSize: 11.5 }}>Google OAuth will be wired to the Load button. Service account needs read access.</span>
              </div>
              <button className="btn btn-secondary btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => toast('Google Drive OAuth — backend integration pending', { icon: '🔌' })}>
                Connect Google Drive
              </button>
            </div>
          )}

          {/* SHAREPOINT */}
          {source === 'sharepoint' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div className="grid-2">
                <input className="form-input" placeholder="https://company.sharepoint.com/sites/..." value={spSiteUrl} onChange={e => setSpSiteUrl(e.target.value)} />
                <input className="form-input" placeholder="/Shared Documents/Reports" value={spFolder} onChange={e => setSpFolder(e.target.value)} />
              </div>
              <div className="grid-2">
                <input className="form-input" placeholder="Username / Client ID" value={spUser} onChange={e => setSpUser(e.target.value)} autoComplete="off" />
                <input className="form-input" type="password" placeholder="Password / Client Secret" value={spPass} onChange={e => setSpPass(e.target.value)} autoComplete="new-password" />
              </div>
            </div>
          )}

          {/* Load button */}
          <button
            className="btn btn-primary"
            style={{ alignSelf: 'stretch', justifyContent: 'center', gap: 8, height: 36 }}
            onClick={handleLoad}
            disabled={submitting}
          >
            <Play size={13} />{submitting ? 'Queuing…' : 'Load into Vector Database'}
          </button>
        </div>
      </div>

      {/* ── Bottom: Run history ── */}
      <div className="card" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div className="card-header" style={{ padding: '10px 16px', flexShrink: 0 }}>
          <span className="card-title">Pipeline Run History</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {pollingRunId && (
              <span className="badge badge-info" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <Clock size={10} /> Processing…
              </span>
            )}
            <span className="badge badge-neutral">{runs.length} runs</span>
            <button className="btn btn-ghost btn-icon btn-sm" onClick={fetchRuns} disabled={runsLoading} title="Refresh">
              <RefreshCw size={13} style={{ animation: (runsLoading || pollingRunId) ? 'spin 1s linear infinite' : 'none' }} />
            </button>
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'auto' }}>
          {runsLoading && runs.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>Loading run history…</div>
          ) : runs.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>No pipeline runs yet. Queue your first run above.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Source</th>
                  <th>Found</th>
                  <th>Processed</th>
                  <th>Failed</th>
                  <th>Status</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(r => (
                  <tr key={r.run_id}>
                    <td style={{ fontWeight: 600 }}>{r.run_name || '—'}</td>
                    <td>
                      <span className="tag">
                        {r.source_type === 'local'      && <Upload size={10} />}
                        {r.source_type === 'gdrive'     && <HardDrive size={10} />}
                        {r.source_type === 'sharepoint' && <Globe size={10} />}
                        {r.source_type === 'local' ? 'Local' : r.source_type === 'gdrive' ? 'G-Drive' : r.source_type === 'sharepoint' ? 'SharePoint' : r.source_type}
                      </span>
                    </td>
                    <td>{r.total_files_found ?? '—'}</td>
                    <td>{r.processed_files ?? '—'}</td>
                    <td>{r.failed_files ?? '—'}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td style={{ color: 'var(--text-tertiary)', fontSize: 12, whiteSpace: 'nowrap' }}>{fmtDate(r.started_at || r.created_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

    </div>
  )
}
