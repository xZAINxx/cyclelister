import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, AlertTriangle } from 'lucide-react'
import { api, ApiError, imageSrc } from '../api'
import StatusBadge from '../components/StatusBadge'

const money = (v) => (v == null ? '—' : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`)

function BarChart({ points, valueKey, color = 'var(--yellow)' }) {
  const max = Math.max(1, ...points.map((p) => p[valueKey]))
  const w = 440
  const h = 120
  const bw = w / points.length
  return (
    <svg viewBox={`0 0 ${w} ${h + 18}`} className="chart-svg" role="img">
      {points.map((p, i) => {
        const bh = Math.round((p[valueKey] / max) * h)
        return (
          <g key={p.week}>
            <rect
              x={i * bw + 6}
              y={h - bh}
              width={bw - 12}
              height={Math.max(bh, 2)}
              rx="2"
              fill={p[valueKey] ? color : 'var(--line)'}
            />
            <text x={i * bw + bw / 2} y={h + 13} textAnchor="middle" fontSize="9" fill="var(--smoke)" fontFamily="var(--font-mono)">
              {p.week.slice(5)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function LineChart({ points, valueKey, color = 'var(--green)' }) {
  const max = Math.max(1, ...points.map((p) => p[valueKey]))
  const w = 440
  const h = 120
  const step = w / Math.max(points.length - 1, 1)
  const coords = points.map((p, i) => `${i * step},${h - (p[valueKey] / max) * (h - 8)}`)
  return (
    <svg viewBox={`0 0 ${w} ${h + 18}`} className="chart-svg" role="img">
      <polyline points={coords.join(' ')} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" />
      {points.map((p, i) => (
        <text key={p.week} x={i * step} y={h + 13} textAnchor="middle" fontSize="9" fill="var(--smoke)" fontFamily="var(--font-mono)">
          {p.week.slice(5)}
        </text>
      ))}
    </svg>
  )
}

export default function DashboardScreen() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [queue, setQueue] = useState([])
  const [error, setError] = useState(null)
  const [loadedAt, setLoadedAt] = useState(null)

  const load = async () => {
    setError(null)
    try {
      const [summary, listings] = await Promise.all([
        api.analyticsSummary(),
        api.getListings('pending_review'),
      ])
      setData(summary)
      setQueue(listings.items.slice(0, 8))
      setLoadedAt(new Date())
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load analytics.')
    }
  }

  useEffect(() => {
    load()
  }, [])

  if (error) {
    return (
      <div className="screen">
        <div className="banner banner-error"><AlertTriangle size={16} /> {error}</div>
        <button className="btn-secondary" onClick={load}>Retry</button>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="screen">
        <div className="skeleton" style={{ height: 90, marginBottom: 10 }} />
        <div className="skeleton" style={{ height: 220 }} />
      </div>
    )
  }

  const { operations: ops, sales, ai, inventory: inv } = data
  return (
    <div className="screen dashboard-screen">
      <div className="dash-head">
        <div className="dash-title">Pit <span className="brand-accent">Wall</span></div>
        <span className="dash-updated">
          {loadedAt && `updated ${loadedAt.toLocaleTimeString()}`}{' '}
          <button className="btn-icon btn-sm" onClick={load} aria-label="Refresh" style={{ verticalAlign: 'middle' }}>
            <RefreshCw size={13} />
          </button>
        </span>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">Listings · 7 days</div>
          <div className="stat-value">{ops.created_7d}</div>
          <div className="stat-sub">{ops.created_30d} in 30 days · {ops.published_7d} published</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Revenue · 30 days</div>
          <div className="stat-value">{money(sales.revenue_30d)}</div>
          <div className="stat-sub">
            {sales.connected ? `${sales.sales_30d} sales · avg ${money(sales.avg_price)}` : <span className="warn">populates when eBay connects</span>}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">AI cost / listing</div>
          <div className="stat-value">{ai.cost_per_listing_usd != null ? money(ai.cost_per_listing_usd) : '—'}</div>
          <div className="stat-sub">
            {money(ai.est_cost_total_usd)} total · confidence {pct(ai.avg_confidence)} · review rate {pct(ai.review_rate)}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Needs review</div>
          <div className="stat-value">{ops.pending_review}</div>
          <div className="stat-sub">{ops.draft} drafts · {ops.error} errors</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Catalog</div>
          <div className="stat-value">{inv.parts_total.toLocaleString()}<span className="unit"> parts</span></div>
          <div className="stat-sub">fitment coverage {pct(inv.fitment_coverage)} · {inv.fitment_rows} rows</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Inventory health</div>
          <div className="stat-value">{inv.active_listings}<span className="unit"> live</span></div>
          <div className="stat-sub">
            {inv.stale_listings > 0
              ? <span className="warn">{inv.stale_listings} stale (&gt;{inv.stale_threshold_days}d)</span>
              : `no stale listings (>${inv.stale_threshold_days}d)`}
          </div>
        </div>
      </div>

      <div className="dash-cols">
        <div className="chart-card">
          <div className="chart-title"><h3>Listings per week</h3><span className="chart-legend">created</span></div>
          {ops.by_week.some((p) => p.created) ? (
            <BarChart points={ops.by_week} valueKey="created" />
          ) : (
            <div className="chart-empty">No listings yet — capture your first part.</div>
          )}
        </div>
        <div className="chart-card">
          <div className="chart-title"><h3>Revenue per week</h3><span className="chart-legend">USD</span></div>
          {sales.by_week.some((p) => p.revenue) ? (
            <LineChart points={sales.by_week} valueKey="revenue" />
          ) : (
            <div className="chart-empty">Sales land here once eBay is connected.</div>
          )}
        </div>
      </div>

      <div className="chart-card queue-card">
        <div className="chart-title"><h3>Review queue</h3><span className="chart-legend">{queue.length} shown</span></div>
        {queue.length === 0 ? (
          <div className="chart-empty">Nothing waiting for review.</div>
        ) : (
          <div className="table-scroll">
            <table className="queue-table">
              <thead>
                <tr><th></th><th>Listing</th><th>Part #</th><th>Price</th><th>Status</th></tr>
              </thead>
              <tbody>
                {queue.map((l) => (
                  <tr key={l.id} onClick={() => navigate(`/review/${l.id}`)}>
                    <td>
                      {l.images[0] ? (
                        <span className="thumb" style={{ width: 40, height: 40, display: 'inline-block' }}>
                          <img src={imageSrc(l.images[0].id)} alt="" loading="lazy" />
                        </span>
                      ) : null}
                    </td>
                    <td className="queue-title-cell">{l.title || '(identifying…)'}</td>
                    <td className="mono">{l.part?.part_number_display || '—'}</td>
                    <td className="mono">{l.price != null ? money(l.price) : '—'}</td>
                    <td><StatusBadge status={l.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
