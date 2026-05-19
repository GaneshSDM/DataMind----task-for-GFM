import { X } from 'lucide-react'

export default function Modal({ title, onClose, children, footer, size = 'default' }) {
  const maxW = size === 'lg' ? 680 : size === 'sm' ? 380 : 520

  const handleOverlayClick = e => {
    if (e.target === e.currentTarget) onClose()
  }

  // Prevent Enter key from closing the modal unexpectedly
  const handleKeyDown = e => {
    if (e.key === 'Escape') onClose()
    if (e.key === 'Enter') e.stopPropagation()
  }

  return (
    <div className="modal-overlay" onClick={handleOverlayClick} onKeyDown={handleKeyDown}>
      <div
        className="modal"
        style={{ maxWidth: maxW }}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <span className="modal-title">{title}</span>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} type="button">
            <X size={14} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}
