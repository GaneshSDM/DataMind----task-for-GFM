import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, Activity, BarChart2, Settings } from 'lucide-react'
import { getAgents, getAgentStatuses, updateAgent } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'

// ── Static tool definitions ───────────────────────────────────────────────────
const AGENT_TOOLS = {
  heimdall: [
    { label: 'all-MiniLM-L6-v2 Embedder',      category: 'Model'     },
    { label: 'tracopp.prompt_policies',          category: 'Database'  },
    { label: 'LangGraph StateGraph',             category: 'Framework' },
  ],
  aria: [
    { label: 'Groq LLM API',                              category: 'LLM'      },
    { label: 'tracopp.rag_document_chunks (pgvector)',     category: 'Database' },
    { label: 'BAAI/bge-large-en-v1.5 Embedder',           category: 'Model'    },
    { label: 'schema_reference.json',                      category: 'Config'   },
  ],
  sage: [
    { label: 'Groq LLM API',              category: 'LLM'    },
    { label: 'schema_reference.json',      category: 'Config' },
    { label: 'examples.json (few-shot)',   category: 'Config' },
    { label: 'correction_examples.json',   category: 'Config' },
  ],
  valkyrie: [
    { label: 'Groq LLM API',              category: 'LLM'  },
    { label: 'SQL Syntax Checker',         category: 'Tool' },
    { label: 'RLS / CLS Policy Enforcer', category: 'Tool' },
  ],
  spyder: [
    { label: 'Groq LLM API',                          category: 'LLM'      },
    { label: 'tracopp.rag_document_chunks (pgvector)', category: 'Database' },
    { label: 'tracopp.rag_files',                      category: 'Database' },
    { label: 'SQL Executor',                           category: 'Tool'     },
  ],
  raven: [
    { label: 'BAAI/bge-large-en-v1.5 Embedder',           category: 'Model'    },
    { label: 'tracopp.rag_document_chunks (pgvector)',     category: 'Database' },
    { label: 'tracopp.rag_files (auth check)',             category: 'Database' },
  ],
}

const CATEGORY_COLOURS = {
  LLM:       { bg: '#eff6ff', color: '#3b82f6', border: '#3b82f6' },
  Model:     { bg: '#f0fdf4', color: '#16a34a', border: '#16a34a' },
  Database:  { bg: '#fff7ed', color: '#ea580c', border: '#ea580c' },
  Config:    { bg: '#faf5ff', color: '#9333ea', border: '#9333ea' },
  Tool:      { bg: '#fefce8', color: '#ca8a04', border: '#ca8a04' },
  Framework: { bg: '#f1f5f9', color: '#475569', border: '#475569' },
}

const AGENT_TABS = ['Persona', 'LLM Config', 'Tools', 'Behavior']
const SECTIONS   = [
  { key: 'Agents',        label: 'Agents',        icon: Settings  },
  { key: 'Observability', label: 'Observability', icon: Activity  },
  { key: 'Evaluation',    label: 'Evaluation',    icon: BarChart2 },
]

// ── Helpers ───────────────────────────────────────────────────────────────────
function deepClone(obj) { return JSON.parse(JSON.stringify(obj ?? {})) }

// ── Shared sub-components ─────────────────────────────────────────────────────

function StatusDot({ status }) {
  const colour = status === 'online' ? '#16a34a' : status === 'degraded' ? '#f59e0b' : '#9ca3af'
  return <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: colour, flexShrink: 0 }} title={status ?? 'unknown'} />
}

function TabBar({ active, onChange }) {
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid var(--border-default)', padding: '0 16px', gap: 2 }}>
      {AGENT_TABS.map(t => (
        <button key={t} onClick={() => onChange(t)} style={{
          padding: '8px 14px', fontSize: 12.5,
          fontWeight: active === t ? 700 : 500,
          color: active === t ? 'var(--brand-orange)' : 'var(--text-secondary)',
          background: 'none', border: 'none', cursor: 'pointer',
          borderBottom: active === t ? '2px solid var(--brand-orange)' : '2px solid transparent',
          marginBottom: -1,
        }}>{t}</button>
      ))}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 5 }}>{label}</div>
      {children}
    </div>
  )
}

