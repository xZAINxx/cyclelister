import { useEffect, useState } from 'react'
import { api } from '../api'

/**
 * eBay connection pill. Derived states:
 *  - grey  "eBay: not configured"        -> configured === false
 *  - amber "eBay: sandbox – not connected"-> configured, not connected
 *  - green "eBay: connected"              -> connected === true
 *  - grey  "eBay: unknown"               -> fetch failed (backend down)
 * Never throws — a failed status check must not crash the header.
 */
export default function EbayStatusPill() {
  const [status, setStatus] = useState(null) // stays null when the fetch fails

  useEffect(() => {
    let alive = true
    api
      .ebayStatus()
      .then((s) => {
        if (alive) setStatus(s)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  let tone = 'grey'
  let label = 'eBay: unknown'

  if (status) {
    if (!status.configured) {
      tone = 'grey'
      label = 'eBay: not configured'
    } else if (!status.connected) {
      tone = 'amber'
      label = `eBay: ${status.environment || 'sandbox'} – not connected`
    } else {
      tone = 'green'
      label = 'eBay: connected'
    }
  }

  return (
    <span className={`pill pill-${tone}`} title={label}>
      <span className="pill-dot" aria-hidden="true" />
      {label}
    </span>
  )
}
