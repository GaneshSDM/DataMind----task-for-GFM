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
      setMessages(m => [
        ...m.filter(x => x.MessageID !== tempId),
        { MessageID: tempId + '_u', Role: 'user', Content: text },
        { MessageID: tempId + '_a', Role: 'assistant', Content: res.response },
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
            {messages.map((m, i) => (
              <div key={m.MessageID || i} className={`message ${m.Role}`}>
                <div className="message-bubble">{m.Content}</div>
              </div>
            ))}
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
