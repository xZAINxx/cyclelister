import { useRef, useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Camera, ImagePlus, X, Star, Loader2 } from 'lucide-react'
import { api, ApiError } from '../api'
import { useToast } from '../components/Toast'

const MAX_IMAGES = 8

export default function CaptureScreen() {
  const navigate = useNavigate()
  const toast = useToast()
  const cameraInput = useRef(null)
  const galleryInput = useRef(null)

  const [photos, setPhotos] = useState([]) // { file, url, key }
  const [hint, setHint] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [progress, setProgress] = useState(null) // { done, total, label }

  // Revoke object URLs on unmount to avoid leaks.
  useEffect(() => {
    return () => photos.forEach((p) => URL.revokeObjectURL(p.url))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const addFiles = (fileList) => {
    const incoming = Array.from(fileList || []).filter((f) => f.type.startsWith('image/'))
    if (incoming.length === 0) return
    setPhotos((prev) => {
      const room = MAX_IMAGES - prev.length
      if (room <= 0) {
        toast.error(`You can attach at most ${MAX_IMAGES} photos.`)
        return prev
      }
      if (incoming.length > room) {
        toast.info(`Only added ${room} photo(s) — ${MAX_IMAGES} max.`)
      }
      const next = incoming.slice(0, room).map((file) => ({
        file,
        url: URL.createObjectURL(file),
        key: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2)}`,
      }))
      return [...prev, ...next]
    })
  }

  const removePhoto = (key) => {
    setPhotos((prev) => {
      const target = prev.find((p) => p.key === key)
      if (target) URL.revokeObjectURL(target.url)
      return prev.filter((p) => p.key !== key)
    })
  }

  const makePrimary = (key) => {
    setPhotos((prev) => {
      const idx = prev.findIndex((p) => p.key === key)
      if (idx <= 0) return prev
      const copy = [...prev]
      const [item] = copy.splice(idx, 1)
      copy.unshift(item)
      return copy
    })
  }

  const submit = async () => {
    if (submitting) return
    if (photos.length === 0) {
      toast.error('Add at least one photo first.')
      return
    }
    setSubmitting(true)
    setProgress({ done: 0, total: photos.length, label: 'Creating listing…' })

    try {
      // 1) Create the listing shell.
      const listing = await api.createListing(hint.trim() || undefined)

      // 2) Upload each image sequentially (order matters; first = primary).
      for (let i = 0; i < photos.length; i++) {
        setProgress({ done: i, total: photos.length, label: `Uploading photo ${i + 1} of ${photos.length}…` })
        try {
          await api.uploadImage(listing.id, photos[i].file, i)
        } catch (err) {
          if (err instanceof ApiError) {
            toast.error(`Photo ${i + 1} failed: ${err.detail}`)
          } else {
            toast.error(`Photo ${i + 1} failed to upload.`)
          }
          // Keep going with remaining photos rather than abandoning the listing.
        }
      }

      // 3) Kick off the AI pipeline.
      setProgress({ done: photos.length, total: photos.length, label: 'Starting AI pipeline…' })
      const { job_id } = await api.runPipeline(listing.id)

      // 4) Hand off to the review screen; carry job_id so it can poll progress.
      navigate(`/review/${listing.id}`, { state: { job_id } })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Something went wrong creating the listing.'
      toast.error(msg)
      setSubmitting(false)
      setProgress(null)
    }
  }

  return (
    <div className="screen capture-screen">
      <input
        ref={cameraInput}
        type="file"
        accept="image/*"
        capture="environment"
        multiple
        hidden
        onChange={(e) => {
          addFiles(e.target.files)
          e.target.value = ''
        }}
      />
      <input
        ref={galleryInput}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => {
          addFiles(e.target.files)
          e.target.value = ''
        }}
      />

      <button
        className="capture-btn"
        onClick={() => cameraInput.current?.click()}
        disabled={submitting || photos.length >= MAX_IMAGES}
      >
        <Camera size={40} />
        <span>Take photo</span>
      </button>

      <button
        className="btn-secondary btn-block gallery-btn"
        onClick={() => galleryInput.current?.click()}
        disabled={submitting || photos.length >= MAX_IMAGES}
      >
        <ImagePlus size={18} />
        Choose from gallery
      </button>

      <div className="strip-header">
        <span className="strip-title">Photos</span>
        <span className="strip-count">
          {photos.length} / {MAX_IMAGES}
        </span>
      </div>

      {photos.length === 0 ? (
        <p className="muted empty-hint">No photos yet. The first photo is the primary image.</p>
      ) : (
        <div className="thumb-strip">
          {photos.map((p, i) => (
            <div className={`thumb ${i === 0 ? 'thumb-primary' : ''}`} key={p.key}>
              <img src={p.url} alt={`Photo ${i + 1}`} />
              {i === 0 && <span className="primary-badge">Primary</span>}
              <div className="thumb-actions">
                {i !== 0 && (
                  <button
                    className="thumb-btn"
                    title="Make primary"
                    onClick={() => makePrimary(p.key)}
                    disabled={submitting}
                  >
                    <Star size={14} />
                  </button>
                )}
                <button
                  className="thumb-btn"
                  title="Remove"
                  onClick={() => removePhoto(p.key)}
                  disabled={submitting}
                >
                  <X size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <label className="field">
        <span>Part number hint (optional)</span>
        <input
          type="text"
          value={hint}
          onChange={(e) => setHint(e.target.value)}
          placeholder="e.g. 4X7-25811-00-00"
          disabled={submitting}
          autoCapitalize="characters"
          autoCorrect="off"
        />
      </label>

      {progress && (
        <div className="progress-block" aria-live="polite">
          <div className="progress-label">
            <Loader2 size={16} className="spin" /> {progress.label}
          </div>
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      <button className="btn-primary btn-block cta" onClick={submit} disabled={submitting || photos.length === 0}>
        {submitting ? 'Working…' : 'Create listing'}
      </button>
    </div>
  )
}
