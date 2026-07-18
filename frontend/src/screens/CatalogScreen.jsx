import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, PlusCircle, AlertTriangle } from 'lucide-react'
import { api, ApiError } from '../api'
import BarcodeScanButton from '../components/BarcodeScanButton'
import { useToast } from '../components/Toast'

// Modern take on MotoLister's part-picker grid: the seller's own growing
// catalog, brand-tabbed and searchable, one click from any part to a
// prefilled draft (docs/motolister-scope-synopsis.md §2).

const priceFromNotes = (notes) => notes?.match(/listed at (\$[\d.,]+)/)?.[1] || null

function fitmentSummary(fitment) {
  const confirmed = fitment.filter((f) => f.confirmed)
  const shown = (confirmed.length ? confirmed : fitment).slice(0, 2)
  return {
    chips: shown.map((f) => `${f.model}${f.year_start ? ` '${String(f.year_start).slice(2)}–'${String(f.year_end ?? f.year_start).slice(2)}` : ''}`),
    more: fitment.length - shown.length,
  }
}

export default function CatalogScreen() {
  const navigate = useNavigate()
  const toast = useToast()
  const [facets, setFacets] = useState(null)
  const [brand, setBrand] = useState('')
  const [q, setQ] = useState('')
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [startingId, setStartingId] = useState(null)

  useEffect(() => {
    api.partsFacets().then(setFacets).catch(() => {})
  }, [])

  useEffect(() => {
    let alive = true
    const t = setTimeout(() => {
      api
        .searchParts(q, brand)
        .then((r) => alive && (setItems(r.items), setError(null)))
        .catch((err) => alive && setError(err instanceof ApiError ? err.detail : 'Search failed.'))
    }, q ? 250 : 0)
    return () => {
      alive = false
      clearTimeout(t)
    }
  }, [q, brand])

  const brands = useMemo(() => facets?.brands || [], [facets])

  const startListing = async (part) => {
    if (startingId) return
    setStartingId(part.id)
    try {
      const listing = await api.createListing(null, part.id)
      toast.success('Draft created from catalog — add photos and price.')
      navigate(`/review/${listing.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not create draft.')
      setStartingId(null)
    }
  }

  return (
    <div className="screen catalog-screen">
      <div className="dash-head">
        <div className="dash-title">Parts <span className="brand-accent">Catalog</span></div>
        <span className="dash-updated">{facets ? `${facets.total.toLocaleString()} parts` : ''}</span>
      </div>

      <div className="drafts-toolbar">
        <div className="chips">
          <button className={`chip ${brand === '' ? 'chip-active' : ''}`} onClick={() => setBrand('')}>
            All
          </button>
          {brands.map((b) => (
            <button
              key={b.brand}
              className={`chip ${brand === b.brand ? 'chip-active' : ''}`}
              onClick={() => setBrand(b.brand)}
            >
              {b.brand} <span className="chip-count">{b.count}</span>
            </button>
          ))}
        </div>
      </div>

      <label className="field search-field">
        <span className="field-label-row">
          <span><Search size={12} /> Search part number, type, or title</span>
          <BarcodeScanButton onScan={setQ} />
        </span>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. 90480-01401, carburetor, XS650 — or scan a barcode"
        />
      </label>

      {error && (
        <div className="banner banner-error"><AlertTriangle size={16} /> {error}</div>
      )}

      {items === null ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : items.length === 0 ? (
        <div className="empty-state">
          No parts match. The catalog grows automatically with every identified listing —
          or seed it: <code className="mono">scripts/import_listings.py</code>
        </div>
      ) : (
        <div className="chart-card table-scroll">
          <table className="queue-table catalog-table">
            <thead>
              <tr><th>Part #</th><th>Known listing title</th><th>Brand</th><th>Fitment</th><th>Last price</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const fit = fitmentSummary(p.fitment)
                const price = priceFromNotes(p.notes)
                return (
                  <tr key={p.id}>
                    <td className="mono">{p.part_number_display || '—'}</td>
                    <td className="queue-title-cell" title={p.title_template || ''}>
                      {p.title_template || <span className="muted">(no title yet)</span>}
                    </td>
                    <td>{p.brand ? <span className="badge">{p.brand}</span> : <span className="muted">—</span>}</td>
                    <td>
                      {fit.chips.map((c) => (
                        <span key={c} className="fit-chip mono">{c}</span>
                      ))}
                      {fit.more > 0 && <span className="muted small"> +{fit.more}</span>}
                    </td>
                    <td className="mono">{price || '—'}</td>
                    <td>
                      <button
                        className="btn-primary btn-sm"
                        disabled={startingId === p.id}
                        onClick={() => startListing(p)}
                      >
                        <PlusCircle size={14} /> {startingId === p.id ? 'Starting…' : 'List it'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
