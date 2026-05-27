import { useState, useMemo } from 'react'
import { Plus, Trash2, Wand2, Save, X } from 'lucide-react'
import { useSkills } from '../contexts/SkillsContext'
import toast from 'react-hot-toast'

// ── Config ─────────────────────────────────────────────────────────────────────
const PG_TYPES = [
  'text', 'varchar', 'char',
  'integer', 'bigint', 'smallint',
  'numeric', 'decimal', 'float', 'double precision', 'real',
  'boolean',
  'date', 'timestamp', 'timestamptz', 'time', 'timetz',
  'uuid',
  'json', 'jsonb',
  'interval', 'array', 'bytea',
]

const DOMAINS = ['Sales', 'Finance', 'HR', 'Operations', 'Marketing', 'Supply Chain', 'Other']

const TYPE_STYLE = {
  view:     { label: 'View',     bg: '#eff6ff', color: '#3b82f6', border: '#93c5fd' },
  template: { label: 'Template', bg: '#f0fdf4', color: '#16a34a', border: '#86efac' },
}

// ── Shared style constants ─────────────────────────────────────────────────────
const LBL = { fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 5 }
const INPUT = {
  width: '100%', boxSizing: 'border-box',
  padding: '7px 10px', borderRadius: 6,
  border: '1px solid var(--border-default)',
  background: 'var(--bg-surface)', color: 'var(--text-primary)',
  fontSize: 12.5, outline: 'none',
}
const TH = {
  padding: '7px 10px', textAlign: 'left', fontWeight: 600,
  color: 'var(--text-secondary)', fontSize: 10.5, whiteSpace: 'nowrap',
  borderBottom: '1px solid var(--border-default)',
  background: 'var(--bg-subtle)',
}

// ── Sub-components ─────────────────────────────────────────────────────────────
function TypeBadge({ type }) {
  const s = TYPE_STYLE[type] || { label: type, bg: '#f1f5f9', color: '#475569', border: '#e2e8f0' }
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 12,
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
    }}>
      {s.label}
    </span>
  )
}

