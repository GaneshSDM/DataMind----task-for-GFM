export default function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="topbar">
      <div>
        <div className="topbar-title">{title}</div>
        {subtitle && <div style={{ fontSize: 11.5, color: 'var(--text-tertiary)', marginTop: 1 }}>{subtitle}</div>}
      </div>
      {actions && <div className="topbar-actions">{actions}</div>}
    </div>
  )
}
