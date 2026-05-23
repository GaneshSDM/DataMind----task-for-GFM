import { useState, useEffect, useRef } from 'react'
import { Plus, Trash2, Send, MessageSquare, ChevronDown, ChevronUp, X } from 'lucide-react'
import { getChats, getChatMessages, sendPrompt, deleteChat, getSecurityGroups, getMe } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'

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
    try { setMessages(await getChatMessages(id)) } catch {}
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
                <div className="empty-state-desc">Type a prompt below to interact with the SLM API. Your security profile and guardrails will be applied automatically.</div>
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
              const intents    = m.IntentResult?.intents || []
              const sqlResults = m.SqlResult?.sql_results || []
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
                    {m.Content}
                    {/* ── SQL Results ── */}
                    {sqlResults.filter(r => r.status === 'success').length > 0 && (
                      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                          Generated SQL ({sqlResults.filter(r => r.status === 'success').length})
                        </div>
                        {sqlResults.map(sr => {
                          if (sr.status !== 'success') return null
                          // Find matching intent for context
                          const matchIntent = intents.find(i => i.intent_id === sr.intent_id)
                          return (
                            <div key={sr.intent_id} style={{
                              background: 'var(--bg-inset, #f9fafb)',
                              border: '1px solid var(--border-default)',
                              borderRadius: 6,
                              overflow: 'hidden',
                            }}>
                              {/* SQL card header */}
                              <div style={{
                                display: 'flex', alignItems: 'center', gap: 8,
                                padding: '5px 10px',
                                background: 'var(--bg-subtle)',
                                borderBottom: '1px solid var(--border-default)',
                                fontSize: 10.5,
                              }}>
                                <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                                  Intent {sr.intent_id}
                                </span>
                                {matchIntent && (
                                  <span style={{ color: 'var(--text-tertiary)' }}>
                                    {matchIntent.domain}{matchIntent.sub_domain ? ` › ${matchIntent.sub_domain}` : ''}
                                  </span>
                                )}
                                {sr.tables_in_scope?.length > 0 && (
                                  <span style={{ fontFamily: 'monospace', color: 'var(--text-tertiary)', fontSize: 10 }}>
                                    {sr.tables_in_scope.join(', ')}
                                  </span>
                                )}
                                <span style={{ marginLeft: 'auto', color: 'var(--text-quaternary, #9ca3af)', fontSize: 10 }}>
                                  {sr.model_used}
                                </span>
                              </div>
                              {/* SQL code block */}
                              <pre style={{
                                margin: 0, padding: '8px 10px',
                                fontSize: 11, lineHeight: 1.5,
                                fontFamily: 'monospace',
                                color: 'var(--text-primary)',
                                overflowX: 'auto',
                                whiteSpace: 'pre',
                              }}>
                                {sr.generated_sql}
                              </pre>
                              {/* RLS / CLS badges */}
                              {(sr.rls_applied?.enabled || sr.cls_applied?.enabled) && (
                                <div style={{
                                  display: 'flex', gap: 6, padding: '4px 10px',
                                  borderTop: '1px solid var(--border-default)',
                                  background: 'var(--bg-subtle)',
                                }}>
                                  {sr.rls_applied?.enabled && (
                                    <span style={{
                                      fontSize: 10, fontWeight: 600, padding: '1px 6px',
                                      borderRadius: 'var(--radius-pill)',
                                      background: 'var(--color-warning-bg, #fffbeb)',
                                      color: 'var(--color-warning, #f59e0b)',
                                      border: '1px solid var(--color-warning, #f59e0b)',
                                    }}>
                                      🔒 RLS: {sr.rls_applied.policy_name || 'applied'}
                                    </span>
                                  )}
                                  {sr.cls_applied?.enabled && (
                                    <span style={{
                                      fontSize: 10, fontWeight: 600, padding: '1px 6px',
                                      borderRadius: 'var(--radius-pill)',
                                      background: 'var(--color-info-bg, #eff6ff)',
                                      color: 'var(--color-info, #3b82f6)',
                                      border: '1px solid var(--color-info, #3b82f6)',
                                    }}>
                                      🔑 CLS: {sr.cls_applied.columns_excluded?.join(', ') || 'applied'}
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}

                    {intents.length > 0 && (
                      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 5 }}>
                        {intents.map(intent => (
                          <div key={intent.intent_id} style={{
                            background: 'var(--bg-surface)',
                            border: '1px solid var(--border-default)',
                            borderRadius: 6,
                            padding: '6px 10px',
                            fontSize: 12,
                          }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                              <span style={{
                                fontSize: 10, fontWeight: 700, padding: '1px 6px',
                                borderRadius: 'var(--radius-pill)',
                                background: 'var(--brand-orange-subtle)',
                                color: 'var(--brand-orange)',
                              }}>
                                {intent.intent_types?.join(' · ') || 'Data'}
                              </span>
                              <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 600 }}>
                                {intent.domain}{intent.sub_domain ? ` › ${intent.sub_domain}` : ''}
                              </span>
                              <span style={{
                                fontSize: 10, fontWeight: 600,
                                color: intent.data_source === 'Structured' ? 'var(--color-success, #22c55e)'
                                  : intent.data_source === 'Unstructured' ? 'var(--color-info, #3b82f6)'
                                  : 'var(--color-warning, #f59e0b)',
                              }}>
                                {intent.data_source}
                              </span>
                            </div>
                            <div style={{ color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                              {intent.description}
                            </div>
                            {(intent.structured_table || intent.structured_view) && (
                              <div style={{ marginTop: 2, fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>
                                {intent.structured_table || intent.structured_view}
                                {intent.relevant_columns?.length > 0 && (
                                  <span style={{ color: 'var(--text-quaternary, #9ca3af)' }}>
                                    {' '}· {intent.relevant_columns.join(', ')}
                                  </span>
                                )}
                              </div>
                            )}
                            {intent.unstructured_source && (
                              <div style={{ marginTop: 2, fontSize: 10, color: 'var(--color-info, #3b82f6)', fontStyle: 'italic' }}>
                                📄 {intent.unstructured_source}
                              </div>
                            )}
                            {intent.retrieved_context?.length > 0 && (
                              <div style={{ marginTop: 6, borderTop: '1px solid var(--border-default)', paddingTop: 5 }}>
                                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                  Retrieved Context ({intent.retrieved_context.length})
                                </div>
                                {intent.retrieved_context.map((chunk, ci) => (
                                  <div key={ci} style={{
                                    fontSize: 11, color: 'var(--text-secondary)',
                                    padding: '4px 6px', marginBottom: 3,
                                    background: 'var(--bg-inset, #f9fafb)',
                                    borderRadius: 4,
                                    borderLeft: '2px solid var(--color-info, #3b82f6)',
                                  }}>
                                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                      {chunk.filename}
                                    </span>
                                    <span style={{ color: 'var(--text-tertiary)', fontSize: 10, marginLeft: 6 }}>
                                      sim {(chunk.similarity * 100).toFixed(0)}%
                                    </span>
                                    <div style={{ marginTop: 2, lineHeight: 1.4 }}>
                                      {chunk.chunk_text?.slice(0, 200)}{chunk.chunk_text?.length > 200 ? '…' : ''}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
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
