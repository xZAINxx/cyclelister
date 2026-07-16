import { useEffect, useRef, useState } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, ImagePlus, RotateCw, Save, Tag, UploadCloud, AlertTriangle, ShieldCheck, X } from 'lucide-react'
import { api, ApiError, imageSrc } from '../api'
import { useToast } from '../components/Toast'
import StatusBadge from '../components/StatusBadge'
import PipelineProgress from '../components/PipelineProgress'
import ItemSpecificsEditor from '../components/ItemSpecificsEditor'
import FitmentSection from '../components/FitmentSection'

// Values are the backend's canonical condition grades (see backend/app/schemas.py
// ConditionGrade); labels are presentation only. The grade drives the eBay
// condition mapping on publish — never send display strings.
const CONDITIONS = [
  { value: 'new_nos', label: 'New – NOS' },
  { value: 'new_other', label: 'New other (see details)' },
  { value: 'used', label: 'Used' },
  { value: 'for_parts', label: 'For parts or not working' },
]
const TITLE_MAX = 80
const POLL_MS = 1500

function specificsToRows(obj) {
  if (!obj || typeof obj !== 'object') return []
  return Object.entries(obj).map(([key, value]) => ({
    id: crypto.randomUUID(),
    key,
    value: value == null ? '' : String(value),
  }))
}

function rowsToSpecifics(rows) {
  const out = {}
  for (const r of rows) {
    const k = r.key.trim()
    if (k) out[k] = r.value
  }
  return out
}

