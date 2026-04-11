import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 120_000 })

// 请求拦截：自动带 token
http.interceptors.request.use(cfg => {
  const token = localStorage.getItem('rag_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

// 响应拦截：统一解构，同时把顶层 trace_id 合并进 data
http.interceptors.response.use(
  r => {
    const body = r.data
    // 标准结构 {code, message, data, trace_id}
    if (body && typeof body === 'object' && 'code' in body && 'data' in body) {
      const result = body.data
      // 把 trace_id 合并到 data 对象，方便页面读取
      if (result && typeof result === 'object' && body.trace_id) {
        result.trace_id = result.trace_id || body.trace_id
      }
      return result
    }
    return body
  },
  e => {
    const detail = e?.response?.data?.message || e?.response?.data?.detail || e.message || '请求失败'
    if (e?.response?.status === 401) {
      localStorage.removeItem('rag_token')
      localStorage.removeItem('rag_user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(detail)
  }
)

// ── Auth ─────────────────────────────────────
export const apiLogin   = (username, password) => http.post('/auth/login', { username, password })
export const apiLogout  = ()                   => http.post('/auth/logout')
export const apiMe      = ()                   => http.get('/auth/me')

// ── Admin / Users ────────────────────────────
export const apiListUsers = (params = {}) => {
  const { skip = 0, limit = 50, cursor } = params
  const q = { skip, limit }
  if (cursor) q.cursor = cursor
  return http.get('/admin/users', { params: q })
}
export const apiCreateUser   = (data)   => http.post('/admin/users', data)
export const apiUpdateUser   = (id, data) => http.put(`/admin/users/${id}`, data)
export const apiChangePassword = (data) => http.post('/admin/change-password', data)

// ── Admin / API Keys ─────────────────────────
export const apiCreateApiKey = (name) => http.post('/admin/apikeys', { name })
export const apiListApiKeys  = ()     => http.get('/admin/apikeys')
export const apiRevokeApiKey = (id)   => http.delete(`/admin/apikeys/${id}`)

// ── Chat ─────────────────────────────────────
export const apiChat = (question, session_id, tag_ids) => {
  const payload = { question, session_id }
  if (tag_ids && tag_ids.length) payload.tag_ids = tag_ids
  return http.post('/chat/', payload)
}
export const apiCreateShare  = (logId) => http.post(`/chat/share/${logId}`)
export const apiShareQA     = (shareToken) => http.get(`/chat/share/${shareToken}`)
export const apiSuggestions = ()      => http.get('/chat/suggestions')
export const apiChatHistory = (skip=0, limit=30) => http.get('/chat/history', { params: { skip, limit } })
// SSE 流式请求：使用 fetch + ReadableStream 以便通过 Header 传 token（避免 URL 泄露）
export const fetchStream = async (question, session_id, { onMessage, onError, onDone, onSources, tagIds }) => {
  const token = localStorage.getItem('rag_token') || ''
  let url = `/api/chat/stream?question=${encodeURIComponent(question)}`
  if (session_id) url += `&session_id=${encodeURIComponent(session_id)}`
  if (tagIds && tagIds.length) url += `&tag_ids=${encodeURIComponent(tagIds.join(','))}`
  try {
    const resp = await fetch(url, {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    })
    if (!resp.ok) { onError(`HTTP ${resp.status}`); return }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // 按 SSE 事件边界（空行）分割
      const events = buf.split('\n\n')
      buf = events.pop() // 保留不完整事件
      for (const event of events) {
        const dataLines = event.split('\n')
          .filter(l => l.startsWith('data: '))
          .map(l => l.slice(6))
        if (!dataLines.length) continue
        const data = dataLines.join('\n')
        if (data === '[DONE]') { onDone(); return }
        if (data.startsWith('[ERROR]')) { onError(data.slice(7)); return }
        if (data.startsWith('[SOURCES]')) {
          try { onSources && onSources(JSON.parse(data.slice(9))) } catch {}
          continue
        }
        onMessage(data)
      }
    }
    onDone()
  } catch (e) { onError(String(e)) }
}
// ── Tags ─────────────────────────────────────
export const apiListTags    = ()          => http.get('/tags/')
export const apiCreateTag   = (name, color) => http.post('/tags/', { name, color })
export const apiDeleteTag   = (id)        => http.delete(`/tags/${id}`)
export const apiBindDocTag  = (doc_id, tag_id) => http.post('/tags/bind', { doc_id, tag_id })
export const apiUnbindDocTag = (doc_id, tag_id) => http.post('/tags/unbind', { doc_id, tag_id })
export const apiDocTags     = (doc_id)    => http.get(`/tags/doc/${doc_id}`)

// ── Upload ───────────────────────────────────
export const apiUpload         = (fd, overwrite=false) => http.post(`/upload/?overwrite=${overwrite}`, fd)
export const apiBatchUpload    = (fd)     => http.post('/upload/batch', fd, { timeout: 300_000 })
export const apiUrlImport      = (urls)   => http.post('/upload/from-url', { urls })
export const apiListDocs       = (skip=0, limit=30, tag='') => http.get('/upload/docs', { params: { skip, limit, tag: tag || undefined } })
export const apiGetDoc    = (id)              => http.get(`/upload/docs/${id}`)
export const apiDeleteDoc = (id)              => http.delete(`/upload/docs/${id}`)
export const apiRetryDoc  = (id)              => http.post(`/upload/docs/${id}/retry`)
export const apiDocChunks = (id, skip=0, limit=50) => http.get(`/upload/docs/${id}/chunks`, { params: { skip, limit } })

// ── Feedback ─────────────────────────────────
export const apiFeedback      = (data) => http.post('/feedback/', data)
export const apiFeedbackStats = ()     => http.get('/feedback/stats')

// ── Metrics ──────────────────────────────────
export const apiOverview     = ()       => http.get('/metrics/overview')
export const apiRagMetrics   = (days=7) => http.get('/metrics/rag', { params: { days } })
export const apiCacheMetrics = ()       => http.get('/metrics/cache')
export const apiDocMetrics   = ()       => http.get('/metrics/docs')
export const apiQPS          = ()       => http.get('/metrics/qps')

// ── Audit ────────────────────────────────────
export const apiAuditLogs = (page=1, limit=20, action='') =>
  http.get('/audit/', { params: { page, limit, action } })

// ── Health（不需要 token，用单独 axios 实例）────
export const apiHealth = () =>
  axios.get('/api/health').then(r => {
    const b = r.data
    return (b && 'data' in b) ? b.data : b
  })
