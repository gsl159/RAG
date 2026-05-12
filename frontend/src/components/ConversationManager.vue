<template>
  <div class="conv-mgr">
    <!-- Search bar -->
    <div class="conv-search">
      <input
        v-model="searchQuery"
        class="conv-search-input"
        placeholder="搜索对话历史..."
        @input="debouncedSearch"
      />
      <svg class="conv-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
      </svg>
    </div>

    <!-- Actions -->
    <div class="conv-actions">
      <button class="btn btn-ghost btn-sm" @click="exportAll" title="导出全部对话">
        📥 导出全部
      </button>
      <button class="btn btn-ghost btn-sm" @click="$emit('new-session')" title="新建会话">
        ✨ 新会话
      </button>
    </div>

    <!-- Session list -->
    <div class="conv-list" ref="listRef">
      <div v-if="listLoading && !sessions.length" class="conv-empty">
        <span class="dots"><span/><span/><span/></span>
      </div>
      <div v-else-if="!sessions.length" class="conv-empty">
        {{ searchQuery ? '无匹配结果' : '暂无对话记录' }}
      </div>

      <div v-for="session in sessions" :key="session.id"
           class="conv-item"
           :class="{active: session.id === currentSessionId}"
           @click="$emit('load-session', session)">
        <div class="conv-item-main">
          <div class="conv-item-q">{{ session.question }}</div>
          <div class="conv-item-a" v-if="session.answer">{{ session.answer.slice(0, 80) }}{{ session.answer.length > 80 ? '...' : '' }}</div>
        </div>
        <div class="conv-item-meta">
          <span class="conv-item-intent" :class="`i-${(session.intent||'c2').toLowerCase()}`">
            {{ session.intent || 'C2' }}
          </span>
          <span class="conv-item-time">{{ fmtTime(session.created_at) }}</span>
          <div class="conv-item-actions">
            <button class="conv-act-btn" @click.stop="shareSession(session)" title="分享">🔗</button>
            <button class="conv-act-btn" @click.stop="exportSession(session)" title="导出">📄</button>
          </div>
        </div>
      </div>

      <!-- Infinite scroll sentinel -->
      <div ref="sentinel" class="conv-sentinel">
        <span v-if="listLoading" class="dots"><span/><span/><span/></span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { apiChatHistory, apiCreateShare } from '@/api/index.js'

const props = defineProps({
  currentSessionId: { type: String, default: '' },
})
const emit = defineEmits(['load-session', 'new-session'])

const searchQuery = ref('')
const sessions    = ref([])
const listLoading = ref(false)
const hasMore     = ref(true)
const total       = ref(0)
const listRef     = ref(null)
const sentinel    = ref(null)
let searchTimer   = null
let observer      = null

function fmtTime(s) {
  if (!s) return ''
  return new Date(s).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  })
}

// ── Data loading ──
async function loadSessions(reset = false) {
  if (listLoading.value) return
  if (!reset && !hasMore.value) return

  listLoading.value = true
  try {
    const skip = reset ? 0 : sessions.value.length
    const data = await apiChatHistory(skip, 30)
    const items = data.items || []
    total.value = data.total || 0

    if (reset) {
      sessions.value = items
    } else {
      sessions.value.push(...items)
    }
    hasMore.value = sessions.value.length < total.value
  } catch (e) {
    console.warn('加载对话历史失败:', e)
  } finally {
    listLoading.value = false
  }
}

// ── Search ──
function debouncedSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    filterLocal()
  }, 300)
}

function filterLocal() {
  // Client-side filter for simplicity
  // For large datasets, this should call a server-side search API
  if (!searchQuery.value.trim()) {
    loadSessions(true)
    return
  }
  const q = searchQuery.value.toLowerCase()
  sessions.value = sessions.value.filter(s =>
    (s.question || '').toLowerCase().includes(q) ||
    (s.answer || '').toLowerCase().includes(q)
  )
}

// ── Export ──
function exportSession(session) {
  const md = `# RAG 问答记录\n\n**时间:** ${session.created_at || '-'}\n**意图:** ${session.intent || '-'}\n\n**Q:** ${session.question}\n\n**A:** ${session.answer || '-'}\n`
  downloadMd(md, `qa_${(session.id || 'unknown').slice(0, 8)}.md`)
}