export default function ReviewScreen() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const toast = useToast()
  const jobId = location.state?.job_id || null

  const [phase, setPhase] = useState('loading') // loading | processing | ready | error
  const [pageError, setPageError] = useState(null)
  const [listing, setListing] = useState(null)
  const [job, setJob] = useState({ status: jobId ? 'queued' : null, steps: null, error: null })

  // Editable form state.
  const [form, setForm] = useState({
    title: '',
    description: '',
    price: '',
    quantity: '',
    condition: '',
    condition_notes: '',
    category_id: '',
  })
  const [specificRows, setSpecificRows] = useState([])

  const [saving, setSaving] = useState(false)
  const [repricing, setRepricing] = useState(false)
  const [showPublish, setShowPublish] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [publishBanner, setPublishBanner] = useState(null) // 503 detail text
  const [ebayEnv, setEbayEnv] = useState(null) // sandbox | production, for the confirm dialog
  const [lightbox, setLightbox] = useState(null)

  const hydratedRef = useRef(false)

  const hydrate = (l) => {
    setForm({
      title: l.title || '',
      description: l.description || '',
      price: l.price != null ? String(l.price) : '',
      quantity: l.quantity != null ? String(l.quantity) : '1',
      condition: l.condition || '',
      condition_notes: l.condition_notes || '',
      category_id: l.category_id || '',
    })
    setSpecificRows(specificsToRows(l.item_specifics))
    hydratedRef.current = true
  }

  // Load + poll. One effect, cleaned up on unmount.
  useEffect(() => {
    let alive = true
    let timer = null

    const schedule = (fn) => {
      timer = setTimeout(fn, POLL_MS)
    }

    const settle = (l) => {
      if (!alive) return
      setListing(l)
      if (!hydratedRef.current) hydrate(l)
      setPhase('ready')
    }

    const pollJob = async () => {
      try {
        const j = await api.getJob(jobId)
        if (!alive) return
        setJob({ status: j.status, steps: j.result?.steps ?? null, error: j.error })
        if (j.status === 'succeeded' || j.status === 'failed') {
          const l = await api.getListing(id)
          if (!alive) return
          return settle(l)
        }
        schedule(pollJob)
      } catch {
        // Job endpoint hiccup — fall back to polling the listing directly.
        schedule(pollListing)
      }
    }

    const pollListing = async () => {
      try {
        const l = await api.getListing(id)
        if (!alive) return
        setListing(l)
        if (l.status !== 'draft') return settle(l)
        schedule(jobId ? pollJob : pollListing)
      } catch (err) {
        if (!alive) return
        // Keep the processing view but note the trouble; retry.
        schedule(jobId ? pollJob : pollListing)
      }
    }

    const start = async () => {
      try {
        const l = await api.getListing(id)
        if (!alive) return
        setListing(l)
        if (l.status !== 'draft' || !jobId) {
          // Terminal status, or a draft with no running pipeline (catalog /
          // relist flow) — render the editable form immediately.
          return settle(l)
        }
        setPhase('processing')
        schedule(pollJob)
      } catch (err) {
        if (!alive) return
        setPageError(err instanceof ApiError ? err.detail : 'Failed to load listing.')
        setPhase('error')
      }
    }

    start()
    return () => {
      alive = false
      if (timer) clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const save = async () => {
    if (saving) return
    setSaving(true)
    try {
      const patch = {
        title: form.title,
        description: form.description,
        price: form.price === '' ? null : Number(form.price),
        quantity: form.quantity === '' ? null : Number(form.quantity),
        condition: form.condition || null,
        condition_notes: form.condition_notes,
        category_id: form.category_id,
        item_specifics: rowsToSpecifics(specificRows),
      }
      const updated = await api.patchListing(id, patch)
      setListing(updated)
      toast.success('Listing saved.')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Failed to save listing.')
    } finally {
      setSaving(false)
    }
  }

  const doReprice = async () => {
    if (repricing) return
    setRepricing(true)
    try {
      const updated = await api.reprice(id)
      setListing(updated)
      if (updated.price != null) setForm((f) => ({ ...f, price: String(updated.price) }))
      toast.success(updated.price != null ? 'Price computed.' : 'No price found — see note.')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Pricing failed.')
    } finally {
      setRepricing(false)
    }
  }

  const doPublish = async () => {
    setPublishing(true)
    setPublishBanner(null)
    try {
      const res = await api.publish(id)
      setListing((l) => (l ? { ...l, status: 'listed', ebay_listing_id: res.ebay_listing_id } : l))
      setShowPublish(false)
      toast.success('Published to eBay.')
    } catch (err) {
      setShowPublish(false)
      if (err instanceof ApiError && err.status === 503) {
        // eBay not connected — show the backend's message, never fake success.
        setPublishBanner(err.detail || 'eBay not connected — configure credentials in backend .env')
      } else {
        toast.error(err instanceof ApiError ? err.detail : 'Publish failed.')
      }
    } finally {
      setPublishing(false)
    }
  }

  // ---- Render states -------------------------------------------------------

  if (phase === 'loading') {
    return (
      <div className="screen review-screen">
        <BackBar onBack={() => navigate(-1)} />
        <div className="fullscreen-center pad-lg">
          <div className="spinner" aria-label="Loading" />
        </div>
      </div>
    )
  }

  if (phase === 'error') {
    return (
      <div className="screen review-screen">
        <BackBar onBack={() => navigate('/drafts')} />
        <div className="banner banner-error">
          <AlertTriangle size={16} /> {pageError}
        </div>
        <button className="btn-secondary" onClick={() => navigate('/drafts')}>
          Back to drafts
        </button>
      </div>
    )
  }

  if (phase === 'processing') {
    return (
      <div className="screen review-screen">
        <BackBar onBack={() => navigate('/drafts')} title="Building listing" />
        <PipelineProgress jobStatus={job.status} steps={job.steps} error={job.error} />
        <p className="muted center small">This usually takes under a minute. You can leave and come back.</p>
      </div>
    )
  }

  // ready
  const images = listing?.images || []
  const status = listing?.status || 'draft'
  const ebayId = listing?.ebay_listing_id || null
  const isListed = status === 'listed' || Boolean(ebayId)
  const part = listing?.part || null

  return (
    <div className="screen review-screen">
      <BackBar onBack={() => navigate('/drafts')} title="Review listing">
        <StatusBadge status={isListed ? 'listed' : status} />
      </BackBar>

      {listing?.needs_human_review && (
        <div className="banner banner-warn">
          <AlertTriangle size={16} />
          <span>
            Needs review
            {listing.ai_confidence != null && ` — AI confidence ${Math.round(Number(listing.ai_confidence) * 100)}%`}
            . Double-check the details before publishing.
          </span>
        </div>
      )}

      {status === 'error' && (
        <div className="banner banner-error">
          <AlertTriangle size={16} /> This listing hit an error during processing. Review and edit below, then retry.
        </div>
      )}

      {publishBanner && (
        <div className="banner banner-warn dismissible">
          <span>
            <AlertTriangle size={16} /> {publishBanner}
          </span>
          <button className="banner-x" onClick={() => setPublishBanner(null)} aria-label="Dismiss">
            <X size={15} />
          </button>
        </div>
      )}

      {ebayId && (
        <div className="banner banner-success">
          <ShieldCheck size={16} /> Published — eBay listing ID <strong>{ebayId}</strong>
        </div>
      )}

      {/* Image gallery (+ add photos — catalog/relist drafts start with none) */}
      <div className="gallery">
        {images
          .slice()
          .sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0))
          .map((img) => (
            <button
              key={img.id}
              className={`gallery-thumb ${img.is_primary ? 'is-primary' : ''}`}
              onClick={() => setLightbox(imageSrc(img.id))}
              type="button"
            >
              <img src={imageSrc(img.id)} alt="" loading="lazy" />
              {img.is_primary && <span className="primary-badge">Primary</span>}
            </button>
          ))}
        {images.length < 8 && !isListed && (
          <label className="gallery-thumb gallery-add">
            <input
              type="file"
              accept="image/*"
              multiple
              hidden
              onChange={async (e) => {
                const files = Array.from(e.target.files || []).slice(0, 8 - images.length)
                e.target.value = ''
                for (const file of files) {
                  try {
                    await api.uploadImage(id, file)
                  } catch (err) {
                    toast.error(err instanceof ApiError ? err.detail : 'Upload failed.')
                  }
                }
                try {
                  setListing(await api.getListing(id))
                } catch { /* keep current view */ }
              }}
            />
            <ImagePlus size={20} />
            <span>Add</span>
          </label>
        )}
      </div>

      {/* Core fields */}
      <section className="section">
        <label className="field">
          <span className="field-label-row">
            <span>Title</span>
            <span className={`counter ${form.title.length >= TITLE_MAX ? 'counter-max' : ''}`}>
              {form.title.length}/{TITLE_MAX}
            </span>
          </span>
          <input
            type="text"
            value={form.title}
            maxLength={TITLE_MAX}
            onChange={(e) => setField('title', e.target.value)}
            placeholder="Brand + part type + part number + key fitment"
          />
        </label>

        <label className="field">
          <span>Description</span>
          <textarea
            rows={6}
            value={form.description}
            onChange={(e) => setField('description', e.target.value)}
            placeholder="Condition, fitment, and any notes…"
          />
        </label>

        <div className="field-row">
          <label className="field">
            <span>Price ($)</span>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              value={form.price}
              onChange={(e) => setField('price', e.target.value)}
              placeholder="0.95"
            />
          </label>
          <label className="field">
            <span>Quantity</span>
            <input
              type="number"
              inputMode="numeric"
              min="0"
              value={form.quantity}
              onChange={(e) => setField('quantity', e.target.value)}
              placeholder="1"
            />
          </label>
        </div>

        {/* Smart Pricing explanation (spec §6 step 8: price with a visible why) */}
        <div className="price-explain">
          <span className="price-explain-text">
            {listing?.price_explanation || 'Smart Pricing has not run on this draft yet.'}
          </span>
          <button className="btn-secondary btn-sm" disabled={repricing} onClick={doReprice} type="button">
            <RotateCw size={13} className={repricing ? 'spin' : ''} /> {repricing ? 'Pricing…' : 'Reprice'}
          </button>
        </div>

        <div className="field-row">
          <label className="field">
            <span>Condition</span>
            <select value={form.condition} onChange={(e) => setField('condition', e.target.value)}>
              <option value="">Select…</option>
              {form.condition && !CONDITIONS.some((c) => c.value === form.condition) && (
                <option value={form.condition}>{form.condition}</option>
              )}
              {CONDITIONS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>eBay category ID</span>
            <input
              type="text"
              value={form.category_id}
              onChange={(e) => setField('category_id', e.target.value)}
              placeholder="e.g. 35570"
              inputMode="numeric"
            />
          </label>
        </div>

        <label className="field">
          <span>Condition notes</span>
          <textarea
            rows={2}
            value={form.condition_notes}
            onChange={(e) => setField('condition_notes', e.target.value)}
            placeholder="e.g. New Old Stock, minor shelf wear on box"
          />
        </label>
      </section>

      {/* Item specifics */}
      <section className="section">
        <div className="section-head">
          <h2>Item specifics</h2>
        </div>
        <ItemSpecificsEditor rows={specificRows} onChange={setSpecificRows} disabled={saving} />
      </section>

      {/* Fitment */}
      <FitmentSection partId={part?.id || null} initialFitment={listing?.fitment} />

      {/* Sticky action bar */}
      <div className="action-bar">
        {isListed && (
          <button
            className="btn-secondary"
            type="button"
            onClick={async () => {
              if (!window.confirm('Mark this listing as sold and archive it to history?')) return
              try {
                const updated = await api.markSold(id, listing?.price ?? null)
                setListing(updated)
                toast.success('Sold — archived to history. Relist it anytime from the Sold tab.')
              } catch (err) {
                toast.error(err instanceof ApiError ? err.detail : 'Could not mark sold.')
              }
            }}
          >
            <Tag size={16} /> Mark sold
          </button>
        )}
        <button className="btn-secondary" onClick={save} disabled={saving} type="button">
          <Save size={16} /> {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          className="btn-primary"
          onClick={() => {
            setShowPublish(true)
            // Real environment for the confirm dialog — never claim "sandbox" from a hardcoded string.
            api.ebayStatus().then((s) => setEbayEnv(s.environment)).catch(() => {})
          }}
          disabled={publishing || isListed}
          type="button"
        >
          <UploadCloud size={16} /> {isListed ? 'Listed' : 'Publish'}
        </button>
      </div>

      {/* Publish confirmation */}
      {showPublish && (
        <div className="modal-overlay" onClick={() => !publishing && setShowPublish(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Publish to eBay{ebayEnv ? ` (${ebayEnv})` : ''}?</h3>
            <p className="muted">
              This creates a live listing on the connected eBay account. You can still edit it afterward on eBay.
            </p>
            <div className="modal-actions">
              <button className="btn-ghost" onClick={() => setShowPublish(false)} disabled={publishing}>
                Cancel
              </button>
              <button className="btn-primary" onClick={doPublish} disabled={publishing}>
                {publishing ? 'Publishing…' : 'Publish'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div className="lightbox" onClick={() => setLightbox(null)}>
          <button className="lightbox-close" aria-label="Close">
            <X size={24} />
          </button>
          <img src={lightbox} alt="Enlarged" />
        </div>
      )}
    </div>
  )
}

function BackBar({ onBack, title, children }) {
  return (
    <div className="back-bar">
      <button className="btn-icon" onClick={onBack} aria-label="Back" type="button">
        <ArrowLeft size={20} />
      </button>
      {title && <span className="back-title">{title}</span>}
      <div className="back-right">{children}</div>
    </div>
  )
}
