import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, RotateCcw, AlertTriangle } from 'lucide-react'
import { api, ApiError, imageSrc } from '../api'
import { useToast } from '../components/Toast'

// Sold history + one-click relist (spec §11): recurring NOS parts re-list in
// one click, reusing the original photos; pricing re-runs on relist.

const money = (v) => (v == null ? '—' : `$${Number(v).toFixed(2)}`)

export default function SoldScreen() {
  const navigate = useNavigate()
  const toast = useToast()
  const [q, setQ] = useState('')
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [relistingId, setRelistingId] = useState(null)

  useEffect(() => {
    let alive = true
    const t = setTimeout(() => {
      api
        .history(q)
        .then((r) => alive && (setItems(r.items), setError(null)))
        .catch((err) => alive && setError(err instanceof ApiError ? err.detail : 'Failed to load history.'))
    }, q ? 250 : 0)
    return () => {
      alive = false
      clearTimeout(t)
    }
  }, [q])

  const doRelist = async (row) => {
    if (relistingId) return
    setRelistingId(row.id)
    try {
      const listing = await api.relist(row.id)
      toast.success('Relisted as a fresh draft — photos reused, price re-run.')
      navigate(`/review/${listing.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Relist failed.')
      setRelistingId(null)
    }
  }

  return (
    <div className="screen sold-screen">
      <div className="dash-head">
        <div className="dash-title">Sold <span className="brand-accent">History</span></div>
        <span className="dash-updated">{items ? `${items.length} shown` : ''}</span>
      </div>

      <label className="field search-field">
        <span className="field-label-row"><span><Search size={12} /> Search part number or title</span></span>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. 3G2-83312-00, carburetor"
        />
      </label>

      {error && (
        <div className="banner banner-error"><AlertTriangle size={16} /> {error}</div>
      )}

      {items === null ? (
        <div className="skeleton" style={{ height: 180 }} />
      ) : items.length === 0 ? (
        <div className="empty-state">
          No sales archived yet. Sales land here automatically once eBay is
          connected — or use "Mark sold" on a live listing.
        </div>
      ) : (
        <div className="chart-card table-scroll">
          <table className="queue-table">
            <thead>
              <tr><th></th><th>Sold listing</th><th>Part #</th><th>Sold for</th><th>Date</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td>
                    {row.thumb_image_id ? (
                      <span className="thumb" style={{ width: 40, height: 40, display: 'inline-block' }}>
                        <img src={imageSrc(row.thumb_image_id)} alt="" loading="lazy" />
                      </span>
                    ) : null}
                  </td>
                  <td className="queue-title-cell" title={row.title || ''}>{row.title || '(untitled)'}</td>
                  <td className="mono">{row.part_number || '—'}</td>
                  <td className="mono">{money(row.sold_price)}</td>
                  <td className="card-date">{row.sold_date ? new Date(row.sold_date).toLocaleDateString() : '—'}</td>
                  <td>
                    <button
                      className="btn-primary btn-sm"
                      disabled={relistingId === row.id}
                      onClick={() => doRelist(row)}
                    >
                      <RotateCcw size={14} /> {relistingId === row.id ? 'Relisting…' : 'Relist'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