const inputStyle = {
  width: '100%', padding: '7px 10px', fontSize: 13, fontFamily: 'inherit',
  border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md, 6px)',
  background: 'var(--bg-surface)', color: 'var(--text-primary)',
  boxSizing: 'border-box', outline: 'none',
}

// ── Metric tile ───────────────────────────────────────────────────────────────
function MetricTile({ label, value, sub, accent }) {
  return (
    <div style={{
      flex: '1 1 140px', minWidth: 130,
      padding: '14px 16px',
      border: '1px solid var(--border-default)',
      borderRadius: 8,
      background: 'var(--bg-surface)',
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: accent || 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

// ── Coming soon placeholder ───────────────────────────────────────────────────
function ComingSoon({ label }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      height: 120, border: '1px dashed var(--border-default)', borderRadius: 8,
      color: 'var(--text-tertiary)', gap: 6,
    }}>
      <div style={{ fontSize: 18 }}>📊</div>
      <div style={{ fontSize: 12, fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 11 }}>Coming soon — backend integration pending</div>
    </div>
  )
}

// ── Section label ─────────────────────────────────────────────────────────────
function SectionLabel({ children }) {
  return <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10, marginTop: 4 }}>{children}</div>
}

// ── Agent tab content ─────────────────────────────────────────────────────────

function PersonaTab({ config, onChange }) {
  const persona = config.persona ?? {}
  return (
    <div style={{ padding: 20 }}>
      <Field label="Role Name">
        <input style={inputStyle} value={persona.role ?? ''} onChange={e => onChange({ ...config, persona: { ...persona, role: e.target.value } })} placeholder="e.g. Domain Synthesizer Agent" />
      </Field>
      <Field label="System Instruction">
        <textarea style={{ ...inputStyle, minHeight: 180, resize: 'vertical', lineHeight: 1.6 }} value={persona.instruction ?? ''} onChange={e => onChange({ ...config, persona: { ...persona, instruction: e.target.value } })} placeholder="Describe how the agent should behave…" />
      </Field>
    </div>
  )
}

function LLMTab({ config, onChange }) {
  const llm = config.llm
  if (!llm) return <div style={{ padding: 20, color: 'var(--text-tertiary)', fontSize: 13 }}>This agent does not use an LLM — it runs on a local embedding model.</div>
  return (
    <div style={{ padding: 20 }}>
      <Field label="Model">
        <input style={inputStyle} value={llm.model ?? ''} onChange={e => onChange({ ...config, llm: { ...llm, model: e.target.value } })} placeholder="e.g. llama-3.3-70b-versatile" />
      </Field>
      <Field label={`Temperature — ${llm.temperature ?? 0.2}`}>
        <input type="range" min="0" max="1" step="0.05" value={llm.temperature ?? 0.2} onChange={e => onChange({ ...config, llm: { ...llm, temperature: parseFloat(e.target.value) } })} style={{ width: '100%', accentColor: 'var(--brand-orange)' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: 'var(--text-tertiary)', marginTop: 2 }}><span>0 — deterministic</span><span>1 — creative</span></div>
      </Field>
      <Field label="Max Tokens">
        <input type="number" min="256" max="32768" step="256" style={{ ...inputStyle, width: 160 }} value={llm.max_tokens ?? 4096} onChange={e => onChange({ ...config, llm: { ...llm, max_tokens: parseInt(e.target.value) || 4096 } })} />
      </Field>
    </div>
  )
}

