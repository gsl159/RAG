// Global toast notification - available before Vue mounts
const toasts = []
let _id = 0

function show(message, type = 'info', duration = 4000) {
  const id = ++_id
  toasts.push({ id, message, type })
  if (duration > 0) setTimeout(() => dismiss(id), duration)
  // Force Vue reactivity if Toast component is mounted
  if (window.__toastRef) {
    window.__toastRef.toasts = [...toasts]
  }
}

function dismiss(id) {
  const idx = toasts.findIndex(t => t.id === id)
  if (idx >= 0) toasts.splice(idx, 1)
  if (window.__toastRef) {
    window.__toastRef.toasts = [...toasts]
  }
}

const $toast = {
  show,
  success: (m, d) => show(m, 'success', d || 4000),
  error: (m, d) => show(m, 'error', d || 6000),
  warning: (m, d) => show(m, 'warning', d || 4000),
  info: (m, d) => show(m, 'info', d || 4000),
}

window.$toast = $toast

export { $toast, toasts, dismiss }
