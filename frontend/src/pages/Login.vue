<template>
  <div class="login-shell">
    <div class="login-card">
      <div class="login-logo">
        <div class="logo-box">
          <span class="logo-letter">R</span>
        </div>
        <span class="logo-text">RAG</span>
      </div>
      <p class="login-sub">// 企业级智能问答平台</p>

      <form @submit.prevent="doLogin" class="login-form">
        <div class="field">
          <label class="field-label">用户名</label>
          <input v-model="username" class="input-base field-input" placeholder="请输入用户名" autocomplete="username" :disabled="loading" />
        </div>
        <div class="field">
          <label class="field-label">密码</label>
          <input v-model="password" type="password" class="input-base field-input" placeholder="请输入密码" autocomplete="current-password" :disabled="loading" />
        </div>
        <div v-if="error" class="err-tip">{{ error }}</div>
        <button class="btn btn-primary login-btn" type="submit" :disabled="loading || !username || !password">
          <span v-if="loading" class="dots"><span/><span/><span/></span>
          <span v-else>系统登录</span>
        </button>
      </form>

      <div class="login-hint">默认账号：admin / admin123</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiLogin } from '@/api/index.js'

const router   = useRouter()
const username = ref('')
const password = ref('')
const loading  = ref(false)
const error    = ref('')

async function doLogin() {
  error.value   = ''
  loading.value = true
  try {
    const data = await apiLogin(username.value, password.value)
    sessionStorage.setItem('rag_token', data.token)
    sessionStorage.setItem('rag_user',  JSON.stringify(data.user))
    router.push('/')
  } catch (e) {
    error.value = typeof e === 'string' ? e : '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-shell {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  background: #0a0e27;
  position: relative;
  overflow: hidden;
}
.login-shell::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  background:
    radial-gradient(ellipse at 30% 40%, rgba(0,243,255,0.1) 0%, transparent 50%),
    radial-gradient(ellipse at 70% 60%, rgba(185,103,255,0.08) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 90%, rgba(255,0,110,0.06) 0%, transparent 50%);
  pointer-events: none;
}
.login-shell::after {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  background-image:
    linear-gradient(rgba(0,243,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,243,255,0.03) 1px, transparent 1px);
  background-size: 50px 50px;
  pointer-events: none;
}
.login-card {
  width: 400px;
  background: rgba(21,25,50,0.8);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(0,243,255,0.2);
  border-radius: 16px;
  padding: 44px 40px;
  position: relative;
  z-index: 1;
  box-shadow:
    0 0 30px rgba(0,243,255,0.05),
    inset 0 1px 0 rgba(0,243,255,0.1);
}
.login-logo {
  display: flex; align-items: center; gap: 12px; margin-bottom: 8px;
}
.logo-box {
  width: 42px; height: 42px;
  background: linear-gradient(135deg, #00f3ff, #b967ff);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 20px rgba(0,243,255,0.3);
}
.logo-letter {
  font-family: "Orbitron", sans-serif;
  font-size: 18px; font-weight: 800;
  color: #0a0e27;
}
.logo-text {
  font-family: "Orbitron", sans-serif;
  font-size: 24px; font-weight: 700;
  color: #00f3ff;
  text-shadow: 0 0 15px rgba(0,243,255,0.4);
  letter-spacing: 3px;
}
.login-sub {
  font-family: "JetBrains Mono", monospace;
  font-size: 12px; color: var(--text-3); margin-bottom: 32px;
  letter-spacing: 0.5px;
}
.login-form { display: flex; flex-direction: column; gap: 18px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label {
  font-family: "Orbitron", sans-serif;
  font-size: 10px; color: #00f3ff; font-weight: 600;
  letter-spacing: 1px; text-transform: uppercase;
}
.field-input { width: 100%; }
.err-tip {
  padding: 8px 12px;
  background: rgba(255,0,110,0.1);
  border: 1px solid rgba(255,0,110,0.3);
  border-radius: var(--r-sm);
  font-size: 12px; color: #ff006e;
}
.login-btn {
  width: 100%; justify-content: center; height: 42px; margin-top: 4px;
  font-family: "Orbitron", sans-serif;
  font-size: 12px; letter-spacing: 2px; text-transform: uppercase;
}
.login-hint {
  margin-top: 24px; text-align: center;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px; color: var(--text-3);
  padding: 8px;
  border: 1px dashed rgba(0,243,255,0.1);
  border-radius: 6px;
}
</style>
