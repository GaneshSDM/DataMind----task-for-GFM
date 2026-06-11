import { useState } from 'react'
import { Link, useLocation, Outlet, Navigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import {
  MessageSquare, Database, Globe, Layers, GitBranch,
  Lock, Shield, Users, LogOut,
  Sliders, Server, Key, Moon, Sun, Menu, Cpu, UserCircle, Bot, Plug, Wand2, ArrowLeftRight
} from 'lucide-react'

const NAV = [
  { section: 'Main', items: [
    { path: '/chats',   label: 'Chats',           icon: MessageSquare },
    { path: '/profile', label: 'My Profile',       icon: UserCircle },
    { path: '/users',   label: 'User Management',  icon: Users,       adminOnly: true },
  ]},
  { section: 'Data', items: [
    { path: '/db-connections', label: 'Database Connections', icon: Database, adminOnly: true },
    { path: '/geographies', label: 'Geography', icon: Globe, adminOnly: true },
    { path: '/domains', label: 'Domains', icon: Layers, adminOnly: true },
    { path: '/subdomains', label: 'Sub-Domains', icon: GitBranch, adminOnly: true },
  ]},
  { section: 'Security', items: [
    { path: '/rls', label: 'Row Level Security', icon: Lock, adminOnly: true },
    { path: '/cls', label: 'Column Level Security', icon: Key, adminOnly: true },
    { path: '/security-groups', label: 'Security Groups', icon: Shield, adminOnly: true },
    { path: '/guardrails', label: 'Guard Rails', icon: Sliders, adminOnly: true },
  ]},
  { section: 'Admin', items: [
    { path: '/data-pipeline',     label: 'Data Pipeline',        icon: ArrowLeftRight, adminOnly: true },
    { path: '/slm-config',         label: 'LLM API Config',       icon: Server,     adminOnly: true },
    { path: '/agent-management',   label: 'Agent Management',     icon: Bot,        adminOnly: true },
    { path: '/app-mapping',        label: 'App User Mapping',     icon: Plug,       adminOnly: true },
    { path: '/agent-skills',       label: 'Agent Skills',         icon: Wand2,      adminOnly: true },
    { path: '/rag-pipelines',      label: 'Manage RAG Pipelines', icon: Cpu,        adminOnly: true },
    { path: '/rag-categories',     label: 'RAG Categories',       icon: Layers,     adminOnly: true },
    { path: '/rag-sub-categories', label: 'RAG Sub-Categories',   icon: GitBranch,  adminOnly: true },
  ]},
]

export default function AppShell() {
  const { user, logout, isAdmin, theme, toggleTheme } = useAuth()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  if (!user) return <Navigate to="/login" replace />

  const initials = user.name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()

  return (
    <div className="app-shell">
      <aside className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`}>
        {/* Logo / header row */}
        <div className="sidebar-logo">
          {!collapsed && (
            <img
              src="/manthanlogo.png"
              alt="Manthan"
              style={{ height: 44, maxWidth: 160, objectFit: 'contain', flex: 1, minWidth: 0 }}
            />
          )}
          <button
            className="btn btn-ghost btn-icon btn-sm"
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={collapsed ? { margin: '0 auto' } : {}}
          >
            <Menu size={15} />
          </button>
        </div>

        {/* Nav — icon-only when collapsed */}
        <nav className="sidebar-nav">
          {NAV.map(group => {
            const visible = group.items.filter(i => !i.adminOnly || isAdmin)
            if (!visible.length) return null
            return (
              <div key={group.section}>
                {!collapsed && <div className="nav-section-label">{group.section}</div>}
                {visible.map(item => {
                  const Icon = item.icon
                  const active = location.pathname.startsWith(item.path)
                  return (
                    <Link key={item.path} to={item.path} title={item.label}>
                      <button className={`nav-item ${active ? 'active' : ''} ${collapsed ? 'nav-item--collapsed' : ''}`}>
                        <Icon size={14} className="nav-icon" />
                        {!collapsed && item.label}
                      </button>
                    </Link>
                  )
                })}
              </div>
            )
          })}
        </nav>

        {/* User footer — hidden when collapsed */}
        {!collapsed && (
          <div className="sidebar-user">
            <div className="user-avatar">{initials}</div>
            <div className="user-info" style={{ flex: 1, minWidth: 0 }}>
              <div className="user-name" style={{ fontWeight: 700, fontSize: 12.5, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.name}
              </div>
              <div className="user-role" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{user.role}</div>
            </div>
            <button className="btn btn-ghost btn-icon btn-sm" onClick={toggleTheme} title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>
              {theme === 'light' ? <Moon size={13} /> : <Sun size={13} />}
            </button>
            <button className="btn btn-ghost btn-icon btn-sm" onClick={logout} title="Sign out">
              <LogOut size={13} />
            </button>
          </div>
        )}
      </aside>


<div className="main-area">
        <Outlet />
      </div>
    </div>
  )
}
