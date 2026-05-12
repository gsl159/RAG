<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div v-for="t in toasts" :key="t.id" :class="['toast', 'toast-' + t.type]" @click="dismiss(t.id)">
          <span class="toast-icon">{{ iconMap[t.type] }}</span>
          <span class="toast-msg">{{ t.message }}</span>
          <button class="toast-close" @click.stop="dismiss(t.id)">&times;</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { toasts as sharedToasts, dismiss as sharedDismiss } from '@/toaster.js'

const toasts = ref([...sharedToasts])
const iconMap = { success: '✓', error: '✗', warning: '⚠', info: 'ℹ' }

onMounted(() => {
  window.__toastRef = { toasts }
})

function dismiss(id) {
  sharedDismiss(id)
  toasts.value = [...sharedToasts]
}
</script>

<style scoped>
.toast-container { position: fixed; top: 16px; right: 16px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; max-width: 380px; pointer-events: none; }
.toast { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-radius: 8px; font-size: 13px; line-height: 1.4; cursor: pointer; pointer-events: auto; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
.toast-success { background: #16a34a; color: #fff; }
.toast-error { background: #dc2626; color: #fff; }
.toast-warning { background: #f59e0b; color: #1a1a1a; }
.toast-info { background: var(--bg-2); color: var(--text-1); border: 1px solid var(--border); }
.toast-icon { font-size: 16px; flex-shrink: 0; }
.toast-msg { flex: 1; }
.toast-close { background: none; border: none; color: inherit; font-size: 18px; cursor: pointer; opacity: 0.6; padding: 0 4px; flex-shrink: 0; }
.toast-close:hover { opacity: 1; }
.toast-enter-active { transition: all 0.3s ease; }
.toast-leave-active { transition: all 0.2s ease; }
.toast-enter-from { opacity: 0; transform: translateX(40px); }
.toast-leave-to { opacity: 0; transform: translateX(40px); }
</style>
