import { useState, useEffect, useRef } from 'react'
import { Plus, Trash2, Send, MessageSquare, ChevronDown, ChevronUp, X } from 'lucide-react'
import { getChats, getChatMessages, sendPrompt, deleteChat, getSecurityGroups, getMe } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'

// ── Simple inline markdown renderer (no dependency) ──────────────────────────
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

// ── SPYDER synthesis panel ────────────────────────────────────────────────────
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

function SpyderPanel({ result }) {
  const llm    = result.llm_response || {}
  const sqlRes = (result.sql_results || []).filter(r => r.status === 'success' && r.rows?.length > 0)

  // Action 3: use dynamic sections from schema; fall back to legacy keys if absent
  const schemaSections = (result.expected_output_schema?.sections || [])
    .filter(s => s.source === 'llm')

  const legacyAnswer = llm.synthesized_answer
  const legacyRecs   = Array.isArray(llm.recommendations) ? llm.recommendations : []

  const hasDynamicContent = schemaSections.some(s => {
    const v = llm[s.section_id]
    return v && (typeof v === 'string' ? v.trim() : Array.isArray(v) ? v.length > 0 : false)
  })
  const hasLegacyContent = !!(legacyAnswer || legacyRecs.length > 0)

  if (sqlRes.length === 0 && !hasDynamicContent && !hasLegacyContent) return null

  return (
    <div style={{
      marginTop: 14,
      border: '1px solid var(--border-default)',
      borderRadius: 8,
      overflow: 'hidden',
    }}>
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
      </div>

      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 12 }}>

        {/* SQL result tables + bar charts */}
        {sqlRes.map(sr => (
          <SpyderTable key={sr.query_id} sr={sr} />
        ))}

        {/* Dynamic LLM sections (Action 3) */}
        {schemaSections.length > 0
          ? schemaSections.map((section, idx) => (
              <SpyderSection
                key={section.section_id}
                section={section}
                value={llm[section.section_id]}
                isFirst={idx === 0 && sqlRes.length === 0}
              />
            ))
          : /* Legacy fallback for old messages / SQL-only responses */
            <>
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

function SpyderTable({ sr }) {
  const [showChart, setShowChart] = useState(true)
  const rows    = sr.rows || []
  const columns = sr.columns || (rows[0] ? Object.keys(rows[0]) : [])
  if (rows.length === 0) return null

  // Auto-detect category col (first string) and value col (first number)
  const catCol = columns.find(c => typeof rows[0][c] === 'string') || columns[0]
  const numCol = columns.find(c => typeof rows[0][c] === 'number')
  const maxVal = numCol ? Math.max(...rows.map(r => Number(r[numCol]) || 0)) : 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {sr.label || sr.query_id} <span style={{ fontWeight: 400 }}>({sr.row_count} rows)</span>
        </div>
        {numCol && (
          <button
            onClick={() => setShowChart(v => !v)}
            style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4, border: '1px solid var(--border-default)', background: 'transparent', cursor: 'pointer', color: 'var(--text-secondary)' }}
          >
            {showChart ? 'Table' : 'Chart'}
          </button>
        )}
      </div>

      {/* Bar chart */}
      {showChart && numCol && maxVal > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {rows.slice(0, 15).map((row, i) => {
            const pct = maxVal > 0 ? (Number(row[numCol]) / maxVal) * 100 : 0
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
                <div style={{ width: 110, textAlign: 'right', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0 }}>
                  {String(row[catCol] ?? '')}
                </div>
                <div style={{ flex: 1, background: 'var(--bg-subtle)', borderRadius: 3, height: 14, overflow: 'hidden' }}>
                  <div style={{
                    width: `${pct}%`, height: '100%',
                    background: 'var(--brand-orange, #f97316)',
                    borderRadius: 3,
                    transition: 'width 0.4s ease',
                    minWidth: pct > 0 ? 3 : 0,
                  }} />
                </div>
                <div style={{ width: 64, color: 'var(--text-primary)', fontWeight: 600, textAlign: 'right', flexShrink: 0 }}>
                  {typeof row[numCol] === 'number' ? row[numCol].toLocaleString() : row[numCol]}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        /* Data table */
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

export default function Chats() {
  const [chats, setChats] = useState([])
  const [activeChatId, setActiveChatId] = useState(null)
  const [messages, setMessages] = useState([])
  const [prompt, setPrompt] = useState('')
  const [sending, setSending] = useState(false)
  const [allSGs, setAllSGs] = useState([])           // all SGs available
  const [userSGIds, setUserSGIds] = useState([])      // IDs assigned to user
  const [selectedSGIds, setSelectedSGIds] = useState([]) // currently selected
  const [recentOpen, setRecentOpen] = useState(true)
  const { user } = useAuth()
  const bottomRef = useRef()
  const suppressNextLoadRef = useRef(false)

  useEffect(() => {
    loadChats()
    Promise.all([getSecurityGroups(), getMe()])
      .then(([sgs, me]) => {
        setAllSGs(sgs)
        const assignedIds = (me.security_groups || []).map(sg => sg.SecurityGroupID)
        setUserSGIds(assignedIds)
        // Default: select all assigned SGs
        setSelectedSGIds(assignedIds)
      })
      .catch(() => {
        getSecurityGroups().then(setAllSGs).catch(() => {})
      })
  }, [])

  useEffect(() => {
    if (activeChatId) loadMessages(activeChatId)
  }, [activeChatId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadChats = async () => {
    try { setChats(await getChats()) } catch {}
  }

  const loadMessages = async id => {
    if (suppressNextLoadRef.current) {
      suppressNextLoadRef.current = false
      return
    }
    try {
      const raw = await getChatMessages(id)
      setMessages(raw.map(m => ({
        ...m,
        SpyderResult: m.SpyderResult ?? m.Payload?.spyder_result ?? null,
      })))
    } catch {}
  }

  const toggleSG = id => {
    setSelectedSGIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const handleSend = async () => {
    if (!prompt.trim() || sending) return
    const text = prompt.trim()
    setPrompt('')
    setSending(true)

    const tempId = Date.now()
    setMessages(m => [...m, { MessageID: tempId, Role: 'user', Content: text }])

    try {
      const res = await sendPrompt({
        chat_id: activeChatId || null,
        prompt: text,
        // Send list if specific subset selected; null means backend uses all assigned
        security_group_ids: selectedSGIds.length > 0 ? selectedSGIds : null,
      })
      if (!activeChatId) {
        suppressNextLoadRef.current = true   // prevent useEffect loadMessages from wiping SpyderResult
        setActiveChatId(res.chat_id)
        await loadChats()
      }
      const guardrailStatus = res.guardrail_status  // 'passed' | 'blocked' | 'error'
      setMessages(m => [
        ...m.filter(x => x.MessageID !== tempId),
        { MessageID: tempId + '_u', Role: 'user', Content: text },
        {
          MessageID: tempId + '_a',
          Role: 'assistant',
          Content: res.response,
          GuardrailStatus: guardrailStatus,
          BlockedBy: res.blocked_by,
          IntentResult: res.intent_result,
          SqlResult: res.sql_result,
          ValkyrieResult: res.valkyrie_result,
          SpyderResult: res.spyder_result,
        },
      ])
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send')
      setMessages(m => m.filter(x => x.MessageID !== tempId))
      setPrompt(text)
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const startNewChat = () => {
    setActiveChatId(null)
    setMessages([])
  }

  const handleDelete = async (e, id) => {
    e.stopPropagation()
    await deleteChat(id)
    if (activeChatId === id) { setActiveChatId(null); setMessages([]) }
    await loadChats()
    toast.success('Chat deleted')
  }

  // SGs available to show in selector — user's assigned ones only
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
          {/* Multi-select SG chips */}
          {visibleSGs.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginRight: 2 }}>
                Groups:
              </span>
              {visibleSGs.map(sg => {
                const selected = selectedSGIds.includes(sg.SecurityGroupID)
                return (
                  <button
                    key={sg.SecurityGroupID}
                    onClick={() => toggleSG(sg.SecurityGroupID)}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      padding: '3px 9px',
                      borderRadius: 'var(--radius-pill)',
                      fontSize: 11.5, fontWeight: 600,
                      border: `1px solid ${selected ? 'var(--brand-orange)' : 'var(--border-default)'}`,
                      background: selected ? 'var(--brand-orange-subtle)' : 'var(--bg-surface)',
                      color: selected ? 'var(--brand-orange)' : 'var(--text-secondary)',
                      cursor: 'pointer',
                      transition: 'all var(--transition-fast)',
                    }}
                    title={selected ? 'Click to deselect' : 'Click to select'}
                  >
                    {sg.SecurityGroupName}
                  </button>
                )
              })}
            </div>
          )}
          <button className="btn btn-primary btn-sm" onClick={startNewChat}>
            <Plus size={12} /> New Chat
          </button>
        </div>
      </div>

      {/* Chat shell */}
      <div className="chat-shell">
        <div className="chat-main">
          {/* Messages */}
          <div className="messages-area">
            {messages.length === 0 && (
              <div className="empty-state" style={{ flex: 1, justifyContent: 'center' }}>
                <MessageSquare size={40} />
                <div className="empty-state-title">Start a new conversation</div>
                <div className="empty-state-desc">Type a prompt below to interact with MANTHAN.AI. Your security profile and guardrails will be applied automatically.</div>
              </div>
            )}
            {messages.map((m, i) => {
              const isBlocked = m.GuardrailStatus === 'blocked'
              const isError = m.GuardrailStatus === 'error'
              const bubbleStyle = isBlocked
                ? { borderLeft: '3px solid var(--color-error, #ef4444)', background: 'var(--bg-error-subtle, #fef2f2)' }
                : isError
                  ? { borderLeft: '3px solid var(--color-warning, #f59e0b)', background: 'var(--bg-warning-subtle, #fffbeb)' }
                  : {}
              const spyderResult  = m.SpyderResult
              return (
                <div key={m.MessageID || i} className={`message ${m.Role}`}>
                  <div className="message-bubble" style={bubbleStyle}>
                    {isBlocked && m.BlockedBy && (
                      <div style={{ marginBottom: 6 }}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          fontSize: 10.5, fontWeight: 700, letterSpacing: '0.04em',
                          padding: '2px 8px', borderRadius: 'var(--radius-pill)',
                          background: 'var(--color-error, #ef4444)',
                          color: '#fff',
                        }}>
                          🚫 {m.BlockedBy}
                        </span>
                      </div>
                    )}
                    {spyderResult
                      ? <SpyderPanel result={spyderResult} />
                      : m.Content
                        ? <MarkdownText text={m.Content} />
                        : null
                    }
                  </div>
                </div>
              )
            })}
            {sending && (
              <div className="message assistant">
                <div className="message-bubble" style={{ opacity: 0.6 }}>
                  <span className="spinner" style={{ display: 'inline-block' }}>⟳</span> Thinking…
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className="chat-input-bar">
            <textarea
              className="chat-textarea"
              rows={2}
              placeholder="Type your prompt… (Enter to send, Shift+Enter for newline)"
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
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

        {/* Recent chats strip — below input */}
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
