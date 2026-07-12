import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, Package, AlertTriangle } from 'lucide-react'
import { api, ApiError, imageSrc } from '../api'
import { useToast } from '../components/Toast'
import StatusBadge from '../components/StatusBadge'

const FILTERS = [
  { key: 'pending_review', label: 'Review' },
  { key: 'draft', label: 'Draft' },
  { key: 'listed', label: 'Listed' },
  { key: 'error', label: 'Error' },
  { key: 'all', label: 'All' },
]

function primaryImage(listing) {
  const imgs = listing.images || []
  const primary = imgs.find((i) => i.is_primary) || imgs[0]
  return primary ? imageSrc(primary.id) : null
}

function formatPrice(p) {
  if (p == null) return null
  const n = Number(p)
  return Number.isFinite(n) ? `$${n.toFixed(2)}` : null
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function DraftsScreen() {
  const navigate = useNavigate()
  const toast = useToast()
  const [filter, setFilter] = useState('pending_review')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(
    async (status) => {
      setLoading(true)
      setError(null)
      try {
        const data = await api.getListings(status)
        setItems(Array.isArray(data?.items) ? data.items : [])
      } catch (err) {
        const msg = err instanceof ApiError ? err.detail : 'Failed to load listings.'
        setError(msg)
        setItems([])
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    load(filter)
  }, [filter, load])

  return (
    <div className="screen drafts-screen">
      <div className="drafts-toolbar">
        <div className="chips" role="tablist" aria-label="Filter listings">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={filter === f.key}
              className={`chip ${filter === f.key ? 'chip-active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button className="btn-icon" title="Refresh" onClick={() => load(filter)} disabled={loading}>
          <RefreshCw size={18} className={loading ? 'spin' : ''} />
        </button>
      </div>

      {error && (
        <div className="banner banner-error">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {loading && items.length === 0 && (
        <div className="card-list">
          {[0, 1, 2].map((i) => (
            <div className="listing-card skeleton" key={i}>
              <div className="thumb-sq shimmer" />
              <div className="card-body">
                <div className="line shimmer" />
                <div className="line short shimmer" />
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="empty-state">
          <Package size={40} />
          <p>No listings in this view.</p>
          <button className="btn-secondary" onClick={() => navigate('/')}>
            Capture a part
          </button>
        </div>
      )}

      <div className="card-list">
        {items.map((listing) => {
          const img = primaryImage(listing)
          const price = formatPrice(listing.price)
          const identifying = listing.status === 'draft' && !listing.title
          return (
            <button
              key={listing.id}
              className="listing-card"
              onClick={() => navigate(`/review/${listing.id}`)}
            >
              <div className="thumb-sq">
                {img ? (
                  <img src={img} alt="" loading="lazy" />
                ) : (
                  <div className="thumb-placeholder">
                    <Package size={22} />
                  </div>
                )}
              </div>
              <div className="card-body">
                <div className="card-title">
                  {listing.title || (identifying ? '(identifying…)' : '(untitled draft)')}
                </div>
                <div className="card-meta">
                  <StatusBadge status={listing.status} />
                  {price && <span className="card-price">{price}</span>}
                  <span className="card-date">{formatDate(listing.created_at)}</span>
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