function ToolsTab({ agentName }) {
  const tools = AGENT_TOOLS[agentName] ?? []
  return (
    <div style={{ padding: 20 }}>
      <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 14, fontStyle: 'italic' }}>Tools are structural — changing them requires code changes.</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {tools.map((t, i) => {
          const c = CATEGORY_COLOURS[t.category] ?? CATEGORY_COLOURS.Tool
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', border: '1px solid var(--border-default)', borderRadius: 6, background: 'var(--bg-surface)' }}>
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 'var(--radius-pill)', background: c.bg, color: c.color, border: `1px solid ${c.border}`, flexShrink: 0 }}>{t.category}</span>
              <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>{t.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function BehaviorTab({ config, onChange }) {
  const behavior = config.behavior ?? {}
  const entries  = Object.entries(behavior)
  if (!entries.length) return <div style={{ padding: 20, color: 'var(--text-tertiary)', fontSize: 13 }}>No behavior settings for this agent.</div>
  const update = (key, val) => onChange({ ...config, behavior: { ...behavior, [key]: val } })
  const READONLY_KEYS = new Set(['check_types', 'embedder_model', 'embedder_dim'])
  return (
    <div style={{ padding: 20 }}>
      {entries.map(([key, val]) => {
        const label    = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
        const readonly = READONLY_KEYS.has(key)
        if (typeof val === 'boolean') return (
          <Field key={key} label={label}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: readonly ? 'default' : 'pointer' }}>
              <input type="checkbox" checked={val} disabled={readonly} onChange={e => !readonly && update(key, e.target.checked)} style={{ accentColor: 'var(--brand-orange)', width: 14, height: 14 }} />
              <span style={{ fontSize: 13, color: readonly ? 'var(--text-tertiary)' : 'var(--text-primary)' }}>{val ? 'Enabled' : 'Disabled'}</span>
            </label>
          </Field>
        )
        if (Array.isArray(val)) return (
          <Field key={key} label={label}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {val.map((v, i) => <span key={i} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 'var(--radius-pill)', background: 'var(--bg-subtle)', border: '1px solid var(--border-default)', color: 'var(--text-secondary)' }}>{v}</span>)}
            </div>
          </Field>
        )
        if (typeof val === 'number') return (
          <Field key={key} label={label}>
            <input type="number" style={{ ...inputStyle, width: 160 }} value={val} disabled={readonly} onChange={e => !readonly && update(key, parseFloat(e.target.value) || 0)} />
          </Field>
        )
        return (
          <Field key={key} label={label}>
            <input style={{ ...inputStyle, color: readonly ? 'var(--text-tertiary)' : 'var(--text-primary)' }} value={val ?? ''} readOnly={readonly} onChange={e => !readonly && update(key, e.target.value)} />
          </Field>
        )
      })}
    </div>
  )
}

// ── Observability section ─────────────────────────────────────────────────────
const SAMPLE_TRACES = [
  { id: 'req_a3f9d1', user: 'priya.m@corp.in',  domain: 'Sales',        guardrail: 'pass',  intent: 'pass',  sql: 'pass',      validation: 'pass', synthesis: 'pass', duration: '3.8s', ts: '26 May 09:14' },
  { id: 'req_b72c4e', user: 'rahul.k@corp.in',  domain: 'Finance',      guardrail: 'pass',  intent: 'pass',  sql: 'corrected', validation: 'pass', synthesis: 'pass', duration: '6.1s', ts: '26 May 09:07' },
  { id: 'req_c1e80a', user: 'admin@slm.local',  domain: 'HR',           guardrail: 'block', intent: '—',     sql: '—',         validation: '—',    synthesis: '—',    duration: '0.4s', ts: '26 May 08:52' },
  { id: 'req_d4b3f2', user: 'ananya.s@corp.in', domain: 'Sales',        guardrail: 'pass',  intent: 'pass',  sql: 'fail',      validation: '—',    synthesis: '—',    duration: '5.2s', ts: '26 May 08:31' },
  { id: 'req_e9a1c7', user: 'priya.m@corp.in',  domain: 'Supply Chain', guardrail: 'pass',  intent: 'pass',  sql: 'pass',      validation: 'pass', synthesis: 'pass', duration: '4.7s', ts: '25 May 17:45' },
  { id: 'req_f6d2b8', user: 'vikram.t@corp.in', domain: 'Sales',        guardrail: 'pass',  intent: 'pass',  sql: 'corrected', validation: 'pass', synthesis: 'pass', duration: '7.3s', ts: '25 May 16:22' },
  { id: 'req_g0e5a3', user: 'rahul.k@corp.in',  domain: 'Finance',      guardrail: 'pass',  intent: 'error', sql: '—',         validation: '—',    synthesis: '—',    duration: '2.9s', ts: '25 May 15:08' },
  { id: 'req_h8c4d6', user: 'admin@slm.local',  domain: 'Sales',        guardrail: 'pass',  intent: 'pass',  sql: 'pass',      validation: 'pass', synthesis: 'pass', duration: '3.2s', ts: '25 May 14:37' },
]

