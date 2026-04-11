<template>
  <!-- 登录页不显示侧边栏 -->
  <div v-if="$route.path === '/login'" class="login-layout">
    <router-view/>
  </div>

  <!-- 主布局 -->
  <div v-else class="shell">
    <aside class="sidebar">
      <!-- Scan animation overlay -->
      <div class="sidebar-scan"></div>

      <!-- Logo -->
      <div class="brand">
        <div class="brand-icon">
          <span class="brand-letter">R</span>
        </div>
        <div class="brand-text">
          <span class="brand-name">RAG</span>
          <span class="brand-sub">知识库系统</span>
        </div>
      </div>

      <!-- Nav -->
      <nav class="nav">
        <div class="nav-group-label">主功能</div>
        <router-link to="/"        class="nav-link" active-class="nav-link--active" exact-active-class="nav-link--active">
          <IconChat class="nav-icon"/> <span>智能问答</span>
        </router-link>
        <router-link to="/docs"    class="nav-link" active-class="nav-link--active">
          <IconDocs class="nav-icon"/> <span>文档管理</span>
        </router-link>

        <div class="nav-group-label" style="margin-top:16px">运营</div>
        <router-link to="/metrics"  class="nav-link" active-class="nav-link--active">
          <IconMetrics class="nav-icon"/> <span>监控大盘</span>
        </router-link>
        <router-link to="/feedback" class="nav-link" active-class="nav-link--active">
          <IconFeedback class="nav-icon"/> <span>用户反馈</span>
        </router-link>

        <div class="nav-group-label" style="margin-top:16px">系统</div>
        <router-link to="/audit" class="nav-link" active-class="nav-link--active">
          <IconAudit class="nav-icon"/> <span>审计日志</span>
        </router-link>
        <router-link to="/admin" class="nav-link" active-class="nav-link--active">
          <IconAdmin class="nav-icon"/>
          <span>{{ isAdmin ? '用户管理' : '账户设置' }}</span>
        </router-link>
      </nav>

      <!-- User -->
      <div class="sidebar-footer">
        <div class="user-row">
          <div class="user-avatar">{{ userInitial }}</div>
          <div class="user-info">
            <div class="user-name">{{ userName }}</div>
            <div class="user-role">{{ userRole }}</div>
          </div>
          <button class="theme-btn" @click="toggleTheme" :title="isDark?'切换亮色':'切换暗色'">
            <svg v-if="isDark" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
          </button>
          <button class="logout-btn" @click="logout" title="退出登录">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          </button>
        </div>
        <div class="health-row">
          <span class="health-dot" :class="healthy?'ok':'err'"></span>
          <span class="health-label">{{ healthy ? '系统在线' : '连接异常' }}</span>
        </div>
      </div>
    </aside>

    <main class="main-content">
      <ErrorBoundary>
        <router-view/>
      </ErrorBoundary>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiHealth, apiLogout } from '@/api/index.js'
import ErrorBoundary from '@/components/ErrorBoundary.vue'

const router  = useRouter()
const healthy = ref(true)
const isDark  = ref(true)
let _healthTimer = null

// 主题初始化
onMounted(() => {
  const saved = localStorage.getItem('rag_theme')
  if (saved === 'light') { isDark.value = false; document.documentElement.setAttribute('data-theme', 'light') }
})

function toggleTheme() {
  isDark.value = !isDark.value
  if (isDark.value) {
    document.documentElement.removeAttribute('data-theme')
    localStorage.setItem('rag_theme', 'dark')
  } else {
    document.documentElement.setAttribute('data-theme', 'light')
    localStorage.setItem('rag_theme', 'light')
  }
}

// 读取本地存储的用户信息
const userInfo = computed(() => {
  try { return JSON.parse(localStorage.getItem('rag_user') || '{}') }
  catch { return {} }
})
const userName    = computed(() => userInfo.value.username || '用户')
const userInitial = computed(() => (userInfo.value.username || 'U').charAt(0).toUpperCase())
const userRole    = computed(() => ({ super_admin:'超级管理员', admin:'管理员', user:'普通用户' }[userInfo.value.role] || '用户'))
const isAdmin     = computed(() => ['admin', 'super_admin'].includes(userInfo.value.role))

onMounted(async () => {
  try { await apiHealth(); healthy.value = true }
  catch { healthy.value = false }
  _healthTimer = setInterval(async () => {
    try { await apiHealth(); healthy.value = true }
    catch { healthy.value = false }
  }, 30000)
})

onUnmounted(() => {
  if (_healthTimer) { clearInterval(_healthTimer); _healthTimer = null }
})

async function logout() {
  try { await apiLogout() } catch {}
  localStorage.removeItem('rag_token')
  localStorage.removeItem('rag_user')
  router.push('/login')
}

