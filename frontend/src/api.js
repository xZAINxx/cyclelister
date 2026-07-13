import { getAccessToken } from './auth/supabaseClient'

// In the browser the API is same-origin (/api). In the Capacitor iOS/Android
// shell there is no same-origin backend, so VITE_API_BASE must point at the
// deployed API (e.g. https://api.example.com).
const API_PREFIX = `${import.meta.env.VITE_API_BASE || ''}/api`

/**
 * Thin fetch wrapper for the CycleLister backend.
 *
 * - Prefixes every path with /api (dev server proxies this to :8000).
 * - Injects `Authorization: Bearer <token>` when Supabase auth is configured.
 * - Parses JSON responses.
 * - Throws an ApiError { status, detail } on any non-2xx response.
 *
 * For multipart uploads, pass a FormData body; we deliberately do NOT set
 * Content-Type so the browser can add the correct multipart boundary.
 */
export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function apiFetch(path, options = {}) {
  const { body, headers: extraHeaders, ...rest } = options

  const headers = { ...(extraHeaders || {}) }
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData

  // JSON-encode plain-object bodies; leave FormData / strings untouched.
  let finalBody = body
  if (body != null && !isFormData && typeof body !== 'string') {
    finalBody = JSON.stringify(body)
    if (!headers['Content-Type']) headers['Content-Type'] = 'application/json'
  }

  const token = await getAccessToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const url = path.startsWith('/api') ? path : `${API_PREFIX}${path}`

  let res
  try {
    res = await fetch(url, { ...rest, headers, body: finalBody })
  } catch (networkErr) {
    // Backend down / offline / CORS — surface a friendly message.
    throw new ApiError(0, `Network error: ${networkErr.message}. Is the backend running?`)
  }

  const contentType = res.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json')

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    if (isJson) {
      try {
        const data = await res.json()
        detail = data?.detail ?? data?.message ?? detail
      } catch {
        /* keep default */
      }
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return null
  if (isJson) return res.json()
  return res.text()
}

// Convenience helpers for the frozen REST contract.
export const api = {
  health: () => apiFetch('/health'),

  createListing: (hint) => apiFetch('/listings', { method: 'POST', body: hint ? { hint } : {} }),
  getListings: (status) =>
    apiFetch(`/listings${status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : ''}`),
  getListing: (id) => apiFetch(`/listings/${id}`),
  patchListing: (id, patch) => apiFetch(`/listings/${id}`, { method: 'PATCH', body: patch }),

  uploadImage: (id, file, orderIndex) => {
    const form = new FormData()
    form.append('file', file)
    if (orderIndex != null) form.append('order_index', String(orderIndex))
    return apiFetch(`/listings/${id}/images`, { method: 'POST', body: form })
  },

  runPipeline: (id) => apiFetch(`/listings/${id}/pipeline`, { method: 'POST' }),
  getJob: (jobId) => apiFetch(`/jobs/${jobId}`),
  publish: (id) => apiFetch(`/listings/${id}/publish`, { method: 'POST' }),

  searchParts: (q) => apiFetch(`/parts?q=${encodeURIComponent(q || '')}`),
  saveFitment: (partId, fitments) =>
    apiFetch(`/parts/${partId}/fitment`, { method: 'PUT', body: { fitments } }),

  ebayStatus: () => apiFetch('/ebay/status'),
  analyticsSummary: () => apiFetch('/analytics/summary'),
}

// The backend serves image binaries directly; build the URL for <img src>.
export function imageSrc(imageId) {
  return `${API_PREFIX}/images/${imageId}`
}