function TraceStatusBadge({ v }) {
  const M = {
    pass:      { t: '✓ Pass',      c: '#16a34a', b: '#f0fdf4' },
    corrected: { t: '⟳ Corrected', c: '#d97706', b: '#fffbeb' },
    block:     { t: '🚫 Blocked',  c: '#dc2626', b: '#fef2f2' },
    fail:      { t: '✗ Failed',    c: '#dc2626', b: '#fef2f2' },
    error:     { t: '⚠ Error',     c: '#f59e0b', b: '#fffbeb' },
    '—':       { t: '—',           c: 'var(--text-tertiary)', b: 'transparent' },
  }
  const s = M[v] ?? M['—']
  return <span style={{ fontSize: 10, fontWeight: 600, padding: v === '—' ? 0 : '2px 6px', borderRadius: 4, background: s.b, color: s.c, whiteSpace: 'nowrap' }}>{s.t}</span>
}

function ObservabilitySection({ agents, statuses }) {
  const PIPELINE_COLS = ['Request ID', 'User', 'Domain', 'Guardrail', 'Intent', 'SQL', 'Validation', 'Synthesis', 'Duration', 'Timestamp']

  return (
    <div style={{ padding: 24, overflowY: 'auto', height: '100%', boxSizing: 'border-box' }}>

      {/* KPI row */}
      <SectionLabel>Pipeline Overview</SectionLabel>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
        <MetricTile label="Total Requests"       value="1,247" sub="All time" />
        <MetricTile label="Avg Latency"          value="4.2s"  sub="End-to-end" />
        <MetricTile label="Error Rate"           value="3.1%"  sub="Any agent failure" accent="#ef4444" />
        <MetricTile label="Guardrail Blocks"     value="8.4%"  sub="% of total" accent="#f59e0b" />
        <MetricTile label="Avg Intents / Prompt" value="2.3"   sub="ARIA output" />
      </div>

      {/* Agent health grid */}
      <SectionLabel>Agent Health</SectionLabel>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 24 }}>
        {agents.map(ag => {
          const status = statuses[ag.agent_name] ?? 'unknown'
          const dotColor = status === 'online' ? '#16a34a' : status === 'degraded' ? '#f59e0b' : '#9ca3af'
          const bgColor  = status === 'online' ? '#f0fdf4' : status === 'degraded' ? '#fffbeb' : 'var(--bg-subtle)'
          return (
            <div key={ag.agent_name} style={{
              flex: '1 1 140px', minWidth: 130,
              padding: '12px 14px',
              border: `1px solid ${status === 'online' ? '#86efac' : status === 'degraded' ? '#fde68a' : 'var(--border-default)'}`,
              borderRadius: 8,
              background: bgColor,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: dotColor, display: 'inline-block', flexShrink: 0 }} />
                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>{ag.display_name}</span>
              </div>
              <div style={{ fontSize: 10.5, color: 'var(--text-tertiary)' }}>Port :{ag.port}</div>
              <div style={{ fontSize: 10.5, color: dotColor, fontWeight: 600, marginTop: 2, textTransform: 'capitalize' }}>{status}</div>
            </div>
          )
        })}
      </div>

      {/* Latency chart placeholder */}
      <SectionLabel>Latency Trend (p50 / p95)</SectionLabel>
      <div style={{ marginBottom: 24 }}>
        <ComingSoon label="Latency Chart" />
      </div>

      {/* Request volume placeholder */}
      <SectionLabel>Request Volume</SectionLabel>
      <div style={{ marginBottom: 24 }}>
        <ComingSoon label="Requests per Hour" />
      </div>

      {/* Pipeline traces table */}
      <SectionLabel>Recent Pipeline Traces</SectionLabel>
      <div style={{ border: '1px solid var(--border-default)', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr>
                {PIPELINE_COLS.map(c => (
                  <th key={c} style={{ padding: '7px 10px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap', fontSize: 10.5 }}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SAMPLE_TRACES.map((row, i) => (
                <tr key={row.id} style={{ background: i % 2 === 0 ? 'var(--bg-surface)' : 'var(--bg-subtle)' }}>
                  <td style={{ padding: '6px 10px', fontFamily: 'monospace', fontSize: 10.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{row.id}</td>
                  <td style={{ padding: '6px 10px', whiteSpace: 'nowrap' }}>{row.user}</td>
                  <td style={{ padding: '6px 10px', whiteSpace: 'nowrap' }}>{row.domain}</td>
                  <td style={{ padding: '6px 10px' }}><TraceStatusBadge v={row.guardrail} /></td>
                  <td style={{ padding: '6px 10px' }}><TraceStatusBadge v={row.intent} /></td>
                  <td style={{ padding: '6px 10px' }}><TraceStatusBadge v={row.sql} /></td>
                  <td style={{ padding: '6px 10px' }}><TraceStatusBadge v={row.validation} /></td>
                  <td style={{ padding: '6px 10px' }}><TraceStatusBadge v={row.synthesis} /></td>
                  <td style={{ padding: '6px 10px', whiteSpace: 'nowrap' }}>{row.duration}</td>
                  <td style={{ padding: '6px 10px', whiteSpace: 'nowrap', color: 'var(--text-tertiary)' }}>{row.ts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── Evaluation section ────────────────────────────────────────────────────────
const SAMPLE_FEEDBACK = [
  { id: 'req_a3f9d1', user: 'priya.m@corp.in',  domain: 'Sales',        rating: '👍', comment: 'Exactly the breakdown I needed'     , ts: '26 May 09:15' },
  { id: 'req_b72c4e', user: 'rahul.k@corp.in',  domain: 'Finance',      rating: '👍', comment: 'Good but took too long'              , ts: '26 May 09:08' },
  { id: 'req_e9a1c7', user: 'priya.m@corp.in',  domain: 'Supply Chain', rating: '👍', comment: ''                                    , ts: '25 May 17:46' },
  { id: 'req_f6d2b8', user: 'vikram.t@corp.in', domain: 'Sales',        rating: '👎', comment: 'Wrong quarter filter applied'        , ts: '25 May 16:24' },
  { id: 'req_h8c4d6', user: 'admin@slm.local',  domain: 'Sales',        rating: '👍', comment: 'Commission calc spot-on'             , ts: '25 May 14:38' },
]

const SAMPLE_VIOLATIONS = [
  { intent: 'INT-02', domain: 'Finance',      type: 'CLS',    detail: 'profit_usd column excluded per CLS policy',              corrected: 'Yes', ts: '26 May 09:07' },
  { intent: 'INT-01', domain: 'Sales',        type: 'RLS',    detail: 'Missing country filter — injected WHERE country IN (…)', corrected: 'Yes', ts: '25 May 16:22' },
  { intent: 'INT-03', domain: 'HR',           type: 'SCHEMA', detail: 'Table hr.dim_employee not in schema_reference.json',     corrected: 'No',  ts: '25 May 15:08' },
  { intent: 'INT-01', domain: 'Supply Chain', type: 'SYNTAX', detail: 'Missing GROUP BY for aggregate SUM(units)',               corrected: 'Yes', ts: '25 May 11:34' },
  { intent: 'INT-02', domain: 'Sales',        type: 'FILTER', detail: 'Date range filter outside allowed window',                corrected: 'Yes', ts: '24 May 14:19' },
]

function ViolationTypeBadge({ type }) {
  const M = {
    CLS:    { c: '#9333ea', b: '#faf5ff' },
    RLS:    { c: '#ea580c', b: '#fff7ed' },
    SCHEMA: { c: '#3b82f6', b: '#eff6ff' },
    SYNTAX: { c: '#ca8a04', b: '#fefce8' },
    FILTER: { c: '#475569', b: '#f1f5f9' },
  }
  const s = M[type] ?? M.SYNTAX
  return <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4, background: s.b, color: s.c }}>{type}</span>
}

function EvaluationSection() {
  const VIOLATION_COLS = ['Intent ID', 'Domain', 'Violation Type', 'Detail', 'Corrected', 'Timestamp']
  const FEEDBACK_COLS  = ['Request ID', 'User', 'Domain', 'Rating', 'Comment', 'Timestamp']

  return (
    <div style={{ padding: 24, overflowY: 'auto', height: '100%', boxSizing: 'border-box' }}>

      {/* Feedback KPIs */}
      <SectionLabel>User Feedback</SectionLabel>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
        <MetricTile label="👍 Upvotes"    value="89"    sub="Total positive" accent="#16a34a" />
        <MetricTile label="👎 Downvotes"  value="12"    sub="Total negative" accent="#ef4444" />
        <MetricTile label="Satisfaction"  value="88.1%" sub="Upvotes / total rated" />
        <MetricTile label="Response Rate" value="62.4%" sub="% prompts rated" />
      </div>

      {/* Feedback log table */}
      <div style={{ border: '1px solid var(--border-default)', borderRadius: 8, overflow: 'hidden', marginBottom: 24 }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr>
                {FEEDBACK_COLS.map(c => (
                  <th key={c} style={{ padding: '7px 10px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap', fontSize: 10.5 }}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SAMPLE_FEEDBACK.map((row, i) => (
                <tr key={row.id} style={{ background: i % 2 === 0 ? 'var(--bg-surface)' : 'var(--bg-subtle)' }}>
                  <td style={{ padding: '6px 10px', fontFamily: 'monospace', fontSize: 10.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{row.id}</td>
                  <td style={{ padding: '6px 10px', whiteSpace: 'nowrap' }}>{row.user}</td>
                  <td style={{ padding: '6px 10px', whiteSpace: 'nowrap' }}>{row.domain}</td>
                  <td style={{ padding: '6px 10px', fontSize: 15 }}>{row.rating}</td>
                  <td style={{ padding: '6px 10px', color: 'var(--text-secondary)', fontStyle: row.comment ? 'normal' : 'italic' }}>{row.comment || 'No comment'}</td>
                  <td style={{ padding: '6px 10px', whiteSpace: 'nowrap', color: 'var(--text-tertiary)' }}>{row.ts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* SQL quality KPIs */}
      <SectionLabel>SQL Quality</SectionLabel>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
        <MetricTile label="First-Pass Rate"    value="74.2%" sub="VALKYRIE pass, no correction" accent="#16a34a" />
        <MetricTile label="Correction Rate"    value="25.8%" sub="Required ≥1 correction round" accent="#f59e0b" />
        <MetricTile label="Correction Success" value="91.3%" sub="Corrected SQL passed" />
        <MetricTile label="Avg Corrections"    value="1.4"   sub="Rounds per failed intent" />
      </div>

      {/* Violation breakdown */}
      <SectionLabel>Validation Violations</SectionLabel>
      <div style={{ border: '1px solid var(--border-default)', borderRadius: 8, overflow: 'hidden', marginBottom: 24 }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr>
                {VIOLATION_COLS.map(c => (
                  <th key={c} style={{ padding: '7px 10px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap', fontSize: 10.5 }}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SAMPLE_VIOLATIONS.map((row, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? 'var(--bg-surface)' : 'var(--bg-subtle)' }}>
                  <td style={{ padding: '6px 10px', fontFamily: 'monospace', fontSize: 10.5, color: 'var(--text-secondary)' }}>{row.intent}</td>
                  <td style={{ padding: '6px 10px', whiteSpace: 'nowrap' }}>{row.domain}</td>
                  <td style={{ padding: '6px 10px' }}><ViolationTypeBadge type={row.type} /></td>
                  <td style={{ padding: '6px 10px', color: 'var(--text-secondary)', maxWidth: 280 }}>{row.detail}</td>
                  <td style={{ padding: '6px 10px' }}>
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 4, background: row.corrected === 'Yes' ? '#f0fdf4' : '#fef2f2', color: row.corrected === 'Yes' ? '#16a34a' : '#dc2626' }}>{row.corrected}</span>
                  </td>
                  <td style={{ padding: '6px 10px', whiteSpace: 'nowrap', color: 'var(--text-tertiary)' }}>{row.ts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Intent + RAG metrics */}
      <SectionLabel>Intent Classification</SectionLabel>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
        <MetricTile label="Avg Intents / Prompt" value="2.3"   sub="ARIA decomposition" />
        <MetricTile label="Structured %"          value="58.2%" sub="DB query intents" />
        <MetricTile label="Unstructured %"         value="21.4%" sub="RAG-only intents" />
        <MetricTile label="Both %"                 value="20.4%" sub="DB + RAG intents" />
      </div>
      <div style={{ marginBottom: 24 }}>
        <ComingSoon label="Intent Distribution Chart" />
      </div>

      {/* RAG quality */}
      <SectionLabel>RAG Retrieval Quality</SectionLabel>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
        <MetricTile label="Avg Similarity"     value="0.847" sub="Top-1 chunk score" />
        <MetricTile label="Zero-Result Rate"   value="4.2%"  sub="Below threshold" accent="#ef4444" />
        <MetricTile label="Avg Chunks / Query" value="3.8"   sub="Returned by RAVEN" />
      </div>
      <div style={{ marginBottom: 8 }}>
        <ComingSoon label="Similarity Score Distribution" />
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AgentManagement() {
  const { logout } = useAuth()
  const [section,    setSection]    = useState('Agents')
  const [agents,     setAgents]     = useState([])
  const [statuses,   setStatuses]   = useState({})
  const [selected,   setSelected]   = useState(null)
  const [activeTab,  setActiveTab]  = useState('Persona')
  const [editConfig, setEditConfig] = useState({})
  const [dirty,      setDirty]      = useState(false)
  const [saving,     setSaving]     = useState(false)
  const [loading,    setLoading]    = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, sts] = await Promise.all([getAgents(), getAgentStatuses()])
      setAgents(list)
      setStatuses(sts)
      if (!selected && list.length) {
        setSelected(list[0].agent_name)
        setEditConfig(deepClone(list[0].config))
      }
    } catch {
      toast.error('Failed to load agents')
    } finally {
      setLoading(false)
    }
  }, []) // eslint-disable-line

  useEffect(() => { load() }, [load])

  const selectedAgent = agents.find(a => a.agent_name === selected)

  const handleSelect = ag => {
    if (dirty && !confirm('Discard unsaved changes?')) return
    setSelected(ag.agent_name)
    setEditConfig(deepClone(ag.config))
    setDirty(false)
    setActiveTab('Persona')
  }

  const handleConfigChange = newConfig => { setEditConfig(newConfig); setDirty(true) }
  const handleDiscard = () => { if (!selectedAgent) return; setEditConfig(deepClone(selectedAgent.config)); setDirty(false) }

  const handleSave = async () => {
    if (!selected || !dirty) return
    setSaving(true)
    try {
      const updated = await updateAgent(selected, { config: editConfig })
      setAgents(prev => prev.map(a => a.agent_name === selected ? { ...a, config: updated.config } : a))
      setDirty(false)
      toast.success('Agent config saved')
      setTimeout(() => {
        const doLogout = window.confirm('Changes take effect on next login.\n\nLog out now to apply the new configuration?')
        if (doLogout) logout()
      }, 400)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>Loading agents…</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* ── Header ── */}
      <div style={{
        height: 52, minHeight: 52, background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', flexShrink: 0,
      }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>Agent Management</span>
        <button className="btn btn-ghost btn-sm" onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {/* ── Section switcher ── */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border-default)', background: 'var(--bg-surface)', padding: '0 16px', gap: 2, flexShrink: 0 }}>
        {SECTIONS.map(({ key, label, icon: Icon }) => {
          const active = section === key
          return (
            <button key={key} onClick={() => setSection(key)} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '10px 16px',
              fontSize: 12.5, fontWeight: active ? 700 : 500,
              color: active ? 'var(--brand-blue, #1A4FA0)' : 'var(--text-secondary)',
              background: 'none', border: 'none', cursor: 'pointer',
              borderBottom: active ? '2px solid var(--brand-blue, #1A4FA0)' : '2px solid transparent',
              marginBottom: -1, transition: 'all 0.15s',
            }}>
              <Icon size={13} />
              {label}
            </button>
          )
        })}
      </div>

      {/* ── Body ── */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>

        {/* ── Agents section ── */}
        {section === 'Agents' && (
          <>
            {/* Left: agent list */}
            <div style={{ width: 220, minWidth: 220, flexShrink: 0, borderRight: '1px solid var(--border-default)', overflowY: 'auto', background: 'var(--bg-surface)' }}>
              <div style={{ padding: '10px 12px 6px', fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Agents</div>
              {agents.map(ag => {
                const isActive = ag.agent_name === selected
                const status   = statuses[ag.agent_name] ?? 'unknown'
                return (
                  <button key={ag.agent_name} onClick={() => handleSelect(ag)} style={{
                    width: '100%', textAlign: 'left', padding: '9px 14px',
                    display: 'flex', alignItems: 'center', gap: 9,
                    background: isActive ? 'var(--brand-orange-subtle)' : 'transparent',
                    border: 'none',
                    borderLeft: isActive ? '3px solid var(--brand-orange)' : '3px solid transparent',
                    cursor: 'pointer', transition: 'background var(--transition-fast)',
                  }}>
                    <StatusDot status={status} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: isActive ? 700 : 500, color: isActive ? 'var(--brand-orange)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ag.display_name}</div>
                      <div style={{ fontSize: 10.5, color: 'var(--text-tertiary)' }}>:{ag.port}</div>
                    </div>
                  </button>
                )
              })}
            </div>

            {/* Right: agent detail */}
            {selectedAgent ? (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                {/* Agent header */}
                <div style={{ padding: '12px 20px 10px', borderBottom: '1px solid var(--border-default)', background: 'var(--bg-header)', flexShrink: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <StatusDot status={statuses[selected] ?? 'unknown'} />
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{selectedAgent.display_name}</div>
                      <div style={{ fontSize: 11.5, color: 'var(--text-tertiary)', marginTop: 1 }}>{selectedAgent.description}</div>
                    </div>
                  </div>
                </div>

                <TabBar active={activeTab} onChange={setActiveTab} />

                <div style={{ flex: 1, overflowY: 'auto' }}>
                  {activeTab === 'Persona'    && <PersonaTab  config={editConfig} onChange={handleConfigChange} />}
                  {activeTab === 'LLM Config' && <LLMTab      config={editConfig} onChange={handleConfigChange} />}
                  {activeTab === 'Tools'      && <ToolsTab    agentName={selected} />}
                  {activeTab === 'Behavior'   && <BehaviorTab config={editConfig} onChange={handleConfigChange} />}
                </div>

                {/* Footer */}
                <div style={{ padding: '10px 20px', borderTop: '1px solid var(--border-default)', background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
                  <span style={{ fontSize: 11.5, fontWeight: 600, color: dirty ? 'var(--color-warning, #f59e0b)' : 'var(--text-tertiary)' }}>
                    {dirty ? '⚠ Unsaved changes' : 'Changes take effect on next login'}
                  </span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-ghost btn-sm" onClick={handleDiscard} disabled={!dirty || saving}>Discard</button>
                    <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={!dirty || saving}>{saving ? 'Saving…' : 'Save'}</button>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>Select an agent</div>
            )}
          </>
        )}

        {/* ── Observability section ── */}
        {section === 'Observability' && (
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <ObservabilitySection agents={agents} statuses={statuses} />
          </div>
        )}

        {/* ── Evaluation section ── */}
        {section === 'Evaluation' && (
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <EvaluationSection />
          </div>
        )}
      </div>
    </div>
  )
}
