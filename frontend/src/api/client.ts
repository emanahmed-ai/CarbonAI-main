import axios from 'axios'

// 60s default: long imports use the background-job API instead of holding a request open.
export const api = axios.create({ baseURL: '/api', timeout: 60_000 })

const TOKEN_KEY = 'carbonai.token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t)
  else localStorage.removeItem(TOKEN_KEY)
}

api.interceptors.request.use((cfg) => {
  const t = getToken()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && !err.config?.url?.includes('/auth/login')) {
      setToken(null)
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export function errMsg(e: unknown): string {
  const d = (e as any)?.response?.data?.detail
  if (typeof d === 'string') return d
  if (d?.detail) return String(d.detail)
  const ax = e as any
  if (ax?.code === 'ECONNABORTED') {
    return 'The request timed out. The server may still be processing — refresh and check the result before retrying.'
  }
  if (ax?.message === 'Network Error') {
    return 'Cannot reach the server. Check that CarbonAI is running and the address is correct.'
  }
  return ax?.message || 'Unexpected error'
}

/** Download a file from an authenticated GET endpoint. */
export async function download(path: string, filename: string) {
  const r = await api.get(path, { responseType: 'blob', timeout: 120_000 })
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
