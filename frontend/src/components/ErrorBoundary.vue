<template>
  <div v-if="hasErr" class="error-boundary">
    <p class="error-boundary__title">页面渲染异常</p>
    <p class="error-boundary__msg">{{ errMsg }}</p>
    <button type="button" class="error-boundary__btn" @click="reload">刷新页面</button>
  </div>
  <slot v-else />
</template>

<script setup>
import { ref, onErrorCaptured } from 'vue'

const hasErr = ref(false)
const errMsg = ref('')

onErrorCaptured((err) => {
  console.error(err)
  hasErr.value = true
  errMsg.value = err?.message || String(err)
  return false
})

function reload() {
  window.location.reload()
}
</script>

<style scoped>
.error-boundary {
  padding: 24px;
  max-width: 480px;
  margin: 40px auto;
  border: 1px solid rgba(255, 0, 110, 0.35);
  border-radius: 12px;
  background: rgba(255, 0, 110, 0.06);
  color: var(--text-1, #e8e8f0);
  font-size: 14px;
}
.error-boundary__title {
  font-weight: 600;
  margin: 0 0 8px;
  color: #ff6b9d;
}
.error-boundary__msg {
  margin: 0 0 16px;
  word-break: break-word;
  color: var(--text-2, #b0b8c8);
  font-size: 13px;
}
.error-boundary__btn {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid rgba(0, 243, 255, 0.35);
  background: rgba(0, 243, 255, 0.1);
  color: #00f3ff;
  cursor: pointer;
  font-size: 13px;
}
.error-boundary__btn:hover {
  background: rgba(0, 243, 255, 0.18);
}
</style>