function exportAll() {
  if (!sessions.value.length) return
  const lines = sessions.value.map((s, i) => {
    return `## ${i + 1}. ${fmtTime(s.created_at)}\n\n**Q:** ${s.question}\n\n**A:** ${s.answer || '-'}\n`
  })
  const md = `# RAG 全部对话记录\n\n导出时间: ${new Date().toLocaleString('zh-CN')}\n共 ${sessions.value.length} 条记录\n\n---\n\n${lines.join('\n---\n\n')}`
  downloadMd(md, `all_conversations_${new Date().toISOString().slice(0, 10)}.md`)
}

function downloadMd(content, filename) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

// ── Share ──
async function shareSession(session) {
  if (!session.id) return
  try {
    const data = await apiCreateShare(session.id)
    const shareUrl = `${location.origin}/api/chat/share/${data.share_token || data.token || session.id}`
    await navigator.clipboard.writeText(shareUrl)
    alert('分享链接已复制到剪贴板')
  } catch (e) {
    // Fallback
    const url = `${location.origin}/api/chat/share/${session.id}`
    prompt('复制分享链接：', url)
  }
}

// ── Infinite scroll with IntersectionObserver ──
onMounted(() => {
  loadSessions(true)

  if (sentinel.value) {
    observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore.value && !listLoading.value) {
          loadSessions(false)
        }
      },
      { root: listRef.value, threshold: 0.1 }
    )
    observer.observe(sentinel.value)
  }
})

onUnmounted(() => {
  if (observer) observer.disconnect()
  clearTimeout(searchTimer)
})
</script>

<style scoped>
.conv-mgr {
  display: flex; flex-direction: column;
  height: 100%; overflow: hidden;
}

.conv-search {
  position: relative;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(0, 243, 255, 0.1);
}
.conv-search-input {
  width: 100%;
  background: rgba(10, 14, 39, 0.6);
  border: 1px solid rgba(0, 243, 255, 0.15);
  border-radius: 6px;
  color: var(--text-1);
  padding: 6px 10px 6px 28px;
  font-size: 12px;
  outline: none;
  transition: all 0.2s;
  font-family: inherit;
}
.conv-search-input:focus {
  border-color: #00f3ff;
  box-shadow: 0 0 8px rgba(0, 243, 255, 0.1);
}
.conv-search-input::placeholder { color: var(--text-3); }
.conv-search-icon {
  position: absolute;
  left: 20px; top: 50%; transform: translateY(-50%);
  color: var(--text-3);
  pointer-events: none;
}

.conv-actions {
  display: flex; gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(0, 243, 255, 0.06);
}

.conv-list {
  flex: 1; overflow-y: auto;
  padding: 4px 6px;
}
.conv-empty {
  padding: 30px 16px;
  text-align: center;
  font-size: 12px;
  color: var(--text-3);
}

.conv-item {
  padding: 10px 12px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 2px;
  border-left: 2px solid transparent;
}
.conv-item:hover {
  background: rgba(0, 243, 255, 0.05);
  border-left-color: rgba(0, 243, 255, 0.3);
}
.conv-item.active {
  background: rgba(0, 243, 255, 0.08);
  border-left-color: #00f3ff;
}

.conv-item-main { margin-bottom: 4px; }
.conv-item-q {
  font-size: 12px; color: var(--text-1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-weight: 500;
}
.conv-item-a {
  font-size: 11px; color: var(--text-3);
  margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.4;
}

.conv-item-meta {
  display: flex; align-items: center; gap: 6px;
  margin-top: 4px;
}
.conv-item-intent {
  font-size: 10px; font-weight: 600;
  padding: 1px 5px; border-radius: 3px;
}
.conv-item-time {
  font-size: 10px; color: var(--text-3);
  font-family: "JetBrains Mono", monospace;
}
.conv-item-actions {
  margin-left: auto;
  display: flex; gap: 2px;
  opacity: 0;
  transition: opacity 0.2s;
}
.conv-item:hover .conv-item-actions { opacity: 1; }
.conv-act-btn {
  background: none; border: none;
  cursor: pointer; font-size: 12px;
  padding: 2px 4px; border-radius: 3px;
  transition: background 0.2s;
}
.conv-act-btn:hover {
  background: rgba(0, 243, 255, 0.1);
}

.conv-sentinel {
  padding: 10px;
  text-align: center;
  min-height: 20px;
}
</style>
