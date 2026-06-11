import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import {
  Play, Download, Eye, EyeOff, RefreshCw,
  Database, Target, Shield, CheckCircle, AlertTriangle,
  ArrowRight, Loader2, Cpu, Upload
} from 'lucide-react'
import toast from 'react-hot-toast'
import { dataflowRun, dataflowPlan, dataflowDiscover, dataflowGetRun, dataflowUploadCsv } from '../api/client'

// ── Status Badge ─────────────────────────────────────────────────
function StatusBadge({ status }) {
  const colors = {
    completed: { bg: '#e8f5e9', fg: '#1b5e20' },
    running:   { bg: '#e3f2fd', fg: '#0d47a1' },
    failed:    { bg: '#fce4ec', fg: '#b71c1c' },
    planned:   { bg: '#fff3e0', fg: '#e65100' },
    approved:  { bg: '#f3e5f5', fg: '#4a148c' },
    skipped:   { bg: '#f5f5f5', fg: '#616161' },
    pending:   { bg: '#f5f5f5', fg: '#9e9e9e' },
  }
  const c = colors[status] || colors.pending
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 10px', borderRadius: 12, fontSize: 11.5,
      fontWeight: 600, background: c.bg, color: c.fg,
    }}>
      {status === 'running' && <Loader2 size={11} className="spinner" />}
      {status}
    </span>
  )
}

