import { useState } from 'react'
import { Plus, Trash2, Save } from 'lucide-react'
import { api, ApiError } from '../api'
import { useToast } from './Toast'

const emptyRow = () => ({
  id: crypto.randomUUID(),
  make: '',
  model: '',
  year_start: '',
  year_end: '',
  confidence: null,
  confirmed: false,
})

function toRow(f) {
  return {
    id: f.id || crypto.randomUUID(),
    make: f.make || '',
    model: f.model || '',
    year_start: f.year_start ?? '',
    year_end: f.year_end ?? '',
    confidence: f.confidence ?? null,
    confirmed: Boolean(f.confirmed),
  }
}

/**
 * Fitment editor. Saving is only possible when the listing has a linked part
 * (PUT /parts/{part.id}/fitment). Without a part we render read-only rows plus
 * an explanatory note.
 */
export default function FitmentSection({ partId, initialFitment }) {
  const toast = useToast()
  const [rows, setRows] = useState((initialFitment || []).map(toRow))
  const [saving, setSaving] = useState(false)

  const canSave = Boolean(partId)

  const update = (id, field, val) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, [field]: val } : r)))
  const removeRow = (id) => setRows((rs) => rs.filter((r) => r.id !== id))
  const addRow = () => setRows((rs) => [...rs, emptyRow()])

  const save = async () => {
    if (!canSave || saving) return
    // Only send rows that have at least make+model.
    const payload = rows
      .filter((r) => r.make.trim() && r.model.trim())
      .map((r) => ({
        make: r.make.trim(),
        model: r.model.trim(),
        year_start: r.year_start === '' ? null : Number(r.year_start),
        year_end: r.year_end === '' ? null : Number(r.year_end),
        confirmed: Boolean(r.confirmed),
      }))
    setSaving(true)
    try {
      const res = await api.saveFitment(partId, payload)
      if (Array.isArray(res?.items)) setRows(res.items.map(toRow))
      toast.success('Fitment saved.')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Failed to save fitment.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="section">
      <div className="section-head">
        <h2>Fitment</h2>
        {canSave && (
          <button className="btn-secondary btn-sm" onClick={save} disabled={saving} type="button">
            <Save size={14} /> {saving ? 'Saving…' : 'Save fitment'}
          </button>
        )}
      </div>

      {!canSave && (
        <div className="banner banner-info small">
          Fitment can be saved once the part is identified and linked to your catalog.
        </div>
      )}

      <div className="fitment-table">
        <div className="fitment-row fitment-header">
          <span>Make</span>
          <span>Model</span>
          <span>From</span>
          <span>To</span>
          <span>Conf.</span>
          <span>OK</span>
          <span />
        </div>

        {rows.length === 0 && <p className="muted small pad">No fitment rows yet.</p>}

        {rows.map((r) => (
          <div className="fitment-row" key={r.id}>
            <input
              value={r.make}
              onChange={(e) => update(r.id, 'make', e.target.value)}
              placeholder="Yamaha"
              disabled={!canSave}
            />
            <input
              value={r.model}
              onChange={(e) => update(r.id, 'model', e.target.value)}
              placeholder="XS650"
              disabled={!canSave}
            />
            <input
              type="number"
              inputMode="numeric"
              value={r.year_start}
              onChange={(e) => update(r.id, 'year_start', e.target.value)}
              placeholder="1978"
              disabled={!canSave}
            />
            <input
              type="number"
              inputMode="numeric"
              value={r.year_end}
              onChange={(e) => update(r.id, 'year_end', e.target.value)}
              placeholder="1984"
              disabled={!canSave}
            />
            <span className="conf-cell">
              {r.confidence != null ? `${Math.round(Number(r.confidence) * 100)}%` : '—'}
            </span>
            <input
              type="checkbox"
              checked={r.confirmed}
              onChange={(e) => update(r.id, 'confirmed', e.target.checked)}
              disabled={!canSave}
              aria-label="Confirmed"
            />
            <button
              className="btn-icon danger"
              onClick={() => removeRow(r.id)}
              disabled={!canSave}
              type="button"
              title="Remove row"
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>

      {canSave && (
        <button className="btn-secondary btn-sm" onClick={addRow} type="button">
          <Plus size={14} /> Add fitment row
        </button>
      )}
    </section>
  )
}
