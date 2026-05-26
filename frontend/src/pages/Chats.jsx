import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Plus, Trash2, Send, MessageSquare, ChevronDown, ChevronUp, Download, ThumbsUp, ThumbsDown } from 'lucide-react'
import { getChats, getChatMessages, sendPrompt, streamSendPrompt, deleteChat, getSecurityGroups, getMe, exportReport } from '../api/client'
import { useSkills } from '../contexts/SkillsContext'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import * as XLSX from 'xlsx'
import {
  ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line,
  PieChart, Pie, Cell, Legend,
} from 'recharts'

// ── Palette ───────────────────────────────────────────────────────────────────
const CHART_COLORS = ['#1A4FA0', '#F47920', '#22c55e', '#a855f7', '#06b6d4', '#f43f5e', '#eab308', '#64748b']

// ── Simple inline markdown renderer ──────────────────────────────────────────
function InlineBold({ text }) {
  const parts = text.split(/\*\*(.+?)\*\*/g)
  return <>{parts.map((p, i) => i % 2 === 1 ? <strong key={i}>{p}</strong> : p)}</>
}

function MarkdownText({ text }) {
  if (!text) return null
  return (
    <div style={{ fontSize: 12.5, color: 'var(--text-primary)', lineHeight: 1.7 }}>
      {text.split('\n').map((line, i) => {
        if (line.startsWith('### '))
          return <div key={i} style={{ fontWeight: 700, fontSize: 12.5, marginTop: 10, marginBottom: 2, color: 'var(--text-primary)' }}><InlineBold text={line.slice(4)} /></div>
        if (line.startsWith('## '))
          return <div key={i} style={{ fontWeight: 700, fontSize: 13.5, marginTop: 12, marginBottom: 3, color: 'var(--text-primary)' }}><InlineBold text={line.slice(3)} /></div>
        if (line.startsWith('# '))
          return <div key={i} style={{ fontWeight: 700, fontSize: 14, marginTop: 14, marginBottom: 4, color: 'var(--text-primary)' }}><InlineBold text={line.slice(2)} /></div>
        if (line.match(/^[-*•] /))
          return <div key={i} style={{ paddingLeft: 14, marginTop: 2 }}>• <InlineBold text={line.slice(2)} /></div>
        if (line.match(/^\d+\. /))
          return <div key={i} style={{ paddingLeft: 14, marginTop: 2 }}><InlineBold text={line} /></div>
        if (line.trim() === '')
          return <div key={i} style={{ height: 6 }} />
        return <div key={i} style={{ marginTop: 1 }}><InlineBold text={line} /></div>
      })}
    </div>
  )
}

// ── Download helpers ──────────────────────────────────────────────────────────
function downloadCSV(sqlResults, requestId) {
  const rows = sqlResults.flatMap(sr =>
    (sr.rows || []).map(row => ({ _query: sr.label || sr.query_id, ...row }))
  )
  if (!rows.length) return
  const cols = Object.keys(rows[0])
  const csv = [cols.join(','), ...rows.map(r => cols.map(c => JSON.stringify(r[c] ?? '')).join(','))].join('\n')
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  a.download = `report_${requestId || Date.now()}.csv`
  a.click()
}

function downloadExcel(sqlResults, requestId) {
  const wb = XLSX.utils.book_new()
  sqlResults.forEach(sr => {
    if (!sr.rows?.length) return
    const ws = XLSX.utils.json_to_sheet(sr.rows)
    XLSX.utils.book_append_sheet(wb, ws, (sr.label || sr.query_id || 'Sheet').slice(0, 31))
  })
  if (!wb.SheetNames.length) return
  XLSX.writeFile(wb, `report_${requestId || Date.now()}.xlsx`)
}

async function downloadPDF(panelRef, requestId) {
  if (!panelRef.current) return
  try {
    const { default: html2canvas } = await import('html2canvas')
    const { default: jsPDF } = await import('jspdf')
    const canvas = await html2canvas(panelRef.current, { scale: 2, useCORS: true })
    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
    const pageW = 190
    const imgH = (canvas.height * pageW) / canvas.width
    const pageH = 277
    let yPos = 0
    let remaining = imgH

    while (remaining > 0) {
      if (yPos > 0) pdf.addPage()
      const sliceH = Math.min(remaining, pageH)
      pdf.addImage(imgData, 'PNG', 10, 10, pageW, imgH, '', 'FAST', 0)
      remaining -= sliceH
      yPos += sliceH
      if (remaining > 0) break // simple single-page for now; multi-page needs canvas slicing
    }
    pdf.save(`report_${requestId || Date.now()}.pdf`)
  } catch (e) {
    toast.error('PDF export failed: ' + e.message)
  }
}