// 内联 SVG 图标组件
const IconChat     = { template: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 3h12M2 7h8M2 11h6"/></svg>` }
const IconDocs     = { template: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="1" width="12" height="14" rx="1.5"/><path d="M5 5h6M5 8h4"/></svg>` }
const IconMetrics  = { template: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 13V9l3-3 3 3 4-4v8"/></svg>` }
const IconFeedback = { template: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 1l1.9 3.8L14 5.6l-3 2.9.7 4.1L8 10.4l-3.7 2.2.7-4.1L2 5.6l4.1-.8z"/></svg>` }
const IconAudit    = { template: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M5 8h6M5 5h3M5 11h4"/></svg>` }
const IconAdmin    = { template: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="5" r="3"/><path d="M2 14c0-3 2.7-5 6-5s6 2 6 5"/></svg>` }
</script>

<style>
html, body, #app { height: 100%; }
</style>

<style scoped>
.login-layout { height: 100%; }

.shell {
  display: flex; height: 100vh; overflow: hidden;
  background: transparent;
}

/* ── Sidebar ── */
.sidebar {
  width: 240px; min-width: 240px;
  background: rgba(10,14,39,0.95);
  border-right: 1px solid rgba(0,243,255,0.15);
  display: flex; flex-direction: column;
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(20px);
}
.sidebar-scan {
  position: absolute;
  top: -100%;
  left: 0;
  width: 100%;
  height: 50%;
  background: linear-gradient(180deg, transparent, rgba(0,243,255,0.03), transparent);
  animation: scanline 8s linear infinite;
  pointer-events: none;
  z-index: 0;
}
.sidebar > *:not(.sidebar-scan) { position: relative; z-index: 1; }

.brand {
  display: flex; align-items: center; gap: 12px;
  padding: 20px 18px;
  border-bottom: 1px solid rgba(0,243,255,0.1);
}
.brand-icon {
  width: 36px; height: 36px;
  background: linear-gradient(135deg, #00f3ff, #b967ff);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 0 15px rgba(0,243,255,0.3);
}
.brand-letter {
  font-family: "Orbitron", sans-serif;
  font-size: 16px;
  font-weight: 800;
  color: #0a0e27;
}
.brand-text { display: flex; flex-direction: column; }
.brand-name {
  font-family: "Orbitron", sans-serif;
  font-size: 16px;
  font-weight: 700;
  color: #00f3ff;
  text-shadow: 0 0 10px rgba(0,243,255,0.4);
  letter-spacing: 2px;
}
.brand-sub {
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 1px;
}

.nav { flex: 1; padding: 12px 10px; display: flex; flex-direction: column; gap: 2px; overflow-y: auto; }
.nav-group-label {
  font-family: "Orbitron", sans-serif;
  font-size: 9px; font-weight: 600; color: var(--text-3);
  letter-spacing: 1.5px; padding: 8px 10px 4px;
  text-transform: uppercase;
}
.nav-link {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; border-radius: var(--r-sm);
  color: var(--text-2); text-decoration: none;
  font-size: 13px; font-weight: 500;
  transition: all .2s;
  border-left: 2px solid transparent;
  position: relative;
}
.nav-link:hover {
  background: rgba(0,243,255,0.05);
  color: var(--text-1);
  border-left-color: rgba(0,243,255,0.3);
}
.nav-link--active {
  background: rgba(0,243,255,0.08);
  color: #00f3ff;
  font-weight: 600;
  border-left-color: #00f3ff;
  text-shadow: 0 0 8px rgba(0,243,255,0.3);
}
.nav-icon { width: 15px; height: 15px; flex-shrink: 0; opacity: .6; }
.nav-link--active .nav-icon { opacity: 1; filter: drop-shadow(0 0 3px rgba(0,243,255,0.5)); }

.sidebar-footer {
  padding: 14px 18px;
  border-top: 1px solid rgba(0,243,255,0.1);
  display: flex; flex-direction: column; gap: 8px;
}
.user-row {
  display: flex; align-items: center; gap: 8px;
}
.user-avatar {
  width: 30px; height: 30px; border-radius: 50%;
  background: linear-gradient(135deg, #00f3ff, #b967ff);
  color: #0a0e27;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; flex-shrink: 0;
  box-shadow: 0 0 10px rgba(0,243,255,0.2);
}
.user-info { flex: 1; min-width: 0; }
.user-name { font-size: 12px; font-weight: 600; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-role { font-size: 10px; color: var(--text-3); }
.logout-btn {
  background: none; border: none; cursor: pointer;
  color: var(--text-3); padding: 4px; border-radius: 4px;
  display: flex; transition: all .2s;
}
.logout-btn:hover { color: #ff006e; filter: drop-shadow(0 0 4px rgba(255,0,110,0.4)); }
.theme-btn {
  background: none; border: none; cursor: pointer;
  color: var(--text-3); padding: 4px; border-radius: 4px;
  display: flex; transition: all .2s;
}
.theme-btn:hover { color: #00f3ff; filter: drop-shadow(0 0 4px rgba(0,243,255,0.4)); }
.health-row { display: flex; align-items: center; gap: 6px; }
.health-dot { width: 6px; height: 6px; border-radius: 50%; }
.health-dot.ok  { background: #05ffa1; box-shadow: 0 0 8px rgba(5,255,161,0.6); animation: neonPulse 2s infinite; }
.health-dot.err { background: #ff006e; box-shadow: 0 0 8px rgba(255,0,110,0.6); }
.health-label { font-size: 11px; color: var(--text-3); letter-spacing: 0.5px; }

/* ── Main ── */
.main-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
</style>