// ── Step Card ────────────────────────────────────────────────────
function StepCard({ step }) {
  const agentIcons = {
    discovery:      Database,
    ingestion:      Download,
    pii_mask:       Shield,
    transformation: RefreshCw,
    quality:        CheckCircle,
    publish:        Target,
  }
  const Icon = agentIcons[step.agent] || Cpu
  const failed = step.status === 'failed'
  const completed = step.status === 'completed'

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 12,
      padding: '12px 16px', borderRadius: 8,
      background: completed ? 'var(--bg-elevated)' : failed ? '#fef2f2' : 'var(--bg-elevated)',
      border: `1px solid ${failed ? '#fecaca' : completed ? '#bbf7d0' : 'var(--border-default)'}`,
      opacity: step.status === 'pending' ? 0.5 : 1,
    }}>
      <Icon size={16} style={{ marginTop: 2, color: failed ? '#dc2626' : completed ? '#16a34a' : 'var(--text-secondary)' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <strong style={{ fontSize: 13, color: 'var(--text-primary)' }}>
            {step.agent.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
          </strong>
          <StatusBadge status={step.status} />
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{step.description}</div>
        {step.error && (
          <div style={{ marginTop: 6, fontSize: 11.5, color: '#dc2626', background: '#fef2f2', padding: '6px 10px', borderRadius: 6 }}>
            {step.error}
          </div>
        )}
        {step.result && (
          <details style={{ marginTop: 8 }}>
            <summary style={{ fontSize: 11.5, cursor: 'pointer', color: 'var(--text-tertiary)' }}>
              View result
            </summary>
            <pre style={{
              marginTop: 6, padding: 8, borderRadius: 6,
              background: '#f8f9fa', fontSize: 11, lineHeight: 1.5,
              maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
            }}>
              {JSON.stringify(step.result, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}

// ── Inline config form ────────────────────────────────────────────
function ConfigForm({ label, icon: Icon, value, onChange }) {
  const [show, setShow] = useState(false)

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon size={14} style={{ color: 'var(--text-secondary)' }} />
        <label style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)' }}>{label}</label>
        <button
          className="btn btn-ghost btn-icon btn-sm"
          onClick={() => setShow(s => !s)}
          title={show ? 'Hide' : 'Show'}
          style={{ marginLeft: 'auto' }}
        >
          {show ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
      </div>
      {show && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <input
            className="input"
            placeholder="Database type (postgresql, mysql, duckdb, etc.)"
            value={value.type || ''}
            onChange={e => onChange({ ...value, type: e.target.value })}
            style={{ fontSize: 12.5, padding: '6px 10px' }}
          />
          <input
            className="input"
            placeholder="Connection string (postgresql://user:pass@host:5432/db)"
            value={value.connection_string || ''}
            onChange={e => onChange({ ...value, connection_string: e.target.value })}
            style={{ fontSize: 12.5, padding: '6px 10px', fontFamily: 'monospace' }}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="input"
              placeholder="Schema (optional)"
              value={value.schema || ''}
              onChange={e => onChange({ ...value, schema: e.target.value })}
              style={{ fontSize: 12.5, padding: '6px 10px', flex: 1 }}
            />
            <input
              className="input"
              placeholder="Tables (comma-separated, optional)"
              value={(value.tables || []).join(', ')}
              onChange={e => onChange({ ...value, tables: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
              style={{ fontSize: 12.5, padding: '6px 10px', flex: 1 }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Pipeline Run View ────────────────────────────────────────────
function PipelineRunView({ run }) {
  if (!run) return null
  const steps = run.plan?.steps || []

  return (
    <div>
      {/* Summary header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 16,
        padding: '12px 16px', borderRadius: 8,
        background: 'var(--bg-elevated)', marginBottom: 16,
        border: '1px solid var(--border-default)',
      }}>
        <strong style={{ fontSize: 13 }}>Run: {run.request_id?.slice(0, 16)}</strong>
        <StatusBadge status={run.status} />
        {run.final_output && (
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', marginLeft: 'auto' }}>
            {run.final_output.final_table} — {run.final_output.row_count?.toLocaleString()} rows
          </span>
        )}
        {run.error && (
          <span style={{ fontSize: 12, color: '#dc2626', marginLeft: 'auto' }}>{run.error}</span>
        )}
      </div>

      {/* Steps */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {steps.map((step, i) => (
          <div key={step.step_id}>
            {i > 0 && <ArrowRight size={14} style={{ margin: '4px auto', color: 'var(--text-tertiary)', display: 'block' }} />}
            <StepCard step={step} />
          </div>
        ))}
      </div>

      {/* Final output details */}
      {run.final_output && (
        <div style={{
          marginTop: 16, padding: 12, borderRadius: 8,
          background: '#f0fdf4', border: '1px solid #bbf7d0',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <CheckCircle size={16} style={{ color: '#16a34a' }} />
            <strong style={{ fontSize: 13, color: '#166534' }}>Pipeline Complete</strong>
          </div>
          <div style={{ fontSize: 12, color: '#166534', lineHeight: 1.6 }}>
            <div>Final table: <code>{run.final_output.final_table}</code></div>
            <div>Schema: <code>{run.final_output.schema}</code></div>
            <div>Row count: <strong>{run.final_output.row_count?.toLocaleString()}</strong></div>
            {run.final_output.column_lineage?.length > 0 && (
              <div style={{ marginTop: 4 }}>
                Column lineage: {run.final_output.column_lineage.length} mappings
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────
export default function DataPipeline() {
  const { isAdmin } = useAuth()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('builder')

  // Config form state
  const [sourceConfig, setSourceConfig] = useState({ type: '', connection_string: '', schema: '', tables: [] })
  const [targetConfig, setTargetConfig] = useState({ type: '', connection_string: '', schema: '', tables: [] })
  const [prompt, setPrompt] = useState('')
  const [options, setOptions] = useState({
    pii_mask: false,
    materialization: 'table',
    quality_rules: '',
    dbt_model: '',
    dry_run: false,
  })

  // Run state
  const [running, setRunning] = useState(false)
  const [currentRun, setCurrentRun] = useState(null)
  const [plan, setPlan] = useState(null)
  const [discoveryResult, setDiscoveryResult] = useState(null)

  // History
  const [runHistory, setRunHistory] = useState([])

  const handleDiscover = async () => {
    if (!sourceConfig.connection_string) {
      toast.error('Enter a source connection string first')
      return
    }
    toast('Discovering source schema...', { icon: '🔍' })
    try {
      const result = await dataflowDiscover({ connection: sourceConfig })
      setDiscoveryResult(result)
      const tableCount = result.tables?.length || 0
      const piiCount = result.tables?.reduce((acc, t) =>
        acc + t.columns.filter(c => c.pii_category).length, 0
      ) || 0
      toast.success(`Discovered ${tableCount} table(s), ${piiCount} PII column(s) detected`)
    } catch (e) {
      toast.error(`Discovery failed: ${e.message}`)
    }
  }

  const handlePlan = async () => {
    if (!prompt.trim()) {
      toast.error('Describe the data engineering task')
      return
    }
    toast('Generating plan...', { icon: '🧠' })
    try {
      const result = await dataflowPlan({
        prompt,
        source_config: sourceConfig,
        target_config: targetConfig,
        options: {
          pii_mask: options.pii_mask,
          quality_rules: options.quality_rules ? options.quality_rules.split(',').map(s => s.trim()).filter(Boolean) : [],
          dbt_model: options.dbt_model || undefined,
          materialization: options.materialization,
        },
        discovery_result: discoveryResult,
      })
      setPlan(result.plan)
      toast.success(`Plan generated: ${result.plan?.steps?.length || 0} steps`)
    } catch (e) {
      toast.error(`Planning failed: ${e.message}`)
    }
  }

  const handleRun = async () => {
    if (!prompt.trim()) {
      toast.error('Describe the data engineering task')
      return
    }
    setRunning(true)
    setCurrentRun(null)
    setPlan(null)
    try {
      const result = await dataflowRun({
        prompt,
        source_config: sourceConfig,
        target_config: targetConfig,
        options: {
          pii_mask: options.pii_mask,
          quality_rules: options.quality_rules ? options.quality_rules.split(',').map(s => s.trim()).filter(Boolean) : [],
          dbt_model: options.dbt_model || undefined,
          materialization: options.materialization,
          dry_run: options.dry_run,
        },
      })
      setCurrentRun(result)
      setRunHistory(prev => [result, ...prev].slice(0, 20))
      const status = result.status
      if (status === 'completed') {
        toast.success('Pipeline completed successfully!')
      } else if (status === 'planned' && options.dry_run) {
        toast('Dry-run plan generated', { icon: '📋' })
      } else {
        toast.error(`Pipeline ${status}: ${result.error || 'check run details'}`)
      }
    } catch (e) {
      toast.error(`Pipeline failed: ${e.message}`)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 1000, margin: '0 auto' }}>
      <div className="page-header" style={{ marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Cpu size={20} style={{ color: 'var(--brand-orange)' }} />
            Data Pipeline
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>
            Agentic data engineering — discover, ingest, transform, mask PII, validate quality, and publish
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--border-default)' }}>
        {['builder', 'history'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '8px 18px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              border: 'none', background: 'none',
              borderBottom: activeTab === tab ? '2px solid var(--brand-orange)' : '2px solid transparent',
              color: activeTab === tab ? 'var(--brand-orange)' : 'var(--text-secondary)',
            }}
          >
            {tab === 'builder' ? 'Pipeline Builder' : 'Run History'}
          </button>
        ))}
      </div>

      {activeTab === 'builder' ? (
        <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: 20, alignItems: 'start' }}>
          {/* Left: Config */}
          <div className="card" style={{ padding: 16 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, margin: '0 0 12px 0' }}>Configuration</h3>

            <ConfigForm label="Source" icon={Database} value={sourceConfig} onChange={setSourceConfig} />

            {/* CSV Upload */}
            <div style={{
              marginBottom: 16, padding: 12, borderRadius: 8,
              border: '1px dashed var(--border-default)',
              background: 'var(--bg-elevated)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Upload size={14} style={{ color: 'var(--text-secondary)' }} />
                <label style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', cursor: 'pointer' }}>
                  Upload CSV as Source
                </label>
              </div>
              <input
                type="file"
                accept=".csv"
                onChange={async (e) => {
                  const file = e.target.files?.[0]
                  if (!file) return
                  toast('Uploading CSV...', { icon: '📤' })
                  try {
                    const result = await dataflowUploadCsv(file)
                    setSourceConfig({
                      type: 'duckdb',
                      connection_string: result.source_config.connection_string,
                      schema: '',
                      tables: result.source_config.tables || [],
                    })
                    toast.success(`Uploaded ${result.filename} (${(result.size_bytes / 1024).toFixed(1)} KB)`)
                  } catch (err) {
                    toast.error(`Upload failed: ${err.message}`)
                  }
                  e.target.value = ''
                }}
                style={{ fontSize: 12, width: '100%' }}
              />
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                CSV is read via DuckDB — no separate database needed
              </div>
            </div>

            <ConfigForm label="Target" icon={Target} value={targetConfig} onChange={setTargetConfig} />

            {/* Options */}
            <div style={{ marginTop: 8 }}>
              <label style={{ fontSize: 12.5, fontWeight: 600, display: 'block', marginBottom: 8, color: 'var(--text-primary)' }}>Options</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input type="checkbox" checked={options.pii_mask} onChange={e => setOptions({ ...options, pii_mask: e.target.checked })} />
                  Auto-detect and mask PII
                </label>
                <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input type="checkbox" checked={options.dry_run} onChange={e => setOptions({ ...options, dry_run: e.target.checked })} />
                  Dry run (plan only)
                </label>
                <input
                  className="input"
                  placeholder="Materialization (table / view / incremental)"
                  value={options.materialization}
                  onChange={e => setOptions({ ...options, materialization: e.target.value })}
                  style={{ fontSize: 12, padding: '6px 10px' }}
                />
                <input
                  className="input"
                  placeholder="Quality rules: no_nulls:id, unique:id, not_empty"
                  value={options.quality_rules}
                  onChange={e => setOptions({ ...options, quality_rules: e.target.value })}
                  style={{ fontSize: 12, padding: '6px 10px' }}
                />
                <input
                  className="input"
                  placeholder="dbt model (optional)"
                  value={options.dbt_model}
                  onChange={e => setOptions({ ...options, dbt_model: e.target.value })}
                  style={{ fontSize: 12, padding: '6px 10px' }}
                />
              </div>
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-secondary" style={{ fontSize: 12.5, padding: '6px 14px' }} onClick={handleDiscover}>
                <Eye size={13} /> Discover
              </button>
              <button className="btn btn-secondary" style={{ fontSize: 12.5, padding: '6px 14px' }} onClick={handlePlan}>
                <RefreshCw size={13} /> Plan
              </button>
              <button className="btn btn-primary" style={{ fontSize: 12.5, padding: '6px 14px', marginLeft: 'auto' }} onClick={handleRun} disabled={running || !prompt.trim()}>
                {running ? <Loader2 size={13} className="spinner" /> : <Play size={13} />}
                {running ? 'Running...' : 'Run Pipeline'}
              </button>
            </div>
          </div>

          {/* Right: Prompt + Results */}
          <div>
            {/* Prompt */}
            <div className="card" style={{ padding: 16, marginBottom: 16 }}>
              <h3 style={{ fontSize: 13, fontWeight: 600, margin: '0 0 8px 0' }}>Task Description</h3>
              <textarea
                className="input"
                placeholder='Describe the data engineering task, e.g. "Ingest the orders table from the source, mask PII on email and phone columns, run the fct_orders dbt model, check quality no nulls on order_id, and publish to the analytics schema"'
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                rows={4}
                style={{ width: '100%', resize: 'vertical', fontSize: 13 }}
              />
            </div>

            {/* Discovery result */}
            {discoveryResult && (
              <div className="card" style={{ padding: 16, marginBottom: 16 }}>
                <h3 style={{ fontSize: 13, fontWeight: 600, margin: '0 0 8px 0', color: '#0d47a1' }}>
                  <Database size={14} style={{ marginRight: 6 }} />
                  Discovery
                </h3>
                {discoveryResult.tables?.map(t => (
                  <div key={t.table_name} style={{ marginBottom: 8 }}>
                    <strong style={{ fontSize: 12 }}>{t.table_name}</strong>
                    {t.row_count != null && (
                      <span style={{ fontSize: 11, color: 'var(--text-secondary)', marginLeft: 8 }}>
                        {t.row_count.toLocaleString()} rows
                      </span>
                    )}
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                      {t.columns.map(c => (
                        <span key={c.name} style={{ marginRight: 8 }}>
                          {c.name} ({c.data_type})
                          {c.pii_category && (
                            <span style={{ color: '#dc2626' }}> ⚠{c.pii_category}</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
                {discoveryResult.warnings?.map((w, i) => (
                  <div key={i} style={{ fontSize: 11, color: '#e65100', marginTop: 4 }}>{w}</div>
                ))}
              </div>
            )}

            {/* Plan */}
            {plan && !currentRun && (
              <div className="card" style={{ padding: 16, marginBottom: 16 }}>
                <h3 style={{ fontSize: 13, fontWeight: 600, margin: '0 0 8px 0', color: '#e65100' }}>
                  <RefreshCw size={14} style={{ marginRight: 6 }} />
                  Generated Plan ({plan.steps?.length || 0} steps)
                </h3>
                {plan.steps?.map(step => (
                  <div key={step.step_id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: 12 }}>
                    <StatusBadge status={step.status} />
                    <strong style={{ textTransform: 'capitalize' }}>{step.agent.replace(/_/g, ' ')}</strong>
                    <span style={{ color: 'var(--text-secondary)' }}>— {step.description}</span>
                  </div>
                ))}
                {plan.rationale && (
                  <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
                    {plan.rationale}
                  </div>
                )}
              </div>
            )}

            {/* Run results */}
            {currentRun && <PipelineRunView run={currentRun} />}
          </div>
        </div>
      ) : (
        /* Run History */
        <div>
          {runHistory.length === 0 ? (
            <div className="empty-state">No pipeline runs yet. Create one in the Builder tab.</div>
          ) : (
            runHistory.map(run => (
              <div key={run.request_id} className="card" style={{ padding: 16, marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                  <strong style={{ fontSize: 12 }}>Run {run.request_id?.slice(0, 16)}</strong>
                  <StatusBadge status={run.status} />
                  {run.final_output && (
                    <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginLeft: 'auto' }}>
                      {run.final_output.final_table} ({run.final_output.row_count?.toLocaleString()} rows)
                    </span>
                  )}
                </div>
                {run.plan?.steps && (
                  <div style={{ fontSize: 11.5, color: 'var(--text-tertiary)', display: 'flex', gap: 12 }}>
                    {run.plan.steps.map(s => (
                      <span key={s.step_id}>
                        {s.agent.replace(/_/g, ' ')}: <StatusBadge status={s.status} />
                      </span>
                    ))}
                  </div>
                )}
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: 11.5, marginTop: 8, padding: '4px 10px' }}
                  onClick={() => setCurrentRun(run)}
                >
                  View details
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