// ── KPI Card ─────────────────────────────────────────────────────────────────
function KPICards({ rows, columns }) {
  const row = rows[0]
  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
      {columns.map((col, i) => {
        const val = row[col]
        const isNum = typeof val === 'number'
        return (
          <div key={col} style={{
            flex: '1 1 120px', minWidth: 100, maxWidth: 200,
            padding: '10px 14px',
            borderRadius: 8,
            background: 'var(--bg-subtle)',
            border: '1px solid var(--border-default)',
          }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{col}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: isNum ? 'var(--brand-orange, #F47920)' : 'var(--text-primary)' }}>
              {isNum ? val.toLocaleString() : String(val ?? '—')}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Chart view ────────────────────────────────────────────────────────────────
function ChartView({ rows, columns, chartType }) {
  const catCol = columns.find(c => typeof rows[0][c] === 'string') || columns[0]
  const numCols = columns.filter(c => typeof rows[0][c] === 'number')
  if (!numCols.length) return null

  const data = rows.slice(0, 30).map(r => ({ name: String(r[catCol] ?? ''), ...Object.fromEntries(numCols.map(nc => [nc, r[nc]])) }))

  const axisStyle = { fontSize: 10, fill: 'var(--text-tertiary)' }
  const tipStyle  = { fontSize: 11 }

  if (chartType === 'pie' && numCols.length >= 1) {
    const pieData = data.map(d => ({ name: d.name, value: d[numCols[0]] }))
    return (
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false}>
            {pieData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
          </Pie>
          <Tooltip formatter={v => v?.toLocaleString()} contentStyle={tipStyle} />
          <Legend iconSize={10} wrapperStyle={{ fontSize: 10 }} />
        </PieChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'line') {
    return (
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis dataKey="name" tick={axisStyle} />
          <YAxis tick={axisStyle} width={50} />
          <Tooltip formatter={v => v?.toLocaleString()} contentStyle={tipStyle} />
          {numCols.map((nc, i) => <Line key={nc} type="monotone" dataKey={nc} stroke={CHART_COLORS[i % CHART_COLORS.length]} dot={false} strokeWidth={2} />)}
        </LineChart>
      </ResponsiveContainer>
    )
  }

  // default: bar
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
        <XAxis dataKey="name" tick={axisStyle} />
        <YAxis tick={axisStyle} width={50} />
        <Tooltip formatter={v => v?.toLocaleString()} contentStyle={tipStyle} />
        {numCols.map((nc, i) => <Bar key={nc} dataKey={nc} fill={CHART_COLORS[i % CHART_COLORS.length]} radius={[2, 2, 0, 0]} />)}
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── SpyderTable ───────────────────────────────────────────────────────────────
function SpyderTable({ sr }) {
  const rows    = sr.rows || []
  const columns = sr.columns || (rows[0] ? Object.keys(rows[0]) : [])
  if (rows.length === 0) return null

  const numCols   = columns.filter(c => typeof rows[0][c] === 'number')
  const hasDate   = columns.some(c => /date|month|year|week|day|time/i.test(c))
  const isKPI     = rows.length === 1 && columns.length <= 4
  const hasChart  = numCols.length > 0 && !isKPI

  // Default chart type heuristic
  const defaultChart = hasDate ? 'line' : rows.length <= 6 && numCols.length === 1 ? 'pie' : 'bar'
  const [view, setView]           = useState(isKPI ? 'kpi' : hasChart ? 'chart' : 'table')
  const [chartType, setChartType] = useState(defaultChart)

  const viewBtnStyle = active => ({
    fontSize: 10, padding: '2px 7px', borderRadius: 4,
    border: `1px solid ${active ? 'var(--brand-blue, #1A4FA0)' : 'var(--border-default)'}`,
    background: active ? 'var(--brand-blue-subtle, #eff6ff)' : 'transparent',
    color: active ? 'var(--brand-blue, #1A4FA0)' : 'var(--text-secondary)',
    cursor: 'pointer',
  })

  return (
    <div>
      {/* Row: label + view toggles */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6, flexWrap: 'wrap', gap: 4 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {sr.label || sr.query_id} <span style={{ fontWeight: 400 }}>({sr.row_count} rows)</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {isKPI && <button style={viewBtnStyle(view === 'kpi')} onClick={() => setView('kpi')}>KPI</button>}
          {hasChart && (
            <>
              <button style={viewBtnStyle(view === 'chart' && chartType === 'bar')}  onClick={() => { setView('chart'); setChartType('bar') }}>Bar</button>
              <button style={viewBtnStyle(view === 'chart' && chartType === 'line')} onClick={() => { setView('chart'); setChartType('line') }}>Line</button>
              <button style={viewBtnStyle(view === 'chart' && chartType === 'pie')}  onClick={() => { setView('chart'); setChartType('pie') }}>Pie</button>
            </>
          )}
          <button style={viewBtnStyle(view === 'table')} onClick={() => setView('table')}>Table</button>
        </div>
      </div>

      {/* Content */}
      {view === 'kpi' && <KPICards rows={rows} columns={columns} />}

      {view === 'chart' && <ChartView rows={rows} columns={columns} chartType={chartType} />}

      {view === 'table' && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr>
                {columns.map(c => (
                  <th key={c} style={{ padding: '3px 8px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 20).map((row, ri) => (
                <tr key={ri} style={{ borderBottom: '1px solid var(--border-default)' }}>
                  {columns.map(c => (
                    <td key={c} style={{ padding: '3px 8px', color: 'var(--text-primary)' }}>
                      {row[c] === null || row[c] === undefined ? '—' : String(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 20 && (
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', padding: '3px 8px' }}>
              Showing 20 of {rows.length} rows
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── SpyderSection ─────────────────────────────────────────────────────────────
function SpyderSection({ section, value, isFirst }) {
  if (!value) return null
  const labelStyle = {
    fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)',
    textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4,
  }
  const wrapStyle = {
    paddingTop: isFirst ? 0 : 10,
    borderTop: isFirst ? 'none' : '1px solid var(--border-subtle)',
  }

  if (section.display_type === 'list' && Array.isArray(value) && value.length > 0) {
    return (
      <div style={wrapStyle}>
        <div style={labelStyle}>{section.title}</div>
        <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 3 }}>
          {value.map((r, i) => (
            <li key={i} style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{r}</li>
          ))}
        </ul>
      </div>
    )
  }

  if (typeof value === 'string' && value.trim()) {
    return (
      <div style={wrapStyle}>
        <div style={labelStyle}>{section.title}</div>
        <MarkdownText text={value} />
      </div>
    )
  }

  return null
}

// ── SpyderPanel ───────────────────────────────────────────────────────────────
function SpyderPanel({ result, prompt }) {
  const panelRef = useRef()
  const [exportOpen, setExportOpen] = useState(false)
  const [feedback, setFeedback] = useState(null)

  const llm    = result.llm_response || {}
  const sqlRes = (result.sql_results || []).filter(r => r.status === 'success' && r.rows?.length > 0)

  const downloadBrandedReport = async () => {
    // Extract synthesis text from LLM response
    const sections = result.expected_output_schema?.sections || []
    let synthesis  = llm.synthesized_answer || ''
    if (!synthesis) {
      sections
        .filter(s => s.source === 'llm')
        .forEach(s => {
          const v = llm[s.section_id]
          if (typeof v === 'string' && v.trim()) synthesis += v + '\n'
          if (Array.isArray(v) && v.length)      synthesis += v.join('\n') + '\n'
        })
    }
    const recs = Array.isArray(llm.recommendations) ? llm.recommendations : []
    if (!synthesis && recs.length) synthesis = recs.join('\n')

    try {
      const title = prompt
        ? `Report: ${prompt.slice(0, 60)}${prompt.length > 60 ? '…' : ''}`
        : 'DataMind Report'
      const res = await exportReport({
        title,
        prompt:      prompt || '',
        synthesis:   synthesis.trim(),
        sql_results: sqlRes.map(sr => ({
          label:   sr.label || sr.query_id || 'Results',
          rows:    sr.rows  || [],
          columns: sr.columns || (sr.rows?.[0] ? Object.keys(sr.rows[0]) : []),
        })),
      })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a   = document.createElement('a')
      a.href     = url
      a.download = `datamind_report_${result.request_id || Date.now()}.pdf`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Branded report downloaded')
    } catch (e) {
      toast.error('Report failed: ' + (e.response?.data?.detail || e.message))
    }
  }

  const schemaSections = (result.expected_output_schema?.sections || []).filter(s => s.source === 'llm')
  const legacyAnswer   = llm.synthesized_answer
  const legacyRecs     = Array.isArray(llm.recommendations) ? llm.recommendations : []

  const hasDynamicContent = schemaSections.some(s => {
    const v = llm[s.section_id]
    return v && (typeof v === 'string' ? v.trim() : Array.isArray(v) ? v.length > 0 : false)
  })

  if (sqlRes.length === 0 && !hasDynamicContent && !legacyAnswer && !legacyRecs.length) return null

  const hasData = sqlRes.length > 0

  return (
    <div ref={panelRef} style={{ marginTop: 14, border: '1px solid var(--border-default)', borderRadius: 8, overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '6px 12px',
        background: 'var(--bg-subtle)',
        borderBottom: '1px solid var(--border-default)',
        fontSize: 10.5, fontWeight: 700, color: 'var(--text-secondary)',
        textTransform: 'uppercase', letterSpacing: '0.05em',
      }}>
        <span>🧠</span> SPYDER Synthesis
        <span style={{ marginLeft: 'auto', fontSize: 10, fontWeight: 500, textTransform: 'none', letterSpacing: 0, color: 'var(--text-tertiary)' }}>
          {result.domain || ''}
        </span>

        {/* Feedback buttons */}
        <button
          onClick={() => { setFeedback(f => f === 'up' ? null : 'up'); toast.success('Thanks for the feedback!', { icon: '👍', duration: 2000 }) }}
          style={{
            display: 'flex', alignItems: 'center',
            padding: '2px 6px', borderRadius: 4,
            border: `1px solid ${feedback === 'up' ? '#22c55e' : 'var(--border-default)'}`,
            background: feedback === 'up' ? '#f0fdf4' : 'transparent',
            color: feedback === 'up' ? '#22c55e' : 'var(--text-secondary)',
            cursor: 'pointer', outline: 'none', transition: 'all 0.15s',
          }}
        >
          <ThumbsUp size={12} />
        </button>
        <button
          onClick={() => { setFeedback(f => f === 'down' ? null : 'down'); toast('We\'ll use this to improve', { icon: '👎', duration: 2000 }) }}
          style={{
            display: 'flex', alignItems: 'center',
            padding: '2px 6px', borderRadius: 4,
            border: `1px solid ${feedback === 'down' ? '#ef4444' : 'var(--border-default)'}`,
            background: feedback === 'down' ? '#fef2f2' : 'transparent',
            color: feedback === 'down' ? '#ef4444' : 'var(--text-secondary)',
            cursor: 'pointer', outline: 'none', transition: 'all 0.15s',
          }}
        >
          <ThumbsDown size={12} />
        </button>

        {/* Export menu */}
        <div style={{ position: 'relative', marginLeft: 8 }}>
          <button
            onClick={() => setExportOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              fontSize: 10, padding: '2px 8px', borderRadius: 4,
              border: '1px solid var(--border-default)',
              background: 'var(--bg-surface)',
              color: 'var(--text-secondary)',
              cursor: 'pointer', fontWeight: 600,
              textTransform: 'none', letterSpacing: 0,
            }}
          >
            <Download size={10} /> Export
          </button>
          {exportOpen && (
            <div
              style={{
                position: 'absolute', right: 0, top: '110%', zIndex: 100,
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-default)',
                borderRadius: 6, boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                minWidth: 150, overflow: 'hidden',
              }}
              onMouseLeave={() => setExportOpen(false)}
            >
              {[
                hasData && { label: 'Excel (.xlsx)',       action: () => downloadExcel(sqlRes, result.request_id) },
                hasData && { label: 'CSV (.csv)',           action: () => downloadCSV(sqlRes, result.request_id) },
                hasData && { label: 'PDF — snapshot',      action: () => downloadPDF(panelRef, result.request_id) },
                          { label: 'Branded Report (.pdf)', action: () => downloadBrandedReport() },
              ].filter(Boolean).map(({ label, action }) => (
                <button
                  key={label}
                  onClick={() => { action(); setExportOpen(false) }}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '7px 12px', fontSize: 11,
                    background: 'none', border: 'none',
                    color: 'var(--text-primary)', cursor: 'pointer',
                    textTransform: 'none', letterSpacing: 0, fontWeight: 400,
                  }}
                  onMouseEnter={e => e.target.style.background = 'var(--bg-subtle)'}
                  onMouseLeave={e => e.target.style.background = 'none'}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* SQL result tables / charts / KPI */}
        {sqlRes.map(sr => <SpyderTable key={sr.query_id} sr={sr} />)}

        {/* Dynamic LLM sections */}
        {schemaSections.length > 0
          ? schemaSections.map((section, idx) => (
              <SpyderSection
                key={section.section_id}
                section={section}
                value={llm[section.section_id]}
                isFirst={idx === 0 && sqlRes.length === 0}
              />
            ))
          : <>
              {legacyAnswer && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                    Synthesized Answer
                  </div>
                  <MarkdownText text={legacyAnswer} />
                </div>
              )}
              {legacyRecs.length > 0 && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                    Recommendations
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {legacyRecs.map((r, i) => (
                      <li key={i} style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
        }
      </div>
    </div>
  )
}

// ── Pipeline progress ─────────────────────────────────────────────────────────
const PIPELINE_NODES = [
  { node: 'guardrail_check',   label: 'Guardrail check' },
  { node: 'intent_classify',   label: 'Intent classification' },
  { node: 'sql_generate',      label: 'SQL generation' },
  { node: 'raven_query',       label: 'RAG retrieval' },
  { node: 'validate_sql',      label: 'SQL validation' },
  { node: 'spyder_synthesize', label: 'Synthesis' },
]

function stepSummary(step) {
  if (!step) return ''
  switch (step.node) {
    case 'guardrail_check':  return step.status === 'passed' ? 'passed' : `blocked — ${step.blocked_by || 'policy'}`
    case 'intent_classify':  return step.status === 'success' ? `${step.intent_count} intent(s)` : step.error || 'error'
    case 'sql_generate':     return step.status === 'skipped' ? 'skipped' : step.status === 'error' ? (step.error || 'error') : `${step.sql_count} query(ies)`
    case 'raven_query':      return step.status === 'skipped' ? 'skipped' : step.status === 'success' ? `${step.inputs} input(s)` : step.error || 'error'
    case 'validate_sql': {
      const corr = step.correction_attempt > 0 ? ` · ${step.correction_attempt} correction(s)` : ''
      return `${step.status}${corr}`
    }
    case 'spyder_synthesize': return step.status === 'success' ? 'complete' : step.error || 'error'
    default: return step.status || ''
  }
}

function PipelineProgress({ steps }) {
  const stepMap    = Object.fromEntries((steps || []).map(s => [s.node, s]))
  const lastDoneIdx = PIPELINE_NODES.reduce((acc, n, i) => stepMap[n.node] ? i : acc, -1)

  return (
    <div style={{ padding: '4px 0', display: 'flex', flexDirection: 'column', gap: 6 }}>
      {PIPELINE_NODES.map((n, i) => {
        const step      = stepMap[n.node]
        const isRunning = !step && i === lastDoneIdx + 1
        const isFailed  = step && ['error', 'blocked', 'fail'].includes(step.status)
        const isSkipped = step?.status === 'skipped'
        const isDone    = !!step && !isFailed && !isSkipped

        const iconColor = isFailed ? '#ef4444' : isDone ? '#22c55e' : isRunning ? 'var(--brand-orange, #F47920)' : 'var(--border-default)'
        const icon      = isFailed ? '✗' : isDone ? '✓' : isRunning ? '⟳' : '○'
        const textColor = isDone || isFailed ? 'var(--text-primary)' : isRunning ? 'var(--text-secondary)' : 'var(--text-tertiary)'

        return (
          <div key={n.node} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5 }}>
            <span style={{ width: 12, textAlign: 'center', color: iconColor, fontWeight: 700, fontSize: 11 }}>{icon}</span>
            <span style={{ color: textColor, fontWeight: isDone || isFailed || isRunning ? 600 : 400 }}>{n.label}</span>
            {step && (
              <span style={{ fontSize: 10, color: isFailed ? '#ef4444' : 'var(--text-tertiary)' }}>
                — {stepSummary(step)}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Chats page ────────────────────────────────────────────────────────────────
export default function Chats() {
  const [chats, setChats]               = useState([])
  const [activeChatId, setActiveChatId] = useState(null)
  const [messages, setMessages]         = useState([])
  const [prompt, setPrompt]             = useState('')
  const [sending, setSending]           = useState(false)
  const [allSGs, setAllSGs]             = useState([])
  const [userSGIds, setUserSGIds]       = useState([])
  const [selectedSGIds, setSelectedSGIds] = useState([])
  const [recentOpen, setRecentOpen]     = useState(true)
  const { user } = useAuth()
  const bottomRef = useRef()
  const textareaRef = useRef()
  const suppressNextLoadRef = useRef(false)

  // ── @skill autocomplete ──────────────────────────────────────────────────
  const { skills } = useSkills()
  const [skillMenu, setSkillMenu]   = useState(false)
  const [skillQuery, setSkillQuery] = useState('')

  const activeSkills = useMemo(() => skills.filter(s => s.is_active), [skills])
  const suggestedSkills = useMemo(() => {
    if (!skillQuery) return activeSkills
    return activeSkills.filter(s =>
      s.name.includes(skillQuery) || s.description.toLowerCase().includes(skillQuery)
    )
  }, [activeSkills, skillQuery])

  const handlePromptChange = e => {
    const val = e.target.value
    setPrompt(val)
    const atMatch = val.match(/@(\w*)$/)
    if (atMatch) {
      setSkillMenu(true)
      setSkillQuery(atMatch[1].toLowerCase())
    } else {
      setSkillMenu(false)
      setSkillQuery('')
    }
  }

  const insertSkill = skill => {
    const params = (skill.parameters || []).filter(p => p.name)
    const text = `@${skill.name}${params.map(p => ` ${p.name}=<${p.example || p.name}>`).join('')} `
    setPrompt(p => p.replace(/@\w*$/, text))
    setSkillMenu(false)
    setTimeout(() => textareaRef.current?.focus(), 0)
  }

  useEffect(() => {
    loadChats()
    Promise.all([getSecurityGroups(), getMe()])
      .then(([sgs, me]) => {
        setAllSGs(sgs)
        const assignedIds = (me.security_groups || []).map(sg => sg.SecurityGroupID)
        setUserSGIds(assignedIds)
        setSelectedSGIds(assignedIds)
      })
      .catch(() => { getSecurityGroups().then(setAllSGs).catch(() => {}) })
  }, [])

  useEffect(() => { if (activeChatId) loadMessages(activeChatId) }, [activeChatId])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const loadChats = async () => { try { setChats(await getChats()) } catch {} }

  const loadMessages = async id => {
    if (suppressNextLoadRef.current) { suppressNextLoadRef.current = false; return }
    try {
      const raw = await getChatMessages(id)
      setMessages(raw.map(m => ({ ...m, SpyderResult: m.SpyderResult ?? m.Payload?.spyder_result ?? null })))
    } catch {}
  }

  const toggleSG = id => setSelectedSGIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const handleSend = async () => {
    if (!prompt.trim() || sending) return
    const text       = prompt.trim()
    const tempId     = Date.now()
    const tempUserId = `${tempId}_u`
    const tempAsstId = `${tempId}_a`
    setPrompt('')
    setSending(true)
    setMessages(m => [
      ...m,
      { MessageID: tempId,     Role: 'user',      Content: text },
      { MessageID: tempAsstId, Role: 'assistant', Content: null, _streaming: true, _steps: [] },
    ])

    try {
      await streamSendPrompt(
        { chat_id: activeChatId || null, prompt: text, security_group_ids: selectedSGIds.length > 0 ? selectedSGIds : null },
        (event) => {
          if (event.type === 'node') {
            setMessages(m => m.map(msg =>
              msg.MessageID === tempAsstId
                ? { ...msg, _steps: [...(msg._steps || []).filter(s => s.node !== event.node), event] }
                : msg
            ))
          } else if (event.type === 'done') {
            if (!activeChatId) {
              suppressNextLoadRef.current = true
              setActiveChatId(event.chat_id)
              loadChats()
            }
            setMessages(m => [
              ...m.filter(x => x.MessageID !== tempId && x.MessageID !== tempAsstId),
              { MessageID: tempUserId, Role: 'user', Content: text },
              {
                MessageID:       tempAsstId,
                Role:            'assistant',
                Content:         event.response,
                GuardrailStatus: event.guardrail_status,
                BlockedBy:       event.blocked_by,
                IntentResult:    event.intent_result,
                SqlResult:       event.sql_result,
                ValkyrieResult:  event.valkyrie_result,
                SpyderResult:    event.spyder_result,
              },
            ])
          } else if (event.type === 'error') {
            toast.error(event.message || 'Pipeline error')
          }
        }
      )
    } catch (err) {
      toast.error(err.message || 'Failed to send')
      setMessages(m => m.filter(x => x.MessageID !== tempId && x.MessageID !== tempAsstId))
      setPrompt(text)
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = e => {
    if (e.key === 'Escape' && skillMenu) { setSkillMenu(false); return }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }
  const startNewChat  = () => { setActiveChatId(null); setMessages([]) }

  const handleDelete = async (e, id) => {
    e.stopPropagation()
    await deleteChat(id)
    if (activeChatId === id) { setActiveChatId(null); setMessages([]) }
    await loadChats()
    toast.success('Chat deleted')
  }

  const visibleSGs = allSGs.filter(sg => userSGIds.includes(sg.SecurityGroupID))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        height: 52, minHeight: 52, background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', flexShrink: 0,
      }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>Chats</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {visibleSGs.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginRight: 2 }}>Groups:</span>
              {visibleSGs.map(sg => {
                const selected = selectedSGIds.includes(sg.SecurityGroupID)
                return (
                  <button
                    key={sg.SecurityGroupID}
                    onClick={() => toggleSG(sg.SecurityGroupID)}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      padding: '3px 9px', borderRadius: 'var(--radius-pill)',
                      fontSize: 11.5, fontWeight: 600,
                      border: `1px solid ${selected ? 'var(--brand-orange)' : 'var(--border-default)'}`,
                      background: selected ? 'var(--brand-orange-subtle)' : 'var(--bg-surface)',
                      color: selected ? 'var(--brand-orange)' : 'var(--text-secondary)',
                      cursor: 'pointer', transition: 'all var(--transition-fast)',
                    }}
                  >
                    {sg.SecurityGroupName}
                  </button>
                )
              })}
            </div>
          )}
          <button className="btn btn-primary btn-sm" onClick={startNewChat}><Plus size={12} /> New Chat</button>
        </div>
      </div>

      {/* Chat shell */}
      <div className="chat-shell">
        <div className="chat-main">
          <div className="messages-area">
            {messages.length === 0 && (
              <div className="empty-state" style={{ flex: 1, justifyContent: 'center' }}>
                <MessageSquare size={40} />
                <div className="empty-state-title">Start a new conversation</div>
                <div className="empty-state-desc">Type a prompt below to interact with MANTHAN.AI. Your security profile and guardrails will be applied automatically.</div>
              </div>
            )}
            {messages.map((m, i) => {
              const isBlocked  = m.GuardrailStatus === 'blocked'
              const isError    = m.GuardrailStatus === 'error'
              const prevPrompt = i > 0 && messages[i - 1]?.Role === 'user' ? messages[i - 1].Content : ''
              const bubbleStyle = isBlocked
                ? { borderLeft: '3px solid var(--color-error, #ef4444)', background: 'var(--bg-error-subtle, #fef2f2)' }
                : isError
                  ? { borderLeft: '3px solid var(--color-warning, #f59e0b)', background: 'var(--bg-warning-subtle, #fffbeb)' }
                  : {}
              return (
                <div key={m.MessageID || i} className={`message ${m.Role}`}>
                  <div className="message-bubble" style={bubbleStyle}>
                    {isBlocked && m.BlockedBy && (
                      <div style={{ marginBottom: 6 }}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          fontSize: 10.5, fontWeight: 700, letterSpacing: '0.04em',
                          padding: '2px 8px', borderRadius: 'var(--radius-pill)',
                          background: 'var(--color-error, #ef4444)', color: '#fff',
                        }}>🚫 {m.BlockedBy}</span>
                      </div>
                    )}
                    {m._streaming
                      ? <PipelineProgress steps={m._steps || []} />
                      : m.SpyderResult
                        ? <SpyderPanel result={m.SpyderResult} prompt={prevPrompt} />
                        : m.Content
                          ? <MarkdownText text={m.Content} />
                          : null
                    }
                  </div>
                </div>
              )
            })}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className="chat-input-bar" style={{ position: 'relative' }}>
            {/* @skill autocomplete dropdown */}
            {skillMenu && suggestedSkills.length > 0 && (
              <div style={{
                position: 'absolute', bottom: '100%', left: 0, right: 0, marginBottom: 4, zIndex: 50,
                background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
                borderRadius: 8, boxShadow: '0 -4px 16px rgba(0,0,0,0.12)',
                maxHeight: 230, overflowY: 'auto',
              }}>
                <div style={{
                  padding: '6px 12px 5px', fontSize: 9.5, fontWeight: 700,
                  color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em',
                  borderBottom: '1px solid var(--border-default)',
                }}>
                  Agent Skills {skillQuery && `— "${skillQuery}"`}
                </div>
                {suggestedSkills.map(s => (
                  <div
                    key={s.id}
                    onMouseDown={e => { e.preventDefault(); insertSkill(s) }}
                    style={{ padding: '8px 12px', cursor: 'pointer', display: 'flex', alignItems: 'flex-start', gap: 10 }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <code style={{ fontSize: 12, fontWeight: 700, color: 'var(--brand-blue, #1A4FA0)', fontFamily: 'monospace', whiteSpace: 'nowrap', flexShrink: 0 }}>
                      @{s.name}
                    </code>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {s.description}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 1 }}>
                        {s.type === 'template' && s.parameters?.length > 0
                          ? `Params: ${s.parameters.map(p => p.name).join(', ')}`
                          : s.type === 'view' ? 'DB View — no parameters' : 'No parameters'
                        }
                      </div>
                    </div>
                  </div>
                ))}
                {suggestedSkills.length === 0 && (
                  <div style={{ padding: '10px 12px', fontSize: 11, color: 'var(--text-tertiary)' }}>
                    No matching skills for "{skillQuery}"
                  </div>
                )}
              </div>
            )}
            <textarea
              ref={textareaRef}
              className="chat-textarea"
              rows={2}
              placeholder="Type your prompt… (Enter to send · Shift+Enter for newline · @ for skills)"
              value={prompt}
              onChange={handlePromptChange}
              onKeyDown={handleKeyDown}
              onBlur={() => setTimeout(() => setSkillMenu(false), 150)}
              disabled={sending}
            />
            <button
              className="btn btn-primary"
              style={{ alignSelf: 'flex-end', height: 38 }}
              onClick={handleSend}
              disabled={!prompt.trim() || sending}
            >
              <Send size={13} />
            </button>
          </div>
        </div>

        {/* Recent chats strip */}
        {chats.length > 0 && (
          <div className="chat-recent">
            <div className="chat-recent-header" onClick={() => setRecentOpen(o => !o)}>
              <span className="chat-recent-label">Recent Chats ({chats.length})</span>
              {recentOpen
                ? <ChevronDown size={12} style={{ color: 'var(--text-tertiary)' }} />
                : <ChevronUp size={12} style={{ color: 'var(--text-tertiary)' }} />}
            </div>
            {recentOpen && (
              <div className="chat-recent-list">
                {chats.map(c => (
                  <div
                    key={c.ChatID}
                    className={`chat-item ${activeChatId === c.ChatID ? 'active' : ''}`}
                    onClick={() => setActiveChatId(c.ChatID)}
                  >
                    <MessageSquare size={11} style={{ flexShrink: 0, opacity: 0.6 }} />
                    <span className="chat-item-text">{c.Title || 'Untitled'}</span>
                    <button className="chat-item-del" onClick={e => handleDelete(e, c.ChatID)}>
                      <Trash2 size={10} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
