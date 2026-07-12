import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { X, AlertTriangle, CheckCircle2, Info } from 'lucide-react'

const ToastContext = createContext(null)

let idCounter = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef(new Map())

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const push = useCallback(
    (message, type = 'info', ttl = 5000) => {
      const id = ++idCounter
      setToasts((list) => [...list, { id, message, type }])
      if (ttl > 0) {
        const timer = setTimeout(() => dismiss(id), ttl)
        timers.current.set(id, timer)
      }
      return id
    },
    [dismiss],
  )

  const value = {
    toast: push,
    success: (m, ttl) => push(m, 'success', ttl),
    error: (m, ttl) => push(m, 'error', ttl ?? 8000),
    info: (m, ttl) => push(m, 'info', ttl),
    dismiss,
  }

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="region" aria-label="Notifications">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`} role="alert">
            <span className="toast-icon">
              {t.type === 'error' && <AlertTriangle size={18} />}
              {t.type === 'success' && <CheckCircle2 size={18} />}
              {t.type === 'info' && <Info size={18} />}
            </span>
            <span className="toast-msg">{t.message}</span>
            <button className="toast-close" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <X size={16} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
