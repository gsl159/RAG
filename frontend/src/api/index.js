import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 120_000 })

// 请求拦截：自动带 token，过期时主动跳登录
http.interceptors.request.use(cfg => {
  const token = sessionStorage.getItem('rag_token')
  if (token) {
    // 检查 JWT 是否已过期（解析 payload.exp）
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      if (payload.exp && payload.exp * 1000 < Date.now()) {
        sessionStorage.removeItem('rag_token')
        sessionStorage.removeItem('rag_user')
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        return Promise.reject('Token expired')
      }
    } catch { /* malformed token, let server reject */ }
    cfg.headers.Authorization = `Bearer ${token}`
  }
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
    const status = e?.response?.status
    // Global toast for non-401 errors
    if (status !== 401 && window.$toast) {
      if (status === 409) window.$toast.warning(detail)
      else if (status >= 500) window.$toast.error('服务器错误: ' + detail)
      else if (status === 429) window.$toast.warning('请求过于频繁，请稍后')
    }
    if (status === 401) {
      sessionStorage.removeItem('rag_token')
      sessionStorage.removeItem('rag_user')
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
export const apiCreateApiKey = (name) => http.post('/admin/api-keys', { name })
export const apiListApiKeys  = ()     => http.get('/admin/api-keys')
export const apiRevokeApiKey = (id)   => http.delete(`/admin/api-keys/${id}`)

// ── Chat ─────────────────────────────────────
export const apiChat = (question, session_id, tag_ids, mode) => {
  const payload = { question, session_id }
  if (tag_ids && tag_ids.length) payload.tag_ids = tag_ids
  if (mode) payload.mode = mode
  return http.post('/chat/', payload)
}
export const apiConfirmAnswer = (logId) => http.post('/chat/confirm', { log_id: logId })
export const apiCreateShare  = (logId) => http.post(`/chat/share/${logId}`)
export const apiShareQA     = (shareToken) => http.get(`/chat/share/${shareToken}`)
export const apiSuggestions = ()      => http.get('/chat/suggestions')
export const apiChatHistory = (skip=0, limit=30) => http.get('/chat/history', { params: { skip, limit } })
// SSE 流式请求：使用 fetch + ReadableStream 以便通过 Header 传 token（避免 URL 泄露）
export const fetchStream = async (question, session_id, { onMessage, onError, onDone, onSources, tagIds, mode }) => {
  const token = sessionStorage.getItem('rag_token') || ''
  let url = `/api/chat/stream?question=${encodeURIComponent(question)}`
  if (session_id) url += `&session_id=${encodeURIComponent(session_id)}`
  if (tagIds && tagIds.length) url += `&tag_ids=${encodeURIComponent(tagIds.join(','))}`
  if (mode) url += `&mode=${encodeURIComponent(mode)}`
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
        // Parse JSON event format from SSE stream
        try {
          const parsed = JSON.parse(data)
          if (parsed && typeof parsed.token === 'string') {
            // Token event: {"token": "text"}
            onMessage(parsed.token)
          } else if (parsed && parsed.type === 'sources') {
            // Sources event: {"type": "sources", "data": [...]}
            onSources && onSources(parsed.data || [])
          } else if (parsed && parsed.type === 'done') {
            // Done event: {"type": "done"}
            onDone()
            return
          } else {
            onMessage(data)
          }
        } catch {
          // Fallback: plain text or legacy format
          onMessage(data)
        }
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
export const apiUpload         = (fd, overwrite=false) => http.post(`/documents/upload?overwrite=${overwrite}`, fd)
export const apiBatchUpload    = (fd)     => http.post('/documents/batch', fd, { timeout: 300_000 })
export const apiUrlImport      = (urls)   => http.post('/documents/import-url', { urls })
export const apiListDocs       = (skip=0, limit=30, tag='') => http.get('/documents/', { params: { skip, limit, tag: tag || undefined } })
export const apiGetDoc    = (id)              => http.get(`/documents/${id}`)
export const apiDeleteDoc = (id)              => http.delete(`/documents/${id}`)
export const apiRetryDoc  = (id)              => http.post(`/documents/${id}/retry`)
export const apiDocChunks = (id, skip=0, limit=50) => http.get(`/documents/${id}/chunks`, { params: { skip, limit } })
export const apiGetDocPermissions    = (id)                       => http.get(`/documents/${id}/permissions`)
export const apiAddDocPermission     = (id, scope_type, scope_value) => http.post(`/documents/${id}/permissions`, { scope_type, scope_value })
export const apiRemoveDocPermission  = (docId, permId)            => http.delete(`/documents/${docId}/permissions/${permId}`)

// ── Feedback ─────────────────────────────────
export const apiFeedback      = (data) => http.post('/feedback/', data)
export const apiFeedbackStats = ()     => http.get('/feedback/stats')

// ── Metrics ──────────────────────────────────
export const apiOverview     = ()       => http.get('/metrics/overview')
export const apiRagMetrics   = (days=7) => http.get('/metrics/rag', { params: { days } })
export const apiCacheMetrics = ()       => http.get('/metrics/cache')
export const apiDocMetrics   = ()       => http.get('/metrics/docs')
export const apiQPS          = ()       => http.get('/metrics/qps')
export const apiListBenchmarks  = (category='', limit=200)  => {
  const params = { limit }
  if (category) params.category = category
  return http.get('/metrics/benchmark', { params })
}
export const apiAddBenchmark    = (data)         => http.post('/metrics/benchmark', data)
export const apiRunBenchmark    = (category='')  => http.post('/metrics/benchmark/run', null, { params: category ? { category } : {}, timeout: 300_000 })
export const apiDeleteBenchmark = (id)           => http.delete(`/metrics/benchmark/${id}`)
export const apiLlmStatus       = ()             => http.get('/metrics/llm-status')

// ── Audit ────────────────────────────────────
export const apiAuditLogs = (page=1, limit=20, action='') =>
  http.get('/admin/users', { params: { skip: (page-1)*limit, limit } })

// ── Chunking ──────────────────────────────────
export const getChunkingProgress = (docId) => http.get(`/documents/${docId}/chunking/progress`)
export const getChunkingReport   = (docId) => http.get(`/documents/${docId}/chunking/report`)
export const getChunkDetail      = (docId, chunkId) => http.get(`/documents/${docId}/chunks/${chunkId}`)
export const triggerIncremental  = (docId) => http.post(`/documents/${docId}/chunking/incremental`)
export const getChunkingMetrics  = (params = {}) => http.get('/metrics/chunking', { params })
export const getChunkingEvents   = (params = {}) => http.get('/metrics/chunking/events', { params })

// ── Health（不需要 token，用单独 axios 实例）────
export const apiHealth = () =>
  axios.get('/api/health').then(r => {
    const b = r.data
    return (b && 'data' in b) ? b.data : b
  })