function InvocationPreview({ name, parameters }) {
  if (!name) return null
  const params = parameters.filter(p => p.name)
  const preview = `@${name}${params.map(p => ` ${p.name}=<${p.example || p.name}>`).join('')}`
  return (
    <div style={{
      background: 'var(--bg-subtle)', border: '1px solid var(--border-default)',
      borderRadius: 6, padding: '12px 14px',
    }}>
      <div style={{
        fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)',
        textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6,
      }}>
        Chat Invocation — type this in chat
      </div>
      <code style={{
        fontSize: 12.5, color: 'var(--brand-blue, #1A4FA0)',
        fontFamily: 'monospace', wordBreak: 'break-all',
      }}>
        {preview}
      </code>
      <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>
        Type <strong>@</strong> in chat to see all active skills. LLM extracts parameter values from natural language.
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function AgentSkills() {
  const { skills, addSkill, updateSkill, deleteSkill, toggleSkill } = useSkills()

  const [selectedId, setSelectedId] = useState(() => skills[0]?.id ?? null)
  const [draft, setDraft]           = useState(() => skills[0] ? JSON.parse(JSON.stringify(skills[0])) : null)
  const [dirty, setDirty]           = useState(false)
  const [isNew, setIsNew]           = useState(false)
  const [filter, setFilter]         = useState('all')
  const [search, setSearch]         = useState('')

  const filtered = useMemo(() => skills.filter(s => {
    if (filter !== 'all' && s.type !== filter) return false
    const q = search.toLowerCase()
    if (q && !s.name.includes(q) && !s.description.toLowerCase().includes(q)) return false
    return true
  }), [skills, filter, search])

  // ── Selection ──────────────────────────────────────────────────────────────
  const selectSkill = s => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    setSelectedId(s.id)
    setDraft(JSON.parse(JSON.stringify(s)))
    setDirty(false)
    setIsNew(false)
  }

  const handleNew = () => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    setSelectedId(null)
    setDraft({ id: null, name: '', type: 'template', description: '', domain: 'Sales', sql: '', parameters: [], is_active: true })
    setDirty(false)
    setIsNew(true)
  }

  // ── Draft mutations ────────────────────────────────────────────────────────
  const setField = (key, val) => { setDraft(d => ({ ...d, [key]: val })); setDirty(true) }

  // ── Save / Discard ─────────────────────────────────────────────────────────
  const handleSave = () => {
    if (!draft.name.trim())               return toast.error('Skill name required')
    if (!/^[a-z0-9_]+$/.test(draft.name)) return toast.error('Name: lowercase letters, numbers, underscores only')
    if (!draft.sql.trim())                return toast.error('SQL required')

    if (isNew) {
      const newId = addSkill(draft)
      setSelectedId(newId)
      setIsNew(false)
      toast.success('Skill created')
    } else {
      updateSkill(selectedId, draft)
      toast.success('Skill saved')
    }
    setDirty(false)
  }

  const handleDiscard = () => {
    if (isNew) {
      const first = skills[0]
      setSelectedId(first?.id ?? null)
      setDraft(first ? JSON.parse(JSON.stringify(first)) : null)
      setIsNew(false)
    } else {
      const orig = skills.find(s => s.id === selectedId)
      if (orig) setDraft(JSON.parse(JSON.stringify(orig)))
    }
    setDirty(false)
  }

  const handleDelete = id => {
    const s = skills.find(x => x.id === id)
    if (!window.confirm(`Delete @${s?.name}? This cannot be undone.`)) return
    deleteSkill(id)
    const remaining = skills.filter(x => x.id !== id)
    const next = remaining[0] ?? null
    setSelectedId(next?.id ?? null)
    setDraft(next ? JSON.parse(JSON.stringify(next)) : null)
    setDirty(false)
    setIsNew(false)
    toast.success('Skill deleted')
  }

  // ── Parameter helpers ──────────────────────────────────────────────────────
  const addParam = () => {
    setDraft(d => ({
      ...d,
      parameters: [...d.parameters, { id: `p_${Date.now()}`, name: '', label: '', type: 'text', required: true, example: '' }],
    }))
    setDirty(true)
  }

  const setParam = (idx, key, val) => {
    setDraft(d => {
      const ps = [...d.parameters]
      ps[idx] = { ...ps[idx], [key]: val }
      return { ...d, parameters: ps }
    })
    setDirty(true)
  }

  const removeParam = idx => {
    setDraft(d => ({ ...d, parameters: d.parameters.filter((_, i) => i !== idx) }))
    setDirty(true)
  }

  const countByType = t => skills.filter(s => s.type === t).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div style={{
        height: 52, minHeight: 52, background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex', alignItems: 'center',
        padding: '0 16px', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Wand2 size={15} style={{ color: 'var(--brand-blue, #1A4FA0)' }} />
          <span style={{ fontSize: 14, fontWeight: 700 }}>Custom Agent Skills</span>
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 12,
            background: '#fff3cd', color: '#856404', border: '1px solid #ffc107',
          }}>
            UI Preview — Backend Pending
          </span>
        </div>
      </div>

      {/* ── Body ──────────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>

        {/* ── Skill selector bar ───────────────────────────────────────────────── */}
        <div style={{
          padding: '8px 16px', flexShrink: 0,
          borderBottom: '1px solid var(--border-default)',
          background: 'var(--bg-surface)',
          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
        }}>
          {/* Search */}
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search skills…"
            style={{ ...INPUT, width: 180, flexShrink: 0 }}
          />

          {/* Filter pills */}
          <div style={{ display: 'flex', gap: 4 }}>
            {[
              { key: 'all',      label: `All (${skills.length})` },
              { key: 'view',     label: `View (${countByType('view')})` },
              { key: 'template', label: `Template (${countByType('template')})` },
            ].map(f => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                style={{
                  padding: '3px 10px', fontSize: 9.5, fontWeight: 600,
                  borderRadius: 12, cursor: 'pointer', whiteSpace: 'nowrap',
                  border: `1px solid ${filter === f.key ? 'var(--brand-orange, #F47920)' : 'var(--border-default)'}`,
                  background: filter === f.key ? 'var(--brand-orange-subtle, #fff7ed)' : 'transparent',
                  color: filter === f.key ? 'var(--brand-orange, #F47920)' : 'var(--text-tertiary)',
                }}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Skill dropdown */}
          {filtered.length > 0 && (
            <select
              value={isNew ? '' : (selectedId || '')}
              onChange={e => {
                const s = skills.find(x => x.id === e.target.value)
                if (s) selectSkill(s)
              }}
              style={{ ...INPUT, minWidth: 200, maxWidth: 320, flex: '1 1 auto' }}
            >
              {isNew && <option value="">— New Skill —</option>}
              {filtered.map(s => (
                <option key={s.id} value={s.id}>
                  @{s.name || 'untitled'} · {TYPE_STYLE[s.type]?.label || s.type} · {s.is_active ? 'Active' : 'Inactive'}
                </option>
              ))}
            </select>
          )}
          {filtered.length === 0 && !isNew && (
            <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)', flex: 1 }}>No skills match filter</span>
          )}

          <button className="btn btn-primary btn-sm" onClick={handleNew} style={{ marginLeft: 'auto', flexShrink: 0 }}>
            <Plus size={12} /> New Skill
          </button>
        </div>

        {draft ? (
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>

            {/* Panel header */}
            <div style={{
              padding: '12px 20px', borderBottom: '1px solid var(--border-default)',
              background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--brand-blue, #1A4FA0)', fontFamily: 'monospace' }}>
                @{draft.name || 'new_skill'}
              </span>
              {!isNew && <TypeBadge type={draft.type} />}
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                {!isNew && (
                  <button
                    onClick={() => { toggleSkill(selectedId); setDraft(d => ({ ...d, is_active: !d.is_active })) }}
                    style={{
                      fontSize: 10.5, fontWeight: 600, padding: '3px 10px', borderRadius: 12, cursor: 'pointer',
                      border: `1px solid ${draft.is_active ? '#86efac' : 'var(--border-default)'}`,
                      background: draft.is_active ? '#f0fdf4' : 'var(--bg-subtle)',
                      color: draft.is_active ? '#16a34a' : 'var(--text-tertiary)',
                    }}
                  >
                    {draft.is_active ? '● Active' : '○ Inactive'}
                  </button>
                )}
                {!isNew && (
                  <button
                    className="btn btn-sm"
                    style={{ color: '#ef4444', borderColor: '#fca5a5' }}
                    onClick={() => handleDelete(selectedId)}
                    title="Delete skill"
                  >
                    <Trash2 size={11} />
                  </button>
                )}
              </div>
            </div>

            {/* Form */}
            <div style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 20 }}>

              {/* Name + Type + Domain */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 150px 180px', gap: 14 }}>
                <div>
                  <label style={LBL}>Skill Name (slug) *</label>
                  <div style={{ position: 'relative' }}>
                    <span style={{
                      position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
                      fontSize: 14, fontWeight: 700, color: 'var(--brand-blue, #1A4FA0)', fontFamily: 'monospace', userSelect: 'none',
                    }}>@</span>
                    <input
                      value={draft.name}
                      onChange={e => setField('name', e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                      placeholder="skill_name"
                      style={{ ...INPUT, paddingLeft: 22, fontFamily: 'monospace' }}
                    />
                  </div>
                  <div style={{ fontSize: 9.5, color: 'var(--text-tertiary)', marginTop: 3 }}>
                    Lowercase · numbers · underscores only
                  </div>
                </div>
                <div>
                  <label style={LBL}>Type</label>
                  <select value={draft.type} onChange={e => setField('type', e.target.value)} style={INPUT}>
                    <option value="template">Template</option>
                    <option value="view">View</option>
                  </select>
                </div>
                <div>
                  <label style={LBL}>Domain</label>
                  <select value={draft.domain} onChange={e => setField('domain', e.target.value)} style={INPUT}>
                    {DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
              </div>

              {/* Description */}
              <div>
                <label style={LBL}>Description — shown in @skill hints, used by LLM to decide when to invoke</label>
                <input
                  value={draft.description}
                  onChange={e => setField('description', e.target.value)}
                  placeholder="What does this skill do? Be specific about when it should be triggered."
                  style={INPUT}
                />
              </div>

              {/* SQL */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <label style={{ ...LBL, marginBottom: 0 }}>
                    {draft.type === 'view' ? 'View Definition SQL' : 'SQL Template'}
                    <span style={{ fontWeight: 400, marginLeft: 6, color: 'var(--text-tertiary)' }}>
                      — any dialect (Postgres / Oracle / MySQL)
                    </span>
                  </label>
                  {draft.type === 'template' && (
                    <code style={{
                      fontSize: 10, color: '#9333ea', background: '#faf5ff',
                      padding: '2px 8px', borderRadius: 4, border: '1px solid #d8b4fe',
                    }}>
                      {'{{param_name}} for substitutions'}
                    </code>
                  )}
                </div>
                <textarea
                  value={draft.sql}
                  onChange={e => setField('sql', e.target.value)}
                  placeholder={draft.type === 'view'
                    ? `CREATE OR REPLACE VIEW schema.view_name AS\nSELECT column1, column2\nFROM table\nGROUP BY 1, 2`
                    : `SELECT *\nFROM table\nWHERE column = '{{param_name}}'\n  AND date >= '{{start_date}}'`
                  }
                  rows={13}
                  style={{ ...INPUT, fontFamily: 'monospace', fontSize: 12, resize: 'vertical', lineHeight: 1.65 }}
                />
              </div>

              {/* Parameters — Template only */}
              {draft.type === 'template' && (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                    <label style={{ ...LBL, marginBottom: 0 }}>
                      Parameters ({draft.parameters.length})
                    </label>
                    <button className="btn btn-sm" onClick={addParam}>
                      <Plus size={11} /> Add Parameter
                    </button>
                  </div>

                  {draft.parameters.length === 0 ? (
                    <div style={{
                      padding: '20px', textAlign: 'center',
                      border: '1px dashed var(--border-default)', borderRadius: 8,
                      color: 'var(--text-tertiary)', fontSize: 12,
                    }}>
                      No parameters defined. Use <code style={{ fontFamily: 'monospace', color: '#9333ea' }}>{'{{param}}'}</code> in SQL above, then add parameter rows here.
                    </div>
                  ) : (
                    <div style={{ border: '1px solid var(--border-default)', borderRadius: 8, overflow: 'hidden' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr>
                            <th style={TH}>Param Name</th>
                            <th style={TH}>Display Label</th>
                            <th style={TH}>PG Type</th>
                            <th style={{ ...TH, textAlign: 'center' }}>Required</th>
                            <th style={TH}>Example Value</th>
                            <th style={TH}></th>
                          </tr>
                        </thead>
                        <tbody>
                          {draft.parameters.map((p, idx) => (
                            <tr key={p.id} style={{ borderTop: '1px solid var(--border-default)' }}>
                              <td style={{ padding: '6px 8px' }}>
                                <input
                                  value={p.name}
                                  onChange={e => setParam(idx, 'name', e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                                  placeholder="param_name"
                                  style={{ ...INPUT, fontSize: 11.5, padding: '4px 7px', fontFamily: 'monospace' }}
                                />
                              </td>
                              <td style={{ padding: '6px 8px' }}>
                                <input
                                  value={p.label}
                                  onChange={e => setParam(idx, 'label', e.target.value)}
                                  placeholder="Display Label"
                                  style={{ ...INPUT, fontSize: 11.5, padding: '4px 7px' }}
                                />
                              </td>
                              <td style={{ padding: '6px 8px' }}>
                                <select
                                  value={p.type}
                                  onChange={e => setParam(idx, 'type', e.target.value)}
                                  style={{ ...INPUT, fontSize: 11.5, padding: '4px 7px' }}
                                >
                                  {PG_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                                </select>
                              </td>
                              <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                                <input
                                  type="checkbox"
                                  checked={!!p.required}
                                  onChange={e => setParam(idx, 'required', e.target.checked)}
                                  style={{ accentColor: '#1A4FA0', width: 14, height: 14, cursor: 'pointer' }}
                                />
                              </td>
                              <td style={{ padding: '6px 8px' }}>
                                <input
                                  value={p.example}
                                  onChange={e => setParam(idx, 'example', e.target.value)}
                                  placeholder="e.g. India"
                                  style={{ ...INPUT, fontSize: 11.5, padding: '4px 7px' }}
                                />
                              </td>
                              <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                                <button
                                  onClick={() => removeParam(idx)}
                                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 2, display: 'flex' }}
                                  title="Remove parameter"
                                >
                                  <X size={13} />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Invocation preview */}
              <InvocationPreview
                name={draft.name}
                parameters={draft.type === 'template' ? draft.parameters : []}
              />

              {/* Save / Discard */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingBottom: 28 }}>
                <button
                  className="btn btn-primary"
                  onClick={handleSave}
                  disabled={!dirty}
                  style={{ opacity: dirty ? 1 : 0.45 }}
                >
                  <Save size={13} /> {isNew ? 'Create Skill' : 'Save Changes'}
                </button>
                <button
                  className="btn"
                  onClick={handleDiscard}
                  disabled={!dirty}
                  style={{ opacity: dirty ? 1 : 0.45 }}
                >
                  Discard
                </button>
                {dirty && (
                  <span style={{ fontSize: 11, color: '#f59e0b', fontWeight: 600 }}>● Unsaved changes</span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 10, color: 'var(--text-tertiary)' }}>
            <Wand2 size={32} style={{ opacity: 0.3 }} />
            <div style={{ fontSize: 13 }}>Select a skill or click "+ New Skill"</div>
          </div>
        )}
      </div>
    </div>
  )
}
