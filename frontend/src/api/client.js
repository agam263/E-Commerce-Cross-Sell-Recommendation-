/**
 * Axios client for the cross-sell API.
 *
 * Base URL resolution order:
 *   1. VITE_API_BASE_URL (set in .env for a deployed build)
 *   2. "/api" in development, proxied to FastAPI by vite.config.js
 */
import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

export const api = axios.create({
  baseURL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

const apiKey = import.meta.env.VITE_API_KEY
if (apiKey) api.defaults.headers.common['X-API-Key'] = apiKey

/** Turn an axios failure into a short, human-readable sentence. */
export function describeError(error) {
  if (!error) return 'Unknown error.'
  const data = error.response?.data
  if (data?.detail) {
    return typeof data.detail === 'string'
      ? data.detail
      : data.detail.map?.((d) => d.msg).join('; ') || JSON.stringify(data.detail)
  }
  if (data?.error) return `${data.error}: ${data.detail ?? ''}`.trim()
  if (error.code === 'ECONNABORTED') return 'The request timed out.'
  if (error.message === 'Network Error') {
    return 'Cannot reach the API. Is it running on http://127.0.0.1:8000 (make api)?'
  }
  return error.message || 'Request failed.'
}

export const endpoints = {
  health: () => api.get('/health').then((r) => r.data),
  stats: () => api.get('/stats').then((r) => r.data),
  config: () => api.get('/config').then((r) => r.data),
  evaluation: () => api.get('/evaluation').then((r) => r.data),
  products: (params) => api.get('/products', { params }).then((r) => r.data),
  product: (id) => api.get(`/products/${encodeURIComponent(id)}`).then((r) => r.data),
  rules: (params) => api.get('/rules', { params }).then((r) => r.data),
  recommendations: (id, params) =>
    api.get(`/recommendations/${encodeURIComponent(id)}`, { params }).then((r) => r.data),
  basketRecommendations: (payload) =>
    api.post('/recommendations', payload).then((r) => r.data),
  simulate: (payload) => api.post('/simulate-revenue', payload).then((r) => r.data),
  insights: (params) => api.get('/insights', { params }).then((r) => r.data),
}

/**
 * The two ranking orders the dashboard can serve.
 *
 * `confidence` is what the shipped configuration uses -- it measured better on
 * the validation split (hit rate @5 of 0.181 against 0.157). `lift` is the
 * ordering the PRD specifies. Both run against the same mined rule set, so
 * switching re-ranks, it never re-mines.
 */
export const RANKINGS = {
  confidence: {
    id: 'confidence',
    label: 'Confidence first',
    order: ['confidence', 'lift', 'support'],
    note: 'Tuned default — ranks by how often the pairing actually happens.',
  },
  lift: {
    id: 'lift',
    label: 'Lift first (PRD)',
    order: ['lift', 'confidence', 'support'],
    note: 'The ordering specified in the PRD — ranks by strength above chance.',
  },
}
