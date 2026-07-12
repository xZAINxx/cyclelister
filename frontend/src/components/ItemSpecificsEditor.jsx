import { Plus, X } from 'lucide-react'

/**
 * Key/value editor for eBay item specifics.
 * Value is the parent's object; we present it as ordered rows via `rows`
 * ([key, value] pairs) held in parent state to keep row identity stable.
 */
export default function ItemSpecificsEditor({ rows, onChange, disabled }) {
  const update = (idx, field, val) => {
    const next = rows.map((r, i) => (i === idx ? { ...r, [field]: val } : r))
    onChange(next)
  }
  const remove = (idx) => onChange(rows.filter((_, i) => i !== idx))
  const add = () => onChange([...rows, { id: crypto.randomUUID(), key: '', value: '' }])

  return (
    <div className="specifics">
      {rows.length === 0 && <p className="muted small">No item specifics yet.</p>}
      {rows.map((row, idx) => (
        <div className="specific-row" key={row.id}>
          <input
            className="specific-key"
            placeholder="Name (e.g. Brand)"
            value={row.key}
            onChange={(e) => update(idx, 'key', e.target.value)}
            disabled={disabled}
          />
          <input
            className="specific-val"
            placeholder="Value (e.g. Yamaha)"
            value={row.value}
            onChange={(e) => update(idx, 'value', e.target.value)}
            disabled={disabled}
          />
          <button
            className="btn-icon danger"
            title="Remove"
            onClick={() => remove(idx)}
            disabled={disabled}
            type="button"
          >
            <X size={16} />
          </button>
        </div>
      ))}
      <button className="btn-secondary btn-sm" onClick={add} disabled={disabled} type="button">
        <Plus size={14} /> Add specific
      </button>
    </div>
  )
}
